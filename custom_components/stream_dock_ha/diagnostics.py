"""Diagnostics for Stream Dock HA. Pictures are left out."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import PROTOCOL
from .data import StreamDockConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: StreamDockConfigEntry
) -> dict[str, Any]:
    """Return what the hub knows, without pictures."""
    hub = entry.runtime_data
    return {
        "protocol": PROTOCOL,
        "integration_version": hub.version,
        "options": dict(entry.options),
        "pcs": [
            {
                "instance_id": pc.instance_id,
                "machine": pc.machine,
                "name": pc.name,
                "online": pc.online,
                "app_version": pc.app_version,
                "control": pc.control,
                "user": pc.user,
                "pc": pc.pc_state,
                "watch": pc.sent_watch,
            }
            for pc in hub.pcs.values()
        ],
        "pads": [
            {
                "pad_id": pad.pad_id,
                "instance_id": pad.instance_id,
                "listed": pad.listed,
                "cards_watching": hub.watchers.count(pad.pad_id),
                "pictures_cached": (
                    {"scale": pad.pictures.scale, "count": len(pad.pictures.pictures)}
                    if pad.pictures
                    else None
                ),
                "state": pad.state,
            }
            for pad in hub.pads.values()
        ],
    }
