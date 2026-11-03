"""Fixtures and an app simulator for the Stream Dock HA tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import copy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stream_dock_ha.const import DOMAIN

INSTANCE_1 = "3f9c1a7e5b2d4c60"
MACHINE_1 = "a81e44c09d1b2f37"
INSTANCE_2 = "0011223344556677"
MACHINE_2 = "8899aabbccddeeff"
PAD_1 = "9d04e1b7a2c35f18"
PAD_2 = "1234567890abcdef"
PAD_DASH = "fedcba0987654321"

RECEIVE_TIMEOUT = 5


def layout(version: str = "77e0b4a1c9d2f356") -> dict[str, Any]:
    """Return a small layout: three keys, a band tile and a knob."""
    controls = [
        {
            "name": f"key_{n}",
            "type": "key",
            "x": n - 1.0,
            "y": 0.0,
            "w": 1.0,
            "h": 1.0,
            "screen": True,
            "press": True,
        }
        for n in (1, 2, 3)
    ]
    controls.append(
        {
            "name": "band_1",
            "type": "band",
            "x": 3.2,
            "y": 0.0,
            "w": 0.94,
            "h": 0.94,
            "screen": True,
            "press": False,
        }
    )
    controls.extend(
        {
            "name": f"top_knob_{part}",
            "type": f"knob_{part}",
            "group": "top_knob",
            "x": 4.6,
            "y": 0.0,
            "w": 1.0,
            "h": 1.0,
            "screen": False,
            "press": True,
        }
        for part in ("left", "right", "press")
    )
    return {"version": version, "width": 5.6, "height": 1.0, "controls": controls}


def pad_state(
    pad_id: str = PAD_1,
    *,
    kind: str = "stream_dock_293s",
    model: str = "Stream Dock 293S",
    name: str = "Desk pad",
    **changes: Any,
) -> dict[str, Any]:
    """Return a PadState."""
    state = {
        "id": pad_id,
        "kind": kind,
        "model": model,
        "name": name,
        "connected": True,
        "screen_on": True,
        "brightness": 25,
        "mini_monitor": None if kind == "dashboard" else False,
        "profile": {"id": "51ac0e9f7d2b8346", "name": "Home"},
        "profiles": [
            {"id": "51ac0e9f7d2b8346", "name": "Home", "pages": 3},
            {"id": "61ac0e9f7d2b8346", "name": "Games", "pages": 1},
        ],
        "page": 1,
        "pages": 3,
        "look": "c2a91f0e33b7d455",
        "alert": False,
        "layout": layout(),
    }
    state.update(changes)
    return state


def pc_state(**changes: Any) -> dict[str, Any]:
    """Return the `pc` part of a state."""
    pc = {
        "mic_muted": False,
        "cpu": 12,
        "memory": 48,
        "gpu": 5,
        "last_press": "2026-11-03T09:12:44Z",
    }
    pc.update(changes)
    return pc


class WsPeer:
    """A WebSocket client that can wait for one message while others queue."""

    def __init__(self, client: Any) -> None:
        """Wrap a `hass_ws_client` client."""
        self.client = client
        self._queue: list[dict[str, Any]] = []
        self._next_id = 0

    async def send(self, msg: dict[str, Any]) -> int:
        """Send a message with the next id and return the id."""
        self._next_id += 1
        await self.client.send_json({**msg, "id": self._next_id})
        return self._next_id

    async def receive(self, match: Callable[[dict[str, Any]], bool]) -> dict[str, Any]:
        """Return the first message (queued or new) that matches."""
        for index, msg in enumerate(self._queue):
            if match(msg):
                return self._queue.pop(index)
        async with asyncio.timeout(RECEIVE_TIMEOUT):
            while True:
                msg = await self.client.receive_json()
                if match(msg):
                    return msg
                self._queue.append(msg)

    async def result(self, msg_id: int) -> dict[str, Any]:
        """Wait for the result of a message."""
        return await self.receive(lambda m: m["id"] == msg_id and m["type"] == "result")

    async def call(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Send a message and wait for its result."""
        return await self.result(await self.send(msg))

    async def event(self, sub_id: int, kind: str | None = None) -> dict[str, Any]:
        """Wait for an event on a subscription, optionally of one kind."""
        return (
            await self.receive(
                lambda m: (
                    m["id"] == sub_id
                    and m["type"] == "event"
                    and (kind is None or m["event"].get("kind") == kind)
                )
            )
        )["event"]

    def queued_events(self, sub_id: int, kind: str) -> list[dict[str, Any]]:
        """Return queued events of a kind without waiting."""
        return [
            m["event"]
            for m in self._queue
            if m["id"] == sub_id
            and m["type"] == "event"
            and m["event"].get("kind") == kind
        ]

    async def drain(self) -> None:
        """Pull every message that already arrived into the queue."""
        while True:
            try:
                async with asyncio.timeout(0.05):
                    self._queue.append(await self.client.receive_json())
            except TimeoutError:
                return


