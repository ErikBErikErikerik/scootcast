"""Tests for the prediction interface. Run them with: python3 -m unittest discover tests

The tests build a tiny baseline artifact in a temporary directory and point
model.predict at it, so they do not depend on the current state of data/.

AI citation: this file was generated with Claude Code (model Claude Opus 4.7,
Anthropic) on 2026-11-27 and reviewed by the project team.
"""

import json
import shutil
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "collector"))

from model import predict  # noqa: E402
from collect import cell_center, cell_id  # noqa: E402

LOCAL = ZoneInfo("Europe/Zurich")
# Two cells inside the St. Gallen bounding box, picked by their coordinates.
BAHNHOF_LAT, BAHNHOF_LON = 47.4227, 9.3683
HSG_LAT, HSG_LON = 47.4317, 9.3763
BAHNHOF_CELL = cell_id(BAHNHOF_LAT, BAHNHOF_LON)
HSG_CELL = cell_id(HSG_LAT, HSG_LON)


class PredictTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = Path(tempfile.mkdtemp())
        artifacts = self.tempdir / "artifacts"
        artifacts.mkdir()
        pd.DataFrame(
            [
                (BAHNHOF_CELL, "scooter", 0, 8, 0.80),
                (BAHNHOF_CELL, "scooter", 1, 8, 0.30),
                (BAHNHOF_CELL, "bike", 0, 8, 0.10),
                (HSG_CELL, "scooter", 0, 8, 0.20),
            ],
            columns=["cell_id", "vehicle", "is_weekend", "hour", "probability"],
        ).to_csv(artifacts / "baseline.csv", index=False)
        (artifacts / "metadata.json").write_text(json.dumps({
            "name": "Test baseline",
            "description": "unit test fixture",
            "built_at": "2026-11-27T00:00:00+00:00",
            "n_snapshots": 100,
            "n_cells": 2,
            "data_from": "2026-11-02T00:00:00+01:00",
            "data_to": "2026-11-27T00:00:00+01:00",
        }))

        self._orig_baseline = predict.BASELINE_FILE
        self._orig_metadata = predict.METADATA_FILE
        predict.BASELINE_FILE = artifacts / "baseline.csv"
        predict.METADATA_FILE = artifacts / "metadata.json"
        predict._reset_cache()

    def tearDown(self):
        predict.BASELINE_FILE = self._orig_baseline
        predict.METADATA_FILE = self._orig_metadata
        predict._reset_cache()
        shutil.rmtree(self.tempdir)

    def test_predict_cell_returns_probability_for_known_cell(self):
        monday = datetime(2026, 11, 2, 8, 0, tzinfo=LOCAL)
        self.assertAlmostEqual(
            predict.predict_cell(BAHNHOF_LAT, BAHNHOF_LON, monday, "scooter"), 0.80
        )

    def test_predict_cell_returns_zero_for_unknown_cell(self):
        monday = datetime(2026, 11, 2, 8, 0, tzinfo=LOCAL)
        # A coordinate far outside St. Gallen (Zurich main station).
        self.assertEqual(predict.predict_cell(47.3779, 8.5403, monday, "scooter"), 0.0)

    def test_predict_cell_distinguishes_workday_and_weekend(self):
        monday = datetime(2026, 11, 2, 8, 0, tzinfo=LOCAL)
        saturday = datetime(2026, 11, 7, 8, 0, tzinfo=LOCAL)
        self.assertGreater(
            predict.predict_cell(BAHNHOF_LAT, BAHNHOF_LON, monday, "scooter"),
            predict.predict_cell(BAHNHOF_LAT, BAHNHOF_LON, saturday, "scooter"),
        )

    def test_predict_cell_distinguishes_vehicle_types(self):
        monday = datetime(2026, 11, 2, 8, 0, tzinfo=LOCAL)
        self.assertAlmostEqual(
            predict.predict_cell(BAHNHOF_LAT, BAHNHOF_LON, monday, "bike"), 0.10
        )

    def test_predict_cell_rejects_invalid_vehicle(self):
        monday = datetime(2026, 11, 2, 8, 0, tzinfo=LOCAL)
        with self.assertRaises(ValueError):
            predict.predict_cell(BAHNHOF_LAT, BAHNHOF_LON, monday, "car")

    def test_predict_cell_accepts_naive_local_datetime(self):
        naive = datetime(2026, 11, 2, 8, 0)
        self.assertAlmostEqual(
            predict.predict_cell(BAHNHOF_LAT, BAHNHOF_LON, naive, "scooter"), 0.80
        )

    def test_predict_grid_has_one_row_per_known_cell_with_coords(self):
        monday = datetime(2026, 11, 2, 8, 0, tzinfo=LOCAL)
        grid = predict.predict_grid(monday, "scooter")
        self.assertEqual(sorted(grid.columns), ["cell_id", "lat", "lon", "probability"])
        self.assertEqual(set(grid["cell_id"]), {BAHNHOF_CELL, HSG_CELL})
        bahnhof = grid[grid["cell_id"] == BAHNHOF_CELL].iloc[0]
        expected_lat, expected_lon = cell_center(BAHNHOF_CELL)
        self.assertAlmostEqual(bahnhof["lat"], expected_lat)
        self.assertAlmostEqual(bahnhof["lon"], expected_lon)
        self.assertAlmostEqual(bahnhof["probability"], 0.80)

    def test_predict_grid_fills_missing_segment_with_zero(self):
        # Monday 9h is not in the fixture; all cells should fall back to 0.
        monday_nine = datetime(2026, 11, 2, 9, 0, tzinfo=LOCAL)
        grid = predict.predict_grid(monday_nine, "scooter")
        self.assertTrue((grid["probability"] == 0.0).all())

    def test_model_report_contains_name_and_description(self):
        report = predict.model_report()
        self.assertIn("name", report)
        self.assertIn("description", report)
        self.assertEqual(report["n_cells"], 2)


if __name__ == "__main__":
    unittest.main()
