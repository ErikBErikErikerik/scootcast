"""Serve the current prediction model to the app.

This is the stable interface the app team builds against: the same three
functions keep working when the real ML model replaces the baseline inside.
Only the artifact in model/artifacts/ is read, never the raw snapshots in
data/, so the Streamlit Cloud deployment and the handed-in archive work
without the collected data.

The baseline artifact is produced by model/build_baseline.py. It stores, for
every cell that ever held a vehicle, the share of past snapshots in which it
held at least one rentable vehicle, grouped by vehicle type, workday/weekend
and hour of day.

AI citation: this file was generated with Claude Code (model Claude Opus 4.7,
Anthropic) on 2026-11-27 and reviewed by the project team.
"""

import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

MODEL_DIR = Path(__file__).resolve().parent
PROJECT_DIR = MODEL_DIR.parent
ARTIFACTS_DIR = MODEL_DIR / "artifacts"
BASELINE_FILE = ARTIFACTS_DIR / "baseline.csv"
METADATA_FILE = ARTIFACTS_DIR / "metadata.json"
LOCAL_TIME = ZoneInfo("Europe/Zurich")
VEHICLE_TYPES = ("scooter", "bike")

sys.path.insert(0, str(PROJECT_DIR / "collector"))
from collect import cell_center, cell_id  # noqa: E402

_cache = {}


def _load_baseline():
    """Return the baseline DataFrame, loading it from disk on first use."""
    if "baseline" not in _cache:
        _cache["baseline"] = pd.read_csv(BASELINE_FILE)
    return _cache["baseline"]


def _load_metadata():
    """Return the metadata dict, loading it from disk on first use."""
    if "metadata" not in _cache:
        with open(METADATA_FILE) as file:
            _cache["metadata"] = json.load(file)
    return _cache["metadata"]


def _reset_cache():
    """Drop the cached artifact so the next call reloads it. Used by tests."""
    _cache.clear()


def _as_local(when):
    """Return the datetime in Europe/Zurich; a naive input is assumed local."""
    if when.tzinfo is None:
        return when.replace(tzinfo=LOCAL_TIME)
    return when.astimezone(LOCAL_TIME)


def _check_vehicle(vehicle):
    """Raise ValueError if vehicle is not one of the supported types."""
    if vehicle not in VEHICLE_TYPES:
        raise ValueError(f"vehicle must be one of {VEHICLE_TYPES}, got {vehicle!r}")


def predict_cell(lat, lon, when, vehicle="scooter"):
    """Return the probability (0..1) that at least one vehicle stands in the cell.

    lat, lon: a position in St. Gallen; the containing 200-m grid cell is used.
    when:     a datetime in Europe/Zurich (naive is treated as local).
    vehicle:  "scooter" or "bike".

    Unknown cells and segments without any history return 0.0.
    """
    _check_vehicle(vehicle)
    when_local = _as_local(when)
    cell = cell_id(lat, lon)
    is_weekend = int(when_local.weekday() >= 5)
    hour = when_local.hour

    baseline = _load_baseline()
    match = baseline[
        (baseline["cell_id"] == cell)
        & (baseline["vehicle"] == vehicle)
        & (baseline["is_weekend"] == is_weekend)
        & (baseline["hour"] == hour)
    ]
    if match.empty:
        return 0.0
    return float(match["probability"].iloc[0])


def predict_grid(when, vehicle="scooter"):
    """Return one probability per known cell as a DataFrame.

    Columns: cell_id, lat, lon, probability.
    The frame covers every cell that has ever held a vehicle in the data;
    cells without history for this segment get probability 0.
    """
    _check_vehicle(vehicle)
    when_local = _as_local(when)
    is_weekend = int(when_local.weekday() >= 5)
    hour = when_local.hour

    baseline = _load_baseline()
    known_cells = pd.DataFrame({"cell_id": baseline["cell_id"].unique()})
    segment = baseline[
        (baseline["vehicle"] == vehicle)
        & (baseline["is_weekend"] == is_weekend)
        & (baseline["hour"] == hour)
    ][["cell_id", "probability"]]

    grid = known_cells.merge(segment, on="cell_id", how="left")
    grid["probability"] = grid["probability"].fillna(0.0)
    centers = [cell_center(cell) for cell in grid["cell_id"]]
    grid["lat"] = [lat for lat, _ in centers]
    grid["lon"] = [lon for _, lon in centers]
    return grid[["cell_id", "lat", "lon", "probability"]].reset_index(drop=True)


def model_report():
    """Return a dict with the model's name, description and build info.

    Used by the Streamlit model page, so callers may add new keys freely.
    """
    return dict(_load_metadata())
