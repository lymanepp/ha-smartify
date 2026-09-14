"""Representation of a Ceiling Fan Controller."""

from __future__ import annotations

import enum
from datetime import datetime, timedelta

from homeassistant.components.fan import (
    ATTR_PERCENTAGE,
    ATTR_PERCENTAGE_STEP,
    SERVICE_SET_PERCENTAGE,
)
from homeassistant.const import PERCENTAGE, STATE_OFF, STATE_ON, Platform
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers.event import async_track_time_interval

from .const import _LOGGER, ON_OFF_STATES, Config
from .entry_types import SmartifyEntrySource
from .smartify_controller import SmartifyController
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


class CeilingFanController(SmartifyController):
    """Representation of a Ceiling Fan Controller."""

    def __init__(self, hass: HomeAssistant, config_entry: SmartifyEntrySource) -> None:
        """Initialize the controller."""
        super().__init__(hass, config_entry, MyState.INIT)

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

        _LOGGER.debug(
            "%s; registering poll timer controller=%s interval=60s",
            self.name,
            id(self),
        )

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

    def _manual_reason(self, mode: str) -> str:
        """Return a concise explanation for a manual fan state."""
        if self._manual_control_period is None:
            return (
                f"EXTERNAL {mode.upper()}: fan changed outside Smartify; "
                "automatic control remains active."
            )

        return (
            f"MANUAL {mode.upper()}: fan changed outside Smartify; automatic "
            "control resumes when the manual-control timer expires."
        )

    def _required_failure(self) -> str | None:
        """Return the first unmet required condition, if any."""
        for entity_id, expected in self._required.items():
            actual = self._required_states.get(entity_id)
            if actual != expected:
                return f"{entity_id} must be {expected} but is {actual or 'unknown'}"
        return None

    def _set_manual_diagnostics(self, mode: str) -> None:
        """Publish a manual-control decision snapshot."""
        self.set_diagnostics(
            self._manual_reason(mode),
            observed_mode=mode,
            timer_expires_at=self.timer_expires_at,
            required_satisfied=self._required_states == self._required,
            required_states=dict(self._required_states),
        )

    async def on_event(self, event: MyEvent) -> None:
        """Handle controller events."""

        async def update_fan_speed() -> bool:
            if self._temp is None or self._humidity is None:
                missing = []
                if self._temp is None:
                    missing.append(self.temp_sensor)
                if self._humidity is None:
                    missing.append(self.humidity_sensor)
                self.set_diagnostics(
                    "WAITING: cannot calculate fan speed because "
                    + ", ".join(missing)
                    + " has no usable value.",
                    temperature=self._temp[0] if self._temp else None,
                    humidity=self._humidity[0] if self._humidity else None,
                    required_satisfied=self._required_states == self._required,
                    required_states=dict(self._required_states),
                )
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

            required_satisfied = self._required_states == self._required
            new_speed = (
                int(round(ssi_speed // speed_step * speed_step, 3))
                if required_satisfied
                else 0
            )

            if required_failure := self._required_failure():
                reason = f"BLOCKED: {required_failure}; target speed is 0%."
            elif ssi < self.ssi_range[0]:
                reason = (
                    f"AUTO OFF: SSI {ssi:.1f} is below the {self.ssi_range[0]:.1f} "
                    "minimum; target speed is 0%."
                )
            elif new_speed == 0 and ssi_speed > 0:
                reason = (
                    f"AUTO OFF: SSI {ssi:.1f} maps to {ssi_speed:.1f}%; quantized "
                    f"to 0% for the fan's {speed_step:g}% speed step."
                )
            else:
                reason = (
                    f"AUTO: SSI {ssi:.1f} maps to {ssi_speed:.1f}%; target is "
                    f"{new_speed}% after {speed_step:g}% fan-step quantization."
                )

            self.set_diagnostics(
                reason,
                temperature=round(self._temp[0], 2),
                humidity=round(self._humidity[0], 2),
                ssi=round(ssi, 2),
                ssi_min=self.ssi_range[0],
                ssi_max=self.ssi_range[1],
                calculated_speed=round(ssi_speed, 2),
                target_speed=new_speed,
                observed_speed=curr_speed,
                speed_step=speed_step,
                required_satisfied=required_satisfied,
                required_states=dict(self._required_states),
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
                self.set_diagnostics(
                    "STARTUP: fan is off; automatic SSI control is active.",
                    observed_mode=STATE_OFF,
                    required_satisfied=self._required_states == self._required,
                    required_states=dict(self._required_states),
                )

            case (MyState.INIT, MyEvent.ON):
                self.set_state(MyState.ON)
                self.set_diagnostics(
                    "STARTUP: fan is on; automatic SSI control is active.",
                    observed_mode=STATE_ON,
                    required_satisfied=self._required_states == self._required,
                    required_states=dict(self._required_states),
                )

            case (MyState.OFF, MyEvent.ON):
                self.set_state(
                    MyState.ON_MANUAL if self._manual_control_period else MyState.ON
                )
                self.set_timer(self._manual_control_period)
                self._set_manual_diagnostics(STATE_ON)

            case (MyState.OFF, MyEvent.REFRESH):
                if fan_on := await update_fan_speed():
                    self.set_state(MyState.ON)

            case (MyState.ON, MyEvent.OFF):
                self.set_state(
                    MyState.OFF_MANUAL if self._manual_control_period else MyState.OFF
                )
                self.set_timer(self._manual_control_period)
                self._set_manual_diagnostics(STATE_OFF)

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
