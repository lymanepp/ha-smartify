"""YAML configuration schemas for Smartify.

Mirrors the fields collected by the config and options flows
(`config_flow_schema.py`) so that a controller can be fully defined in
`configuration.yaml` instead of (or in addition to) the UI. A controller
defined here runs entirely independently of `hass.config_entries`: it is
never turned into a config entry, has no options flow, and is not shown in
the UI's integration list -- see `async_setup` in `__init__.py`. YAML and
the UI are two parallel ways to define a controller, not one feeding into
the other. Changing YAML requires a reload/restart, same as most
YAML-configured Home Assistant integrations.
"""

from __future__ import annotations

from typing import Any, Final

import voluptuous as vol
import homeassistant.helpers.config_validation as cv

from .const import (
    DEFAULT_EXHAUST_FALLING_THRESHOLD,
    DEFAULT_EXHAUST_MANUAL_MINUTES,
    DEFAULT_EXHAUST_RISING_THRESHOLD,
    DOMAIN,
    Config,
    ControllerType,
)

_MINUTES_SCHEMA: Final = vol.All(vol.Coerce(int), vol.Range(min=0, max=60))

# `unique_id` is accepted by every controller type: an optional, stable
# override for the synthetic entry_id/device identity that `async_setup`
# would otherwise derive by slugifying `controlled_entity`/`sensor_name`.
# Useful so renaming a light or rewording an occupancy sensor's name doesn't
# also change its entity registry identity.
_UNIQUE_ID_FIELD: Final = {vol.Optional(str(Config.UNIQUE_ID)): cv.string}

# `name` is only meaningful for entity-based controllers (occupancy already
# has a required `sensor_name`, which doubles as its title). It overrides
# the title that would otherwise be derived from the controlled entity's
# current friendly name -- useful at startup, before other integrations'
# entities (and therefore their friendly names) may exist yet.
_NAME_OVERRIDE_FIELD: Final = {vol.Optional(str(Config.NAME)): cv.string}

_CEILING_FAN_SCHEMA: Final = vol.Schema(
    {
        **_NAME_OVERRIDE_FIELD,
        **_UNIQUE_ID_FIELD,
        vol.Required(str(Config.CONTROLLED_ENTITY)): cv.entity_id,
        vol.Required(str(Config.TEMP_SENSOR)): cv.entity_id,
        vol.Required(str(Config.HUMIDITY_SENSOR)): cv.entity_id,
        vol.Required(str(Config.SSI_MIN)): vol.Coerce(float),
        vol.Required(str(Config.SSI_MAX)): vol.Coerce(float),
        vol.Required(str(Config.SPEED_MIN)): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=100)
        ),
        vol.Required(str(Config.SPEED_MAX)): vol.All(
            vol.Coerce(float), vol.Range(min=0, max=100)
        ),
        vol.Optional(str(Config.REQUIRED_ON_ENTITIES)): cv.entity_ids,
        vol.Optional(str(Config.REQUIRED_OFF_ENTITIES)): cv.entity_ids,
        vol.Optional(str(Config.MANUAL_CONTROL_MINUTES)): _MINUTES_SCHEMA,
    }
)

_EXHAUST_FAN_SCHEMA: Final = vol.Schema(
    {
        **_NAME_OVERRIDE_FIELD,
        **_UNIQUE_ID_FIELD,
        vol.Required(str(Config.CONTROLLED_ENTITY)): cv.entity_id,
        vol.Required(str(Config.TEMP_SENSOR)): cv.entity_id,
        vol.Required(str(Config.HUMIDITY_SENSOR)): cv.entity_id,
        vol.Required(str(Config.REFERENCE_TEMP_SENSOR)): cv.entity_id,
        vol.Required(str(Config.REFERENCE_HUMIDITY_SENSOR)): cv.entity_id,
        vol.Optional(
            str(Config.RISING_THRESHOLD), default=DEFAULT_EXHAUST_RISING_THRESHOLD
        ): vol.Coerce(float),
        vol.Optional(
            str(Config.FALLING_THRESHOLD), default=DEFAULT_EXHAUST_FALLING_THRESHOLD
        ): vol.Coerce(float),
        vol.Optional(
            str(Config.MANUAL_CONTROL_MINUTES), default=DEFAULT_EXHAUST_MANUAL_MINUTES
        ): _MINUTES_SCHEMA,
    }
)

