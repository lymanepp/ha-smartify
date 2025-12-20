"""Binary sensor platform for smartify."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ControllerData
from .const import Config, ControllerType
from .entity import SmartControllerEntity
from .smartify import SmartifyBase

_LOGGER = logging.getLogger(__name__)

ENTITY_DESCRIPTIONS = [
    BinarySensorEntityDescription(
        key=ControllerType.OCCUPANCY,
        device_class=BinarySensorDeviceClass.OCCUPANCY,
        icon="mdi:account",
    ),
]


async def async_setup_platform(
    hass: HomeAssistant,
    config: dict[str, Any],
    async_add_entities: AddEntitiesCallback,
    discovery_info: dict[str, Any] | None = None,
) -> None:
    """Set up via YAML-authoritative discovery (no config entries)."""
    if not discovery_info:
        return

    controllers: dict[str, SmartifyBase] = discovery_info.get("controllers", {})
    entities: list[SmartControllerBinarySensor] = []

    for controller in controllers.values():
        type_ = controller.data.get(Config.CONTROLLER_TYPE)
        if type_ != ControllerType.OCCUPANCY:
            continue

        for entity_description in ENTITY_DESCRIPTIONS:
            if entity_description.key == type_:
                name = (
                    getattr(controller.config_entry, "title", None)
                    or controller.name
                    or "Occupancy"
                )
                entities.append(
                    SmartControllerBinarySensor(
                        controller=controller,
                        entity_description=entity_description,
                        name=name,
                    )
                )

    if entities:
        async_add_entities(entities)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry[ControllerData],
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the platform from a config entry (UI flow)."""
    controller = entry.runtime_data.controller
    type_ = entry.data.get(Config.CONTROLLER_TYPE)

    _LOGGER.debug("Binary sensor type from config: %s", type_)
    _LOGGER.debug(
        "Available entity descriptions: %s", [desc.key for desc in ENTITY_DESCRIPTIONS]
    )

    async_add_entities(
        [
            SmartControllerBinarySensor(
                controller=controller,
                entity_description=entity_description,
                name=entry.title,
            )
            for entity_description in ENTITY_DESCRIPTIONS
            if entity_description.key == type_
        ]
    )


class SmartControllerBinarySensor(SmartControllerEntity, BinarySensorEntity):
    """Smartify Binary Sensor class."""

    def __init__(
        self,
        controller: SmartifyBase,
        entity_description: BinarySensorEntityDescription,
        name: str,
    ) -> None:
        """Initialize the sensor class."""
        super().__init__(controller)
        self.entity_description = entity_description
        self._attr_name = name

    @property
    def is_on(self) -> bool:
        """Return the status of the sensor."""
        return self.controller.is_on
