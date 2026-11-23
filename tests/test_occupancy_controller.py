from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.const import STATE_OFF, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, State
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

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
async def test_trigger_only_trigger_on_enters_triggered_occupied_and_holds_without_timer(
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
    assert timer_calls == [None]


@pytest.mark.asyncio
async def test_trigger_only_trigger_off_starts_decay_timer(
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
    assert timer_calls == [None, timedelta(minutes=3)]


@pytest.mark.asyncio
async def test_trigger_only_retrigger_during_decay_cancels_timer(
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
    await _set_and_notify(hass, controller, trigger, STATE_OFF)
    await _set_and_notify(hass, controller, trigger, STATE_ON)

    assert controller.state == MyState.TRIGGERED_OCCUPIED
    assert timer_calls == [None, timedelta(minutes=5), None]


@pytest.mark.asyncio
async def test_trigger_only_attribute_update_does_not_retrigger(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    trigger = "binary_sensor.office_pir"
    controller = OccupancyController(
        hass,
        _entry({Config.TRIGGER_ENTITIES: [trigger], Config.DECAY_MINUTES: 5}),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    old_state = State(trigger, STATE_ON, {"signal_strength": 10})
    new_state = State(trigger, STATE_ON, {"signal_strength": 20})

    hass.states.async_set(trigger, STATE_ON, {"signal_strength": 10})
    await controller._on_state_change(None, old_state)
    hass.states.async_set(trigger, STATE_ON, {"signal_strength": 20})
    await controller._on_state_change(old_state, new_state)

    assert controller.state == MyState.TRIGGERED_OCCUPIED
    assert timer_calls == [None]


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
    await _set_and_notify(hass, controller, trigger, STATE_OFF)
    await controller.fire_event(MyEvent.TIMER)

    assert controller.state == MyState.UNOCCUPIED
    assert controller.is_on is False
    assert timer_calls == [None, timedelta(minutes=3), None]


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
async def test_sustain_only_all_sustains_off_starts_grace_timer_then_exits(
    hass: HomeAssistant,
):
    """Last sustain off starts the decay grace timer; exit only on expiry."""
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass, _entry({Config.SUSTAIN_ENTITIES: [sustain], Config.DECAY_MINUTES: 1})
    )

    await _set_and_notify(hass, controller, sustain, STATE_ON)
    await _set_and_notify(hass, controller, sustain, STATE_OFF)

    # Does not exit immediately; grace timer is running.
    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert controller.is_on is True
    assert controller._timer_unsub is not None

    # Grace period expires with no sustain active -> exit.
    await controller.fire_event(MyEvent.TIMER)

    assert controller.state == MyState.UNOCCUPIED
    assert controller.is_on is False

    controller.async_unload()


@pytest.mark.asyncio
async def test_sustain_only_returns_during_grace_cancels_timer(
    hass: HomeAssistant,
):
    """A sustain returning during the grace period cancels the timer."""
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass, _entry({Config.SUSTAIN_ENTITIES: [sustain], Config.DECAY_MINUTES: 1})
    )

    await _set_and_notify(hass, controller, sustain, STATE_ON)
    await _set_and_notify(hass, controller, sustain, STATE_OFF)

    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert controller._timer_unsub is not None

    # Sustain comes back before the timer expires.
    await _set_and_notify(hass, controller, sustain, STATE_ON)

    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert controller.is_on is True
    assert controller._timer_unsub is None

    controller.async_unload()


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
    assert timer_calls == [None]


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
    assert timer_calls == [None, timedelta(minutes=1), None]


@pytest.mark.asyncio
async def test_hybrid_sustained_occupied_starts_grace_timer_when_sustains_turn_off(
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
    await _set_and_notify(hass, controller, trigger, STATE_OFF)
    await _set_and_notify(hass, controller, sustain, STATE_OFF)

    # Grace timer started; still occupied until it expires.
    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert controller.is_on is True
    assert controller._timer_unsub is not None

    await controller.fire_event(MyEvent.TIMER)

    assert controller.state == MyState.UNOCCUPIED
    assert controller.is_on is False

    controller.async_unload()


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
    assert timer_calls == [None, None]


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


@pytest.mark.asyncio
async def test_sustained_grace_exits_immediately_when_required_becomes_invalid(
    hass: HomeAssistant,
):
    """Requirements are a hard gate even during the sustained grace period."""
    sustain = "binary_sensor.office_mmwave"
    required = "binary_sensor.required"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.SUSTAIN_ENTITIES: [sustain],
                Config.REQUIRED_ON_ENTITIES: [required],
                Config.DECAY_MINUTES: 1,
            }
        ),
    )

    await _set_and_notify(hass, controller, required, STATE_ON)
    await _set_and_notify(hass, controller, sustain, STATE_ON)
    assert controller.state == MyState.SUSTAINED_OCCUPIED

    # Sustain drops -> grace timer running, still occupied.
    await _set_and_notify(hass, controller, sustain, STATE_OFF)
    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert controller._timer_unsub is not None

    # Required condition fails -> immediate exit, timer cancelled.
    await _set_and_notify(hass, controller, required, STATE_OFF)
    assert controller.state == MyState.UNOCCUPIED
    assert controller.is_on is False
    assert controller._timer_unsub is None

    controller.async_unload()


@pytest.mark.asyncio
async def test_sustained_grace_timer_not_restarted_on_repeated_events(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    """Repeated SUSTAIN/REQUIRED events during grace must not extend the window."""
    sustain = "binary_sensor.office_mmwave"
    other = "binary_sensor.office_mmwave2"
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.SUSTAIN_ENTITIES: [sustain, other],
                Config.DECAY_MINUTES: 1,
            }
        ),
    )

    # Enter sustained via one sustain, then both off.
    await _set_and_notify(hass, controller, sustain, STATE_ON)
    assert controller.state == MyState.SUSTAINED_OCCUPIED
    await _set_and_notify(hass, controller, sustain, STATE_OFF)
    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert controller._timer_unsub is not None

    # Now track timer calls; a second sustain reporting OFF while already in the
    # grace window must not call set_timer again.
    timer_calls = _track_timer_calls(monkeypatch, controller)
    await _set_and_notify(hass, controller, other, STATE_OFF)

    assert timer_calls == []
    assert controller.state == MyState.SUSTAINED_OCCUPIED

    controller.async_unload()


