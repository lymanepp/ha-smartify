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


def test_diagnostics_notify_only_when_snapshot_changes(hass: HomeAssistant):
    controller = DummyController(
        hass,
        MockConfigEntry(),
        "off",
    )
    updates = 0

    def listener():
        nonlocal updates
        updates += 1

    controller.async_add_listener(listener)

    controller.set_diagnostics("AUTO HOLD", value=1)
    controller.set_diagnostics("AUTO HOLD", value=1)
    controller.set_diagnostics("AUTO HOLD", value=2)

    assert updates == 2
    assert controller.diagnostic_attributes["reason"] == "AUTO HOLD"
    assert controller.diagnostic_attributes["value"] == 2
    assert "diagnostic_updated_at" in controller.diagnostic_attributes


def test_diagnostics_republish_when_live_inputs_change(hass: HomeAssistant):
    controller = DummyController(
        hass,
        MockConfigEntry(),
        "off",
    )
    updates = 0

    def listener():
        nonlocal updates
        updates += 1

    controller.async_add_listener(listener)

    controller.set_diagnostics(
        "AUTO: SSI 86.7 -> 50%",
        ssi=86.7,
        target_speed=50,
    )
    first_snapshot = controller.diagnostic_attributes

    controller.set_diagnostics(
        "AUTO: SSI 86.9 -> 50%",
        ssi=86.9,
        target_speed=50,
    )

    assert updates == 2
    assert controller.diagnostic_attributes != first_snapshot
    assert controller.diagnostic_attributes["ssi"] == 86.9
    assert controller.diagnostic_attributes["target_speed"] == 50

    # An identical payload should still be a no-op.
    controller.set_diagnostics(
        "AUTO: SSI 86.9 -> 50%",
        ssi=86.9,
        target_speed=50,
    )
    assert updates == 2
