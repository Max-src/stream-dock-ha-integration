"""Tests for the card's commands: pads, watch and press."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import PAD_1, PAD_DASH, FakeApp, WsPeer, get_device, pad_state

PICTURE_1 = {"hash": "1b7c03e9aa4d2f60", "data": "AAAA"}
PICTURE_2 = {"hash": "2b7c03e9aa4d2f60", "data": "BBBB"}


async def _watch(card: WsPeer, pad_id: str = PAD_1, scale: int | None = None) -> int:
    msg: dict[str, Any] = {"type": "stream_dock_ha/watch", "pad_id": pad_id}
    if scale is not None:
        msg["scale"] = scale
    msg_id = await card.send(msg)
    result = await card.result(msg_id)
    assert result["success"], result
    return msg_id


async def test_pads(
    hass: HomeAssistant, hass_ws_client: Any, app_with_pads: FakeApp
) -> None:
    """The card lists every pad with its device."""
    card = WsPeer(await hass_ws_client(hass))
    result = await card.call({"type": "stream_dock_ha/pads"})
    assert result["result"] == {
        "pads": [
            {
                "pad_id": PAD_1,
                "name": "Desk pad",
                "pc": "DESKTOP-MAX",
                "kind": "stream_dock_293s",
                "online": True,
                "device_id": get_device(hass, PAD_1).id,
            },
            {
                "pad_id": PAD_DASH,
                "name": "Tablet",
                "pc": "DESKTOP-MAX",
                "kind": "dashboard",
                "online": True,
                "device_id": get_device(hass, PAD_DASH).id,
            },
        ]
    }


async def test_watch_unknown_pad(
    hass: HomeAssistant, hass_ws_client: Any, setup_entry: MockConfigEntry
) -> None:
    """Watching an unknown pad is refused."""
    card = WsPeer(await hass_ws_client(hass))
    result = await card.call({"type": "stream_dock_ha/watch", "pad_id": PAD_1})
    assert result["error"]["code"] == "not_found"


async def test_watch_flow(
    hass: HomeAssistant, hass_ws_client: Any, app_with_pads: FakeApp
) -> None:
    """Cards get the pad and pictures; the PC gets the watch map."""
    app = app_with_pads
    card = WsPeer(await hass_ws_client(hass))
    sub = await _watch(card)
    first = await card.event(sub)
    assert first == {
        "kind": "pad",
        "online": True,
        "listed": True,
        "pc": "DESKTOP-MAX",
        "pad": pad_state(),
    }
    # The PC is asked for pictures at the default scale.
    assert await app.next_event("watch") == {"kind": "watch", "pads": {PAD_1: 2}}

    # The app sends a complete set, then one change.
    result = await app.call(
        {
            "type": "stream_dock_ha/pictures",
            "pad_id": PAD_1,
            "scale": 2,
            "complete": True,
            "pictures": {"key_1": PICTURE_1, "key_2": None},
        }
    )
    assert result["success"]
    event = await card.event(sub, "pictures")
    assert event == {
        "kind": "pictures",
        "complete": True,
        "scale": 2,
        "pictures": {"key_1": PICTURE_1, "key_2": None},
    }
    await app.call(
        {
            "type": "stream_dock_ha/pictures",
            "pad_id": PAD_1,
            "scale": 2,
            "complete": False,
            "pictures": {"key_3": PICTURE_2},
        }
    )
    event = await card.event(sub, "pictures")
    assert event["complete"] is False
    assert event["pictures"] == {"key_3": PICTURE_2}

    # A second card at a larger scale gets the cache at once and raises the scale.
    card_2 = WsPeer(await hass_ws_client(hass))
    sub_2 = await _watch(card_2, scale=3)
    assert (await card_2.event(sub_2))["kind"] == "pad"
    cached = await card_2.event(sub_2)
    assert cached == {
        "kind": "pictures",
        "complete": True,
        "scale": 2,
        "pictures": {
            "key_1": PICTURE_1,
            "key_2": None,
            "key_3": PICTURE_2,
            "band_1": None,
        },
    }
    assert await app.next_event("watch") == {"kind": "watch", "pads": {PAD_1: 3}}

    # Pad changes reach the cards.
    await app.send_state([pad_state(page=2), *app.pads[1:]])
    assert (await card.event(sub, "pad"))["pad"]["page"] == 2

    # When the second card leaves, the scale drops; when the last leaves, it's empty.
    assert (await card_2.call({"type": "unsubscribe_events", "subscription": sub_2}))[
        "success"
    ]
    assert await app.next_event("watch") == {"kind": "watch", "pads": {PAD_1: 2}}
    await card.client.close()
    assert await app.next_event("watch") == {"kind": "watch", "pads": {}}

    # The PC going away is shown to cards still watching.
    card_3 = WsPeer(await hass_ws_client(hass))
    sub_3 = await _watch(card_3)
    await card_3.event(sub_3, "pad")
    await app.client.close()
    await hass.async_block_till_done()
    offline = await card_3.event(sub_3, "pad")
    assert offline["online"] is False
    assert offline["listed"] is True
    assert offline["pad"]["id"] == PAD_1


async def test_reconnecting_pc_gets_watch(
    hass: HomeAssistant, hass_ws_client: Any, app_with_pads: FakeApp
) -> None:
    """A PC that reconnects is told at once which pads cards show."""
    card = WsPeer(await hass_ws_client(hass))
    await _watch(card, scale=1)
    assert await app_with_pads.next_event("watch") == {
        "kind": "watch",
        "pads": {PAD_1: 1},
    }
    await app_with_pads.client.close()
    await hass.async_block_till_done()

    again = FakeApp(await hass_ws_client(hass))
    assert (await again.connect())["success"]
    assert await again.next_event("watch") == {"kind": "watch", "pads": {PAD_1: 1}}


async def test_press_from_card(
    hass: HomeAssistant, hass_ws_client: Any, app_with_pads: FakeApp
) -> None:
    """A press goes to the app as `press_key` from the dashboard."""
    card = WsPeer(await hass_ws_client(hass))
    msg_id = await card.send(
        {"type": "stream_dock_ha/press", "pad_id": PAD_1, "control": "key_3"}
    )
    event = await app_with_pads.next_event("command")
    assert event["data"]["command"] == "press_key"
    assert event["data"]["control"] == "key_3"
    assert event["data"]["source"] == "dashboard"
    assert event["data"]["pad"] == PAD_1
    assert "user" in event["data"]
    await app_with_pads.reply(event["request_id"], result={})
    result = await card.result(msg_id)
    assert result["success"]
    assert result["result"] == {}

    # The app says no.
    msg_id = await card.send(
        {"type": "stream_dock_ha/press", "pad_id": PAD_1, "control": "key_1"}
    )
    event = await app_with_pads.next_event("command")
    await app_with_pads.reply(event["request_id"], ok=False, error="Not allowed")
    result = await card.result(msg_id)
    assert result["error"] == {"code": "failed", "message": "Not allowed"}

    result = await card.call(
        {
            "type": "stream_dock_ha/press",
            "pad_id": "0000000000000000",
            "control": "key_1",
        }
    )
    assert result["error"]["code"] == "not_found"

    await app_with_pads.send_state(control=False)
    result = await card.call(
        {"type": "stream_dock_ha/press", "pad_id": PAD_1, "control": "key_1"}
    )
    assert result["error"]["code"] == "control_off"

    await app_with_pads.client.close()
    await hass.async_block_till_done()
    result = await card.call(
        {"type": "stream_dock_ha/press", "pad_id": PAD_1, "control": "key_1"}
    )
    assert result["error"]["code"] == "offline"


async def test_press_permissions(
    hass: HomeAssistant,
    hass_ws_client: Any,
    hass_read_only_access_token: str,
    app_with_pads: FakeApp,
    setup_entry: MockConfigEntry,
) -> None:
    """Any user may press unless the option limits it to administrators."""
    user_card = WsPeer(await hass_ws_client(hass, hass_read_only_access_token))
    admin_card = WsPeer(await hass_ws_client(hass))

    msg_id = await user_card.send(
        {"type": "stream_dock_ha/press", "pad_id": PAD_1, "control": "key_1"}
    )
    event = await app_with_pads.next_event("command")
    await app_with_pads.reply(event["request_id"])
    assert (await user_card.result(msg_id))["success"]

    hass.config_entries.async_update_entry(
        setup_entry, options={"admin_only_press": True}
    )
    await hass.async_block_till_done()

    result = await user_card.call(
        {"type": "stream_dock_ha/press", "pad_id": PAD_1, "control": "key_1"}
    )
    assert result["error"]["code"] == "unauthorized"

    msg_id = await admin_card.send(
        {"type": "stream_dock_ha/press", "pad_id": PAD_1, "control": "key_1"}
    )
    event = await app_with_pads.next_event("command")
    await app_with_pads.reply(event["request_id"])
    assert (await admin_card.result(msg_id))["success"]


async def test_mouse_from_card(
    hass: HomeAssistant,
    hass_ws_client: Any,
    hass_read_only_access_token: str,
    app_with_pads: FakeApp,
) -> None:
    """The card's mouse goes to the app as `mouse`, for administrators only."""
    card = WsPeer(await hass_ws_client(hass))
    msg_id = await card.send(
        {
            "type": "stream_dock_ha/mouse",
            "pad_id": PAD_1,
            "action": "down",
            "x": 0.25,
            "y": 0.75,
            "button": "right",
        }
    )
    event = await app_with_pads.next_event("command")
    assert event["data"]["command"] == "mouse"
    assert event["data"]["action"] == "down"
    assert (event["data"]["x"], event["data"]["y"]) == (0.25, 0.75)
    assert event["data"]["button"] == "right"
    assert event["data"]["source"] == "dashboard"
    assert "amount" not in event["data"]
    await app_with_pads.reply(event["request_id"], result={})
    assert (await card.result(msg_id))["success"]

    # Scrolling says how far; the button is left unless asked.
    msg_id = await card.send(
        {
            "type": "stream_dock_ha/mouse",
            "pad_id": PAD_1,
            "action": "scroll",
            "x": 0.5,
            "y": 0.5,
            "amount": -3,
        }
    )
    event = await app_with_pads.next_event("command")
    assert (event["data"]["amount"], event["data"]["button"]) == (-3, "left")
    await app_with_pads.reply(
        event["request_id"], ok=False, error="Mouse from dashboard cards is off"
    )
    result = await card.result(msg_id)
    assert result["error"] == {
        "code": "failed",
        "message": "Mouse from dashboard cards is off",
    }

    # Out of the picture, or an unknown action, isn't sent.
    for bad in ({"x": 1.5}, {"action": "drag"}, {"button": "back"}):
        msg = {
            "type": "stream_dock_ha/mouse",
            "pad_id": PAD_1,
            "action": "click",
            "x": 0.5,
            "y": 0.5,
            **bad,
        }
        assert (await card.call(msg))["error"]["code"] == "invalid_format"

    user_card = WsPeer(await hass_ws_client(hass, hass_read_only_access_token))
    result = await user_card.call(
        {
            "type": "stream_dock_ha/mouse",
            "pad_id": PAD_1,
            "action": "click",
            "x": 0.5,
            "y": 0.5,
        }
    )
    assert result["error"]["code"] == "unauthorized"
