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
        data=data or {},
    )


def _track_timer_calls(monkeypatch: pytest.MonkeyPatch, controller: OccupancyController):
    calls = []

    def set_timer(period):
        calls.append(period)

    monkeypatch.setattr(controller, "set_timer", set_timer)

    return calls


@pytest.mark.asyncio
async def test_trigger_only_trigger_enters_occupied_and_starts_decay_timer(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    trigger = "binary_sensor.office_pir"
    hass.states.async_set(trigger, STATE_ON)

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

    state = hass.states.get(trigger)
    assert state is not None

    await controller.on_state_change(state)

    assert controller.state == MyState.OCCUPIED
    assert timer_calls == [timedelta(minutes=2)]


@pytest.mark.asyncio
async def test_trigger_only_retrigger_extends_occupancy_by_restarting_decay_timer(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: ["binary_sensor.office_pir"],
                Config.DECAY_MINUTES: 5,
            }
        ),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await controller.fire_event(MyEvent.TRIGGER)
    await controller.fire_event(MyEvent.TRIGGER)

    assert controller.state == MyState.OCCUPIED
    assert timer_calls == [
        timedelta(minutes=5),
        timedelta(minutes=5),
    ]


@pytest.mark.asyncio
async def test_trigger_only_timer_expiration_exits_occupied_state(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: ["binary_sensor.office_pir"],
                Config.DECAY_MINUTES: 3,
            }
        ),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await controller.fire_event(MyEvent.TRIGGER)
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
    hass.states.async_set(sustain, STATE_ON)

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

    state = hass.states.get(sustain)
    assert state is not None

    await controller.on_state_change(state)

    assert controller.state == MyState.OCCUPIED
    assert timer_calls == [None]


@pytest.mark.asyncio
async def test_sustain_only_all_sustains_off_exits_occupied_without_waiting_for_timer(
    hass: HomeAssistant,
):
    sustain = "binary_sensor.office_mmwave"
    hass.states.async_set(sustain, STATE_ON)

    controller = OccupancyController(
        hass,
        _entry({Config.SUSTAIN_ENTITIES: [sustain]}),
    )

    state = hass.states.get(sustain)
    assert state is not None

    await controller.on_state_change(state)
    assert controller.state == MyState.OCCUPIED

    hass.states.async_set(sustain, STATE_OFF)
    state = hass.states.get(sustain)
    assert state is not None

    await controller.on_state_change(state)

    assert controller.state == MyState.UNOCCUPIED


@pytest.mark.asyncio
async def test_hybrid_sustain_on_while_vacant_does_not_enter_occupied_state(
    hass: HomeAssistant,
):
    sustain = "binary_sensor.office_mmwave"
    hass.states.async_set(sustain, STATE_ON)

    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: ["binary_sensor.office_pir"],
                Config.SUSTAIN_ENTITIES: [sustain],
            }
        ),
    )

    state = hass.states.get(sustain)
    assert state is not None

    await controller.on_state_change(state)

    assert controller.state == MyState.UNOCCUPIED


@pytest.mark.asyncio
async def test_hybrid_trigger_enters_occupied_when_sustain_is_active_without_timer(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    trigger = "binary_sensor.office_pir"
    sustain = "binary_sensor.office_mmwave"
    hass.states.async_set(trigger, STATE_ON)
    hass.states.async_set(sustain, STATE_ON)

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

    state = hass.states.get(trigger)
    assert state is not None

    await controller.on_state_change(state)

    assert controller.state == MyState.OCCUPIED
    assert timer_calls == [None]


@pytest.mark.asyncio
async def test_hybrid_trigger_remains_occupied_while_trigger_is_on_even_if_sustain_is_off(
    hass: HomeAssistant,
):
    trigger = "binary_sensor.office_pir"
    sustain = "binary_sensor.office_mmwave"
    hass.states.async_set(trigger, STATE_ON)
    hass.states.async_set(sustain, STATE_OFF)

    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.SUSTAIN_ENTITIES: [sustain],
            }
        ),
    )

    state = hass.states.get(trigger)
    assert state is not None

    await controller.on_state_change(state)

    assert controller.state == MyState.OCCUPIED


@pytest.mark.asyncio
async def test_hybrid_exits_when_trigger_and_sustain_are_both_off(
    hass: HomeAssistant,
):
    trigger = "binary_sensor.office_pir"
    sustain = "binary_sensor.office_mmwave"
    hass.states.async_set(trigger, STATE_ON)
    hass.states.async_set(sustain, STATE_OFF)

    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.SUSTAIN_ENTITIES: [sustain],
            }
        ),
    )

    state = hass.states.get(trigger)
    assert state is not None
    await controller.on_state_change(state)
    assert controller.state == MyState.OCCUPIED

    hass.states.async_set(trigger, STATE_OFF)
    state = hass.states.get(trigger)
    assert state is not None
    await controller.on_state_change(state)

    assert controller.state == MyState.UNOCCUPIED


@pytest.mark.asyncio
async def test_hybrid_all_sustains_off_exits_occupied_state(
    hass: HomeAssistant,
):
    trigger = "binary_sensor.office_pir"
    sustain = "binary_sensor.office_mmwave"
    hass.states.async_set(trigger, STATE_ON)
    hass.states.async_set(sustain, STATE_ON)

    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: [trigger],
                Config.SUSTAIN_ENTITIES: [sustain],
            }
        ),
    )

    trigger_state = hass.states.get(trigger)
    assert trigger_state is not None

    await controller.on_state_change(trigger_state)
    assert controller.state == MyState.OCCUPIED

    hass.states.async_set(sustain, STATE_OFF)
    sustain_state = hass.states.get(sustain)
    assert sustain_state is not None

    await controller.on_state_change(sustain_state)

    assert controller.state == MyState.UNOCCUPIED


@pytest.mark.asyncio
async def test_required_entity_missing_prevents_trigger_occupancy(
    hass: HomeAssistant,
):
    required = "binary_sensor.required"
    hass.states.async_set(required, STATE_OFF)

    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.TRIGGER_ENTITIES: ["binary_sensor.office_pir"],
                Config.REQUIRED_ON_ENTITIES: [required],
            }
        ),
    )

    await controller.fire_event(MyEvent.TRIGGER)

    assert controller.state == MyState.UNOCCUPIED


@pytest.mark.asyncio
async def test_required_entity_missing_prevents_sustain_only_occupancy(
    hass: HomeAssistant,
):
    sustain = "binary_sensor.office_mmwave"
    required = "binary_sensor.required"
    hass.states.async_set(sustain, STATE_ON)
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

    await controller.fire_event(MyEvent.SUSTAIN_UPDATE)

    assert controller.state == MyState.UNOCCUPIED


@pytest.mark.asyncio
async def test_sustain_only_required_update_enters_when_sustain_is_active_and_requirements_become_valid(
    hass: HomeAssistant,
):
    sustain = "binary_sensor.office_mmwave"
    required = "binary_sensor.required"
    hass.states.async_set(sustain, STATE_ON)
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

    await controller.fire_event(MyEvent.SUSTAIN_UPDATE)
    assert controller.state == MyState.UNOCCUPIED

    hass.states.async_set(required, STATE_ON)
    await controller.fire_event(MyEvent.REQUIRED_UPDATE)

    assert controller.state == MyState.OCCUPIED