@pytest.mark.asyncio
async def test_sustained_grace_timer_handoff_if_sustain_active_at_expiry(
    hass: HomeAssistant,
):
    """If a sustain is active when the grace timer fires, stay sustained."""
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass, _entry({Config.SUSTAIN_ENTITIES: [sustain], Config.DECAY_MINUTES: 1})
    )

    await _set_and_notify(hass, controller, sustain, STATE_ON)
    await _set_and_notify(hass, controller, sustain, STATE_OFF)
    assert controller.state == MyState.SUSTAINED_OCCUPIED

    # Sustain is physically back on but its event was missed; the timer fires.
    hass.states.async_set(sustain, STATE_ON)
    await controller.fire_event(MyEvent.TIMER)

    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert controller.is_on is True

    controller.async_unload()


@pytest.mark.asyncio
async def test_diagnostics_explain_trigger_decay(
    hass: HomeAssistant,
):
    trigger = "binary_sensor.office_pir"
    controller = OccupancyController(
        hass,
        _entry({Config.TRIGGER_ENTITIES: [trigger], Config.DECAY_MINUTES: 3}),
    )

    await _set_and_notify(hass, controller, trigger, STATE_ON)

    diagnostics = controller.diagnostic_attributes
    assert diagnostics["reason"] == (
        "TRIGGERED: binary_sensor.office_pir is on; occupancy is held while it "
        "stays on, then for 3 minute(s) after all triggers turn off."
    )
    assert diagnostics["last_event"] == "trigger"
    assert diagnostics["active_trigger_entities"] == [trigger]

    controller.async_unload()


@pytest.mark.asyncio
async def test_diagnostics_explain_sustain_grace_period(
    hass: HomeAssistant,
):
    sustain = "binary_sensor.office_mmwave"
    controller = OccupancyController(
        hass,
        _entry({Config.SUSTAIN_ENTITIES: [sustain], Config.DECAY_MINUTES: 1}),
    )

    await _set_and_notify(hass, controller, sustain, STATE_ON)
    await _set_and_notify(hass, controller, sustain, STATE_OFF)

    diagnostics = controller.diagnostic_attributes
    assert diagnostics["reason"] == (
        "DECAY: no sustain entities are active; occupancy remains on until the "
        "decay timer expires unless a sustain returns."
    )
    assert diagnostics["active_sustain_entities"] == []

    controller.async_unload()


