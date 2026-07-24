from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartify.const import DOMAIN


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
        assert (
            hass.data[DOMAIN][entry.entry_id]
            is new_controller
        )


@pytest.mark.asyncio
async def test_unload_calls_controller_unload_when_present(
    hass: HomeAssistant,
):
    """When hass.data holds a controller, unload must release it."""
    from custom_components.smartify import async_unload_entry

    entry = MockConfigEntry(
        domain="smartify",
        data={},
    )
    entry.add_to_hass(hass)

    controller = MagicMock()
    controller.async_unload = MagicMock()
    hass.data.setdefault(DOMAIN, {})[
        entry.entry_id
    ] = controller

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    ):
        result = await async_unload_entry(hass, entry)

    assert result is True
    controller.async_unload.assert_called_once()
    assert entry.entry_id not in hass.data[DOMAIN]


@pytest.mark.asyncio
async def test_failed_unload_does_not_release_controller(
    hass: HomeAssistant,
):
    """If platform unload fails, the controller must be left intact."""
    from custom_components.smartify import async_unload_entry

    entry = MockConfigEntry(
        domain="smartify",
        data={},
    )
    entry.add_to_hass(hass)

    controller = MagicMock()
    controller.async_unload = MagicMock()
    hass.data.setdefault(DOMAIN, {})[
        entry.entry_id
    ] = controller

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=False),
    ):
        result = await async_unload_entry(hass, entry)

    assert result is False
    controller.async_unload.assert_not_called()
