"""Constants for the Irish Tides integration."""
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
