"""Tests for controllers defined directly in YAML.

These must run entirely independently of config entries: no entry should be
created, updated, or shown in the UI, and no options flow is involved -- the
controller and its entities exist purely in memory for the life of the HA run.
"""

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.smartify import DATA_CONTROLLERS, async_setup
from custom_components.smartify.const import DOMAIN, Config, ControllerType
from custom_components.smartify.light_controller import LightController
from custom_components.smartify.occupancy_controller import OccupancyController


def _yaml_controllers(hass):
    return hass.data.get(DOMAIN, {}).get(DATA_CONTROLLERS, {})


@pytest.mark.asyncio
async def test_async_setup_without_domain_key_is_a_noop(hass):
    """No 'smartify:' key in YAML means nothing to set up."""
    assert await async_setup(hass, {}) is True
    await hass.async_block_till_done()

    assert _yaml_controllers(hass) == {}
    assert hass.config_entries.async_entries(DOMAIN) == []


@pytest.mark.asyncio
async def test_yaml_light_creates_a_controller_with_no_config_entry(hass):
    """A YAML-defined light gets a real controller but never a config entry."""
    hass.states.async_set(
        "light.office_light", "off", {"friendly_name": "Office Light"}
    )

    config = {
        DOMAIN: {
            "light": [
                {
                    Config.CONTROLLED_ENTITY: "light.office_light",
                    Config.AUTO_OFF_MINUTES: 5,
                }
            ]
        }
    }

    assert await async_setup(hass, config) is True
    await hass.async_block_till_done()

    # Nothing was written to config entry storage.
    assert hass.config_entries.async_entries(DOMAIN) == []

    controllers = _yaml_controllers(hass)
    assert len(controllers) == 1
    controller = next(iter(controllers.values()))
    assert isinstance(controller, LightController)
    assert controller.config_entry.title == "Office Light"
    assert controller.config_entry.data[Config.AUTO_OFF_MINUTES] == 5


@pytest.mark.asyncio
async def test_yaml_occupancy_creates_a_real_binary_sensor_entity(hass):
    """The occupancy binary_sensor entity is actually created via discovery,
    with no config entry involved.
    """
    config = {
        DOMAIN: {
            "occupancy": [
                {
                    Config.SENSOR_NAME: "Office Occupancy",
                    Config.TRIGGER_ENTITIES: ["binary_sensor.office_motion"],
                    Config.DECAY_MINUTES: 10,
                }
            ]
        }
    }

    assert await async_setup(hass, config) is True
    await hass.async_block_till_done()

    assert hass.config_entries.async_entries(DOMAIN) == []

    controllers = _yaml_controllers(hass)
    assert len(controllers) == 1
    controller = next(iter(controllers.values()))
    assert isinstance(controller, OccupancyController)
    assert controller.config_entry.title == "Office Occupancy"

    matching_states = [
        state
        for state in hass.states.async_all("binary_sensor")
        if state.entity_id != "binary_sensor.office_motion"
    ]
    assert len(matching_states) == 1


@pytest.mark.asyncio
async def test_yaml_controller_already_configured_via_ui_is_skipped(hass):
    """If the same entity is already controlled by a UI config entry, the
    YAML definition is skipped (with a warning) instead of double-controlling
    it.
    """
    hass.states.async_set(
        "light.office_light", "off", {"friendly_name": "Office Light"}
    )

    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Office Light",
        unique_id=f"{DOMAIN}__light_office_light",
        data={
            Config.CONTROLLER_TYPE: ControllerType.LIGHT,
            Config.CONTROLLED_ENTITY: "light.office_light",
        },
    )
    entry.add_to_hass(hass)

    config = {
        DOMAIN: {
            "light": [
                {
                    Config.CONTROLLED_ENTITY: "light.office_light",
                    Config.AUTO_OFF_MINUTES: 5,
                }
            ]
        }
    }

    assert await async_setup(hass, config) is True
    await hass.async_block_till_done()

    assert _yaml_controllers(hass) == {}
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1


