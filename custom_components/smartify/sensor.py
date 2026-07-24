"""Sensor platform for Smartify."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import get_controller, async_setup_yaml_platform
from .smartify_controller import SmartifyController
from .const import DOMAIN
from .entity import SmartifyEntity

CONTROLLER_STATE_DESCRIPTION = SensorEntityDescription(
    key="controller_state",
    name="State",
    icon="mdi:state-machine",
    entity_category=EntityCategory.DIAGNOSTIC,
)


def _sensors_for_controller(
    controller: SmartifyController,
) -> list["SmartifyControllerStateSensor"]:
    """Build the diagnostic sensor for one controller, regardless of whether
    it came from a config entry (UI) or a YAML-configured entry.
    """
    return [
        SmartifyControllerStateSensor(
            controller=controller,
            entity_description=CONTROLLER_STATE_DESCRIPTION,
        )
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform for a UI-created config entry."""
    controller = get_controller(hass, config_entry.entry_id)

    if isinstance(controller, SmartifyController):
        async_add_entities(_sensors_for_controller(controller))


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

    await async_setup_yaml_platform(
        hass,
        discovery_info["entry_ids"],
        async_add_entities,
        _sensors_for_controller,
    )


class SmartifyControllerStateSensor(SmartifyEntity, SensorEntity):
    """Diagnostic sensor exposing a controller's state machine state."""

    def __init__(
        self,
        controller: SmartifyController,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the controller state sensor."""
        super().__init__(controller, unique_id_suffix=entity_description.key)
        self.controller: SmartifyController = controller
        self.entity_description = entity_description
        self._attr_name = entity_description.name
        self._attr_icon = entity_description.icon
        self._attr_entity_category = entity_description.entity_category

    @property
    def native_value(self) -> str:
        """Return the current controller state machine state."""
        return str(self.controller.state)

    @property
    def extra_state_attributes(self) -> dict[str, object]:
        """Return diagnostic attributes for the controller state machine."""
        return (
            self.controller.diagnostic_attributes
            if hasattr(self.controller, "diagnostic_attributes")
            else {}
        )
