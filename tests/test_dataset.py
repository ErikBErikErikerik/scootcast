"""Tests for model/build_dataset.py. Run with: python3 -m unittest discover tests

Each test writes a tiny CSV into a temporary data directory and calls
build() with data_dir=tmp, so no test depends on the current state of the
real data/ folder. The timestamps are chosen outside of analysis/outages.csv
except for the outage test, which deliberately uses a known outage window.

AI citation: this file was generated with Claude Code (model Claude Opus 4.7,
Anthropic) on 2026-11-27 and reviewed by the project team.
"""

import math
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import date  # noqa: E402

from model.build_dataset import (  # noqa: E402
    BASELINES,
    FEATURES_A,
    FEATURES_B,
    SPLIT_DATE,
    TARGETS,
    add_weather_features,
    build,
    calibrate_evening_baseline,
    split_by_day,
)

VEHICLE_TYPE = "dott_st-gallen:dott_scooter"
PROVIDER = "dott_st-gallen"
HEADER = "timestamp,cell_id,provider_id,vehicle_type_id,count\n"

# All test timestamps are in UTC, outside analysis/outages.csv unless noted.
# December 2026 is used so Switzerland is on CET (UTC+1) throughout; the
# fictitious test data has no risk of colliding with the DST change on
# 2026-10-25 or any real outage.


def _dummy_weather(start="2026-11-01", end="2026-12-15"):
    """Return a flat weather DF that covers any test timestamp in our range.

    Needed because build() calls load_weather() by default, which hits the
    Open-Meteo API; passing a dummy frame keeps the tests offline.
    """
    hours = pd.date_range(start, end, freq="h", tz="Europe/Zurich")
    return pd.DataFrame({
        "time": hours,
        "temperature_c": 10.0,
        "precipitation_mm": 0.0,
    })


def _write_city_data(data_dir, city, rows):
    """Write rows as one CSV per UTC day under data_dir/<city>/."""
    city_dir = data_dir / city
    city_dir.mkdir(parents=True, exist_ok=True)
    per_day = {}
    for timestamp, cell, count in rows:
        day = timestamp[:10]
        per_day.setdefault(day, []).append((timestamp, cell, count))
    for day, items in per_day.items():
        lines = [HEADER]
        for timestamp, cell, count in sorted(items):
            lines.append(f"{timestamp},{cell},{PROVIDER},{VEHICLE_TYPE},{count}\n")
        (city_dir / f"{day}.csv").write_text("".join(lines))


def _ts(day, hhmm):
    """Build a UTC ISO timestamp like '2026-10-20T08:00:00Z'."""
    return f"{day}T{hhmm}:00Z"


class BuildDatasetTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tempdir)

    def test_missing_cell_in_stored_slot_is_available_zero(self):
        rows = [
            (_ts("2026-12-01", "08:00"), "100_100", 1),
            (_ts("2026-12-01", "08:10"), "100_100", 1),
            (_ts("2026-12-01", "08:10"), "100_200", 1),
        ]
        _write_city_data(self.tempdir, "st_gallen", rows)
        df = build("scooter", 0.0, data_dir=self.tempdir, weather_df=_dummy_weather())
        # cell 100_200 has no vehicle at 08:00 UTC = 09:00 local, but the
        # slot was stored.
        row = df[(df["cell_id"] == "100_200") & (df["time"].dt.strftime("%H:%M") == "09:00")]
        self.assertEqual(len(row), 1)
        self.assertEqual(int(row.iloc[0]["available"]), 0)

    def test_vehicle_only_in_neighbour_gives_available_zero_and_nearby_one(self):
        # Two slots so both cells enter the catalog; in the second slot only
        # the neighbour has a vehicle.
        rows = [
            (_ts("2026-12-01", "08:00"), "100_100", 1),
            (_ts("2026-12-01", "08:00"), "100_101", 1),
            (_ts("2026-12-01", "08:10"), "100_100", 1),
        ]
        _write_city_data(self.tempdir, "st_gallen", rows)
        df = build("scooter", 0.0, data_dir=self.tempdir, weather_df=_dummy_weather())
        row = df[(df["cell_id"] == "100_101") & (df["time"].dt.strftime("%H:%M") == "09:10")]
        self.assertEqual(len(row), 1)
        self.assertEqual(int(row.iloc[0]["available"]), 0)
        self.assertEqual(int(row.iloc[0]["available_nearby"]), 1)

    def test_rate_cell_is_nan_on_first_day_and_does_not_see_day_d(self):
        # Two scenarios share Tue 2026-12-01 and differ on Tue 2026-12-08:
        # in scenario A the cell is available on day 8, in scenario B it is
        # not. rate_cell(day 8) must be identical in both, because day 8
        # does not enter its own rate. On day 1 rate_cell must be NaN.
        base_rows = [
            (_ts("2026-12-01", "08:00"), "100_100", 1),
            (_ts("2026-12-01", "08:00"), "100_200", 1),
        ]

        a_rows = base_rows + [
            (_ts("2026-12-08", "08:00"), "100_100", 1),
            (_ts("2026-12-08", "08:00"), "100_200", 1),
        ]
        a_dir = self.tempdir / "a"
        _write_city_data(a_dir, "st_gallen", a_rows)
        df_a = build("scooter", 0.0, data_dir=a_dir, weather_df=_dummy_weather())

        b_rows = base_rows + [
            # On day 8 cell 100_100 is missing (only 100_200 holds a vehicle).
            (_ts("2026-12-08", "08:00"), "100_200", 1),
        ]
        b_dir = self.tempdir / "b"
        _write_city_data(b_dir, "st_gallen", b_rows)
        df_b = build("scooter", 0.0, data_dir=b_dir, weather_df=_dummy_weather())

        def cell_100_100_rate_on(df, day_prefix):
            row = df[
                (df["cell_id"] == "100_100")
                & (df["time"].dt.strftime("%Y-%m-%d") == day_prefix)
                & (df["time"].dt.strftime("%H:%M") == "09:00")
            ]
            return row.iloc[0]["rate_cell"]

        rate_on_day_1_a = cell_100_100_rate_on(df_a, "2026-12-01")
        rate_on_day_8_a = cell_100_100_rate_on(df_a, "2026-12-08")
        rate_on_day_8_b = cell_100_100_rate_on(df_b, "2026-12-08")

        self.assertTrue(math.isnan(rate_on_day_1_a))
        self.assertAlmostEqual(rate_on_day_8_a, rate_on_day_8_b)
        self.assertAlmostEqual(rate_on_day_8_a, 1.0)  # day 1 was available

    def test_baseline_week_looks_back_exactly_seven_days(self):
        # Day 1 08:30 UTC = 09:30 local, cell A available.
        # Day 8 08:30 UTC = 09:30 local, cell X holds a vehicle so the slot
        # exists, but we check the baseline for cell A (which is in the
        # catalog because it was seen on day 1).
        rows = [
            (_ts("2026-12-01", "08:30"), "100_100", 1),
            (_ts("2026-12-01", "08:30"), "100_200", 1),
            (_ts("2026-12-08", "08:30"), "100_200", 1),
        ]
        _write_city_data(self.tempdir, "st_gallen", rows)
        df = build("scooter", 0.0, data_dir=self.tempdir, weather_df=_dummy_weather())
        row = df[
            (df["cell_id"] == "100_100")
            & (df["time"].dt.strftime("%Y-%m-%d %H:%M") == "2026-12-08 09:30")
        ]
        self.assertEqual(len(row), 1)
        self.assertEqual(int(row.iloc[0]["baseline_week"]), 1)
        self.assertEqual(int(row.iloc[0]["available"]), 0)

    def test_evening_count_uses_22h_slot_not_22h30(self):
        # Day 1 evening in local time: 21:00 UTC = 22:00 local, 21:30 UTC =
        # 22:30 local. Both have the same cell with different counts; the
        # feature for day 2 must pick 22:00 local.
        rows = [
            (_ts("2026-12-01", "21:00"), "100_100", 5),
            (_ts("2026-12-01", "21:30"), "100_100", 7),
            (_ts("2026-12-02", "07:00"), "100_100", 1),
        ]
        _write_city_data(self.tempdir, "st_gallen", rows)
        df = build("scooter", 0.0, data_dir=self.tempdir, weather_df=_dummy_weather())
        day_2 = df[
            (df["cell_id"] == "100_100")
            & (df["time"].dt.strftime("%Y-%m-%d %H:%M") == "2026-12-02 08:00")
        ]
        self.assertEqual(len(day_2), 1)
        self.assertEqual(int(day_2.iloc[0]["evening_count_cell"]), 5)

    def test_outage_slots_are_filtered(self):
        # 2026-11-03T08:40Z..08:50Z is in analysis/outages.csv for st_gallen.
        # A slot inside that window must disappear; a slot just outside
        # (09:00Z) must remain.
        rows = [
            (_ts("2026-11-03", "08:40"), "100_100", 1),
            (_ts("2026-11-03", "09:00"), "100_100", 1),
        ]
        _write_city_data(self.tempdir, "st_gallen", rows)
        df = build("scooter", 0.0, data_dir=self.tempdir, weather_df=_dummy_weather())
        times = set(df["time"].dt.strftime("%Y-%m-%dT%H:%M:%SZ%z").tolist())
        # Convert back: 09:00 UTC = 10:00 local.
        self.assertTrue(any("10:00:00" in t for t in times))
        self.assertFalse(any("09:40:00" in t for t in times))  # 08:40 UTC is 09:40 local

    def test_column_lists_cover_every_non_identity_column(self):
        # The constants that train.py imports must stay consistent with the
        # saved table layout.
        rows = [
            (_ts("2026-10-20", "08:00"), "100_100", 1),
            (_ts("2026-10-20", "08:10"), "100_100", 1),
        ]
        _write_city_data(self.tempdir, "st_gallen", rows)
        df = build("scooter", 0.0, data_dir=self.tempdir, weather_df=_dummy_weather())
        identity = {"time", "cell_id", "vehicle"}
        documented = set(FEATURES_A + FEATURES_B + TARGETS + BASELINES)
        self.assertEqual(set(df.columns) - identity, documented)

    def test_weather_joins_by_hourly_ceil(self):
        # Open-Meteo's precipitation at 08:00 is the rain from 07:00 to 08:00,
        # so a slot at 07:10 belongs to the 08:00 weather row. A slot at
        # exactly 08:00 also keeps 08:00 (ceil of an aligned hour is itself).
        tz = "Europe/Zurich"
        base = pd.DataFrame({
            "time": pd.to_datetime(
                ["2026-12-01 07:10", "2026-12-01 08:00", "2026-12-01 08:10"]
            ).tz_localize(tz),
            "cell_id": ["100_100"] * 3,
        })
        wx = pd.DataFrame({
            "time": pd.to_datetime(
                ["2026-12-01 07:00", "2026-12-01 08:00", "2026-12-01 09:00"]
            ).tz_localize(tz),
            "temperature_c": [5.0, 7.0, 9.0],
            "precipitation_mm": [0.1, 0.2, 0.3],
        })
        result = add_weather_features(base, wx).sort_values("time").reset_index(drop=True)
        # 07:10 -> ceil 08:00
        self.assertAlmostEqual(result.iloc[0]["temperature_c"], 7.0)
        self.assertAlmostEqual(result.iloc[0]["precipitation_mm"], 0.2)
        # 08:00 -> ceil 08:00 (unchanged)
        self.assertAlmostEqual(result.iloc[1]["temperature_c"], 7.0)
        self.assertAlmostEqual(result.iloc[1]["precipitation_mm"], 0.2)
        # 08:10 -> ceil 09:00
        self.assertAlmostEqual(result.iloc[2]["temperature_c"], 9.0)
        self.assertAlmostEqual(result.iloc[2]["precipitation_mm"], 0.3)

    def test_missing_weather_hour_stays_nan(self):
        tz = "Europe/Zurich"
        base = pd.DataFrame({
            "time": pd.to_datetime(["2026-12-01 10:00"]).tz_localize(tz),
            "cell_id": ["100_100"],
        })
        # weather only has 08:00, so 10:00 has no matching hour.
        wx = pd.DataFrame({
            "time": pd.to_datetime(["2026-12-01 08:00"]).tz_localize(tz),
            "temperature_c": [7.0],
            "precipitation_mm": [0.2],
        })
        result = add_weather_features(base, wx)
        self.assertTrue(math.isnan(result.iloc[0]["temperature_c"]))
        self.assertTrue(math.isnan(result.iloc[0]["precipitation_mm"]))

    def test_baseline_evening_is_calibrated_from_training_per_is_weekend(self):
        # Pre-split training rows teach the two probabilities:
        #   workday, ev>0: available mean = 2/3 (two out of three)
        #   workday, ev==0: available mean = 0
        #   weekend, ev>0: available mean = 1 (one of one)
        # Post-split rows then receive those numbers depending on their
        # own (is_weekend, evening_count_cell>0) cell. NaN evening_count
        # keeps baseline_evening NaN.
        tz = "Europe/Zurich"
        times = pd.to_datetime([
            "2026-11-10 09:00",  # train, workday, ev>0, avail=1
            "2026-11-10 10:00",  # train, workday, ev>0, avail=0
            "2026-11-10 11:00",  # train, workday, ev>0, avail=1
            "2026-11-10 12:00",  # train, workday, ev==0, avail=0
            "2026-11-14 09:00",  # train, weekend (Sat), ev>0, avail=1
            "2026-11-25 09:00",  # test, workday, ev>0 -> expect 2/3
            "2026-11-25 10:00",  # test, workday, ev==0 -> expect 0
            "2026-11-28 09:00",  # test, weekend, ev>0 -> expect 1
            "2026-11-25 11:00",  # test, workday, ev NaN -> expect NaN
        ]).tz_localize(tz)
        df = pd.DataFrame({
            "time": times,
            "cell_id": ["100_100"] * 9,
            "is_weekend": [0, 0, 0, 0, 1, 0, 0, 1, 0],
            "evening_count_cell": [5, 5, 5, 0, 5, 5, 0, 5, float("nan")],
            "available": [1, 0, 1, 0, 1, 0, 0, 0, 0],
        })
        out = calibrate_evening_baseline(df, split_date=date(2026, 11, 21))
        got = out.set_index("time")["baseline_evening"]
        self.assertAlmostEqual(got[pd.Timestamp("2026-11-25 09:00", tz=tz)], 2 / 3)
        self.assertEqual(got[pd.Timestamp("2026-11-25 10:00", tz=tz)], 0.0)
        self.assertEqual(got[pd.Timestamp("2026-11-28 09:00", tz=tz)], 1.0)
        self.assertTrue(math.isnan(got[pd.Timestamp("2026-11-25 11:00", tz=tz)]))
        self.assertIn("baseline_evening", BASELINES)

    def test_split_by_day_is_strict_on_the_split_date(self):
        # Build a frame spanning the SPLIT_DATE boundary.
        before = SPLIT_DATE - pd.Timedelta(days=1).to_pytimedelta()
        times = pd.to_datetime(
            [f"{before.isoformat()}T10:00:00", f"{SPLIT_DATE.isoformat()}T10:00:00"]
        ).tz_localize("Europe/Zurich")
        df = pd.DataFrame({"time": times, "cell_id": ["a", "b"]})
        train, test = split_by_day(df)
        self.assertEqual(len(train), 1)
        self.assertEqual(len(test), 1)
        self.assertEqual(train.iloc[0]["cell_id"], "a")
        self.assertEqual(test.iloc[0]["cell_id"], "b")


if __name__ == "__main__":
    unittest.main()
