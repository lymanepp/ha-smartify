from unittest.mock import AsyncMock

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartify.const import Config
from custom_components.smartify.exhaust_fan_controller import (
    ExhaustFanController,
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
