"""Data update coordinator for the EireTide integration."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import api
from .const import (
    CONF_HEIGHT_OFFSET,
    CONF_STATION_ID,
    DEFAULT_HEIGHT_OFFSET,
    DOMAIN,
    FORECAST_DAYS,
    LOOKBACK_HOURS,
    SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


class IrishTidesDataUpdateCoordinator(DataUpdateCoordinator[list[api.TideEvent]]):
    """Fetch and cache tide predictions for one station."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.station_id: str = entry.data[CONF_STATION_ID]
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_{self.station_id}",
            update_interval=SCAN_INTERVAL,
        )
        self.entry = entry
        self._session = async_get_clientsession(hass)
        self._schema: api.DatasetSchema | None = None

    async def _async_update_data(self) -> list[api.TideEvent]:
        try:
            if self._schema is None:
                self._schema = await api.async_discover_schema(self._session)

            now = dt_util.utcnow()
            events = await api.async_get_tide_events(
                self._session,
                self._schema,
                self.station_id,
                now - timedelta(hours=LOOKBACK_HOURS),
                now + timedelta(days=FORECAST_DAYS),
            )
        except api.ErddapError as err:
            self._schema = None
            raise UpdateFailed(f"Error communicating with Marine Institute API: {err}") from err
        except aiohttp.ClientError as err:
            raise UpdateFailed(f"Error connecting to Marine Institute API: {err}") from err

        if not events:
            raise UpdateFailed(f"No tide predictions returned for station '{self.station_id}'")

        return events

    def get_next_events(self, count: int = 2) -> list[api.TideEvent]:
        """Return up to `count` tide events that are still in the future."""
        if not self.data:
            return []
        now = dt_util.utcnow()
        return [event for event in self.data if event.time > now][:count]

    def current_height_m(self, at: datetime | None = None) -> float | None:
        """Estimate the current tide height by interpolating between predictions."""
        if not self.data:
            return None
        return api.interpolated_height_m(self.data, at or dt_util.utcnow())

    @property
    def height_offset_m(self) -> float:
        """User-supplied OD-Malin-to-Chart-Datum correction, if any (0 = none)."""
        return self.entry.options.get(CONF_HEIGHT_OFFSET, DEFAULT_HEIGHT_OFFSET)
