import pytest

from datetime import timedelta

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
    return MockConfigEntry(
        domain="smartify",
        title="Office Occupancy",
        data=data or {},
    )


def _track_timer_calls(monkeypatch: pytest.MonkeyPatch, controller: OccupancyController):
    calls = []

    def set_timer(period):
        calls.append(period)

    monkeypatch.setattr(controller, "set_timer", set_timer)

    return calls


async def _set_and_notify(
    hass: HomeAssistant,
    controller: OccupancyController,
    entity_id: str,
    state_value: str,
):
    hass.states.async_set(entity_id, state_value)
    state = hass.states.get(entity_id)
    assert state is not None
    await controller.on_state_change(state)


@pytest.mark.asyncio
async def test_trigger_only_trigger_enters_occupied_and_starts_decay_timer(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    trigger = "binary_sensor.office_pir"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.DECAY_MINUTES: 2,
            }
        ),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await _set_and_notify(hass, controller, trigger, STATE_ON)

    assert controller.state == MyState.OCCUPIED
    assert timer_calls == [timedelta(minutes=2)]


@pytest.mark.asyncio
async def test_trigger_only_retrigger_extends_occupancy_by_restarting_decay_timer(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    trigger = "binary_sensor.office_pir"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.DECAY_MINUTES: 5,
            }
        ),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await _set_and_notify(hass, controller, trigger, STATE_ON)
    await controller.fire_event(MyEvent.TRIGGER)

    assert controller.state == MyState.OCCUPIED
    assert timer_calls == [
        timedelta(minutes=5),
        timedelta(minutes=5),
    ]


@pytest.mark.asyncio
async def test_trigger_only_trigger_off_does_not_exit_before_decay_timer(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    trigger = "binary_sensor.office_pir"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.DECAY_MINUTES: 3,
            }
        ),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await _set_and_notify(hass, controller, trigger, STATE_ON)
    await _set_and_notify(hass, controller, trigger, STATE_OFF)

    assert controller.state == MyState.OCCUPIED
    assert timer_calls == [timedelta(minutes=3)]


@pytest.mark.asyncio
async def test_trigger_only_timer_expiration_exits_occupied_state(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    trigger = "binary_sensor.office_pir"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.DECAY_MINUTES: 3,
            }
        ),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await _set_and_notify(hass, controller, trigger, STATE_ON)
    assert controller.state == MyState.OCCUPIED

    await controller.fire_event(MyEvent.TIMER)

    assert controller.state == MyState.UNOCCUPIED
    assert timer_calls == [
        timedelta(minutes=3),
        None,
    ]


@pytest.mark.asyncio
async def test_sustain_only_sustain_on_enters_occupied_without_decay_timer(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.SUSTAIN_ENTITIES: [sustain],
                Config.DECAY_MINUTES: 10,
            }
        ),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await _set_and_notify(hass, controller, sustain, STATE_ON)

    assert controller.state == MyState.OCCUPIED
    assert timer_calls == [None]


@pytest.mark.asyncio
async def test_sustain_only_all_sustains_off_exits_occupied_without_waiting_for_timer(
    hass: HomeAssistant,
):
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass,
        _entry({Config.SUSTAIN_ENTITIES: [sustain]}),
    )

    await _set_and_notify(hass, controller, sustain, STATE_ON)
    assert controller.state == MyState.OCCUPIED

    await _set_and_notify(hass, controller, sustain, STATE_OFF)

    assert controller.state == MyState.UNOCCUPIED


@pytest.mark.asyncio
async def test_sustain_only_timer_event_is_harmless_while_sustain_is_active(
    hass: HomeAssistant,
):
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass,
        _entry({Config.SUSTAIN_ENTITIES: [sustain]}),
    )

    await _set_and_notify(hass, controller, sustain, STATE_ON)
    await controller.fire_event(MyEvent.TIMER)

    assert controller.state == MyState.OCCUPIED


@pytest.mark.asyncio
async def test_hybrid_sustain_on_while_vacant_does_not_enter_occupied_state(
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
            }
        ),
    )

    await _set_and_notify(hass, controller, sustain, STATE_ON)

    assert controller.state == MyState.UNOCCUPIED


@pytest.mark.asyncio
async def test_hybrid_trigger_enters_occupied_even_before_sustain_turns_on(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    """Regression: PIR trigger must not immediately turn off if mmWave lags."""
    trigger = "binary_sensor.office_pir"
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.SUSTAIN_ENTITIES: [sustain],
                Config.DECAY_MINUTES: 10,
            }
        ),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await _set_and_notify(hass, controller, sustain, STATE_OFF)
    await _set_and_notify(hass, controller, trigger, STATE_ON)

    assert controller.state == MyState.OCCUPIED
    assert timer_calls == [None]


@pytest.mark.asyncio
async def test_hybrid_sustain_off_does_not_exit_while_trigger_remains_on(
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
            }
        ),
    )

    await _set_and_notify(hass, controller, sustain, STATE_ON)
    await _set_and_notify(hass, controller, trigger, STATE_ON)
    assert controller.state == MyState.OCCUPIED

    await _set_and_notify(hass, controller, sustain, STATE_OFF)

    assert controller.state == MyState.OCCUPIED


@pytest.mark.asyncio
async def test_hybrid_trigger_off_does_not_exit_while_sustain_remains_on(
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
            }
        ),
    )

    await _set_and_notify(hass, controller, sustain, STATE_ON)
    await _set_and_notify(hass, controller, trigger, STATE_ON)
    assert controller.state == MyState.OCCUPIED

    await _set_and_notify(hass, controller, trigger, STATE_OFF)

    assert controller.state == MyState.OCCUPIED


@pytest.mark.asyncio
async def test_hybrid_exits_when_trigger_and_sustain_are_both_off(
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
            }
        ),
    )

    await _set_and_notify(hass, controller, sustain, STATE_ON)
    await _set_and_notify(hass, controller, trigger, STATE_ON)
    assert controller.state == MyState.OCCUPIED

    await _set_and_notify(hass, controller, trigger, STATE_OFF)
    assert controller.state == MyState.OCCUPIED

    await _set_and_notify(hass, controller, sustain, STATE_OFF)

    assert controller.state == MyState.UNOCCUPIED


@pytest.mark.asyncio
async def test_hybrid_trigger_turns_on_sustain_turns_on_trigger_turns_off_stays_occupied(
    hass: HomeAssistant,
):
    """Realistic PIR acquisition followed by delayed mmWave sustain."""
    trigger = "binary_sensor.office_pir"
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.SUSTAIN_ENTITIES: [sustain],
            }
        ),
    )

    await _set_and_notify(hass, controller, trigger, STATE_ON)
    assert controller.state == MyState.OCCUPIED

    await _set_and_notify(hass, controller, sustain, STATE_ON)
    assert controller.state == MyState.OCCUPIED

    await _set_and_notify(hass, controller, trigger, STATE_OFF)

    assert controller.state == MyState.OCCUPIED


@pytest.mark.asyncio
async def test_hybrid_timer_event_is_harmless_while_trigger_is_active(
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
            }
        ),
    )

    await _set_and_notify(hass, controller, trigger, STATE_ON)
    assert controller.state == MyState.OCCUPIED

    await controller.fire_event(MyEvent.TIMER)

    assert controller.state == MyState.OCCUPIED


@pytest.mark.asyncio
async def test_required_entity_missing_prevents_trigger_occupancy(
    hass: HomeAssistant,
):
    trigger = "binary_sensor.office_pir"
    required = "binary_sensor.required"
    hass.states.async_set(required, STATE_OFF)

    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.REQUIRED_ON_ENTITIES: [required],
                Config.DECAY_MINUTES: 2,
            }
        ),
    )

    await _set_and_notify(hass, controller, trigger, STATE_ON)

    assert controller.state == MyState.UNOCCUPIED


@pytest.mark.asyncio
async def test_required_entity_missing_prevents_sustain_only_occupancy(
    hass: HomeAssistant,
):
    sustain = "binary_sensor.office_mmwave"
    required = "binary_sensor.required"
    hass.states.async_set(required, STATE_OFF)

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


@pytest.mark.asyncio
async def test_occupied_state_exits_when_required_condition_becomes_invalid(
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
    assert controller.state == MyState.OCCUPIED

    await _set_and_notify(hass, controller, required, STATE_OFF)

    assert controller.state == MyState.UNOCCUPIED


@pytest.mark.asyncio
async def test_sustain_only_required_update_enters_when_sustain_is_active_and_requirements_become_valid(
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

    assert controller.state == MyState.OCCUPIED
