"""Sensor platform for integration_blueprint."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, Config, ControllerType
from .entity import SmartifyEntity
from .smartify_controller import SmartifyController

ENTITY_DESCRIPTIONS = [
    BinarySensorEntityDescription(
        key=ControllerType.OCCUPANCY,
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        icon="mdi:account",
    ),
]


async def async_setup_entry(
    hass, config_entry: ConfigEntry, async_add_entities: AddEntitiesCallback
):
    """Set up the sensor platform."""
    controller = hass.data[DOMAIN][config_entry.entry_id]
    type_ = config_entry.data[Config.CONTROLLER_TYPE]

    async_add_entities(
        [
            SmartifyBinarySensor(
                controller=controller,
                entity_description=entity_description,
                name=config_entry.title,
            )
            for entity_description in ENTITY_DESCRIPTIONS
            if entity_description.key == type_
        ]
    )


class SmartifyBinarySensor(SmartifyEntity, BinarySensorEntity):
    """Smartify Binary Sensor class."""

    def __init__(
        self,
        controller: SmartifyController,
        entity_description: BinarySensorEntityDescription,
        name: str,
    ) -> None:
        """Initialize the sensor class."""
        super().__init__(controller)
        self.entity_description = entity_description
        self._attr_name = name

    @property
    def is_on(self):
        """Return the status of the sensor."""
        return self.controller.is_on
