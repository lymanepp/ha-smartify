"""Custom integration to add Smart Controller to Home Assistant.

For more details about this integration, please refer to
https://github.com/lymanepp/ha-smartify
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STARTED,
    EVENT_HOMEASSISTANT_STOP,
    SERVICE_RELOAD,
    Platform,
)
from homeassistant.core import CoreState, Event, HomeAssistant, ServiceCall
from homeassistant.helpers import reload as reload_helper
from homeassistant.helpers.discovery import async_load_platform
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.service import async_register_admin_service
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

DATA_CONTROLLERS = "controllers"
DATA_YAML_RUNTIME = "yaml_runtime"
EVENT_YAML_RELOADED = f"event_{DOMAIN}_reloaded"

EntityBuilder = Callable[[SmartifyController], list[Entity]]
YamlPlatformReloader = Callable[[list[str]], Awaitable[None]]


@dataclass(slots=True)
class YamlRuntime:
    """Runtime state owned exclusively by native YAML configuration."""

    entry_ids: list[str] = field(default_factory=list)
    platform_reloaders: list[YamlPlatformReloader] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up native YAML controllers and the YAML reload action."""
    runtime = _yaml_runtime(hass)
    await _async_replace_yaml_controllers(hass, config.get(DOMAIN, {}))

    # Load one YAML-backed instance of each entity platform even when the
    # current YAML is empty. This allows adding Smartify YAML later and using
    # smartify.reload without restarting Home Assistant.
    discovery_info = {"entry_ids": runtime.entry_ids}
    for platform in PLATFORMS:
        hass.async_create_task(
            async_load_platform(hass, platform, DOMAIN, discovery_info, config)
        )

    async def async_reload_yaml(call: ServiceCall) -> None:
        """Reload Smartify's native YAML configuration."""
        reloaded_config = await reload_helper.async_integration_yaml_config(
            hass, DOMAIN, raise_on_failure=True
        )
        await _async_replace_yaml_controllers(
            hass, reloaded_config.get(DOMAIN, {}), reload_entities=True
        )
        hass.bus.async_fire(EVENT_YAML_RELOADED, context=call.context)

    async_register_admin_service(
        hass, DOMAIN, SERVICE_RELOAD, async_reload_yaml, schema={}
    )

    async def async_stop_yaml_controllers(_: Event) -> None:
        """Unload whichever YAML controllers are active at shutdown."""
        controllers = _controller_registry(hass)
        for entry_id in runtime.entry_ids:
            if (controller := controllers.pop(entry_id, None)) is not None:
                controller.async_unload()
        runtime.entry_ids.clear()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_stop_yaml_controllers)
    return True


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up this integration using UI."""
    controller = _create_controller(hass, config_entry)
    _controller_registry(hass)[config_entry.entry_id] = controller

    await _async_start_controller(hass, controller)
    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)
    config_entry.async_on_unload(config_entry.add_update_listener(async_reload_entry))
    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Handle removal of an entry."""
    if not await hass.config_entries.async_unload_platforms(config_entry, PLATFORMS):
        return False

    controller = _controller_registry(hass).pop(config_entry.entry_id, None)
    if controller is not None:
        controller.async_unload()

    return True


async def async_reload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> None:
    """Reload config entry."""
    await hass.config_entries.async_reload(config_entry.entry_id)


async def async_setup_yaml_platform(
    hass: HomeAssistant,
    entry_ids: list[str],
    async_add_entities: AddEntitiesCallback,
    build_entities: EntityBuilder,
) -> None:
    """Set up a reloadable entity platform for native YAML controllers."""
    entities: list[Entity] = []

    async def async_replace_entities(new_entry_ids: list[str]) -> None:
        """Remove this platform's old YAML entities and add the new set."""
        nonlocal entities

        if entities:
            await asyncio.gather(*(entity.async_remove() for entity in entities))

        controllers = _controller_registry(hass)
        entities = [
            entity
            for entry_id in new_entry_ids
            if (controller := controllers.get(entry_id)) is not None
            for entity in build_entities(controller)
        ]
        if entities:
            async_add_entities(entities)

    await async_replace_entities(entry_ids)
    _yaml_runtime(hass).platform_reloaders.append(async_replace_entities)


# #### Internal functions ####


def _domain_data(hass: HomeAssistant) -> dict[str, Any]:
    """Return Smartify's domain runtime data."""
    return hass.data.setdefault(DOMAIN, {})


def _controller_registry(hass: HomeAssistant) -> dict[str, SmartifyController]:
    """Return the shared runtime controller registry."""
    return _domain_data(hass).setdefault(DATA_CONTROLLERS, {})


def _yaml_runtime(hass: HomeAssistant) -> YamlRuntime:
    """Return native YAML lifecycle state."""
    return _domain_data(hass).setdefault(DATA_YAML_RUNTIME, YamlRuntime())


def get_controller(hass: HomeAssistant, entry_id: str) -> SmartifyController | None:
    """Return a runtime controller by YAML or config-entry id."""
    return _controller_registry(hass).get(entry_id)


async def _async_replace_yaml_controllers(
    hass: HomeAssistant,
    yaml_config: Mapping[str, Any],
    *,
    reload_entities: bool = False,
) -> None:
    """Replace native YAML controllers while preserving UI controllers."""
    runtime = _yaml_runtime(hass)

    async with runtime.lock:
        new_controllers = _build_yaml_controllers(hass, yaml_config)
        controllers = _controller_registry(hass)

        for entry_id in runtime.entry_ids:
            if (controller := controllers.pop(entry_id, None)) is not None:
                controller.async_unload()

        controllers.update(new_controllers)
        runtime.entry_ids = list(new_controllers)

        for controller in new_controllers.values():
            await _async_start_controller(hass, controller)

        if reload_entities:
            await asyncio.gather(
                *(
                    reloader(runtime.entry_ids)
                    for reloader in runtime.platform_reloaders
                )
            )


def _build_yaml_controllers(
    hass: HomeAssistant, yaml_config: Mapping[str, Any]
) -> dict[str, SmartifyController]:
    """Build and validate the complete native YAML controller set."""
    existing = _existing_identities(hass)
    controllers: dict[str, SmartifyController] = {}

    for controller_type in ControllerType:
        for entry_config in yaml_config.get(str(controller_type), []):
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
            controllers[entry.entry_id] = _create_controller(hass, entry)

    return controllers


async def _async_start_controller(
    hass: HomeAssistant, controller: SmartifyController
) -> None:
    """Start a controller now or when Home Assistant finishes starting."""

    async def start_controller(_: Event | None = None) -> None:
        await controller.async_setup(hass)

    if hass.state == CoreState.running:
        await start_controller()
    else:
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, start_controller)


def _create_controller(
    hass: HomeAssistant, config_entry: SmartifyEntrySource
) -> SmartifyController:
    """Create the controller matching an entry's declared type."""
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
    """Return the controller's real-world identity used for deduplication."""
    if controller_type == ControllerType.OCCUPANCY:
        return entry_config[Config.SENSOR_NAME]

    return entry_config[Config.CONTROLLED_ENTITY]


def _build_entry(
    hass: HomeAssistant,
    controller_type: ControllerType,
    entry_config: Mapping[str, Any],
) -> tuple[str, YamlControllerEntry]:
    """Build one synthetic in-memory entry for native YAML."""
    data = dict(entry_config)
    identity = _identity(controller_type, data)
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
    """Return type/identity keys for every UI-created controller."""
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
