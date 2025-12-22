"""Constants for smartify."""

import enum
from logging import Logger, getLogger
from typing import Final

from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN

_LOGGER: Logger = getLogger(__package__)

DOMAIN: Final = "smartify"
NAME: Final = "Smartify"

IGNORE_STATES: Final = (STATE_UNKNOWN, STATE_UNAVAILABLE)
ON_OFF_STATES: Final = (STATE_ON, STATE_OFF)

GRAMS_PER_CUBIC_METER: Final = "g/m³"

DEFAULT_CEILING_SSI_MIN_FAHRENHEIT: Final = 81.0
DEFAULT_CEILING_SSI_MAX_FAHRENHEIT: Final = 91.0

DEFAULT_EXHAUST_FALLING_THRESHOLD: Final = 0.5
DEFAULT_EXHAUST_RISING_THRESHOLD: Final = 2.0
DEFAULT_EXHAUST_MANUAL_MINUTES: Final = 15.0


class ControllerType(enum.StrEnum):
    """Supported controller types."""

    CEILING_FAN = "ceiling_fan"
    EXHAUST_FAN = "exhaust_fan"
    LIGHT = "light"
    OCCUPANCY = "occupancy"


class Config(enum.StrEnum):
    """Configuration values."""

    AUTO_OFF_MINUTES = "auto_off_minutes"
    BRIGHTNESS_PCT = "brightness_pct"
    CONTROLLED_ENTITY = "controlled_entity"
    CONTROLLER_TYPE = "type"
    DOOR_SENSORS = "door_sensors"
    FALLING_THRESHOLD = "falling_threshold"
    HUMIDITY_SENSOR = "humidity_sensor"
    ILLUMINANCE_CUTOFF = "illuminance_cutoff"
    ILLUMINANCE_SENSOR = "illuminance_sensor"
    MANUAL_CONTROL_MINUTES = "manual_control_minutes"
    MOTION_SENSORS = "motion_sensors"
    MOTION_OFF_MINUTES = "motion_off_minutes"
    OTHER_ENTITIES = "other_entities"
    REFERENCE_HUMIDITY_SENSOR = "reference_humidity_sensor"
    REFERENCE_TEMP_SENSOR = "reference_temp_sensor"
    REQUIRED_OFF_ENTITIES = "required_off_entities"
    REQUIRED_ON_ENTITIES = "required_on_entities"
    RISING_THRESHOLD = "rising_threshold"
    SENSOR_NAME = "sensor_name"
    SPEED_MAX = "speed_max"
    SPEED_MIN = "speed_min"
    SSI_MAX = "ssi_max"
    SSI_MIN = "ssi_min"
    TEMP_SENSOR = "temp_sensor"
    TRIGGER_ENTITY = "trigger_entity"
