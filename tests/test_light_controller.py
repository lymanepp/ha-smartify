from unittest.mock import AsyncMock

import pytest
from homeassistant.const import (
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    Platform,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartify.const import Config
from custom_components.smartify.light_controller import LightController, MyState


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


@pytest.mark.asyncio
async def test_diagnostics_explain_required_condition_block(hass: HomeAssistant):
    hass.states.async_set("light.test", STATE_OFF)
    hass.states.async_set("binary_sensor.motion", STATE_OFF)
    hass.states.async_set("input_boolean.required", STATE_OFF)

    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.CONTROLLED_ENTITY: "light.test",
            Config.TRIGGER_ENTITY: "binary_sensor.motion",
            Config.REQUIRED_ON_ENTITIES: ["input_boolean.required"],
        },
    )

    controller = LightController(hass, entry)
    controller.async_service_call = AsyncMock()
    await controller.async_setup(hass)

    hass.states.async_set("binary_sensor.motion", STATE_ON)
    await controller.on_state_change(hass.states.get("binary_sensor.motion"))

    diagnostics = controller.diagnostic_attributes
    assert diagnostics["reason"] == (
        "BLOCKED: input_boolean.required must be on but is off; trigger did not "
        "turn the light on."
    )
    assert diagnostics["required_satisfied"] is False
    assert diagnostics["target_mode"] == STATE_OFF
    controller.async_service_call.assert_not_called()

    controller.async_unload()


# These tests deliberately use Home Assistant state_changed events rather than
# calling on_state_change directly: unavailable/unknown/removed states reach a
# separate hook in SmartifyController, and must be tested through that listener.


def _make_light_controller(hass: HomeAssistant, **config) -> LightController:
    entry = MockConfigEntry(
        domain="smartify",
        data={
            Config.CONTROLLED_ENTITY: "light.test",
            Config.TRIGGER_ENTITY: "binary_sensor.home",
            **config,
        },
    )
    controller = LightController(hass, entry)
    controller.async_service_call = AsyncMock()
    return controller


async def _set_state(hass: HomeAssistant, entity_id: str, state: str) -> None:
    hass.states.async_set(entity_id, state)
    await hass.async_block_till_done()


