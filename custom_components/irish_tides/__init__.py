"""The EireTide integration."""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_SOURCE, DOMAIN, SOURCE_HARMONIC
from .coordinator import IrishTidesDataUpdateCoordinator
from .harmonic_coordinator import HarmonicTideCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EireTide from a config entry."""
    if entry.data.get(CONF_SOURCE) == SOURCE_HARMONIC:
        coordinator: IrishTidesDataUpdateCoordinator | HarmonicTideCoordinator = (
            HarmonicTideCoordinator(hass, entry)
        )
    else:
        coordinator = IrishTidesDataUpdateCoordinator(hass, entry)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok
