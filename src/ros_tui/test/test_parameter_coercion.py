# SPDX-License-Identifier: GPL-3.0
# Copyright (c) 2026, João Turra

import pytest
from rcl_interfaces.msg import ParameterType

from ros_tui.parameter_values import (
    coerce_parameter_value,
    format_parameter_value,
    parse_array,
    parse_bool,
)
from ros_tui.ros_handler import NumericRange, ParameterInfo


def make_parameter(type_name: str, value: object = None, **kwargs) -> ParameterInfo:
    type_id = {
        "bool": ParameterType.PARAMETER_BOOL,
        "integer": ParameterType.PARAMETER_INTEGER,
        "double": ParameterType.PARAMETER_DOUBLE,
        "string": ParameterType.PARAMETER_STRING,
        "byte_array": ParameterType.PARAMETER_BYTE_ARRAY,
        "bool_array": ParameterType.PARAMETER_BOOL_ARRAY,
        "integer_array": ParameterType.PARAMETER_INTEGER_ARRAY,
        "double_array": ParameterType.PARAMETER_DOUBLE_ARRAY,
        "string_array": ParameterType.PARAMETER_STRING_ARRAY,
    }[type_name]
    return ParameterInfo("param", type_id, type_name, value, **kwargs)


@pytest.mark.parametrize(
    ("type_name", "raw", "expected"),
    [
        ("bool", True, True),
        ("bool", "off", False),
        ("integer", " 42 ", 42),
        ("double", "1.50", 1.5),
        ("string", "hello", "hello"),
        ("byte_array", "1, 255", [1, 255]),
        ("bool_array", "true, no", [True, False]),
        ("bool_array", "[True, False]", [True, False]),
        ("integer_array", "[1, 2, 3]", [1, 2, 3]),
        ("integer_array", "", []),
        ("double_array", "1, 2.5", [1.0, 2.5]),
        ("string_array", "a, b", ["a", "b"]),
        ("string_array", "[a, b]", ["a", "b"]),
        ("string_array", "['a, b', 'c']", ["a, b", "c"]),
    ],
)
def test_coerce_valid(type_name: str, raw: object, expected: object) -> None:
    assert coerce_parameter_value(make_parameter(type_name), raw) == expected


@pytest.mark.parametrize(
    ("type_name", "raw"),
    [
        ("bool", "maybe"),
        ("integer", "1.5"),
        ("integer", str(2**63)),
        ("double", "abc"),
        ("byte_array", "256"),
        ("integer_array", "[1.5, 2]"),
        ("integer_array", "[1, 2"),
        ("integer_array", "[True]"),
        ("double_array", "1, x"),
    ],
)
def test_coerce_invalid_raises_value_error(type_name: str, raw: object) -> None:
    with pytest.raises(ValueError):
        coerce_parameter_value(make_parameter(type_name), raw)


def test_integer_range() -> None:
    parameter = make_parameter("integer", value_range=NumericRange(0, 10, 2))
    assert coerce_parameter_value(parameter, "4") == 4
    assert coerce_parameter_value(parameter, "10") == 10
    with pytest.raises(ValueError):
        coerce_parameter_value(parameter, "3")
    with pytest.raises(ValueError):
        coerce_parameter_value(parameter, "12")


def test_float_range_applies_to_array_items() -> None:
    parameter = make_parameter("double_array", value_range=NumericRange(0.0, 1.0, 0.1))
    assert coerce_parameter_value(parameter, "0.3, 1.0") == [0.3, 1.0]
    with pytest.raises(ValueError):
        coerce_parameter_value(parameter, "0.35")


def test_format_round_trips() -> None:
    for type_name, value in [
        ("integer_array", [1, 2]),
        ("double", 0.165),
        ("string_array", ["a, b", " c"]),
        ("bool_array", [True, False]),
    ]:
        parameter = make_parameter(type_name, value)
        text = format_parameter_value(parameter, value)
        assert coerce_parameter_value(parameter, text) == value


def test_parse_array_rejects_non_list_literal() -> None:
    with pytest.raises(ValueError):
        parse_array("[1, 2")


def test_parse_bool_accepts_python_bools() -> None:
    assert parse_bool(True) is True
    assert parse_bool(False) is False
