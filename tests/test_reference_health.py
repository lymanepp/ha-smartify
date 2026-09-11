"""Tests for Smartify reference-health diagnostics."""

import logging

from homeassistant.const import STATE_OFF, STATE_UNAVAILABLE

from custom_components.smartify.const import Config, ControllerType
from custom_components.smartify.entry_types import YamlControllerEntry
from custom_components.smartify.light_controller import LightController


def _light_entry(controlled_entity: str, **extra) -> YamlControllerEntry:
    """Build a minimal YAML light entry."""
    data = {
        Config.CONTROLLER_TYPE: ControllerType.LIGHT,
        Config.CONTROLLED_ENTITY: controlled_entity,
        **extra,
    }
    return YamlControllerEntry(
        entry_id="yaml_test_light",
        title="Test Light",
        data=data,
    )


def test_missing_reference_is_reported(hass, caplog):
    """A persistent missing reference is an actionable configuration error."""
    controller = LightController(
        hass,
        _light_entry(
            "light.test_light",
            **{Config.TRIGGER_ENTITY: "binary_sensor.missing_motion"},
        ),
    )
    hass.states.async_set("light.test_light", STATE_OFF)

    with caplog.at_level(logging.ERROR, logger="custom_components.smartify"):
        controller._validate_references()

    assert controller.diagnostic_attributes["healthy"] is False
    assert controller.diagnostic_attributes["missing_entities"] == [
        "binary_sensor.missing_motion"
    ]
    assert controller.diagnostic_attributes["reference_roles"][
        "binary_sensor.missing_motion"
    ] == ["trigger_entity"]
    assert "binary_sensor.missing_motion" in caplog.text
    assert "does not exist in Home Assistant's state machine" in caplog.text


def test_unavailable_reference_is_reported(hass, caplog):
    """An unavailable dependency is reported separately from a missing one."""
    controller = LightController(
        hass,
        _light_entry(
            "light.test_light",
            **{Config.TRIGGER_ENTITY: "binary_sensor.motion"},
        ),
    )
    hass.states.async_set("light.test_light", STATE_OFF)
    hass.states.async_set("binary_sensor.motion", STATE_UNAVAILABLE)

    with caplog.at_level(logging.WARNING, logger="custom_components.smartify"):
        controller._validate_references()

    assert controller.diagnostic_attributes["unavailable_entities"] == [
        "binary_sensor.motion"
    ]
    assert "binary_sensor.motion" in caplog.text
    assert "is unavailable" in caplog.text


def test_reference_recovery_clears_problem(hass, caplog):
    """A recovered dependency clears diagnostics and logs recovery once."""
    controller = LightController(
        hass,
        _light_entry(
            "light.test_light",
            **{Config.TRIGGER_ENTITY: "binary_sensor.motion"},
        ),
    )
    hass.states.async_set("light.test_light", STATE_OFF)

    controller._validate_references()
    assert controller.diagnostic_attributes["healthy"] is False

    hass.states.async_set("binary_sensor.motion", STATE_OFF)
    with caplog.at_level(logging.INFO, logger="custom_components.smartify"):
        controller._validate_references()

    assert controller.diagnostic_attributes["healthy"] is True
    assert controller.diagnostic_attributes["reference_problems"] == {}
    assert "recovered from missing" in caplog.text


def test_wrong_controlled_entity_domain_is_reported(hass, caplog):
    """A light controller cannot silently point at a non-light entity."""
    controller = LightController(hass, _light_entry("switch.test_light"))
    hass.states.async_set("switch.test_light", STATE_OFF)

    with caplog.at_level(logging.ERROR, logger="custom_components.smartify"):
        controller._validate_references()

    assert controller.diagnostic_attributes["wrong_domain_entities"] == [
        "switch.test_light"
    ]
    assert controller.diagnostic_attributes["reference_problems"] == {
        "switch.test_light": "wrong_domain:light"
    }
    assert "must be in the 'light' domain" in caplog.text
