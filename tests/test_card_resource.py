"""The card is kept in the dashboards' resources, so it loads after a restart."""

from __future__ import annotations

from homeassistant.components.frontend import DATA_EXTRA_MODULE_URL
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stream_dock_ha.const import DOMAIN

URL = "/stream_dock_ha/stream-dock-card.js"


async def _setup(hass: HomeAssistant, lovelace: dict | None = None) -> MockConfigEntry:
    assert await async_setup_component(hass, "lovelace", lovelace or {})
    entry = MockConfigEntry(domain=DOMAIN, title="Stream Dock HA", data={}, options={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _cards(hass: HomeAssistant) -> list[dict]:
    items = hass.data[LOVELACE_DATA].resources.async_items()
    return [item for item in items if "stream-dock-card" in item["url"]]


async def test_card_is_listed_once(hass: HomeAssistant) -> None:
    """Setting up lists the card as a module, with the same URL as the extra module."""
    await _setup(hass)
    assert [(item["type"], item["url"]) for item in _cards(hass)] == [("module", URL)]


async def test_old_versions_are_brought_up_to_date(hass: HomeAssistant) -> None:
    """An older version is updated in place, and copies are removed."""
    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data[LOVELACE_DATA].resources
    await resources.async_get_info()
    await resources.async_create_item(
        {"res_type": "js", "url": "/stream_dock_ha/stream-dock-card.js?v=0.0.1"}
    )
    await resources.async_create_item(
        {"res_type": "module", "url": "/stream_dock_ha/stream-dock-card.js"}
    )
    await resources.async_create_item(
        {"res_type": "module", "url": "/local/other-card.js"}
    )
    entry = MockConfigEntry(domain=DOMAIN, title="Stream Dock HA", data={}, options={})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert [(item["type"], item["url"]) for item in _cards(hass)] == [("module", URL)]
    others = [
        item["url"] for item in resources.async_items() if "other-card" in item["url"]
    ]
    assert others == ["/local/other-card.js"]


async def test_removing_the_integration_unlists_the_card(hass: HomeAssistant) -> None:
    """Removing the integration takes the card out of the resources."""
    entry = await _setup(hass)
    assert await hass.config_entries.async_remove(entry.entry_id)
    await hass.async_block_till_done()
    assert _cards(hass) == []


async def test_yaml_resources_are_left_alone(hass: HomeAssistant) -> None:
    """Resources written in YAML aren't touched; every page loads the card instead."""
    await _setup(hass, {"lovelace": {"resource_mode": "yaml", "resources": []}})
    assert _cards(hass) == []
    assert URL in hass.data[DATA_EXTRA_MODULE_URL].urls


async def test_a_listed_card_isnt_also_put_in_every_page(hass: HomeAssistant) -> None:
    """With the card in the resources, pages don't load it a second way."""
    await _setup(hass)
    assert URL not in hass.data[DATA_EXTRA_MODULE_URL].urls
