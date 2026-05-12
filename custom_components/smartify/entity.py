"""BlueprintEntity class."""

from __future__ import annotations

from homeassistant.const import ATTR_SW_VERSION
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo, Entity
from homeassistant.loader import async_get_custom_components

from .const import DOMAIN, NAME
from .smartify_controller import SmartifyController


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
        assert self.device_info

        custom_components = await async_get_custom_components(self.hass)
        if version := custom_components[DOMAIN].version:
            self.device_info[ATTR_SW_VERSION] = version.string
