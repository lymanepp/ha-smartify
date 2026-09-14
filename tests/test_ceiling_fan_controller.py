from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartify.ceiling_fan_controller import (
    CeilingFanController,
    MyEvent,
)
from custom_components.smartify.const import Config


@pytest.mark.asyncio
async def test_high_ssi_increases_speed(
    hass: HomeAssistant,
):
    hass.states.async_set(
        "sensor.temperature",
        82,
    )

    hass.states.async_set(
        "sensor.humidity",
        80,
    )

    hass.states.async_set(
        "fan.family_room",
        "on",
        {
            "percentage": 0,
        },
    )

    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.CONTROLLED_ENTITY: "fan.family_room",
            Config.TEMP_SENSOR: "sensor.temperature",
            Config.HUMIDITY_SENSOR: "sensor.humidity",
            Config.SSI_MIN: 81,
            Config.SSI_MAX: 91,
            Config.SPEED_MIN: 0,
            Config.SPEED_MAX: 100,
        },
    )

    controller = CeilingFanController(
        hass,
        entry,
    )

    controller.async_service_call = AsyncMock()

    await controller.async_setup(hass)

    await controller.on_state_change(hass.states.get("sensor.temperature"))

    controller.async_service_call.assert_called()

    controller.async_unload()


@pytest.mark.asyncio
async def test_attribute_only_percentage_change_processed(
    hass: HomeAssistant,
):
    hass.states.async_set(
        "sensor.temperature",
        75,
    )

    hass.states.async_set(
        "sensor.humidity",
        50,
    )

    hass.states.async_set(
        "fan.family_room",
        "on",
        {
            "percentage": 25,
        },
    )

    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.CONTROLLED_ENTITY: "fan.family_room",
            Config.TEMP_SENSOR: "sensor.temperature",
            Config.HUMIDITY_SENSOR: "sensor.humidity",
            Config.SSI_MIN: 81,
            Config.SSI_MAX: 91,
            Config.SPEED_MIN: 0,
            Config.SPEED_MAX: 100,
        },
    )

    controller = CeilingFanController(
        hass,
        entry,
    )

    controller.async_service_call = AsyncMock()

    await controller.async_setup(hass)

    old_state = hass.states.get("fan.family_room")

    hass.states.async_set(
        "fan.family_room",
        "on",
        {
            "percentage": 50,
        },
    )

    new_state = hass.states.get("fan.family_room")

    await controller._on_state_change(
        old_state,
        new_state,
    )

    controller.async_service_call.assert_called()

    controller.async_unload()


@pytest.mark.asyncio
async def test_setup_registers_poll_timer(
    hass: HomeAssistant,
):
    """Ceiling fan setup must register a recurring poll (item 6).

    The poll registration adds an unsubscriber beyond the base state listener;
    this guards the setup path and the corrected debug log context.
    """
    hass.states.async_set("sensor.temperature", 75)
    hass.states.async_set("sensor.humidity", 50)
    hass.states.async_set("fan.family_room", "off", {"percentage": 0})

    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.CONTROLLED_ENTITY: "fan.family_room",
            Config.TEMP_SENSOR: "sensor.temperature",
            Config.HUMIDITY_SENSOR: "sensor.humidity",
            Config.SSI_MIN: 81,
            Config.SSI_MAX: 91,
            Config.SPEED_MIN: 0,
            Config.SPEED_MAX: 100,
        },
    )

    controller = CeilingFanController(hass, entry)
    controller.async_service_call = AsyncMock()

    await controller.async_setup(hass)

    # Base registers the state listener; this controller adds the poll timer.
    assert len(controller._unsubscribers) >= 2

    controller.async_unload()

    # All unsubscribers (state listener + poll timer) are cleaned up on unload.
    assert controller._unsubscribers == []


