"""Actions that send commands to a pad's PC (protocol section 8)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError, Unauthorized, UnknownUser
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import VolDictType
import probatio

from .const import DOMAIN
from .data import async_get_hub
from .hub import StreamDockHub

ATTR_DEVICE_ID = "device_id"

PAGE = probatio.All(probatio.Coerce(int), probatio.Range(min=1))
KEY = probatio.All(probatio.Coerce(int), probatio.Range(min=1))
RGB = probatio.All(
    probatio.ExactSequence((cv.byte, cv.byte, cv.byte)), probatio.Coerce(list)
)

LOCATION: VolDictType = {
    probatio.Optional("profile"): cv.string,
    probatio.Optional("page"): PAGE,
}
TARGET: VolDictType = {
    probatio.Exclusive("key", "target"): KEY,
    probatio.Exclusive("control", "target"): cv.string,
}
# A key on whatever page the pad shows: its number (also as text) or a
# control's name such as "key_3".
ON_KEY: VolDictType = {
    probatio.Exclusive("key", "target"): probatio.Any(KEY, cv.string),
    probatio.Exclusive("control", "target"): cv.string,
}
TO_SCHEMA = probatio.All(
    probatio.Schema(
        {
            **TARGET,
            **LOCATION,
            probatio.Optional(ATTR_DEVICE_ID): cv.string,
        }
    ),
    cv.has_at_least_one_key("key", "control"),
)


@dataclass(frozen=True, slots=True)
class ActionSpec:
    """How an action maps to an app command."""

    fields: VolDictType = field(default_factory=dict)
    command: str | None = None
    needs_target: bool = False
    changes: bool = True
    response: SupportsResponse = SupportsResponse.OPTIONAL


def _target(extra: VolDictType | None = None) -> ActionSpec:
    return ActionSpec({**TARGET, **LOCATION, **(extra or {})}, needs_target=True)


ACTIONS: dict[str, ActionSpec] = {
    # Profiles
    "show_profile": ActionSpec({probatio.Required("profile"): cv.string}),
    "next_profile": ActionSpec(),
    "previous_profile": ActionSpec(),
    "first_profile": ActionSpec(),
    "add_profile": ActionSpec({probatio.Required("name"): cv.string}),
    "rename_profile": ActionSpec(
        {probatio.Required("name"): cv.string, probatio.Required("profile"): cv.string}
    ),
    "duplicate_profile": ActionSpec(
        {probatio.Required("profile"): cv.string, probatio.Optional("name"): cv.string}
    ),
    "delete_profile": ActionSpec({probatio.Required("profile"): cv.string}),
    # Pages
    "show_page": ActionSpec(
        {probatio.Required("page"): PAGE, probatio.Optional("profile"): cv.string}
    ),
    "next_page": ActionSpec({probatio.Optional("profile"): cv.string}),
    "previous_page": ActionSpec({probatio.Optional("profile"): cv.string}),
    "add_page": ActionSpec({probatio.Optional("profile"): cv.string}),
    "delete_page": ActionSpec(
        {probatio.Required("page"): PAGE, probatio.Optional("profile"): cv.string}
    ),
    # Keys
    "set_key": _target({probatio.Required("set"): dict}),
    "add_key": ActionSpec({**LOCATION, probatio.Required("set"): dict}),
    "clear_key": _target(),
    "press_key": _target(),
    "swap_keys": ActionSpec(
        {**LOCATION, probatio.Required("key"): KEY, probatio.Required("with"): KEY}
    ),
    "copy_key": _target({probatio.Required("to"): TO_SCHEMA}),
    "move_key": _target({probatio.Required("to"): TO_SCHEMA}),
    "get_key": ActionSpec(
        {**TARGET, **LOCATION},
        needs_target=True,
        changes=False,
        response=SupportsResponse.ONLY,
    ),
    "get_state": ActionSpec(
        command="state", changes=False, response=SupportsResponse.ONLY
    ),
    # Pads
    "set_brightness": ActionSpec(
        {
            probatio.Required("level"): probatio.All(
                probatio.Coerce(int), probatio.Range(min=0, max=100)
            )
        }
    ),
    "set_screen": ActionSpec({probatio.Required("on"): cv.boolean}),
    "mini_monitor": ActionSpec({probatio.Required("on"): cv.boolean}),
    # Alerts
    "show_alert": ActionSpec(
        {
            probatio.Optional("title"): cv.string,
            probatio.Optional("message"): cv.string,
            probatio.Optional("icon"): cv.icon,
            probatio.Optional("color"): RGB,
            probatio.Optional("seconds"): cv.positive_int,
            probatio.Optional("camera"): cv.entity_domain("camera"),
        }
    ),
    "clear_alert": ActionSpec(),
    # Something on one key for a while
    "show_on_key": ActionSpec(
        {
            **ON_KEY,
            probatio.Optional("title"): cv.string,
            probatio.Optional("message"): cv.string,
            probatio.Optional("icon"): cv.icon,
            probatio.Optional("color"): RGB,
            probatio.Optional("seconds"): probatio.All(
                probatio.Coerce(float), probatio.Range(min=0, max=86400)
            ),
            probatio.Exclusive("camera", "picture"): cv.entity_domain("camera"),
            probatio.Exclusive("picture", "picture"): cv.string,
            probatio.Optional("fit"): probatio.In(["fill", "fit", "stretch"]),
        },
        needs_target=True,
    ),
    "clear_on_key": ActionSpec(ON_KEY),
}


def _schema(spec: ActionSpec) -> Any:
    schema = probatio.Schema(
        {probatio.Required(ATTR_DEVICE_ID): cv.string, **spec.fields}
    )
    if spec.needs_target:
        return probatio.All(schema, cv.has_at_least_one_key("key", "control"))
    return schema


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions."""

    async def handle(call: ServiceCall) -> ServiceResponse:
        spec = ACTIONS[call.service]
        hub = async_get_hub(hass)
        if hub is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="not_loaded"
            )
        user = await _async_user_name(hass, call, admin_only=spec.changes)
        fields = dict(call.data)
        pad = hub.pad_by_device_id(fields.pop(ATTR_DEVICE_ID))
        if pad is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="not_a_pad"
            )
        if "to" in fields:
            fields["to"] = _resolve_to(hub, fields["to"])
        result = await hub.async_command(
            pad.pad_id,
            spec.command or call.service,
            fields,
            source="action",
            user=user,
        )
        if not call.return_response:
            return None
        return result if isinstance(result, dict) else {"result": result}

    for name, spec in ACTIONS.items():
        hass.services.async_register(
            DOMAIN, name, handle, schema=_schema(spec), supports_response=spec.response
        )


def _resolve_to(hub: StreamDockHub, to: dict[str, Any]) -> dict[str, Any]:
    """Turn `to.device_id` into the app's `to.pad`."""
    to = dict(to)
    if (device_id := to.pop(ATTR_DEVICE_ID, None)) is not None:
        if (pad := hub.pad_by_device_id(device_id)) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="not_a_pad"
            )
        to["pad"] = pad.pad_id
    return to


async def _async_user_name(
    hass: HomeAssistant, call: ServiceCall, *, admin_only: bool
) -> str | None:
    """Return the calling user's name, refusing non-administrators if asked.

    Automations and scripts run without a user and are always allowed.
    """
    if call.context.user_id is None:
        return None
    user = await hass.auth.async_get_user(call.context.user_id)
    if user is None:
        raise UnknownUser(context=call.context)
    if admin_only and not user.is_admin:
        raise Unauthorized(context=call.context)
    return user.name
