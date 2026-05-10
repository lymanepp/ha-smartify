"""Adds config flow for Light Controller."""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Final

import voluptuous as vol
from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.fan import ATTR_PERCENTAGE_STEP
from homeassistant.components.input_boolean import DOMAIN as INPUT_BOOLEAN_DOMAIN
from homeassistant.components.light import ATTR_SUPPORTED_COLOR_MODES, ColorMode
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import PERCENTAGE, Platform, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import AbortFlow
from homeassistant.helpers import selector
from homeassistant.helpers.typing import ConfigType
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import (
    DEFAULT_CEILING_SSI_MAX_FAHRENHEIT,
    DEFAULT_CEILING_SSI_MIN_FAHRENHEIT,
    DEFAULT_EXHAUST_FALLING_THRESHOLD,
    DEFAULT_EXHAUST_MANUAL_MINUTES,
    DEFAULT_EXHAUST_RISING_THRESHOLD,
    DOMAIN,
    GRAMS_PER_CUBIC_METER,
    Config,
)
from .util import domain_entities, on_off_entities

ErrorsType = MutableMapping[str, str]

FAN_TYPE: Final = "fan_type"


def make_controlled_entity_schema(
    hass: HomeAssistant, user_input: ConfigType, domain: str
) -> vol.Schema:
    """Create 'controlled_entity' config schema."""

    entities = domain_entities(hass, domain)
    entities.difference_update(_existing_controlled_entities(hass))
    entities = sorted(entities)

    if not entities:
        raise AbortFlow("nothing_to_control")

    return vol.Schema(
        {
            vol.Required(
                str(Config.CONTROLLED_ENTITY),
                default=user_input.get(Config.CONTROLLED_ENTITY, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(include_entities=entities),
            ),
        }
    )


def make_ceiling_fan_schema(
    hass: HomeAssistant, user_input: ConfigType, controlled_entity: str
) -> vol.Schema:
    """Create 'ceiling_fan' config schema."""

    temp_sensors = domain_entities(
        hass,
        [Platform.SENSOR],
        device_classes=SensorDeviceClass.TEMPERATURE,
        units_of_measurement=[
            None,
            UnitOfTemperature.CELSIUS,
            UnitOfTemperature.FAHRENHEIT,
        ],
    )

    humidity_sensors = domain_entities(
        hass,
        [Platform.SENSOR],
        device_classes=SensorDeviceClass.HUMIDITY,
        units_of_measurement=[None, PERCENTAGE],
    )

    required_entities = domain_entities(
        hass, [Platform.BINARY_SENSOR, INPUT_BOOLEAN_DOMAIN]
    ) | on_off_entities(hass, [Platform.FAN])

    fan_state = hass.states.get(controlled_entity)
    assert fan_state
    speed_step = fan_state.attributes.get(ATTR_PERCENTAGE_STEP, 100)

    default_ssi_min = TemperatureConverter.convert(
        DEFAULT_CEILING_SSI_MIN_FAHRENHEIT,
        UnitOfTemperature.FAHRENHEIT,
        hass.config.units.temperature_unit,
    )

    default_ssi_max = TemperatureConverter.convert(
        DEFAULT_CEILING_SSI_MAX_FAHRENHEIT,
        UnitOfTemperature.FAHRENHEIT,
        hass.config.units.temperature_unit,
    )

    ssi_selector = selector.NumberSelector(
        selector.NumberSelectorConfig(
            unit_of_measurement=hass.config.units.temperature_unit,
            mode=selector.NumberSelectorMode.BOX,
        ),
    )

    speed_selector = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=100,
            step=speed_step,
            unit_of_measurement=PERCENTAGE,
            mode=selector.NumberSelectorMode.SLIDER,
        ),
    )

    minutes_selector = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=60,
            unit_of_measurement="minutes",
            mode=selector.NumberSelectorMode.SLIDER,
        ),
    )

    return vol.Schema(
        {
            # temperature sensor
            vol.Required(
                str(Config.TEMP_SENSOR),
                default=user_input.get(Config.TEMP_SENSOR, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(include_entities=list(temp_sensors)),
            ),
            # humidity sensor
            vol.Required(
                str(Config.HUMIDITY_SENSOR),
                default=user_input.get(Config.HUMIDITY_SENSOR, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(include_entities=list(humidity_sensors)),
            ),
            # minimum SSI
            vol.Required(
                str(Config.SSI_MIN),
                default=user_input.get(Config.SSI_MIN, round(default_ssi_min, 1)),
            ): ssi_selector,
            # maximum SSI
            vol.Required(
                str(Config.SSI_MAX),
                default=user_input.get(Config.SSI_MAX, round(default_ssi_max, 1)),
            ): ssi_selector,
            # minimum fan speed
            vol.Required(
                str(Config.SPEED_MIN),
                default=user_input.get(Config.SPEED_MIN, vol.UNDEFINED),
            ): speed_selector,
            # maximum fan speed
            vol.Required(
                str(Config.SPEED_MAX),
                default=user_input.get(Config.SPEED_MAX, vol.UNDEFINED),
            ): speed_selector,
            # required on entities
            vol.Optional(
                str(Config.REQUIRED_ON_ENTITIES),
                default=user_input.get(Config.REQUIRED_ON_ENTITIES, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    include_entities=list(required_entities), multiple=True
                ),
            ),
            # required off entities
            vol.Optional(
                str(Config.REQUIRED_OFF_ENTITIES),
                default=user_input.get(Config.REQUIRED_OFF_ENTITIES, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    include_entities=list(required_entities), multiple=True
                ),
            ),
            # manual control minutes (optional)
            vol.Optional(
                str(Config.MANUAL_CONTROL_MINUTES),
                default=user_input.get(
                    Config.MANUAL_CONTROL_MINUTES,
                    vol.UNDEFINED,
                ),
            ): vol.All(minutes_selector, vol.Coerce(int)),
        }
    )


def make_exhaust_fan_schema(hass: HomeAssistant, user_input: ConfigType) -> vol.Schema:
    """Create 'exhaust_fan' config schema."""

    temp_sensors = domain_entities(
        hass,
        [Platform.SENSOR],
        device_classes=SensorDeviceClass.TEMPERATURE,
        units_of_measurement=[
            None,
            UnitOfTemperature.CELSIUS,
            UnitOfTemperature.FAHRENHEIT,
        ],
    )

    humidity_sensors = domain_entities(
        hass,
        [Platform.SENSOR],
        device_classes=SensorDeviceClass.HUMIDITY,
        units_of_measurement=[None, PERCENTAGE],
    )

    abs_humidity_selector = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0.0,
            max=5.0,
            step=0.1,
            unit_of_measurement=GRAMS_PER_CUBIC_METER,
            mode=selector.NumberSelectorMode.SLIDER,
        ),
    )

    minutes_selector = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=60,
            unit_of_measurement="minutes",
            mode=selector.NumberSelectorMode.SLIDER,
        ),
    )

    return vol.Schema(
        {
            # temperature sensor
            vol.Required(
                str(Config.TEMP_SENSOR),
                default=user_input.get(Config.TEMP_SENSOR, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(include_entities=list(temp_sensors)),
            ),
            # humidity sensor
            vol.Required(
                str(Config.HUMIDITY_SENSOR),
                default=user_input.get(Config.HUMIDITY_SENSOR, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(include_entities=list(humidity_sensors)),
            ),
            # reference temperature sensor
            vol.Required(
                str(Config.REFERENCE_TEMP_SENSOR),
                default=user_input.get(Config.REFERENCE_TEMP_SENSOR, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(include_entities=list(temp_sensors)),
            ),
            # reference humidity sensor
            vol.Required(
                str(Config.REFERENCE_HUMIDITY_SENSOR),
                default=user_input.get(Config.REFERENCE_HUMIDITY_SENSOR, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(include_entities=list(humidity_sensors)),
            ),
            # rising threshold
            vol.Required(
                str(Config.RISING_THRESHOLD),
                default=user_input.get(
                    Config.RISING_THRESHOLD, DEFAULT_EXHAUST_RISING_THRESHOLD
                ),
            ): abs_humidity_selector,
            # falling threshold
            vol.Required(
                str(Config.FALLING_THRESHOLD),
                default=user_input.get(
                    Config.FALLING_THRESHOLD,
                    DEFAULT_EXHAUST_FALLING_THRESHOLD,
                ),
            ): abs_humidity_selector,
            # manual control minutes
            vol.Optional(
                str(Config.MANUAL_CONTROL_MINUTES),
                default=user_input.get(
                    Config.MANUAL_CONTROL_MINUTES,
                    DEFAULT_EXHAUST_MANUAL_MINUTES,
                ),
            ): vol.All(minutes_selector, vol.Coerce(int)),
        }
    )


def make_light_schema(
    hass: HomeAssistant, user_input: ConfigType, controlled_entity: str
) -> vol.Schema:
    """Create 'light' config schema."""

    illuminance_sensors = domain_entities(
        hass,
        [Platform.SENSOR],
        device_classes=SensorDeviceClass.ILLUMINANCE,
    )

    binary_entities = domain_entities(
        hass, [Platform.BINARY_SENSOR, INPUT_BOOLEAN_DOMAIN]
    )

    minutes_selector = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=60,
            unit_of_measurement="minutes",
            mode=selector.NumberSelectorMode.SLIDER,
        ),
    )

    illuminance_selector = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            mode=selector.NumberSelectorMode.BOX,
        ),
    )

    schema = {}

    light_state = hass.states.get(controlled_entity)
    assert light_state
    color_modes = light_state.attributes.get(ATTR_SUPPORTED_COLOR_MODES, [])

    if ColorMode.BRIGHTNESS in color_modes:
        brightness_selector = selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1,
                max=100,
                unit_of_measurement=PERCENTAGE,
                mode=selector.NumberSelectorMode.SLIDER,
            ),
        )

        schema.update(
            {
                vol.Required(
                    str(Config.BRIGHTNESS_PCT),
                    default=user_input.get(Config.BRIGHTNESS_PCT, 100),
                ): brightness_selector,
            }
        )

    schema.update(
        {
            # trigger entities
            vol.Optional(
                str(Config.TRIGGER_ENTITY),
                default=user_input.get(Config.TRIGGER_ENTITY, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(include_entities=list(binary_entities)),
            ),
            # illuminance sensor
            vol.Inclusive(
                str(Config.ILLUMINANCE_SENSOR),
                "illumininance",
                default=user_input.get(Config.ILLUMINANCE_SENSOR, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    include_entities=list(illuminance_sensors)
                ),
            ),
            # illuminance threshold
            vol.Inclusive(
                str(Config.ILLUMINANCE_CUTOFF),
                "illumininance",
                default=user_input.get(Config.ILLUMINANCE_CUTOFF, vol.UNDEFINED),
            ): vol.All(illuminance_selector, vol.Coerce(int)),
            # required 'on' entities
            vol.Optional(
                str(Config.REQUIRED_ON_ENTITIES),
                default=user_input.get(Config.REQUIRED_ON_ENTITIES, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    include_entities=list(binary_entities), multiple=True
                ),
            ),
            # required 'off' entities
            vol.Optional(
                str(Config.REQUIRED_OFF_ENTITIES),
                default=user_input.get(Config.REQUIRED_OFF_ENTITIES, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    include_entities=list(binary_entities), multiple=True
                ),
            ),
            # auto off minutes
            vol.Optional(
                str(Config.AUTO_OFF_MINUTES),
                default=user_input.get(Config.AUTO_OFF_MINUTES, vol.UNDEFINED),
            ): vol.All(minutes_selector, vol.Coerce(int)),
        }
    )

    return vol.Schema(schema)


def make_occupancy_schema(hass: HomeAssistant, user_input: ConfigType) -> vol.Schema:
    """Create 'occupancy' config schema."""

    motion_sensors = domain_entities(
        hass,
        [Platform.BINARY_SENSOR],
        device_classes=BinarySensorDeviceClass.MOTION,
    )

    minutes_selector = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=60,
            unit_of_measurement="minutes",
            mode=selector.NumberSelectorMode.SLIDER,
        ),
    )

    conditional_entities = domain_entities(
        hass, [Platform.BINARY_SENSOR, INPUT_BOOLEAN_DOMAIN]
    ) | on_off_entities(hass, [Platform.BINARY_SENSOR, INPUT_BOOLEAN_DOMAIN])

    conditional_entities -= motion_sensors

    door_sensors = domain_entities(
        hass,
        [Platform.BINARY_SENSOR],
        device_classes=[
            BinarySensorDeviceClass.DOOR,
            BinarySensorDeviceClass.GARAGE_DOOR,
        ],
    )

    return vol.Schema(
        {
            # name
            vol.Required(
                str(Config.SENSOR_NAME),
                default=user_input.get(Config.SENSOR_NAME, vol.UNDEFINED),
            ): str,
            # motion sensors
            vol.Optional(
                str(Config.MOTION_SENSORS),
                default=user_input.get(Config.MOTION_SENSORS, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    include_entities=list(motion_sensors), multiple=True
                ),
            ),
            # motion-off minutes
            vol.Optional(
                str(Config.MOTION_OFF_MINUTES),
                default=user_input.get(Config.MOTION_OFF_MINUTES, vol.UNDEFINED),
            ): vol.All(minutes_selector, vol.Coerce(int)),
            # other entities
            vol.Optional(
                str(Config.OTHER_ENTITIES),
                default=user_input.get(Config.OTHER_ENTITIES, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    include_entities=list(conditional_entities), multiple=True
                ),
            ),
            # door sensors
            vol.Optional(
                str(Config.DOOR_SENSORS),
                default=user_input.get(Config.DOOR_SENSORS, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    include_entities=list(door_sensors), multiple=True
                ),
            ),
            # required on entities
            vol.Optional(
                str(Config.REQUIRED_ON_ENTITIES),
                default=user_input.get(Config.REQUIRED_ON_ENTITIES, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    include_entities=list(conditional_entities), multiple=True
                ),
            ),
            # required off entities
            vol.Optional(
                str(Config.REQUIRED_OFF_ENTITIES),
                default=user_input.get(Config.REQUIRED_OFF_ENTITIES, vol.UNDEFINED),
            ): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    include_entities=list(conditional_entities), multiple=True
                ),
            ),
        }
    )


# #### Internal functions ####


def _existing_controlled_entities(hass: HomeAssistant):
    return [
        entry.data.get(Config.CONTROLLED_ENTITY)
        for entry in hass.config_entries.async_entries(DOMAIN)
    ]
