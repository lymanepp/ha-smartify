from custom_components.smartify.util import (
    remove_empty,
    extrapolate_value,
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
