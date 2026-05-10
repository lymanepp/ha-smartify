import pytest
from homeassistant import data_entry_flow
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from custom_components.smartify.const import (
    DOMAIN,
    Config,
    ControllerType,
)


@pytest.mark.asyncio
async def test_user_flow_starts_at_menu(
    hass,
):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    assert result["type"] == (data_entry_flow.FlowResultType.MENU)

    assert result["menu_options"]


@pytest.mark.asyncio
async def test_all_menu_options_are_selectable(
    hass,
):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    for option in result["menu_options"]:
        flow = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user"},
        )

        next_result = await hass.config_entries.flow.async_configure(
            flow["flow_id"],
            {"next_step_id": option},
        )

        assert next_result["type"] in (
            data_entry_flow.FlowResultType.FORM,
            data_entry_flow.FlowResultType.CREATE_ENTRY,
            data_entry_flow.FlowResultType.ABORT,
            data_entry_flow.FlowResultType.MENU,
        )


@pytest.mark.asyncio
async def test_invalid_menu_selection_rejected(
    hass,
):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    with pytest.raises(Exception):
        await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"next_step_id": "invalid"},
        )


@pytest.mark.asyncio
async def test_multiple_flows_can_start(
    hass,
):
    result1 = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    result2 = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    assert result1
    assert result2


@pytest.mark.asyncio
async def test_existing_entry_does_not_break_flow(
    hass,
):
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="existing",
        unique_id="existing",
        data={
            Config.CONTROLLER_TYPE: ControllerType.LIGHT,
        },
    )

    entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    assert result["type"] in (
        data_entry_flow.FlowResultType.MENU,
        data_entry_flow.FlowResultType.FORM,
    )


@pytest.mark.asyncio
async def test_flow_result_contains_required_keys(
    hass,
):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    assert "type" in result


@pytest.mark.asyncio
async def test_light_step_reachable(
    hass,
):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "light"},
    )

    assert result["type"] in (
        data_entry_flow.FlowResultType.FORM,
        data_entry_flow.FlowResultType.CREATE_ENTRY,
        data_entry_flow.FlowResultType.ABORT,
    )


@pytest.mark.asyncio
async def test_ceiling_fan_step_reachable(
    hass,
):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "ceiling_fan"},
    )

    assert result["type"] in (
        data_entry_flow.FlowResultType.FORM,
        data_entry_flow.FlowResultType.CREATE_ENTRY,
        data_entry_flow.FlowResultType.ABORT,
    )


@pytest.mark.asyncio
async def test_exhaust_fan_step_reachable(
    hass,
):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "exhaust_fan"},
    )

    assert result["type"] in (
        data_entry_flow.FlowResultType.FORM,
        data_entry_flow.FlowResultType.CREATE_ENTRY,
        data_entry_flow.FlowResultType.ABORT,
    )


@pytest.mark.asyncio
async def test_occupancy_step_reachable(
    hass,
):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"next_step_id": "occupancy"},
    )

    assert result["type"] in (
        data_entry_flow.FlowResultType.FORM,
        data_entry_flow.FlowResultType.CREATE_ENTRY,
        data_entry_flow.FlowResultType.ABORT,
    )


@pytest.mark.asyncio
async def test_repeated_menu_navigation(
    hass,
):
    for _ in range(5):
        result = await hass.config_entries.flow.async_init(
            DOMAIN,
            context={"source": "user"},
        )

        assert result["type"] == (data_entry_flow.FlowResultType.MENU)


@pytest.mark.asyncio
async def test_flow_ids_are_unique(
    hass,
):
    result1 = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    result2 = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    assert result1["flow_id"] != result2["flow_id"]


@pytest.mark.asyncio
async def test_invalid_reconfigure_does_not_crash(
    hass,
):
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": "user"},
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        None,
    )

    assert result["type"] in (
        data_entry_flow.FlowResultType.MENU,
        data_entry_flow.FlowResultType.FORM,
        data_entry_flow.FlowResultType.ABORT,
    )
