"""Base class for controllers."""

from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from typing import Any

from homeassistant.const import ATTR_ENTITY_ID, STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Context,
    Event,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_point_in_utc_time,
    async_track_state_change_event,
)
from homeassistant.helpers.issue_registry import (
    IssueSeverity,
    async_create_issue,
    async_delete_issue,
)
from homeassistant.util import dt

from .const import DOMAIN, _LOGGER, IGNORE_STATES, Config, ControllerType
from .entry_types import SmartifyEntrySource

_REFERENCE_VALIDATION_DELAY = 10.0
_SINGLE_ENTITY_REFERENCE_KEYS = (
    Config.CONTROLLED_ENTITY,
    Config.TEMP_SENSOR,
    Config.HUMIDITY_SENSOR,
    Config.REFERENCE_TEMP_SENSOR,
    Config.REFERENCE_HUMIDITY_SENSOR,
    Config.TRIGGER_ENTITY,
    Config.ILLUMINANCE_SENSOR,
)
_MULTI_ENTITY_REFERENCE_KEYS = (
    Config.TRIGGER_ENTITIES,
    Config.SUSTAIN_ENTITIES,
    Config.REQUIRED_ON_ENTITIES,
    Config.REQUIRED_OFF_ENTITIES,
)
_EXPECTED_CONTROLLED_DOMAINS = {
    str(ControllerType.LIGHT): "light",
    str(ControllerType.CEILING_FAN): "fan",
    str(ControllerType.EXHAUST_FAN): "fan",
}


