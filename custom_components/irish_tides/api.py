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
    """Discover the dataset's real column names from ERDDAP's info endpoint."""
    url = f"{ERDDAP_BASE_URL}/info/{DATASET_ID}/index.csvp"
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


async def async_get_station_list(
    session: aiohttp.ClientSession, schema: DatasetSchema
) -> list[str]:
    """Return the sorted, distinct list of station names known to the dataset."""
    column = quote(schema.station_column, safe="")
    url = f"{ERDDAP_BASE_URL}/tabledap/{DATASET_ID}.csvp?{column}&distinct()"
    text = await _get_text(session, url)

    reader = csv.DictReader(io.StringIO(text))
    stations = {
        row[schema.station_column].strip()
        for row in reader
        if row.get(schema.station_column)
    }
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
    url = f"{ERDDAP_BASE_URL}/tabledap/{DATASET_ID}.csvp?{query}"
    text = await _get_text(session, url)
    return parse_tide_events(text, schema)


def parse_tide_events(text: str, schema: DatasetSchema) -> list[TideEvent]:
    """Parse an ERDDAP csvp response into a chronological list of tide events."""
    reader = csv.DictReader(io.StringIO(text))
    events: list[TideEvent] = []

    for row in reader:
        raw_time = row.get(schema.time_column)
        raw_height = row.get(schema.height_column)
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

        category_raw = row.get(schema.category_column) if schema.category_column else None
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
