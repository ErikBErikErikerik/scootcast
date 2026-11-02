"""Report which snapshots are missing from the collected data.

Run it with: python3 collector/check_gaps.py

AI citation: this file was generated with Claude Code (model Claude Opus 5.5,
Anthropic) on 2026-11-02 and reviewed by the project team.
"""

import csv
from datetime import datetime, timedelta

from collect import CITIES, DATA_DIR

TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def find_gaps(slots, minutes):
    """Return (first missing slot, number of missing slots) for each hole in a sorted list."""
    step = timedelta(minutes=minutes)
    gaps = []
    for previous, current in zip(slots, slots[1:]):
        missing = (current - previous) // step - 1
        if missing > 0:
            gaps.append((previous + step, missing))
    return gaps


def load_slots(city):
    """Return the sorted, distinct snapshot times saved for a city."""
    slots = set()
    for path in sorted((DATA_DIR / city).glob("*.csv")):
        with path.open(newline="") as file:
            slots.update(row["timestamp"] for row in csv.DictReader(file))
    return sorted(datetime.strptime(slot, TIME_FORMAT) for slot in slots)


def main():
    for city, settings in CITIES.items():
        slots = load_slots(city)
        if not slots:
            print(f"{city}: no data yet")
            continue

        minutes = settings["minutes"]
        gaps = find_gaps(slots, minutes)
        missing = sum(count for _, count in gaps)
        coverage = len(slots) / (len(slots) + missing)
        print(f"{city}: {len(slots)} snapshots, {missing} missing ({coverage:.1%} coverage)")
        for start, count in gaps:
            print(f"  {start:{TIME_FORMAT}}: {count * minutes} minutes missing")


if __name__ == "__main__":
    main()
