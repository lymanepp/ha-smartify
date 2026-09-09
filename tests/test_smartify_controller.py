import pytest

from homeassistant.core import (
    HomeAssistant,
    State,
)

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartify.smartify_controller import SmartifyController


class DummyController(SmartifyController):
    async def on_state_change(self, state):
        self.last_state = state

    async def on_timer_expired(self):
        self.timer_expired = True

    async def on_event(self, event):
        self.last_event = event


@pytest.mark.asyncio
async def test_state_change_ignored_for_identical_states(hass: HomeAssistant):
    controller = DummyController(
        hass,
        MockConfigEntry(),
        "off",
    )

    state = State("light.test", "on")

    await controller._on_state_change(
        state,
        state,
    )

    assert not hasattr(controller, "last_state")


@pytest.mark.asyncio
async def test_state_change_ignored_when_only_attributes_change(hass: HomeAssistant):
    controller = DummyController(
        hass,
        MockConfigEntry(),
        "off",
    )

    old_state = State("binary_sensor.test", "on", {"signal_strength": 10})
    new_state = State("binary_sensor.test", "on", {"signal_strength": 20})

    await controller._on_state_change(old_state, new_state)

    assert not hasattr(controller, "last_state")


@pytest.mark.asyncio
async def test_fire_event_dispatches(hass: HomeAssistant):
    controller = DummyController(
        hass,
        MockConfigEntry(),
        "off",
    )

    await controller.fire_event("hello")

    assert controller.last_event == "hello"


def test_listener_remove_safe(hass: HomeAssistant):
    controller = DummyController(
        hass,
        MockConfigEntry(),
        "off",
    )

    def cb():
        pass

    remove = controller.async_add_listener(cb)

    remove()
    remove()

    assert controller._listeners == []
