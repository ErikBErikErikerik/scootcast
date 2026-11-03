"""Save one snapshot of available shared vehicles per city, counted per grid cell.

The sharedmobility.ch API only shows the current state, so ScootCast builds its
own history: GitHub Actions runs this script every 10 minutes and appends the
counts to one CSV per city and UTC day (data/<city>/<YYYY-MM-DD>.csv). Each city
saves a new snapshot as often as its settings in CITIES say.

Each row has the columns: timestamp | cell_id | provider_id | vehicle_type_id | count
Vehicle IDs are deliberately not stored, because we do not track single vehicles.

Data source: Swiss Federal Office of Energy (BFE), sharedmobility.ch (GBFS feed,
and its map API as a fallback for St. Gallen when the feed fails).

AI citation: this file was generated with Claude Code (model Claude Opus 5.5,
Anthropic) on 2026-11-02 and reviewed by the project team.
"""

import csv
import gzip
import http.client
import json
import math
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

FEED_URL = "https://sharedmobility.ch/free_bike_status.json"
USER_AGENT = "ScootCast (HSG FCS student project)"
MAX_ATTEMPTS = 3
RETRY_WAIT_SECONDS = 10

# The server sometimes closes the connection early, which shows up as an
# incomplete read, a broken gzip stream or invalid JSON.
DOWNLOAD_ERRORS = (http.client.HTTPException, OSError, EOFError, ValueError)

# When the feed fails, the map API of sharedmobility.ch lists the same vehicles
# around a point, 50 per page. It is only used for St. Gallen (about 20 pages),
# because Zurich would need about 160 pages per snapshot.
FALLBACK_URL = "https://api.sharedmobility.ch/v1/sharedmobility/identify"
FALLBACK_CITY = "st_gallen"
FALLBACK_CENTER = (47.42, 9.36)
FALLBACK_RADIUS_M = 8000
FALLBACK_PAGE_SIZE = 50
FALLBACK_MAX_PAGES = 100

# The map API names vehicle types differently than the feed. Dott's types are
# translated to the feed's names, so both sources give the same IDs.
DOTT_VEHICLE_TYPES = {"E-Scooter": "dott_scooter", "E-Bike": "dott_bicycle"}

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CSV_COLUMNS = ["timestamp", "cell_id", "provider_id", "vehicle_type_id", "count"]

# The grid is fixed for all of Switzerland: one degree of longitude is converted
# to meters at a single reference latitude, so a cell ID never depends on a city.
CELL_SIZE_M = 200
REFERENCE_LATITUDE = 47.4
METERS_PER_DEGREE_LAT = 111_320
METERS_PER_DEGREE_LON = METERS_PER_DEGREE_LAT * math.cos(math.radians(REFERENCE_LATITUDE))

# Bounding boxes are (south, north, west, east) in degrees. Zurich is only a backup
# in case the St. Gallen feed fails. With 11 times as many rows it would add about
# 44 MB per day, so it is saved less often and without provider and vehicle type.
CITIES = {
    "st_gallen": {"box": (47.38, 47.46, 9.28, 9.44), "minutes": 10, "detailed": True},
    "zurich": {"box": (47.32, 47.44, 8.44, 8.63), "minutes": 30, "detailed": False},
}


def cell_id(lat, lon):
    """Return the ID ("<row>_<column>") of the grid cell containing a position."""
    row = math.floor(lat * METERS_PER_DEGREE_LAT / CELL_SIZE_M)
    column = math.floor(lon * METERS_PER_DEGREE_LON / CELL_SIZE_M)
    return f"{row}_{column}"


def cell_center(cell):
    """Return the (lat, lon) center of a grid cell, e.g. to draw it on the map."""
    row, column = (int(part) for part in cell.split("_"))
    lat = (row + 0.5) * CELL_SIZE_M / METERS_PER_DEGREE_LAT
    lon = (column + 0.5) * CELL_SIZE_M / METERS_PER_DEGREE_LON
    return lat, lon


def snapshot_slot(unix_time, minutes):
    """Round a Unix time down to a multiple of `minutes`, as an ISO string in UTC.

    GitHub Actions often starts late. The slot makes all snapshots line up and
    lets us notice when a slot was already saved or went missing.
    """
    moment = datetime.fromtimestamp(unix_time, tz=timezone.utc)
    moment = moment.replace(minute=moment.minute - moment.minute % minutes, second=0, microsecond=0)
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def download_json(url):
    """Download and parse JSON, retrying because a single failed call would leave a gap."""
    # Compressed, the feed is about 0.9 MB instead of 7 MB, which makes it less
    # likely that the server cuts the download off halfway.
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    request = urllib.request.Request(url, headers=headers)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
                if response.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return json.loads(body)
        except DOWNLOAD_ERRORS as error:
            print(f"Attempt {attempt}/{MAX_ATTEMPTS} failed: {error}")
            if attempt == MAX_ATTEMPTS:
                raise
            time.sleep(RETRY_WAIT_SECONDS)