class FakeApp(WsPeer):
    """The Windows app, as Home Assistant sees it."""

    def __init__(
        self,
        client: Any,
        instance_id: str = INSTANCE_1,
        machine: str = MACHINE_1,
        name: str = "DESKTOP-MAX",
    ) -> None:
        """Initialize the app."""
        super().__init__(client)
        self.instance_id = instance_id
        self.machine = machine
        self.name = name
        self.sub_id: int | None = None
        self.frame_key = ""
        self.pads: list[dict[str, Any]] = []

    async def connect(
        self, *, protocol: int = 1, control: bool = True
    ) -> dict[str, Any]:
        """Send `connect` and return its result."""
        msg_id = await self.send(
            {
                "type": "stream_dock_ha/connect",
                "protocol": protocol,
                "app_version": "1.1.0",
                "instance_id": self.instance_id,
                "machine": self.machine,
                "name": self.name,
                "control": control,
            }
        )
        result = await self.result(msg_id)
        if result["success"]:
            self.sub_id = msg_id
            self.frame_key = result["result"]["frame_key"]
        return result

    async def send_state(
        self,
        pads: list[dict[str, Any]] | None = None,
        *,
        control: bool = True,
        pc: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Send a full `state` and return its result."""
        if pads is not None:
            self.pads = pads
        return await self.call(
            {
                "type": "stream_dock_ha/state",
                "name": self.name,
                "control": control,
                "pc": pc if pc is not None else pc_state(),
                "pads": copy.deepcopy(self.pads),
            }
        )

    async def next_event(self, kind: str | None = None) -> dict[str, Any]:
        """Wait for an event on the `connect` subscription."""
        assert self.sub_id is not None
        return await self.event(self.sub_id, kind)

    async def reply(
        self, request_id: str, ok: bool = True, **fields: Any
    ) -> dict[str, Any]:
        """Answer a command event."""
        return await self.call(
            {
                "type": "stream_dock_ha/reply",
                "request_id": request_id,
                "ok": ok,
                **fields,
            }
        )

    async def press(
        self, pad_id: str = PAD_1, control: str = "key_3", **fields: Any
    ) -> dict[str, Any]:
        """Announce a press."""
        msg = {
            "type": "stream_dock_ha/pressed",
            "pad_id": pad_id,
            "control": control,
            "profile": "Home",
            "page": 1,
            "title": "Desk lamp",
            "source": "pad",
        }
        msg.update(fields)
        return await self.call(msg)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Enable custom integrations in every test."""


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """Return the config entry."""
    return MockConfigEntry(domain=DOMAIN, title="Stream Dock HA", data={}, options={})


@pytest.fixture
async def setup_entry(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> MockConfigEntry:
    """Set up the integration with its config entry."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


@pytest.fixture
async def app(
    hass: HomeAssistant, hass_ws_client: Any, setup_entry: MockConfigEntry
) -> FakeApp:
    """Return an app that's connected, without having sent its state yet."""
    fake = FakeApp(await hass_ws_client(hass))
    result = await fake.connect()
    assert result["success"], result
    assert await fake.next_event("watch") == {"kind": "watch", "pads": {}}
    return fake


@pytest.fixture
async def app_with_pads(hass: HomeAssistant, app: FakeApp) -> FakeApp:
    """Return a connected app that has sent a 293S and a dashboard pad."""
    result = await app.send_state(
        [
            pad_state(),
            pad_state(PAD_DASH, kind="dashboard", model="Dashboard", name="Tablet"),
        ]
    )
    assert result["success"], result
    assert result["result"] == {"renew_pads": []}
    await hass.async_block_till_done()
    return app


def entity_id(hass: HomeAssistant, platform: str, unique_id: str) -> str:
    """Return an entity id from its unique id."""
    found = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
    assert found is not None, f"No {platform} with unique id {unique_id}"
    return found


def get_device(hass: HomeAssistant, identifier: str) -> Any:
    """Return this integration's device with an identifier: a PC, or a pad,
    which is a child device of its PC."""
    registry = dr.async_get(hass)
    devices = registry.async_get_devices(identifiers={(DOMAIN, identifier)})
    if devices:
        return devices[0]
    for entry in hass.config_entries.async_entries(DOMAIN):
        if child := registry.async_get_child_device_by_identifier(
            (DOMAIN, identifier), entry.entry_id
        ):
            return child
    return None
