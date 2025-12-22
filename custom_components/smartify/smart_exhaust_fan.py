"""Representation of an Exhaust Fan Controller."""

from __future__ import annotations

import enum
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    Platform,
)
from homeassistant.core import HomeAssistant, State

from .const import _LOGGER, ON_OFF_STATES, Config
from .smartify import SmartBase
from .util import absolute_humidity, float_with_unit, remove_empty


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
    TIMER = "timer"
    REFRESH = "refresh"


class SmartExhaustFan(SmartBase):
    """Representation of an Exhaust Fan Controller."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the controller."""
        super().__init__(hass, entry, MyState.INIT)

        self.temp_sensor: str = self.data[Config.TEMP_SENSOR]
        self.humidity_sensor: str = self.data[Config.HUMIDITY_SENSOR]
        self.ref_temp_sensor: str = self.data[Config.REFERENCE_TEMP_SENSOR]
        self.ref_humidity_sensor: str = self.data[Config.REFERENCE_HUMIDITY_SENSOR]

        self.falling_threshold: float = self.data[Config.FALLING_THRESHOLD]
        self.rising_threshold: float = self.data[Config.RISING_THRESHOLD]

        manual_control_minutes = self.data.get(Config.MANUAL_CONTROL_MINUTES)
        self._manual_control_period = (
            timedelta(minutes=manual_control_minutes)
            if manual_control_minutes
            else None
        )

        self._temp: tuple[float, str] | None = None
        self._humidity: tuple[float, str] | None = None
        self._ref_temp: tuple[float, str] | None = None
        self._ref_humidity: tuple[float, str] | None = None

        self.tracked_entity_ids = remove_empty(
            [
                self.controlled_entity,
                self.temp_sensor,
                self.humidity_sensor,
                self.ref_temp_sensor,
                self.ref_humidity_sensor,
            ]
        )

    async def async_setup(self, hass) -> None:
        """Additional setup unique to this controller."""
        await super().async_setup(hass)
        await self.fire_event(MyEvent.REFRESH)

    async def on_state_change(self, state: State) -> None:
        """Handle entity state changes from base."""
        match state.entity_id:
            case self.controlled_entity if state.state in ON_OFF_STATES:
                await self.fire_event(
                    MyEvent.ON if state.state == STATE_ON else MyEvent.OFF
                )

            case self.temp_sensor:
                self._temp = float_with_unit(
                    state, self.hass.config.units.temperature_unit
                )
                await self.fire_event(MyEvent.REFRESH)

            case self.humidity_sensor:
                self._humidity = float_with_unit(state, PERCENTAGE)
                await self.fire_event(MyEvent.REFRESH)

            case self.ref_temp_sensor:
                self._ref_temp = float_with_unit(
                    state, self.hass.config.units.temperature_unit
                )
                await self.fire_event(MyEvent.REFRESH)

            case self.ref_humidity_sensor:
                self._ref_humidity = float_with_unit(state, PERCENTAGE)
                await self.fire_event(MyEvent.REFRESH)

    async def on_timer_expired(self) -> None:
        """Handle timer expiration from base."""
        await self.fire_event(MyEvent.TIMER)

    async def on_event(self, event: MyEvent) -> None:
        """Handle controller events."""

        async def set_fan_mode() -> bool:
            if (
                self._temp is None
                or self._humidity is None
                or self._ref_temp is None
                or self._ref_humidity is None
            ):
                return False

            abs_hum = absolute_humidity(self._temp, self._humidity[0])
            ref_abs_hum = absolute_humidity(self._ref_temp, self._ref_humidity[0])
            difference = abs_hum - ref_abs_hum

            assert self.controlled_entity
            fan_state = self.hass.states.get(self.controlled_entity)

            assert fan_state
            curr_mode = fan_state.state

            if curr_mode == STATE_OFF and difference > self.rising_threshold:
                new_mode = STATE_ON
            elif curr_mode == STATE_ON and difference < self.falling_threshold:
                new_mode = STATE_OFF
            else:
                new_mode = curr_mode

            if new_mode != curr_mode:
                await self.async_service_call(
                    Platform.FAN,
                    SERVICE_TURN_ON if new_mode == STATE_ON else SERVICE_TURN_OFF,
                )

            return new_mode == STATE_ON

        match (self._state, event):
            case (MyState.INIT, MyEvent.OFF):
                self.set_state(MyState.OFF)

            case (MyState.INIT, MyEvent.ON):
                self.set_state(MyState.ON)

            case (MyState.OFF, MyEvent.ON):
                self.set_state(
                    MyState.ON_MANUAL if self._manual_control_period else MyState.ON
                )
                self.set_timer(self._manual_control_period)

            case (MyState.OFF, MyEvent.REFRESH):
                if fan_on := await set_fan_mode():
                    self.set_state(MyState.ON)

            case (MyState.ON, MyEvent.OFF):
                self.set_state(
                    MyState.OFF_MANUAL if self._manual_control_period else MyState.OFF
                )
                self.set_timer(self._manual_control_period)

            case (MyState.ON, MyEvent.REFRESH):
                if not (fan_on := await set_fan_mode()):
                    self.set_state(MyState.OFF)

            case (MyState.OFF_MANUAL, MyEvent.ON):
                self.set_timer(None)
                fan_on = await set_fan_mode()
                self.set_state(MyState.ON if fan_on else MyState.OFF)

            case (MyState.OFF_MANUAL, MyEvent.TIMER):
                fan_on = await set_fan_mode()
                self.set_state(MyState.ON if fan_on else MyState.OFF)

            case (MyState.ON_MANUAL, MyEvent.OFF):
                self.set_timer(None)
                fan_on = await set_fan_mode()
                self.set_state(MyState.ON if fan_on else MyState.OFF)

            case (MyState.ON_MANUAL, MyEvent.TIMER):
                fan_on = await set_fan_mode()
                self.set_state(MyState.ON if fan_on else MyState.OFF)

            case _:
                _LOGGER.debug(
                    "%s; state=%s; ignored '%s' event",
                    self.name,
                    self._state,
                    event,
                )
