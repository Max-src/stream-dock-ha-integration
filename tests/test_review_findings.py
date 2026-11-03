"""Review tests: each asserts the correct behaviour, so each fails while the defect exists."""

from __future__ import annotations

import contextlib
from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stream_dock_ha.data import async_get_hub
from custom_components.stream_dock_ha.errors import OfflineError

from .conftest import (
    INSTANCE_1,
    MACHINE_2,
    PAD_1,
    FakeApp,
    entity_id,
    get_device,
    pad_state,
    pc_state,
)

FAKE_INSTANCE = "deadbeefdeadbeef"


async def test_review_instance_id_takes_over_pad_device(
    hass: HomeAssistant,
    hass_ws_client: Any,
    app_with_pads: FakeApp,
) -> None:
    """A `connect` whose instance_id is a known pad_id must not touch that pad's device.

    App commands need an admin token now (protocol section 7), so this is the
    admin form; the non-admin form is refused earlier with `unauthorized`.
    """
    device_before = get_device(hass, PAD_1)
    assert device_before is not None
    assert device_before.name == "Desk pad"

    # pad ids are given to any user by stream_dock_ha/pads.
    evil = FakeApp(
        await hass_ws_client(hass),
        instance_id=PAD_1,
        machine=MACHINE_2,
        name="EVIL",
    )
    result = await evil.connect()
    await hass.async_block_till_done()

    device_after = get_device(hass, PAD_1)
    # Expected: refused (renew_instance) and the pad's device untouched.
    assert device_after.name == "Desk pad", (
        f"pad device renamed to {device_after.name!r}"
    )
    assert not result["success"], "connect with a pad's id was accepted"
    assert result["error"]["code"] == "renew_instance"


async def test_review_fake_pad_id_attaches_to_real_pc_device(
    hass: HomeAssistant,
    hass_ws_client: Any,
    app_with_pads: FakeApp,
) -> None:
    """A pad whose id equals a PC's instance_id must not take over that PC's device.

    In its admin form, as for the test above.
    """
    pc_device = get_device(hass, INSTANCE_1)
    assert pc_device is not None

    evil = FakeApp(
        await hass_ws_client(hass),
        instance_id=FAKE_INSTANCE,
        machine=MACHINE_2,
        name="EVIL",
    )
    assert (await evil.connect())["success"]
    result = await evil.send_state([pad_state(INSTANCE_1, name="Fake pad")])
    await hass.async_block_till_done()

    hub = async_get_hub(hass)
    assert hub is not None
    hijacked = hub.pad_by_device_id(pc_device.id)
    assert result["result"]["renew_pads"] == [INSTANCE_1] or hijacked is None, (
        "the real PC's device is now treated as the fake PC's pad; "
        f"device name is {get_device(hass, INSTANCE_1).name!r}"
    )


async def test_review_picture_cache_takes_any_name(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """The picture cache should only hold the pad's screen controls."""
    for batch in range(5):
        result = await app_with_pads.call(
            {
                "type": "stream_dock_ha/pictures",
                "pad_id": PAD_1,
                "scale": 2,
                "complete": False,
                "pictures": {
                    f"junk_{batch}_{n}": {"hash": "x", "data": "A" * 100}
                    for n in range(200)
                },
            }
        )
        assert result["success"]

    hub = async_get_hub(hass)
    assert hub is not None
    pad = hub.pads[PAD_1]
    extra = set(pad.pictures.pictures) - set(pad.screen_controls)
    assert not extra, f"{len(extra)} names that aren't controls are cached and replayed"


async def test_review_light_low_brightness_turns_screen_dark(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """light.turn_on with brightness 1 (lowest 'on') must not send level 0."""
    light = entity_id(hass, "light", f"{PAD_1}_screen")
    task = hass.async_create_task(
        hass.services.async_call(
            "light", "turn_on", {"entity_id": light, "brightness": 1}, blocking=True
        )
    )
    first = await app_with_pads.next_event("command")
    await app_with_pads.reply(first["request_id"], result={"on": True})
    second = await app_with_pads.next_event("command")
    await app_with_pads.reply(second["request_id"])
    await task
    assert second["data"]["command"] == "set_brightness"
    assert second["data"]["level"] >= 1, "brightness 1 was sent as level 0"


async def test_review_request_ids_repeat_after_reload(
    hass: HomeAssistant, app_with_pads: FakeApp, setup_entry: MockConfigEntry
) -> None:
    """Request ids restart at r-1 after a reload, so a late reply can answer the wrong request."""
    hub = async_get_hub(hass)
    task = hass.async_create_task(hub.async_command(PAD_1, "next_page"))
    first = await app_with_pads.next_event("command")
    assert await hass.config_entries.async_reload(setup_entry.entry_id)
    await hass.async_block_till_done()
    with contextlib.suppress(OfflineError):
        await task

    assert (await app_with_pads.connect())["success"]
    await app_with_pads.send_state()
    hub = async_get_hub(hass)
    task = hass.async_create_task(hub.async_command(PAD_1, "show_page", {"page": 3}))
    second = await app_with_pads.next_event("command")
    # The app's late answer to the first command would resolve the second.
    await app_with_pads.reply(first["request_id"], result={"stale": True})
    # With distinct ids the stale reply is ignored, so the real answer is needed.
    if first["request_id"] != second["request_id"]:
        await app_with_pads.reply(second["request_id"], result={"page": 3})
    result = await task
    assert result != {"stale": True}
    assert first["request_id"] != second["request_id"], (
        f"both commands used {first['request_id']}; the stale reply returned {result}"
    )


async def test_review_invalid_last_press_freezes_sensor(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """A last_press the sensor can't show should make it unknown, not leave it stale."""
    sensor = entity_id(hass, "sensor", f"{INSTANCE_1}_last_press")
    before = hass.states.get(sensor).state
    await app_with_pads.send_state(pc=pc_state(last_press="2026-11-03T10:00:00"))
    await hass.async_block_till_done()
    after = hass.states.get(sensor).state
    assert after != before, f"sensor stuck at {after} after a naive timestamp"
