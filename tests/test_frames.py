"""Mini Monitor frames: from the app, on any of its connections, to the cards."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .conftest import INSTANCE_1, PAD_1, FakeApp, WsPeer

TILES = [{"name": "key_1", "x": 0, "y": 0, "w": 85, "h": 85}]


def frame(app: FakeApp, **changes: Any) -> dict[str, Any]:
    msg = {
        "type": "stream_dock_ha/frame",
        "instance_id": INSTANCE_1,
        "key": app.frame_key,
        "pad_id": PAD_1,
        "width": 640,
        "height": 340,
        "data": "AAAA",
        "tiles": TILES,
    }
    msg.update(changes)
    return msg


async def test_a_frame_reaches_the_cards_from_another_connection(
    hass: HomeAssistant, hass_ws_client: Any, app_with_pads: FakeApp
) -> None:
    """Frames sent over a second connection, as over the local address, arrive."""
    app = app_with_pads
    card = WsPeer(await hass_ws_client(hass))
    sub = await card.send({"type": "stream_dock_ha/watch", "pad_id": PAD_1})
    assert (await card.result(sub))["success"]
    await card.event(sub, "pad")
    side = WsPeer(await hass_ws_client(hass))
    result = await side.call(frame(app))
    assert result["success"], result
    assert await card.event(sub, "frame") == {
        "kind": "frame",
        "width": 640,
        "height": 340,
        "data": "AAAA",
        "tiles": TILES,
        "seamless": False,
    }
    # One picture across the gaps, when the app asks for it.
    assert (await side.call(frame(app, seamless=True)))["success"]
    assert (await card.event(sub, "frame"))["seamless"] is True


async def test_a_frame_needs_the_pcs_key_and_its_own_pad(
    hass: HomeAssistant, hass_ws_client: Any, app_with_pads: FakeApp
) -> None:
    """Another key, or a pad that isn't the PC's, is refused."""
    app = app_with_pads
    side = WsPeer(await hass_ws_client(hass))
    result = await side.call(frame(app, key="0" * 32))
    assert result["error"]["code"] == "not_connected"
    result = await side.call(frame(app, pad_id="00000000000000ff"))
    assert result["error"]["code"] == "not_found"


async def test_with_no_card_watching_a_frame_goes_nowhere(
    hass: HomeAssistant, app_with_pads: FakeApp
) -> None:
    """A frame nobody watches is accepted and dropped."""
    result = await app_with_pads.call(frame(app_with_pads))
    assert result["success"]


async def test_a_frame_after_the_pc_left_is_refused(
    hass: HomeAssistant, hass_ws_client: Any, app_with_pads: FakeApp
) -> None:
    """The key ends with the PC's connection."""
    app = app_with_pads
    key = app.frame_key
    await app.client.close()
    await hass.async_block_till_done()
    side = WsPeer(await hass_ws_client(hass))
    result = await side.call(frame(app, key=key))
    assert result["error"]["code"] == "not_connected"
