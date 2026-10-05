# SPDX-License-Identifier: GPL-3.0
# Copyright (c) 2026, João Turra

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from rcl_interfaces.msg import Parameter, ParameterDescriptor, ParameterType, ParameterValue
from rcl_interfaces.srv import (
    DescribeParameters,
    GetParameters,
    ListParameters,
    SetParameters,
)
from rclpy.executors import Executor
from rclpy.node import Node
from rclpy.client import Client as ServiceClient


class CallStatus(Enum):
    SUCCESS = "success"
    UNAVAILABLE = "unavailable"
    TIMEOUT = "timeout"
    ERROR = "error"
    REJECTED = "rejected"


@dataclass(slots=True)
class ServiceInfo:
    name: str
    type: str
    client: ServiceClient | None


@dataclass(slots=True)
class NumericRange:
    from_value: float
    to_value: float
    step: float


@dataclass(slots=True)
class ParameterInfo:
    name: str
    type_id: int
    type_name: str
    value: Any
    read_only: bool = False
    description: str = ""
    additional_constraints: str = ""
    value_range: NumericRange | None = None


@dataclass(slots=True)
class ParameterResult:
    status: CallStatus
    message: str = ""
    parameters: dict[str, ParameterInfo] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status is CallStatus.SUCCESS


@dataclass(slots=True)
class NodeInfo:
    name: str
    namespace: str
    full_name: str
    parameters: dict[str, ParameterInfo] = field(default_factory=dict)


