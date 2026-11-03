"""Config flow for Stream Dock HA."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
import probatio

from .const import CONF_ADMIN_ONLY_PRESS, DOMAIN, NAME
from .data import StreamDockConfigEntry


class StreamDockConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add Stream Dock HA. There is nothing to fill in."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding the integration."""
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={})
        return self.async_show_form(step_id="user")

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: StreamDockConfigEntry) -> OptionsFlow:
        """Return the options flow."""
        return StreamDockOptionsFlow()


class StreamDockOptionsFlow(OptionsFlow):
    """Who may press keys on dashboards."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        return self.async_show_form(
            step_id="init",
            data_schema=probatio.Schema(
                {
                    probatio.Required(
                        CONF_ADMIN_ONLY_PRESS,
                        default=self.config_entry.options.get(
                            CONF_ADMIN_ONLY_PRESS, False
                        ),
                    ): bool,
                }
            ),
        )