async def _lose_state(
    hass: HomeAssistant, entity_id: str, failure: str | None
) -> None:
    if failure is None:
        hass.states.async_remove(entity_id)
    else:
        hass.states.async_set(entity_id, failure)
    await hass.async_block_till_done()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("requirement_key", "allowed", "blocked"),
    [
        (Config.REQUIRED_OFF_ENTITIES, STATE_OFF, STATE_ON),
        (Config.REQUIRED_ON_ENTITIES, STATE_ON, STATE_OFF),
    ],
    ids=["required_off_sleeping", "required_on_enabled"],
)
async def test_required_change_turns_automatic_light_off_and_restores(
    hass: HomeAssistant, requirement_key: str, allowed: str, blocked: str
):
    """Requirements are active gates, not merely checks on trigger activation."""
    hass.states.async_set("light.test", STATE_ON)
    hass.states.async_set("binary_sensor.home", STATE_ON)
    hass.states.async_set("binary_sensor.requirement", allowed)
    controller = _make_light_controller(
        hass, **{requirement_key: ["binary_sensor.requirement"]}
    )
    await controller.async_setup(hass)
    assert controller.state == MyState.ON
    controller.async_service_call.assert_not_called()

    await _set_state(hass, "binary_sensor.requirement", blocked)
    assert controller.state == MyState.OFF
    controller.async_service_call.assert_awaited_once_with(
        Platform.LIGHT, SERVICE_TURN_OFF, {}
    )
    assert controller.diagnostic_attributes["required_satisfied"] is False
    assert controller.diagnostic_attributes["target_mode"] == STATE_OFF

    # A real relay reports OFF after receiving the shutoff service request.
    await _set_state(hass, "light.test", STATE_OFF)
    controller.async_service_call.reset_mock()

    await _set_state(hass, "binary_sensor.requirement", allowed)
    assert controller.state == MyState.ON
    controller.async_service_call.assert_awaited_once_with(
        Platform.LIGHT, SERVICE_TURN_ON, {}
    )
    assert controller.diagnostic_attributes["required_satisfied"] is True
    controller.async_unload()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [STATE_UNAVAILABLE, STATE_UNKNOWN, None],
    ids=["unavailable", "unknown", "removed"],
)
@pytest.mark.parametrize(
    ("requirement_key", "allowed"),
    [
        (Config.REQUIRED_OFF_ENTITIES, STATE_OFF),
        (Config.REQUIRED_ON_ENTITIES, STATE_ON),
    ],
    ids=["required_off", "required_on"],
)
async def test_lost_requirement_turns_off_and_recovery_turns_on(
    hass: HomeAssistant, failure: str | None, requirement_key: str, allowed: str
):
    """A missing sensor must not leave an auto-controlled light ON."""
    hass.states.async_set("light.test", STATE_ON)
    hass.states.async_set("binary_sensor.home", STATE_ON)
    hass.states.async_set("binary_sensor.requirement", allowed)
    controller = _make_light_controller(
        hass, **{requirement_key: ["binary_sensor.requirement"]}
    )
    await controller.async_setup(hass)
    assert controller.state == MyState.ON

    await _lose_state(hass, "binary_sensor.requirement", failure)
    assert controller.state == MyState.OFF
    controller.async_service_call.assert_awaited_once_with(
        Platform.LIGHT, SERVICE_TURN_OFF, {}
    )
    assert controller.diagnostic_attributes["required_satisfied"] is False

    await _set_state(hass, "light.test", STATE_OFF)
    controller.async_service_call.reset_mock()
    await _set_state(hass, "binary_sensor.requirement", allowed)
    assert controller.state == MyState.ON
    controller.async_service_call.assert_awaited_once_with(
        Platform.LIGHT, SERVICE_TURN_ON, {}
    )
    controller.async_unload()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [STATE_UNAVAILABLE, STATE_UNKNOWN, None],
    ids=["unavailable", "unknown", "removed"],
)
async def test_lost_trigger_turns_automatic_light_off(
    hass: HomeAssistant, failure: str | None
):
    """A presence sensor loss must not hold automatic lighting ON."""
    hass.states.async_set("light.test", STATE_ON)
    hass.states.async_set("binary_sensor.home", STATE_ON)
    controller = _make_light_controller(hass)
    await controller.async_setup(hass)
    assert controller.state == MyState.ON

    await _lose_state(hass, "binary_sensor.home", failure)
    assert controller.state == MyState.OFF
    controller.async_service_call.assert_awaited_once_with(
        Platform.LIGHT, SERVICE_TURN_OFF, {}
    )

    await _set_state(hass, "light.test", STATE_OFF)
    controller.async_service_call.reset_mock()
    await _set_state(hass, "binary_sensor.home", STATE_ON)
    assert controller.state == MyState.ON
    controller.async_service_call.assert_awaited_once_with(
        Platform.LIGHT, SERVICE_TURN_ON, {}
    )
    controller.async_unload()


@pytest.mark.asyncio
async def test_multiple_requirements_must_all_recover(hass: HomeAssistant):
    hass.states.async_set("light.test", STATE_ON)
    hass.states.async_set("binary_sensor.home", STATE_ON)
    hass.states.async_set("binary_sensor.sleeping", STATE_OFF)
    hass.states.async_set("input_boolean.enabled", STATE_ON)
    controller = _make_light_controller(
        hass,
        **{
            Config.REQUIRED_OFF_ENTITIES: ["binary_sensor.sleeping"],
            Config.REQUIRED_ON_ENTITIES: ["input_boolean.enabled"],
        },
    )
    await controller.async_setup(hass)
    assert controller.state == MyState.ON

    await _set_state(hass, "binary_sensor.sleeping", STATE_ON)
    assert controller.state == MyState.OFF
    await _set_state(hass, "light.test", STATE_OFF)
    controller.async_service_call.reset_mock()

    await _set_state(hass, "input_boolean.enabled", STATE_OFF)
    await _set_state(hass, "binary_sensor.sleeping", STATE_OFF)
    assert controller.state == MyState.OFF
    controller.async_service_call.assert_not_called()

    await _set_state(hass, "input_boolean.enabled", STATE_ON)
    assert controller.state == MyState.ON
    controller.async_service_call.assert_awaited_once_with(
        Platform.LIGHT, SERVICE_TURN_ON, {}
    )
    controller.async_unload()


