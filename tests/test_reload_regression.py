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


@pytest.mark.asyncio
async def test_unload_without_stored_controller_does_not_raise(
    hass: HomeAssistant,
):
    """Unloading when no controller was stored must not raise KeyError.

    Regression test for hass.data[DOMAIN].pop(entry_id) failing when the entry
    was never inserted (e.g. setup failed midway, or a double-unload).
    """
    from custom_components.smartify import async_unload_entry
    from custom_components.smartify.const import DOMAIN

    entry = MockConfigEntry(
        domain="smartify",
        data={},
    )
    entry.add_to_hass(hass)

    # Ensure the domain bucket exists but contains no controller for this entry.
    hass.data.setdefault(DOMAIN, {})

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    ):
        result = await async_unload_entry(hass, entry)

    assert result is True


@pytest.mark.asyncio
async def test_unload_with_missing_domain_bucket_does_not_raise(
    hass: HomeAssistant,
):
    """Unloading when the DOMAIN bucket is absent entirely must not raise."""
    from custom_components.smartify import async_unload_entry
    from custom_components.smartify.const import DOMAIN

    entry = MockConfigEntry(
        domain="smartify",
        data={},
    )
    entry.add_to_hass(hass)

    hass.data.pop(DOMAIN, None)

    with patch.object(
        hass.config_entries,
        "async_unload_platforms",
        AsyncMock(return_value=True),
    ):
        result = await async_unload_entry(hass, entry)

    assert result is True
