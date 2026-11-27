"""Compute the baseline probabilities that model/predict.py serves.

The baseline is the share of snapshots in which a 200-m grid cell held at
least one rentable vehicle, grouped by cell, vehicle type (scooter or bike),
workday/weekend and hour of day. This captures the strongest signal we see in
the data (the commuter pattern, weekday vs. weekend) without any model
training, so the app team can build the heatmap and the prediction page
against a stable interface while the real ML model is still in the works.

Usage:
    python3 model/build_baseline.py

Reads the cleaned snapshots through analysis/load_data.iter_snapshots (already
in Swiss local time and with known outages removed) and writes two small
files to model/artifacts/:
  - baseline.csv      one row per (cell, vehicle, is_weekend, hour) with hits
  - metadata.json     name, description, build time and data coverage

Only cells that were ever seen in the data are kept, which keeps the artifact
small; predict.py returns 0 for unknown cells. Rentable vehicles are counted
per snapshot, which matches the "at least one vehicle" question the app asks.

AI citation: this file was generated with Claude Code (model Claude Opus 4.7,
Anthropic) on 2026-11-27 and reviewed by the project team.
"""

import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

MODEL_DIR = Path(__file__).resolve().parent
PROJECT_DIR = MODEL_DIR.parent
ARTIFACTS_DIR = MODEL_DIR / "artifacts"

sys.path.insert(0, str(PROJECT_DIR / "analysis"))
from load_data import iter_snapshots  # noqa: E402

CITY = "st_gallen"
BASELINE_COLUMNS = ["cell_id", "vehicle", "is_weekend", "hour", "probability"]


def classify_vehicle(vehicle_type_id):
    """Map a raw vehicle_type_id to "scooter", "bike", or None.

    The data uses provider-prefixed IDs like "dott_st-gallen:dott_scooter" or
    "carvelo2go:E-CargoBike". Scooters contain "scooter"; bikes contain
    "bicycle" or come from carvelo2go (cargo bikes). "all" is the Zurich
    aggregate and is ignored because this baseline is for St. Gallen only.
    """
    if vehicle_type_id == "all":
        return None
    lower = vehicle_type_id.lower()
    if "scooter" in lower:
        return "scooter"
    if "bicycle" in lower or "bike" in lower or vehicle_type_id.startswith("carvelo2go:"):
        return "bike"
    return None


def collect_hits(city=CITY):
    """Walk the snapshots once and return (hits, snapshots_per_segment, meta).

    hits[(cell, vehicle, is_weekend, hour)] counts the snapshots in which this
    cell held at least one vehicle of this type. snapshots_per_segment[
    (is_weekend, hour)] counts how many distinct snapshots fell into that
    segment overall. The probability is hits / snapshots_per_segment.

    A snapshot is identified by its local time. Rows for the same snapshot
    arrive consecutively (iter_snapshots yields files in order), so we reset
    the "already seen in this snapshot" set when the time changes.
    """
    hits = Counter()
    snapshots_per_segment = Counter()
    known_cells = set()
    current_time = None
    current_segment = None
    seen_in_snapshot = set()
    first_time = None
    last_time = None

    for row in iter_snapshots(city):
        time = row["time"]
        if time != current_time:
            current_time = time
            current_segment = (time.weekday() >= 5, time.hour)
            seen_in_snapshot = set()
            snapshots_per_segment[current_segment] += 1
            if first_time is None or time < first_time:
                first_time = time
            if last_time is None or time > last_time:
                last_time = time

        vehicle = classify_vehicle(row["vehicle_type_id"])
        if vehicle is None:
            continue

        cell = row["cell_id"]
        known_cells.add(cell)
        key = (cell, vehicle)
        if key in seen_in_snapshot:
            continue
        seen_in_snapshot.add(key)
        hits[(cell, vehicle, current_segment[0], current_segment[1])] += 1

    total_snapshots = sum(snapshots_per_segment.values())
    meta = {
        "n_snapshots": total_snapshots,
        "n_cells": len(known_cells),
        "data_from": first_time.isoformat() if first_time else None,
        "data_to": last_time.isoformat() if last_time else None,
    }
    return hits, snapshots_per_segment, meta


def write_baseline(hits, snapshots_per_segment, path):
    """Write one row per (cell, vehicle, is_weekend, hour) with hits > 0."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as file:
        writer = csv.writer(file, lineterminator="\n")
        writer.writerow(BASELINE_COLUMNS)
        for (cell, vehicle, is_weekend, hour), count in sorted(hits.items()):
            total = snapshots_per_segment[(is_weekend, hour)]
            probability = count / total if total else 0.0
            writer.writerow([cell, vehicle, int(is_weekend), hour, f"{probability:.6f}"])


def write_metadata(meta, path):
    """Write the metadata.json that model_report() serves."""
    report = {
        "name": "Historical frequency baseline",
        "description": (
            "Share of past snapshots in which the cell held at least one "
            "rentable vehicle of the given type, computed per cell, "
            "workday/weekend and hour of day. Placeholder for the ML model."
        ),
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        **meta,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")


def main():
    """Build the baseline artifact from the stored snapshots."""
    hits, snapshots_per_segment, meta = collect_hits()
    baseline_path = ARTIFACTS_DIR / "baseline.csv"
    metadata_path = ARTIFACTS_DIR / "metadata.json"
    write_baseline(hits, snapshots_per_segment, baseline_path)
    write_metadata(meta, metadata_path)

    print(f"snapshots processed: {meta['n_snapshots']}")
    print(f"known cells:         {meta['n_cells']}")
    print(f"coverage:            {meta['data_from']} .. {meta['data_to']}")
    print(f"baseline rows:       {len(hits)}")
    print(f"written to:          {baseline_path}")


if __name__ == "__main__":
    main()
