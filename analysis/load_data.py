"""Read the collected snapshots for analysis and model training.

The collector only appends raw snapshots to data/<city>/<UTC day>.csv. This
module reads them back, converts the UTC timestamps to Swiss local time and
leaves out the known outages listed in analysis/outages.csv, so that every
analysis and the model use the same cleaned data.

The rows are yielded one by one instead of returned as a list, because
St. Gallen alone has more than a million rows.

AI citation: this file was generated with Claude Code (model Claude Opus 5.5,
Anthropic) on 2026-11-26 and reviewed by the project team.
"""

import csv
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ANALYSIS_DIR = Path(__file__).resolve().parent
DATA_DIR = ANALYSIS_DIR.parent / "data"
OUTAGES_FILE = ANALYSIS_DIR / "outages.csv"
LOCAL_TIME = ZoneInfo("Europe/Zurich")


def to_local_time(timestamp):
    """Convert a UTC timestamp like "2026-11-02T20:50:00Z" to Swiss local time."""
    return datetime.fromisoformat(timestamp.replace("Z", "+00:00")).astimezone(LOCAL_TIME)


def load_outages(city, path=OUTAGES_FILE):
    """Return the (start, end) UTC timestamps of the known outages of a city.

    Rows with the city "all" apply to every city. Both ends are inclusive.
    """
    with open(path, newline="") as file:
        return [(row["start"], row["end"]) for row in csv.DictReader(file)
                if row["city"] in (city, "all")]


def in_outage(timestamp, outages):
    """Check whether a UTC timestamp lies inside one of the outages."""
    # Timestamps in the same ISO format and time zone sort like the times they stand for.
    return any(start <= timestamp <= end for start, end in outages)


def iter_snapshots(city, skip_outages=True, data_dir=DATA_DIR):
    """Yield every saved row of a city as a dict, oldest first.

    Each row keeps the CSV columns and gets two changes: "count" is an int and
    "time" is the snapshot time in Swiss local time. Slots inside a known outage
    are left out unless skip_outages is False.
    """
    outages = load_outages(city) if skip_outages else []
    for path in sorted((data_dir / city).glob("*.csv")):
        with open(path, newline="") as file:
            last_timestamp = None
            for row in csv.DictReader(file):
                # All rows of one snapshot share a timestamp, so it is only
                # checked and converted once per snapshot.
                if row["timestamp"] != last_timestamp:
                    last_timestamp = row["timestamp"]
                    skip = in_outage(last_timestamp, outages)
                    time = to_local_time(last_timestamp)
                if skip:
                    continue
                row["count"] = int(row["count"])
                row["time"] = time
                yield row
