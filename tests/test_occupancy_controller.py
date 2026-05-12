from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartify.const import Config
from custom_components.smartify.occupancy_controller import (
    MyEvent,
    MyState,
    OccupancyController,
)


def _entry(data: dict | None = None) -> MockConfigEntry:
    return MockConfigEntry(domain="smartify", data=data or {})


async def _set_and_notify(
    hass: HomeAssistant,
    controller: OccupancyController,
    entity_id: str,
    state_value: str,
) -> None:
    hass.states.async_set(entity_id, state_value)
    state = hass.states.get(entity_id)
    assert state is not None
    await controller.on_state_change(state)


def _track_timer_calls(
    monkeypatch: pytest.MonkeyPatch, controller: OccupancyController
):
    calls = []

    def set_timer(period):
        calls.append(period)

    monkeypatch.setattr(controller, "set_timer", set_timer)
    return calls


@pytest.mark.asyncio
async def test_trigger_only_trigger_enters_triggered_occupied_and_starts_decay_timer(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    trigger = "binary_sensor.office_pir"
    controller = OccupancyController(
        hass,
        _entry({Config.TRIGGER_ENTITIES: [trigger], Config.DECAY_MINUTES: 2}),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await _set_and_notify(hass, controller, trigger, STATE_ON)

    assert controller.state == MyState.TRIGGERED_OCCUPIED
    assert controller.is_on is True
    assert timer_calls == [timedelta(minutes=2)]


@pytest.mark.asyncio
async def test_trigger_only_trigger_off_does_not_exit_before_decay_timer(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    trigger = "binary_sensor.office_pir"
    controller = OccupancyController(
        hass,
        _entry({Config.TRIGGER_ENTITIES: [trigger], Config.DECAY_MINUTES: 3}),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await _set_and_notify(hass, controller, trigger, STATE_ON)
    await _set_and_notify(hass, controller, trigger, STATE_OFF)

    assert controller.state == MyState.TRIGGERED_OCCUPIED
    assert controller.is_on is True
    assert timer_calls == [timedelta(minutes=3)]


@pytest.mark.asyncio
async def test_trigger_only_retrigger_restarts_decay_timer(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    trigger = "binary_sensor.office_pir"
    controller = OccupancyController(
        hass,
        _entry({Config.TRIGGER_ENTITIES: [trigger], Config.DECAY_MINUTES: 5}),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await _set_and_notify(hass, controller, trigger, STATE_ON)
    await controller.fire_event(MyEvent.TRIGGER)

    assert controller.state == MyState.TRIGGERED_OCCUPIED
    assert timer_calls == [timedelta(minutes=5), timedelta(minutes=5)]


@pytest.mark.asyncio
async def test_trigger_only_timer_expiration_exits_triggered_occupied(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    trigger = "binary_sensor.office_pir"
    controller = OccupancyController(
        hass,
        _entry({Config.TRIGGER_ENTITIES: [trigger], Config.DECAY_MINUTES: 3}),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await _set_and_notify(hass, controller, trigger, STATE_ON)
    await controller.fire_event(MyEvent.TIMER)

    assert controller.state == MyState.UNOCCUPIED
    assert controller.is_on is False
    assert timer_calls == [timedelta(minutes=3), None]


@pytest.mark.asyncio
async def test_sustain_only_sustain_on_enters_sustained_occupied_without_decay_timer(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass,
        _entry({Config.SUSTAIN_ENTITIES: [sustain]}),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await _set_and_notify(hass, controller, sustain, STATE_ON)

    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert controller.is_on is True
    assert timer_calls == [None]


@pytest.mark.asyncio
async def test_sustain_only_all_sustains_off_exits_sustained_occupied_immediately(
    hass: HomeAssistant,
):
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(hass, _entry({Config.SUSTAIN_ENTITIES: [sustain]}))

    await _set_and_notify(hass, controller, sustain, STATE_ON)
    await _set_and_notify(hass, controller, sustain, STATE_OFF)

    assert controller.state == MyState.UNOCCUPIED
    assert controller.is_on is False


@pytest.mark.asyncio
async def test_sustain_only_timer_event_is_harmless_while_sustain_is_active(
    hass: HomeAssistant,
):
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(hass, _entry({Config.SUSTAIN_ENTITIES: [sustain]}))

    await _set_and_notify(hass, controller, sustain, STATE_ON)
    await controller.fire_event(MyEvent.TIMER)

    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert controller.is_on is True


@pytest.mark.asyncio
async def test_hybrid_sustain_on_while_unoccupied_does_not_enter_occupancy(
    hass: HomeAssistant,
):
    trigger = "binary_sensor.office_pir"
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.SUSTAIN_ENTITIES: [sustain],
                Config.DECAY_MINUTES: 1,
            }
        ),
    )

    await _set_and_notify(hass, controller, sustain, STATE_ON)

    assert controller.state == MyState.UNOCCUPIED
    assert controller.is_on is False


@pytest.mark.asyncio
async def test_hybrid_trigger_enters_triggered_occupied_even_before_sustain_turns_on(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    """Regression: PIR acquisition must not immediately drop because mmWave lags."""
    trigger = "binary_sensor.office_pir"
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.SUSTAIN_ENTITIES: [sustain],
                Config.DECAY_MINUTES: 1,
            }
        ),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await _set_and_notify(hass, controller, sustain, STATE_OFF)
    await _set_and_notify(hass, controller, trigger, STATE_ON)

    assert controller.state == MyState.TRIGGERED_OCCUPIED
    assert controller.is_on is True
    assert timer_calls == [timedelta(minutes=1)]


@pytest.mark.asyncio
async def test_hybrid_trigger_off_does_not_exit_triggered_occupied_before_decay_timer(
    hass: HomeAssistant,
):
    """Regression: PIR turning off is not vacancy; the decay timer owns that state."""
    trigger = "binary_sensor.office_pir"
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.SUSTAIN_ENTITIES: [sustain],
                Config.DECAY_MINUTES: 1,
            }
        ),
    )

    await _set_and_notify(hass, controller, trigger, STATE_ON)
    await _set_and_notify(hass, controller, trigger, STATE_OFF)

    assert controller.state == MyState.TRIGGERED_OCCUPIED
    assert controller.is_on is True


@pytest.mark.asyncio
async def test_hybrid_sustain_on_while_triggered_transitions_to_sustained_and_cancels_timer(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    """Core handoff: PIR-triggered occupancy is immediately owned by mmWave."""
    trigger = "binary_sensor.office_pir"
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.SUSTAIN_ENTITIES: [sustain],
                Config.DECAY_MINUTES: 1,
            }
        ),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await _set_and_notify(hass, controller, trigger, STATE_ON)
    await _set_and_notify(hass, controller, trigger, STATE_OFF)
    await _set_and_notify(hass, controller, sustain, STATE_ON)

    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert controller.is_on is True
    assert timer_calls == [timedelta(minutes=1), None]


@pytest.mark.asyncio
async def test_hybrid_sustained_occupied_exits_when_all_sustains_turn_off(
    hass: HomeAssistant,
):
    trigger = "binary_sensor.office_pir"
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.SUSTAIN_ENTITIES: [sustain],
                Config.DECAY_MINUTES: 1,
            }
        ),
    )

    await _set_and_notify(hass, controller, trigger, STATE_ON)
    await _set_and_notify(hass, controller, sustain, STATE_ON)
    await _set_and_notify(hass, controller, sustain, STATE_OFF)

    assert controller.state == MyState.UNOCCUPIED
    assert controller.is_on is False


