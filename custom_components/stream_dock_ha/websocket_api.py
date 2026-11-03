"""WebSocket commands for the app (protocol section 3) and the card (section 5)."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components import websocket_api
from homeassistant.components.websocket_api import ActiveConnection
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.network import NoURLAvailableError, get_url
import probatio

from .const import CONF_ADMIN_ONLY_PRESS, DEFAULT_WATCH_SCALE, PROTOCOL
from .data import DATA_KEY, async_get_hub
from .errors import NoAnswerError, PadNotFoundError, StreamDockError
from .hub import NotConnectedError, RenewInstanceError, StreamDockHub

_LOGGER = logging.getLogger(__name__)

ERR_NOT_SET_UP = "not_set_up"
ERR_NOT_CONNECTED = "not_connected"
ERR_PROTOCOL_MISMATCH = "protocol_mismatch"
ERR_RENEW_INSTANCE = "renew_instance"
ERR_FAILED = "failed"

HEX_ID = probatio.All(str, probatio.Match(r"^[0-9a-f]{16}$"))
SCALE = probatio.In([1, 2, 3])
OPTIONAL_STR = probatio.Any(None, str)
OPTIONAL_NUMBER = probatio.Any(None, int, float)

PC_SCHEMA = probatio.Schema(
    {
        probatio.Optional("mic_muted"): probatio.Any(None, bool),
        probatio.Optional("cpu"): OPTIONAL_NUMBER,
        probatio.Optional("memory"): OPTIONAL_NUMBER,
        probatio.Optional("gpu"): OPTIONAL_NUMBER,
        probatio.Optional("last_press"): OPTIONAL_STR,
    },
    extra=probatio.ALLOW_EXTRA,
)

CONTROL_SCHEMA = probatio.Schema(
    {
        probatio.Required("name"): str,
        probatio.Required("type"): str,
        probatio.Required("screen"): bool,
        probatio.Required("press"): bool,
    },
    extra=probatio.ALLOW_EXTRA,
)

LAYOUT_SCHEMA = probatio.Schema(
    {
        probatio.Required("version"): str,
        probatio.Required("controls"): [CONTROL_SCHEMA],
    },
    extra=probatio.ALLOW_EXTRA,
)

PROFILE_SCHEMA = probatio.Schema(
    {probatio.Required("id"): str, probatio.Required("name"): str},
    extra=probatio.ALLOW_EXTRA,
)

PAD_SCHEMA = probatio.Schema(
    {
        probatio.Required("id"): HEX_ID,
        probatio.Required("kind"): str,
        probatio.Required("model"): str,
        probatio.Required("name"): str,
        probatio.Required("connected"): bool,
        probatio.Required("screen_on"): bool,
        probatio.Required("brightness"): probatio.All(
            int, probatio.Range(min=0, max=100)
        ),
        probatio.Required("mini_monitor"): probatio.Any(None, bool),
        probatio.Required("profile"): probatio.Any(None, PROFILE_SCHEMA),
        probatio.Required("profiles"): [PROFILE_SCHEMA],
        probatio.Required("page"): int,
        probatio.Required("pages"): int,
        probatio.Required("look"): str,
        probatio.Required("alert"): bool,
        probatio.Required("layout"): LAYOUT_SCHEMA,
    },
    extra=probatio.ALLOW_EXTRA,
)

PICTURE_SCHEMA = probatio.Any(
    None,
    probatio.Schema(
        {probatio.Required("hash"): str, probatio.Required("data"): str},
        extra=probatio.ALLOW_EXTRA,
    ),
)


@callback
def async_register_commands(hass: HomeAssistant) -> None:
    """Register the WebSocket commands."""
    for handler in (
        ws_connect,
        ws_state,
        ws_pressed,
        ws_pictures,
        ws_frame,
        ws_reply,
        ws_pads,
        ws_watch,
        ws_press,
    ):
        websocket_api.async_register_command(hass, handler)


def _hub_or_error(connection: ActiveConnection, msg_id: int) -> StreamDockHub | None:
    """Return the hub, or send `not_set_up` and return None."""
    if (hub := async_get_hub(connection.hass)) is None:
        connection.send_error(
            msg_id, ERR_NOT_SET_UP, "Add the Stream Dock HA integration first"
        )
    return hub


def _app_hub_or_error(
    connection: ActiveConnection, msg_id: int
) -> StreamDockHub | None:
    """Return the hub for an app command other than `connect`.

    Without a loaded hub (none set up, or a reload in progress) there can't be
    a live `connect`, so the app gets `not_connected` and connects again.
    """
    if (hub := async_get_hub(connection.hass)) is None:
        connection.send_error(msg_id, ERR_NOT_CONNECTED, "Send connect first")
    return hub


def _is_admin_or_error(connection: ActiveConnection, msg_id: int) -> bool:
    """Return whether the user is an administrator, or send `unauthorized`.

    The app's commands need an administrator's token (protocol section 7).
    """
    if connection.user is not None and connection.user.is_admin:
        return True
    connection.send_error(
        msg_id,
        websocket_api.ERR_UNAUTHORIZED,
        "The integration needs a token from an administrator user",
    )
    return False


def _send_app_error(connection: ActiveConnection, msg_id: int, err: Exception) -> None:
    if isinstance(err, NotConnectedError):
        connection.send_error(msg_id, ERR_NOT_CONNECTED, "Send connect first")
    elif isinstance(err, StreamDockError):
        connection.send_error(msg_id, err.code, err.text)
    else:  # pragma: no cover - defensive
        raise err


# ----------------------------------------------------------------------
# The app's commands


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "stream_dock_ha/connect",
        probatio.Required("protocol"): int,
        probatio.Required("app_version"): str,
        probatio.Required("instance_id"): HEX_ID,
        probatio.Required("machine"): HEX_ID,
        probatio.Required("name"): str,
        probatio.Required("control"): bool,
    }
)
@callback
def ws_connect(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Link this connection to a PC (a subscription)."""
    _LOGGER.debug("connect: %s", msg)
    if not _is_admin_or_error(connection, msg["id"]):
        return
    if msg["protocol"] != PROTOCOL:
        connection.send_error(
            msg["id"],
            ERR_PROTOCOL_MISMATCH,
            f"The integration speaks protocol {PROTOCOL}",
        )
        return
    if (hub := _hub_or_error(connection, msg["id"])) is None:
        return
    try:
        pc = hub.async_connect(connection, msg["id"], msg)
    except RenewInstanceError:
        connection.send_error(
            msg["id"], ERR_RENEW_INSTANCE, "This instance id belongs to another PC"
        )
        return
    assert pc.link is not None
    connection.send_result(
        msg["id"],
        {
            "protocol": PROTOCOL,
            "integration_version": hub.version,
            "local_url": _local_url(hass),
            "frame_key": pc.link.frame_key,
        },
    )
    hub.async_update_watch(pc.instance_id)


