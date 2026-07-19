"""Constants for the EireTide integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "irish_tides"

CONF_STATION_ID = "station_id"

DEFAULT_STATION = "Dublin_Port"

ERDDAP_BASE_URL = "https://erddap.marine.ie/erddap"
DATASET_ID = "IMI_TidePrediction_HighLow"

SCAN_INTERVAL = timedelta(minutes=30)
FORECAST_DAYS = 7
LOOKBACK_HOURS = 24
REQUEST_TIMEOUT = 20

ATTRIBUTION = "Tide predictions provided by the Marine Institute, Ireland (erddap.marine.ie)"

# --- Prediction source selection -------------------------------------------
# EireTide can either fetch predictions from the Marine Institute (Ireland
# only), or compute them locally from Moon/Sun position using a harmonic
# tide model with per-station constants supplied by the user (works for any
# station, Ireland or UK, that the user has harmonic constants for).
CONF_SOURCE = "source"
SOURCE_MARINE_INSTITUTE = "marine_institute"
SOURCE_HARMONIC = "harmonic"

# --- Harmonic (local astronomical model) source -----------------------------
CONF_LABEL = "label"
CONF_MEAN_LEVEL = "mean_level_m"
CONF_CONSTITUENTS = "constituents"
CONF_DATUM_LABEL = "datum_label"

DEFAULT_DATUM_LABEL = "As referenced by the supplied harmonic constants"

# Predictions are computed instantly on demand, so this only controls how
# often the cached high/low event list is regenerated to slide the forecast
# window forward -- not how fresh the underlying data is.
HARMONIC_SCAN_INTERVAL = timedelta(hours=6)
HARMONIC_FORECAST_DAYS = 7
HARMONIC_LOOKBACK_HOURS = 24

ATTRIBUTION_HARMONIC = (
    "Predicted locally from Moon/Sun position using a harmonic tide model "
    "and user-supplied station constants -- not official measurements or "
    "predictions"
)

# Example shown as the default value of the constituents text box in the
# config flow. Deliberately not presented as accurate for any real station
# -- see the "Local harmonic model" section of the README for where to
# source real per-station constants.
EXAMPLE_CONSTITUENTS_TEXT = (
    "M2 1.90 137\nS2 0.70 171\nN2 0.40 120\nK1 0.10 200\nO1 0.08 190"
)

# All heights in this dataset are relative to OD Malin, Ireland's national
# geodetic datum -- not the Chart Datum / Lowest Astronomical Tide most
# consumer tide apps use, which is why the numbers can look very different
# (OD Malin sits roughly at mid-tide, so it swings negative; Chart Datum is
# pinned near the lowest tide ever recorded, so it's always positive).
HEIGHT_DATUM = "OD Malin"

# Used only when the live station-list query succeeds at reaching the dataset
# schema but the distinct() station query itself fails. Captured from a live
# query against IMI_TidePrediction_HighLow on 2026-07-19; the Marine
# Institute may add stations over time, so live discovery is always tried
# first.
FALLBACK_STATIONS: tuple[str, ...] = (
    "Achill_Island",
    "Aranmore",
    "Arklow",
    "Ballycotton",
    "Ballyglass",
    "Bray_Harbour",
    "Buncranna",
    "Carrigaholt",
    "Castletownbere",
    "Clare_Island",
    "Crosshaven",
    "Dingle",
    "Dublin_Port",
    "Dungarvan",
    "Dunmore",
    "Fenit",
    "Galway",
    "Howth",
    "Inishmore",
    "Killary_Harbour",
    "Killybegs",
    "Kilrush",
    "Kinsale",
    "Lahinch",
    "Letterfrack",
    "Malin_Head",
    "Port_Oriel",
    "Ringaskiddy",
    "Roonagh",
    "Rossaveel",
    "Rosslare",
    "Skerries",
    "Sligo",
    "Tom_Clarke_Bridge",
    "Tory_Island",
    "Union_Hall",
    "Wexford",
    "Wicklow",
)