@pytest.mark.asyncio
async def test_diagnostics_explain_quantized_auto_speed(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    hass.states.async_set("sensor.temperature", 78)
    hass.states.async_set("sensor.humidity", 60)
    hass.states.async_set(
        "fan.family_room",
        "on",
        {
            "percentage": 50,
            "percentage_step": 25,
        },
    )

    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.CONTROLLED_ENTITY: "fan.family_room",
            Config.TEMP_SENSOR: "sensor.temperature",
            Config.HUMIDITY_SENSOR: "sensor.humidity",
            Config.SSI_MIN: 81,
            Config.SSI_MAX: 91,
            Config.SPEED_MIN: 25,
            Config.SPEED_MAX: 75,
        },
    )

    monkeypatch.setattr(
        "custom_components.smartify.ceiling_fan_controller.summer_simmer_index",
        lambda *_: 86.7,
    )
    monkeypatch.setattr(
        "custom_components.smartify.ceiling_fan_controller.extrapolate_value",
        lambda *_args, **_kwargs: 57.0,
    )

    controller = CeilingFanController(hass, entry)
    controller.async_service_call = AsyncMock()

    await controller.async_setup(hass)

    diagnostics = controller.diagnostic_attributes
    assert diagnostics["reason"] == (
        "AUTO: SSI 86.7 maps to 57.0%; target is 50% after 25% "
        "fan-step quantization."
    )
    assert diagnostics["ssi"] == 86.7
    assert diagnostics["calculated_speed"] == 57.0
    assert diagnostics["target_speed"] == 50
    assert diagnostics["observed_speed"] == 50
    assert diagnostics["speed_step"] == 25
    assert diagnostics["required_satisfied"] is True

    controller.async_unload()


@pytest.mark.asyncio
async def test_diagnostics_explain_required_condition_block(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    hass.states.async_set("sensor.temperature", 78)
    hass.states.async_set("sensor.humidity", 60)
    hass.states.async_set("binary_sensor.occupancy", "off")
    hass.states.async_set(
        "fan.family_room",
        "off",
        {
            "percentage": 0,
            "percentage_step": 25,
        },
    )

    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.CONTROLLED_ENTITY: "fan.family_room",
            Config.TEMP_SENSOR: "sensor.temperature",
            Config.HUMIDITY_SENSOR: "sensor.humidity",
            Config.SSI_MIN: 81,
            Config.SSI_MAX: 91,
            Config.SPEED_MIN: 25,
            Config.SPEED_MAX: 75,
            Config.REQUIRED_ON_ENTITIES: ["binary_sensor.occupancy"],
        },
    )

    monkeypatch.setattr(
        "custom_components.smartify.ceiling_fan_controller.summer_simmer_index",
        lambda *_: 86.7,
    )
    monkeypatch.setattr(
        "custom_components.smartify.ceiling_fan_controller.extrapolate_value",
        lambda *_args, **_kwargs: 57.0,
    )

    controller = CeilingFanController(hass, entry)
    controller.async_service_call = AsyncMock()

    await controller.async_setup(hass)

    diagnostics = controller.diagnostic_attributes
    assert diagnostics["reason"] == (
        "BLOCKED: binary_sensor.occupancy must be on but is off; target speed is 0%."
    )
    assert diagnostics["target_speed"] == 0
    assert diagnostics["required_satisfied"] is False

    controller.async_unload()


@pytest.mark.asyncio
async def test_same_speed_decision_refreshes_live_diagnostics(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    hass.states.async_set("sensor.temperature", 78)
    hass.states.async_set("sensor.humidity", 60)
    hass.states.async_set(
        "fan.family_room",
        "on",
        {"percentage": 50, "percentage_step": 25},
    )

    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.CONTROLLED_ENTITY: "fan.family_room",
            Config.TEMP_SENSOR: "sensor.temperature",
            Config.HUMIDITY_SENSOR: "sensor.humidity",
            Config.SSI_MIN: 81,
            Config.SSI_MAX: 91,
            Config.SPEED_MIN: 25,
            Config.SPEED_MAX: 75,
        },
    )

    values = {"ssi": 86.7, "speed": 57.0}
    monkeypatch.setattr(
        "custom_components.smartify.ceiling_fan_controller.summer_simmer_index",
        lambda *_: values["ssi"],
    )
    monkeypatch.setattr(
        "custom_components.smartify.ceiling_fan_controller.extrapolate_value",
        lambda *_args, **_kwargs: values["speed"],
    )

    controller = CeilingFanController(hass, entry)
    controller.async_service_call = AsyncMock()
    await controller.async_setup(hass)
    first_snapshot = controller.diagnostic_attributes

    values.update(ssi=86.9, speed=59.0)
    await controller.fire_event(MyEvent.REFRESH)

    assert controller.diagnostic_attributes != first_snapshot
    assert controller.diagnostic_attributes["ssi"] == 86.9
    assert controller.diagnostic_attributes["calculated_speed"] == 59.0
    assert controller.diagnostic_attributes["target_speed"] == 50
    controller.async_unload()
