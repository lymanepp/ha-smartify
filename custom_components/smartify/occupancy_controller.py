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
    TRIGGERED_OCCUPIED = "triggered_occupied"
    SUSTAINED_OCCUPIED = "sustained_occupied"


class MyEvent(enum.StrEnum):
    """State machine events."""

    TRIGGER = "trigger"
    SUSTAIN = "sustain"
    REQUIRED = "required"
    TIMER = "timer"


ON_STATES: Final = {
    MyState.TRIGGERED_OCCUPIED,
    MyState.SUSTAINED_OCCUPIED,
}


class OccupancyController(SmartifyController):
    """Representation of an Occupancy Controller.

    This controller uses a simple two-role, three-state occupancy model.

    Roles:

    * Triggers: entities that are allowed to start occupancy. These are usually
      PIR or motion sensors.
    * Sustains: entities that are allowed to maintain occupancy. These are
      usually mmWave, presence, BLE room-presence, or other reliable
      still-present signals.

    States:

    * unoccupied: no occupancy is currently detected.
    * triggered_occupied: occupancy was started by a trigger and is held by the
      configured trigger decay timer.
    * sustained_occupied: occupancy is being maintained by one or more active
      sustain entities.

    Rules:

    * If triggers are configured, only a trigger turning on may enter occupancy
      from the unoccupied state. Sustains cannot create occupancy while vacant.
    * If triggers are configured, decay_minutes is expected to be configured.
      Every trigger-on event starts or restarts that decay timer.
    * In triggered_occupied, any sustain turning on immediately transitions to
      sustained_occupied and cancels the decay timer.
    * If the trigger decay timer expires before any sustain turns on, occupancy
      exits to unoccupied.
    * In sustained_occupied, occupancy exits when all sustain entities are off.
    * If no triggers are configured, any sustain turning on enters
      sustained_occupied, and occupancy follows the sustain entities directly.
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

        self._decay_minutes = self.data.get(Config.DECAY_MINUTES, 1)
        self._trigger_decay_period = timedelta(minutes=self._decay_minutes)

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
        """Return the status of the binary occupancy sensor."""
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
        """Return diagnostic attributes for the controller state sensor."""
        return {
            "strategy": self.occupancy_strategy,
            "trigger_entities": self._trigger_entities,
            "sustain_entities": self._sustain_entities,
            "active_trigger_entities": self.active_trigger_entities,
            "active_sustain_entities": self.active_sustain_entities,
            "required_entities": self._required,
            "required_satisfied": self.required_satisfied,
            "decay_minutes": self._decay_minutes,
            "last_event": self._last_event.value if self._last_event else None,
            "last_trigger_entity": self._last_trigger_entity,
            "last_sustain_entity": self._last_sustain_entity,
            "last_required_entity": self._last_required_entity,
        }

    async def on_state_change(self, state: State) -> None:
        """Handle entity state changes from base."""
        if state.entity_id in self._trigger_entities:
            self._last_trigger_entity = state.entity_id

            if state.state == STATE_ON:
                await self.fire_event(MyEvent.TRIGGER)

        elif state.entity_id in self._sustain_entities:
            if state.state in ON_OFF_STATES:
                self._last_sustain_entity = state.entity_id
                await self.fire_event(MyEvent.SUSTAIN)

        elif state.entity_id in self._required:
            if state.state in ON_OFF_STATES:
                self._last_required_entity = state.entity_id
                await self.fire_event(MyEvent.REQUIRED)

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

    def _have_triggers(self) -> bool:
        """Return whether trigger entities are configured."""
        return bool(self._trigger_entities)

    def _have_sustains(self) -> bool:
        """Return whether sustain entities are configured."""
        return bool(self._sustain_entities)

    def _have_active_sustain(self) -> bool:
        """Return whether any configured sustain entity is currently on."""
        return bool(self.active_sustain_entities)

    def _have_required(self) -> bool:
        """Return whether the required entity states match configuration."""
        actual: dict[str, str | None] = {}
        for entity in self._required:
            state = self.hass.states.get(entity)
            actual[entity] = state.state if state else None
        return actual == self._required

    def _enter_unoccupied_state(self) -> None:
        """Enter the unoccupied state and cancel any active timer."""
        self.set_timer(None)
        self.set_state(MyState.UNOCCUPIED)

    def _enter_triggered_occupied_state(self) -> None:
        """Enter triggered occupancy and start/restart the trigger decay timer."""
        self.set_timer(self._trigger_decay_period)
        self.set_state(MyState.TRIGGERED_OCCUPIED)

    def _enter_sustained_occupied_state(self) -> None:
        """Enter sustained occupancy and cancel any trigger decay timer."""
        self.set_timer(None)
        self.set_state(MyState.SUSTAINED_OCCUPIED)

    def _reevaluate_sustained_occupied_state(self) -> None:
        """Stay sustained while requirements and at least one sustain are active."""
        if not self._have_required():
            self._enter_unoccupied_state()
            return

        if not self._have_active_sustain():
            self._enter_unoccupied_state()

    async def on_event(self, event: MyEvent) -> None:
        """Handle controller events."""
        original_state = self._state
        self._last_event = event

        match (self._state, event):
            case (MyState.UNOCCUPIED, MyEvent.TRIGGER):
                if self._have_triggers() and self._have_required():
                    self._enter_triggered_occupied_state()

            case (MyState.UNOCCUPIED, MyEvent.SUSTAIN):
                if (
                    not self._have_triggers()
                    and self._have_active_sustain()
                    and self._have_required()
                ):
                    self._enter_sustained_occupied_state()

            case (MyState.UNOCCUPIED, MyEvent.REQUIRED):
                if (
                    not self._have_triggers()
                    and self._have_active_sustain()
                    and self._have_required()
                ):
                    self._enter_sustained_occupied_state()

            case (MyState.TRIGGERED_OCCUPIED, MyEvent.TRIGGER):
                if self._have_required():
                    self._enter_triggered_occupied_state()

            case (MyState.TRIGGERED_OCCUPIED, MyEvent.SUSTAIN):
                if not self._have_required():
                    self._enter_unoccupied_state()
                elif self._have_active_sustain():
                    self._enter_sustained_occupied_state()

            case (MyState.TRIGGERED_OCCUPIED, MyEvent.REQUIRED):
                if not self._have_required():
                    self._enter_unoccupied_state()
                elif self._have_active_sustain():
                    self._enter_sustained_occupied_state()

            case (MyState.TRIGGERED_OCCUPIED, MyEvent.TIMER):
                if self._have_required() and self._have_active_sustain():
                    # Defensive handoff in case a sustain was already on but its
                    # state-change event was missed or processed before the trigger.
                    self._enter_sustained_occupied_state()
                else:
                    self._enter_unoccupied_state()

            case (MyState.SUSTAINED_OCCUPIED, MyEvent.SUSTAIN):
                self._reevaluate_sustained_occupied_state()

            case (MyState.SUSTAINED_OCCUPIED, MyEvent.REQUIRED):
                self._reevaluate_sustained_occupied_state()

            case _:
                _LOGGER.debug(
                    "%s; state=%s; ignored '%s' event",
                    self.name,
                    self._state,
                    event,
                )

        if self._state == original_state:
            self._update_listeners()
