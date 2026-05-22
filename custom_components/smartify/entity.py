"""BlueprintEntity class."""

from __future__ import annotations

from homeassistant.const import ATTR_SW_VERSION
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.loader import async_get_custom_components

from .const import DOMAIN, NAME
from .smartify_controller import SmartifyController

# The integration version is static for the lifetime of the process, so resolve
# it at most once and share it across every entity instead of calling
# async_get_custom_components for each entity that is added.
_VERSION_CACHE: str | None = None
_VERSION_RESOLVED = False


async def _async_get_version(hass: HomeAssistant) -> str | None:
    """Return the integration version, resolving and caching it once."""
    global _VERSION_CACHE, _VERSION_RESOLVED  # noqa: PLW0603

    if _VERSION_RESOLVED:
        return _VERSION_CACHE

    custom_components = await async_get_custom_components(hass)
    integration = custom_components.get(DOMAIN)
    version = integration.version if integration else None
    _VERSION_CACHE = version.string if version else None
    _VERSION_RESOLVED = True

    return _VERSION_CACHE


class SmartifyEntity(Entity):
    """SmartifyEntity class."""

    def __init__(
        self,
        controller: SmartifyController,
        unique_id_suffix: str | None = None,
    ) -> None:
        """Initialize."""
        entry_id = controller.config_entry.entry_id
        self.hass = controller.hass
        self.controller = controller
        self._attr_unique_id = (
            f"{entry_id}_{unique_id_suffix}" if unique_id_suffix else entry_id
        )
        self._attr_has_entity_name = True
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            entry_type=DeviceEntryType.SERVICE,
            name=controller.config_entry.title,
            manufacturer=NAME,
        )

    async def async_added_to_hass(self) -> None:
        """Set up a listener and load data."""
        await self._set_sw_version()
        self.async_on_remove(self.controller.async_add_listener(self._update_callback))
        self._update_callback()

    # #### Internal methods ####

    @callback
    def _update_callback(self) -> None:
        """Load data from controller."""
        self._attr_state = self.controller.state
        self.async_write_ha_state()

    async def _set_sw_version(self) -> None:
        """Populate sw_version on the DeviceInfo before the device is registered.

        This runs in async_added_to_hass, before the entity is fully added, so the
        value is read when the device registry entry is created/updated. Mutating
        device_info after registration would not propagate.
        """
        if self._attr_device_info is None:
            return

        if version := await _async_get_version(self.hass):
            self._attr_device_info[ATTR_SW_VERSION] = version
