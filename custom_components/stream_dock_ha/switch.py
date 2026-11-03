"""Mini Monitor switch for Stream Dock HA pads."""

from __future__ import annotations

from collections.abc import Hashable
from functools import partial
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import signal_new_pad, signal_pad
from .data import StreamDockConfigEntry
from .entity import StreamDockPadEntity

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StreamDockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the Mini Monitor switches, for pads that can show it."""
    hub = entry.runtime_data
    waiting: dict[str, CALLBACK_TYPE] = {}

    @callback
    def check(pad_id: str) -> None:
        pad = hub.pads.get(pad_id)
        if pad is None or pad.state.get("mini_monitor") is None:
            if pad is not None and pad_id not in waiting:
                waiting[pad_id] = async_dispatcher_connect(
                    hass, signal_pad(entry.entry_id, pad_id), partial(check, pad_id)
                )
            return
        if (unsub := waiting.pop(pad_id, None)) is not None:
            unsub()
        async_add_entities([MiniMonitorSwitch(hub, pad_id, "mini_monitor")])

    @callback
    def stop_waiting() -> None:
        for unsub in waiting.values():
            unsub()
        waiting.clear()

    for pad_id in list(hub.pads):
        check(pad_id)
    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_new_pad(entry.entry_id), check)
    )
    entry.async_on_unload(stop_waiting)


class MiniMonitorSwitch(StreamDockPadEntity, SwitchEntity):
    """Whether the pad shows Mini Monitor."""

    @property
    def is_on(self) -> bool | None:
        """Return whether Mini Monitor is on."""
        return self.pad_state.get("mini_monitor")

    def _state_key(self) -> Hashable:
        return (self.available, self.is_on)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn Mini Monitor on."""
        await self._async_command("mini_monitor", on=True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn Mini Monitor off."""
        await self._async_command("mini_monitor", on=False)
