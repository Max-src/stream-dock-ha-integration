"""Page number for Stream Dock HA pads."""

from __future__ import annotations

from collections.abc import Hashable

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .data import StreamDockConfigEntry
from .entity import StreamDockPadEntity, async_add_pad_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StreamDockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the page numbers."""
    async_add_pad_entities(
        hass,
        entry,
        async_add_entities,
        lambda hub, pad: [PageNumber(hub, pad.pad_id, "page")],
    )


class PageNumber(StreamDockPadEntity, NumberEntity):
    """The page showing on the pad, from 1."""

    _attr_mode = NumberMode.BOX
    _attr_native_min_value = 1
    _attr_native_step = 1

    @property
    def native_max_value(self) -> float:
        """Return the number of pages."""
        return max(1, int(self.pad_state.get("pages") or 1))

    @property
    def native_value(self) -> float | None:
        """Return the page showing."""
        return self.pad_state.get("page")

    def _state_key(self) -> Hashable:
        return (self.available, self.native_value, self.native_max_value)

    async def async_set_native_value(self, value: float) -> None:
        """Show a page."""
        await self._async_command("show_page", page=int(value))