def bike_from_map_item(item):
    """Convert one result of the map API to the feed's format, or None for a station."""
    attributes = item["attributes"]
    # Stations are listed too, but the feed only contains single vehicles.
    if attributes.get("pickup_type") != "free_floating":
        return None

    provider = attributes["provider_id"]
    vehicle_type = (attributes.get("vehicle_type") or ["unknown"])[0]
    if provider.startswith("dott"):
        vehicle_type = DOTT_VEHICLE_TYPES.get(vehicle_type, vehicle_type)

    return {
        "lat": item["geometry"]["y"],
        "lon": item["geometry"]["x"],
        "is_disabled": attributes.get("vehicle_status_disabled", False),
        "is_reserved": attributes.get("vehicle_status_reserved", False),
        "provider_id": provider,
        "vehicle_type_id": f"{provider}:{vehicle_type}",
    }


def fetch_fallback_bikes():
    """Download all vehicles around St. Gallen from the map API, page by page."""
    lat, lon = FALLBACK_CENTER
    bikes = []
    for page in range(FALLBACK_MAX_PAGES):
        query = urllib.parse.urlencode({
            "Geometry": f"{lon},{lat}",
            "Tolerance": FALLBACK_RADIUS_M,
            "geometryFormat": "esrijson",
            "offset": page * FALLBACK_PAGE_SIZE,
        })
        items = download_json(f"{FALLBACK_URL}?{query}")
        for item in items:
            bike = bike_from_map_item(item)
            if bike:
                bikes.append(bike)
        # A page that is not full is the last one.
        if len(items) < FALLBACK_PAGE_SIZE:
            return bikes
    raise RuntimeError(f"Map API returned more than {FALLBACK_MAX_PAGES} pages")


def count_vehicles(bikes, bounding_box, detailed=True):
    """Count the rentable vehicles inside a box.

    With `detailed` the counts are per (cell, provider, vehicle type). Without it
    they are per cell only, and the provider and vehicle type are set to "all".
    """
    south, north, west, east = bounding_box
    counts = Counter()
    for bike in bikes:
        # A disabled or reserved vehicle is on the map, but nobody can rent it.
        if bike["is_disabled"] or bike["is_reserved"]:
            continue
        if south <= bike["lat"] <= north and west <= bike["lon"] <= east:
            cell = cell_id(bike["lat"], bike["lon"])
            if detailed:
                counts[(cell, bike["provider_id"], bike["vehicle_type_id"])] += 1
            else:
                counts[(cell, "all", "all")] += 1
    return counts


def slot_already_saved(path, slot):
    """Check whether the slot is saved; rows are appended in time order."""
    if not path.exists():
        return False
    last_row = path.read_text().rstrip().rsplit("\n", 1)[-1]
    return last_row.split(",")[0] >= slot


def append_snapshot(path, slot, counts):
    """Append one snapshot to a daily CSV, creating the file with a header if new."""
    is_new_file = not path.exists()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        if is_new_file:
            writer.writerow(CSV_COLUMNS)
        for (cell, provider, vehicle_type), count in sorted(counts.items()):
            writer.writerow([slot, cell, provider, vehicle_type, count])


def main():
    try:
        feed = download_json(FEED_URL)
        bikes, updated, cities = feed["data"]["bikes"], feed["last_updated"], CITIES
    except DOWNLOAD_ERRORS as error:
        # Zurich is skipped and shows up as a gap in check_gaps.py.
        print(f"Feed failed ({error}), using the map API for {FALLBACK_CITY} only")
        bikes, updated = fetch_fallback_bikes(), time.time()
        cities = {FALLBACK_CITY: CITIES[FALLBACK_CITY]}

    any_city_empty = False
    for city, settings in cities.items():
        slot = snapshot_slot(updated, settings["minutes"])
        path = DATA_DIR / city / f"{slot[:10]}.csv"
        counts = count_vehicles(bikes, settings["box"], settings["detailed"])
        if not counts:
            # No rows are written, so the slot shows up as a gap in check_gaps.py.
            print(f"{city}: no vehicles in feed")
            any_city_empty = True
        elif slot_already_saved(path, slot):
            print(f"{city}: slot {slot} already saved")
        else:
            append_snapshot(path, slot, counts)
            print(f"{city}: {sum(counts.values())} vehicles in {len(counts)} rows at {slot}")

    # A failed run turns red in GitHub Actions, which is how we notice a feed outage.
    return 1 if any_city_empty else 0


if __name__ == "__main__":
    sys.exit(main())
