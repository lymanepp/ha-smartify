from unittest.mock import AsyncMock

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartify.const import Config
from custom_components.smartify.exhaust_fan_controller import (
    ExhaustFanController,
    MyEvent,
)


@pytest.mark.asyncio
async def test_high_humidity_turns_fan_on(
    hass: HomeAssistant,
):
    hass.states.async_set(
        "sensor.temp",
        75,
    )

    hass.states.async_set(
        "sensor.humidity",
        80,
    )

    hass.states.async_set(
        "sensor.ref_temp",
        70,
    )

    hass.states.async_set(
        "sensor.ref_humidity",
        50,
    )

    hass.states.async_set(
        "fan.bathroom",
        STATE_OFF,
    )

    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.CONTROLLED_ENTITY: "fan.bathroom",
            Config.TEMP_SENSOR: "sensor.temp",
            Config.HUMIDITY_SENSOR: "sensor.humidity",
            Config.REFERENCE_TEMP_SENSOR: "sensor.ref_temp",
            Config.REFERENCE_HUMIDITY_SENSOR: "sensor.ref_humidity",
            Config.RISING_THRESHOLD: 2.0,
            Config.FALLING_THRESHOLD: 0.5,
        },
    )

    controller = ExhaustFanController(
        hass,
        entry,
    )

    controller.async_service_call = AsyncMock()

    await controller.async_setup(hass)

    await controller.on_state_change(hass.states.get("sensor.humidity"))

    controller.async_service_call.assert_called()

    controller.async_unload()


@pytest.mark.asyncio
async def test_low_humidity_turns_fan_off(
    hass: HomeAssistant,
):
    hass.states.async_set(
        "sensor.temp",
        70,
    )

    hass.states.async_set(
        "sensor.humidity",
        45,
    )

    hass.states.async_set(
        "sensor.ref_temp",
        70,
    )

    hass.states.async_set(
        "sensor.ref_humidity",
        50,
    )

    hass.states.async_set(
        "fan.bathroom",
        STATE_ON,
    )

    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.CONTROLLED_ENTITY: "fan.bathroom",
            Config.TEMP_SENSOR: "sensor.temp",
            Config.HUMIDITY_SENSOR: "sensor.humidity",
            Config.REFERENCE_TEMP_SENSOR: "sensor.ref_temp",
            Config.REFERENCE_HUMIDITY_SENSOR: "sensor.ref_humidity",
            Config.RISING_THRESHOLD: 2.0,
            Config.FALLING_THRESHOLD: 0.5,
        },
    )

    controller = ExhaustFanController(
        hass,
        entry,
    )

    controller.async_service_call = AsyncMock()

    await controller.async_setup(hass)

    await controller.on_state_change(hass.states.get("sensor.humidity"))

    controller.async_service_call.assert_called()

    controller.async_unload()


@pytest.mark.asyncio
async def test_invalid_humidity_does_not_crash(
    hass: HomeAssistant,
):
    hass.states.async_set(
        "sensor.temp",
        70,
    )

    hass.states.async_set(
        "sensor.humidity",
        "garbage",
    )

    hass.states.async_set(
        "sensor.ref_temp",
        70,
    )

    hass.states.async_set(
        "sensor.ref_humidity",
        50,
    )

    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.CONTROLLED_ENTITY: "fan.bathroom",
            Config.TEMP_SENSOR: "sensor.temp",
            Config.HUMIDITY_SENSOR: "sensor.humidity",
            Config.REFERENCE_TEMP_SENSOR: "sensor.ref_temp",
            Config.REFERENCE_HUMIDITY_SENSOR: "sensor.ref_humidity",
            Config.RISING_THRESHOLD: 2.0,
            Config.FALLING_THRESHOLD: 0.5,
        },
    )

    controller = ExhaustFanController(
        hass,
        entry,
    )

    controller.async_service_call = AsyncMock()

    await controller.async_setup(hass)

    await controller.on_state_change(hass.states.get("sensor.humidity"))

    controller.async_service_call.assert_not_called()

    controller.async_unload()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("fan_state", "reason_prefix"),
    [
        (STATE_ON, "AUTO ON:"),
        (STATE_OFF, "AUTO OFF:"),
    ],
)
async def test_diagnostics_explain_hysteresis_hold(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
    fan_state: str,
    reason_prefix: str,
):
    hass.states.async_set("sensor.temp", 75)
    hass.states.async_set("sensor.humidity", 60)
    hass.states.async_set("sensor.ref_temp", 75)
    hass.states.async_set("sensor.ref_humidity", 50)
    hass.states.async_set("fan.bathroom", fan_state)

    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.CONTROLLED_ENTITY: "fan.bathroom",
            Config.TEMP_SENSOR: "sensor.temp",
            Config.HUMIDITY_SENSOR: "sensor.humidity",
            Config.REFERENCE_TEMP_SENSOR: "sensor.ref_temp",
            Config.REFERENCE_HUMIDITY_SENSOR: "sensor.ref_humidity",
            Config.RISING_THRESHOLD: 2.0,
            Config.FALLING_THRESHOLD: 0.5,
        },
    )

    monkeypatch.setattr(
        "custom_components.smartify.exhaust_fan_controller.absolute_humidity",
        lambda _temp, humidity: 12.3 if humidity == 60 else 11.0,
    )

    controller = ExhaustFanController(hass, entry)
    controller.async_service_call = AsyncMock()

    await controller.async_setup(hass)

    diagnostics = controller.diagnostic_attributes
    assert diagnostics["reason"].startswith(reason_prefix)
    assert diagnostics["humidity_difference"] == 1.3
    assert diagnostics["rising_threshold"] == 2.0
    assert diagnostics["falling_threshold"] == 0.5
    assert diagnostics["observed_mode"] == fan_state
    assert diagnostics["target_mode"] == fan_state
    controller.async_service_call.assert_not_called()

    controller.async_unload()


@pytest.mark.asyncio
async def test_same_hysteresis_decision_refreshes_live_diagnostics(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    hass.states.async_set("sensor.temp", 75)
    hass.states.async_set("sensor.humidity", 60)
    hass.states.async_set("sensor.ref_temp", 75)
    hass.states.async_set("sensor.ref_humidity", 50)
    hass.states.async_set("fan.bathroom", STATE_ON)

    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.CONTROLLED_ENTITY: "fan.bathroom",
            Config.TEMP_SENSOR: "sensor.temp",
            Config.HUMIDITY_SENSOR: "sensor.humidity",
            Config.REFERENCE_TEMP_SENSOR: "sensor.ref_temp",
            Config.REFERENCE_HUMIDITY_SENSOR: "sensor.ref_humidity",
            Config.RISING_THRESHOLD: 2.0,
            Config.FALLING_THRESHOLD: 0.5,
        },
    )

    monkeypatch.setattr(
        "custom_components.smartify.exhaust_fan_controller.absolute_humidity",
        lambda _temp, humidity: {50: 11.0, 60: 12.3, 61: 12.5}[humidity],
    )

    controller = ExhaustFanController(hass, entry)
    controller.async_service_call = AsyncMock()
    await controller.async_setup(hass)
    first_snapshot = controller.diagnostic_attributes

    controller._humidity = (61, "%")
    await controller.fire_event(MyEvent.REFRESH)

    assert controller.diagnostic_attributes != first_snapshot
    assert controller.diagnostic_attributes["local_humidity"] == 61
    assert controller.diagnostic_attributes["humidity_difference"] == 1.5
    assert controller.diagnostic_attributes["target_mode"] == STATE_ON
    controller.async_unload()
