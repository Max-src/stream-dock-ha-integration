"""Press events for Stream Dock HA pads."""

from __future__ import annotations

from collections.abc import Hashable
import logging
from typing import Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import EVENT_TYPE_DISMISSED, signal_press
from .data import StreamDockConfigEntry
from .entity import StreamDockPadEntity, async_add_pad_entities

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

EVENT_ATTRIBUTES = ("profile", "page", "title", "source")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StreamDockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the press events."""
    async_add_pad_entities(
        hass,
        entry,
        async_add_entities,
        lambda hub, pad: [PressEvent(hub, pad.pad_id, "press")],
    )


class PressEvent(StreamDockPadEntity, EventEntity):
    """Each press on the pad, named after the control pressed."""

    @property
    def event_types(self) -> list[str]:
        """Return the pressable controls, and `dismissed`."""
        return [*self.pad.press_controls, EVENT_TYPE_DISMISSED]

    def _state_key(self) -> Hashable:
        return (self.available, tuple(self.event_types))

    async def async_added_to_hass(self) -> None:
        """Listen for presses too."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                signal_press(self.hub.entry.entry_id, self.pad_id),
                self._async_pressed,
            )
        )

    @callback
    def _async_pressed(self, data: dict[str, Any]) -> None:
        event_type = EVENT_TYPE_DISMISSED if data["dismissed"] else data["control"]
        if event_type not in self.event_types:
            _LOGGER.debug(
                "Press on %s isn't in the layout: %s", self.pad_id, event_type
            )
            return
        self._trigger_event(event_type, {key: data[key] for key in EVENT_ATTRIBUTES})
        self.async_write_ha_state()
