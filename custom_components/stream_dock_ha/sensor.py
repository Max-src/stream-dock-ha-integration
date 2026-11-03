"""Sensors for Stream Dock HA PCs."""

from __future__ import annotations

from collections.abc import Callable, Hashable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .data import StreamDockConfigEntry
from .entity import StreamDockPcEntity, async_add_pc_entities
from .hub import StreamDockHub

PARALLEL_UPDATES = 0


def _percent(key: str) -> Callable[[dict[str, Any]], Any]:
    return lambda pc: pc.get(key)


def _timestamp(pc: dict[str, Any]) -> datetime | None:
    """Return `last_press`, or None if it isn't a time with a time zone.

    A timestamp sensor refuses a naive time when writing its state, which would
    leave it stuck at the previous value, so anything doubtful becomes unknown.
    """
    if not isinstance(value := pc.get("last_press"), str) or not value:
        return None
    try:
        parsed = dt_util.parse_datetime(value)
    except ValueError:
        return None
    if parsed is None or parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed


@dataclass(frozen=True, kw_only=True)
class PcSensorDescription(SensorEntityDescription):
    """Describes a PC sensor."""

    value_fn: Callable[[dict[str, Any]], Any]


SENSORS: tuple[PcSensorDescription, ...] = (
    *(
        PcSensorDescription(
            key=key,
            translation_key=key,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            entity_registry_enabled_default=False,
            value_fn=_percent(key),
        )
        for key in ("cpu", "memory", "gpu")
    ),
    PcSensorDescription(
        key="last_press",
        translation_key="last_press",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_timestamp,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StreamDockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the PC sensors."""
    async_add_pc_entities(
        hass,
        entry,
        async_add_entities,
        lambda hub, pc: [
            PcSensor(hub, pc.instance_id, description) for description in SENSORS
        ],
    )


class PcSensor(StreamDockPcEntity, SensorEntity):
    """A value the app reports about its PC."""

    entity_description: PcSensorDescription

    def __init__(
        self, hub: StreamDockHub, instance_id: str, description: PcSensorDescription
    ) -> None:
        """Initialize the sensor."""
        super().__init__(hub, instance_id, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> Any:
        """Return the value."""
        return self.entity_description.value_fn(self.pc.pc_state)

    def _state_key(self) -> Hashable:
        return (self.available, self.native_value)
