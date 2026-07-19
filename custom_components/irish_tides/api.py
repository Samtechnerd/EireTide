"""Client for the Marine Institute ERDDAP tide prediction service.

The dataset is queried through ERDDAP's tabledap CSV interface
(https://erddap.marine.ie/erddap/tabledap/IMI_TidePrediction_HighLow). Rather
than hardcoding the dataset's column names -- which ERDDAP deployments can
rename -- the actual variable names are discovered up front from the
dataset's ``info`` endpoint and then used to build every subsequent query.
High/low classification falls back to comparing neighbouring tide heights
when the category text is missing or unrecognised, so parsing does not
depend on knowing the exact wording the server uses for that column either.
"""
from __future__ import annotations

import csv
import io
import logging
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import quote

import aiohttp

from .const import DATASET_ID, ERDDAP_BASE_URL, REQUEST_TIMEOUT

_LOGGER = logging.getLogger(__name__)


class ErddapError(Exception):
    """Raised when the ERDDAP server can't be reached or returns unexpected data."""


@dataclass
class TideEvent:
    """A single predicted high or low tide."""

    time: datetime
    height_m: float | None
    is_high: bool | None
    category_raw: str | None


@dataclass
class DatasetSchema:
    """Resolved column names for the tide prediction dataset."""

    station_column: str
    time_column: str
    height_column: str
    category_column: str | None


def _pick_column(
    columns: list[str], *keywords: str, exclude: tuple[str, ...] = ()
) -> str | None:
    for column in columns:
        lowered = column.lower()
        if any(bad in lowered for bad in exclude):
            continue
        if any(keyword in lowered for keyword in keywords):
            return column
    return None


async def _get_text(session: aiohttp.ClientSession, url: str) -> str:
    _LOGGER.debug("Requesting %s", url)
    timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT)
    async with session.get(url, timeout=timeout) as response:
        if response.status == 404:
            raise ErddapError(f"No data found for query: {url}")
        if response.status >= 400:
            body = await response.text()
            raise ErddapError(
                f"ERDDAP request failed with status {response.status}: {body[:300]}"
            )
        return await response.text()


async def async_discover_schema(session: aiohttp.ClientSession) -> DatasetSchema:
    """Discover the dataset's real column names from ERDDAP's info endpoint.

    Unlike tabledap, the info endpoint has no units row to strip, so it only
    serves plain .csv (not .csvp).
    """
    url = f"{ERDDAP_BASE_URL}/info/{DATASET_ID}/index.csv"
    text = await _get_text(session, url)

    reader = csv.DictReader(io.StringIO(text))
    variables: list[str] = []
    for row in reader:
        if row.get("Row Type") == "variable":
            name = row.get("Variable Name")
            if name:
                variables.append(name)

    if not variables:
        raise ErddapError(f"Could not read the variable list for dataset {DATASET_ID}")

    station_column = _pick_column(variables, "station")
    time_column = _pick_column(variables, "time", exclude=("categ",)) or "time"
    height_column = _pick_column(variables, "height", "level")
    category_column = _pick_column(variables, "categ", "type", "sign")

    if not station_column or not height_column:
        raise ErddapError(
            f"Unexpected schema for dataset {DATASET_ID}, variables found: {variables}"
        )

    return DatasetSchema(
        station_column=station_column,
        time_column=time_column,
        height_column=height_column,
        category_column=category_column,
    )


def _resolve_header(fieldnames: list[str], column: str) -> str | None:
    """Match a discovered column name against an actual CSV header.

    ERDDAP's .csvp tabledap responses fold a variable's units into its
    header instead of using a separate units row, e.g. the "time" variable
    comes back as the header "time (UTC)". Columns with no units (like
    stationID) still come back unchanged, so both forms need handling.
    """
    for name in fieldnames:
        if name == column or name.startswith(f"{column} ("):
            return name
    return None


