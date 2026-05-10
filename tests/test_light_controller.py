from unittest.mock import AsyncMock

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartify.const import Config
from custom_components.smartify.light_controller import (
    LightController,
)


@pytest.mark.asyncio
async def test_required_on_entity_blocks_activation(
    hass: HomeAssistant,
):
    hass.states.async_set(
        "binary_sensor.motion",
        STATE_ON,
    )

    hass.states.async_set(
        "input_boolean.required",
        STATE_OFF,
    )

    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.CONTROLLED_ENTITY: "light.test",
            Config.TRIGGER_ENTITY: "binary_sensor.motion",
            Config.REQUIRED_ON_ENTITIES: [
                "input_boolean.required",
            ],
        },
    )

    controller = LightController(
        hass,
        entry,
    )

    controller.async_service_call = AsyncMock()

    await controller.async_setup(hass)

    await controller.on_state_change(hass.states.get("binary_sensor.motion"))

    controller.async_service_call.assert_not_called()

    controller.async_unload()


@pytest.mark.asyncio
async def test_invalid_illuminance_does_not_crash(
    hass: HomeAssistant,
):
    hass.states.async_set(
        "sensor.lux",
        "garbage",
    )

    hass.states.async_set(
        "binary_sensor.motion",
        STATE_ON,
    )

    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.CONTROLLED_ENTITY: "light.test",
            Config.TRIGGER_ENTITY: "binary_sensor.motion",
            Config.ILLUMINANCE_SENSOR: "sensor.lux",
            Config.ILLUMINANCE_CUTOFF: 10,
        },
    )

    controller = LightController(
        hass,
        entry,
    )

    controller.async_service_call = AsyncMock()

    await controller.async_setup(hass)

    await controller.on_state_change(hass.states.get("binary_sensor.motion"))

    controller.async_service_call.assert_not_called()

    controller.async_unload()
