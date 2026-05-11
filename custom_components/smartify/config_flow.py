"""Adds config and options flows for Smartify."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Final

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import Platform
from homeassistant.core import callback
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify

from .config_flow_schema import (
    make_ceiling_fan_schema,
    make_controlled_entity_schema,
    make_exhaust_fan_schema,
    make_light_schema,
    make_occupancy_schema,
)
from .const import DOMAIN, Config, ControllerType

ErrorsType = MutableMapping[str, str]

FAN_TYPE: Final = "fan_type"
GITHUB_URL: Final = "https://github.com/lymanepp/ha-smartify"
SSI_URL: Final = "http://www.summersimmer.com/home.htm"


class SmartifyConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow for Smartify."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the config flow."""
        self._controlled_entity: str | None = None
        self._placeholders: dict[str, str] = {
            "github_url": GITHUB_URL,
            "ssi_url": SSI_URL,
        }

    async def async_step_user(
        self,
        user_input: ConfigType | None = None,
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        return self.async_show_menu(
            step_id="user",
            menu_options=[
                ControllerType.CEILING_FAN,
                ControllerType.EXHAUST_FAN,
                ControllerType.LIGHT,
                ControllerType.OCCUPANCY,
            ],
        )

    async def async_step_ceiling_fan(
        self,
        user_input: ConfigType | None = None,
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: ErrorsType = {}

        if user_input is not None:
            self._controlled_entity = user_input[Config.CONTROLLED_ENTITY]

            if not self._controlled_entity:
                return self.async_abort(reason="invalid_entity")

            state = self.hass.states.get(self._controlled_entity)

            if state is None:
                return self.async_abort(reason="invalid_entity")

            self._placeholders["controlled_entity"] = state.name

            return await self.async_step_ceiling_fan_options()

        return self.async_show_form(
            step_id="ceiling_fan",
            data_schema=make_controlled_entity_schema(
                self.hass, user_input or {}, Platform.FAN
            ),
            description_placeholders=self._placeholders,
            errors=errors,
        )

    async def async_step_ceiling_fan_options(
        self,
        user_input: ConfigType | None = None,
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: ErrorsType = {}

        if not self._controlled_entity:
            return self.async_abort(reason="invalid_entity")

        if user_input is not None:
            # TODO: validate dependencies between fields here (or in schema)

            unique_id = f"{DOMAIN}__" + slugify(self._controlled_entity)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            state = self.hass.states.get(self._controlled_entity)

            if state is None:
                return self.async_abort(reason="invalid_entity")

            data = {
                Config.CONTROLLER_TYPE: ControllerType.CEILING_FAN,
                Config.CONTROLLED_ENTITY: self._controlled_entity,
                **user_input,
            }

            return self.async_create_entry(title=state.name, data=data)

        return self.async_show_form(
            step_id="ceiling_fan_options",
            data_schema=make_ceiling_fan_schema(
                self.hass, user_input or {}, self._controlled_entity
            ),
            description_placeholders=self._placeholders,
            errors=errors,
        )

    async def async_step_exhaust_fan(
        self,
        user_input: ConfigType | None = None,
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: ErrorsType = {}

        if user_input is not None:
            self._controlled_entity = user_input[Config.CONTROLLED_ENTITY]

            if not self._controlled_entity:
                return self.async_abort(reason="invalid_entity")

            state = self.hass.states.get(self._controlled_entity)

            if state is None:
                return self.async_abort(reason="invalid_entity")

            self._placeholders["controlled_entity"] = state.name

            return await self.async_step_exhaust_fan_options()

        return self.async_show_form(
            step_id="exhaust_fan",
            data_schema=make_controlled_entity_schema(
                self.hass, user_input or {}, Platform.FAN
            ),
            description_placeholders=self._placeholders,
            errors=errors,
        )

    async def async_step_exhaust_fan_options(
        self,
        user_input: ConfigType | None = None,
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: ErrorsType = {}

        if not self._controlled_entity:
            return self.async_abort(reason="invalid_entity")

        if user_input is not None:
            unique_id = f"{DOMAIN}__" + slugify(self._controlled_entity)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            state = self.hass.states.get(self._controlled_entity)

            if state is None:
                return self.async_abort(reason="invalid_entity")

            data = {
                Config.CONTROLLER_TYPE: ControllerType.EXHAUST_FAN,
                Config.CONTROLLED_ENTITY: self._controlled_entity,
                **user_input,
            }

            return self.async_create_entry(title=state.name, data=data)

        return self.async_show_form(
            step_id="exhaust_fan_options",
            data_schema=make_exhaust_fan_schema(self.hass, user_input or {}),
            description_placeholders=self._placeholders,
            errors=errors,
        )

    async def async_step_light(
        self,
        user_input: ConfigType | None = None,
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: ErrorsType = {}

        if user_input is not None:
            self._controlled_entity = user_input[Config.CONTROLLED_ENTITY]

            if not self._controlled_entity:
                return self.async_abort(reason="invalid_entity")

            state = self.hass.states.get(self._controlled_entity)

            if state is None:
                return self.async_abort(reason="invalid_entity")

            self._placeholders["controlled_entity"] = state.name

            return await self.async_step_light_options()

        return self.async_show_form(
            step_id="light",
            data_schema=make_controlled_entity_schema(
                self.hass, user_input or {}, Platform.LIGHT
            ),
            description_placeholders=self._placeholders,
            errors=errors,
        )

    async def async_step_light_options(
        self,
        user_input: ConfigType | None = None,
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: ErrorsType = {}

        if not self._controlled_entity:
            return self.async_abort(reason="invalid_entity")

        if user_input:
            unique_id = f"{DOMAIN}__" + slugify(self._controlled_entity)
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            state = self.hass.states.get(self._controlled_entity)

            if state is None:
                return self.async_abort(reason="invalid_entity")

            data = {
                Config.CONTROLLER_TYPE: ControllerType.LIGHT,
                Config.CONTROLLED_ENTITY: self._controlled_entity,
                **user_input,
            }

            return self.async_create_entry(title=state.name, data=data)

        return self.async_show_form(
            step_id="light_options",
            data_schema=make_light_schema(
                self.hass, user_input or {}, self._controlled_entity
            ),
            description_placeholders=self._placeholders,
            errors=errors,
        )

    async def async_step_occupancy(
        self,
        user_input: ConfigType | None = None,
    ) -> ConfigFlowResult:
        """Handle a flow initialized by the user."""
        errors: ErrorsType = {}

        if user_input is not None and _validate_occupancy(user_input, errors):
            sensor_name = user_input[Config.SENSOR_NAME]
            unique_id = f"{DOMAIN}__{ControllerType.OCCUPANCY}__" + slugify(sensor_name)

            if await self.async_set_unique_id(unique_id):
                errors["base"] = "duplicate_name"
            else:
                self._abort_if_unique_id_configured()

                data = {
                    Config.CONTROLLER_TYPE: ControllerType.OCCUPANCY,
                    **{
                        key: value
                        for key, value in user_input.items()
                        if key != Config.SENSOR_NAME
                    },
                }

                return self.async_create_entry(title=sensor_name, data=data)

        return self.async_show_form(
            step_id="occupancy",
            data_schema=make_occupancy_schema(self.hass, user_input or {}),
            description_placeholders=self._placeholders,
            errors=errors,
        )

    @staticmethod
    @callback  # type: ignore
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return SmartifyOptionsFlow(config_entry)


class SmartifyOptionsFlow(OptionsFlow):  # type: ignore
    """Handle options."""

    def __init__(self, config_entry: ConfigEntry):
        """Initialize options flow."""
        data = dict(config_entry.data)
        self._controller_type = data.pop(Config.CONTROLLER_TYPE)
        self._controlled_entity = data.pop(Config.CONTROLLED_ENTITY, None)
        self.original_data = dict(config_entry.options) or data
        self._placeholders: dict[str, str] = {
            "github_url": GITHUB_URL,
            "ssi_url": SSI_URL,
        }

    async def async_step_init(self, _: ConfigType | None = None) -> ConfigFlowResult:
        """Handle option flow 'init' step."""
        if self._controlled_entity:
            state = self.hass.states.get(self._controlled_entity)

            if state is None:
                return self.async_abort(reason="invalid_entity")

            self._placeholders["controlled_entity"] = state.name

        match self._controller_type:
            case ControllerType.CEILING_FAN:
                return await self.async_step_ceiling_fan()
            case ControllerType.EXHAUST_FAN:
                return await self.async_step_exhaust_fan()
            case ControllerType.LIGHT:
                return await self.async_step_light()
            case ControllerType.OCCUPANCY:
                return await self.async_step_occupancy()
        raise AbortFlow("invalid_type")

    async def async_step_ceiling_fan(
        self, user_input: ConfigType | None = None
    ) -> ConfigFlowResult:
        """Handle option flow 'ceiling fan' step."""
        errors: ErrorsType = {}

        if not self._controlled_entity:
            return self.async_abort(reason="invalid_entity")

        if user_input is not None:
            state = self.hass.states.get(self._controlled_entity)

            if state is None:
                return self.async_abort(reason="invalid_entity")

            return self.async_create_entry(title=state.name, data=user_input)

        schema = make_ceiling_fan_schema(
            self.hass, user_input or self.original_data, self._controlled_entity
        )

        return self.async_show_form(
            step_id="ceiling_fan",
            data_schema=schema,
            description_placeholders=self._placeholders,
            errors=errors,
        )

    async def async_step_exhaust_fan(
        self, user_input: ConfigType | None = None
    ) -> ConfigFlowResult:
        """Handle option flow 'exhaust fan' step."""
        errors: ErrorsType = {}

        if not self._controlled_entity:
            return self.async_abort(reason="invalid_entity")

        if user_input is not None:
            state = self.hass.states.get(self._controlled_entity)

            if state is None:
                return self.async_abort(reason="invalid_entity")

            return self.async_create_entry(title=state.name, data=user_input)

        schema = make_exhaust_fan_schema(self.hass, user_input or self.original_data)

        return self.async_show_form(
            step_id="exhaust_fan",
            data_schema=schema,
            description_placeholders=self._placeholders,
            errors=errors,
        )

    async def async_step_light(
        self, user_input: ConfigType | None = None
    ) -> ConfigFlowResult:
        """Handle option flow 'light' step."""
        errors: ErrorsType = {}

        if not self._controlled_entity:
            return self.async_abort(reason="invalid_entity")

        if user_input:
            state = self.hass.states.get(self._controlled_entity)

            if state is None:
                return self.async_abort(reason="invalid_entity")

            return self.async_create_entry(title=state.name, data=user_input)

        schema = make_light_schema(
            self.hass, user_input or self.original_data, self._controlled_entity
        )

        return self.async_show_form(
            step_id="light",
            data_schema=schema,
            description_placeholders=self._placeholders,
            errors=errors,
        )

    async def async_step_occupancy(
        self, user_input: ConfigType | None = None
    ) -> ConfigFlowResult:
        """Handle option flow 'occupancy' step."""
        errors: ErrorsType = {}

        if user_input is not None and _validate_occupancy(user_input, errors):
            return self.async_create_entry(title="", data=user_input)

        schema = make_occupancy_schema(
            self.hass,
            user_input or self.original_data,
            include_name=False,
        )

        return self.async_show_form(
            step_id="occupancy",
            data_schema=schema,
            description_placeholders=self._placeholders,
            errors=errors,
        )


# #### Internal functions ####


def _validate_occupancy(user_input: ConfigType, errors: ErrorsType) -> bool:
    """Validate occupancy controller configuration.

    Trigger entities are allowed to start occupancy. Sustain entities are allowed
    to maintain occupancy. If triggers exist without sustains, the controller
    needs a decay timer because nothing else can prove the room remains occupied.
    If sustains exist, no decay timer is required.
    """
    trigger_entities = user_input.get(Config.TRIGGER_ENTITIES)
    sustain_entities = user_input.get(Config.SUSTAIN_ENTITIES)
    decay_minutes = user_input.get(Config.DECAY_MINUTES)

    if not trigger_entities and not sustain_entities:
        errors["base"] = "occupancy_needs_entity"
        return False

    if trigger_entities and not sustain_entities and not decay_minutes:
        errors["base"] = "trigger_only_needs_decay"
        return False

    return True
