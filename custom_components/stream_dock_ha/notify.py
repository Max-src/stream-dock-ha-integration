"""Alert notify entity for Stream Dock HA pads."""

from __future__ import annotations

from homeassistant.components.notify import NotifyEntity, NotifyEntityFeature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .data import StreamDockConfigEntry
from .entity import StreamDockPadEntity, async_add_pad_entities

PARALLEL_UPDATES = 0


async def async_setup_entry(
    hass: HomeAssistant,
    entry: StreamDockConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the alert notify entities."""
    async_add_pad_entities(
        hass,
        entry,
        async_add_entities,
        lambda hub, pad: [AlertNotify(hub, pad.pad_id, "alert")],
    )


class AlertNotify(StreamDockPadEntity, NotifyEntity):
    """Show a message as an alert over the pad's keys."""

    _attr_supported_features = NotifyEntityFeature.TITLE

    async def async_send_message(self, message: str, title: str | None = None) -> None:
        """Show an alert."""
        fields = {"message": message}
        if title:
            fields["title"] = title
        await self._async_command("show_alert", **fields)
