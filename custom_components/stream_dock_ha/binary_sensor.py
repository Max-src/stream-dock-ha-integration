"""Binary sensors for Stream Dock HA pads and PCs."""

from __future__ import annotations

from collections.abc import Hashable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import KIND_DASHBOARD
from .data import StreamDockConfigEntry
from .entity import (
    StreamDockPadEntity,
    StreamDockPcEntity,
    async_add_pad_entities,
    async_add_pc_entities,
)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StreamDockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    async_add_pad_entities(
        hass,
        entry,
        async_add_entities,
        lambda hub, pad: (
            []
            if pad.kind == KIND_DASHBOARD
            else [PadConnectedSensor(hub, pad.pad_id, "connected")]
        ),
    )
    async_add_pc_entities(
        hass,
        entry,
        async_add_entities,
        lambda hub, pc: [
            MicMutedSensor(hub, pc.instance_id, "mic_muted"),
            PcOnlineSensor(hub, pc.instance_id, "online"),
        ],
    )


class PadConnectedSensor(StreamDockPadEntity, BinarySensorEntity):
    """Whether the physical pad is plugged in and working."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def is_on(self) -> bool | None:
        """Return whether the pad is connected."""
        return self.pad_state.get("connected")

    def _state_key(self) -> Hashable:
        return (self.available, self.is_on)


class MicMutedSensor(StreamDockPcEntity, BinarySensorEntity):
    """Whether the PC's microphone is muted."""

    @property
    def is_on(self) -> bool | None:
        """Return whether the microphone is muted."""
        return self.pc.pc_state.get("mic_muted")

    def _state_key(self) -> Hashable:
        return (self.available, self.is_on)


class PcOnlineSensor(StreamDockPcEntity, BinarySensorEntity):
    """Whether the PC is connected. Always available."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self) -> bool:
        """Return True: this entity says whether the PC is there."""
        return True

    @property
    def is_on(self) -> bool:
        """Return whether the PC is connected."""
        return self.pc.online

    def _state_key(self) -> Hashable:
        return (self.is_on,)
