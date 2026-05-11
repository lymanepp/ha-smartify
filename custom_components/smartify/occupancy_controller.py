"""Representation of an Occupancy Controller."""

from __future__ import annotations

import enum
from datetime import timedelta
from typing import Final

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant, State

from .const import _LOGGER, ON_OFF_STATES, Config
from .smartify_controller import SmartifyController
from .util import remove_empty


class MyState(enum.StrEnum):
    """State machine states."""

    UNOCCUPIED = "unoccupied"
    OCCUPIED = "occupied"


class MyEvent(enum.StrEnum):
    """State machine events."""

    TRIGGER = "trigger"
    TRIGGER_UPDATE = "trigger_update"
    SUSTAIN_UPDATE = "sustain_update"
    REQUIRED_UPDATE = "required_update"
    TIMER = "timer"


ON_STATES: Final = {MyState.OCCUPIED}


class OccupancyController(SmartifyController):
    """Representation of an Occupancy Controller.

    This controller intentionally uses a simple two-role occupancy model:

    * Triggers: entities that are allowed to start occupancy.
    * Sustains: entities that are allowed to maintain occupancy.

    Rules:

    * If one or more triggers are configured, only a trigger turning on may enter the
      occupied state. Sustains cannot create occupancy while vacant.
    * If triggers are configured and sustains are also configured, a trigger may
      start occupancy and keep it occupied while the trigger remains on. Occupancy
      exits after all triggers and all sustains are off.
    * If triggers are configured and no sustains are configured, occupancy exits
      when the decay timer expires. Each trigger that turns on while occupied
      restarts that decay timer.
    * If no triggers are configured, any sustain turning on will enter the occupied
      state, and occupancy exits as soon as all sustains are off. No timer is used.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the Occupancy Controller."""
        super().__init__(hass, config_entry, initial_state=MyState.UNOCCUPIED)

        self.name = config_entry.title

        self._trigger_entities: list[str] = self.data.get(Config.TRIGGER_ENTITIES, [])
        self._sustain_entities: list[str] = self.data.get(Config.SUSTAIN_ENTITIES, [])

        self._last_event: MyEvent | None = None
        self._last_trigger_entity: str | None = None
        self._last_sustain_entity: str | None = None
        self._last_required_entity: str | None = None

        decay_minutes = self.data.get(Config.DECAY_MINUTES)
        self._motion_off_period = (
            timedelta(minutes=decay_minutes) if decay_minutes else None
        )

        required_on_entities: list[str] = self.data.get(Config.REQUIRED_ON_ENTITIES, [])
        required_off_entities: list[str] = self.data.get(
            Config.REQUIRED_OFF_ENTITIES, []
        )
        self._required: dict[str, str] = {
            **{k: STATE_ON for k in required_on_entities},
            **{k: STATE_OFF for k in required_off_entities},
        }

        self.tracked_entity_ids = remove_empty(
            [
                self.controlled_entity,
                *self._trigger_entities,
                *self._sustain_entities,
                *self._required,
            ]
        )

    @property
    def is_on(self) -> bool:
        """Return the status of the sensor."""
        return self._state in ON_STATES

    @property
    def occupancy_strategy(self) -> str:
        """Return the configured occupancy strategy."""
        if self._trigger_entities and self._sustain_entities:
            return "trigger_and_sustain"
        if self._trigger_entities:
            return "trigger_only"
        if self._sustain_entities:
            return "sustain_only"
        return "unconfigured"

    @property
    def active_trigger_entities(self) -> list[str]:
        """Return configured trigger entities that are currently on."""
        return self._active_entities(self._trigger_entities)

    @property
    def active_sustain_entities(self) -> list[str]:
        """Return configured sustain entities that are currently on."""
        return self._active_entities(self._sustain_entities)

    @property
    def required_satisfied(self) -> bool:
        """Return whether all required entity conditions are currently satisfied."""
        return self._have_required()

    @property
    def diagnostic_attributes(self) -> dict[str, object]:
        """Return diagnostic attributes for the occupancy state sensor."""
        return {
            "strategy": self.occupancy_strategy,
            "trigger_entities": self._trigger_entities,
            "sustain_entities": self._sustain_entities,
            "active_trigger_entities": self.active_trigger_entities,
            "active_sustain_entities": self.active_sustain_entities,
            "required_entities": self._required,
            "required_satisfied": self.required_satisfied,
            "decay_minutes": self.data.get(Config.DECAY_MINUTES),
            "last_event": self._last_event.value if self._last_event else None,
            "last_trigger_entity": self._last_trigger_entity,
            "last_sustain_entity": self._last_sustain_entity,
            "last_required_entity": self._last_required_entity,
        }

    async def on_state_change(self, state: State) -> None:
        """Handle entity state changes from base."""
        if state.entity_id in self._trigger_entities:
            if state.state == STATE_ON:
                self._last_trigger_entity = state.entity_id
                await self.fire_event(MyEvent.TRIGGER)
            elif state.state in ON_OFF_STATES:
                self._last_trigger_entity = state.entity_id
                await self.fire_event(MyEvent.TRIGGER_UPDATE)

        elif state.entity_id in self._sustain_entities:
            if state.state in ON_OFF_STATES:
                self._last_sustain_entity = state.entity_id
                await self.fire_event(MyEvent.SUSTAIN_UPDATE)

        elif state.entity_id in self._required:
            if state.state in ON_OFF_STATES:
                self._last_required_entity = state.entity_id
                await self.fire_event(MyEvent.REQUIRED_UPDATE)

    async def on_timer_expired(self) -> None:
        """Handle timer expiration from base."""
        await self.fire_event(MyEvent.TIMER)

    def _active_entities(self, entities: list[str]) -> list[str]:
        """Return the entities from the provided list that are currently on."""
        active: list[str] = []
        for entity in entities:
            state = self.hass.states.get(entity)
            if state and state.state == STATE_ON:
                active.append(entity)
        return active

    def _have_required(self) -> bool:
        """Return whether the required entity states match configuration."""
        actual: dict[str, str | None] = {}
        for entity in self._required:
            state = self.hass.states.get(entity)
            actual[entity] = state.state if state else None
        return actual == self._required

    async def on_event(self, event: MyEvent) -> None:
        """Handle controller events."""
        original_state = self._state
        self._last_event = event

        def have_triggers() -> bool:
            return bool(self._trigger_entities)

        def have_sustains() -> bool:
            return bool(self._sustain_entities)

        def have_active_trigger() -> bool:
            for entity in self._trigger_entities:
                state = self.hass.states.get(entity)
                if state and state.state == STATE_ON:
                    return True
            return False

        def have_active_sustain() -> bool:
            for entity in self._sustain_entities:
                state = self.hass.states.get(entity)
                if state and state.state == STATE_ON:
                    return True
            return False

        def have_required() -> bool:
            actual: dict[str, str | None] = {}
            for entity in self._required:
                state = self.hass.states.get(entity)
                actual[entity] = state.state if state else None
            return actual == self._required

        def enter_unoccupied_state() -> None:
            self.set_timer(None)
            self.set_state(MyState.UNOCCUPIED)

        def start_trigger_decay_timer() -> None:
            self.set_timer(self._motion_off_period)

        def enter_occupied_state() -> None:
            if have_sustains():
                self.set_timer(None)
            else:
                start_trigger_decay_timer()
            self.set_state(MyState.OCCUPIED)

        def reevaluate_occupied_state() -> None:
            if not have_required():
                enter_unoccupied_state()
                return

            if have_sustains():
                if not have_active_trigger() and not have_active_sustain():
                    enter_unoccupied_state()
                return

            # No sustains configured: occupancy is controlled by trigger-created
            # decay timer only. There is nothing to reevaluate until the timer
            # expires or another trigger restarts it.

        match (self._state, event):
            case (MyState.UNOCCUPIED, MyEvent.TRIGGER):
                if have_triggers() and have_required():
                    enter_occupied_state()

            case (MyState.UNOCCUPIED, MyEvent.SUSTAIN_UPDATE):
                if not have_triggers() and have_active_sustain() and have_required():
                    enter_occupied_state()

            case (MyState.UNOCCUPIED, MyEvent.REQUIRED_UPDATE):
                if not have_triggers() and have_active_sustain() and have_required():
                    enter_occupied_state()

            case (MyState.OCCUPIED, MyEvent.TRIGGER):
                if not have_required():
                    enter_unoccupied_state()
                elif not have_sustains():
                    # Trigger-only strategy: each trigger ON event extends
                    # occupancy by restarting the decay timer.
                    start_trigger_decay_timer()
                else:
                    # Hybrid strategy: an active trigger may keep occupancy alive
                    # while sustain sensors catch up.
                    reevaluate_occupied_state()

            case (MyState.OCCUPIED, MyEvent.TRIGGER_UPDATE):
                reevaluate_occupied_state()

            case (MyState.OCCUPIED, MyEvent.SUSTAIN_UPDATE):
                reevaluate_occupied_state()

            case (MyState.OCCUPIED, MyEvent.REQUIRED_UPDATE):
                reevaluate_occupied_state()

            case (MyState.OCCUPIED, MyEvent.TIMER):
                if not have_sustains():
                    enter_unoccupied_state()
                else:
                    # A timer should not normally exist while sustains are configured,
                    # but make the event harmless if an old timer fires after a config
                    # reload or race.
                    reevaluate_occupied_state()

            case _:
                _LOGGER.debug(
                    "%s; state=%s; ignored '%s' event",
                    self.name,
                    self._state,
                    event,
                )

        if self._state == original_state:
            self._update_listeners()
