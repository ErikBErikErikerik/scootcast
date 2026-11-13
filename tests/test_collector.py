"""Tests for the collector. Run them with: python3 -m unittest discover tests

AI citation: this file was generated with Claude Code (model Claude Opus 5.5,
Anthropic) on 2026-11-02 and reviewed by the project team.
"""

import sys
import tempfile
import unittest
from datetime import datetime
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "collector"))

from check_gaps import find_gaps
from collect import (
    CELL_SIZE_M,
    METERS_PER_DEGREE_LAT,
    append_snapshot,
    bike_from_map_item,
    cell_center,
    cell_id,
    count_vehicles,
    load_bikes,
    slot_already_saved,
    snapshot_slot,
)

ST_GALLEN_STATION = (47.4232, 9.3697)
BOX = (47.0, 48.0, 9.0, 10.0)


def bike(lat=47.5, lon=9.5, disabled=False, reserved=False):
    return {
        "lat": lat,
        "lon": lon,
        "is_disabled": disabled,
        "is_reserved": reserved,
        "provider_id": "dott",
        "vehicle_type_id": "dott:scooter",
    }


class GridTests(unittest.TestCase):
    def test_center_lies_in_its_own_cell(self):
        cell = cell_id(*ST_GALLEN_STATION)
        self.assertEqual(cell_id(*cell_center(cell)), cell)

    def test_position_is_close_to_its_cell_center(self):
        center_lat, _ = cell_center(cell_id(*ST_GALLEN_STATION))
        distance_m = abs(center_lat - ST_GALLEN_STATION[0]) * METERS_PER_DEGREE_LAT
        self.assertLessEqual(distance_m, CELL_SIZE_M / 2)

    def test_positions_400_m_apart_are_in_different_cells(self):
        north = ST_GALLEN_STATION[0] + 400 / METERS_PER_DEGREE_LAT
        self.assertNotEqual(cell_id(*ST_GALLEN_STATION), cell_id(north, ST_GALLEN_STATION[1]))


class SlotTests(unittest.TestCase):
    def test_rounds_down_to_the_city_interval(self):
        # 1793652505 is 2026-11-02 at 20:48:25 UTC.
        self.assertEqual(snapshot_slot(1793652505, 10), "2026-11-02T20:40:00Z")
        self.assertEqual(snapshot_slot(1793652505, 30), "2026-11-02T20:30:00Z")


class CountTests(unittest.TestCase):
    def test_same_cell_is_summed(self):
        counts = count_vehicles([bike(), bike()], BOX)
        self.assertEqual(list(counts.values()), [2])

    def test_unavailable_and_outside_vehicles_are_ignored(self):
        bikes = [bike(disabled=True), bike(reserved=True), bike(lat=46.0)]
        self.assertEqual(count_vehicles(bikes, BOX), {})

    def test_without_details_providers_are_merged(self):
        other_provider = {**bike(), "provider_id": "voi"}
        self.assertEqual(len(count_vehicles([bike(), other_provider], BOX)), 2)

        counts = count_vehicles([bike(), other_provider], BOX, detailed=False)
        self.assertEqual(counts, {(cell_id(47.5, 9.5), "all", "all"): 2})


class MapApiTests(unittest.TestCase):
    def map_item(self, provider, vehicle_type, pickup_type="free_floating"):
        return {
            "geometry": {"x": 9.37, "y": 47.42},
            "attributes": {
                "provider_id": provider,
                "pickup_type": pickup_type,
                "vehicle_type": [vehicle_type],
                "vehicle_status_disabled": False,
                "vehicle_status_reserved": False,
            },
        }

    def test_dott_types_match_the_feed(self):
        bike = bike_from_map_item(self.map_item("dott_st-gallen", "E-Scooter"))
        self.assertEqual(bike["vehicle_type_id"], "dott_st-gallen:dott_scooter")
        self.assertEqual((bike["lat"], bike["lon"]), (47.42, 9.37))

    def test_other_providers_keep_the_map_type(self):
        bike = bike_from_map_item(self.map_item("carvelo2go", "E-CargoBike"))
        self.assertEqual(bike["vehicle_type_id"], "carvelo2go:E-CargoBike")

    def test_stations_are_skipped(self):
        item = self.map_item("mobility", "E-Car", pickup_type="station_based")
        self.assertIsNone(bike_from_map_item(item))


class SourceTests(unittest.TestCase):
    def test_empty_feed_falls_back_to_the_map_api(self):
        empty_feed = {"last_updated": 1793652505, "data": {"bikes": []}}
        with mock.patch("collect.download_json", return_value=empty_feed), \
                mock.patch("collect.fetch_fallback_bikes", return_value=[bike()]):
            bikes, _, cities = load_bikes()
        self.assertEqual(bikes, [bike()])
        self.assertEqual(list(cities), ["st_gallen"])

    def test_full_feed_saves_all_cities(self):
        feed = {"last_updated": 1793652505, "data": {"bikes": [bike()]}}
        with mock.patch("collect.download_json", return_value=feed):
            bikes, updated, cities = load_bikes()
        self.assertEqual((bikes, updated), ([bike()], 1793652505))
        self.assertEqual(list(cities), ["st_gallen", "zurich"])


class StorageTests(unittest.TestCase):
    def test_saved_slot_is_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "city" / "day.csv"
            self.assertFalse(slot_already_saved(path, "2026-11-02T20:40:00Z"))

            append_snapshot(path, "2026-11-02T20:40:00Z", count_vehicles([bike()], BOX))
            self.assertTrue(slot_already_saved(path, "2026-11-02T20:40:00Z"))
            self.assertFalse(slot_already_saved(path, "2026-11-02T20:50:00Z"))

    def test_header_is_written_once(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "day.csv"
            counts = count_vehicles([bike()], BOX)
            append_snapshot(path, "2026-11-02T20:40:00Z", counts)
            append_snapshot(path, "2026-11-02T20:50:00Z", counts)
            self.assertEqual(path.read_text().count("timestamp"), 1)


class GapTests(unittest.TestCase):
    def test_missing_slots_are_counted(self):
        slots = [
            datetime(2026, 11, 2, 20, 0),
            datetime(2026, 11, 2, 20, 10),
            datetime(2026, 11, 2, 20, 40),
        ]
        self.assertEqual(find_gaps(slots, 10), [(datetime(2026, 11, 2, 20, 20), 2)])


if __name__ == "__main__":
    unittest.main()
