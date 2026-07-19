"""Data update coordinator for the local astronomical (harmonic) tide source.

Unlike ``coordinator.py``, this never makes a network request: every value
is computed on this machine from the current Moon/Sun position and the
station's harmonic constants supplied at setup time. The coordinator still
runs on a schedule so the cached high/low event list keeps sliding forward
in time, but "refresh" here means "recompute", not "re-fetch".
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import api, harmonic
from .const import (
    CONF_CONSTITUENTS,
    CONF_LABEL,
    CONF_MEAN_LEVEL,
    DOMAIN,
    HARMONIC_FORECAST_DAYS,
    HARMONIC_LOOKBACK_HOURS,
    HARMONIC_SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class HarmonicTideCoordinator(DataUpdateCoordinator[list[api.TideEvent]]):
    """Compute tide predictions locally from a station's harmonic constants."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.station_id: str = entry.data[CONF_LABEL]
        self.mean_level_m: float = entry.data[CONF_MEAN_LEVEL]
        self.constituents: list[harmonic.HarmonicConstituent] = [
            harmonic.HarmonicConstituent(
                name=c["name"], amplitude_m=c["amplitude_m"], phase_deg=c["phase_deg"]
            )
            for c in entry.data[CONF_CONSTITUENTS]
        ]
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_harmonic_{self.station_id}",
            update_interval=HARMONIC_SCAN_INTERVAL,
        )
        self.entry = entry

    async def _async_update_data(self) -> list[api.TideEvent]:
        now = dt_util.utcnow()
        start = now - timedelta(hours=HARMONIC_LOOKBACK_HOURS)
        end = now + timedelta(days=HARMONIC_FORECAST_DAYS)

        # find_extrema samples the height curve at 10-minute resolution over
        # up to 8 days, which is cheap but non-trivial pure-Python work --
        # run it off the event loop like any other coordinator update.
        extrema = await self.hass.async_add_executor_job(
            harmonic.find_extrema, self.constituents, self.mean_level_m, start, end
        )

        return [
            api.TideEvent(
                time=extremum.time,
                height_m=extremum.height_m,
                is_high=extremum.is_high,
                category_raw=None,
            )
            for extremum in extrema
        ]

    def get_next_events(self, count: int = 2) -> list[api.TideEvent]:
        """Return up to `count` tide events that are still in the future."""
        if not self.data:
            return []
        now = dt_util.utcnow()
        return [event for event in self.data if event.time > now][:count]

    def current_height_m(self, at: datetime | None = None) -> float | None:
        """Compute the tide height at `at` directly from the harmonic model."""
        return harmonic.predict_height_m(
            self.constituents, self.mean_level_m, at or dt_util.utcnow()
        )
