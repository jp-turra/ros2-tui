# SPDX-License-Identifier: GPL-3.0
# Copyright (c) 2026, João Turra

from typing import Any
from unittest.mock import MagicMock

import pytest
from rcl_interfaces.msg import (
    IntegerRange,
    ParameterDescriptor,
    ParameterType,
    ParameterValue,
    SetParametersResult,
)
from rcl_interfaces.srv import DescribeParameters, GetParameters, ListParameters, SetParameters

from ros_tui.ros_handler import CallStatus, NumericRange, ParameterInfo, ROS2Handler

NODE = "/talker"


class FakeFuture:
    def __init__(self, response: Any, done: bool = True) -> None:
        self._response = response
        self._done = done

    def done(self) -> bool:
        return self._done

    def exception(self) -> Exception | None:
        return None

    def result(self) -> Any:
        return self._response


class FakeClient:
    def __init__(self, srv_name: str, ros: "FakeRos") -> None:
        self.srv_name = srv_name
        self.ros = ros
        self.requests: list[Any] = []

    def wait_for_service(self, timeout_sec: float) -> bool:
        return self.srv_name not in self.ros.unavailable

    def call_async(self, request: Any) -> FakeFuture:
        self.requests.append(request)
        return FakeFuture(
            self.ros.responses.get(self.srv_name),
            done=self.srv_name not in self.ros.timeouts,
        )


class FakeRos:
    """Fake node whose service clients answer from a response table."""

    def __init__(self) -> None:
        self.responses: dict[str, Any] = {}
        self.unavailable: set[str] = set()
        self.timeouts: set[str] = set()
        self.clients: dict[str, FakeClient] = {}
        self.node = MagicMock()
        self.node.create_client.side_effect = self._create_client

    def _create_client(self, service_type: type, service_name: str) -> FakeClient:
        client = FakeClient(service_name, self)
        self.clients[service_name] = client
        return client


@pytest.fixture
def ros() -> FakeRos:
    fake = FakeRos()

    list_response = ListParameters.Response()
    list_response.result.names = ["rate", "name"]
    fake.responses[f"{NODE}/list_parameters"] = list_response

    get_response = GetParameters.Response()
    get_response.values = [
        ParameterValue(type=ParameterType.PARAMETER_INTEGER, integer_value=10),
        ParameterValue(type=ParameterType.PARAMETER_STRING, string_value="chatter"),
    ]
    fake.responses[f"{NODE}/get_parameters"] = get_response

    describe_response = DescribeParameters.Response()
    describe_response.descriptors = [
        ParameterDescriptor(
            name="rate",
            description="Publish rate",
            integer_range=[IntegerRange(from_value=1, to_value=100, step=1)],
        ),
        ParameterDescriptor(name="name", read_only=True),
    ]
    fake.responses[f"{NODE}/describe_parameters"] = describe_response
    return fake


@pytest.fixture
def handler(ros: FakeRos) -> ROS2Handler:
    return ROS2Handler(ros.node, MagicMock())


def test_get_parameters_includes_descriptors(handler: ROS2Handler) -> None:
    result = handler.get_parameters(NODE)

    assert result.status is CallStatus.SUCCESS
    rate = result.parameters["rate"]
    assert rate.type_name == "integer"
    assert rate.value == 10
    assert rate.description == "Publish rate"
    assert rate.value_range == NumericRange(1, 100, 1)
    assert result.parameters["name"].read_only


def test_get_parameters_without_describe_service(ros: FakeRos, handler: ROS2Handler) -> None:
    ros.unavailable.add(f"{NODE}/describe_parameters")

    result = handler.get_parameters(NODE)

    assert result.ok
    assert result.parameters["rate"].value_range is None


def test_get_parameters_reports_unavailable(ros: FakeRos, handler: ROS2Handler) -> None:
    ros.unavailable.add(f"{NODE}/list_parameters")

    result = handler.get_parameters(NODE)

    assert result.status is CallStatus.UNAVAILABLE
    assert "unavailable" in result.message
    assert result.parameters == {}


def test_get_parameters_reports_timeout(ros: FakeRos, handler: ROS2Handler) -> None:
    ros.timeouts.add(f"{NODE}/get_parameters")

    result = handler.get_parameters(NODE)

    assert result.status is CallStatus.TIMEOUT


def _rate_parameter() -> ParameterInfo:
    return ParameterInfo("rate", ParameterType.PARAMETER_INTEGER, "integer", 10)


def test_set_parameter_success(ros: FakeRos, handler: ROS2Handler) -> None:
    response = SetParameters.Response()
    response.results = [SetParametersResult(successful=True)]
    ros.responses[f"{NODE}/set_parameters"] = response

    result = handler.set_parameter(NODE, _rate_parameter(), 20)

    assert result.ok
    request = ros.clients[f"{NODE}/set_parameters"].requests[0]
    assert request.parameters[0].name == "rate"
    assert request.parameters[0].value.integer_value == 20


def test_set_parameter_rejected(ros: FakeRos, handler: ROS2Handler) -> None:
    response = SetParameters.Response()
    response.results = [SetParametersResult(successful=False, reason="out of range")]
    ros.responses[f"{NODE}/set_parameters"] = response

    result = handler.set_parameter(NODE, _rate_parameter(), 1000)

    assert result.status is CallStatus.REJECTED
    assert result.message == "out of range"


def test_set_parameter_timeout(ros: FakeRos, handler: ROS2Handler) -> None:
    ros.timeouts.add(f"{NODE}/set_parameters")

    result = handler.set_parameter(NODE, _rate_parameter(), 20)

    assert result.status is CallStatus.TIMEOUT


def test_byte_array_round_trip(handler: ROS2Handler) -> None:
    message = ROS2Handler._parameter_value_message(ParameterType.PARAMETER_BYTE_ARRAY, [1, 255])
    assert list(message.byte_array_value) == [b"\x01", b"\xff"]
    assert handler._parameter_value(message) == [1, 255]


@pytest.mark.parametrize(
    ("type_id", "value"),
    [
        (ParameterType.PARAMETER_BOOL, True),
        (ParameterType.PARAMETER_DOUBLE, 0.165),
        (ParameterType.PARAMETER_STRING_ARRAY, ["a", "b"]),
        (ParameterType.PARAMETER_DOUBLE_ARRAY, [1.0, 2.5]),
    ],
)
def test_value_message_round_trip(handler: ROS2Handler, type_id: int, value: object) -> None:
    message = ROS2Handler._parameter_value_message(type_id, value)
    assert handler._parameter_value(message) == value
