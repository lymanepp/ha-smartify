from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
