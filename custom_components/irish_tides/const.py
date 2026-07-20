"""Constants for the EireTide integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "irish_tides"

CONF_STATION_ID = "station_id"
CONF_HEIGHT_OFFSET = "height_offset_m"
DEFAULT_HEIGHT_OFFSET = 0.0

DEFAULT_STATION = "Dublin_Port"

ERDDAP_BASE_URL = "https://erddap.marine.ie/erddap"
DATASET_ID = "IMI_TidePrediction_HighLow"

SCAN_INTERVAL = timedelta(minutes=30)
FORECAST_DAYS = 7
LOOKBACK_HOURS = 24
REQUEST_TIMEOUT = 20

ATTRIBUTION = "Tide predictions provided by the Marine Institute, Ireland (erddap.marine.ie)"

# All heights in this dataset are relative to OD Malin, Ireland's national
# geodetic datum -- not the Chart Datum / Lowest Astronomical Tide most
# consumer tide apps use, which is why the numbers can look very different
# (OD Malin sits roughly at mid-tide, so it swings negative; Chart Datum is
# pinned near the lowest tide ever recorded, so it's always positive).
HEIGHT_DATUM = "OD Malin"

# Approximate OD-Malin-to-Chart-Datum (~LAT) offsets in metres, i.e. add
# this to an OD Malin height to estimate the Chart Datum height most
# consumer tide apps show. Derived from simultaneous "Water Level - OD
# Malin" / "Water Level - LAT" readings on the Marine Institute's real-time
# tidal observations network on 2026-07-20 -- Chart Datum is a fixed
# geodetic offset per station, so a single simultaneous reading is enough
# to derive it, but treat these as estimates, not surveyed figures. Used
# only to pre-fill the options flow; users can always override with their
# own value, and stations not listed here just default to no correction.
KNOWN_HEIGHT_OFFSETS: dict[str, float] = {
    "Aranmore": 2.190,
    "Ballycotton": 2.460,
    "Ballyglass": 2.109,
    "Buncranna": 2.326,
    "Castletownbere": 2.075,
    "Dingle": 2.423,
    "Dublin_Port": 2.458,
    "Dunmore": 2.541,
    "Galway": 2.949,
    "Howth": 2.561,
    "Inishmore": 2.789,
    "Killybegs": 2.267,
    "Kilrush": 3.003,
    "Malin_Head": 2.084,
    "Roonagh": 1.948,
    "Rosslare": 1.080,
    "Skerries": 2.883,
    "Tom_Clarke_Bridge": 2.339,
    "Union_Hall": 2.075,
    "Wexford": 0.960,
}

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