async def async_get_station_list(
    session: aiohttp.ClientSession, schema: DatasetSchema
) -> list[str]:
    """Return the sorted, distinct list of station names known to the dataset."""
    column = quote(schema.station_column, safe="")
    url = f"{ERDDAP_BASE_URL}/tabledap/{DATASET_ID}.csvp?{column}&distinct()"
    text = await _get_text(session, url)

    reader = csv.DictReader(io.StringIO(text))
    station_key = _resolve_header(reader.fieldnames or [], schema.station_column)
    if station_key is None:
        raise ErddapError(
            f"Station column '{schema.station_column}' not found in response headers: "
            f"{reader.fieldnames}"
        )

    stations = {row[station_key].strip() for row in reader if row.get(station_key)}
    return sorted(stations)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def async_get_tide_events(
    session: aiohttp.ClientSession,
    schema: DatasetSchema,
    station_id: str,
    start: datetime,
    end: datetime,
) -> list[TideEvent]:
    """Fetch predicted high/low tide events for a station within a time window."""
    station_value = quote(f'"{station_id}"', safe="")
    query = (
        f"{schema.station_column}={station_value}"
        f"&{schema.time_column}%3E={_iso(start)}"
        f"&{schema.time_column}%3C={_iso(end)}"
    )
    # No variable list is given (we want every column), but ERDDAP still
    # requires something before the first constraint's leading '&' -- an
    # empty variable list satisfies that.
    url = f"{ERDDAP_BASE_URL}/tabledap/{DATASET_ID}.csvp?&{query}"
    text = await _get_text(session, url)
    return parse_tide_events(text, schema)


def parse_tide_events(text: str, schema: DatasetSchema) -> list[TideEvent]:
    """Parse an ERDDAP csvp response into a chronological list of tide events."""
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = reader.fieldnames or []
    time_key = _resolve_header(fieldnames, schema.time_column)
    height_key = _resolve_header(fieldnames, schema.height_column)
    category_key = (
        _resolve_header(fieldnames, schema.category_column) if schema.category_column else None
    )

    if time_key is None or height_key is None:
        raise ErddapError(
            f"Expected time/height columns not found in response headers: {fieldnames}"
        )

    events: list[TideEvent] = []

    for row in reader:
        raw_time = row.get(time_key)
        raw_height = row.get(height_key)
        if not raw_time or raw_height in (None, ""):
            continue

        try:
            event_time = datetime.strptime(raw_time, "%Y-%m-%dT%H:%M:%SZ").replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            _LOGGER.debug("Skipping row with unparseable time %r", raw_time)
            continue

        try:
            height: float | None = float(raw_height)
        except ValueError:
            height = None

        category_raw = row.get(category_key) if category_key else None
        events.append(
            TideEvent(
                time=event_time,
                height_m=height,
                is_high=_category_to_is_high(category_raw),
                category_raw=category_raw,
            )
        )

    events.sort(key=lambda event: event.time)
    _infer_missing_high_low(events)
    return events


def _category_to_is_high(category_raw: str | None) -> bool | None:
    if not category_raw:
        return None
    lowered = category_raw.lower()
    if "high" in lowered:
        return True
    if "low" in lowered:
        return False
    return None


def _infer_missing_high_low(events: list[TideEvent]) -> None:
    """Classify events whose category text was missing or unrecognised.

    A high/low tide table only ever lists alternating crests and troughs, so
    comparing an event's height to either neighbour's is enough to tell them
    apart even without any category text at all.
    """
    for index, event in enumerate(events):
        if event.is_high is not None or event.height_m is None:
            continue

        neighbour: TideEvent | None = None
        if index > 0 and events[index - 1].height_m is not None:
            neighbour = events[index - 1]
        elif index + 1 < len(events) and events[index + 1].height_m is not None:
            neighbour = events[index + 1]

        if neighbour is not None:
            event.is_high = event.height_m > neighbour.height_m


def interpolated_height_m(events: list[TideEvent], at: datetime) -> float | None:
    """Estimate the tide height at `at` from the surrounding predicted events.

    `events` must be sorted ascending by time (as returned by
    `parse_tide_events`). The real tide curve between two consecutive highs
    and lows is close to one half-cycle of a cosine, so that's used to
    interpolate between the bracketing pair rather than a straight line.
    This isn't a substitute for a full harmonic model, but it's accurate to
    within a few centimetres for the semi-diurnal tides found around
    Ireland, and needs no data beyond what's already fetched for the
    high/low sensors.
    """
    previous_event: TideEvent | None = None
    next_event: TideEvent | None = None
    for event in events:
        if event.height_m is None:
            continue
        if event.time <= at:
            previous_event = event
        else:
            next_event = event
            break

    if next_event is None:
        # `at` is at or after the last known event; only an exact match on
        # that last event is something we can answer without extrapolating.
        if previous_event is not None and previous_event.time == at:
            return previous_event.height_m
        return None

    if previous_event is None:
        return None

    span = (next_event.time - previous_event.time).total_seconds()
    if span <= 0:
        return previous_event.height_m

    progress = (at - previous_event.time).total_seconds() / span
    progress = min(max(progress, 0.0), 1.0)
    cosine_progress = (1 - math.cos(math.pi * progress)) / 2

    start = previous_event.height_m
    end = next_event.height_m
    return start + (end - start) * cosine_progress
