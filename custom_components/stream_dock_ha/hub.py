"""The hub: what the integration knows about every PC and pad."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from homeassistant.components.websocket_api import ActiveConnection, event_message
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store

from .const import (
    DOMAIN,
    EVENT_PRESSED,
    MANUFACTURERS,
    NAME,
    READ_ONLY_COMMANDS,
    REQUEST_TIMEOUT,
    STORAGE_KEY,
    STORAGE_SAVE_DELAY,
    STORAGE_VERSION,
    signal_new_pad,
    signal_new_pc,
    signal_pad,
    signal_pc,
    signal_press,
)
from .data import StreamDockConfigEntry, StreamDockData
from .errors import (
    AppRefusedError,
    ControlOffError,
    NoAnswerError,
    OfflineError,
    PadNotFoundError,
)
from .models import Pad, Pc, PcLink, Pictures

_LOGGER = logging.getLogger(__name__)


class RenewInstanceError(Exception):
    """The `instance_id` belongs to another machine (protocol section 2)."""


class NotConnectedError(Exception):
    """A message came on a connection that isn't a connected PC."""


class StreamDockHub:
    """Keep track of PCs, pads, their connections and pending requests."""

    def __init__(
        self, hass: HomeAssistant, entry: StreamDockConfigEntry, data: StreamDockData
    ) -> None:
        """Initialize the hub."""
        self.hass = hass
        self.entry = entry
        self.version = data.version
        self.watchers = data.watchers
        self.pcs: dict[str, Pc] = {}
        self.pads: dict[str, Pad] = {}
        self._links: dict[ActiveConnection, str] = {}
        self._pending: dict[str, tuple[str, asyncio.Future[Any]]] = {}
        self._request_counter = 0
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._unsub_watchers: CALLBACK_TYPE | None = None

    # ------------------------------------------------------------------
    # Life cycle

    async def async_setup(self) -> None:
        """Load what was stored and create the devices."""
        stored = await self._store.async_load() or {}
        for instance_id, pc in stored.get("pcs", {}).items():
            self.pcs[instance_id] = Pc(instance_id, pc["machine"], pc["name"])
        for pad_id, pad in stored.get("pads", {}).items():
            if pad["instance_id"] in self.pcs:
                self.pads[pad_id] = Pad(pad_id, pad["instance_id"], pad["state"])
        for pc in self.pcs.values():
            self._ensure_pc_device(pc)
        for pad in self.pads.values():
            self._ensure_pad_device(pad)
        self._unsub_watchers = self.watchers.async_listen(self._watchers_changed)
        for pad in self.pads.values():
            self._send_pad_to_cards(pad)

    async def async_unload(self) -> None:
        """End every PC's subscription and save."""
        if self._unsub_watchers is not None:
            self._unsub_watchers()
            self._unsub_watchers = None
        for pc in self.pcs.values():
            if pc.link is not None:
                pc.link.connection.subscriptions.pop(pc.link.msg_id, None)
                self._go_offline(pc)
        await self._store.async_save(self._storage_data())

    # ------------------------------------------------------------------
    # Lookups used by entities, actions and the WebSocket API

    def pc_of(self, pad: Pad) -> Pc:
        """Return the PC a pad belongs to."""
        return self.pcs[pad.instance_id]

    def pad_available(self, pad: Pad) -> bool:
        """Return whether a pad's entities are available."""
        return pad.listed and self.pc_of(pad).online

    def pad_by_device_id(self, device_id: str) -> Pad | None:
        """Return the pad of a device."""
        return next(
            (pad for pad in self.pads.values() if pad.device_id == device_id), None
        )

    def pad_event(self, pad: Pad) -> dict[str, Any]:
        """Return the card's `pad` event for a pad."""
        return {
            "kind": "pad",
            "online": self.pc_of(pad).online,
            "listed": pad.listed,
            "pc": self.pc_of(pad).name,
            "pad": pad.state,
        }

    @staticmethod
    def pictures_event(pad: Pad) -> dict[str, Any] | None:
        """Return the card's `pictures` event with every cached picture."""
        if pad.pictures is None:
            return None
        return {
            "kind": "pictures",
            "complete": True,
            "scale": pad.pictures.scale,
            "pictures": dict(pad.pictures.pictures),
        }

    # ------------------------------------------------------------------
    # Messages from the app

    @callback
    def async_connect(
        self, connection: ActiveConnection, msg_id: int, msg: dict[str, Any]
    ) -> Pc:
        """Link a connection to a PC. The caller sends the result."""
        instance_id: str = msg["instance_id"]
        machine: str = msg["machine"]
        pc = self.pcs.get(instance_id)
        if pc is not None and pc.machine != machine:
            raise RenewInstanceError

        # The same socket connecting again as another PC drops the first one.
        if (
            old_id := self._links.get(connection)
        ) is not None and old_id != instance_id:
            old_pc = self.pcs[old_id]
            if old_pc.link is not None:
                connection.subscriptions.pop(old_pc.link.msg_id, None)
            self._go_offline(old_pc)

        new = pc is None
        if pc is None:
            pc = self.pcs[instance_id] = Pc(instance_id, machine, msg["name"])
        elif pc.link is not None:
            # The same PC coming back: the new connection replaces the old one.
            _LOGGER.debug("PC %s replaces its old connection", instance_id)
            old = pc.link
            old.connection.subscriptions.pop(old.msg_id, None)
            self._links.pop(old.connection, None)

        pc.name = msg["name"]
        pc.control = msg["control"]
        pc.app_version = msg["app_version"]
        pc.user = connection.user.name if connection.user else None
        pc.link = PcLink(connection, msg_id)
        pc.sent_watch = None
        self._links[connection] = instance_id

        @callback
        def closed() -> None:
            if pc.link is not None and pc.link.connection is connection:
                _LOGGER.debug("PC %s disconnected", instance_id)
                self._go_offline(pc)

        connection.subscriptions[msg_id] = closed

        self._ensure_pc_device(pc)
        self._schedule_save()
        if new:
            async_dispatcher_send(
                self.hass, signal_new_pc(self.entry.entry_id), instance_id
            )
        self._pc_changed(pc, pads_too=True)
        return pc

    @callback
    def async_state(
        self, connection: ActiveConnection, msg: dict[str, Any]
    ) -> list[str]:
        """Take a full `state` and return the pad ids to renew."""
        pc = self._pc_for(connection)
        renamed = msg["name"] != pc.name
        pc_changed = renamed or (msg["control"], msg["pc"]) != (pc.control, pc.pc_state)
        pc.control = msg["control"]
        pc.pc_state = msg["pc"]
        if renamed:
            pc.name = msg["name"]
            self._ensure_pc_device(pc)
            self._schedule_save()

        renew, new_pads, changed_pads = self._apply_pad_states(pc, msg["pads"])

        if new_pads or changed_pads:
            self._schedule_save()
        for pad in new_pads:
            async_dispatcher_send(
                self.hass, signal_new_pad(self.entry.entry_id), pad.pad_id
            )
            self._send_pad_to_cards(pad)
        for pad in changed_pads:
            self._pad_changed(pad)
        if pc_changed:
            self._pc_changed(pc, pads_too=False)
        if renamed:
            # The cards show the PC's name with each pad.
            for pad in self.pads.values():
                if pad.instance_id == pc.instance_id and pad not in changed_pads:
                    self._send_pad_to_cards(pad)
        if renew:
            _LOGGER.debug("PC %s must renew pads %s", pc.instance_id, renew)
        return renew

    def _apply_pad_states(
        self, pc: Pc, states: list[dict[str, Any]]
    ) -> tuple[list[str], list[Pad], list[Pad]]:
        """Store a PC's pad states; return the renewed, new and changed pads."""
        renew: list[str] = []
        seen: set[str] = set()
        new_pads: list[Pad] = []
        changed_pads: list[Pad] = []
        for state in states:
            pad_id: str = state["id"]
            pad = self.pads.get(pad_id)
            if pad is not None and pad.instance_id != pc.instance_id:
                renew.append(pad_id)
            elif pad_id in seen:
                continue
            elif pad is None:
                pad = self.pads[pad_id] = Pad(
                    pad_id, pc.instance_id, state, listed=True
                )
                self._ensure_pad_device(pad)
                new_pads.append(pad)
            elif pad.state != state or not pad.listed:
                device_changed = any(
                    pad.state.get(key) != state.get(key)
                    for key in ("name", "model", "kind")
                )
                pad.state = state
                pad.listed = True
                if device_changed:
                    self._ensure_pad_device(pad)
                changed_pads.append(pad)
            seen.add(pad_id)

        for pad in self.pads.values():
            if (
                pad.instance_id == pc.instance_id
                and pad.listed
                and pad.pad_id not in seen
            ):
                pad.listed = False
                changed_pads.append(pad)
        return renew, new_pads, changed_pads

    @callback
    def async_pressed(self, connection: ActiveConnection, msg: dict[str, Any]) -> None:
        """Announce a press on the bus and to the pad's event entity."""
        pad = self._own_pad(self._pc_for(connection), msg["pad_id"])
        data = {
            "device_id": pad.device_id,
            "pad_id": pad.pad_id,
            "control": msg["control"],
            "profile": msg.get("profile"),
            "page": msg.get("page"),
            "title": msg.get("title"),
            "source": msg.get("source"),
            "dismissed": msg.get("dismissed", False),
        }
        self.hass.bus.async_fire(EVENT_PRESSED, data)
        async_dispatcher_send(
            self.hass, signal_press(self.entry.entry_id, pad.pad_id), data
        )

    @callback
    def async_pictures(self, connection: ActiveConnection, msg: dict[str, Any]) -> None:
        """Cache pictures and pass them to the cards."""
        pad = self._own_pad(self._pc_for(connection), msg["pad_id"])
        scale: int = msg["scale"]
        complete: bool = msg["complete"]
        pictures: dict[str, dict[str, str] | None] = msg["pictures"]
        cache = pad.pictures
        if complete or cache is None or cache.scale != scale:
            base: dict[str, dict[str, str] | None] = (
                dict.fromkeys(pad.screen_controls) if complete else {}
            )
            cache = pad.pictures = Pictures(scale, base)
        cache.pictures.update(pictures)
        self.watchers.async_send(
            pad.pad_id,
            {
                "kind": "pictures",
                "complete": complete,
                "scale": scale,
                "pictures": pictures,
            },
        )

    @callback
    def async_reply(self, connection: ActiveConnection, msg: dict[str, Any]) -> None:
        """Resolve the request a reply answers."""
        pc = self._pc_for(connection)
        request_id: str = msg["request_id"]
        pending = self._pending.get(request_id)
        if pending is None or pending[0] != pc.instance_id or pending[1].done():
            _LOGGER.debug("Reply to unknown or finished request %s", request_id)
            return
        future = pending[1]
        if msg["ok"]:
            result = msg.get("result")
            future.set_result({} if result is None else result)
        else:
            future.set_exception(AppRefusedError(msg.get("error")))

    # ------------------------------------------------------------------
    # Commands to the app

    async def async_command(
        self,
        pad_id: str,
        command: str,
        fields: dict[str, Any] | None = None,
        *,
        source: str = "action",
        user: str | None = None,
    ) -> Any:
        """Send a command event for a pad and return the app's result."""
        if (pad := self.pads.get(pad_id)) is None:
            raise PadNotFoundError
        pc = self.pc_of(pad)
        if pc.link is None:
            raise OfflineError
        if command not in READ_ONLY_COMMANDS and not pc.control:
            raise ControlOffError
        data: dict[str, Any] = {"command": command, **(fields or {})}
        data["pad"] = pad_id
        data["source"] = source
        if user:
            data["user"] = user
        return await self._async_request(pc, pc.link, data)

    async def _async_request(self, pc: Pc, link: PcLink, data: dict[str, Any]) -> Any:
        self._request_counter += 1
        request_id = f"r-{self._request_counter}"
        future: asyncio.Future[Any] = self.hass.loop.create_future()
        self._pending[request_id] = (pc.instance_id, future)
        _LOGGER.debug("Command %s to %s: %s", request_id, pc.instance_id, data)
        try:
            link.connection.send_message(
                event_message(
                    link.msg_id,
                    {"kind": "command", "request_id": request_id, "data": data},
                )
            )
            async with asyncio.timeout(REQUEST_TIMEOUT):
                return await future
        except TimeoutError:
            raise NoAnswerError from None
        finally:
            self._pending.pop(request_id, None)

    # ------------------------------------------------------------------
    # Watching

    @callback
    def _watchers_changed(self, pad_id: str) -> None:
        if (pad := self.pads.get(pad_id)) is not None:
            self.async_update_watch(pad.instance_id)

    @callback
    def async_update_watch(self, instance_id: str) -> None:
        """Send a PC its `watch` map if it changed."""
        pc = self.pcs.get(instance_id)
        if pc is None or pc.link is None:
            return
        watch = {
            pad_id: scale
            for pad_id in self._pad_ids(pc)
            if (scale := self.watchers.scale(pad_id)) is not None
        }
        if watch == pc.sent_watch:
            return
        pc.sent_watch = watch
        _LOGGER.debug("Watch for %s: %s", instance_id, watch)
        pc.link.connection.send_message(
            event_message(pc.link.msg_id, {"kind": "watch", "pads": watch})
        )

    # ------------------------------------------------------------------
    # Device removal

    @callback
    def async_remove_device(self, device: dr.DeviceEntry) -> bool:
        """Forget a pad or PC, unless it's connected now."""
        registry = dr.async_get(self.hass)
        for domain, identifier in device.identifiers:
            if domain != DOMAIN:
                continue
            if (pad := self.pads.get(identifier)) is not None:
                if self.pad_available(pad):
                    return False
                del self.pads[identifier]
            elif (pc := self.pcs.get(identifier)) is not None:
                if pc.online:
                    return False
                del self.pcs[identifier]
                for pad in [
                    p for p in self.pads.values() if p.instance_id == identifier
                ]:
                    del self.pads[pad.pad_id]
                    if pad.device_id is not None:
                        registry.async_update_device(
                            pad.device_id, remove_config_entry_id=self.entry.entry_id
                        )
        self._schedule_save()
        return True

    # ------------------------------------------------------------------
    # Internals

    def _pc_for(self, connection: ActiveConnection) -> Pc:
        if (instance_id := self._links.get(connection)) is None:
            raise NotConnectedError
        return self.pcs[instance_id]

    def _own_pad(self, pc: Pc, pad_id: str) -> Pad:
        pad = self.pads.get(pad_id)
        if pad is None or pad.instance_id != pc.instance_id:
            raise PadNotFoundError
        return pad

    def _pad_ids(self, pc: Pc) -> list[str]:
        return [
            pad_id
            for pad_id, pad in self.pads.items()
            if pad.instance_id == pc.instance_id
        ]

    @callback
    def _go_offline(self, pc: Pc) -> None:
        if pc.link is not None:
            self._links.pop(pc.link.connection, None)
        pc.link = None
        pc.sent_watch = None
        for instance_id, future in self._pending.values():
            if instance_id == pc.instance_id and not future.done():
                future.set_exception(OfflineError())
        self._pc_changed(pc, pads_too=True)

    @callback
    def _pc_changed(self, pc: Pc, *, pads_too: bool) -> None:
        async_dispatcher_send(self.hass, signal_pc(self.entry.entry_id, pc.instance_id))
        if pads_too:
            for pad in self.pads.values():
                if pad.instance_id == pc.instance_id:
                    self._pad_changed(pad)

    @callback
    def _pad_changed(self, pad: Pad) -> None:
        async_dispatcher_send(self.hass, signal_pad(self.entry.entry_id, pad.pad_id))
        self._send_pad_to_cards(pad)

    @callback
    def _send_pad_to_cards(self, pad: Pad) -> None:
        if self.watchers.count(pad.pad_id):
            self.watchers.async_send(pad.pad_id, self.pad_event(pad))

    def _ensure_pc_device(self, pc: Pc) -> None:
        device = dr.async_get(self.hass).async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers={(DOMAIN, pc.instance_id)},
            manufacturer=NAME,
            name=pc.name,
            **({"sw_version": pc.app_version} if pc.app_version else {}),
        )
        pc.device_id = device.id

    def _ensure_pad_device(self, pad: Pad) -> None:
        pc = self.pc_of(pad)
        device = dr.async_get(self.hass).async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers={(DOMAIN, pad.pad_id)},
            manufacturer=MANUFACTURERS.get(pad.kind, NAME),
            model=pad.state.get("model"),
            name=pad.name,
            **({"via_device_id": pc.device_id} if pc.device_id else {}),
        )
        pad.device_id = device.id

    def _schedule_save(self) -> None:
        self._store.async_delay_save(self._storage_data, STORAGE_SAVE_DELAY)

    @callback
    def _storage_data(self) -> dict[str, Any]:
        return {
            "pcs": {
                pc.instance_id: {
                    "instance_id": pc.instance_id,
                    "machine": pc.machine,
                    "name": pc.name,
                }
                for pc in self.pcs.values()
            },
            "pads": {
                pad.pad_id: {"instance_id": pad.instance_id, "state": pad.state}
                for pad in self.pads.values()
            },
        }
