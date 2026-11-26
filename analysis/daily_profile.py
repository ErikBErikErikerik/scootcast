"""Print the average number of vehicles per hour at the named places.

Workdays and weekends are averaged separately, because the commuter pattern
only exists on workdays. Known outages are left out (see outages.csv).

Usage:
    python3 analysis/daily_profile.py st_gallen --vehicle scooter
    python3 analysis/daily_profile.py zurich

AI citation: this file was generated with Claude Code (model Claude Opus 5.5,
Anthropic) on 2026-11-26 and reviewed by the project team.
"""

import argparse
import statistics
from collections import defaultdict

from load_data import iter_snapshots
from places import PLACES

HOURS = (5, 7, 8, 9, 12, 15, 17, 18, 20, 23)


def hourly_counts(city, vehicle=None):
    """Return {(place, hour, is_weekend): [count per snapshot]} for full hours.

    vehicle: only count rows whose vehicle_type_id contains this text, such as
    "scooter". Zurich is saved without vehicle types, so it has no effect there.
    """
    place_of_cell = {cell: place for place, cells in PLACES[city].items() for cell in cells}
    per_snapshot = defaultdict(lambda: defaultdict(int))
    for row in iter_snapshots(city):
        if row["time"].minute != 0:
            continue
        if vehicle and row["vehicle_type_id"] != "all" and vehicle not in row["vehicle_type_id"]:
            continue
        # Make sure every snapshot exists, even if no vehicle stands at a place.
        counts = per_snapshot[row["time"]]
        place = place_of_cell.get(row["cell_id"])
        if place:
            counts[place] += row["count"]

    result = defaultdict(list)
    for time, counts in per_snapshot.items():
        for place in PLACES[city]:
            # A place without a row had no vehicle, so it counts as 0.
            result[(place, time.hour, time.weekday() >= 5)].append(counts[place])
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("city", choices=sorted(PLACES))
    parser.add_argument("--vehicle", help='only count this vehicle type, e.g. "scooter"')
    args = parser.parse_args()

    counts = hourly_counts(args.city, args.vehicle)
    print(f"{'place':18} {'days':8} " + " ".join(f"{hour:02}h" for hour in HOURS) + "   days  sd 9h")
    for place in PLACES[args.city]:
        for is_weekend, label in ((False, "workday"), (True, "weekend")):
            means = [counts[(place, hour, is_weekend)] for hour in HOURS]
            row = " ".join(f"{round(statistics.mean(m)) if m else '-':>3}" for m in means)
            at_nine = counts[(place, 9, is_weekend)]
            # The standard deviation at 9 o'clock shows how regular a place is.
            spread = round(statistics.pstdev(at_nine), 1) if at_nine else "-"
            print(f"{place:18} {label:8} {row}   {len(at_nine):4}  {spread:>5}")


if __name__ == "__main__":
    main()
