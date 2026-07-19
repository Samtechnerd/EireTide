"""Constants for the Irish Tides integration."""
from __future__ import annotations

from datetime import timedelta

DOMAIN = "irish_tides"

CONF_STATION_ID = "station_id"

DEFAULT_STATION = "Howth"

ERDDAP_BASE_URL = "https://erddap.marine.ie/erddap"
DATASET_ID = "IMI_TidePrediction_HighLow"

SCAN_INTERVAL = timedelta(minutes=30)
FORECAST_DAYS = 7
LOOKBACK_HOURS = 24
REQUEST_TIMEOUT = 20

ATTRIBUTION = "Tide predictions provided by the Marine Institute, Ireland (erddap.marine.ie)"
