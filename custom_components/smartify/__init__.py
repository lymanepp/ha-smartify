"""Custom integration to add Smart Controller to Home Assistant.

For more details about this integration, please refer to
https://github.com/lymanepp/ha-smartify
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_HOMEASSISTANT_STOP,
    Platform,
)
from homeassistant.core import CoreState, Event, HomeAssistant
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify

from .ceiling_fan_controller import CeilingFanController
from .config_schema import CONFIG_SCHEMA  # noqa: F401  used by HA to validate YAML
from .const import _LOGGER, DOMAIN, Config, ControllerType
from .entry_types import SmartifyEntrySource, YamlControllerEntry
from .exhaust_fan_controller import ExhaustFanController
from .light_controller import LightController
from .occupancy_controller import OccupancyController
from .smartify_controller import SmartifyController

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

# https://developers.home-assistant.io/docs/config_entries_index/#defining-a-config-schema
async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up controllers defined directly in YAML.

    This is entirely independent of the config-entry/UI path below: each
    `smartify.<controller_type>` YAML entry gets its own controller and
    entities immediately, in memory, for the lifetime of this HA run. Nothing
    is written to config entry storage and no config/options flow is
    involved -- YAML and the UI are two parallel ways to define controllers,
    not one feeding into the other.
    """
    if DOMAIN not in config:
        return True

    controllers = _controller_registry(hass)

    existing = _existing_identities(hass)
    entry_ids: list[str] = []

    for controller_type in ControllerType:
        for entry_config in config[DOMAIN].get(str(controller_type), []):
            dedup_key, entry = _build_entry(hass, controller_type, entry_config)

            if dedup_key in existing:
                _LOGGER.error(
                    "Skipping YAML-configured %s '%s': already configured via "
                    "the UI, which takes precedence. Remove one of the two "
                    "configurations.",
                    controller_type,
                    dedup_key.split(":", 1)[1],
                )
                continue

            if entry.entry_id in controllers:
                _LOGGER.error(
                    "Skipping YAML-configured %s '%s': its id '%s' collides "
                    "with another YAML entry. Set a distinct 'unique_id' on "
                    "one of them.",
                    controller_type,
                    dedup_key.split(":", 1)[1],
                    entry.entry_id,
                )
                continue

            existing.add(dedup_key)

            controller = _create_controller(hass, entry)
            controllers[entry.entry_id] = controller
            entry_ids.append(entry.entry_id)

            async def start_controller(
                _: Event | None = None, controller: SmartifyController = controller
            ) -> None:
                await controller.async_setup(hass)

            if hass.state == CoreState.running:
                hass.async_create_task(start_controller())
            else:
                hass.bus.async_listen_once(
                    EVENT_HOMEASSISTANT_STARTED, start_controller
                )

    if not entry_ids:
        return True

    discovery_info = {"entry_ids": entry_ids}

    for platform in PLATFORMS:
        hass.async_create_task(
            async_load_platform(hass, platform, DOMAIN, discovery_info, config)
        )

    async def _async_stop_yaml_controllers(_: Event) -> None:
        for entry_id in entry_ids:
            if (controller := controllers.pop(entry_id, None)) is not None:
                controller.async_unload()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop_yaml_controllers)

    return True


# https://developers.home-assistant.io/docs/config_entries_index/#setting-up-an-entry
async def async_setup_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Set up this integration using UI."""
    controller = _create_controller(hass, config_entry)
    _controller_registry(hass)[config_entry.entry_id] = controller

    async def start_controller(_: Event | None = None):
        await controller.async_setup(hass)

    if hass.state == CoreState.running:
        await start_controller()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, start_controller)

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    config_entry.async_on_unload(config_entry.add_update_listener(async_reload_entry))

    return True


async def async_unload_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> bool:
    """Handle removal of an entry."""
    if not await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS):
        return False

    controller = _controller_registry(hass).pop(config_entry.entry_id, None)
    if controller is not None:
        controller.async_unload()

    return True


async def async_reload_entry(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(config_entry.entry_id)


# #### Internal functions ####


def _controller_registry(hass: HomeAssistant) -> dict[str, SmartifyController]:
    """Return the shared runtime controller registry."""
    return hass.data.setdefault(DOMAIN, {})


def get_controller(hass: HomeAssistant, entry_id: str) -> SmartifyController | None:
    """Return a runtime controller by YAML or config-entry id."""
    return _controller_registry(hass).get(entry_id)


def _create_controller(
    hass: HomeAssistant, config_entry: SmartifyEntrySource
) -> SmartifyController:
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


def _identity(controller_type: ControllerType, entry_config: Mapping[str, Any]) -> str:
    """Return the value that identifies a controller for dedup/naming purposes.

    This is the same value the config flow uses to compute a unique_id:
    `sensor_name` for occupancy controllers, `controlled_entity` for the rest.
    It is independent of the optional YAML `unique_id`/`name` overrides below,
    since it answers "which real-world entity/sensor is this", not "what
    should its entity registry id or title be".
    """
    if controller_type == ControllerType.OCCUPANCY:
        return entry_config[Config.SENSOR_NAME]

    return entry_config[Config.CONTROLLED_ENTITY]


def _build_entry(
    hass: HomeAssistant,
    controller_type: ControllerType,
    entry_config: Mapping[str, Any],
) -> tuple[str, YamlControllerEntry]:
    """Build the YamlControllerEntry for one YAML list item.

    Returns (dedup_key, entry). `dedup_key` is `"<type>:<identity>"`, matching
    `_existing_identities` below, and is independent of any explicit
    `unique_id`/`name` override -- those affect *how the controller is
    labeled/identified in the registry*, not *which real-world entity it is*.
    """
    data = dict(entry_config)
    identity = _identity(controller_type, data)

    # Neither field is a controller setting -- both are consumed here and
    # never stored on `data`, the same way the config flow strips
    # SENSOR_NAME out of an occupancy entry before saving it.
    explicit_unique_id = data.pop(Config.UNIQUE_ID, None)
    explicit_name = data.pop(Config.NAME, None)

    if controller_type == ControllerType.OCCUPANCY:
        data.pop(Config.SENSOR_NAME, None)
        title = identity
    else:
        title = explicit_name or _title_for_entity(hass, identity)

    entry_id = (
        f"yaml_{explicit_unique_id}"
        if explicit_unique_id
        else f"yaml_{controller_type}_{slugify(identity)}"
    )

    entry = YamlControllerEntry(
        entry_id=entry_id,
        title=title,
        data={Config.CONTROLLER_TYPE: controller_type, **data},
    )

    return f"{controller_type}:{identity}", entry


def _title_for_entity(hass: HomeAssistant, entity_id: str) -> str:
    """Return the entity's friendly name, or the entity_id if not yet known."""
    state = hass.states.get(entity_id)
    return state.name if state else entity_id


def _existing_identities(hass: HomeAssistant) -> set[str]:
    """Return `type:identity` keys for every UI-created (config entry) controller.

    For occupancy this relies on `config_entry.title`, since that's the only
    place the config flow stores the sensor_name it was given (it deliberately
    isn't kept in `data`) -- the same convention `_build_entry` above follows
    for YAML.
    """
    identities: set[str] = set()

    for config_entry in hass.config_entries.async_entries(DOMAIN):
        data = config_entry.data | config_entry.options
        controller_type = data.get(Config.CONTROLLER_TYPE)

        identity = (
            config_entry.title
            if controller_type == ControllerType.OCCUPANCY
            else data.get(Config.CONTROLLED_ENTITY)
        )

        if identity:
            identities.add(f"{controller_type}:{identity}")

    return identities
