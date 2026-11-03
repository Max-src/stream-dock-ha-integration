"""Tests for setup: the card's file, and actions matching services.yaml."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry
import yaml

from custom_components.stream_dock_ha.const import DOMAIN
from custom_components.stream_dock_ha.services import ACTIONS

PACKAGE = Path(__file__).parent.parent / "custom_components" / DOMAIN


async def test_card_is_served(
    hass: HomeAssistant, hass_client: Any, setup_entry: MockConfigEntry
) -> None:
    """The card is served and loaded on dashboards as a module."""
    assert (
        "/stream_dock_ha/stream-dock-card.js?v=0.1.0"
        in hass.data[DATA_EXTRA_MODULE_URL].urls
    )
    client = await hass_client()
    response = await client.get("/stream_dock_ha/stream-dock-card.js")
    assert response.status == 200


async def test_services_yaml_matches_actions(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """Every action is registered and described with the fields it takes."""
    described = yaml.safe_load((PACKAGE / "services.yaml").read_text(encoding="utf-8"))
    assert set(described) == set(ACTIONS)
    for name, spec in ACTIONS.items():
        assert hass.services.has_service(DOMAIN, name)
        fields = {str(key) for key in spec.fields} | {"device_id"}
        assert set(described[name]["fields"]) == fields, name
