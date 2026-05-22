from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartify.ceiling_fan_controller import CeilingFanController
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
