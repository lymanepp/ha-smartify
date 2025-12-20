"""Custom integration to add Smartify to Home Assistant.

For more details about this integration, please refer to
https://github.com/lymanepp/ha-smartify
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STARTED, Platform
from homeassistant.core import CoreState, Event, HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.util import slugify

from .const import DOMAIN, Config, ControllerType
from .smart_ceiling_fan import SmartCeilingFan
from .smart_exhaust_fan import SmartExhaustFan
from .smart_light import SmartLight
from .smart_occupancy import SmartOccupancy
from .smartify import SmartifyBase

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.BINARY_SENSOR]

CONF_CONTROLLERS = "controllers"

# YAML schema: authoritative when provided.
CONTROLLER_SCHEMA = vol.Schema(
    {
        vol.Required(str(Config.CONTROLLER_TYPE)): cv.string,
        vol.Optional(str(Config.CONTROLLED_ENTITY)): cv.entity_id,
        vol.Optional(str(Config.SENSOR_NAME)): cv.string,
    },
    extra=vol.ALLOW_EXTRA,
)

CONFIG_SCHEMA = vol.Schema(
    {
        DOMAIN: vol.Schema(
            {
                vol.Required(CONF_CONTROLLERS): vol.All(
                    cv.ensure_list, [CONTROLLER_SCHEMA]
                ),
            },
            extra=vol.ALLOW_EXTRA,
        )
    },
    extra=vol.ALLOW_EXTRA,
)


@dataclass
class ControllerData:
    controller: SmartifyBase


@dataclass(frozen=True, slots=True)
class YamlPseudoEntry:
    """Minimal stand-in for a ConfigEntry when running YAML-authoritative.

    Controllers and entities in this integration currently expect a config_entry-like
    object with entry_id, title, data, and options.
    """

    entry_id: str
    title: str
    data: dict[str, Any]
    options: dict[str, Any]


def _yaml_unique_id(controller_conf: dict[str, Any]) -> str:
    """Return the same unique_id convention used by config_flow."""
    type_raw = controller_conf.get(str(Config.CONTROLLER_TYPE))

    if type_raw == ControllerType.OCCUPANCY:
        sensor_name = controller_conf.get(str(Config.SENSOR_NAME), "")
        return f"{DOMAIN}__{ControllerType.OCCUPANCY}__" + slugify(sensor_name)

    controlled_entity = controller_conf.get(str(Config.CONTROLLED_ENTITY), "")
    return f"{DOMAIN}__" + slugify(controlled_entity)


def _entry_unique_id(entry: ConfigEntry) -> str:
    """Return the unique_id convention implied by entry.data (matches config_flow)."""
    type_raw = entry.data.get(Config.CONTROLLER_TYPE)

    if type_raw == ControllerType.OCCUPANCY:
        sensor_name = entry.data.get(Config.SENSOR_NAME) or entry.title
        return f"{DOMAIN}__{ControllerType.OCCUPANCY}__" + slugify(str(sensor_name))

    controlled_entity = entry.data.get(Config.CONTROLLED_ENTITY, "")
    return f"{DOMAIN}__" + slugify(str(controlled_entity))


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up Smartify from YAML.

    If YAML is present, it is authoritative for the controllers defined there.
    Those controllers are created and started directly, and any overlapping UI
    config entries will be ignored.
    """
    hass.data.setdefault(DOMAIN, {})
    domain_conf = config.get(DOMAIN)

    # No YAML: run config-entry mode only.
    if not domain_conf or not domain_conf.get(CONF_CONTROLLERS):
        hass.data[DOMAIN]["yaml_mode"] = False
        hass.data[DOMAIN]["yaml_unique_ids"] = set()
        hass.data[DOMAIN]["yaml_controllers"] = {}
        return True

    controllers_conf: list[dict[str, Any]] = domain_conf[CONF_CONTROLLERS]
    yaml_controllers: dict[str, SmartifyBase] = {}
    yaml_unique_ids: set[str] = set()

    for c in controllers_conf:
        unique_id = _yaml_unique_id(c)
        yaml_unique_ids.add(unique_id)

        title = (
            c.get(str(Config.SENSOR_NAME))
            if c.get(str(Config.CONTROLLER_TYPE)) == ControllerType.OCCUPANCY
            else c.get(str(Config.CONTROLLED_ENTITY), unique_id)
        )

        pseudo_entry = YamlPseudoEntry(
            entry_id=unique_id,  # stable for version-controlled YAML
            title=str(title),
            data=dict(c),
            options={},
        )

        controller = _create_controller_from_data(hass, pseudo_entry)
        if controller is None:
            _LOGGER.error("Failed to create YAML controller: %s", unique_id)
            continue

        yaml_controllers[unique_id] = controller

    hass.data[DOMAIN]["yaml_mode"] = True
    hass.data[DOMAIN]["yaml_unique_ids"] = yaml_unique_ids
    hass.data[DOMAIN]["yaml_controllers"] = yaml_controllers

    async def start_yaml_controllers(_: Event | None = None) -> None:
        for uid, controller in yaml_controllers.items():
            if controller.is_setup:
                continue
            _LOGGER.debug("Starting YAML controller: %s", uid)
            await controller.async_setup(hass)
            controller.is_setup = True

    if hass.state == CoreState.running:
        await start_yaml_controllers()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, start_yaml_controllers)

    # Load platforms for YAML controllers (no config entries involved).
    await async_load_platform(
        hass,
        Platform.BINARY_SENSOR,
        DOMAIN,
        {"controllers": yaml_controllers},
        config,
    )

    _LOGGER.info(
        "Smartify running in YAML-authoritative mode with %d controller(s). "
        "Overlapping UI config entries will be ignored.",
        len(yaml_controllers),
    )
    return True


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry[ControllerData]
) -> bool:
    """Set up this integration using UI config entries."""
    _LOGGER.debug("Setting up integration entry: %s", entry.entry_id)

    # YAML-authoritative: ignore overlapping entries to avoid drift.
    if hass.data.get(DOMAIN, {}).get("yaml_mode"):
        yaml_uids: set[str] = hass.data[DOMAIN].get("yaml_unique_ids", set())
        entry_uid = _entry_unique_id(entry)
        if entry_uid in yaml_uids:
            _LOGGER.warning(
                "Ignoring config entry %s because YAML defines %s (YAML is authoritative).",
                entry.entry_id,
                entry_uid,
            )
            return True

    if (controller := _create_controller(hass, entry)) is None:
        _LOGGER.error("Failed to create controller for entry: %s", entry.entry_id)
        return False

    entry.runtime_data.controller = controller

    async def start_controller(_: Event | None = None):
        if controller.is_setup:
            _LOGGER.warning("Controller already started for entry: %s", entry.entry_id)
            return
        _LOGGER.debug("Starting controller for entry: %s", entry.entry_id)
        await controller.async_setup(hass)
        controller.is_setup = True  # Mark as started

    if hass.state == CoreState.running:
        await start_controller()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, start_controller)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: ConfigEntry[ControllerData]
) -> bool:
    """Handle removal of an entry."""
    _LOGGER.debug("Unloading integration: %s", entry.entry_id)

    controller = entry.runtime_data.controller
    if controller:
        _LOGGER.debug("Calling async_unload for controller: %s", entry.entry_id)
        controller.async_unload()

    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload config entry."""
    _LOGGER.debug("Reloading integration: %s", entry.entry_id)
    await async_unload_entry(hass, entry)
    await async_setup_entry(hass, entry)


# #### Internal functions ####


def _create_controller(
    hass: HomeAssistant, entry: ConfigEntry[ControllerData]
) -> SmartifyBase | None:
    """Factory method to create the appropriate controller."""
    type_ = entry.data.get(Config.CONTROLLER_TYPE)

    match type_:
        case ControllerType.CEILING_FAN:
            return SmartCeilingFan(hass, entry)
        case ControllerType.EXHAUST_FAN:
            return SmartExhaustFan(hass, entry)
        case ControllerType.LIGHT:
            return SmartLight(hass, entry)
        case ControllerType.OCCUPANCY:
            return SmartOccupancy(hass, entry)

    _LOGGER.error("Invalid controller type: %s", type_)
    return None


def _create_controller_from_data(
    hass: HomeAssistant, pseudo_entry: YamlPseudoEntry
) -> SmartifyBase | None:
    """Create controller from YAML data using a pseudo entry."""
    type_raw = pseudo_entry.data.get(str(Config.CONTROLLER_TYPE), "")

    # Normalize: allow either enum value or raw string
    try:
        type_ = ControllerType(type_raw)
    except Exception:
        _LOGGER.error("Invalid controller type in YAML: %s", type_raw)
        return None

    match type_:
        case ControllerType.CEILING_FAN:
            return SmartCeilingFan(hass, pseudo_entry)  # type: ignore[arg-type]
        case ControllerType.EXHAUST_FAN:
            return SmartExhaustFan(hass, pseudo_entry)  # type: ignore[arg-type]
        case ControllerType.LIGHT:
            return SmartLight(hass, pseudo_entry)  # type: ignore[arg-type]
        case ControllerType.OCCUPANCY:
            return SmartOccupancy(hass, pseudo_entry)  # type: ignore[arg-type]

    _LOGGER.error("Invalid controller type in YAML: %s", type_)
    return None