@pytest.mark.asyncio
async def test_yaml_import_falls_back_to_entity_id_when_state_missing(hass):
    """If the controlled entity has no state yet, the entity_id is used as
    the title.
    """
    config = {
        DOMAIN: {
            "light": [
                {
                    Config.CONTROLLED_ENTITY: "light.not_yet_loaded",
                }
            ]
        }
    }

    assert await async_setup(hass, config) is True
    await hass.async_block_till_done()

    controllers = _yaml_controllers(hass)
    assert len(controllers) == 1
    controller = next(iter(controllers.values()))
    assert controller.config_entry.title == "light.not_yet_loaded"


@pytest.mark.asyncio
async def test_yaml_name_override_is_used_even_when_entity_state_is_missing(hass):
    """An explicit 'name' wins over both the derived friendly name and the
    entity_id fallback -- useful since the controlled entity may not have a
    state yet this early in startup.
    """
    config = {
        DOMAIN: {
            "light": [
                {
                    Config.NAME: "Not Yet Loaded Light",
                    Config.CONTROLLED_ENTITY: "light.not_yet_loaded",
                }
            ]
        }
    }

    assert await async_setup(hass, config) is True
    await hass.async_block_till_done()

    controller = next(iter(_yaml_controllers(hass).values()))
    assert controller.config_entry.title == "Not Yet Loaded Light"
    # 'name' is consumed for the title only, never stored on controller data.
    assert Config.NAME not in controller.config_entry.data


@pytest.mark.asyncio
async def test_yaml_unique_id_override_is_used_for_the_entry_id(hass):
    """An explicit 'unique_id' determines the synthetic entry_id instead of
    slugifying the controlled_entity/sensor_name, so renaming the display
    name or entity later doesn't change entity registry identity.
    """
    config = {
        DOMAIN: {
            "occupancy": [
                {
                    Config.UNIQUE_ID: "office_occupancy_v1",
                    Config.SENSOR_NAME: "Office Occupancy",
                    Config.SUSTAIN_ENTITIES: ["binary_sensor.office_mmwave"],
                }
            ]
        }
    }

    assert await async_setup(hass, config) is True
    await hass.async_block_till_done()

    controllers = _yaml_controllers(hass)
    assert list(controllers) == ["yaml_office_occupancy_v1"]
    controller = controllers["yaml_office_occupancy_v1"]
    # 'unique_id' is consumed for the entry_id only, never stored on data.
    assert Config.UNIQUE_ID not in controller.config_entry.data


@pytest.mark.asyncio
async def test_yaml_duplicate_unique_id_within_yaml_is_skipped(hass):
    """Two YAML entries that collide on the same explicit unique_id: the
    second is skipped (with an error logged) rather than silently
    overwriting the first.
    """
    config = {
        DOMAIN: {
            "light": [
                {
                    Config.UNIQUE_ID: "dup",
                    Config.CONTROLLED_ENTITY: "light.first",
                },
                {
                    Config.UNIQUE_ID: "dup",
                    Config.CONTROLLED_ENTITY: "light.second",
                },
            ]
        }
    }

    assert await async_setup(hass, config) is True
    await hass.async_block_till_done()

    controllers = _yaml_controllers(hass)
    assert len(controllers) == 1
    assert controllers["yaml_dup"].controlled_entity == "light.first"


@pytest.mark.asyncio
async def test_yaml_sustain_only_occupancy_from_converted_config(hass):
    """Regression check against a real converted entry (Living Room
    Occupancy): sustain-only, empty trigger_entities, decay_minutes: 0.
    """
    config = {
        DOMAIN: {
            "occupancy": [
                {
                    Config.SENSOR_NAME: "Living Room Occupancy",
                    Config.TRIGGER_ENTITIES: [],
                    Config.SUSTAIN_ENTITIES: ["binary_sensor.any_home"],
                    Config.DECAY_MINUTES: 0,
                    Config.REQUIRED_OFF_ENTITIES: ["binary_sensor.all_sleeping"],
                }
            ]
        }
    }

    assert await async_setup(hass, config) is True
    await hass.async_block_till_done()

    controller = next(iter(_yaml_controllers(hass).values()))
    assert isinstance(controller, OccupancyController)
    assert controller.occupancy_strategy == "sustain_only"