@pytest.mark.asyncio
async def test_required_recovery_does_not_turn_on_when_away(hass: HomeAssistant):
    hass.states.async_set("light.test", STATE_OFF)
    hass.states.async_set("binary_sensor.home", STATE_OFF)
    hass.states.async_set("binary_sensor.sleeping", STATE_ON)
    controller = _make_light_controller(
        hass, **{Config.REQUIRED_OFF_ENTITIES: ["binary_sensor.sleeping"]}
    )
    await controller.async_setup(hass)

    await _set_state(hass, "binary_sensor.sleeping", STATE_OFF)
    assert controller.state == MyState.OFF
    controller.async_service_call.assert_not_called()
    controller.async_unload()


@pytest.mark.asyncio
async def test_required_recovery_does_not_override_manual_off(hass: HomeAssistant):
    hass.states.async_set("light.test", STATE_OFF)
    hass.states.async_set("binary_sensor.home", STATE_OFF)
    hass.states.async_set("binary_sensor.sleeping", STATE_OFF)
    controller = _make_light_controller(
        hass, **{Config.REQUIRED_OFF_ENTITIES: ["binary_sensor.sleeping"]}
    )
    await controller.async_setup(hass)

    await _set_state(hass, "binary_sensor.home", STATE_ON)
    assert controller.state == MyState.ON
    # Simulate relay acknowledging the controller's initial ON request.
    await _set_state(hass, "light.test", STATE_ON)
    controller.async_service_call.reset_mock()

    await _set_state(hass, "light.test", STATE_OFF)
    assert controller.state == MyState.OFF_MANUAL
    await _set_state(hass, "binary_sensor.sleeping", STATE_ON)
    await _set_state(hass, "binary_sensor.sleeping", STATE_OFF)
    assert controller.state == MyState.OFF_MANUAL
    controller.async_service_call.assert_not_called()
    controller.async_unload()


@pytest.mark.asyncio
async def test_required_failure_preserves_manual_on_and_blocks_takeover(
    hass: HomeAssistant,
):
    hass.states.async_set("light.test", STATE_ON)
    hass.states.async_set("binary_sensor.home", STATE_OFF)
    hass.states.async_set("binary_sensor.sleeping", STATE_OFF)
    controller = _make_light_controller(
        hass, **{Config.REQUIRED_OFF_ENTITIES: ["binary_sensor.sleeping"]}
    )
    await controller.async_setup(hass)
    assert controller.state == MyState.ON_MANUAL

    await _set_state(hass, "binary_sensor.sleeping", STATE_ON)
    assert controller.state == MyState.ON_MANUAL
    await _set_state(hass, "binary_sensor.home", STATE_ON)
    assert controller.state == MyState.ON_MANUAL
    controller.async_service_call.assert_not_called()

    await _set_state(hass, "binary_sensor.sleeping", STATE_OFF)
    assert controller.state == MyState.ON_MANUAL
    controller.async_service_call.assert_not_called()
    controller.async_unload()


@pytest.mark.asyncio
async def test_startup_shuts_off_existing_automatic_light_with_missing_requirement(
    hass: HomeAssistant,
):
    hass.states.async_set("light.test", STATE_ON)
    hass.states.async_set("binary_sensor.home", STATE_ON)
    # Missing sleeping sensor is unsafe, and must not keep the tree on.
    controller = _make_light_controller(
        hass, **{Config.REQUIRED_OFF_ENTITIES: ["binary_sensor.sleeping"]}
    )
    await controller.async_setup(hass)

    assert controller.state == MyState.OFF
    controller.async_service_call.assert_awaited_once_with(
        Platform.LIGHT, SERVICE_TURN_OFF, {}
    )
    assert controller.diagnostic_attributes["required_satisfied"] is False
    controller.async_unload()


@pytest.mark.asyncio
async def test_required_recovery_respects_illuminance_cutoff(hass: HomeAssistant):
    hass.states.async_set("light.test", STATE_OFF)
    hass.states.async_set("binary_sensor.home", STATE_ON)
    hass.states.async_set("binary_sensor.sleeping", STATE_ON)
    hass.states.async_set("sensor.lux", "50")
    controller = _make_light_controller(
        hass,
        **{
            Config.REQUIRED_OFF_ENTITIES: ["binary_sensor.sleeping"],
            Config.ILLUMINANCE_SENSOR: "sensor.lux",
            Config.ILLUMINANCE_CUTOFF: 10,
        },
    )
    await controller.async_setup(hass)

    await _set_state(hass, "binary_sensor.sleeping", STATE_OFF)
    assert controller.state == MyState.OFF
    controller.async_service_call.assert_not_called()
    assert "illuminance" in controller.diagnostic_attributes["reason"]
    controller.async_unload()
