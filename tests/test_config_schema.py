"""Tests for YAML configuration schema validation."""

import pytest
import voluptuous as vol

from custom_components.smartify.config_schema import CONFIG_SCHEMA
from custom_components.smartify.const import DOMAIN, Config


def test_full_yaml_config_validates():
    """All four controller types can be defined in YAML at once."""
    raw = {
        DOMAIN: {
            "ceiling_fan": [
                {
                    Config.CONTROLLED_ENTITY: "fan.office_fan",
                    Config.TEMP_SENSOR: "sensor.office_temperature",
                    Config.HUMIDITY_SENSOR: "sensor.office_humidity",
                    Config.SSI_MIN: 81,
                    Config.SSI_MAX: 91,
                    Config.SPEED_MIN: 25,
                    Config.SPEED_MAX: 100,
                }
            ],
            "exhaust_fan": [
                {
                    Config.CONTROLLED_ENTITY: "fan.bathroom_fan",
                    Config.TEMP_SENSOR: "sensor.bathroom_temperature",
                    Config.HUMIDITY_SENSOR: "sensor.bathroom_humidity",
                    Config.REFERENCE_TEMP_SENSOR: "sensor.indoor_temperature",
                    Config.REFERENCE_HUMIDITY_SENSOR: "sensor.indoor_humidity",
                }
            ],
            "light": [
                {
                    Config.CONTROLLED_ENTITY: "light.office_light",
                    Config.TRIGGER_ENTITY: "binary_sensor.office_occupancy",
                }
            ],
            "occupancy": [
                {
                    Config.SENSOR_NAME: "Office Occupancy",
                    Config.TRIGGER_ENTITIES: ["binary_sensor.office_motion"],
                    Config.DECAY_MINUTES: 10,
                }
            ],
        }
    }

    validated = CONFIG_SCHEMA(raw)

    exhaust = validated[DOMAIN]["exhaust_fan"][0]
    assert exhaust[Config.RISING_THRESHOLD] == 2.0
    assert exhaust[Config.FALLING_THRESHOLD] == 0.5
    assert exhaust[Config.MANUAL_CONTROL_MINUTES] == 15.0


def test_missing_controller_types_default_to_empty_lists():
    """Omitted controller-type keys default to an empty list, not an error."""
    validated = CONFIG_SCHEMA({DOMAIN: {}})

    assert validated[DOMAIN]["ceiling_fan"] == []
    assert validated[DOMAIN]["exhaust_fan"] == []
    assert validated[DOMAIN]["light"] == []
    assert validated[DOMAIN]["occupancy"] == []


def test_occupancy_requires_trigger_or_sustain():
    """Occupancy needs at least one trigger or sustain entity."""
    raw = {
        DOMAIN: {
            "occupancy": [
                {
                    Config.SENSOR_NAME: "Empty Room",
                }
            ],
        }
    }

    with pytest.raises(vol.Invalid):
        CONFIG_SCHEMA(raw)


def test_occupancy_trigger_only_requires_decay_minutes():
    """Trigger-only occupancy must set a decay time, same as the options flow."""
    raw = {
        DOMAIN: {
            "occupancy": [
                {
                    Config.SENSOR_NAME: "Hallway",
                    Config.TRIGGER_ENTITIES: ["binary_sensor.hallway_motion"],
                }
            ],
        }
    }

    with pytest.raises(vol.Invalid):
        CONFIG_SCHEMA(raw)


def test_occupancy_sustain_only_does_not_require_decay_minutes():
    """Sustain-only occupancy is valid without a decay time."""
    raw = {
        DOMAIN: {
            "occupancy": [
                {
                    Config.SENSOR_NAME: "Office",
                    Config.SUSTAIN_ENTITIES: ["binary_sensor.office_mmwave"],
                }
            ],
        }
    }

    validated = CONFIG_SCHEMA(raw)
    assert validated[DOMAIN]["occupancy"][0][Config.SENSOR_NAME] == "Office"


def test_light_illuminance_sensor_and_cutoff_are_inclusive():
    """Illuminance sensor and cutoff must be configured together."""
    raw = {
        DOMAIN: {
            "light": [
                {
                    Config.CONTROLLED_ENTITY: "light.office_light",
                    Config.ILLUMINANCE_SENSOR: "sensor.office_illuminance",
                }
            ],
        }
    }

    with pytest.raises(vol.Invalid):
        CONFIG_SCHEMA(raw)


def test_ceiling_fan_missing_required_field_is_rejected():
    """Required fields (e.g. humidity_sensor) cannot be omitted."""
    raw = {
        DOMAIN: {
            "ceiling_fan": [
                {
                    Config.CONTROLLED_ENTITY: "fan.office_fan",
                    Config.TEMP_SENSOR: "sensor.office_temperature",
                    Config.SSI_MIN: 81,
                    Config.SSI_MAX: 91,
                    Config.SPEED_MIN: 25,
                    Config.SPEED_MAX: 100,
                }
            ],
        }
    }

    with pytest.raises(vol.Invalid):
        CONFIG_SCHEMA(raw)


def test_optional_name_and_unique_id_accepted_on_entity_based_types():
    """Light/ceiling_fan/exhaust_fan accept optional 'name' and 'unique_id'
    overrides alongside their normal fields.
    """
    raw = {
        DOMAIN: {
            "light": [
                {
                    Config.NAME: "Closet Light",
                    Config.UNIQUE_ID: "closet_light_v1",
                    Config.CONTROLLED_ENTITY: "light.closet_light",
                    Config.AUTO_OFF_MINUTES: 5,
                }
            ],
        }
    }

    validated = CONFIG_SCHEMA(raw)
    entry = validated[DOMAIN]["light"][0]
    assert entry[Config.NAME] == "Closet Light"
    assert entry[Config.UNIQUE_ID] == "closet_light_v1"


def test_optional_unique_id_accepted_on_occupancy():
    """Occupancy accepts 'unique_id' too, even though it has no 'name'
    override (its required sensor_name already serves as the title).
    """
    raw = {
        DOMAIN: {
            "occupancy": [
                {
                    Config.UNIQUE_ID: "office_occupancy_v1",
                    Config.SENSOR_NAME: "Office Occupancy",
                    Config.SUSTAIN_ENTITIES: ["binary_sensor.office_mmwave"],
                }
            ],
        }
    }

    validated = CONFIG_SCHEMA(raw)
    entry = validated[DOMAIN]["occupancy"][0]
    assert entry[Config.UNIQUE_ID] == "office_occupancy_v1"
