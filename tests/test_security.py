"""Protocol section 7 rules, the picture cache and the life cycle fixes."""

from __future__ import annotations

import asyncio
import re
from typing import Any
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
import probatio
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stream_dock_ha.const import DOMAIN, STORAGE_KEY
from custom_components.stream_dock_ha.data import DATA_KEY, async_get_hub
from custom_components.stream_dock_ha.errors import OfflineError

from .conftest import (
    INSTANCE_1,
    INSTANCE_2,
    MACHINE_1,
    MACHINE_2,
    PAD_1,
    PAD_2,
    FakeApp,
    entity_id,
    get_device,
    layout,
    pad_state,
    pc_state,
)

PICTURE = {"hash": "1b7c03e9aa4d2f60", "data": "AAAA"}

APP_MESSAGES: dict[str, dict[str, Any]] = {
    "state": {
        "type": "stream_dock_ha/state",
        "name": "EVIL",
        "control": True,
        "pc": pc_state(),
        "pads": [pad_state(PAD_2)],
    },
    "pressed": {
        "type": "stream_dock_ha/pressed",
        "pad_id": PAD_1,
        "control": "key_1",
    },
    "pictures": {
        "type": "stream_dock_ha/pictures",
        "pad_id": PAD_1,
        "scale": 2,
        "complete": True,
        "pictures": {"key_1": PICTURE},
    },
    "reply": {"type": "stream_dock_ha/reply", "request_id": "r-1", "ok": True},
}


# ----------------------------------------------------------------------
# Admin-only app commands


async def test_non_admin_connect_unauthorized(
    hass: HomeAssistant,
    hass_ws_client: Any,
    hass_read_only_access_token: str,
    setup_entry: MockConfigEntry,
) -> None:
    """A non-admin can't connect as a PC, so no device is made."""
    evil = FakeApp(
        await hass_ws_client(hass, hass_read_only_access_token),
        instance_id=INSTANCE_2,
        machine=MACHINE_2,
    )
    result = await evil.connect()
    assert not result["success"]
    assert result["error"]["code"] == "unauthorized"
    await hass.async_block_till_done()
    assert get_device(hass, INSTANCE_2) is None
    assert INSTANCE_2 not in async_get_hub(hass).pcs


@pytest.mark.parametrize("command", list(APP_MESSAGES))
async def test_non_admin_app_commands_unauthorized(
    hass: HomeAssistant,
    hass_ws_client: Any,
    hass_read_only_access_token: str,
    app_with_pads: FakeApp,
    command: str,
) -> None:
    """`state`, `pressed`, `pictures` and `reply` need an admin token."""
    evil = FakeApp(await hass_ws_client(hass, hass_read_only_access_token))
    result = await evil.call(APP_MESSAGES[command])
    assert not result["success"]
    assert result["error"]["code"] == "unauthorized"
    await hass.async_block_till_done()
    assert get_device(hass, PAD_2) is None


async def test_default_test_client_is_admin(
    hass: HomeAssistant, hass_admin_user: Any, app: FakeApp
) -> None:
    """The simulated app logs in as an administrator."""
    pc = async_get_hub(hass).pcs[INSTANCE_1]
    assert pc.user == hass_admin_user.name


# ----------------------------------------------------------------------
# One id space


async def test_connect_with_pad_id_renews_instance(
    hass: HomeAssistant, hass_ws_client: Any, app_with_pads: FakeApp
) -> None:
    """An instance_id that is a known pad id gets `renew_instance`."""
    other = FakeApp(await hass_ws_client(hass), instance_id=PAD_1, machine=MACHINE_1)
    result = await other.connect()
    assert result["error"]["code"] == "renew_instance"
    assert PAD_1 not in async_get_hub(hass).pcs


