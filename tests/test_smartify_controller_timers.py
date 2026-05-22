from datetime import timedelta
from unittest.mock import patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from homeassistant.util import dt

from custom_components.smartify.smartify_controller import SmartifyController


class DummyController(SmartifyController):
    async def on_state_change(self, state):
        pass

    async def on_timer_expired(self):
        self.timer_fired = True

    async def on_event(self, event):
        pass


@pytest.mark.asyncio
async def test_set_timer_creates_timer(
    hass: HomeAssistant,
):
    controller = DummyController(
        hass,
        MockConfigEntry(
            domain="smartify",
        ),
        "off",
    )

    controller.set_timer(
        timedelta(seconds=30),
    )

    assert controller._timer_unsub is not None

    controller.async_unload()


@pytest.mark.asyncio
async def test_set_timer_replaces_existing_timer(
    hass: HomeAssistant,
):
    controller = DummyController(
        hass,
        MockConfigEntry(
            domain="smartify",
        ),
        "off",
    )

    controller.set_timer(
        timedelta(seconds=30),
    )

    first_timer = controller._timer_unsub

    controller.set_timer(
        timedelta(seconds=60),
    )

    assert controller._timer_unsub is not None
    assert controller._timer_unsub != first_timer

    controller.async_unload()


@pytest.mark.asyncio
async def test_set_timer_none_cancels_timer(
    hass: HomeAssistant,
):
    controller = DummyController(
        hass,
        MockConfigEntry(
            domain="smartify",
        ),
        "off",
    )

    controller.set_timer(
        timedelta(seconds=30),
    )

    assert controller._timer_unsub is not None

    controller.set_timer(None)

    assert controller._timer_unsub is None


@pytest.mark.asyncio
async def test_async_unload_cleans_up_timer(
    hass: HomeAssistant,
):
    controller = DummyController(
        hass,
        MockConfigEntry(
            domain="smartify",
        ),
        "off",
    )

    controller.set_timer(
        timedelta(seconds=30),
    )

    controller.async_unload()

    assert controller._timer_unsub is None
    assert controller._shutting_down is True


@pytest.mark.asyncio
async def test_timer_expiration_invokes_on_timer_expired(
    hass: HomeAssistant,
):
    """When the timer fires, on_timer_expired runs and the unsub is cleared."""
    controller = DummyController(
        hass,
        MockConfigEntry(
            domain="smartify",
        ),
        "off",
    )
    controller.timer_fired = False

    controller.set_timer(timedelta(seconds=30))
    assert controller._timer_unsub is not None

    async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=31))
    await hass.async_block_till_done()

    assert controller.timer_fired is True
    # The expiration callback clears its own unsub handle.
    assert controller._timer_unsub is None


@pytest.mark.asyncio
async def test_timer_uses_thread_safe_create_task(
    hass: HomeAssistant,
):
    """The timer callback must use the thread-safe hass.create_task.

    Regression test for the crash where hass.async_create_task was called from a
    non-loop thread, which raises RuntimeError on modern HA. We assert the
    callback routes through hass.create_task (the thread-safe public wrapper).
    Note: create_task delegates to async_create_task when already on the loop,
    so we only assert that the thread-safe entry point was used and the coroutine
    actually ran.
    """
    controller = DummyController(
        hass,
        MockConfigEntry(
            domain="smartify",
        ),
        "off",
    )
    controller.timer_fired = False

    with patch.object(hass, "create_task", wraps=hass.create_task) as mock_create_task:
        controller.set_timer(timedelta(seconds=30))
        async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=31))
        await hass.async_block_till_done()

    # Thread-safe wrapper was used, and the coroutine actually ran.
    assert mock_create_task.called
    assert controller.timer_fired is True


@pytest.mark.asyncio
async def test_timer_does_not_fire_when_shutting_down(
    hass: HomeAssistant,
):
    """A timer that fires after unload must not invoke on_timer_expired."""
    controller = DummyController(
        hass,
        MockConfigEntry(
            domain="smartify",
        ),
        "off",
    )
    controller.timer_fired = False

    controller.set_timer(timedelta(seconds=30))

    # Simulate the timer surviving to fire after shutdown started by setting the
    # flag and invoking the registered point-in-time callback directly.
    controller._shutting_down = True

    with patch.object(hass, "create_task") as mock_create_task:
        async_fire_time_changed(hass, dt.utcnow() + timedelta(seconds=31))
        await hass.async_block_till_done()

    assert not mock_create_task.called
    assert controller.timer_fired is False
