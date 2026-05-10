from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.asyncio
async def test_async_setup_entry(
    hass: HomeAssistant,
):
    entry = MockConfigEntry(
        domain="smartify",
        data={},
    )

    entry.add_to_hass(hass)

    controller = MagicMock()
    controller.async_setup = AsyncMock()
    controller.async_unload = MagicMock()

    with patch("custom_components.smartify._create_controller") as mock_create:
        mock_create.return_value = controller

        result = await hass.config_entries.async_setup(
            entry.entry_id,
        )

        assert result is True

        controller.async_setup.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_unload_entry(
    hass: HomeAssistant,
):
    entry = MockConfigEntry(
        domain="smartify",
        data={},
    )

    entry.add_to_hass(hass)

    controller = MagicMock()
    controller.async_setup = AsyncMock()
    controller.async_unload = MagicMock()

    with patch("custom_components.smartify._create_controller") as mock_create:
        mock_create.return_value = controller

        result = await hass.config_entries.async_setup(
            entry.entry_id,
        )

        assert result is True

        unload_result = await hass.config_entries.async_unload(
            entry.entry_id,
        )

        assert unload_result is True

        controller.async_unload.assert_called_once()