async def test_state_with_instance_id_renews_pad(
    hass: HomeAssistant, hass_ws_client: Any, app_with_pads: FakeApp
) -> None:
    """A pad whose id is a known instance_id (its own PC's too) is renewed."""
    other = FakeApp(
        await hass_ws_client(hass), instance_id=INSTANCE_2, machine=MACHINE_2
    )
    assert (await other.connect())["success"]
    result = await other.send_state(
        [pad_state(INSTANCE_1, name="Fake"), pad_state(INSTANCE_2, name="Self")]
    )
    assert result["result"] == {"renew_pads": [INSTANCE_1, INSTANCE_2]}
    hub = async_get_hub(hass)
    assert INSTANCE_1 not in hub.pads
    assert INSTANCE_2 not in hub.pads
    assert get_device(hass, INSTANCE_1).name == "DESKTOP-MAX"


# ----------------------------------------------------------------------
# The picture cache


async def _pictures(app: FakeApp, complete: bool, pictures: dict[str, Any]) -> None:
    result = await app.call(
        {
            "type": "stream_dock_ha/pictures",
            "pad_id": PAD_1,
            "scale": 2,
            "complete": complete,
            "pictures": pictures,
        }
    )
    assert result["success"], result


async def test_picture_cache_keeps_screen_controls_only(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """Names that aren't screen controls are neither cached nor complete."""
    await _pictures(
        app_with_pads,
        False,
        {"key_1": PICTURE, "junk": PICTURE, "top_knob_press": PICTURE},
    )
    pad = async_get_hub(hass).pads[PAD_1]
    assert pad.pictures.pictures == {"key_1": PICTURE}
    event = async_get_hub(hass).pictures_event(pad)
    assert event["complete"] is False
    assert event["pictures"] == {"key_1": PICTURE}


async def test_pictures_event_complete_after_complete_set(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """The cache is complete once a complete set came, and stays so."""
    await _pictures(app_with_pads, True, {"key_1": PICTURE})
    await _pictures(app_with_pads, False, {"key_2": PICTURE})
    hub = async_get_hub(hass)
    event = hub.pictures_event(hub.pads[PAD_1])
    assert event["complete"] is True
    assert event["pictures"] == {
        "key_1": PICTURE,
        "key_2": PICTURE,
        "key_3": None,
        "band_1": None,
    }

    # A different scale resets the cache: not complete until a full set comes.
    await app_with_pads.call(
        {
            "type": "stream_dock_ha/pictures",
            "pad_id": PAD_1,
            "scale": 3,
            "complete": False,
            "pictures": {"key_1": PICTURE},
        }
    )
    event = hub.pictures_event(hub.pads[PAD_1])
    assert event["complete"] is False
    assert event["scale"] == 3


async def test_layout_version_change_drops_cache(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """A new layout version drops the cached pictures; other changes don't."""
    await _pictures(app_with_pads, True, {"key_1": PICTURE})
    hub = async_get_hub(hass)
    await app_with_pads.send_state([pad_state(brightness=50), *app_with_pads.pads[1:]])
    assert hub.pads[PAD_1].pictures is not None
    await app_with_pads.send_state(
        [pad_state(layout=layout("0000000000000002")), *app_with_pads.pads[1:]]
    )
    assert hub.pads[PAD_1].pictures is None
    assert hub.pictures_event(hub.pads[PAD_1]) is None


# ----------------------------------------------------------------------
# Requests


async def test_request_ids_are_random(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """Request ids are `r-` and 16 hex characters, different each time."""
    hub = async_get_hub(hass)
    ids = []
    for _ in range(2):
        task = hass.async_create_task(hub.async_command(PAD_1, "next_page"))
        event = await app_with_pads.next_event("command")
        await app_with_pads.reply(event["request_id"])
        await task
        ids.append(event["request_id"])
    assert all(re.fullmatch(r"r-[0-9a-f]{16}", rid) for rid in ids), ids
    assert ids[0] != ids[1]


async def test_replaced_connection_fails_pending_at_once(
    hass: HomeAssistant, hass_ws_client: Any, app_with_pads: FakeApp
) -> None:
    """The old link's pending requests fail with the offline error at once."""
    hub = async_get_hub(hass)
    task = hass.async_create_task(hub.async_command(PAD_1, "next_page"))
    await app_with_pads.next_event("command")

    again = FakeApp(await hass_ws_client(hass))
    assert (await again.connect())["success"]
    async with asyncio.timeout(1):
        with pytest.raises(OfflineError):
            await task


async def test_app_commands_not_connected_without_hub(
    hass: HomeAssistant, app_with_pads: FakeApp, setup_entry: MockConfigEntry
) -> None:
    """With no hub loaded, app commands but `connect` get `not_connected`."""
    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    await hass.async_block_till_done()
    for name, msg in APP_MESSAGES.items():
        result = await app_with_pads.call(msg)
        assert result["error"]["code"] == "not_connected", name
    assert (await app_with_pads.connect())["error"]["code"] == "not_set_up"


# ----------------------------------------------------------------------
# Life cycle


async def test_remove_entry_removes_store(
    hass: HomeAssistant, hass_storage: dict[str, Any], app_with_pads: FakeApp
) -> None:
    """Removing the integration deletes what it stored."""
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert STORAGE_KEY in hass_storage
    await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert STORAGE_KEY not in hass_storage


async def test_failed_setup_leaves_no_watch_listener(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A setup that fails after the hub started doesn't leak its listener."""
    config_entry.add_to_hass(hass)
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups",
        side_effect=HomeAssistantError("boom"),
    ):
        await hass.config_entries.async_setup(config_entry.entry_id)
        await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_ERROR
    assert not hass.data[DATA_KEY].watchers._listeners


# ----------------------------------------------------------------------
# Entities


async def test_light_brightness_never_zero_while_on(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """Level 0 shows as brightness 1; full brightness maps both ways."""
    light = entity_id(hass, "light", f"{PAD_1}_screen")
    await app_with_pads.send_state([pad_state(brightness=0), *app_with_pads.pads[1:]])
    await hass.async_block_till_done()
    assert hass.states.get(light).attributes["brightness"] == 1
    await app_with_pads.send_state([pad_state(brightness=100), *app_with_pads.pads[1:]])
    await hass.async_block_till_done()
    assert hass.states.get(light).attributes["brightness"] == 255


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-11-03T10:00:00Z", "2026-11-03T10:00:00+00:00"),
        ("2026-11-03T11:00:00+01:00", "2026-11-03T10:00:00+00:00"),
        ("2026-11-03T10:00:00", "unknown"),
        ("yesterday", "unknown"),
        ("2026-13-45T99:00:00Z", "unknown"),
        (None, "unknown"),
    ],
)
async def test_last_press_values(
    hass: HomeAssistant, app_with_pads: FakeApp, value: str | None, expected: str
) -> None:
    """Only times with a time zone are shown; anything else is unknown."""
    sensor = entity_id(hass, "sensor", f"{INSTANCE_1}_last_press")
    await app_with_pads.send_state(pc=pc_state(last_press=value))
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == expected
    # Never frozen: a good value afterwards shows.
    await app_with_pads.send_state(pc=pc_state(last_press="2026-11-03T12:00:00Z"))
    await hass.async_block_till_done()
    assert hass.states.get(sensor).state == "2026-11-03T12:00:00+00:00"


@pytest.mark.parametrize("service", ["rename_profile", "duplicate_profile"])
async def test_profile_required(
    hass: HomeAssistant, app_with_pads: FakeApp, service: str
) -> None:
    """`rename_profile` and `duplicate_profile` need `profile`."""
    with pytest.raises(probatio.Invalid):
        await hass.services.async_call(
            DOMAIN,
            service,
            {"device_id": get_device(hass, PAD_1).id, "name": "New"},
            blocking=True,
        )