@pytest.mark.asyncio
async def test_yaml_auto_off_only_light_from_converted_config(hass):
    """Regression check against a real converted entry (Bedroom 2 Closet
    Light): only auto_off_minutes, no trigger_entity at all.
    """
    hass.states.async_set(
        "light.bedroom_2_closet_light", "off", {"friendly_name": "Closet Light"}
    )

    config = {
        DOMAIN: {
            "light": [
                {
                    Config.CONTROLLED_ENTITY: "light.bedroom_2_closet_light",
                    Config.AUTO_OFF_MINUTES: 5,
                }
            ]
        }
    }

    assert await async_setup(hass, config) is True
    await hass.async_block_till_done()

    controller = next(iter(_yaml_controllers(hass).values()))
    assert isinstance(controller, LightController)
    assert controller.trigger_entity is None
    assert controller.config_entry.data[Config.AUTO_OFF_MINUTES] == 5


@pytest.mark.asyncio
async def test_yaml_reload_replaces_only_yaml_controllers(hass):
    """smartify.reload replaces YAML controllers and leaves UI entries alone."""
    from unittest.mock import patch

    from homeassistant.const import SERVICE_RELOAD

    ui_entry = MockConfigEntry(
        domain=DOMAIN,
        title="UI Light",
        unique_id=f"{DOMAIN}__light_ui_light",
        data={
            Config.CONTROLLER_TYPE: ControllerType.LIGHT,
            Config.CONTROLLED_ENTITY: "light.ui_light",
        },
    )
    ui_entry.add_to_hass(hass)

    initial_config = {
        DOMAIN: {
            "light": [
                {
                    Config.UNIQUE_ID: "yaml_first",
                    Config.CONTROLLED_ENTITY: "light.first",
                }
            ]
        }
    }
    reloaded_config = {
        DOMAIN: {
            "light": [
                {
                    Config.UNIQUE_ID: "yaml_second",
                    Config.CONTROLLED_ENTITY: "light.second",
                }
            ]
        }
    }

    assert await async_setup(hass, initial_config) is True
    await hass.async_block_till_done()
    old_controller = _yaml_controllers(hass)["yaml_yaml_first"]

    with (
        patch(
            "custom_components.smartify.reload_helper.async_integration_yaml_config",
            return_value=reloaded_config,
        ),
        patch.object(old_controller, "async_unload", wraps=old_controller.async_unload) as unload,
    ):
        await hass.services.async_call(DOMAIN, SERVICE_RELOAD, blocking=True)

    controllers = _yaml_controllers(hass)
    assert "yaml_yaml_first" not in controllers
    assert "yaml_yaml_second" in controllers
    assert unload.call_count == 1
    assert hass.config_entries.async_entries(DOMAIN) == [ui_entry]


@pytest.mark.asyncio
async def test_yaml_reload_can_remove_all_yaml_controllers(hass):
    """Reloading after removing the YAML section unloads all YAML controllers."""
    from unittest.mock import patch

    from homeassistant.const import SERVICE_RELOAD

    config = {
        DOMAIN: {
            "occupancy": [
                {
                    Config.SENSOR_NAME: "Office Occupancy",
                    Config.SUSTAIN_ENTITIES: ["binary_sensor.office_presence"],
                }
            ]
        }
    }

    assert await async_setup(hass, config) is True
    await hass.async_block_till_done()
    assert _yaml_controllers(hass)

    with patch(
        "custom_components.smartify.reload_helper.async_integration_yaml_config",
        return_value={},
    ):
        await hass.services.async_call(DOMAIN, SERVICE_RELOAD, blocking=True)

    assert _yaml_controllers(hass) == {}


@pytest.mark.asyncio
async def test_yaml_reload_service_is_available_without_initial_yaml(hass):
    """YAML may be added later and loaded without restarting Home Assistant."""
    from unittest.mock import patch

    from homeassistant.const import SERVICE_RELOAD

    assert await async_setup(hass, {}) is True
    await hass.async_block_till_done()
    assert hass.services.has_service(DOMAIN, SERVICE_RELOAD)

    reloaded_config = {
        DOMAIN: {
            "light": [
                {
                    Config.UNIQUE_ID: "later",
                    Config.CONTROLLED_ENTITY: "light.added_later",
                }
            ]
        }
    }
    with patch(
        "custom_components.smartify.reload_helper.async_integration_yaml_config",
        return_value=reloaded_config,
    ):
        await hass.services.async_call(DOMAIN, SERVICE_RELOAD, blocking=True)

    assert "yaml_later" in _yaml_controllers(hass)
