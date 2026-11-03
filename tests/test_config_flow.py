"""Tests for the config and options flows."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.stream_dock_ha.const import CONF_ADMIN_ONLY_PRESS, DOMAIN


async def test_user_flow(hass: HomeAssistant) -> None:
    """The flow asks nothing and makes one entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Stream Dock HA"
    assert result["data"] == {}


async def test_single_instance(
    hass: HomeAssistant, setup_entry: MockConfigEntry
) -> None:
    """A second entry is refused."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow(hass: HomeAssistant, setup_entry: MockConfigEntry) -> None:
    """The option defaults to off and can be turned on."""
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    schema = result["data_schema"].schema
    key = next(k for k in schema if k == CONF_ADMIN_ONLY_PRESS)
    assert key.default() is False
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_ADMIN_ONLY_PRESS: True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert setup_entry.options == {CONF_ADMIN_ONLY_PRESS: True}
