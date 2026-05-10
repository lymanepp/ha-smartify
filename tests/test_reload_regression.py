from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.mark.asyncio
async def test_duplicate_reload_replaces_old_controller(
    hass: HomeAssistant,
):
    entry = MockConfigEntry(
        domain="smartify",
        data={},
    )

    entry.add_to_hass(hass)

    old_controller = MagicMock()
    old_controller.async_setup = AsyncMock()
    old_controller.async_unload = MagicMock()

    new_controller = MagicMock()
    new_controller.async_setup = AsyncMock()
    new_controller.async_unload = MagicMock()

    with patch("custom_components.smartify._create_controller") as mock_create:
        mock_create.side_effect = [
            old_controller,
            new_controller,
        ]

        await hass.config_entries.async_setup(
            entry.entry_id,
        )

        await hass.config_entries.async_reload(
            entry.entry_id,
        )

        old_controller.async_unload.assert_called()