@pytest.mark.asyncio
async def test_trigger_held_on_past_decay_keeps_occupancy(hass: HomeAssistant):
    """Regression: a PIR that stays on longer than decay must not clear occupancy."""
    trigger = "binary_sensor.office_pir"
    hass.states.async_set(trigger, STATE_OFF)
    controller = OccupancyController(
        hass,
        _entry({Config.TRIGGER_ENTITIES: [trigger], Config.DECAY_MINUTES: 2}),
    )
    await controller.async_setup(hass)

    hass.states.async_set(trigger, STATE_ON)
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=10))
    await hass.async_block_till_done()

    assert controller.state == MyState.TRIGGERED_OCCUPIED
    assert controller.timer_expires_at is None

    hass.states.async_set(trigger, STATE_OFF)
    await hass.async_block_till_done()
    assert controller.is_on is True
    assert controller.timer_expires_at is not None

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=3))
    await hass.async_block_till_done()
    assert controller.state == MyState.UNOCCUPIED

    controller.async_unload()


@pytest.mark.asyncio
async def test_decay_waits_for_last_of_multiple_triggers(
    hass: HomeAssistant,
    monkeypatch: pytest.MonkeyPatch,
):
    pir_a = "binary_sensor.pir_a"
    pir_b = "binary_sensor.pir_b"
    controller = OccupancyController(
        hass,
        _entry({Config.TRIGGER_ENTITIES: [pir_a, pir_b], Config.DECAY_MINUTES: 4}),
    )
    timer_calls = _track_timer_calls(monkeypatch, controller)

    await _set_and_notify(hass, controller, pir_a, STATE_ON)
    await _set_and_notify(hass, controller, pir_b, STATE_ON)
    await _set_and_notify(hass, controller, pir_a, STATE_OFF)
    assert timer_calls == [None, None]

    await _set_and_notify(hass, controller, pir_b, STATE_OFF)
    assert timer_calls == [None, None, timedelta(minutes=4)]
    assert controller.state == MyState.TRIGGERED_OCCUPIED


@pytest.mark.asyncio
async def test_unavailable_trigger_releases_hold(hass: HomeAssistant):
    """A PIR that drops off the network must not hold occupancy forever."""
    trigger = "binary_sensor.office_pir"
    hass.states.async_set(trigger, STATE_OFF)
    controller = OccupancyController(
        hass,
        _entry({Config.TRIGGER_ENTITIES: [trigger], Config.DECAY_MINUTES: 2}),
    )
    await controller.async_setup(hass)

    hass.states.async_set(trigger, STATE_ON)
    await hass.async_block_till_done()
    hass.states.async_set(trigger, STATE_UNAVAILABLE)
    await hass.async_block_till_done()
    assert controller.timer_expires_at is not None

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=3))
    await hass.async_block_till_done()
    assert controller.state == MyState.UNOCCUPIED

    controller.async_unload()


@pytest.mark.asyncio
async def test_last_sustain_off_hands_back_immediately_to_held_trigger(
    hass: HomeAssistant,
):
    """Last sustain off hands occupancy immediately to an active PIR."""
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

    assert controller.state == MyState.TRIGGERED_OCCUPIED
    assert controller.timer_expires_at is None

    controller.async_unload()


async def _lose_entity(
    hass: HomeAssistant, entity_id: str, failure: str | None
) -> None:
    """Exercise the real state-event listener for a sensor that stops reporting."""
    if failure is None:
        hass.states.async_remove(entity_id)
    else:
        hass.states.async_set(entity_id, failure)
    await hass.async_block_till_done()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [STATE_UNAVAILABLE, STATE_UNKNOWN, None],
    ids=["unavailable", "unknown", "removed"],
)
async def test_lost_trigger_starts_decay(
    hass: HomeAssistant, failure: str | None
):
    """Even a removed PIR must release trigger-held occupancy."""
    trigger = "binary_sensor.office_pir"
    hass.states.async_set(trigger, STATE_ON)
    controller = OccupancyController(
        hass, _entry({Config.TRIGGER_ENTITIES: [trigger], Config.DECAY_MINUTES: 2})
    )
    await controller.async_setup(hass)
    assert controller.state == MyState.TRIGGERED_OCCUPIED
    assert controller.timer_expires_at is None

    await _lose_entity(hass, trigger, failure)
    assert controller.state == MyState.TRIGGERED_OCCUPIED
    assert controller.timer_expires_at is not None
    assert controller.diagnostic_attributes["last_trigger_entity"] == trigger

    await controller.fire_event(MyEvent.TIMER)
    assert controller.state == MyState.UNOCCUPIED
    controller.async_unload()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [STATE_UNAVAILABLE, STATE_UNKNOWN, None],
    ids=["unavailable", "unknown", "removed"],
)
async def test_lost_sustain_starts_grace_without_trigger(
    hass: HomeAssistant, failure: str | None
):
    """Loss of the last sustain starts a grace timer, not an indefinite hold."""
    sustain = "binary_sensor.office_mmwave"
    hass.states.async_set(sustain, STATE_ON)
    controller = OccupancyController(
        hass, _entry({Config.SUSTAIN_ENTITIES: [sustain], Config.DECAY_MINUTES: 2})
    )
    await controller.async_setup(hass)
    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert controller.timer_expires_at is None

    await _lose_entity(hass, sustain, failure)
    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert controller.timer_expires_at is not None
    assert controller.diagnostic_attributes["last_sustain_entity"] == sustain

    await controller.fire_event(MyEvent.TIMER)
    assert controller.state == MyState.UNOCCUPIED
    controller.async_unload()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "failure", [STATE_UNAVAILABLE, STATE_UNKNOWN, None],
    ids=["unavailable", "unknown", "removed"],
)
async def test_lost_sustain_hands_back_to_active_trigger(
    hass: HomeAssistant, failure: str | None
):
    """If PIR is still on, losing mmWave immediately hands control to PIR."""
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
                Config.DECAY_MINUTES: 2,
            }
        ),
    )
    await controller.async_setup(hass)
    assert controller.state == MyState.SUSTAINED_OCCUPIED

    await _lose_entity(hass, sustain, failure)
    assert controller.state == MyState.TRIGGERED_OCCUPIED
    assert controller.timer_expires_at is None
    controller.async_unload()


@pytest.mark.asyncio
async def test_losing_one_of_two_sustains_does_not_start_grace(hass: HomeAssistant):
    """One failed mmWave must not override another active sustain."""
    sustain_a = "binary_sensor.mmwave_a"
    sustain_b = "binary_sensor.mmwave_b"
    hass.states.async_set(sustain_a, STATE_ON)
    hass.states.async_set(sustain_b, STATE_ON)
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.SUSTAIN_ENTITIES: [sustain_a, sustain_b],
                Config.DECAY_MINUTES: 2,
            }
        ),
    )
    await controller.async_setup(hass)

    await _lose_entity(hass, sustain_a, STATE_UNAVAILABLE)
    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert controller.timer_expires_at is None

    await _lose_entity(hass, sustain_b, STATE_UNAVAILABLE)
    assert controller.state == MyState.SUSTAINED_OCCUPIED
    assert controller.timer_expires_at is not None
    controller.async_unload()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("required_key", "expected"),
    [
        (Config.REQUIRED_ON_ENTITIES, STATE_ON),
        (Config.REQUIRED_OFF_ENTITIES, STATE_OFF),
    ],
    ids=["required_on", "required_off"],
)
@pytest.mark.parametrize(
    "failure", [STATE_UNAVAILABLE, STATE_UNKNOWN, None],
    ids=["unavailable", "unknown", "removed"],
)
async def test_lost_required_entity_clears_triggered_occupancy_immediately(
    hass: HomeAssistant,
    required_key: str,
    expected: str,
    failure: str | None,
):
    """Every required condition is a hard gate, including when it disappears."""
    trigger = "binary_sensor.office_pir"
    required = "binary_sensor.requirement"
    hass.states.async_set(trigger, STATE_ON)
    hass.states.async_set(required, expected)
    controller = OccupancyController(
        hass,
        _entry({Config.TRIGGER_ENTITIES: [trigger], required_key: [required]}),
    )
    await controller.async_setup(hass)
    assert controller.state == MyState.TRIGGERED_OCCUPIED

    await _lose_entity(hass, required, failure)
    assert controller.state == MyState.UNOCCUPIED
    assert controller.timer_expires_at is None
    assert controller.diagnostic_attributes["required_satisfied"] is False
    assert controller.diagnostic_attributes["last_required_entity"] == required
    controller.async_unload()


@pytest.mark.asyncio
async def test_lost_required_entity_clears_sustained_and_recovers(
    hass: HomeAssistant,
):
    """Required sensor loss clears sustained occupancy; recovery can restore it."""
    sustain = "binary_sensor.office_mmwave"
    required = "binary_sensor.requirement"
    hass.states.async_set(sustain, STATE_ON)
    hass.states.async_set(required, STATE_ON)
    controller = OccupancyController(
        hass,
        _entry(
            {
                Config.SUSTAIN_ENTITIES: [sustain],
                Config.REQUIRED_ON_ENTITIES: [required],
            }
        ),
    )
    await controller.async_setup(hass)
    assert controller.state == MyState.SUSTAINED_OCCUPIED

    await _lose_entity(hass, required, STATE_UNAVAILABLE)
    assert controller.state == MyState.UNOCCUPIED
    assert controller.timer_expires_at is None

    hass.states.async_set(required, STATE_ON)
    await hass.async_block_till_done()
    assert controller.state == MyState.SUSTAINED_OCCUPIED
    controller.async_unload()
