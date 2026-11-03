"""Errors raised by the Stream Dock HA hub."""

from __future__ import annotations

from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN


class StreamDockError(HomeAssistantError):
    """A command could not be carried out.

    `code` is the WebSocket error code of protocol section 5.3, and the
    translation key used when the error reaches an action or an entity.
    """

    code = "failed"
    default_message = "The command failed"

    def __init__(self, message: str | None = None) -> None:
        """Initialize the error."""
        self.text = message or self.default_message
        super().__init__(
            translation_domain=DOMAIN,
            translation_key=self.code,
            translation_placeholders={"message": self.text},
        )


class PadNotFoundError(StreamDockError):
    """The pad isn't known."""

    code = "not_found"
    default_message = "Unknown pad"


class OfflineError(StreamDockError):
    """The pad's PC isn't connected."""

    code = "offline"
    default_message = "The PC isn't connected"


class ControlOffError(StreamDockError):
    """The app doesn't let Home Assistant control it."""

    code = "control_off"
    default_message = "Home Assistant control is turned off in the app"


class NoAnswerError(StreamDockError):
    """The app didn't answer in time."""

    code = "timeout"
    default_message = "The PC didn't answer"


class AppRefusedError(StreamDockError):
    """The app answered `ok: false`."""

    code = "failed"
