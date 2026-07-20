"""Sensor platform for EireTide."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import TideEvent
from .const import ATTRIBUTION, DOMAIN, HEIGHT_DATUM
from .coordinator import IrishTidesDataUpdateCoordinator

CURRENT_HEIGHT_REFRESH_INTERVAL = timedelta(minutes=5)
HEIGHT_SENSOR_KEYS = {"next_tide_height", "following_tide_height"}


def _event_type(event: TideEvent) -> str | None:
    if event.is_high is None:
        return None
    return "High" if event.is_high else "Low"


@dataclass(frozen=True, kw_only=True)
class IrishTidesSensorDescription(SensorEntityDescription):
    """Describes an EireTide sensor tied to one of the upcoming tide events."""

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


def _device_info(coordinator: IrishTidesDataUpdateCoordinator, entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name=f"EireTide - {coordinator.station_id}",
        manufacturer="Marine Institute",
        model="Tide Prediction",
        configuration_url=(
            "https://www.marine.ie/site-area/data-services/marine-forecasts/tidal-predictions"
        ),
    )


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up EireTide sensors from a config entry."""
    coordinator: IrishTidesDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list[SensorEntity] = [IrishTidesCurrentHeightSensor(coordinator, entry)]
    entities.extend(
        IrishTidesSensor(coordinator, entry, description) for description in SENSOR_DESCRIPTIONS
    )
    async_add_entities(entities)


class IrishTidesCurrentHeightSensor(
    CoordinatorEntity[IrishTidesDataUpdateCoordinator], SensorEntity
):
    """The estimated current tide height, interpolated between predicted highs and lows."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_translation_key = "current_tide_height"
    _attr_native_unit_of_measurement = "m"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2
    _attr_icon = "mdi:waves"

    def __init__(self, coordinator: IrishTidesDataUpdateCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_current_tide_height"
        self._attr_device_info = _device_info(coordinator, entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        # The coordinator only fetches new predictions every 30 minutes, but the
        # interpolated height should keep moving between those refreshes.
        self.async_on_remove(
            async_track_time_interval(
                self.hass, self._async_handle_tick, CURRENT_HEIGHT_REFRESH_INTERVAL
            )
        )

    @callback
    def _async_handle_tick(self, _now: datetime) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> float | None:
        return self.coordinator.current_height_m()

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        attributes: dict[str, object] = {"datum": HEIGHT_DATUM}
        height = self.coordinator.current_height_m()
        offset = self.coordinator.height_offset_m
        if height is not None and offset:
            attributes["chart_datum_estimate_m"] = round(height + offset, 3)
        return attributes


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
        self._attr_device_info = _device_info(coordinator, entry)

    @property
    def native_value(self) -> str | float | datetime | None:
        events = self.coordinator.get_next_events(count=2)
        index = self.entity_description.event_index
        if index >= len(events):
            return None
        return self.entity_description.value_fn(events[index])

    @property
    def extra_state_attributes(self) -> dict[str, object] | None:
        key = self.entity_description.key
        offset = self.coordinator.height_offset_m
        if key == "next_tide_time":
            return {
                "datum": HEIGHT_DATUM,
                "upcoming_tides": [
                    {
                        "time": event.time.isoformat(),
                        "type": _event_type(event),
                        "height_m": event.height_m,
                        "chart_datum_estimate_m": (
                            round(event.height_m + offset, 3)
                            if event.height_m is not None and offset
                            else None
                        ),
                    }
                    for event in self.coordinator.get_next_events(count=10)
                ],
            }
        if key in HEIGHT_SENSOR_KEYS:
            attributes: dict[str, object] = {"datum": HEIGHT_DATUM}
            events = self.coordinator.get_next_events(count=2)
            index = self.entity_description.event_index
            height = events[index].height_m if index < len(events) else None
            if height is not None and offset:
                attributes["chart_datum_estimate_m"] = round(height + offset, 3)
            return attributes
        return None
