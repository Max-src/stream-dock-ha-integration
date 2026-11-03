"""Tests for presses: event entity, bus event and device trigger."""

from __future__ import annotations

from homeassistant.components import automation
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    async_capture_events,
    async_get_device_automations,
    async_mock_service,
)

from custom_components.stream_dock_ha.const import DOMAIN, EVENT_PRESSED

from .conftest import PAD_1, FakeApp, entity_id, get_device


async def test_press_fires_event_entity_and_bus_event(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """A press updates the event entity and fires `stream_dock_ha_event`."""
    events = async_capture_events(hass, EVENT_PRESSED)
    press_id = entity_id(hass, "event", f"{PAD_1}_press")

    assert (await app_with_pads.press(control="key_3"))["success"]
    await hass.async_block_till_done()

    assert events[-1].data == {
        "device_id": get_device(hass, PAD_1).id,
        "pad_id": PAD_1,
        "control": "key_3",
        "profile": "Home",
        "page": 1,
        "title": "Desk lamp",
        "source": "pad",
        "dismissed": False,
    }
    state = hass.states.get(press_id)
    assert state.attributes["event_type"] == "key_3"
    assert state.attributes["profile"] == "Home"
    assert state.attributes["page"] == 1
    assert state.attributes["title"] == "Desk lamp"
    assert state.attributes["source"] == "pad"

    assert (await app_with_pads.press(control="key_1", dismissed=True))["success"]
    await hass.async_block_till_done()
    assert events[-1].data["dismissed"] is True
    assert hass.states.get(press_id).attributes["event_type"] == "dismissed"


async def test_press_for_unknown_pad(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """A press for a pad the PC doesn't own is refused."""
    result = await app_with_pads.press(pad_id="0000000000000000")
    assert result["error"]["code"] == "not_found"


async def test_device_trigger(hass: HomeAssistant, app_with_pads: FakeApp) -> None:
    """Device triggers list each pressable control and fire on its presses."""
    device_id = get_device(hass, PAD_1).id
    triggers = await async_get_device_automations(
        hass, DeviceAutomationType.TRIGGER, device_id
    )
    ours = [t for t in triggers if t["domain"] == DOMAIN]
    assert {t["subtype"] for t in ours} == {
        "key_1",
        "key_2",
        "key_3",
        "top_knob_left",
        "top_knob_right",
        "top_knob_press",
    }
    assert all(t["type"] == "pressed" for t in ours)

    calls = async_mock_service(hass, "test", "automation")
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                {
                    "triggers": [
                        {
                            "trigger": "device",
                            "domain": DOMAIN,
                            "device_id": device_id,
                            "type": "pressed",
                            "subtype": "top_knob_press",
                        }
                    ],
                    "actions": [
                        {
                            "action": "test.automation",
                            "data": {"title": "{{ trigger.event.data.title }}"},
                        }
                    ],
                }
            ]
        },
    )

    await app_with_pads.press(control="key_1")
    await app_with_pads.press(control="top_knob_press", title="Knob")
    await app_with_pads.press(control="top_knob_press", dismissed=True)
    await hass.async_block_till_done()
    assert len(calls) == 1
    assert calls[0].data == {"title": "Knob"}
