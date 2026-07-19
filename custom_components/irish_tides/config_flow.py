"""Config flow for the Irish Tides integration."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.util import dt as dt_util

from . import api
from .const import CONF_STATION_ID, DEFAULT_STATION, DOMAIN, FALLBACK_STATIONS

_LOGGER = logging.getLogger(__name__)


class IrishTidesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Irish Tides."""

    VERSION = 1

    def __init__(self) -> None:
        self._schema: api.DatasetSchema | None = None
        self._stations: list[str] = []
        self._discovery_attempted = False

    async def _async_discover_stations(self) -> None:
        if self._discovery_attempted:
            return
        self._discovery_attempted = True

        session = async_get_clientsession(self.hass)
        try:
            self._schema = await api.async_discover_schema(session)
        except (api.ErddapError, aiohttp.ClientError) as err:
            _LOGGER.warning(
                "Could not reach the Marine Institute dataset, falling back to "
                "manual station entry: %s",
                err,
            )
            return

        try:
            self._stations = await api.async_get_station_list(session, self._schema)
        except (api.ErddapError, aiohttp.ClientError) as err:
            _LOGGER.warning(
                "Could not load the live station list, falling back to the "
                "built-in station list: %s",
                err,
            )
            self._stations = list(FALLBACK_STATIONS)

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """First step: pick a station from a dropdown, if we could load the list."""
        await self._async_discover_stations()

        if not self._stations:
            return await self.async_step_manual_station(user_input)

        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_validate_station(user_input[CONF_STATION_ID])
            if not errors:
                return self._async_create_entry(user_input[CONF_STATION_ID])

        default_station = next(
            (station for station in self._stations if station.lower() == DEFAULT_STATION.lower()),
            self._stations[0],
        )
        options = [
            SelectOptionDict(value=station, label=station.replace("_", " "))
            for station in self._stations
        ]
        data_schema = vol.Schema(
            {
                vol.Required(CONF_STATION_ID, default=default_station): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.DROPDOWN)
                )
            }
        )
        return self.async_show_form(step_id="user", data_schema=data_schema, errors=errors)

    async def async_step_manual_station(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Fallback step: type in a station name when the station list can't be loaded."""
        errors: dict[str, str] = {}
        if user_input is not None:
            station_id = user_input[CONF_STATION_ID].strip()
            errors = await self._async_validate_station(station_id)
            if not errors:
                return self._async_create_entry(station_id)

        data_schema = vol.Schema({vol.Required(CONF_STATION_ID, default=DEFAULT_STATION): str})
        return self.async_show_form(
            step_id="manual_station", data_schema=data_schema, errors=errors
        )

    async def _async_validate_station(self, station_id: str) -> dict[str, str]:
        """Check that the station exists and returns data. Returns an errors dict."""
        await self.async_set_unique_id(f"{DOMAIN}_{station_id.lower()}")
        self._abort_if_unique_id_configured()

        session = async_get_clientsession(self.hass)
        try:
            schema = self._schema or await api.async_discover_schema(session)
            now = dt_util.utcnow()
            events = await api.async_get_tide_events(
                session, schema, station_id, now, now + timedelta(days=2)
            )
        except (api.ErddapError, aiohttp.ClientError) as err:
            _LOGGER.warning("Validation request failed for station %s: %s", station_id, err)
            return {"base": "cannot_connect"}

        if not events:
            return {"base": "unknown_station"}

        return {}

    def _async_create_entry(self, station_id: str) -> FlowResult:
        return self.async_create_entry(
            title=f"Irish Tides - {station_id}",
            data={CONF_STATION_ID: station_id},
        )
