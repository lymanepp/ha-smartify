"""Sensor platform for Smartify."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from custom_components.smartify.smartify_controller import SmartifyController

from .const import DOMAIN
from .entity import SmartifyEntity

CONTROLLER_STATE_DESCRIPTION = SensorEntityDescription(
    key="controller_state",
    name="State",
    icon="mdi:state-machine",
    entity_category=EntityCategory.DIAGNOSTIC,
)


async def async_setup_entry(
    hass, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the sensor platform."""
    controller = hass.data[DOMAIN][config_entry.entry_id]

    if isinstance(controller, SmartifyController):
        async_add_entities(
            [
                SmartifyControllerStateSensor(
                    controller=controller,
                    entity_description=CONTROLLER_STATE_DESCRIPTION,
                )
            ]
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
