"""Binary sensor platform for Smartify."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from . import get_controller, async_setup_yaml_platform
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


def _binary_sensors_for_controller(
    controller: SmartifyController,
) -> list["SmartifyBinarySensor"]:
    """Build the binary sensor entities for one controller, regardless of
    whether it came from a config entry (UI) or a YAML-configured entry.
    """
    type_ = controller.config_entry.data[Config.CONTROLLER_TYPE]

    return [
        SmartifyBinarySensor(
            controller=controller,
            entity_description=entity_description,
        )
        for entity_description in ENTITY_DESCRIPTIONS
        if entity_description.key == type_
    ]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform for a UI-created config entry."""
    controller = get_controller(hass, config_entry.entry_id)
    if isinstance(controller, SmartifyController):
        async_add_entities(_binary_sensors_for_controller(controller))


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up binary sensors for YAML-configured controllers.

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
        _binary_sensors_for_controller,
    )


class SmartifyBinarySensor(SmartifyEntity, BinarySensorEntity):
    """Smartify Binary Sensor class."""

    def __init__(
        self,
        controller: SmartifyController,
        entity_description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the sensor class."""
        super().__init__(controller)
        self.entity_description = entity_description
        # Primary entity: use the device/controller name without adding a suffix.
        self._attr_name = None

    @property
    def is_on(self):
        """Return the status of the sensor."""
        return self.controller.is_on
