"""Tests for persistence, several PCs, device removal and diagnostics."""

from __future__ import annotations

from typing import Any

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)

from custom_components.stream_dock_ha.const import DOMAIN

from .conftest import (
    INSTANCE_1,
    INSTANCE_2,
    MACHINE_1,
    MACHINE_2,
    PAD_1,
    PAD_2,
    PAD_DASH,
    FakeApp,
    WsPeer,
    entity_id,
    get_device,
    pad_state,
)


async def test_persists_across_reload(
    hass: HomeAssistant,
    hass_ws_client: Any,
    hass_storage: dict[str, Any],
    app_with_pads: FakeApp,
    setup_entry: MockConfigEntry,
) -> None:
    """After a reload, entities exist and are unavailable until the PC is back."""
    card = WsPeer(await hass_ws_client(hass))
    watch_id = await card.send({"type": "stream_dock_ha/watch", "pad_id": PAD_1})
    assert (await card.result(watch_id))["success"]
    await card.event(watch_id, "pad")

    assert await hass.config_entries.async_reload(setup_entry.entry_id)
    await hass.async_block_till_done()

    stored = hass_storage[DOMAIN]["data"]
    assert stored["pcs"][INSTANCE_1] == {
        "instance_id": INSTANCE_1,
        "machine": MACHINE_1,
        "name": "DESKTOP-MAX",
    }
    assert stored["pads"][PAD_1] == {"instance_id": INSTANCE_1, "state": pad_state()}

    profile = entity_id(hass, "select", f"{PAD_1}_profile")
    online = entity_id(hass, "binary_sensor", f"{INSTANCE_1}_online")
    assert hass.states.get(profile).state == STATE_UNAVAILABLE
    assert (
        hass.states.get(entity_id(hass, "sensor", f"{INSTANCE_1}_last_press")).state
        == STATE_UNAVAILABLE
    )
    assert hass.states.get(online).state == "off"

    # The card kept its subscription and saw the pad go offline.
    offline = await card.event(watch_id, "pad")
    assert offline["online"] is False

    # The old socket must connect again; then everything comes back.
    assert (await app_with_pads.send_state())["error"]["code"] == "not_connected"
    result = await app_with_pads.connect()
    assert result["success"]
    assert await app_with_pads.next_event("watch") == {
        "kind": "watch",
        "pads": {PAD_1: 2},
    }
    await app_with_pads.send_state()
    await hass.async_block_till_done()
    assert hass.states.get(profile).state == "Home"
    assert hass.states.get(online).state == "on"
    while (
        not (event := await card.event(watch_id, "pad"))["listed"]
        or not event["online"]
    ):
        pass
    assert event["pad"] == pad_state()

    # The machine binding survived the reload.
    copy = FakeApp(await hass_ws_client(hass), machine=MACHINE_2)
    assert (await copy.connect())["error"]["code"] == "renew_instance"


async def test_loads_from_storage(
    hass: HomeAssistant, hass_storage: dict[str, Any], config_entry: MockConfigEntry
) -> None:
    """A PC that's off at start still has its devices and entities."""
    hass_storage[DOMAIN] = {
        "version": 1,
        "minor_version": 1,
        "key": DOMAIN,
        "data": {
            "pcs": {
                INSTANCE_1: {
                    "instance_id": INSTANCE_1,
                    "machine": MACHINE_1,
                    "name": "DESKTOP-MAX",
                }
            },
            "pads": {PAD_1: {"instance_id": INSTANCE_1, "state": pad_state()}},
        },
    }
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert get_device(hass, PAD_1).parent_device_id == get_device(hass, INSTANCE_1).id
    assert (
        hass.states.get(entity_id(hass, "light", f"{PAD_1}_screen")).state
        == STATE_UNAVAILABLE
    )
    assert (
        hass.states.get(entity_id(hass, "binary_sensor", f"{INSTANCE_1}_online")).state
        == "off"
    )


async def test_a_pad_device_from_before_becomes_a_child_of_its_pc(
    hass: HomeAssistant, hass_storage: dict[str, Any], config_entry: MockConfigEntry
) -> None:
    """A pad that was a device of its own keeps its id, now under its PC."""
    hass_storage[DOMAIN] = {
        "version": 1,
        "minor_version": 1,
        "key": DOMAIN,
        "data": {
            "pcs": {
                INSTANCE_1: {
                    "instance_id": INSTANCE_1,
                    "machine": MACHINE_1,
                    "name": "DESKTOP-MAX",
                }
            },
            "pads": {PAD_1: {"instance_id": INSTANCE_1, "state": pad_state()}},
        },
    }
    config_entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    pc = registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, INSTANCE_1)},
        name="DESKTOP-MAX",
    )
    old = registry.async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={(DOMAIN, PAD_1)},
        manufacturer="Mirabox",
        name="Desk pad",
        via_device_id=pc.id,
    )
    # As after a restart: the devices are known, nothing has set them up yet.
    registry._live_device_ids.clear()
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    pad = get_device(hass, PAD_1)
    assert (pad.id, pad.parent_device_id) == (old.id, pc.id)
    assert registry.async_get(old.id) is pad
    assert entity_id(hass, "light", f"{PAD_1}_screen") is not None


