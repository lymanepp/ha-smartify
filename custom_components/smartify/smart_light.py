"""Representation of a Light Controller."""

from __future__ import annotations

import enum
from datetime import timedelta

from homeassistant.components.light import ATTR_BRIGHTNESS_PCT
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant, State

from .const import _LOGGER, ON_OFF_STATES, Config
from .smartify import SmartifyBase
from .util import remove_empty


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


class SmartLight(SmartifyBase):
    """Representation of a Light Controller."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the Light Controller."""
        super().__init__(hass, entry, MyState.INIT)

        self.brightness_pct: float | None = self.data.get(Config.BRIGHTNESS_PCT)
        self.trigger_entity: str | None = self.data.get(Config.TRIGGER_ENTITY)
        self.illuminance_sensor: str | None = self.data.get(Config.ILLUMINANCE_SENSOR)
        self.illuminance_cutoff: int | None = self.data.get(Config.ILLUMINANCE_CUTOFF)

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
            ]
        )

    async def on_state_change(self, state: State) -> None:
        """Handle entity state changes from base."""
        if state.entity_id == self.controlled_entity:
            if state.state in ON_OFF_STATES:
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

    async def on_timer_expired(self) -> None:
        """Handle timer expiration from base."""
        await self.fire_event(MyEvent.TIMER)

    async def on_event(self, event: MyEvent) -> None:
        """Handle controller events."""

        def acceptable_illuminance():
            if self.illuminance_sensor and self.illuminance_cutoff is not None:
                state = self.hass.states.get(self.illuminance_sensor)
                if state and state.state is not None:
                    return float(state.state) <= self.illuminance_cutoff
            return True

        def have_required() -> bool:
            actual: dict[str, str | None] = {}
            for entity in self._required:
                state = self.hass.states.get(entity)
                actual[entity] = state.state if state else None
            return actual == self._required

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

            case (MyState.INIT, MyEvent.ON) | (MyState.OFF, MyEvent.ON):
                if self.is_entity_state(self.trigger_entity, STATE_ON):
                    self.set_state(MyState.ON)
                else:
                    self.set_state(MyState.ON_MANUAL)
                    self.set_timer(self._auto_off_period)

            case (MyState.OFF, MyEvent.TRIGGER_ON):
                if acceptable_illuminance() and have_required():
                    self.set_state(MyState.ON)
                    await set_light_mode(STATE_ON)

            case (MyState.ON, MyEvent.OFF):
                if self.is_entity_state(self.trigger_entity, STATE_OFF):
                    self.set_state(MyState.OFF)
                else:
                    self.set_state(MyState.OFF_MANUAL)
                    self.set_timer(None)

            case (MyState.ON, MyEvent.TRIGGER_OFF):
                self.set_state(MyState.OFF)
                self.set_timer(None)
                await set_light_mode(STATE_OFF)

            case (MyState.ON, MyEvent.TIMER):
                self.set_state(MyState.OFF)
                await set_light_mode(STATE_OFF)

            case (MyState.OFF_MANUAL, MyEvent.ON):
                self.set_state(MyState.ON)

            case (MyState.OFF_MANUAL, MyEvent.TRIGGER_OFF):
                self.set_state(MyState.OFF)

            case (MyState.ON_MANUAL, MyEvent.OFF):
                self.set_state(MyState.OFF)
                self.set_timer(None)

            case (MyState.ON_MANUAL, MyEvent.TRIGGER_ON):
                self.set_state(MyState.ON)
                self.set_timer(None)

            case (MyState.ON_MANUAL, MyEvent.TIMER):
                self.set_state(MyState.OFF)
                await set_light_mode(STATE_OFF)

            case _:
                _LOGGER.debug(
                    "%s; state=%s; ignored '%s' event",
                    self.name,
                    self._state,
                    event,
                )
