"""Representation of a Ceiling Fan Controller."""

from __future__ import annotations

import enum
from datetime import datetime, timedelta

from homeassistant.components.fan import (
    ATTR_PERCENTAGE,
    ATTR_PERCENTAGE_STEP,
    SERVICE_SET_PERCENTAGE,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, STATE_OFF, STATE_ON, Platform
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.event import async_track_time_interval

from .const import _LOGGER, ON_OFF_STATES, Config
from .smartify import SmartifyBase
from .util import extrapolate_value, float_with_unit, remove_empty, summer_simmer_index


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


class SmartCeilingFan(SmartifyBase):
    """Representation of a Ceiling Fan Controller."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the controller."""
        super().__init__(hass, entry, MyState.INIT)

        self.temp_sensor: str = self.data[Config.TEMP_SENSOR]
        self.humidity_sensor: str = self.data[Config.HUMIDITY_SENSOR]

        self.ssi_range = (
            float(self.data[Config.SSI_MIN]),
            float(self.data[Config.SSI_MAX]),
        )

        self.speed_range = (
            float(self.data[Config.SPEED_MIN]),
            float(self.data[Config.SPEED_MAX]),
        )

        manual_control_minutes = self.data.get(Config.MANUAL_CONTROL_MINUTES)
        self._manual_control_period = (
            timedelta(minutes=manual_control_minutes)
            if manual_control_minutes
            else None
        )

        required_on_entities: list[str] = self.data.get(Config.REQUIRED_ON_ENTITIES, [])
        required_off_entities: list[str] = self.data.get(
            Config.REQUIRED_OFF_ENTITIES, []
        )
        self._required = {
            **{k: STATE_ON for k in required_on_entities},
            **{k: STATE_OFF for k in required_off_entities},
        }
        self._required_states: dict[str, str | None] = {k: None for k in self._required}

        self._temp: tuple[float, str] | None = None
        self._humidity: tuple[float, str] | None = None

        self.tracked_entity_ids = remove_empty(
            [
                self.controlled_entity,
                self.temp_sensor,
                self.humidity_sensor,
                *self._required,
            ]
        )

    async def async_setup(self, hass) -> None:
        """Additional setup unique to this controller."""
        await super().async_setup(hass)
        self._unsubscribers.append(
            async_track_time_interval(hass, self._on_poll, timedelta(seconds=60))
        )
        await self.fire_event(MyEvent.REFRESH)

    async def on_state_change(self, state: State) -> None:
        """Handle entity state changes from base."""
        if state.entity_id == self.controlled_entity and state.state in ON_OFF_STATES:
            await self.fire_event(
                MyEvent.ON if state.state == STATE_ON else MyEvent.OFF
            )

        elif state.entity_id == self.temp_sensor:
            self._temp = float_with_unit(state, self.hass.config.units.temperature_unit)

        elif state.entity_id == self.humidity_sensor:
            self._humidity = float_with_unit(state, PERCENTAGE)

        elif state.entity_id in self._required_states:
            if state.state in ON_OFF_STATES:
                self._required_states[state.entity_id] = state.state
                await self.fire_event(MyEvent.REFRESH)

    async def on_timer_expired(self) -> None:
        """Handle timer expiration from base."""
        await self.fire_event(MyEvent.TIMER)

    async def _on_poll(self, _: datetime) -> None:
        _LOGGER.debug("%s; state=%s; polling for changes", self.name, self._state)
        await self.fire_event(MyEvent.REFRESH)

    async def on_event(self, event: MyEvent) -> None:
        """Handle controller events."""

        async def update_fan_speed() -> bool:
            if self._temp is None or self._humidity is None:
                return False

            ssi = summer_simmer_index(self.hass, self._temp, self._humidity[0])
            ssi_speed = extrapolate_value(
                ssi, self.ssi_range, self.speed_range, low_default=0
            )

            assert self.controlled_entity
            fan_state = self.hass.states.get(self.controlled_entity)

            assert fan_state
            speed_step = fan_state.attributes.get(ATTR_PERCENTAGE_STEP, 100)

            curr_speed = int(
                fan_state.attributes.get(ATTR_PERCENTAGE, 100)
                if fan_state.state == STATE_ON
                else 0
            )

            new_speed = (
                int(round(ssi_speed // speed_step * speed_step, 3))
                if self._required_states == self._required
                else 0
            )

            if new_speed != curr_speed:
                _LOGGER.debug(
                    "%s; state=%s; changing speed to %d percent for SSI=%.1f",
                    self.name,
                    self._state,
                    new_speed,
                    ssi,
                )

                await self.async_service_call(
                    Platform.FAN,
                    SERVICE_SET_PERCENTAGE,
                    {ATTR_PERCENTAGE: new_speed},
                )

            return new_speed > 0

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
                if fan_on := await update_fan_speed():
                    self.set_state(MyState.ON)

            case (MyState.ON, MyEvent.OFF):
                self.set_state(
                    MyState.OFF_MANUAL if self._manual_control_period else MyState.OFF
                )
                self.set_timer(self._manual_control_period)

            case (MyState.ON, MyEvent.REFRESH):
                if not (fan_on := await update_fan_speed()):
                    self.set_state(MyState.OFF)

            case (MyState.OFF_MANUAL, MyEvent.ON):
                self.set_timer(None)
                fan_on = await update_fan_speed()
                self.set_state(MyState.ON if fan_on else MyState.OFF)

            case (MyState.OFF_MANUAL, MyEvent.TIMER):
                fan_on = await update_fan_speed()
                self.set_state(MyState.ON if fan_on else MyState.OFF)

            case (MyState.ON_MANUAL, MyEvent.OFF):
                self.set_timer(None)
                fan_on = await update_fan_speed()
                self.set_state(MyState.ON if fan_on else MyState.OFF)

            case (MyState.ON_MANUAL, MyEvent.TIMER):
                fan_on = await update_fan_speed()
                self.set_state(MyState.ON if fan_on else MyState.OFF)

            case _:
                _LOGGER.debug(
                    "%s; state=%s; ignored '%s' event",
                    self.name,
                    self._state,
                    event,
                )
