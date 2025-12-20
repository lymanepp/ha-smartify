"""Base class for controllers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, STATE_ON
from homeassistant.core import (
    CALLBACK_TYPE,
    Context,
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
)
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.util import dt

from .const import _LOGGER, IGNORE_STATES, Config


class MyContext(Context):
    """Makes it possible to identify state changes triggered by our service calls."""


class SmartifyBase(ABC):
    """Base class for controllers."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, initial_state: str
    ) -> None:
        """Initialize the controller base."""

        self.is_setup = False
        self.hass = hass
        self.config_entry = entry
        self._state = initial_state
        self.data: Mapping[str, Any] = entry.data | entry.options
        self.controlled_entity: str | None = self.data.get(Config.CONTROLLED_ENTITY)
        self.name: str | None = None
        self.tracked_entity_ids: list[str] = []
        self._timer_unsub: CALLBACK_TYPE | None = None
        self._unsubscribers: list[CALLBACK_TYPE] = []
        self._listeners: list[CALLBACK_TYPE] = []

    async def async_setup(self, hass) -> None:
        """Subscribe to state change events for all tracked entities."""
        for entity_id in self.tracked_entity_ids:
            state = hass.states.get(entity_id)
            if state is not None:
                if self.name is None and entity_id == self.controlled_entity:
                    self.name = state.name
                await self._on_state_change(None, state)
            else:
                _LOGGER.warning(
                    "%s; referenced entity '%s' is missing.", self.name, entity_id
                )

        async def on_state_event(event: Event[EventStateChangedData]) -> None:
            # ignore state change events triggered by service calls from derived controllers
            if not isinstance(event.context, MyContext):
                await self._on_state_change(
                    event.data["old_state"], event.data["new_state"]
                )

        self._unsubscribers.append(
            async_track_state_change_event(
                hass, self.tracked_entity_ids, on_state_event
            )
        )

    def async_unload(self) -> None:
        """Call when controller is being unloaded."""
        while self._unsubscribers:
            unsubscriber = self._unsubscribers.pop()
            unsubscriber()

    def async_add_listener(self, update_callback: CALLBACK_TYPE) -> Callable[[], None]:
        """Listen for data updates."""

        def remove_listener() -> None:
            self._listeners.remove(update_callback)

        self._listeners.append(update_callback)

        return remove_listener

    @property
    def state(self) -> str:
        """Return the state."""
        return self._state

    @property
    def is_on(self):
        """Return the status of the sensor."""
        return self._state == STATE_ON

    def is_entity_state(self, entity: str | None, value: Any):
        """Compare the state of an entity. Return True if the value matches the state."""
        if entity is None:
            return False
        state = self.hass.states.get(entity)
        return state and state.state == value

    def set_timer(self, period: timedelta | None) -> None:
        """Start a timer or cancel a timer if time period is 'None'."""

        def timer_expired(_: datetime) -> None:
            self._timer_unsub = None
            self.hass.add_job(self.on_timer_expired)

        if self._timer_unsub is not None:
            self._unsubscribers.remove(self._timer_unsub)
            self._timer_unsub()
            self._timer_unsub = None
            _LOGGER.debug("%s; state=%s; canceled timer", self.name, self._state)

        if period is not None:
            self._timer_unsub = async_track_point_in_utc_time(
                self.hass, timer_expired, dt.utcnow() + period
            )
            self._unsubscribers.append(self._timer_unsub)
            _LOGGER.debug(
                "%s; state=%s; started timer for '%s'",
                self.name,
                self._state,
                period,
            )

    def set_state(self, new_state: str):
        """Change the current state."""
        if self._state == new_state:
            return

        _LOGGER.debug(
            "%s; state=%s; changing state to '%s'",
            self.name,
            self._state,
            new_state,
        )
        self._state = new_state
        self._update_listeners()

    @abstractmethod
    async def on_state_change(self, state: State) -> None:
        """Handle tracked entity state changes."""

    @abstractmethod
    async def on_timer_expired(self) -> None:
        """Handle timer expiration."""

    @abstractmethod
    async def on_event(self, event: Any) -> None:
        """Handle controller events."""

    async def fire_event(self, event: Any) -> None:
        """Fire an event to the controller."""
        _LOGGER.debug(
            "%s; state=%s; processing '%s' event",
            self.name,
            self._state,
            event,
        )
        await self.on_event(event)

    async def async_service_call(
        self,
        domain: str,
        service: str,
        service_data: dict[str, Any] | None = None,
    ) -> None:
        """Call a service."""

        _LOGGER.debug(
            "%s; state=%s; calling '%s.%s' service",
            self.name,
            self._state,
            domain,
            service,
        )

        await self.hass.services.async_call(
            domain,
            service,
            service_data,
            target={ATTR_ENTITY_ID: self.controlled_entity},
            context=MyContext(),
        )

    # #### Internal methods ####

    def _update_listeners(self) -> None:
        """Update all registered listeners."""
        for update_callback in self._listeners:
            update_callback()

    async def _on_state_change(
        self, old_state: State | None, new_state: State | None
    ) -> None:
        if (
            new_state is None
            or new_state.state in IGNORE_STATES
            or (old_state and old_state.state == new_state.state)
        ):
            return

        _LOGGER.debug(
            "%s; state=%s; %s changed from '%s' to '%s'",
            self.name,
            self._state,
            new_state.name,
            old_state.state if old_state else None,
            new_state.state,
        )

        await self.on_state_change(new_state)
