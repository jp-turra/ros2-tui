# SPDX-License-Identifier: GPL-3.0
# Copyright (c) 2026, João Turra

"""Conversion between editor text and typed ROS 2 parameter values."""

import ast
import math

from ros_tui.ros_handler import NumericRange, ParameterInfo

INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1

TRUE_STRINGS = {"true", "1", "yes", "on"}
FALSE_STRINGS = {"false", "0", "no", "off"}


def coerce_parameter_value(parameter: ParameterInfo, raw_value: object) -> object:
    """Convert raw editor input to the parameter's type, raising ValueError if invalid."""
    type_name = parameter.type_name
    value: object
    if type_name == "bool":
        value = raw_value if isinstance(raw_value, bool) else parse_bool(raw_value)
    elif type_name == "integer":
        value = parse_int(raw_value)
    elif type_name == "double":
        value = parse_float(raw_value)
    elif type_name == "string":
        value = "" if raw_value is None else str(raw_value)
    elif type_name == "byte_array":
        value = [parse_byte(item) for item in parse_array(raw_value)]
    elif type_name == "bool_array":
        value = [parse_bool(item) for item in parse_array(raw_value)]
    elif type_name == "integer_array":
        value = [parse_int(item) for item in parse_array(raw_value)]
    elif type_name == "double_array":
        value = [parse_float(item) for item in parse_array(raw_value)]
    elif type_name == "string_array":
        value = [str(item) for item in parse_array(raw_value)]
    else:
        return raw_value

    if parameter.value_range is not None:
        check_range(parameter.value_range, value)
    return value


def format_parameter_value(parameter: ParameterInfo, value: object) -> str:
    """Render a typed value as editor text that coerce_parameter_value can parse back."""
    if value is None:
        return ""
    if parameter.type_name.endswith("_array") and isinstance(value, list):
        if parameter.type_name == "string_array" and any(
            "," in item or item != item.strip() for item in value
        ):
            return repr(value)
        return ", ".join(str(item) for item in value)
    return str(value)


def parse_array(raw_value: object) -> list[object]:
    text = "" if raw_value is None else str(raw_value).strip()
    if not text:
        return []
    if text.startswith("["):
        if not text.endswith("]"):
            raise ValueError("unterminated list, expected ']'")
        try:
            parsed = ast.literal_eval(text)
        except (ValueError, SyntaxError):
            # Not a Python literal, e.g. unquoted strings such as [a, b].
            inner = text[1:-1].strip()
            return [item.strip() for item in inner.split(",")] if inner else []
        if not isinstance(parsed, (list, tuple)):
            raise ValueError("expected a list")
        return list(parsed)
    return [item.strip() for item in text.split(",")]


def parse_bool(value: object) -> bool:
    text = str(value).strip().lower()
    if text in TRUE_STRINGS:
        return True
    if text in FALSE_STRINGS:
        return False
    raise ValueError(f"invalid boolean '{value}'")


def parse_int(value: object) -> int:
    if isinstance(value, bool):
        raise ValueError(f"expected an integer, got '{value}'")
    if isinstance(value, int):
        result = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ValueError(f"expected an integer, got '{value}'")
        result = int(value)
    else:
        try:
            result = int(str(value).strip())
        except ValueError:
            raise ValueError(f"expected an integer, got '{value}'") from None

    if not INT64_MIN <= result <= INT64_MAX:
        raise ValueError(f"{result} is outside the int64 range")
    return result


def parse_float(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError(f"expected a number, got '{value}'")
    try:
        return float(str(value).strip())
    except ValueError:
        raise ValueError(f"expected a number, got '{value}'") from None


def parse_byte(value: object) -> int:
    result = parse_int(value)
    if not 0 <= result <= 255:
        raise ValueError(f"{result} is not a byte (0-255)")
    return result


def check_range(value_range: NumericRange, value: object) -> None:
    items = value if isinstance(value, list) else [value]
    for item in items:
        if isinstance(item, bool) or not isinstance(item, (int, float)):
            continue
        _check_in_range(value_range, item)


def _check_in_range(value_range: NumericRange, item: float) -> None:
    low, high, step = value_range.from_value, value_range.to_value, value_range.step
    if not low <= item <= high:
        raise ValueError(f"{item} is outside the range [{low}, {high}]")
    if not step or item == high:
        return

    if isinstance(item, int) and isinstance(low, int) and isinstance(step, int):
        on_step = (item - low) % step == 0
    else:
        steps = (item - low) / step
        on_step = math.isclose(steps, round(steps), abs_tol=1e-9)
    if not on_step:
        raise ValueError(f"{item} is not on a step of {step} from {low}")
