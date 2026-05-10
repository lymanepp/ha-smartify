import pytest

from homeassistant.core import HomeAssistant
from homeassistant.const import STATE_ON, STATE_OFF

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartify.occupancy_controller import (
    OccupancyController,
    MyState,
    MyEvent,
)
from custom_components.smartify.const import Config


@pytest.mark.asyncio
async def test_motion_transitions_to_motion(hass: HomeAssistant):
    hass.states.async_set(
        "binary_sensor.motion",
        STATE_ON,
    )

    entry = MockConfigEntry()

    controller = OccupancyController(hass, entry)

    await controller.fire_event(MyEvent.MOTION)

    assert controller.state == MyState.MOTION


@pytest.mark.asyncio
async def test_closed_door_enters_wasp(hass: HomeAssistant):
    hass.states.async_set(
        "binary_sensor.door",
        STATE_ON,
    )

    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.DOOR_SENSORS: [
                "binary_sensor.door",
            ],
        },
    )

    controller = OccupancyController(hass, entry)

    await controller.fire_event(MyEvent.MOTION)

    assert controller.state == MyState.WASP_IN_BOX


@pytest.mark.asyncio
async def test_required_entity_missing_prevents_occupancy(hass: HomeAssistant):
    hass.states.async_set(
        "binary_sensor.required",
        STATE_OFF,
    )

    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.REQUIRED_ON_ENTITIES: [
                "binary_sensor.required",
            ],
        },
    )

    controller = OccupancyController(hass, entry)

    await controller.fire_event(MyEvent.MOTION)

    assert controller.state == MyState.UNOCCUPIED
