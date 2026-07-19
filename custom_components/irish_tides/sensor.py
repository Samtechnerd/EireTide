"""Sensor platform for Irish Tides."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import TideEvent
from .const import ATTRIBUTION, DOMAIN
from .coordinator import IrishTidesDataUpdateCoordinator


def _event_type(event: TideEvent) -> str | None:
    if event.is_high is None:
        return None
    return "High" if event.is_high else "Low"


@dataclass(frozen=True, kw_only=True)
class IrishTidesSensorDescription(SensorEntityDescription):
    """Describes an Irish Tides sensor tied to one of the upcoming tide events."""

    event_index: int
    value_fn: Callable[[TideEvent], str | float | datetime | None]


SENSOR_DESCRIPTIONS: tuple[IrishTidesSensorDescription, ...] = (
    IrishTidesSensorDescription(
        key="next_tide_time",
        translation_key="next_tide_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        event_index=0,
        value_fn=lambda event: event.time,
    ),
    IrishTidesSensorDescription(
        key="next_tide_type",
        translation_key="next_tide_type",
        event_index=0,
        value_fn=_event_type,
    ),
    IrishTidesSensorDescription(
        key="next_tide_height",
        translation_key="next_tide_height",
        native_unit_of_measurement="m",
        suggested_display_precision=2,
        event_index=0,
        value_fn=lambda event: event.height_m,
    ),
    IrishTidesSensorDescription(
        key="following_tide_time",
        translation_key="following_tide_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        event_index=1,
        value_fn=lambda event: event.time,
    ),
    IrishTidesSensorDescription(
        key="following_tide_type",
        translation_key="following_tide_type",
        event_index=1,
        value_fn=_event_type,
    ),
    IrishTidesSensorDescription(
        key="following_tide_height",
        translation_key="following_tide_height",
        native_unit_of_measurement="m",
        suggested_display_precision=2,
        event_index=1,
        value_fn=lambda event: event.height_m,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Irish Tides sensors from a config entry."""
    coordinator: IrishTidesDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        IrishTidesSensor(coordinator, entry, description) for description in SENSOR_DESCRIPTIONS
    )


class IrishTidesSensor(CoordinatorEntity[IrishTidesDataUpdateCoordinator], SensorEntity):
    """A sensor reporting one field of an upcoming tide event."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    entity_description: IrishTidesSensorDescription

    def __init__(
        self,
        coordinator: IrishTidesDataUpdateCoordinator,
        entry: ConfigEntry,
        description: IrishTidesSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{entry.entry_id}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=f"Irish Tides - {coordinator.station_id}",
            manufacturer="Marine Institute",
            model="Tide Prediction",
            configuration_url=(
                "https://www.marine.ie/site-area/data-services/marine-forecasts/tidal-predictions"
            ),
        )

    @property
    def native_value(self) -> str | float | datetime | None:
        events = self.coordinator.get_next_events(count=2)
        index = self.entity_description.event_index
        if index >= len(events):
            return None
        return self.entity_description.value_fn(events[index])

    @property
    def extra_state_attributes(self) -> dict[str, list] | None:
        if self.entity_description.key != "next_tide_time":
            return None
        return {
            "upcoming_tides": [
                {
                    "time": event.time.isoformat(),
                    "type": _event_type(event),
                    "height_m": event.height_m,
                }
                for event in self.coordinator.get_next_events(count=10)
            ]
        }
