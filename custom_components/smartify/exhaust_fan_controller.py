"""Representation of an Exhaust Fan Controller."""

from __future__ import annotations

import enum
from datetime import timedelta

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
from .entry_types import SmartifyEntrySource
from .smartify_controller import SmartifyController
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


class ExhaustFanController(SmartifyController):
    """Representation of an Exhaust Fan Controller."""

    def __init__(self, hass: HomeAssistant, config_entry: SmartifyEntrySource) -> None:
        """Initialize the controller."""
        super().__init__(hass, config_entry, MyState.INIT)

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
        # NOTE: these are dotted names, so they are *value* patterns (compared
        # against state.entity_id), not capture patterns. Do not replace any of
        # these with a bare name or it will silently match everything.
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

    def _manual_reason(self, mode: str) -> str:
        """Return a concise explanation for a manual fan state."""
        if self._manual_control_period is None:
            return (
                f"EXTERNAL {mode.upper()}: fan changed outside Smartify; "
                "automatic humidity control remains active."
            )

        return (
            f"MANUAL {mode.upper()}: fan changed outside Smartify; automatic "
            "humidity control resumes when the manual-control timer expires."
        )

    def _set_manual_diagnostics(self, mode: str) -> None:
        """Publish a manual-control decision snapshot."""
        self.set_diagnostics(
            self._manual_reason(mode),
            observed_mode=mode,
            timer_expires_at=self.timer_expires_at,
            rising_threshold=self.rising_threshold,
            falling_threshold=self.falling_threshold,
        )

    async def on_event(self, event: MyEvent) -> None:
        """Handle controller events."""

        async def set_fan_mode() -> bool:
            missing = []
            if self._temp is None:
                missing.append(self.temp_sensor)
            if self._humidity is None:
                missing.append(self.humidity_sensor)
            if self._ref_temp is None:
                missing.append(self.ref_temp_sensor)
            if self._ref_humidity is None:
                missing.append(self.ref_humidity_sensor)

            if missing:
                self.set_diagnostics(
                    "WAITING: cannot evaluate humidity difference because "
                    + ", ".join(missing)
                    + " has no usable value.",
                    local_temperature=self._temp[0] if self._temp else None,
                    local_humidity=self._humidity[0] if self._humidity else None,
                    reference_temperature=(
                        self._ref_temp[0] if self._ref_temp else None
                    ),
                    reference_humidity=(
                        self._ref_humidity[0] if self._ref_humidity else None
                    ),
                    rising_threshold=self.rising_threshold,
                    falling_threshold=self.falling_threshold,
                )
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
                reason = (
                    f"AUTO ON: humidity difference {difference:+.2f} g/m³ exceeded "
                    f"the {self.rising_threshold:.2f} turn-on threshold; fan stays "
                    f"on until it falls below {self.falling_threshold:.2f}."
                )
            elif curr_mode == STATE_ON and difference < self.falling_threshold:
                new_mode = STATE_OFF
                reason = (
                    f"AUTO OFF: humidity difference {difference:+.2f} g/m³ fell "
                    f"below the {self.falling_threshold:.2f} turn-off threshold."
                )
            else:
                new_mode = curr_mode
                if curr_mode == STATE_ON:
                    reason = (
                        f"AUTO ON: humidity difference {difference:+.2f} g/m³; fan "
                        f"stays on until it falls below {self.falling_threshold:.2f}."
                    )
                else:
                    reason = (
                        f"AUTO OFF: humidity difference {difference:+.2f} g/m³; fan "
                        f"stays off until it exceeds {self.rising_threshold:.2f}."
                    )

            self.set_diagnostics(
                reason,
                local_temperature=round(self._temp[0], 2),
                local_humidity=round(self._humidity[0], 2),
                local_absolute_humidity=round(abs_hum, 3),
                reference_temperature=round(self._ref_temp[0], 2),
                reference_humidity=round(self._ref_humidity[0], 2),
                reference_absolute_humidity=round(ref_abs_hum, 3),
                humidity_difference=round(difference, 3),
                rising_threshold=self.rising_threshold,
                falling_threshold=self.falling_threshold,
                observed_mode=curr_mode,
                target_mode=new_mode,
            )

            if new_mode != curr_mode:
                await self.async_service_call(
                    Platform.FAN,
                    SERVICE_TURN_ON if new_mode == STATE_ON else SERVICE_TURN_OFF,
                )

            return new_mode == STATE_ON

        match (self._state, event):
            case (MyState.INIT, MyEvent.OFF):
                self.set_state(MyState.OFF)
                self.set_diagnostics(
                    "STARTUP: fan is off; automatic humidity control is active.",
                    observed_mode=STATE_OFF,
                    rising_threshold=self.rising_threshold,
                    falling_threshold=self.falling_threshold,
                )

            case (MyState.INIT, MyEvent.ON):
                self.set_state(MyState.ON)
                self.set_diagnostics(
                    "STARTUP: fan is on; automatic humidity control is active.",
                    observed_mode=STATE_ON,
                    rising_threshold=self.rising_threshold,
                    falling_threshold=self.falling_threshold,
                )

            case (MyState.OFF, MyEvent.ON):
                self.set_state(
                    MyState.ON_MANUAL if self._manual_control_period else MyState.ON
                )
                self.set_timer(self._manual_control_period)
                self._set_manual_diagnostics(STATE_ON)

            case (MyState.OFF, MyEvent.REFRESH):
                if fan_on := await set_fan_mode():
                    self.set_state(MyState.ON)

            case (MyState.ON, MyEvent.OFF):
                self.set_state(
                    MyState.OFF_MANUAL if self._manual_control_period else MyState.OFF
                )
                self.set_timer(self._manual_control_period)
                self._set_manual_diagnostics(STATE_OFF)

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
