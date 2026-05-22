"""Tests for SmartifyEntity software-version handling.

Regression tests for item 5: sw_version must be written into DeviceInfo before
the device is registered (i.e. inside async_added_to_hass via _set_sw_version),
the version lookup must be cached across entities, and missing integration
metadata must not raise.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import ATTR_SW_VERSION

import custom_components.smartify.entity as entity_module
from custom_components.smartify.const import DOMAIN
from custom_components.smartify.entity import SmartifyEntity

# Capture the genuine implementation at import time, before conftest's autouse
# suppress_entity_sw_version fixture replaces it with an AsyncMock.
_REAL_SET_SW_VERSION = SmartifyEntity._set_sw_version


@pytest.fixture(autouse=True)
def _restore_version_cache():
    """Reset the module-level version cache around each test."""
    saved = (entity_module._VERSION_CACHE, entity_module._VERSION_RESOLVED)
    entity_module._VERSION_CACHE = None
    entity_module._VERSION_RESOLVED = False
    yield
    entity_module._VERSION_CACHE, entity_module._VERSION_RESOLVED = saved


@pytest.fixture
def _real_set_sw_version(monkeypatch):
    """Undo conftest's autouse suppression so the real method runs."""
    monkeypatch.setattr(
        "custom_components.smartify.entity.SmartifyEntity._set_sw_version",
        _REAL_SET_SW_VERSION,
    )


def make_controller(hass):
    controller = MagicMock()
    controller.name = "Test Controller"
    controller.hass = hass
    controller.config_entry.entry_id = "entry-123"
    controller.config_entry.title = "Test Controller"
    return controller


def _patch_custom_components(version_string: str | None):
    integration = SimpleNamespace(
        version=SimpleNamespace(string=version_string) if version_string else None
    )
    return patch.object(
        entity_module,
        "async_get_custom_components",
        AsyncMock(return_value={DOMAIN: integration}),
    )


@pytest.mark.asyncio
async def test_set_sw_version_populates_device_info(hass, _real_set_sw_version):
    controller = make_controller(hass)
    entity = SmartifyEntity(controller)

    with _patch_custom_components("1.2.3"):
        await entity._set_sw_version()

    assert entity._attr_device_info[ATTR_SW_VERSION] == "1.2.3"


@pytest.mark.asyncio
async def test_set_sw_version_no_version_metadata(hass, _real_set_sw_version):
    controller = make_controller(hass)
    entity = SmartifyEntity(controller)

    with _patch_custom_components(None):
        await entity._set_sw_version()

    assert ATTR_SW_VERSION not in entity._attr_device_info


@pytest.mark.asyncio
async def test_set_sw_version_missing_domain_does_not_raise(hass, _real_set_sw_version):
    controller = make_controller(hass)
    entity = SmartifyEntity(controller)

    with patch.object(
        entity_module,
        "async_get_custom_components",
        AsyncMock(return_value={}),  # DOMAIN absent
    ):
        await entity._set_sw_version()

    assert ATTR_SW_VERSION not in entity._attr_device_info


@pytest.mark.asyncio
async def test_version_lookup_is_cached_across_entities(hass, _real_set_sw_version):
    controller = make_controller(hass)
    e1 = SmartifyEntity(controller)
    e2 = SmartifyEntity(controller)

    with _patch_custom_components("9.9.9") as mock_get:
        await e1._set_sw_version()
        await e2._set_sw_version()

    # Resolved once, reused for the second entity.
    assert mock_get.call_count == 1
    assert e1._attr_device_info[ATTR_SW_VERSION] == "9.9.9"
    assert e2._attr_device_info[ATTR_SW_VERSION] == "9.9.9"
