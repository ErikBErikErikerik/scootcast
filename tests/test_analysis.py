"""Tests for the analysis helpers. Run them with: python3 -m unittest discover tests

AI citation: this file was generated with Claude Code (model Claude Opus 5.5,
Anthropic) on 2026-11-26 and reviewed by the project team.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "analysis"))

from load_data import in_outage, iter_snapshots, load_outages, to_local_time

CSV_HEADER = "timestamp,cell_id,provider_id,vehicle_type_id,count\n"


class LoadDataTests(unittest.TestCase):
    def test_utc_is_converted_to_swiss_time(self):
        # In November Switzerland is one hour ahead of UTC.
        self.assertEqual(to_local_time("2026-11-02T20:50:00Z").hour, 21)

    def test_outage_ends_are_inclusive(self):
        outages = [("2026-11-08T07:40:00Z", "2026-11-08T12:20:00Z")]
        self.assertTrue(in_outage("2026-11-08T07:40:00Z", outages))
        self.assertTrue(in_outage("2026-11-08T12:20:00Z", outages))
        self.assertFalse(in_outage("2026-11-08T12:30:00Z", outages))

    def test_listed_outages_are_valid(self):
        for city in ("st_gallen", "zurich"):
            for start, end in load_outages(city):
                self.assertLessEqual(start, end)

    def test_outage_rows_are_skipped(self):
        with tempfile.TemporaryDirectory() as folder:
            day = Path(folder) / "st_gallen" / "2026-11-03.csv"
            day.parent.mkdir()
            day.write_text(
                CSV_HEADER
                + "2026-11-03T11:10:00Z,1_1,dott,dott:scooter,2\n"
                + "2026-11-03T11:30:00Z,1_1,dott,dott:scooter,5\n"
            )
            rows = list(iter_snapshots("st_gallen", data_dir=Path(folder)))
            all_rows = list(iter_snapshots("st_gallen", skip_outages=False, data_dir=Path(folder)))

        # 11:30 UTC lies in the listed Dott outage of 2026-11-03.
        self.assertEqual([row["count"] for row in rows], [2])
        self.assertEqual(len(all_rows), 2)


if __name__ == "__main__":
    unittest.main()
