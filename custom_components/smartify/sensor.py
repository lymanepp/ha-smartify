"""Sensor platform for Smartify."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import get_controller
from .smartify_controller import SmartifyController
from .const import DOMAIN
from .entity import SmartifyEntity

CONTROLLER_STATE_DESCRIPTION = SensorEntityDescription(
    key="controller_state",
    name="State",
    icon="mdi:state-machine",
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform for a UI-created config entry."""
    if controller := get_controller(hass, config_entry.entry_id):
        async_add_entities([SmartifyControllerStateSensor(controller)])


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up sensors for YAML-configured controllers.

    Reached via `discovery.async_load_platform` from `async_setup`, never via
    a config entry -- `discovery_info["entry_ids"]` identifies which
    controllers in the shared `hass.data` registry to add.
    """
    if discovery_info is None:
        return

    async_add_entities(
        [
            SmartifyControllerStateSensor(controller)
            for entry_id in discovery_info["entry_ids"]
            if (controller := get_controller(hass, entry_id)) is not None
        ]
    )


class SmartifyControllerStateSensor(SmartifyEntity, SensorEntity):
    """Diagnostic sensor exposing a controller's state machine state."""

    def __init__(self, controller: SmartifyController) -> None:
        """Initialize the controller state sensor."""
        super().__init__(controller, unique_id_suffix=CONTROLLER_STATE_DESCRIPTION.key)
        self.entity_description = CONTROLLER_STATE_DESCRIPTION

    @property
    def native_value(self) -> str:
        """Return the current controller state machine state."""
        return str(self.controller.state)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return diagnostic attributes for the controller state machine."""
        return self.controller.diagnostic_attributes
