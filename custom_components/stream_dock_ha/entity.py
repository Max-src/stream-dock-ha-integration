"""Base entities for Stream Dock HA."""

from __future__ import annotations

from collections.abc import Callable, Hashable, Iterable
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import ChildDeviceInfo, DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import DOMAIN, signal_new_pad, signal_new_pc, signal_pad, signal_pc
from .data import StreamDockConfigEntry
from .hub import StreamDockHub
from .models import Pad, Pc


@callback
def async_add_pad_entities(
    hass: HomeAssistant,
    entry: StreamDockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[StreamDockHub, Pad], Iterable[Entity]],
) -> None:
    """Add a platform's entities for every pad, now and as pads appear."""
    hub = entry.runtime_data

    @callback
    def add(pad_id: str) -> None:
        async_add_entities(factory(hub, hub.pads[pad_id]))

    for pad_id in list(hub.pads):
        add(pad_id)
    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_new_pad(entry.entry_id), add)
    )


@callback
def async_add_pc_entities(
    hass: HomeAssistant,
    entry: StreamDockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
    factory: Callable[[StreamDockHub, Pc], Iterable[Entity]],
) -> None:
    """Add a platform's entities for every PC, now and as PCs appear."""
    hub = entry.runtime_data

    @callback
    def add(instance_id: str) -> None:
        async_add_entities(factory(hub, hub.pcs[instance_id]))

    for instance_id in list(hub.pcs):
        add(instance_id)
    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_new_pc(entry.entry_id), add)
    )


class StreamDockEntity(Entity):
    """An entity fed by the hub.

    It writes its state only when `_state_key()` changes, so an entity isn't
    rewritten when another part of its pad or PC changes.
    """

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, hub: StreamDockHub, device_key: str, key: str) -> None:
        """Initialize the entity."""
        self.hub = hub
        self._attr_unique_id = f"{device_key}_{key}"
        self._attr_translation_key = key
        self._attr_device_info: DeviceInfo | ChildDeviceInfo = DeviceInfo(
            identifiers={(DOMAIN, device_key)}
        )
        self._last_key: Hashable = None

    @property
    def _signal(self) -> str:
        raise NotImplementedError

    def _state_key(self) -> Hashable:
        """Return everything the entity shows, to spot changes."""
        return (self.available,)

    async def async_added_to_hass(self) -> None:
        """Listen for changes."""
        self._last_key = self._state_key()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, self._signal, self._async_changed)
        )

    @callback
    def _async_changed(self) -> None:
        if (key := self._state_key()) != self._last_key:
            self._last_key = key
            self.async_write_ha_state()


class StreamDockPadEntity(StreamDockEntity):
    """An entity of a pad."""

    def __init__(self, hub: StreamDockHub, pad_id: str, key: str) -> None:
        """Initialize the entity."""
        super().__init__(hub, pad_id, key)
        self.pad_id = pad_id
        self.pad: Pad = hub.pads[pad_id]
        # A pad is a child device of its PC (see the hub).
        parent = hub.pc_of(self.pad).device_id
        if parent is not None:
            self._attr_device_info = ChildDeviceInfo(
                identifiers={(DOMAIN, pad_id)}, parent_device_id=parent
            )

    @property
    def pad_state(self) -> dict[str, Any]:
        """Return the pad's last `PadState`."""
        return self.pad.state

    @property
    def available(self) -> bool:
        """Return whether the PC is online and lists this pad."""
        return self.hub.pad_available(self.pad)

    @property
    def _signal(self) -> str:
        return signal_pad(self.hub.entry.entry_id, self.pad_id)

    async def _async_command(self, command: str, **fields: Any) -> Any:
        """Send a command for this pad, as the user behind the change."""
        user = None
        if (
            self._context is not None
            and self._context.user_id is not None
            and (found := await self.hass.auth.async_get_user(self._context.user_id))
        ):
            user = found.name
        return await self.hub.async_command(
            self.pad_id, command, fields, source="action", user=user
        )


class StreamDockPcEntity(StreamDockEntity):
    """An entity of a PC."""

    def __init__(self, hub: StreamDockHub, instance_id: str, key: str) -> None:
        """Initialize the entity."""
        super().__init__(hub, instance_id, key)
        self.instance_id = instance_id
        self.pc: Pc = hub.pcs[instance_id]

    @property
    def available(self) -> bool:
        """Return whether the PC is online."""
        return self.pc.online

    @property
    def _signal(self) -> str:
        return signal_pc(self.hub.entry.entry_id, self.instance_id)
