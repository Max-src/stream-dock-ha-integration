"""Diagnostics for Stream Dock HA. Pictures and personal names are left out."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import REDACTED, async_redact_data
from homeassistant.core import HomeAssistant

from .const import PROTOCOL
from .data import StreamDockConfigEntry

# People paste diagnostics into public issues: PC, user, profile, key and alert
# names are their own words, so they're left out. Control names stay.
TO_REDACT = {"machine", "message", "name", "pc", "title", "user"}


def _pad_state(state: dict[str, Any] | None) -> dict[str, Any] | None:
    """The pad's state with names redacted, keeping its layout's control names."""
    if not state:
        return state
    rest = {key: value for key, value in state.items() if key != "layout"}
    redacted = async_redact_data(rest, TO_REDACT)
    if "layout" in state:
        redacted["layout"] = state["layout"]
    return redacted


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: StreamDockConfigEntry
) -> dict[str, Any]:
    """Return what the hub knows, without pictures or personal names."""
    hub = entry.runtime_data
    return {
        "protocol": PROTOCOL,
        "integration_version": hub.version,
        "options": dict(entry.options),
        "pcs": [
            {
                "instance_id": pc.instance_id,
                "machine": REDACTED,
                "name": REDACTED,
                "online": pc.online,
                "app_version": pc.app_version,
                "control": pc.control,
                "user": REDACTED,
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
                "state": _pad_state(pad.state),
            }
            for pad in hub.pads.values()
        ],
    }
