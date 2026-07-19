"""Config flow for the EireTide integration."""
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
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util

from . import api, harmonic
from .const import (
    CONF_CONSTITUENTS,
    CONF_DATUM_LABEL,
    CONF_LABEL,
    CONF_MEAN_LEVEL,
    CONF_SOURCE,
    CONF_STATION_ID,
    DEFAULT_DATUM_LABEL,
    DEFAULT_STATION,
    DOMAIN,
    EXAMPLE_CONSTITUENTS_TEXT,
    FALLBACK_STATIONS,
    SOURCE_HARMONIC,
    SOURCE_MARINE_INSTITUTE,
)

_LOGGER = logging.getLogger(__name__)


class IrishTidesConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for EireTide."""

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
        """First step: choose where predictions come from."""
        return self.async_show_menu(
            step_id="user",
            menu_options=["marine_institute", "harmonic"],
        )

    async def async_step_marine_institute(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Pick an Irish station from the Marine Institute, from a dropdown if possible."""
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
        return self.async_show_form(
            step_id="marine_institute", data_schema=data_schema, errors=errors
        )

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
            title=f"EireTide - {station_id}",
            data={CONF_SOURCE: SOURCE_MARINE_INSTITUTE, CONF_STATION_ID: station_id},
        )

    async def async_step_harmonic(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Configure a station predicted locally from a harmonic constituent model.

        Unlike the Marine Institute source, this needs no network access at
        all: the user supplies their station's harmonic constants (amplitude
        + Greenwich phase lag per tidal constituent, e.g. from the UK's
        National Tidal and Sea Level Facility / BODC, Admiralty EasyTide, or
        their own harmonic analysis of measured data), and EireTide computes
        predictions from Moon/Sun position from that point on.
        """
        errors: dict[str, str] = {}
        constituents: list[dict[str, Any]] = []

        if user_input is not None:
            label = user_input[CONF_LABEL].strip()
            try:
                parsed = harmonic.parse_constituents_text(user_input[CONF_CONSTITUENTS])
            except ValueError as err:
                errors["base"] = "invalid_constituents"
                _LOGGER.debug("Could not parse harmonic constituents: %s", err)
            else:
                constituents = [
                    {"name": c.name, "amplitude_m": c.amplitude_m, "phase_deg": c.phase_deg}
                    for c in parsed
                ]

            if not errors:
                await self.async_set_unique_id(f"{DOMAIN}_harmonic_{label.lower()}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"EireTide - {label}",
                    data={
                        CONF_SOURCE: SOURCE_HARMONIC,
                        CONF_LABEL: label,
                        CONF_MEAN_LEVEL: user_input[CONF_MEAN_LEVEL],
                        CONF_DATUM_LABEL: user_input[CONF_DATUM_LABEL].strip(),
                        CONF_CONSTITUENTS: constituents,
                    },
                )

        data_schema = vol.Schema(
            {
                vol.Required(CONF_LABEL, default="My Station"): str,
                vol.Required(CONF_MEAN_LEVEL, default=0.0): vol.Coerce(float),
                vol.Required(CONF_DATUM_LABEL, default=DEFAULT_DATUM_LABEL): str,
                vol.Required(
                    CONF_CONSTITUENTS, default=EXAMPLE_CONSTITUENTS_TEXT
                ): TextSelector(TextSelectorConfig(multiline=True, type=TextSelectorType.TEXT)),
            }
        )
        return self.async_show_form(
            step_id="harmonic", data_schema=data_schema, errors=errors
        )
