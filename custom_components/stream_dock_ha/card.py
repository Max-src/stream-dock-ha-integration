"""Keeps the dashboard card listed in the dashboards' resources.

`add_extra_js_url` only reaches pages rendered after this integration was set
up: a browser that reconnects while Home Assistant restarts keeps a page
without the card, and dashboards then say "Custom element doesn't exist:
stream-dock-card" until a full reload. Dashboards fetch their resources
themselves, so the card is listed there, as HACS does; `add_extra_js_url` is
only for resources written in YAML. An older address with `?v=` is updated.
"""

from __future__ import annotations

import logging

from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant

from .const import CARD_URL

_LOGGER = logging.getLogger(__name__)


def _resources(hass: HomeAssistant):
    """The dashboards' resource list, when Home Assistant keeps it in storage."""
    lovelace = hass.data.get(LOVELACE_DATA)
    if lovelace is None or lovelace.resource_mode != "storage":
        # Resources written in YAML are the person's own to edit.
        return None
    return lovelace.resources


def _ours(items: list[dict]) -> list[dict]:
    return [item for item in items if item.get("url", "").split("?")[0] == CARD_URL]


async def async_list_card(hass: HomeAssistant, url: str) -> bool:
    """Add the card to the resources, or bring its address up to date.

    Returns whether it's listed; not when resources are written in YAML.
    """
    try:
        resources = _resources(hass)
    except Exception:  # Lovelace's insides changed: the page loads it
        _LOGGER.debug("Dashboard resources aren't available", exc_info=True)
        return False
    if resources is None:
        _LOGGER.debug("Dashboard resources aren't in storage; not listing the card")
        return False
    await resources.async_get_info()
    first, *extra = _ours(resources.async_items()) or [None]
    if first is None:
        await resources.async_create_item({"res_type": "module", "url": url})
        _LOGGER.debug("Listed the card in the dashboard resources: %s", url)
    elif first.get("url") != url or first.get("type") != "module":
        await resources.async_update_item(
            first["id"], {"res_type": "module", "url": url}
        )
        _LOGGER.debug("Updated the card's dashboard resource to %s", url)
    for item in extra:
        await resources.async_delete_item(item["id"])
    return True


async def async_unlist_card(hass: HomeAssistant) -> None:
    """Take the card out of the resources, when the integration is removed."""
    resources = _resources(hass)
    if resources is None:
        return
    await resources.async_get_info()
    for item in _ours(resources.async_items()):
        await resources.async_delete_item(item["id"])
