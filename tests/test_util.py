import math

from homeassistant.const import UnitOfTemperature

from custom_components.smartify.util import (
    absolute_humidity,
    remove_empty,
    extrapolate_value,
)


def _reference_absolute_humidity(t_c: float, hum: float) -> float:
    """Independent reference using the original math.e ** form."""
    return (
        hum
        * 6.112
        * 2.1674
        * math.e ** ((t_c * 17.67) / (t_c + 243.5))
        / (t_c + 273.15)
    )


def test_remove_empty_deduplicates():
    result = remove_empty(["a", None, "b", "a"])
    assert result == ["a", "b"]


def test_extrapolate_value_midpoint():
    result = extrapolate_value(
        50,
        (0, 100),
        (0, 10),
    )
    assert result == 4.5


def test_absolute_humidity_matches_reference():
    """math.exp() must give the same result as the original math.e ** form."""
    for t_c, hum in [(20.0, 50.0), (0.0, 80.0), (35.0, 95.0), (-10.0, 60.0)]:
        result = absolute_humidity((t_c, UnitOfTemperature.CELSIUS), hum)
        assert math.isclose(result, _reference_absolute_humidity(t_c, hum))


def test_absolute_humidity_zero_humidity_is_zero():
    assert absolute_humidity((25.0, UnitOfTemperature.CELSIUS), 0.0) == 0.0


def test_absolute_humidity_increases_with_humidity():
    low = absolute_humidity((25.0, UnitOfTemperature.CELSIUS), 30.0)
    high = absolute_humidity((25.0, UnitOfTemperature.CELSIUS), 60.0)
    assert high > low
