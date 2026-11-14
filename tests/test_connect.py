"""Tests for `stream_dock_ha/connect` and the duplicate-id rules."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from .conftest import INSTANCE_1, MACHINE_2, PAD_1, FakeApp, entity_id, get_device


async def test_connect_success(
    hass: HomeAssistant, hass_ws_client: Any, setup_entry: MockConfigEntry
) -> None:
    """A PC connects, gets the protocol and an empty watch, and gets a device."""
    app = FakeApp(await hass_ws_client(hass))
    result = await app.connect()
    assert result["success"]
    assert result["result"]["protocol"] == 1
    assert result["result"]["integration_version"] == "0.1.12"
    # A key for its Mini Monitor frames, and the local address if known.
    assert len(result["result"]["frame_key"]) == 32
    assert "local_url" in result["result"]
    assert await app.next_event() == {"kind": "watch", "pads": {}}

    device = get_device(hass, INSTANCE_1)
    assert device is not None
    assert device.name == "DESKTOP-MAX"
    assert device.manufacturer == "Stream Dock HA"
    assert device.sw_version == "1.1.0"
    await hass.async_block_till_done()
    assert (
        hass.states.get(entity_id(hass, "binary_sensor", f"{INSTANCE_1}_online")).state
        == "on"
    )


async def test_connect_protocol_mismatch(
    hass: HomeAssistant, hass_ws_client: Any, setup_entry: MockConfigEntry
) -> None:
    """Another protocol number is refused."""
    app = FakeApp(await hass_ws_client(hass))
    result = await app.connect(protocol=2)
    assert not result["success"]
    assert result["error"]["code"] == "protocol_mismatch"
    assert "1" in result["error"]["message"]


async def test_connect_not_set_up(
    hass: HomeAssistant, hass_ws_client: Any, config_entry: MockConfigEntry
) -> None:
    """With no loaded config entry, the app and the card get `not_set_up`."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()

    app = FakeApp(await hass_ws_client(hass))
    result = await app.connect()
    assert result["error"]["code"] == "not_set_up"
    for msg in (
        {"type": "stream_dock_ha/pads"},
        {"type": "stream_dock_ha/watch", "pad_id": PAD_1},
        {"type": "stream_dock_ha/press", "pad_id": PAD_1, "control": "key_1"},
    ):
        result = await app.call(msg)
        assert result["error"]["code"] == "not_set_up", msg


async def test_renew_instance_for_another_machine(
    hass: HomeAssistant, hass_ws_client: Any, app: FakeApp
) -> None:
    """A known instance id from another machine must be renewed."""
    copy = FakeApp(await hass_ws_client(hass), machine=MACHINE_2)
    result = await copy.connect()
    assert result["error"]["code"] == "renew_instance"

    # Also once the first PC is gone: the id stays tied to its machine.
    await app.client.close()
    await hass.async_block_till_done()
    result = await copy.connect()
    assert result["error"]["code"] == "renew_instance"


async def test_same_machine_replaces_old_connection(
    hass: HomeAssistant, hass_ws_client: Any, app_with_pads: FakeApp
) -> None:
    """The same PC on a new socket replaces the old connection."""
    old = app_with_pads
    new = FakeApp(await hass_ws_client(hass))
    assert (await new.connect())["success"]
    assert await new.next_event("watch") == {"kind": "watch", "pads": {}}

    online = entity_id(hass, "binary_sensor", f"{INSTANCE_1}_online")
    assert hass.states.get(online).state == "on"

    # The old socket is no longer the PC.
    result = await old.send_state()
    assert result["error"]["code"] == "not_connected"

    # Closing the old socket doesn't take the PC offline.
    await old.client.close()
    await hass.async_block_till_done()
    assert hass.states.get(online).state == "on"

    assert (await new.send_state([*old.pads]))["success"]
    await new.client.close()
    await hass.async_block_till_done()
    assert hass.states.get(online).state == "off"


async def test_messages_before_connect(
    hass: HomeAssistant, hass_ws_client: Any, setup_entry: MockConfigEntry
) -> None:
    """App messages on a socket that hasn't connected get `not_connected`."""
    app = FakeApp(await hass_ws_client(hass))
    result = await app.send_state([])
    assert result["error"]["code"] == "not_connected"
    result = await app.press()
    assert result["error"]["code"] == "not_connected"