async def test_two_pcs(
    hass: HomeAssistant, hass_ws_client: Any, app_with_pads: FakeApp
) -> None:
    """Two PCs at once, each with its own pads, commands and watch map."""
    laptop = FakeApp(await hass_ws_client(hass), INSTANCE_2, MACHINE_2, "LAPTOP")
    assert (await laptop.connect())["success"]
    assert await laptop.next_event("watch") == {"kind": "watch", "pads": {}}
    await laptop.send_state(
        [pad_state(PAD_2, kind="akp03e", model="AKP03E", name="Small pad")]
    )
    await hass.async_block_till_done()

    assert get_device(hass, PAD_2).parent_device_id == get_device(hass, INSTANCE_2).id

    # A card on the laptop's pad changes only the laptop's watch.
    card = WsPeer(await hass_ws_client(hass))
    sub = await card.send({"type": "stream_dock_ha/watch", "pad_id": PAD_2, "scale": 1})
    assert (await card.result(sub))["success"]
    assert await laptop.next_event("watch") == {"kind": "watch", "pads": {PAD_2: 1}}
    await app_with_pads.drain()
    assert not app_with_pads.queued_events(app_with_pads.sub_id, "watch")

    # A command for the laptop's pad goes only to the laptop.
    task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "next_profile",
            {"device_id": get_device(hass, PAD_2).id},
            blocking=True,
        )
    )
    event = await laptop.next_event("command")
    assert event["data"]["pad"] == PAD_2
    await laptop.reply(event["request_id"])
    await task
    await app_with_pads.drain()
    assert not app_with_pads.queued_events(app_with_pads.sub_id, "command")

    # A reply from the wrong PC doesn't resolve another PC's request.
    task = hass.async_create_task(
        hass.services.async_call(
            DOMAIN,
            "next_profile",
            {"device_id": get_device(hass, PAD_2).id},
            blocking=True,
        )
    )
    event = await laptop.next_event("command")
    await app_with_pads.reply(event["request_id"])
    assert not task.done()
    await laptop.reply(event["request_id"])
    await task

    # One PC leaving doesn't affect the other.
    await laptop.client.close()
    await hass.async_block_till_done()
    assert (
        hass.states.get(entity_id(hass, "select", f"{PAD_2}_profile")).state
        == STATE_UNAVAILABLE
    )
    assert (
        hass.states.get(entity_id(hass, "select", f"{PAD_1}_profile")).state == "Home"
    )


async def test_device_removal(
    hass: HomeAssistant,
    hass_ws_client: Any,
    app_with_pads: FakeApp,
    setup_entry: MockConfigEntry,
) -> None:
    """Connected pads and PCs can't be removed; others can."""
    client = await hass_ws_client(hass)

    response = await client.remove_device(get_device(hass, PAD_1).id)
    assert not response["success"]
    response = await client.remove_device(get_device(hass, INSTANCE_1).id)
    assert not response["success"]

    # A physical pad left out of the state keeps its device until it's
    # removed by hand. (A virtual pad's goes by itself: test_state.py.)
    await app_with_pads.send_state(
        [pad_state(PAD_DASH, kind="dashboard", model="Dashboard", name="Tablet")]
    )
    response = await client.remove_device(get_device(hass, PAD_1).id)
    assert response["success"]
    assert get_device(hass, PAD_1) is None
    assert PAD_1 not in setup_entry.runtime_data.pads

    # An offline PC can go, with its pads.
    await app_with_pads.client.close()
    await hass.async_block_till_done()
    response = await client.remove_device(get_device(hass, INSTANCE_1).id)
    assert response["success"]
    assert get_device(hass, INSTANCE_1) is None
    assert get_device(hass, PAD_DASH) is None
    assert setup_entry.runtime_data.pcs == {}


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: Any,
    app_with_pads: FakeApp,
    setup_entry: MockConfigEntry,
) -> None:
    """Diagnostics hold the hub's data but no pictures."""
    await app_with_pads.call(
        {
            "type": "stream_dock_ha/pictures",
            "pad_id": PAD_1,
            "scale": 1,
            "complete": True,
            "pictures": {"key_1": {"hash": "x", "data": "SECRETPICTURE"}},
        }
    )
    result = await get_diagnostics_for_config_entry(hass, hass_client, setup_entry)
    assert result["pcs"][0]["instance_id"] == INSTANCE_1
    assert result["pcs"][0]["online"] is True
    assert result["pads"][0]["pictures_cached"] == {"scale": 1, "count": 4}
    assert "SECRETPICTURE" not in str(result)
    # Names people chose stay out of what gets pasted into issues.
    assert result["pcs"][0]["name"] == "**REDACTED**"
    assert result["pcs"][0]["user"] == "**REDACTED**"
    state = result["pads"][0]["state"]
    assert state["name"] == "**REDACTED**"
    control = state["layout"]["controls"][0]["name"]
    assert control.startswith(("key_", "button_", "band_"))