@pytest.mark.asyncio
async def test_hybrid_timer_expiration_exits_triggered_occupied_when_no_sustain_active(
    hass: HomeAssistant,
):
    trigger = "binary_sensor.office_pir"
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.SUSTAIN_ENTITIES: [sustain],
                Config.DECAY_MINUTES: 1,
            }
        ),
    )

    await _set_and_notify(hass, controller, trigger, STATE_ON)
    await _set_and_notify(hass, controller, trigger, STATE_OFF)
    await controller.fire_event(MyEvent.TIMER)

    assert controller.state == MyState.UNOCCUPIED
    assert controller.is_on is False


@pytest.mark.asyncio
async def test_hybrid_timer_expiration_hands_off_to_sustained_if_sustain_is_active(
    hass: HomeAssistant,
):
    """Defensive path: stale/missed sustain update should not cause false vacancy."""
    trigger = "binary_sensor.office_pir"
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.SUSTAIN_ENTITIES: [sustain],
                Config.DECAY_MINUTES: 1,
            }
        ),
    )

    await _set_and_notify(hass, controller, trigger, STATE_ON)
    hass.states.async_set(sustain, STATE_ON)
    await controller.fire_event(MyEvent.TIMER)

    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert controller.is_on is True


@pytest.mark.asyncio
async def test_hybrid_trigger_while_sustained_and_sustain_active_stays_sustained(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    trigger = "binary_sensor.office_pir"
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.SUSTAIN_ENTITIES: [sustain],
                Config.DECAY_MINUTES: 1,
            }
        ),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await _set_and_notify(hass, controller, trigger, STATE_ON)
    await _set_and_notify(hass, controller, sustain, STATE_ON)
    await _set_and_notify(hass, controller, trigger, STATE_ON)

    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert timer_calls == [timedelta(minutes=1), None]


