"""Diagnostics support for EireTide."""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import IrishTidesDataUpdateCoordinator
from .harmonic_coordinator import HarmonicTideCoordinator


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator: IrishTidesDataUpdateCoordinator | HarmonicTideCoordinator = hass.data[DOMAIN][
        entry.entry_id
    ]
    return {
        "station_id": coordinator.station_id,
        "last_update_success": coordinator.last_update_success,
        "events": [
            {
                "time": event.time.isoformat(),
                "height_m": event.height_m,
                "is_high": event.is_high,
                "category_raw": event.category_raw,
            }
            for event in coordinator.data or []
        ],
    }
