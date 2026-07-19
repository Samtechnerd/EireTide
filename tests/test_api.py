"""Tests for the ERDDAP CSV parsing logic in custom_components/irish_tides/api.py.

These only exercise pure parsing functions and don't require Home Assistant
to be installed.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest


def _load_irish_tides_module(name: str):
    """Load a module from custom_components/irish_tides/ without importing
    the package's __init__.py, which pulls in homeassistant."""
    package_dir = Path(__file__).resolve().parents[1] / "custom_components" / "irish_tides"
    package_name = "irish_tides_under_test"

    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = [str(package_dir)]
        sys.modules[package_name] = package

    full_name = f"{package_name}.{name}"
    spec = importlib.util.spec_from_file_location(full_name, package_dir / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[full_name] = module
    spec.loader.exec_module(module)
    return module


const = _load_irish_tides_module("const")
api = _load_irish_tides_module("api")


SCHEMA_WITH_CATEGORY = api.DatasetSchema(
    station_column="stationID",
    time_column="time",
    height_column="tide_height",
    category_column="tide_time_category",
)

SCHEMA_WITHOUT_CATEGORY = api.DatasetSchema(
    station_column="stationID",
    time_column="time",
    height_column="tide_height",
    category_column=None,
)


def test_parse_tide_events_with_category_column() -> None:
    csv_text = (
        "stationID,time,tide_height,tide_time_category\n"
        "Howth,2026-07-19T02:15:00Z,3.9,High Water\n"
        "Howth,2026-07-19T08:30:00Z,1.1,Low Water\n"
        "Howth,2026-07-19T14:40:00Z,4.0,High Water\n"
    )

    events = api.parse_tide_events(csv_text, SCHEMA_WITH_CATEGORY)

    assert len(events) == 3
    assert events[0].time == datetime(2026, 7, 19, 2, 15, tzinfo=timezone.utc)
    assert events[0].height_m == 3.9
    assert events[0].is_high is True
    assert events[1].is_high is False
    assert events[2].is_high is True


def test_parse_tide_events_infers_high_low_without_category() -> None:
    csv_text = (
        "stationID,time,tide_height\n"
        "Howth,2026-07-19T02:15:00Z,3.9\n"
        "Howth,2026-07-19T08:30:00Z,1.1\n"
        "Howth,2026-07-19T14:40:00Z,4.0\n"
        "Howth,2026-07-19T20:55:00Z,0.9\n"
    )

    events = api.parse_tide_events(csv_text, SCHEMA_WITHOUT_CATEGORY)

    assert [event.is_high for event in events] == [True, False, True, False]


def test_parse_tide_events_handles_erddap_units_suffixed_headers() -> None:
    # ERDDAP's tabledap .csvp responses fold units into the header itself
    # (e.g. "time" -> "time (UTC)") instead of using a separate units row.
    # This is the real response shape confirmed live against
    # erddap.marine.ie for the Howth station.
    schema = api.DatasetSchema(
        station_column="stationID",
        time_column="time",
        height_column="Water_Level_ODMalin",
        category_column="tide_time_category",
    )
    csv_text = (
        "stationID,time (UTC),longitude (degrees_east),latitude (degrees_north),"
        "tide_time_category,Water_Level_ODMalin (metres)\n"
        "Howth,2026-07-18T19:55:00Z,-6.0683,53.39148,LOW,-1.803\n"
        "Howth,2026-07-19T02:40:00Z,-6.0683,53.39148,HIGH,1.858\n"
    )

    events = api.parse_tide_events(csv_text, schema)

    assert len(events) == 2
    assert events[0].time == datetime(2026, 7, 18, 19, 55, tzinfo=timezone.utc)
    assert events[0].height_m == -1.803
    assert events[0].is_high is False
    assert events[1].is_high is True


def test_parse_tide_events_sorts_out_of_order_rows() -> None:
    csv_text = (
        "stationID,time,tide_height\n"
        "Howth,2026-07-19T14:40:00Z,4.0\n"
        "Howth,2026-07-19T02:15:00Z,3.9\n"
        "Howth,2026-07-19T08:30:00Z,1.1\n"
    )

    events = api.parse_tide_events(csv_text, SCHEMA_WITHOUT_CATEGORY)

    assert [event.time.hour for event in events] == [2, 8, 14]


def test_parse_tide_events_skips_rows_missing_time_or_height() -> None:
    csv_text = (
        "stationID,time,tide_height\n"
        "Howth,,3.9\n"
        "Howth,2026-07-19T08:30:00Z,\n"
        "Howth,2026-07-19T14:40:00Z,4.0\n"
    )

    events = api.parse_tide_events(csv_text, SCHEMA_WITHOUT_CATEGORY)

    assert len(events) == 1
    assert events[0].height_m == 4.0


def _event(hour: int, minute: int, height: float) -> api.TideEvent:
    return api.TideEvent(
        time=datetime(2026, 7, 19, hour, minute, tzinfo=timezone.utc),
        height_m=height,
        is_high=None,
        category_raw=None,
    )


def test_interpolated_height_at_the_endpoints_matches_the_events() -> None:
    low = _event(8, 30, 1.1)
    high = _event(14, 40, 4.0)

    assert api.interpolated_height_m([low, high], low.time) == 1.1
    assert api.interpolated_height_m([low, high], high.time) == 4.0


def test_interpolated_height_at_the_midpoint_is_the_average() -> None:
    low = _event(8, 0, 1.0)
    high = _event(14, 0, 3.0)
    midpoint = datetime(2026, 7, 19, 11, 0, tzinfo=timezone.utc)

    height = api.interpolated_height_m([low, high], midpoint)

    assert height == pytest.approx(2.0)


def test_interpolated_height_rises_slowly_near_the_low() -> None:
    # Cosine interpolation should ease in/out, so a quarter of the way
    # through the rise should be well short of a quarter of the height gain.
    low = _event(8, 0, 0.0)
    high = _event(12, 0, 4.0)
    quarter_time = datetime(2026, 7, 19, 9, 0, tzinfo=timezone.utc)

    height = api.interpolated_height_m([low, high], quarter_time)

    assert height is not None
    assert height < 1.0


def test_interpolated_height_returns_none_outside_the_known_range() -> None:
    low = _event(8, 0, 1.0)
    high = _event(14, 0, 3.0)

    before = datetime(2026, 7, 19, 7, 0, tzinfo=timezone.utc)
    after = datetime(2026, 7, 19, 15, 0, tzinfo=timezone.utc)

    assert api.interpolated_height_m([low, high], before) is None
    assert api.interpolated_height_m([low, high], after) is None


def test_resolve_header_matches_exact_or_units_suffixed_name() -> None:
    fieldnames = ["stationID", "time (UTC)", "Water_Level_ODMalin (metres)", "tide_time_category"]

    assert api._resolve_header(fieldnames, "stationID") == "stationID"
    assert api._resolve_header(fieldnames, "time") == "time (UTC)"
    assert api._resolve_header(fieldnames, "Water_Level_ODMalin") == "Water_Level_ODMalin (metres)"
    assert api._resolve_header(fieldnames, "tide_time_category") == "tide_time_category"
    assert api._resolve_header(fieldnames, "nonexistent") is None


def test_resolve_header_does_not_match_unrelated_prefix() -> None:
    # "time" must not match "timezone (whatever)" -- only an exact name or
    # "<name> (" should count.
    fieldnames = ["timezone (whatever)"]

    assert api._resolve_header(fieldnames, "time") is None


def test_pick_column_matches_keyword_case_insensitively() -> None:
    columns = ["stationID", "time", "tide_height", "TideTimeCategory"]

    assert api._pick_column(columns, "station") == "stationID"
    assert api._pick_column(columns, "height") == "tide_height"
    assert api._pick_column(columns, "categ") == "TideTimeCategory"
    assert api._pick_column(columns, "nonexistent") is None


def test_pick_column_respects_exclude() -> None:
    columns = ["time", "tide_time_category"]

    assert api._pick_column(columns, "time", exclude=("categ",)) == "time"


def test_fallback_stations_contains_default_station_and_no_duplicates() -> None:
    assert const.DEFAULT_STATION in const.FALLBACK_STATIONS
    assert len(const.FALLBACK_STATIONS) == len(set(const.FALLBACK_STATIONS))
    assert all(station.strip() for station in const.FALLBACK_STATIONS)
