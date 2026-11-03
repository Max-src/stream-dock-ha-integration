"""Constants for the Stream Dock HA integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "stream_dock_ha"
NAME: Final = "Stream Dock HA"

PROTOCOL: Final = 1
"""The protocol version this integration speaks (docs/protocol.md)."""

REQUEST_TIMEOUT: Final = 10
"""Seconds to wait for the app's reply to a command event."""

STORAGE_KEY: Final = DOMAIN
STORAGE_VERSION: Final = 1
STORAGE_SAVE_DELAY: Final = 10

CONF_ADMIN_ONLY_PRESS: Final = "admin_only_press"

EVENT_PRESSED: Final = "stream_dock_ha_event"
"""Bus event fired for every press on a pad."""

URL_BASE: Final = "/stream_dock_ha"
CARD_FILENAME: Final = "stream-dock-card.js"
CARD_URL: Final = f"{URL_BASE}/{CARD_FILENAME}"

DEFAULT_WATCH_SCALE: Final = 2

KIND_STREAM_DOCK_293S: Final = "stream_dock_293s"
KIND_AKP03E: Final = "akp03e"
KIND_DASHBOARD: Final = "dashboard"

MANUFACTURERS: Final = {
    KIND_STREAM_DOCK_293S: "Mirabox",
    KIND_AKP03E: "AJAZZ",
    KIND_DASHBOARD: NAME,
}

EVENT_TYPE_DISMISSED: Final = "dismissed"

PLATFORMS: Final = [
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.IMAGE,
    Platform.LIGHT,
    Platform.NOTIFY,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

# Commands the app runs even while its control setting is off (protocol section 7).
READ_ONLY_COMMANDS: Final = frozenset({"state", "get_key", "snapshot"})


def signal_new_pad(entry_id: str) -> str:
    """Return the signal sent when a pad is first known."""
    return f"{DOMAIN}_{entry_id}_new_pad"


def signal_new_pc(entry_id: str) -> str:
    """Return the signal sent when a PC is first known."""
    return f"{DOMAIN}_{entry_id}_new_pc"


def signal_pad(entry_id: str, pad_id: str) -> str:
    """Return the signal sent when a pad's data or availability changes."""
    return f"{DOMAIN}_{entry_id}_pad_{pad_id}"


def signal_pc(entry_id: str, instance_id: str) -> str:
    """Return the signal sent when a PC's data or availability changes."""
    return f"{DOMAIN}_{entry_id}_pc_{instance_id}"


def signal_press(entry_id: str, pad_id: str) -> str:
    """Return the signal sent for each press on a pad."""
    return f"{DOMAIN}_{entry_id}_press_{pad_id}"
