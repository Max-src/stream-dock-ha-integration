"""Tests for `stream_dock_ha/state`: devices, entities and `renew_pads`."""

from __future__ import annotations

from typing import Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import (
    INSTANCE_1,
    INSTANCE_2,
    MACHINE_2,
    PAD_1,
    PAD_DASH,
    FakeApp,
    entity_id,
    get_device,
    pad_state,
    pc_state,
)


async def test_state_creates_devices_and_entities(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """A state makes a device per pad, under the PC, with its entities."""
    pc_device = get_device(hass, INSTANCE_1)
    pad_device = get_device(hass, PAD_1)
    dash_device = get_device(hass, PAD_DASH)
    assert pad_device.name == "Desk pad"
    # Pads are child devices of their PC, shown under it.
    assert pad_device.parent_device_id == pc_device.id
    assert dash_device.parent_device_id == pc_device.id
    assert pc_device.manufacturer == "Stream Dock HA"

    registry = er.async_get(hass)
    pad_unique_ids = {
        entry.unique_id
        for entry in er.async_entries_for_device(registry, pad_device.id)
    }
    assert pad_unique_ids == {
        f"{PAD_1}_{key}"
        for key in (
            "profile",
            "page",
            "screen",
            "mini_monitor",
            "connected",
            "press",
            "picture",
            "alert",
        )
    }
    dash_unique_ids = {
        entry.unique_id
        for entry in er.async_entries_for_device(registry, dash_device.id)
    }
    # No Mini Monitor switch and no Connected sensor for a dashboard pad.
    assert dash_unique_ids == {
        f"{PAD_DASH}_{key}"
        for key in ("profile", "page", "screen", "press", "picture", "alert")
    }
    pc_unique_ids = {
        entry.unique_id
        for entry in er.async_entries_for_device(
            registry, pc_device.id, include_disabled_entities=True
        )
    }
    assert pc_unique_ids == {
        f"{INSTANCE_1}_{key}"
        for key in ("mic_muted", "cpu", "memory", "gpu", "last_press", "online")
    }

    profile = hass.states.get(entity_id(hass, "select", f"{PAD_1}_profile"))
    assert profile.state == "Home"
    assert profile.attributes["options"] == ["Home", "Games"]
    page = hass.states.get(entity_id(hass, "number", f"{PAD_1}_page"))
    assert page.state == "1"
    assert page.attributes["max"] == 3
    assert page.attributes["mode"] == "box"
    screen = hass.states.get(entity_id(hass, "light", f"{PAD_1}_screen"))
    assert screen.state == "on"
    assert screen.attributes["brightness"] == 64
    assert (
        hass.states.get(entity_id(hass, "switch", f"{PAD_1}_mini_monitor")).state
        == "off"
    )
    assert (
        hass.states.get(entity_id(hass, "binary_sensor", f"{PAD_1}_connected")).state
        == "on"
    )
    press = hass.states.get(entity_id(hass, "event", f"{PAD_1}_press"))
    assert press.attributes["event_types"] == [
        "key_1",
        "key_2",
        "key_3",
        "top_knob_left",
        "top_knob_right",
        "top_knob_press",
        "dismissed",
    ]
    assert (
        hass.states.get(entity_id(hass, "image", f"{PAD_1}_picture")).state
        != STATE_UNAVAILABLE
    )
    assert (
        hass.states.get(entity_id(hass, "notify", f"{PAD_1}_alert")).state
        != STATE_UNAVAILABLE
    )

    assert (
        hass.states.get(
            entity_id(hass, "binary_sensor", f"{INSTANCE_1}_mic_muted")
        ).state
        == "off"
    )
    last_press = hass.states.get(entity_id(hass, "sensor", f"{INSTANCE_1}_last_press"))
    assert last_press.state == "2026-11-03T09:12:44+00:00"


async def test_resource_sensors_disabled_by_default(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """CPU, memory and GPU are disabled by default."""
    registry = er.async_get(hass)
    for key in ("cpu", "memory", "gpu"):
        entry = registry.async_get(entity_id(hass, "sensor", f"{INSTANCE_1}_{key}"))
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_state_changes_update_entities(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """Entities follow the next state, and only write when their data changes."""
    profile_id = entity_id(hass, "select", f"{PAD_1}_profile")
    screen_id = entity_id(hass, "light", f"{PAD_1}_screen")
    mic_id = entity_id(hass, "binary_sensor", f"{INSTANCE_1}_mic_muted")
    screen_before = hass.states.get(screen_id)

    pads = app_with_pads.pads
    pads[0] = pad_state(profile={"id": "61ac0e9f7d2b8346", "name": "Games"}, pages=1)
    await app_with_pads.send_state(pads, pc=pc_state(mic_muted=True))
    await hass.async_block_till_done()

    assert hass.states.get(profile_id).state == "Games"
    assert (
        hass.states.get(entity_id(hass, "number", f"{PAD_1}_page")).attributes["max"]
        == 1
    )
    assert hass.states.get(mic_id).state == "on"
    # The screen didn't change, so its state wasn't written again.
    assert hass.states.get(screen_id).last_reported == screen_before.last_reported


async def test_pad_not_listed_is_unavailable(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """A pad missing from the latest state has unavailable entities."""
    await app_with_pads.send_state([pad_state()])
    await hass.async_block_till_done()
    assert (
        hass.states.get(entity_id(hass, "select", f"{PAD_DASH}_profile")).state
        == STATE_UNAVAILABLE
    )
    assert (
        hass.states.get(entity_id(hass, "select", f"{PAD_1}_profile")).state == "Home"
    )


async def test_renew_pads(
    hass: HomeAssistant, hass_ws_client: Any, app_with_pads: FakeApp
) -> None:
    """A pad id that belongs to another PC comes back in `renew_pads`."""
    other = FakeApp(await hass_ws_client(hass), INSTANCE_2, MACHINE_2, "LAPTOP")
    assert (await other.connect())["success"]
    result = await other.send_state(
        [
            pad_state(PAD_1, name="Copied pad"),
            pad_state("aaaaaaaaaaaaaaaa", name="Own pad"),
        ]
    )
    assert result["result"] == {"renew_pads": [PAD_1]}
    await hass.async_block_till_done()

    # The first PC keeps its pad; the second PC gets only its own.
    assert get_device(hass, PAD_1).name == "Desk pad"
    own = get_device(hass, "aaaaaaaaaaaaaaaa")
    assert own.parent_device_id == get_device(hass, INSTANCE_2).id


async def test_invalid_state_is_refused(hass: HomeAssistant, app: FakeApp) -> None:
    """A malformed pad id is refused by the schema."""
    result = await app.send_state([pad_state("NOT-HEX")])
    assert not result["success"]
    assert result["error"]["code"] == "invalid_format"


async def test_mini_monitor_switch_appears_later(
    hass: HomeAssistant, app: FakeApp
) -> None:
    """The switch is added once the pad reports Mini Monitor."""
    await app.send_state([pad_state(mini_monitor=None)])
    await hass.async_block_till_done()
    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id(
            "switch", "stream_dock_ha", f"{PAD_1}_mini_monitor"
        )
        is None
    )

    await app.send_state([pad_state(mini_monitor=True)])
    await hass.async_block_till_done()
    assert (
        hass.states.get(entity_id(hass, "switch", f"{PAD_1}_mini_monitor")).state
        == "on"
    )


async def test_pc_rename_updates_device(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """A new PC name in the state renames its device."""
    app_with_pads.name = "STUDIO"
    await app_with_pads.send_state()
    assert get_device(hass, INSTANCE_1).name == "STUDIO"
