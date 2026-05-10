"""Base class for controllers."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_ENTITY_ID, STATE_ON
from homeassistant.core import CALLBACK_TYPE, Context, Event, HomeAssistant, State
from homeassistant.helpers.event import (
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.util import dt

from .const import _LOGGER, IGNORE_STATES, Config


class SmartifyController(ABC):
    """Base class for controllers."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        initial_state: str,
    ) -> None:
        """Initialize the controller base."""

        self.hass = hass
        self.config_entry = config_entry
        self._state = initial_state
        self.data: Mapping[str, Any] = config_entry.data | config_entry.options
        self.controlled_entity: str | None = self.data.get(Config.CONTROLLED_ENTITY)
        self.name: str | None = None

        self.tracked_entity_ids: list[str] = []

        self._timer_unsub: CALLBACK_TYPE | None = None
        self._unsubscribers: list[CALLBACK_TYPE] = []
        self._listeners: list[CALLBACK_TYPE] = []

        self._service_context_ids: set[str] = set()
        self._transition_lock = asyncio.Lock()
        self._shutting_down = False

    async def async_setup(self, hass: HomeAssistant) -> None:
        """Subscribe to state change events for all tracked entities."""

        self.tracked_entity_ids = list(dict.fromkeys(self.tracked_entity_ids))

        initial_states: list[State] = []

        for entity_id in self.tracked_entity_ids:
            state = hass.states.get(entity_id)

            if state is None:
                _LOGGER.warning(
                    "%s; referenced entity '%s' is missing.",
                    self.name,
                    entity_id,
                )
                continue

            if self.name is None and entity_id == self.controlled_entity:
                self.name = state.name

            initial_states.append(state)

        async def on_state_event(event: Event) -> None:
            if self._shutting_down:
                return

            if (
                event.context is not None
                and event.context.id in self._service_context_ids
            ):
                return

            old_state = event.data.get("old_state")
            new_state = event.data.get("new_state")

            if new_state is None:
                return

            await self._on_state_change(old_state, new_state)

        self._unsubscribers.append(
            async_track_state_change_event(
                hass,
                self.tracked_entity_ids,
                on_state_event,
            )
        )

        for state in initial_states:
            await self._on_state_change(None, state)

    def async_unload(self) -> None:
        """Call when controller is being unloaded."""

        self._shutting_down = True

        self._cancel_timer()

        while self._unsubscribers:
            unsubscriber = self._unsubscribers.pop()

            try:
                unsubscriber()
            except Exception:
                _LOGGER.exception(
                    "%s; failed while unloading callback",
                    self.name,
                )

        self._listeners.clear()
        self._service_context_ids.clear()

    def async_add_listener(self, update_callback: CALLBACK_TYPE) -> Callable[[], None]:
        """Listen for data updates."""

        self._listeners.append(update_callback)

        def remove_listener() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return remove_listener

    @property
    def state(self) -> str:
        """Return the state."""
        return self._state

    @property
    def is_on(self) -> bool:
        """Return the status of the sensor."""
        return self._state == STATE_ON

    def is_entity_state(self, entity: str | None, value: Any) -> bool:
        """Compare the state of an entity. Return True if the value matches the state."""

        if entity is None:
            return False

        state = self.hass.states.get(entity)

        return bool(state and state.state == value)

    def _cancel_timer(self) -> None:
        """Cancel active timer."""

        if self._timer_unsub is None:
            return

        try:
            self._timer_unsub()
        except Exception:
            _LOGGER.exception("%s; failed canceling timer", self.name)

        self._timer_unsub = None

    def set_timer(self, period: timedelta | None) -> None:
        """Start a timer or cancel a timer if time period is 'None'."""

        self._cancel_timer()

        if period is None:
            return

        def timer_expired(_: datetime) -> None:
            self._timer_unsub = None

            if self._shutting_down:
                return

            self.hass.async_create_task(self.on_timer_expired())

        self._timer_unsub = async_track_point_in_utc_time(
            self.hass,
            timer_expired,
            dt.utcnow() + period,
        )

        _LOGGER.debug(
            "%s; state=%s; started timer for '%s'",
            self.name,
            self._state,
            period,
        )

    def set_state(self, new_state: str) -> None:
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

        if self._shutting_down:
            return

        async with self._transition_lock:
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

        context = Context()
        self._service_context_ids.add(context.id)

        try:
            await self.hass.services.async_call(
                domain,
                service,
                service_data,
                target={ATTR_ENTITY_ID: self.controlled_entity},
                context=context,
                blocking=True,
            )
        finally:
            self._service_context_ids.discard(context.id)

    def _update_listeners(self) -> None:
        """Update all registered listeners."""

        for update_callback in list(self._listeners):
            try:
                update_callback()
            except Exception:
                _LOGGER.exception(
                    "%s; listener callback failed",
                    self.name,
                )

    async def _on_state_change(
        self,
        old_state: State | None,
        new_state: State | None,
    ) -> None:
        """Internal state change dispatcher."""

        if self._shutting_down:
            return

        if new_state is None:
            return

        if new_state.state in IGNORE_STATES:
            return

        if (
            old_state is not None
            and old_state.state == new_state.state
            and old_state.attributes == new_state.attributes
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
