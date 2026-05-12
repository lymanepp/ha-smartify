from unittest.mock import MagicMock

from homeassistant.const import EntityCategory, STATE_ON

from custom_components.smartify.const import Config
from custom_components.smartify.occupancy_controller import OccupancyController
from custom_components.smartify.sensor import (
    SmartifyControllerStateSensor,
    CONTROLLER_STATE_DESCRIPTION,
)


def _entry(data: dict | None = None):
    entry = MagicMock()
    entry.entry_id = "entry-123"
    entry.title = "Office Occupancy"
    entry.data = data or {}
    entry.options = {}
    return entry


def test_occupancy_state_sensor_uses_diagnostic_suffix(hass):
    controller = OccupancyController(
        hass,
        _entry({Config.SUSTAIN_ENTITIES: ["binary_sensor.office_mmwave"]}),
    )

    entity = SmartifyControllerStateSensor(controller, CONTROLLER_STATE_DESCRIPTION)

    assert entity.unique_id == "entry-123_controller_state"
    assert entity.name == "State"
    assert entity.entity_category == EntityCategory.DIAGNOSTIC
    assert entity.has_entity_name is True


def test_occupancy_state_sensor_native_value_and_attributes(hass):
    trigger = "binary_sensor.office_pir"
    sustain = "binary_sensor.office_mmwave"
    required = "input_boolean.occupancy_enabled"
    hass.states.async_set(trigger, STATE_ON)
    hass.states.async_set(sustain, STATE_ON)
    hass.states.async_set(required, STATE_ON)

    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.SUSTAIN_ENTITIES: [sustain],
                Config.REQUIRED_ON_ENTITIES: [required],
            }
        ),
    )
    entity = SmartifyControllerStateSensor(controller, CONTROLLER_STATE_DESCRIPTION)

    assert entity.native_value == "unoccupied"
    assert entity.extra_state_attributes["strategy"] == "trigger_and_sustain"
    assert entity.extra_state_attributes["active_trigger_entities"] == [trigger]
    assert entity.extra_state_attributes["active_sustain_entities"] == [sustain]
    assert entity.extra_state_attributes["required_satisfied"] is True