_LIGHT_SCHEMA: Final = vol.Schema(
    {
        **_NAME_OVERRIDE_FIELD,
        **_UNIQUE_ID_FIELD,
        vol.Required(str(Config.CONTROLLED_ENTITY)): cv.entity_id,
        vol.Optional(str(Config.BRIGHTNESS_PCT)): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=100)
        ),
        vol.Optional(str(Config.TRIGGER_ENTITY)): cv.entity_id,
        # Illuminance sensor/cutoff must be configured together, same as the UI.
        vol.Inclusive(str(Config.ILLUMINANCE_SENSOR), "illuminance"): cv.entity_id,
        vol.Inclusive(str(Config.ILLUMINANCE_CUTOFF), "illuminance"): vol.All(
            vol.Coerce(int), vol.Range(min=0)
        ),
        vol.Optional(str(Config.REQUIRED_ON_ENTITIES)): cv.entity_ids,
        vol.Optional(str(Config.REQUIRED_OFF_ENTITIES)): cv.entity_ids,
        vol.Optional(str(Config.AUTO_OFF_MINUTES)): _MINUTES_SCHEMA,
    }
)


def _validate_occupancy(config: dict[str, Any]) -> dict[str, Any]:
    """Apply the same trigger/sustain/decay rules as the options flow."""
    trigger_entities = config.get(Config.TRIGGER_ENTITIES)
    sustain_entities = config.get(Config.SUSTAIN_ENTITIES)
    decay_minutes = config.get(Config.DECAY_MINUTES)

    if not trigger_entities and not sustain_entities:
        raise vol.Invalid(
            "must configure at least one of 'trigger_entities' or 'sustain_entities'"
        )

    if trigger_entities and not sustain_entities and not decay_minutes:
        raise vol.Invalid(
            "'decay_minutes' is required when only 'trigger_entities' are configured"
        )

    return config


_OCCUPANCY_SCHEMA: Final = vol.All(
    vol.Schema(
        {
            **_UNIQUE_ID_FIELD,
            vol.Required(str(Config.SENSOR_NAME)): cv.string,
            vol.Optional(str(Config.TRIGGER_ENTITIES)): cv.entity_ids,
            vol.Optional(str(Config.SUSTAIN_ENTITIES)): cv.entity_ids,
            vol.Optional(str(Config.DECAY_MINUTES)): _MINUTES_SCHEMA,
            vol.Optional(str(Config.REQUIRED_ON_ENTITIES)): cv.entity_ids,
            vol.Optional(str(Config.REQUIRED_OFF_ENTITIES)): cv.entity_ids,
        }
    ),
    _validate_occupancy,
)

CONFIG_SCHEMA: Final = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Optional(
                    str(ControllerType.CEILING_FAN), default=list
                ): vol.All(cv.ensure_list, [_CEILING_FAN_SCHEMA]),
                vol.Optional(
                    str(ControllerType.EXHAUST_FAN), default=list
                ): vol.All(cv.ensure_list, [_EXHAUST_FAN_SCHEMA]),
                vol.Optional(str(ControllerType.LIGHT), default=list): vol.All(
                    cv.ensure_list, [_LIGHT_SCHEMA]
                ),
                vol.Optional(
                    str(ControllerType.OCCUPANCY), default=list
                ): vol.All(cv.ensure_list, [_OCCUPANCY_SCHEMA]),
            }
        )
    },
    extra=vol.ALLOW_EXTRA,
)
