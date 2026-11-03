"""Screen light for Stream Dock HA pads."""

from __future__ import annotations

from collections.abc import Hashable
from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
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
    """Set up the screen lights."""
    async_add_pad_entities(
        hass,
        entry,
        async_add_entities,
        lambda hub, pad: [ScreenLight(hub, pad.pad_id, "screen")],
    )


class ScreenLight(StreamDockPadEntity, LightEntity):
    """The pad's screen: on or off, and its brightness."""

    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    @property
    def is_on(self) -> bool | None:
        """Return whether the screen is on."""
        return self.pad_state.get("screen_on")

    @property
    def brightness(self) -> int | None:
        """Return the brightness, 0 to 100 shown as 0 to 255."""
        if (level := self.pad_state.get("brightness")) is None:
            return None
        return round(level * 255 / 100)

    def _state_key(self) -> Hashable:
        return (self.available, self.is_on, self.brightness)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the screen on, and set its brightness if given."""
        await self._async_command("set_screen", on=True)
        if (brightness := kwargs.get(ATTR_BRIGHTNESS)) is not None:
            await self._async_command(
                "set_brightness", level=round(brightness * 100 / 255)
            )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the screen off."""
        await self._async_command("set_screen", on=False)
