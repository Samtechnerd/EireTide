"""Binary sensor platform for Irish Tides."""
from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import ATTRIBUTION, DOMAIN
from .coordinator import IrishTidesDataUpdateCoordinator


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the Irish Tides binary sensor from a config entry."""
    coordinator: IrishTidesDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([IrishTidesRisingBinarySensor(coordinator, entry)])


class IrishTidesRisingBinarySensor(
    CoordinatorEntity[IrishTidesDataUpdateCoordinator], BinarySensorEntity
):
    """True while the tide is rising towards the next high tide."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_translation_key = "tide_rising"
    _attr_icon = "mdi:wave"

    def __init__(self, coordinator: IrishTidesDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_tide_rising"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, entry.entry_id)})

    @property
    def is_on(self) -> bool | None:
        events = self.coordinator.get_next_events(count=1)
        if not events:
            return None
        return events[0].is_high
