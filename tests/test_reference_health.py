"""Tests for Smartify reference-health reporting."""

import logging
from unittest.mock import patch

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


def test_missing_reference_creates_repair(hass, caplog):
    """A persistent missing reference creates an actionable Repairs issue."""
    controller = LightController(
        hass,
        _light_entry(
            "light.test_light",
            **{Config.TRIGGER_ENTITY: "binary_sensor.missing_motion"},
        ),
    )
    hass.states.async_set("light.test_light", STATE_OFF)

    with (
        patch(
            "custom_components.smartify.smartify_controller.async_create_issue"
        ) as create,
        caplog.at_level(logging.ERROR, logger="custom_components.smartify"),
    ):
        controller._validate_references()

    create.assert_called_once()
    kwargs = create.call_args.kwargs
    assert kwargs["translation_key"] == "missing_reference"
    assert (
        kwargs["translation_placeholders"]["entity_id"]
        == "binary_sensor.missing_motion"
    )
    assert "binary_sensor.missing_motion" in caplog.text
    assert "does not exist in Home Assistant's state machine" in caplog.text


def test_unavailable_reference_logs_without_repair(hass, caplog):
    """An unavailable dependency is a runtime warning, not a Repairs issue."""
    controller = LightController(
        hass,
        _light_entry(
            "light.test_light",
            **{Config.TRIGGER_ENTITY: "binary_sensor.motion"},
        ),
    )
    hass.states.async_set("light.test_light", STATE_OFF)
    hass.states.async_set("binary_sensor.motion", STATE_UNAVAILABLE)

    with (
        patch(
            "custom_components.smartify.smartify_controller.async_create_issue"
        ) as create,
        caplog.at_level(logging.WARNING, logger="custom_components.smartify"),
    ):
        controller._validate_references()

    create.assert_not_called()
    assert "binary_sensor.motion" in caplog.text
    assert "is unavailable" in caplog.text


def test_reference_recovery_deletes_repair(hass, caplog):
    """A recovered dependency removes its Repairs issue and logs recovery once."""
    controller = LightController(
        hass,
        _light_entry(
            "light.test_light",
            **{Config.TRIGGER_ENTITY: "binary_sensor.motion"},
        ),
    )
    hass.states.async_set("light.test_light", STATE_OFF)
    controller._validate_references()

    hass.states.async_set("binary_sensor.motion", STATE_OFF)
    with (
        patch(
            "custom_components.smartify.smartify_controller.async_delete_issue"
        ) as delete,
        caplog.at_level(logging.INFO, logger="custom_components.smartify"),
    ):
        controller._validate_references()

    delete.assert_called_once()
    assert "recovered from missing" in caplog.text


def test_wrong_controlled_entity_domain_creates_repair(hass, caplog):
    """A wrong controlled-entity domain creates an actionable Repairs issue."""
    controller = LightController(hass, _light_entry("switch.test_light"))
    hass.states.async_set("switch.test_light", STATE_OFF)

    with (
        patch(
            "custom_components.smartify.smartify_controller.async_create_issue"
        ) as create,
        caplog.at_level(logging.ERROR, logger="custom_components.smartify"),
    ):
        controller._validate_references()

    create.assert_called_once()
    kwargs = create.call_args.kwargs
    assert kwargs["translation_key"] == "wrong_reference_domain"
    assert kwargs["translation_placeholders"]["expected_domain"] == "light"
    assert "must be in the 'light' domain" in caplog.text
