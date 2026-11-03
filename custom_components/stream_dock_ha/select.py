"""Profile select for Stream Dock HA pads."""

from __future__ import annotations

from collections.abc import Hashable

from homeassistant.components.select import SelectEntity
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
    """Set up the profile selects."""
    async_add_pad_entities(
        hass,
        entry,
        async_add_entities,
        lambda hub, pad: [ProfileSelect(hub, pad.pad_id, "profile")],
    )


class ProfileSelect(StreamDockPadEntity, SelectEntity):
    """The pad's profile."""

    @property
    def options(self) -> list[str]:
        """Return the profile names."""
        return [profile["name"] for profile in self.pad_state.get("profiles", [])]

    @property
    def current_option(self) -> str | None:
        """Return the profile showing."""
        return (self.pad_state.get("profile") or {}).get("name")

    def _state_key(self) -> Hashable:
        return (self.available, tuple(self.options), self.current_option)

    async def async_select_option(self, option: str) -> None:
        """Show a profile."""
        await self._async_command("show_profile", profile=option)
