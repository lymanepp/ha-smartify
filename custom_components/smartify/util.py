"""Utility functions."""

from collections.abc import Iterable
from math import e

from homeassistant import util
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry
from homeassistant.util.percentage import (
    percentage_to_ranged_value,
    ranged_value_to_percentage,
)
from homeassistant.util.unit_conversion import TemperatureConverter

from .const import ON_OFF_STATES


def absolute_humidity(temp: tuple[float, str], hum: float):
    """Calculate absolute humidity from temperature and humidity."""
    t_c = TemperatureConverter.convert(*temp, UnitOfTemperature.CELSIUS)

    return hum * 6.112 * 2.1674 * e ** ((t_c * 17.67) / (t_c + 243.5)) / (t_c + 273.15)


def summer_simmer_index(hass: HomeAssistant, temp: tuple[float, str], hum: float):
    """Calculate summer simmer index from temperature and humidity."""
    t_f = TemperatureConverter.convert(*temp, UnitOfTemperature.FAHRENHEIT)

    ssi = 1.98 * (t_f - (0.55 - (0.0055 * hum)) * (t_f - 58)) - 56.83

    return TemperatureConverter.convert(
        ssi, UnitOfTemperature.FAHRENHEIT, hass.config.units.temperature_unit
    )


def remove_empty(values):
    """Remove entries if they contain 'None'."""
    return [value for value in values if value is not None]


def float_with_unit(state: State, default_unit: str) -> tuple[float, str]:
    """Return state's value with unit of measurement as a tuple."""
    value = util.convert(state.state, float)
    assert value is not None
    return (value, state.attributes.get(ATTR_UNIT_OF_MEASUREMENT, default_unit))


def extrapolate_value(
    source_value: float,
    source_range: tuple[float, float],
    target_range: tuple[float, float],
    low_default: float | None = None,
    high_default: float | None = None,
):
    """Extrapolate a value in the target range from a value in the source range."""
    if source_value < source_range[0]:
        return target_range[0] if low_default is None else low_default

    if source_value > source_range[1]:
        return target_range[1] if high_default is None else high_default

    # TODO: replace these functions to eliminate min/max hack below
    target_value = percentage_to_ranged_value(
        target_range,
        ranged_value_to_percentage(source_range, source_value),
    )

    return min(target_range[1], max(target_range[0], target_value))


def domain_entities(
    hass: HomeAssistant,
    domains: Iterable[str],
    device_classes: str | Iterable[str | None] | None = None,
    units_of_measurement: str | Iterable[str | None] | None = None,
) -> set[str]:
    """Get list of matching entities."""

    if isinstance(device_classes, str):
        device_classes = [device_classes]

    if isinstance(units_of_measurement, str):
        units_of_measurement = [units_of_measurement]

    entity_ids = set()
    ent_reg = entity_registry.async_get(hass)

    for state in hass.states.async_all(domains):
        entity = ent_reg.async_get(state.entity_id)
        if entity and entity.hidden:
            continue

        if (
            device_classes
            and state.attributes.get(ATTR_DEVICE_CLASS) not in device_classes
        ):
            continue

        if (
            units_of_measurement
            and state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            not in units_of_measurement
        ):
            continue

        entity_ids.add(state.entity_id)

    return entity_ids


def on_off_entities(
    hass: HomeAssistant,
    excluded_domains: Iterable[str],
) -> set[str]:
    """Get list of entities with on/off state."""

    entity_ids = set()
    ent_reg = entity_registry.async_get(hass)

    for state in hass.states.async_all():
        if state.domain not in excluded_domains and state.state in ON_OFF_STATES:
            entity = ent_reg.async_get(state.entity_id)
            if entity is None or not entity.hidden:
                entity_ids.add(state.entity_id)

    return entity_ids
