"""Data kept for the whole Home Assistant process."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.util.hass_dict import HassKey

from .const import DOMAIN
from .watchers import CardWatchers

if TYPE_CHECKING:
    from .hub import StreamDockHub

type StreamDockConfigEntry = ConfigEntry[StreamDockHub]


@dataclass(slots=True)
class StreamDockData:
    """Process-wide data: survives config entry reloads."""

    version: str
    watchers: CardWatchers = field(default_factory=CardWatchers)


DATA_KEY: HassKey[StreamDockData] = HassKey(DOMAIN)


def async_get_hub(hass: HomeAssistant) -> StreamDockHub | None:
    """Return the hub of the loaded config entry, if there is one."""
    entries: list[StreamDockConfigEntry] = hass.config_entries.async_loaded_entries(
        DOMAIN
    )
    return entries[0].runtime_data if entries else None
