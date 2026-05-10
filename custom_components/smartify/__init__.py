"""Custom integration to add Smart Controller to Home Assistant.

For more details about this integration, please refer to
https://github.com/lymanepp/ha-smartify
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import CoreState, Event, HomeAssistant

from .ceiling_fan_controller import CeilingFanController
from .const import DOMAIN, Config, ControllerType
from .exhaust_fan_controller import ExhaustFanController
from .light_controller import LightController
from .occupancy_controller import OccupancyController
from .smartify_controller import SmartifyController

PLATFORMS = [Platform.BINARY_SENSOR]


# https://developers.home-assistant.io/docs/config_entries_index/#setting-up-an-entry
async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    domain_data = hass.data.setdefault(DOMAIN, {})

    if (controller := _create_controller(hass, config_entry)) is None:
        return False

    domain_data[config_entry.entry_id] = controller

    async def start_controller(_: Event | None = None):
        await controller.async_setup(hass)

    if hass.state == CoreState.running:
        await start_controller()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, start_controller)

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    config_entry.async_on_unload(config_entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(
        config_entry, PLATFORMS
    ):
        controller: SmartifyController = hass.data[DOMAIN].pop(config_entry.entry_id)
        controller.async_unload()

    return unloaded


async def async_reload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Reload config entry."""
    await async_unload_entry(hass, config_entry)
    await async_setup_entry(hass, config_entry)


# #### Internal functions ####


def _create_controller(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> SmartifyController | None:
    type_ = config_entry.data[Config.CONTROLLER_TYPE]
    match type_:
        case ControllerType.CEILING_FAN:
            return CeilingFanController(hass, config_entry)
        case ControllerType.EXHAUST_FAN:
            return ExhaustFanController(hass, config_entry)
        case ControllerType.LIGHT:
            return LightController(hass, config_entry)
        case ControllerType.OCCUPANCY:
            return OccupancyController(hass, config_entry)

    raise TypeError(f"Invalid controller type: {type_}")
