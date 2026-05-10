import pytest
from homeassistant.core import Context, Event, HomeAssistant, State
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartify.smartify_controller import SmartifyController


class DummyController(SmartifyController):
    async def on_state_change(self, state):
        self.state_calls += 1

    async def on_timer_expired(self):
        pass

    async def on_event(self, event):
        pass


@pytest.mark.asyncio
async def test_self_generated_context_ignored(
    hass: HomeAssistant,
):
    controller = DummyController(
        hass,
        MockConfigEntry(
            domain="smartify",
        ),
        "off",
    )

    controller.state_calls = 0

    context = Context()

    controller._service_context_ids.add(context.id)

    event = Event(
        "state_changed",
        {
            "old_state": None,
            "new_state": State(
                "light.test",
                "on",
            ),
        },
        context=context,
    )

    await controller._on_state_change(
        None,
        event.data["new_state"],
    )

    assert controller.state_calls == 1
