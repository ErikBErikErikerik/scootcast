"""Tests for model/weather.py. They use a fixed sample answer and need no internet.

Run them with: python3 -m unittest discover tests

AI citation: this file was generated with Claude Code (model Claude Opus 5.5,
Anthropic) on 2026-11-27 and reviewed by Moritz.
"""

import sys
import unittest
from datetime import date
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "model"))

import weather

# Shortened Open-Meteo answer: three UTC hours around midnight Swiss time.
SAMPLE = {
    "hourly": {
        "time": ["2026-11-02T22:00", "2026-11-02T23:00", "2026-11-03T00:00"],
        "temperature_2m": [4.1, 3.8, None],
        "precipitation": [0.0, None, 1.2],
    }
}


class ParseHourlyTests(unittest.TestCase):
    def setUp(self):
        self.table = weather.parse_hourly(SAMPLE)

    def test_columns(self):
        self.assertEqual(list(self.table.columns), ["time", "temperature_c", "precipitation_mm"])

    def test_utc_is_converted_to_swiss_time(self):
        # In November Switzerland is one hour ahead of UTC: 23:00 UTC is midnight.
        self.assertEqual(str(self.table["time"].dt.tz), "Europe/Zurich")
        self.assertEqual(self.table["time"][1].hour, 0)
        self.assertEqual(self.table["time"][1].date(), date(2026, 11, 3))

    def test_missing_precipitation_counts_as_zero(self):
        self.assertEqual(self.table["precipitation_mm"][1], 0.0)

    def test_missing_temperature_stays_missing(self):
        self.assertTrue(self.table["temperature_c"].isna()[2])


class FetchWeatherTests(unittest.TestCase):
    def test_only_requested_local_days_are_kept(self):
        answer = mock.Mock()
        answer.json.return_value = SAMPLE
        with mock.patch.object(weather.requests, "get", return_value=answer) as get:
            table = weather.fetch_weather(date(2026, 11, 3), date(2026, 11, 3))
        # 22:00 UTC is 23:00 on 2.11. in Swiss time and is cut off.
        self.assertEqual(len(table), 2)
        self.assertTrue((table["time"].dt.date == date(2026, 11, 3)).all())
        # The request asks for UTC and one extra day on each side.
        params = get.call_args.kwargs["params"]
        self.assertEqual(params["timezone"], "GMT")
        self.assertEqual(params["start_date"], "2026-11-02")
        self.assertEqual(params["end_date"], "2026-11-04")


if __name__ == "__main__":
    unittest.main()
