"""Data the hub keeps about PCs and pads."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.components.websocket_api import ActiveConnection


@dataclass(slots=True)
class PcLink:
    """A live `connect` subscription from a PC."""

    connection: ActiveConnection
    msg_id: int
    #: Frames name it, so only this app's frames are taken, whichever
    #: connection they come on (protocol 3.6).
    frame_key: str = ""


@dataclass(slots=True)
class Pc:
    """A PC running the app (an `instance_id`)."""

    instance_id: str
    machine: str
    name: str
    device_id: str | None = None
    link: PcLink | None = None
    control: bool = False
    app_version: str | None = None
    user: str | None = None
    pc_state: dict[str, Any] = field(default_factory=dict)
    sent_watch: dict[str, int] | None = None

    @property
    def online(self) -> bool:
        """Return whether the PC is connected now."""
        return self.link is not None


@dataclass(slots=True)
class Pictures:
    """The latest pictures of a pad, kept in memory only."""

    scale: int
    pictures: dict[str, dict[str, str] | None] = field(default_factory=dict)
    # Whether a complete set was received since the cache was last reset.
    complete: bool = False


@dataclass(slots=True)
class Pad:
    """A pad (physical or on a dashboard) of one PC."""

    pad_id: str
    instance_id: str
    state: dict[str, Any]
    device_id: str | None = None
    listed: bool = False
    pictures: Pictures | None = None

    @property
    def kind(self) -> str:
        """Return the pad's kind."""
        return str(self.state.get("kind", ""))

    @property
    def name(self) -> str:
        """Return the pad's name."""
        return str(self.state.get("name") or self.pad_id)

    @property
    def screen_controls(self) -> list[str]:
        """Return the names of the controls that show a picture."""
        return [
            control["name"]
            for control in self.state.get("layout", {}).get("controls", [])
            if control.get("screen")
        ]

    @property
    def press_controls(self) -> list[str]:
        """Return the names of the controls that can be pressed."""
        return [
            control["name"]
            for control in self.state.get("layout", {}).get("controls", [])
            if control.get("press")
        ]
