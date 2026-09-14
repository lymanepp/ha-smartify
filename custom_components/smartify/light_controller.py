"""Representation of a Light Controller."""

from __future__ import annotations

import enum
from datetime import timedelta

from homeassistant.components.light import ATTR_BRIGHTNESS_PCT
from homeassistant.const import (
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant, State

from .const import _LOGGER, ON_OFF_STATES, Config
from .entry_types import SmartifyEntrySource
from .smartify_controller import SmartifyController
from .util import is_number, remove_empty


class MyState(enum.StrEnum):
    """State machine states."""

    INIT = "init"
    OFF = "off"
    ON = "on"
    ON_MANUAL = "on_manual"
    OFF_MANUAL = "off_manual"


class MyEvent(enum.StrEnum):
    """State machine events."""

    OFF = "off"
    ON = "on"
    TRIGGER_OFF = "trigger_off"
    TRIGGER_ON = "trigger_on"
    TIMER = "timer"


class LightController(SmartifyController):
    """Representation of a Light Controller."""

    def __init__(self, hass: HomeAssistant, config_entry: SmartifyEntrySource) -> None:
        """Initialize the Light Controller."""
        super().__init__(hass, config_entry, MyState.INIT)

        self.brightness_pct: float | None = self.data.get(Config.BRIGHTNESS_PCT)
        self.trigger_entity: str | None = self.data.get(Config.TRIGGER_ENTITY)
        self.illuminance_sensor: str | None = self.data.get(Config.ILLUMINANCE_SENSOR)
        self.illuminance_cutoff: int | None = self.data.get(Config.ILLUMINANCE_CUTOFF)
        self._cached_illuminance: float | None = None

        required_on_entities: list[str] = self.data.get(Config.REQUIRED_ON_ENTITIES, [])
        required_off_entities: list[str] = self.data.get(
            Config.REQUIRED_OFF_ENTITIES, []
        )
        auto_off_minutes: int | None = self.data.get(Config.AUTO_OFF_MINUTES)

        self._auto_off_period = (
            timedelta(minutes=auto_off_minutes) if auto_off_minutes else None
        )

        self._required = {
            **{k: STATE_ON for k in required_on_entities},
            **{k: STATE_OFF for k in required_off_entities},
        }

        self.tracked_entity_ids = remove_empty(
            [
                self.controlled_entity,
                self.trigger_entity,
                self.illuminance_sensor,
                *self._required,
            ]
        )

    async def on_state_change(self, state: State) -> None:
        """Handle entity state changes from base."""

        if state.entity_id == self.controlled_entity:
            if state.state in ON_OFF_STATES:
                self._cached_illuminance = None
                await self.fire_event(
                    MyEvent.ON if state.state == STATE_ON else MyEvent.OFF
                )

        elif state.entity_id == self.trigger_entity:
            if state.state in ON_OFF_STATES:
                await self.fire_event(
                    MyEvent.TRIGGER_ON
                    if state.state == STATE_ON
                    else MyEvent.TRIGGER_OFF
                )

        elif state.entity_id == self.illuminance_sensor:
            self._cached_illuminance = (
                float(state.state) if is_number(state.state) else None
            )

    async def on_timer_expired(self) -> None:
        """Handle timer expiration from base."""
        await self.fire_event(MyEvent.TIMER)

    def _required_states(self) -> dict[str, str | None]:
        """Return current states for all configured required entities."""
        actual: dict[str, str | None] = {}
        for entity in self._required:
            state = self.hass.states.get(entity)
            actual[entity] = state.state if state else None
        return actual

    def _required_failure(self) -> str | None:
        """Return the first unmet required condition, if any."""
        actual = self._required_states()
        for entity_id, expected in self._required.items():
            if actual[entity_id] != expected:
                return (
                    f"{entity_id} must be {expected} but is "
                    f"{actual[entity_id] or 'unknown'}"
                )
        return None

    def _set_light_diagnostics(self, reason: str, target_mode: str | None = None) -> None:
        """Publish the current light-control decision snapshot."""
        trigger_state = None
        if self.trigger_entity and (state := self.hass.states.get(self.trigger_entity)):
            trigger_state = state.state

        required_states = self._required_states()
        self.set_diagnostics(
            reason,
            trigger_entity=self.trigger_entity,
            trigger_state=trigger_state,
            brightness_pct=self.brightness_pct,
            illuminance_sensor=self.illuminance_sensor,
            illuminance=self._cached_illuminance,
            illuminance_cutoff=self.illuminance_cutoff,
            required_entities=dict(self._required),
            required_states=required_states,
            required_satisfied=required_states == self._required,
            target_mode=target_mode,
            timer_expires_at=self.timer_expires_at,
        )

    async def on_event(self, event: MyEvent) -> None:
        """Handle controller events."""

        def acceptable_illuminance():
            if self.illuminance_sensor and self.illuminance_cutoff is not None:
                return (
                    self._cached_illuminance is None
                    or self._cached_illuminance <= self.illuminance_cutoff
                )

            return True

        def have_required():
            return self._required_states() == self._required

        async def set_light_mode(mode: str):
            service_data = {}
            if self.brightness_pct is not None and mode == STATE_ON:
                service_data[ATTR_BRIGHTNESS_PCT] = self.brightness_pct

            await self.async_service_call(
                Platform.LIGHT,
                SERVICE_TURN_ON if mode == STATE_ON else SERVICE_TURN_OFF,
                service_data,
            )

        match (self._state, event):
            case (MyState.INIT, MyEvent.OFF):
                self.set_state(MyState.OFF)
                self._set_light_diagnostics(
                    "STARTUP: light is off; automatic trigger control is active.",
                    STATE_OFF,
                )

            case (MyState.INIT, MyEvent.ON):
                if self.is_entity_state(self.trigger_entity, STATE_ON):
                    self.set_state(MyState.ON)
                    self._set_light_diagnostics(
                        "STARTUP: light is on and its trigger is on; Smartify is "
                        "tracking it as automatic on.",
                        STATE_ON,
                    )
                else:
                    self.set_state(MyState.ON_MANUAL)
                    self.set_timer(self._auto_off_period)
                    self._set_light_diagnostics(
                        "STARTUP MANUAL ON: light is on while its trigger is off; "
                        "Smartify is honoring the existing on state as manual.",
                        STATE_ON,
                    )

            case (MyState.OFF, MyEvent.ON):
                if self.is_entity_state(self.trigger_entity, STATE_ON):
                    self.set_state(MyState.ON)
                    self._set_light_diagnostics(
                        "EXTERNAL ON: light changed outside Smartify while its "
                        "trigger is on; automatic control continues.",
                        STATE_ON,
                    )
                else:
                    self.set_state(MyState.ON_MANUAL)
                    self.set_timer(self._auto_off_period)
                    self._set_light_diagnostics(
                        "MANUAL ON: light changed outside Smartify while its trigger "
                        "is off; automatic control resumes when the manual timer "
                        "expires or the trigger turns on.",
                        STATE_ON,
                    )

            case (MyState.OFF, MyEvent.TRIGGER_ON):
                if required_failure := self._required_failure():
                    self._set_light_diagnostics(
                        f"BLOCKED: {required_failure}; trigger did not turn the light on.",
                        STATE_OFF,
                    )
                elif not acceptable_illuminance():
                    self._set_light_diagnostics(
                        f"BLOCKED: illuminance {self._cached_illuminance:g} exceeds "
                        f"the {self.illuminance_cutoff} cutoff.",
                        STATE_OFF,
                    )
                elif have_required():
                    if self.illuminance_sensor and self._cached_illuminance is None:
                        reason = (
                            "AUTO ON: trigger is on and required conditions are "
                            "satisfied; illuminance has no usable value, so the "
                            "configured cutoff does not block activation."
                        )
                    else:
                        reason = (
                            "AUTO ON: trigger is on and all configured conditions "
                            "permit activation."
                        )
                    self.set_state(MyState.ON)
                    self._set_light_diagnostics(reason, STATE_ON)
                    await set_light_mode(STATE_ON)

            case (MyState.ON, MyEvent.OFF):
                if self.is_entity_state(self.trigger_entity, STATE_OFF):
                    self.set_state(MyState.OFF)
                    self._set_light_diagnostics(
                        "OFF: light is off and its trigger is off; automatic control "
                        "is idle.",
                        STATE_OFF,
                    )
                else:
                    self.set_state(MyState.OFF_MANUAL)
                    self.set_timer(None)
                    self._set_light_diagnostics(
                        "MANUAL OFF: light changed outside Smartify while its trigger "
                        "remains on; automatic-on is suppressed until the trigger clears.",
                        STATE_OFF,
                    )

            case (MyState.ON, MyEvent.TRIGGER_OFF):
                self.set_state(MyState.OFF)
                self.set_timer(None)
                self._set_light_diagnostics(
                    "AUTO OFF: trigger turned off, so Smartify turned the light off.",
                    STATE_OFF,
                )
                await set_light_mode(STATE_OFF)

            case (MyState.ON, MyEvent.TIMER):
                self.set_state(MyState.OFF)
                self._set_light_diagnostics(
                    "AUTO OFF: the active timer expired, so Smartify turned the light off.",
                    STATE_OFF,
                )
                await set_light_mode(STATE_OFF)

            case (MyState.OFF_MANUAL, MyEvent.ON):
                self.set_state(MyState.ON)
                self._set_light_diagnostics(
                    "MANUAL OFF CANCELLED: light was turned back on while its trigger "
                    "is active; automatic control resumed.",
                    STATE_ON,
                )

            case (MyState.OFF_MANUAL, MyEvent.TRIGGER_OFF):
                self.set_state(MyState.OFF)
                self._set_light_diagnostics(
                    "OFF: trigger cleared after a manual-off override; automatic "
                    "control is ready for the next trigger.",
                    STATE_OFF,
                )

            case (MyState.ON_MANUAL, MyEvent.OFF):
                self.set_state(MyState.OFF)
                self.set_timer(None)
                self._set_light_diagnostics(
                    "MANUAL OFF: manually-on light was turned off before its timer expired.",
                    STATE_OFF,
                )

            case (MyState.ON_MANUAL, MyEvent.TRIGGER_ON):
                self.set_state(MyState.ON)
                self.set_timer(None)
                self._set_light_diagnostics(
                    "AUTO TAKEOVER: trigger turned on while the light was manually on; "
                    "Smartify resumed automatic control.",
                    STATE_ON,
                )

            case (MyState.ON_MANUAL, MyEvent.TIMER):
                self.set_state(MyState.OFF)
                self._set_light_diagnostics(
                    "AUTO OFF: manual-on timer expired, so Smartify turned the light off.",
                    STATE_OFF,
                )
                await set_light_mode(STATE_OFF)

            case _:
                _LOGGER.debug(
                    "%s; state=%s; ignored '%s' event",
                    self.name,
                    self._state,
                    event,
                )