@pytest.mark.asyncio
async def test_required_entity_missing_prevents_trigger_occupancy(
    hass: HomeAssistant,
):
    trigger = "binary_sensor.office_pir"
    required = "binary_sensor.required"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.REQUIRED_ON_ENTITIES: [required],
                Config.DECAY_MINUTES: 1,
            }
        ),
    )

    await _set_and_notify(hass, controller, required, STATE_OFF)
    await _set_and_notify(hass, controller, trigger, STATE_ON)

    assert controller.state == MyState.UNOCCUPIED
    assert controller.is_on is False


@pytest.mark.asyncio
async def test_required_entity_missing_prevents_sustain_only_occupancy(
    hass: HomeAssistant,
):
    sustain = "binary_sensor.office_mmwave"
    required = "binary_sensor.required"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.SUSTAIN_ENTITIES: [sustain],
                Config.REQUIRED_ON_ENTITIES: [required],
            }
        ),
    )

    await _set_and_notify(hass, controller, required, STATE_OFF)
    await _set_and_notify(hass, controller, sustain, STATE_ON)

    assert controller.state == MyState.UNOCCUPIED
    assert controller.is_on is False


@pytest.mark.asyncio
async def test_triggered_occupied_exits_when_required_condition_becomes_invalid(
    hass: HomeAssistant,
):
    trigger = "binary_sensor.office_pir"
    required = "binary_sensor.required"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.REQUIRED_ON_ENTITIES: [required],
                Config.DECAY_MINUTES: 1,
            }
        ),
    )

    await _set_and_notify(hass, controller, required, STATE_ON)
    await _set_and_notify(hass, controller, trigger, STATE_ON)
    assert controller.state == MyState.TRIGGERED_OCCUPIED

    await _set_and_notify(hass, controller, required, STATE_OFF)

    assert controller.state == MyState.UNOCCUPIED
    assert controller.is_on is False


@pytest.mark.asyncio
async def test_sustained_occupied_exits_when_required_condition_becomes_invalid(
    hass: HomeAssistant,
):
    sustain = "binary_sensor.office_mmwave"
    required = "binary_sensor.required"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.SUSTAIN_ENTITIES: [sustain],
                Config.REQUIRED_ON_ENTITIES: [required],
            }
        ),
    )

    await _set_and_notify(hass, controller, required, STATE_ON)
    await _set_and_notify(hass, controller, sustain, STATE_ON)
    assert controller.state == MyState.SUSTAINED_OCCUPIED

    await _set_and_notify(hass, controller, required, STATE_OFF)

    assert controller.state == MyState.UNOCCUPIED
    assert controller.is_on is False


@pytest.mark.asyncio
async def test_sustain_only_required_update_enters_when_sustain_active_and_requirements_become_valid(
    hass: HomeAssistant,
):
    sustain = "binary_sensor.office_mmwave"
    required = "binary_sensor.required"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.SUSTAIN_ENTITIES: [sustain],
                Config.REQUIRED_ON_ENTITIES: [required],
            }
        ),
    )

    await _set_and_notify(hass, controller, sustain, STATE_ON)
    assert controller.state == MyState.UNOCCUPIED

    await _set_and_notify(hass, controller, required, STATE_ON)

    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert controller.is_on is True
