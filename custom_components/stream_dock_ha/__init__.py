"""The Stream Dock HA integration."""

from __future__ import annotations

import logging
from pathlib import Path

from aiohttp import web
from homeassistant.components.frontend import add_extra_js_url
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.http import KEY_HASS, HomeAssistantView
from homeassistant.helpers.storage import Store
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .card import async_list_card, async_unlist_card
from .const import (
    CARD_URL,
    DOMAIN,
    PLATFORMS,
    STORAGE_KEY,
    STORAGE_VERSION,
    URL_BASE,
)
from .data import DATA_KEY, StreamDockConfigEntry, StreamDockData
from .hub import StreamDockHub
from .services import async_setup_services
from .websocket_api import async_register_commands

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

FRONTEND_DIR = Path(__file__).parent / "frontend"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up what the integration needs once per Home Assistant process."""
    integration = await async_get_integration(hass, DOMAIN)
    version = str(integration.version)
    hass.data[DATA_KEY] = StreamDockData(version=version)

    async_register_commands(hass)
    async_setup_services(hass)
    await _async_register_card(hass, version)
    return True


async def _async_register_card(hass: HomeAssistant, version: str) -> None:
    """Serve the dashboard card and load it on every dashboard.

    It's listed in the dashboards' resources, as HACS does, so it loads even
    in a page that was open while Home Assistant restarted. Only when those
    are written in YAML is it put in every page instead. Its address has no
    version, and the browser checks for a newer file at each page load, so a
    new card shows after a refresh, without restarting Home Assistant.
    """
    if not await hass.async_add_executor_job(FRONTEND_DIR.is_dir):
        _LOGGER.warning("The card's folder is missing: %s", FRONTEND_DIR)
        return
    hass.http.register_view(CardView())
    if not await async_list_card(hass, CARD_URL):
        add_extra_js_url(hass, CARD_URL)


def _card_file(path: str) -> Path | None:
    """The card's script at that path, or None. Touches the disk, so not on the loop."""
    root = FRONTEND_DIR.resolve()
    file = (root / path).resolve()
    # Only the folder's own scripts: "../" and other kinds are refused.
    if not file.is_relative_to(root) or file.suffix != ".js" or not file.is_file():
        return None
    return file


class CardView(HomeAssistantView):
    """The card's files, without login: browsers load them as scripts."""

    url = f"{URL_BASE}/{{path:.+}}"
    name = f"{DOMAIN}:card"
    requires_auth = False

    async def get(self, request: web.Request, path: str) -> web.FileResponse:
        """Return a file of the card's folder, to be checked again next time."""
        file = await request.app[KEY_HASS].async_add_executor_job(_card_file, path)
        if file is None:
            raise web.HTTPNotFound
        return web.FileResponse(
            file,
            headers={
                "Cache-Control": "no-cache, stale-if-error=86400",
                "Content-Type": "text/javascript",
            },
        )


async def async_setup_entry(hass: HomeAssistant, entry: StreamDockConfigEntry) -> bool:
    """Set up the hub from a config entry."""
    hub = StreamDockHub(hass, entry, hass.data[DATA_KEY])
    await hub.async_setup()
    entry.runtime_data = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: StreamDockConfigEntry) -> bool:
    """Unload a config entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_unload()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: StreamDockConfigEntry) -> None:
    """Delete what was stored when the integration is removed."""
    await Store[dict](hass, STORAGE_VERSION, STORAGE_KEY).async_remove()
    await async_unlist_card(hass)


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: StreamDockConfigEntry, device: dr.DeviceEntry
) -> bool:
    """Allow removing a pad or PC that isn't connected."""
    return entry.runtime_data.async_remove_device(device)
