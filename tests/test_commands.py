"""Tests for command events: entity changes and actions."""

from __future__ import annotations

import asyncio
import base64
from typing import Any
from unittest.mock import patch

from homeassistant.core import Context, HomeAssistant
from homeassistant.exceptions import HomeAssistantError, Unauthorized
import pytest

from custom_components.stream_dock_ha.const import DOMAIN

from .conftest import INSTANCE_1, PAD_1, FakeApp, entity_id, get_device


async def _answer(app: FakeApp, ok: bool = True, **fields: Any) -> dict[str, Any]:
    """Wait for the next command event, answer it and return it."""
    event = await app.next_event("command")
    reply = await app.reply(event["request_id"], ok, **fields)
    assert reply["success"], reply
    return event


async def test_select_sends_show_profile(
    hass: HomeAssistant, app_with_pads: FakeApp, hass_admin_user: Any
) -> None:
    """Choosing a profile sends `show_profile` and waits for the reply."""
    task = hass.async_create_task(
        hass.services.async_call(
            "select",
            "select_option",
            {
                "entity_id": entity_id(hass, "select", f"{PAD_1}_profile"),
                "option": "Games",
            },
            blocking=True,
            context=Context(user_id=hass_admin_user.id),
        )
    )
    event = await _answer(app_with_pads, result={"profile": "Games"})
    assert event["kind"] == "command"
    assert event["request_id"].startswith("r-")
    assert event["data"] == {
        "command": "show_profile",
        "profile": "Games",
        "pad": PAD_1,
        "source": "action",
        "user": hass_admin_user.name,
    }
    await task


async def test_light_and_number_commands(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """The screen light and the page number send their commands."""
    light = entity_id(hass, "light", f"{PAD_1}_screen")
    task = hass.async_create_task(
        hass.services.async_call(
            "light", "turn_on", {"entity_id": light, "brightness": 255}, blocking=True
        )
    )
    first = await _answer(app_with_pads, result={"on": True})
    assert first["data"]["command"] == "set_screen"
    assert first["data"]["on"] is True
    assert "user" not in first["data"]
    second = await _answer(app_with_pads)
    assert second["data"]["command"] == "set_brightness"
    assert second["data"]["level"] == 100
    await task

    task = hass.async_create_task(
        hass.services.async_call(
            "light", "turn_off", {"entity_id": light}, blocking=True
        )
    )
    event = await _answer(app_with_pads)
    assert event["data"]["command"] == "set_screen"
    assert event["data"]["on"] is False
    await task

    task = hass.async_create_task(
        hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id(hass, "number", f"{PAD_1}_page"), "value": 2},
            blocking=True,
        )
    )
    event = await _answer(app_with_pads)
    assert event["data"]["command"] == "show_page"
    assert event["data"]["page"] == 2
    await task

    task = hass.async_create_task(
        hass.services.async_call(
            "switch",
            "turn_on",
            {"entity_id": entity_id(hass, "switch", f"{PAD_1}_mini_monitor")},
            blocking=True,
        )
    )
    event = await _answer(app_with_pads)
    assert event["data"]["command"] == "mini_monitor"
    assert event["data"]["on"] is True
    await task

    task = hass.async_create_task(
        hass.services.async_call(
            "notify",
            "send_message",
            {
                "entity_id": entity_id(hass, "notify", f"{PAD_1}_alert"),
                "title": "Door",
                "message": "Someone's here",
            },
            blocking=True,
        )
    )
    event = await _answer(app_with_pads)
    assert event["data"]["command"] == "show_alert"
    assert event["data"]["title"] == "Door"
    assert event["data"]["message"] == "Someone's here"
    await task


async def test_image_fetches_snapshot(
    hass: HomeAssistant, app_with_pads: FakeApp, hass_client: Any
) -> None:
    """The picture asks for a snapshot, once per look."""
    image = entity_id(hass, "image", f"{PAD_1}_picture")
    state = hass.states.get(image)
    client = await hass_client()
    jpeg = b"\xff\xd8\xff\xe0fake-jpeg"

    async def fetch() -> bytes:
        response = await client.get(state.attributes["entity_picture"])
        assert response.status == 200
        return await response.read()

    task = hass.async_create_task(fetch())
    event = await _answer(
        app_with_pads,
        result={"content_type": "image/jpeg", "data": base64.b64encode(jpeg).decode()},
    )
    assert event["data"] == {
        "command": "snapshot",
        "scale": 1,
        "pad": PAD_1,
        "source": "action",
    }
    assert await task == jpeg

    # Same look: served from memory without asking the PC.
    assert await fetch() == jpeg
    await app_with_pads.drain()
    assert not app_with_pads.queued_events(app_with_pads.sub_id, "command")