def _local_url(hass: HomeAssistant) -> str | None:
    """Home Assistant's address on the home network, if it knows one.

    The app sends Mini Monitor frames there when it reached Home Assistant
    some other way, so they don't go out to the internet and back.
    """
    try:
        return get_url(
            hass, allow_internal=True, allow_external=False, allow_cloud=False
        )
    except NoURLAvailableError:
        return None


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "stream_dock_ha/state",
        probatio.Required("name"): str,
        probatio.Required("control"): bool,
        probatio.Required("pc"): PC_SCHEMA,
        probatio.Required("pads"): [PAD_SCHEMA],
    }
)
@callback
def ws_state(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Take the app's full state."""
    _LOGGER.debug("state: %s", msg)
    if not _is_admin_or_error(connection, msg["id"]):
        return
    if (hub := _app_hub_or_error(connection, msg["id"])) is None:
        return
    try:
        renew = hub.async_state(connection, msg)
    except NotConnectedError as err:
        _send_app_error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"], {"renew_pads": renew})


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "stream_dock_ha/pressed",
        probatio.Required("pad_id"): HEX_ID,
        probatio.Required("control"): str,
        probatio.Optional("profile"): OPTIONAL_STR,
        probatio.Optional("page"): probatio.Any(None, int),
        probatio.Optional("title"): OPTIONAL_STR,
        probatio.Optional("source"): OPTIONAL_STR,
        probatio.Optional("dismissed", default=False): bool,
    }
)
@callback
def ws_pressed(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Announce a press."""
    _LOGGER.debug("pressed: %s", msg)
    if not _is_admin_or_error(connection, msg["id"]):
        return
    if (hub := _app_hub_or_error(connection, msg["id"])) is None:
        return
    try:
        hub.async_pressed(connection, msg)
    except (NotConnectedError, PadNotFoundError) as err:
        _send_app_error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "stream_dock_ha/frame",
        probatio.Required("instance_id"): HEX_ID,
        probatio.Required("key"): str,
        probatio.Required("pad_id"): HEX_ID,
        probatio.Required("width"): probatio.All(int, probatio.Range(min=1, max=4096)),
        probatio.Required("height"): probatio.All(int, probatio.Range(min=1, max=4096)),
        probatio.Required("data"): str,
        probatio.Required("tiles"): [
            probatio.Schema(
                {
                    probatio.Required("name"): str,
                    probatio.Required("x"): int,
                    probatio.Required("y"): int,
                    probatio.Required("w"): int,
                    probatio.Required("h"): int,
                }
            )
        ],
        probatio.Optional("seamless", default=False): bool,
    }
)
@callback
def ws_frame(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Take a Mini Monitor frame for the cards (protocol 3.6)."""
    if not _is_admin_or_error(connection, msg["id"]):
        return
    if (hub := _app_hub_or_error(connection, msg["id"])) is None:
        return
    try:
        hub.async_frame(msg)
    except (NotConnectedError, PadNotFoundError) as err:
        _send_app_error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "stream_dock_ha/pictures",
        probatio.Required("pad_id"): HEX_ID,
        probatio.Required("scale"): SCALE,
        probatio.Required("complete"): bool,
        probatio.Required("pictures"): {str: PICTURE_SCHEMA},
    }
)
@callback
def ws_pictures(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Take pictures for the cards."""
    _LOGGER.debug(
        "pictures: %s scale %s complete %s, %d controls",
        msg["pad_id"],
        msg["scale"],
        msg["complete"],
        len(msg["pictures"]),
    )
    if not _is_admin_or_error(connection, msg["id"]):
        return
    if (hub := _app_hub_or_error(connection, msg["id"])) is None:
        return
    try:
        hub.async_pictures(connection, msg)
    except (NotConnectedError, PadNotFoundError) as err:
        _send_app_error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"])


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "stream_dock_ha/reply",
        probatio.Required("request_id"): str,
        probatio.Required("ok"): bool,
        probatio.Optional("result"): object,
        probatio.Optional("error"): OPTIONAL_STR,
    }
)
@callback
def ws_reply(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Take the answer to a command event."""
    _LOGGER.debug("reply: %s", msg)
    if not _is_admin_or_error(connection, msg["id"]):
        return
    if (hub := _app_hub_or_error(connection, msg["id"])) is None:
        return
    try:
        hub.async_reply(connection, msg)
    except NotConnectedError as err:
        _send_app_error(connection, msg["id"], err)
        return
    connection.send_result(msg["id"])


# ----------------------------------------------------------------------
# The card's commands


@websocket_api.websocket_command({probatio.Required("type"): "stream_dock_ha/pads"})
@callback
def ws_pads(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """List every known pad."""
    if (hub := _hub_or_error(connection, msg["id"])) is None:
        return
    connection.send_result(
        msg["id"],
        {
            "pads": [
                {
                    "pad_id": pad.pad_id,
                    "name": pad.name,
                    "pc": hub.pc_of(pad).name,
                    "kind": pad.kind,
                    "online": hub.pc_of(pad).online,
                    "device_id": pad.device_id,
                }
                for pad in hub.pads.values()
            ]
        },
    )


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "stream_dock_ha/watch",
        probatio.Required("pad_id"): str,
        probatio.Optional("scale", default=DEFAULT_WATCH_SCALE): SCALE,
    }
)
@callback
def ws_watch(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Watch a pad's state and pictures (a subscription)."""
    if (hub := _hub_or_error(connection, msg["id"])) is None:
        return
    if (pad := hub.pads.get(msg["pad_id"])) is None:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Unknown pad")
        return

    @callback
    def send(event: dict[str, Any]) -> None:
        connection.send_message(websocket_api.event_message(msg["id"], event))

    connection.subscriptions[msg["id"]] = hass.data[DATA_KEY].watchers.async_add(
        pad.pad_id, msg["scale"], send
    )
    connection.send_result(msg["id"])
    send(hub.pad_event(pad))
    if (pictures := hub.pictures_event(pad)) is not None:
        send(pictures)


@websocket_api.websocket_command(
    {
        probatio.Required("type"): "stream_dock_ha/press",
        probatio.Required("pad_id"): str,
        probatio.Required("control"): str,
    }
)
@websocket_api.async_response
async def ws_press(
    hass: HomeAssistant, connection: ActiveConnection, msg: dict[str, Any]
) -> None:
    """Press a control from a card."""
    if (hub := _hub_or_error(connection, msg["id"])) is None:
        return
    if msg["pad_id"] not in hub.pads:
        connection.send_error(msg["id"], websocket_api.ERR_NOT_FOUND, "Unknown pad")
        return
    if hub.entry.options.get(CONF_ADMIN_ONLY_PRESS) and not connection.user.is_admin:
        connection.send_error(
            msg["id"],
            websocket_api.ERR_UNAUTHORIZED,
            "Only administrators can press keys here",
        )
        return
    try:
        result = await hub.async_command(
            msg["pad_id"],
            "press_key",
            {"control": msg["control"]},
            source="dashboard",
            user=connection.user.name,
        )
    except NoAnswerError as err:
        connection.send_error(msg["id"], ERR_FAILED, err.text)
        return
    except StreamDockError as err:
        connection.send_error(msg["id"], err.code, err.text)
        return
    connection.send_result(msg["id"], result)
