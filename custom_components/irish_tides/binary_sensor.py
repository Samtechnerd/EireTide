"""Binary sensor platform for EireTide."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, ATTRIBUTION_HARMONIC, CONF_SOURCE, DOMAIN, SOURCE_HARMONIC
from .coordinator import IrishTidesDataUpdateCoordinator
from .harmonic_coordinator import HarmonicTideCoordinator

TideCoordinator = IrishTidesDataUpdateCoordinator | HarmonicTideCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the EireTide binary sensor from a config entry."""
    coordinator: TideCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([IrishTidesRisingBinarySensor(coordinator, entry)])


class IrishTidesRisingBinarySensor(CoordinatorEntity[TideCoordinator], BinarySensorEntity):
    """True while the tide is rising towards the next high tide."""

    _attr_has_entity_name = True
    _attr_translation_key = "tide_rising"
    _attr_icon = "mdi:wave"

    def __init__(self, coordinator: TideCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_tide_rising"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})
        self._attr_attribution = (
            ATTRIBUTION_HARMONIC if entry.data.get(CONF_SOURCE) == SOURCE_HARMONIC else ATTRIBUTION
        )

    @property
    def is_on(self) -> bool | None:
        events = self.coordinator.get_next_events(count=1)
        if not events:
            return None
        return events[0].is_high