async def test_action_round_trip_with_response(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """An action returns the app's result as response data."""
    device_id = get_device(hass, PAD_1).id
    task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "get_key",
            {"device_id": device_id, "key": 3, "page": 2},
            blocking=True,
            return_response=True,
        )
    )
    event = await _answer(app_with_pads, result={"title": "Desk lamp"})
    assert event["data"] == {
        "command": "get_key",
        "key": 3,
        "page": 2,
        "pad": PAD_1,
        "source": "action",
    }
    assert await task == {"title": "Desk lamp"}

    task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "get_state",
            {"device_id": device_id},
            blocking=True,
            return_response=True,
        )
    )
    event = await _answer(app_with_pads, result={"pads": []})
    assert event["data"]["command"] == "state"
    assert await task == {"pads": []}

    task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "show_alert",
            {
                "device_id": device_id,
                "title": "Door",
                "color": [255, 0, 0],
                "seconds": 30,
                "camera": "camera.front_door",
            },
            blocking=True,
        )
    )
    event = await _answer(app_with_pads, result={})
    assert event["data"] == {
        "command": "show_alert",
        "title": "Door",
        "color": [255, 0, 0],
        "seconds": 30,
        "camera": "camera.front_door",
        "pad": PAD_1,
        "source": "action",
    }
    assert await task is None


async def test_copy_key_resolves_target_device(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """`to.device_id` becomes the app's `to.pad`."""
    task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "copy_key",
            {
                "device_id": get_device(hass, PAD_1).id,
                "key": 1,
                "to": {"key": 2, "device_id": get_device(hass, PAD_1).id},
            },
            blocking=True,
        )
    )
    event = await _answer(app_with_pads)
    assert event["data"]["to"] == {"key": 2, "pad": PAD_1}
    await task


async def test_action_app_refuses(hass: HomeAssistant, app_with_pads: FakeApp) -> None:
    """`ok: false` raises with the app's words."""
    task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "press_key",
            {"device_id": get_device(hass, PAD_1).id, "key": 1},
            blocking=True,
        )
    )
    await _answer(app_with_pads, ok=False, error="That key opens programs")
    with pytest.raises(HomeAssistantError) as err:
        await task
    assert err.value.translation_key == "failed"
    assert err.value.translation_placeholders == {"message": "That key opens programs"}


async def test_action_timeout(hass: HomeAssistant, app_with_pads: FakeApp) -> None:
    """No answer in time raises."""
    with (
        patch("custom_components.stream_dock_ha.hub.REQUEST_TIMEOUT", 0.05),
        pytest.raises(HomeAssistantError) as err,
    ):
        await hass.services.async_call(
            DOMAIN,
            "next_page",
            {"device_id": get_device(hass, PAD_1).id},
            blocking=True,
        )
    assert err.value.translation_key == "timeout"
    # A late reply is ignored without an error.
    event = await app_with_pads.next_event("command")
    assert (await app_with_pads.reply(event["request_id"]))["success"]


async def test_action_offline(hass: HomeAssistant, app_with_pads: FakeApp) -> None:
    """An action for a pad whose PC is gone raises."""
    await app_with_pads.client.close()
    await hass.async_block_till_done()
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN,
            "next_page",
            {"device_id": get_device(hass, PAD_1).id},
            blocking=True,
        )
    assert err.value.translation_key == "offline"


async def test_pc_drops_while_waiting(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """A pending action fails at once when the PC disconnects."""
    task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "next_page",
            {"device_id": get_device(hass, PAD_1).id},
            blocking=True,
        )
    )
    await app_with_pads.next_event("command")
    await app_with_pads.client.close()
    with pytest.raises(HomeAssistantError) as err:
        async with asyncio.timeout(5):
            await task
    assert err.value.translation_key == "offline"


async def test_control_off(hass: HomeAssistant, app_with_pads: FakeApp) -> None:
    """With control off, changes are refused without asking; reads still go."""
    await app_with_pads.send_state(control=False)
    device_id = get_device(hass, PAD_1).id
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN, "next_page", {"device_id": device_id}, blocking=True
        )
    assert err.value.translation_key == "control_off"

    task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "get_state",
            {"device_id": device_id},
            blocking=True,
            return_response=True,
        )
    )
    await _answer(app_with_pads, result={"pads": []})
    assert await task == {"pads": []}


async def test_non_admin_cannot_change(
    hass: HomeAssistant, app_with_pads: FakeApp, hass_read_only_user: Any
) -> None:
    """Non-administrators can read but not change through actions."""
    device_id = get_device(hass, PAD_1).id
    context = Context(user_id=hass_read_only_user.id)
    with pytest.raises(Unauthorized):
        await hass.services.async_call(
            DOMAIN,
            "next_page",
            {"device_id": device_id},
            blocking=True,
            context=context,
        )
    task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "get_state",
            {"device_id": device_id},
            blocking=True,
            return_response=True,
            context=context,
        )
    )
    event = await _answer(app_with_pads, result={"pads": []})
    assert event["data"]["user"] == hass_read_only_user.name
    await task


async def test_action_needs_a_pad_device(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """A PC's device isn't a pad."""
    with pytest.raises(HomeAssistantError) as err:
        await hass.services.async_call(
            DOMAIN,
            "next_page",
            {"device_id": get_device(hass, INSTANCE_1).id},
            blocking=True,
        )
    assert err.value.translation_key == "not_a_pad"
