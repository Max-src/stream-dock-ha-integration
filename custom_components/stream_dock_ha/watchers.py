"""Cards watching pads.

Watchers live at the domain level rather than in the hub, so a card keeps its
subscription when the config entry reloads.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.core import CALLBACK_TYPE, callback

type WatchSender = Callable[[dict[str, Any]], None]
type WatchListener = Callable[[str], None]


@dataclass(slots=True, eq=False)
class _Watcher:
    scale: int
    send: WatchSender


class CardWatchers:
    """Track which cards watch which pads, and at what scale."""

    def __init__(self) -> None:
        """Initialize the registry."""
        self._by_pad: dict[str, set[_Watcher]] = {}
        self._listeners: set[WatchListener] = set()

    @callback
    def async_add(self, pad_id: str, scale: int, send: WatchSender) -> CALLBACK_TYPE:
        """Add a watcher and return a callback that removes it."""
        watcher = _Watcher(scale, send)
        self._by_pad.setdefault(pad_id, set()).add(watcher)
        self._changed(pad_id)

        @callback
        def remove() -> None:
            watchers = self._by_pad.get(pad_id)
            if watchers is None or watcher not in watchers:
                return
            watchers.discard(watcher)
            if not watchers:
                del self._by_pad[pad_id]
            self._changed(pad_id)

        return remove

    @callback
    def async_listen(self, listener: WatchListener) -> CALLBACK_TYPE:
        """Call `listener(pad_id)` whenever a pad's watchers change."""
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def scale(self, pad_id: str) -> int | None:
        """Return the largest scale asked for a pad, or None if nobody watches."""
        if not (watchers := self._by_pad.get(pad_id)):
            return None
        return max(watcher.scale for watcher in watchers)

    def count(self, pad_id: str) -> int:
        """Return how many cards watch a pad."""
        return len(self._by_pad.get(pad_id, ()))

    @callback
    def async_send(self, pad_id: str, message: dict[str, Any]) -> None:
        """Send an event to every card watching a pad."""
        for watcher in list(self._by_pad.get(pad_id, ())):
            watcher.send(message)

    def _changed(self, pad_id: str) -> None:
        for listener in list(self._listeners):
            listener(pad_id)