class SmartifyController(ABC):
    """Base class for controllers."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: SmartifyEntrySource,
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
        self._reference_problems: dict[str, str] = {}
        self._reference_validation_unsub: CALLBACK_TYPE | None = None

    async def async_setup(self, hass: HomeAssistant) -> None:
        """Subscribe to state changes and seed the controller from current states."""

        self.tracked_entity_ids = list(dict.fromkeys(self.tracked_entity_ids))

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
                self._schedule_reference_validation()
                return

            problem = self._reference_problem_for_state(
                new_state.entity_id, new_state
            )
            if problem is not None:
                if problem.startswith("wrong_domain:"):
                    self._set_reference_problem(new_state.entity_id, problem)
                else:
                    self._schedule_reference_validation()
                return

            self._clear_reference_problem(new_state.entity_id)
            await self._on_state_change(old_state, new_state)

        _LOGGER.debug(
            "%s; registering state listener controller=%s tracked=%s",
            self.name,
            id(self),
            self.tracked_entity_ids,
        )

        # Register first, then take the startup snapshot. This closes the race
        # where a YAML-created dependency (for example a Smartify occupancy
        # sensor) can appear after the initial lookup but before the listener
        # exists. If it is still absent, its first state_changed event will be
        # handled normally when the entity is added.
        self._unsubscribers.append(
            async_track_state_change_event(
                hass,
                self.tracked_entity_ids,
                on_state_event,
            )
        )

        for entity_id in self.tracked_entity_ids:
            state = hass.states.get(entity_id)

            if state is None:
                continue

            if self.name is None and entity_id == self.controlled_entity:
                self.name = state.name

            await self._on_state_change(None, state)

        # Do not diagnose missing references synchronously during startup. YAML
        # controllers can legitimately be created before their dependencies.
        # Validate after a short grace period, then report only persistent
        # problems. This same debounce is reused if an entity later disappears
        # or becomes unavailable during an integration reload.
        self._schedule_reference_validation()

    def async_unload(self) -> None:
        """Call when controller is being unloaded."""

        _LOGGER.debug(
            "%s; unloading controller=%s unsubscribers=%s listeners=%s",
            self.name,
            id(self),
            len(self._unsubscribers),
            len(self._listeners),
        )

        self._shutting_down = True

        self._cancel_timer()
        self._cancel_reference_validation()

        for entity_id in self.tracked_entity_ids:
            async_delete_issue(self.hass, DOMAIN, self._reference_issue_id(entity_id))
        self._reference_problems.clear()

        while self._unsubscribers:
            unsubscriber = self._unsubscribers.pop()

            try:
                unsubscriber()
            except Exception:
                _LOGGER.exception(
                    "%s; failed while unloading callback",
                    self.name,
                )

        _LOGGER.debug(
            "%s; unload complete controller=%s",
            self.name,
            id(self),
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

    def _cancel_reference_validation(self) -> None:
        """Cancel a pending reference-health validation."""
        if self._reference_validation_unsub is None:
            return
        self._reference_validation_unsub()
        self._reference_validation_unsub = None

    def _schedule_reference_validation(self) -> None:
        """Validate entity references after a short settling period."""
        self._cancel_reference_validation()

        @callback
        def validate_references(_: datetime) -> None:
            self._reference_validation_unsub = None
            if not self._shutting_down:
                self._validate_references()

        self._reference_validation_unsub = async_call_later(
            self.hass, _REFERENCE_VALIDATION_DELAY, validate_references
        )

    def _reference_roles(self, entity_id: str) -> list[str]:
        """Return configuration fields that reference an entity id."""
        roles: list[str] = []
        for key in _SINGLE_ENTITY_REFERENCE_KEYS:
            if self.data.get(key) == entity_id:
                roles.append(str(key))
        for key in _MULTI_ENTITY_REFERENCE_KEYS:
            if entity_id in self.data.get(key, []):
                roles.append(str(key))
        return roles or ["tracked_entity"]

    def _expected_controlled_domain(self) -> str | None:
        """Return the required domain for the controlled entity, if any."""
        controller_type = self.data.get(Config.CONTROLLER_TYPE)
        return _EXPECTED_CONTROLLED_DOMAINS.get(str(controller_type))

    def _reference_problem_for_state(
        self, entity_id: str, state: State
    ) -> str | None:
        """Return the current problem for an existing referenced entity."""
        if state.state == STATE_UNAVAILABLE:
            return "unavailable"
        if state.state == STATE_UNKNOWN:
            return "unknown"

        if entity_id == self.controlled_entity:
            expected_domain = self._expected_controlled_domain()
            actual_domain = entity_id.partition(".")[0]
            if expected_domain is not None and actual_domain != expected_domain:
                return f"wrong_domain:{expected_domain}"

        return None

    def _validate_references(self) -> None:
        """Validate all configured entity references and report persistent issues."""
        for entity_id in self.tracked_entity_ids:
            state = self.hass.states.get(entity_id)
            if state is None:
                self._set_reference_problem(entity_id, "missing")
                continue

            if problem := self._reference_problem_for_state(entity_id, state):
                self._set_reference_problem(entity_id, problem)
                continue

            self._clear_reference_problem(entity_id)

    def _reference_issue_id(self, entity_id: str) -> str:
        """Return a stable Repairs issue id for a referenced entity."""
        safe_entity_id = entity_id.replace(".", "_")
        return f"reference_{self.config_entry.entry_id}_{safe_entity_id}"

    def _sync_reference_issue(self, entity_id: str, problem: str) -> None:
        """Create, update, or remove an actionable Repairs issue."""
        issue_id = self._reference_issue_id(entity_id)
        roles = ", ".join(self._reference_roles(entity_id))
        controller_name = self.name or self.config_entry.title

        if problem == "missing":
            async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                is_persistent=True,
                severity=IssueSeverity.ERROR,
                translation_key="missing_reference",
                translation_placeholders={
                    "controller": controller_name,
                    "entity_id": entity_id,
                    "roles": roles,
                },
            )
            return

        if problem.startswith("wrong_domain:"):
            expected_domain = problem.split(":", 1)[1]
            async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                is_persistent=True,
                severity=IssueSeverity.ERROR,
                translation_key="wrong_reference_domain",
                translation_placeholders={
                    "controller": controller_name,
                    "entity_id": entity_id,
                    "expected_domain": expected_domain,
                    "roles": roles,
                },
            )
            return

        # unavailable/unknown are runtime conditions, not configuration
        # defects. Keep them in the log without leaving a Repairs issue.
        async_delete_issue(self.hass, DOMAIN, issue_id)

    def _set_reference_problem(self, entity_id: str, problem: str) -> None:
        """Record and report a reference problem once per state transition."""
        previous = self._reference_problems.get(entity_id)
        self._sync_reference_issue(entity_id, problem)
        if previous == problem:
            return

        self._reference_problems[entity_id] = problem
        roles = ", ".join(self._reference_roles(entity_id))

        if problem == "missing":
            _LOGGER.error(
                "%s; configuration problem: %s references '%s', but that entity "
                "does not exist in Home Assistant's state machine.",
                self.name or self.config_entry.title,
                roles,
                entity_id,
            )
        elif problem == "unavailable":
            _LOGGER.warning(
                "%s; reference problem: %s entity '%s' is unavailable.",
                self.name or self.config_entry.title,
                roles,
                entity_id,
            )
        elif problem == "unknown":
            _LOGGER.warning(
                "%s; reference problem: %s entity '%s' has unknown state.",
                self.name or self.config_entry.title,
                roles,
                entity_id,
            )
        elif problem.startswith("wrong_domain:"):
            expected_domain = problem.split(":", 1)[1]
            _LOGGER.error(
                "%s; configuration problem: %s references '%s', but the controlled "
                "entity must be in the '%s' domain.",
                self.name or self.config_entry.title,
                roles,
                entity_id,
                expected_domain,
            )

    def _clear_reference_problem(self, entity_id: str) -> None:
        """Clear a reference problem and its Repairs issue when it recovers."""
        async_delete_issue(self.hass, DOMAIN, self._reference_issue_id(entity_id))
        previous = self._reference_problems.pop(entity_id, None)
        if previous is None:
            return

        _LOGGER.info(
            "%s; referenced entity '%s' recovered from %s.",
            self.name or self.config_entry.title,
            entity_id,
            previous,
        )

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

        @callback
        def timer_expired(_: datetime) -> None:
            self._timer_unsub = None

            if self._shutting_down:
                return

            # Use the thread-safe wrapper so this is correct regardless of which
            # thread the timer fires on. hass.create_task schedules onto the loop
            # via call_soon_threadsafe when invoked off-loop, unlike
            # hass.async_create_task which must only be called from the loop.
            self.hass.create_task(self.on_timer_expired())

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

        # Controllers react to entity state transitions. Home Assistant may emit
        # state_changed events when only attributes change; forwarding those as
        # transitions can retrigger automations (for example, an occupancy PIR
        # that remains ON while an attribute is updated would restart its decay
        # timer indefinitely).
        if old_state is not None and old_state.state == new_state.state:
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
