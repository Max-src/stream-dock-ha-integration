"""Picture of Stream Dock HA pads."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Hashable
import logging

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .data import StreamDockConfigEntry
from .entity import StreamDockPadEntity, async_add_pad_entities
from .errors import StreamDockError
from .hub import StreamDockHub

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StreamDockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the pad pictures."""
    async_add_pad_entities(
        hass,
        entry,
        async_add_entities,
        lambda hub, pad: [PadPicture(hub, pad.pad_id)],
    )


class PadPicture(StreamDockPadEntity, ImageEntity):
    """A picture of the whole pad, asked from the app when shown."""

    _attr_content_type = "image/jpeg"

    def __init__(self, hub: StreamDockHub, pad_id: str) -> None:
        """Initialize the picture."""
        StreamDockPadEntity.__init__(self, hub, pad_id, "picture")
        ImageEntity.__init__(self, hub.hass)
        self._look: str | None = self.pad_state.get("look")
        self._image: tuple[str | None, bytes] | None = None
        if self._look is not None:
            self._attr_image_last_updated = dt_util.utcnow()

    def _state_key(self) -> Hashable:
        return (self.available, self.pad_state.get("look"))

    @callback
    def _async_changed(self) -> None:
        look = self.pad_state.get("look")
        if look != self._look:
            self._look = look
            self._attr_image_last_updated = dt_util.utcnow()
        super()._async_changed()

    async def async_image(self) -> bytes | None:
        """Return the pad's picture, fetched with `snapshot` once per look."""
        look = self._look
        if self._image is not None and self._image[0] == look:
            return self._image[1]
        if not self.available:
            return None
        try:
            result = await self.hub.async_command(self.pad_id, "snapshot", {"scale": 1})
            data = base64.b64decode(result["data"], validate=True)
        except (StreamDockError, KeyError, TypeError, binascii.Error) as err:
            _LOGGER.debug("No picture of %s: %s", self.pad_id, err)
            return None
        self._image = (look, data)
        return data
