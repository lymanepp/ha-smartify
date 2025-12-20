from unittest.mock import AsyncMock, patch

import pytest

from custom_components.smartify.config_flow import SmartControllerConfigFlow
from custom_components.smartify.const import Config, ControllerType
from homeassistant.data_entry_flow import FlowResultType


@pytest.fixture
def mock_hass():
    hass = AsyncMock()
    hass.states.get = AsyncMock()
    return hass

@pytest.fixture
def config_flow(mock_hass):
    flow = SmartControllerConfigFlow()
    flow.hass = mock_hass
    return flow

async def test_async_step_light_options_no_user_input(config_flow):
    """Test async_step_light_options with no user input."""
    config_flow._controlled_entity = "light.entity"
    result = await config_flow.async_step_light_options(user_input=None)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "light_options"

async def test_async_step_light_options_valid_user_input(config_flow):
    """Test async_step_light_options with valid user input."""
    config_flow._controlled_entity = "light.entity"
    config_flow.hass.states.get.return_value = AsyncMock(name="Light Entity")

    user_input = {"brightness": 255}
    with patch("homeassistant.util.slugify", return_value="light_entity"):
        result = await config_flow.async_step_light_options(user_input=user_input)

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Light Entity"
    assert result["data"] == {
        Config.CONTROLLER_TYPE: ControllerType.LIGHT,
        Config.CONTROLLED_ENTITY: "light.entity",
        "brightness": 255,
    }

async def test_async_step_light_options_duplicate_unique_id(config_flow):
    """Test async_step_light_options with duplicate unique ID."""
    config_flow._controlled_entity = "light.entity"
    config_flow.hass.states.get.return_value = AsyncMock(name="Light Entity")

    user_input = {"brightness": 255}
    with patch("homeassistant.util.slugify", return_value="light_entity"):
        with patch.object(config_flow, "async_set_unique_id", return_value=True):
            result = await config_flow.async_step_light_options(user_input=user_input)

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "light_options"
    assert "base" in result["errors"]

async def test_async_step_light_options_no_controlled_entity(config_flow):
    """Test async_step_light_options with no controlled entity."""
    config_flow._controlled_entity = None

    with pytest.raises(AssertionError):
        await config_flow.async_step_light_options(user_input=None)

async def test_async_step_light_options_state_not_found(config_flow):
    """Test async_step_light_options with state not found."""
    config_flow._controlled_entity = "light.entity"
    config_flow.hass.states.get.return_value = None

    with pytest.raises(AssertionError):
        await config_flow.async_step_light_options(user_input={"brightness": 255})
