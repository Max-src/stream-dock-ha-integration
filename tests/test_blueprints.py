"""Tests for the blueprints: they validate, and two of them run."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.components import automation
from homeassistant.components.automation.config import AUTOMATION_BLUEPRINT_SCHEMA
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import parse_yaml
from pytest_homeassistant_custom_component.common import async_mock_service

from .conftest import INSTANCE_1, PAD_1, FakeApp, entity_id, get_device

BLUEPRINTS = (
    Path(__file__).parent.parent / "blueprints" / "automation" / "stream_dock_ha"
)


def _automation(name: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """Return an automation made from a blueprint with inputs."""
    blueprint = Blueprint(
        parse_yaml((BLUEPRINTS / name).read_text(encoding="utf-8")),
        expected_domain=automation.DOMAIN,
        schema=AUTOMATION_BLUEPRINT_SCHEMA,
    )
    assert blueprint.validate() is None
    with_inputs = BlueprintInputs(
        blueprint, {"use_blueprint": {"path": name, "input": inputs}}
    )
    with_inputs.validate()
    return with_inputs.async_substitute()


async def test_all_blueprints_validate(hass: HomeAssistant) -> None:
    """Every blueprint is valid with sample inputs."""
    samples = {
        "knob_dims_light.yaml": {"pad": "abc", "light": "light.desk"},
        "key_toggles_entity.yaml": {"pad": "abc", "target_entity": "switch.fan"},
        "microphone_on_air_light.yaml": {
            "microphone": "binary_sensor.pc_microphone_muted",
            "light": "light.on_air",
        },
        "doorbell_alert.yaml": {
            "doorbell": "binary_sensor.doorbell",
            "pad": "abc",
            "camera": "camera.door",
        },
    }
    assert {path.name for path in BLUEPRINTS.glob("*.yaml")} == set(samples)
    for name, inputs in samples.items():
        assert _automation(name, inputs)["triggers"], name


async def test_knob_and_key_blueprints_run(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """The knob dims and toggles a light; a key toggles an entity."""
    device_id = get_device(hass, PAD_1).id
    turn_on = async_mock_service(hass, "light", "turn_on")
    toggle = async_mock_service(hass, "light", "toggle")
    ha_toggle = async_mock_service(hass, "homeassistant", "toggle")
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                _automation(
                    "knob_dims_light.yaml",
                    {"pad": device_id, "light": "light.desk", "step": 20},
                ),
                _automation(
                    "key_toggles_entity.yaml",
                    {"pad": device_id, "control": "key_2", "target_entity": "fan.desk"},
                ),
            ]
        },
    )

    await app_with_pads.press(control="top_knob_right")
    await app_with_pads.press(control="top_knob_left")
    await app_with_pads.press(control="top_knob_press")
    await app_with_pads.press(control="key_2")
    await hass.async_block_till_done()

    assert [call.data["brightness_step_pct"] for call in turn_on] == [20, -20]
    assert len(toggle) == 1
    assert ha_toggle[0].data["entity_id"] == ["fan.desk"]


async def test_microphone_blueprint_runs(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """The on-air light follows the microphone."""
    turn_on = async_mock_service(hass, "light", "turn_on")
    turn_off = async_mock_service(hass, "light", "turn_off")
    mic = entity_id(hass, "binary_sensor", f"{INSTANCE_1}_mic_muted")
    assert await async_setup_component(
        hass,
        automation.DOMAIN,
        {
            automation.DOMAIN: [
                _automation(
                    "microphone_on_air_light.yaml",
                    {"microphone": mic, "light": "light.on_air"},
                )
            ]
        },
    )
    await app_with_pads.send_state(pc={"mic_muted": True})
    await hass.async_block_till_done()
    assert len(turn_off) == 1
    await app_with_pads.send_state(pc={"mic_muted": False})
    await hass.async_block_till_done()
    assert turn_on[-1].data["rgb_color"] == [255, 0, 0]