class ROS2Handler:
    """Small wrapper around ROS2 graph and parameter APIs."""

    _PARAMETER_TYPE_NAMES = {
        ParameterType.PARAMETER_NOT_SET: "not_set",
        ParameterType.PARAMETER_BOOL: "bool",
        ParameterType.PARAMETER_INTEGER: "integer",
        ParameterType.PARAMETER_DOUBLE: "double",
        ParameterType.PARAMETER_STRING: "string",
        ParameterType.PARAMETER_BYTE_ARRAY: "byte_array",
        ParameterType.PARAMETER_BOOL_ARRAY: "bool_array",
        ParameterType.PARAMETER_INTEGER_ARRAY: "integer_array",
        ParameterType.PARAMETER_DOUBLE_ARRAY: "double_array",
        ParameterType.PARAMETER_STRING_ARRAY: "string_array",
    }

    def __init__(self, node: Node, executor: Executor) -> None:
        self.node = node
        self.executor = executor
        self.logger = node.get_logger()
        self._list_parameters_clients: dict[str, ServiceClient] = {}
        self._get_parameters_clients: dict[str, ServiceClient] = {}
        self._set_parameters_clients: dict[str, ServiceClient] = {}
        self._describe_parameters_clients: dict[str, ServiceClient] = {}

        self._service_clients: dict[str, ServiceInfo] = {}

    def list_nodes(self, include_parameters: bool = True) -> dict[str, NodeInfo]:
        nodes: dict[str, NodeInfo] = {}

        for name, namespace in self.node.get_node_names_and_namespaces():
            full_name = self._full_node_name(name, namespace)
            self.logger.debug(f"Found node '{full_name}'")
            node_info = NodeInfo(name=name, namespace=namespace, full_name=full_name)
            if include_parameters:
                node_info.parameters = self.get_parameters(full_name).parameters
            nodes[full_name] = node_info

        return nodes

    def list_parameter_names(
        self,
        node_name: str,
        service_timeout_sec: float = 1.0,
    ) -> tuple[CallStatus, list[str], str]:
        client = self._get_or_create_client(
            self._list_parameters_clients,
            ListParameters,
            f"{node_name}/list_parameters",
        )

        request = ListParameters.Request()
        request.depth = 0

        status, response = self._call_service(client, request, service_timeout_sec)
        if status is not CallStatus.SUCCESS:
            return status, [], self._failure_message(status, client.srv_name)

        return status, list(response.result.names), ""

    def get_parameters(
        self,
        node_name: str,
        service_timeout_sec: float = 1.0,
    ) -> ParameterResult:
        status, names, message = self.list_parameter_names(node_name, service_timeout_sec)
        if status is not CallStatus.SUCCESS:
            return ParameterResult(status, message)
        if not names:
            return ParameterResult(CallStatus.SUCCESS)

        client = self._get_or_create_client(
            self._get_parameters_clients,
            GetParameters,
            f"{node_name}/get_parameters",
        )

        request = GetParameters.Request()
        request.names = names

        status, response = self._call_service(client, request, service_timeout_sec)
        if status is not CallStatus.SUCCESS:
            return ParameterResult(status, self._failure_message(status, client.srv_name))

        parameters = {
            name: self._parameter_info(name, value)
            for name, value in zip(names, response.values, strict=False)
        }

        # Descriptors only add metadata, so parameters are still shown if this fails.
        for name, descriptor in self.describe_parameters(
            node_name, names, service_timeout_sec
        ).items():
            if name in parameters:
                self._apply_descriptor(parameters[name], descriptor)

        return ParameterResult(CallStatus.SUCCESS, parameters=parameters)

    def describe_parameters(
        self,
        node_name: str,
        names: list[str],
        service_timeout_sec: float = 1.0,
    ) -> dict[str, ParameterDescriptor]:
        client = self._get_or_create_client(
            self._describe_parameters_clients,
            DescribeParameters,
            f"{node_name}/describe_parameters",
        )

        request = DescribeParameters.Request()
        request.names = names

        status, response = self._call_service(client, request, service_timeout_sec)
        if status is not CallStatus.SUCCESS:
            self.logger.debug(self._failure_message(status, client.srv_name))
            return {}

        return {
            name: descriptor
            for name, descriptor in zip(names, response.descriptors, strict=False)
        }

    def set_parameter(
        self,
        node_name: str,
        parameter: ParameterInfo,
        value: Any,
        service_timeout_sec: float = 1.0,
    ) -> ParameterResult:
        client = self._get_or_create_client(
            self._set_parameters_clients,
            SetParameters,
            f"{node_name}/set_parameters",
        )

        request = SetParameters.Request()
        request.parameters = [
            Parameter(
                name=parameter.name,
                value=self._parameter_value_message(parameter.type_id, value),
            )
        ]

        status, response = self._call_service(client, request, service_timeout_sec)
        if status is not CallStatus.SUCCESS:
            return ParameterResult(status, self._failure_message(status, client.srv_name))

        if not response.results:
            return ParameterResult(CallStatus.ERROR, "empty response from set_parameters")

        result = response.results[0]
        if not result.successful:
            return ParameterResult(
                CallStatus.REJECTED,
                result.reason or "parameter update rejected",
            )

        return ParameterResult(CallStatus.SUCCESS, result.reason)

    def list_services(self):
        services = self.node.get_service_names_and_types()

        self._service_clients = {
            name: ServiceInfo(name=name, type=types[0], client=None)
            for name, types in services
        }

    def get_servives(self):
        return self._service_clients

    def _get_or_create_client(
        self,
        cache: dict[str, Any],
        service_type: type,
        service_name: str,
    ) -> ServiceClient:
        client = cache.get(service_name)
        if client is None:
            client = self.node.create_client(service_type, service_name)
            cache[service_name] = client
        return client

    def _call_service(
        self,
        client: ServiceClient,
        request: Any,
        timeout_sec: float,
    ) -> tuple[CallStatus, Any | None]:
        if not client.wait_for_service(timeout_sec=timeout_sec):
            self.logger.debug(f"Service '{client.srv_name}' is unavailable")
            return CallStatus.UNAVAILABLE, None

        future = client.call_async(request)
        self.executor.spin_until_future_complete(future, timeout_sec=timeout_sec)

        if not future.done():
            self.logger.warning(
                f"Timed out waiting for service '{client.srv_name}' response"
            )
            return CallStatus.TIMEOUT, None

        if future.exception() is not None:
            self.logger.warning(
                f"Service '{client.srv_name}' failed: {future.exception()}"
            )
            return CallStatus.ERROR, None

        return CallStatus.SUCCESS, future.result()

    @staticmethod
    def _failure_message(status: CallStatus, service_name: str) -> str:
        if status is CallStatus.UNAVAILABLE:
            return f"service '{service_name}' is unavailable"
        if status is CallStatus.TIMEOUT:
            return f"timed out waiting for '{service_name}'"
        return f"service '{service_name}' failed"

    def _parameter_info(self, name: str, value: ParameterValue) -> ParameterInfo:
        return ParameterInfo(
            name=name,
            type_id=value.type,
            type_name=self._PARAMETER_TYPE_NAMES.get(value.type, "unknown"),
            value=self._parameter_value(value),
        )

    @staticmethod
    def _apply_descriptor(parameter: ParameterInfo, descriptor: ParameterDescriptor) -> None:
        parameter.read_only = descriptor.read_only
        parameter.description = descriptor.description
        parameter.additional_constraints = descriptor.additional_constraints
        if descriptor.integer_range:
            int_range = descriptor.integer_range[0]
            parameter.value_range = NumericRange(
                int_range.from_value, int_range.to_value, int_range.step
            )
        elif descriptor.floating_point_range:
            float_range = descriptor.floating_point_range[0]
            parameter.value_range = NumericRange(
                float_range.from_value, float_range.to_value, float_range.step
            )

    def _parameter_value(self, value: ParameterValue) -> Any:
        if value.type == ParameterType.PARAMETER_BOOL:
            return value.bool_value
        if value.type == ParameterType.PARAMETER_INTEGER:
            return value.integer_value
        if value.type == ParameterType.PARAMETER_DOUBLE:
            return value.double_value
        if value.type == ParameterType.PARAMETER_STRING:
            return value.string_value
        if value.type == ParameterType.PARAMETER_BYTE_ARRAY:
            # rclpy represents each byte as a length-1 bytes object.
            return [
                item[0] if isinstance(item, bytes) else int(item)
                for item in value.byte_array_value
            ]
        if value.type == ParameterType.PARAMETER_BOOL_ARRAY:
            return list(value.bool_array_value)
        if value.type == ParameterType.PARAMETER_INTEGER_ARRAY:
            return list(value.integer_array_value)
        if value.type == ParameterType.PARAMETER_DOUBLE_ARRAY:
            return list(value.double_array_value)
        if value.type == ParameterType.PARAMETER_STRING_ARRAY:
            return list(value.string_array_value)
        return None

    @staticmethod
    def _parameter_value_message(type_id: int, value: Any) -> ParameterValue:
        message = ParameterValue(type=type_id)
        if type_id == ParameterType.PARAMETER_BOOL:
            message.bool_value = bool(value)
        elif type_id == ParameterType.PARAMETER_INTEGER:
            message.integer_value = int(value)
        elif type_id == ParameterType.PARAMETER_DOUBLE:
            message.double_value = float(value)
        elif type_id == ParameterType.PARAMETER_STRING:
            message.string_value = str(value)
        elif type_id == ParameterType.PARAMETER_BYTE_ARRAY:
            message.byte_array_value = [bytes([int(item)]) for item in value]
        elif type_id == ParameterType.PARAMETER_BOOL_ARRAY:
            message.bool_array_value = list(value)
        elif type_id == ParameterType.PARAMETER_INTEGER_ARRAY:
            message.integer_array_value = list(value)
        elif type_id == ParameterType.PARAMETER_DOUBLE_ARRAY:
            message.double_array_value = list(value)
        elif type_id == ParameterType.PARAMETER_STRING_ARRAY:
            message.string_array_value = list(value)
        return message

    @staticmethod
    def _full_node_name(name: str, namespace: str) -> str:
        namespace = namespace.rstrip("/")
        if not namespace:
            return f"/{name}"
        return f"{namespace}/{name}"


ROS2Interface = ROS2Handler
