# SPDX-License-Identifier: GPL-3.0
# Copyright (c) 2026, João Turra

from dataclasses import dataclass, field
from typing import Any

from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue
from rcl_interfaces.srv import GetParameters, ListParameters, SetParameters
from rclpy.executors import Executor
from rclpy.node import Node
from rclpy.client import Client as ServiceClient


@dataclass(slots=True)
class ParameterInfo:
    name: str
    type_id: int
    type_name: str
    value: Any


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

        self.node.declare_parameter(
            name="param_int",
            value=0
        )
        self.node.declare_parameter(
            name="param_double",
            value=0.0
        )
        self.node.declare_parameter(
            name="param_string",
            value=""
        )

    def list_nodes(self, include_parameters: bool = True) -> dict[str, NodeInfo]:
        nodes: dict[str, NodeInfo] = {}

        for name, namespace in self.node.get_node_names_and_namespaces():
            full_name = self._full_node_name(name, namespace)
            self.logger.debug(f"Found node '{full_name}'")
            node_info = NodeInfo(name=name, namespace=namespace, full_name=full_name)
            if include_parameters:
                node_info.parameters = self.get_parameters(full_name)
            nodes[full_name] = node_info

        return nodes

    def list_parameter_names(
        self,
        node_name: str,
        service_timeout_sec: float = 1.0,
    ) -> list[str]:
        client: ServiceClient = self._get_or_create_client(
            self._list_parameters_clients,
            ListParameters,
            f"{node_name}/list_parameters",
        )

        if not client.wait_for_service(timeout_sec=service_timeout_sec):
            self.logger.debug(
                f"Service unavailable for list_parameters on node '{node_name}'"
            )
            return []

        request = ListParameters.Request()
        request.depth = 0

        response: ListParameters.Response = self._call_service(client, request, service_timeout_sec)
        if response is None:
            return []

        return list(response.result.names)

    def get_parameters(
        self,
        node_name: str,
        service_timeout_sec: float = 1.0,
    ) -> dict[str, ParameterInfo]:
        names = self.list_parameter_names(node_name, service_timeout_sec)
        if not names:
            return {}

        client = self._get_or_create_client(
            self._get_parameters_clients,
            GetParameters,
            f"{node_name}/get_parameters",
        )

        if not client.wait_for_service(timeout_sec=service_timeout_sec):
            self.logger.debug(
                f"Service unavailable for get_parameters on node '{node_name}'"
            )
            return {}

        request = GetParameters.Request()
        request.names = names

        response: GetParameters.Response = self._call_service(client, request, service_timeout_sec)
        if response is None:
            return {}

        return {
            name: self._parameter_info(name, value)
            for name, value in zip(names, response.values, strict=False)
        }

    def set_parameter(
        self,
        node_name: str,
        parameter: ParameterInfo,
        value: Any,
        service_timeout_sec: float = 1.0,
    ) -> tuple[bool, str]:
        client = self._get_or_create_client(
            self._set_parameters_clients,
            SetParameters,
            f"{node_name}/set_parameters",
        )

        if not client.wait_for_service(timeout_sec=service_timeout_sec):
            return False, f"Service unavailable for set_parameters on node '{node_name}'"

        request = SetParameters.Request()
        request.parameters = [
            Parameter(name=parameter.name, value=self._parameter_value_message(parameter.type_id, value))
        ]

        response: SetParameters.Response = self._call_service(client, request, service_timeout_sec)
        if response is None or not response.results:
            return False, f"Failed to set parameter '{parameter.name}' on node '{node_name}'"

        result = response.results[0]
        return result.successful, result.reason

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
    ) -> Any | None:
        future = client.call_async(request)
        self.executor.spin_until_future_complete(future, timeout_sec=timeout_sec)

        if not future.done():
            self.logger.warning(
                f"Timed out waiting for service '{client.srv_name}' response"
            )
            return None

        if future.exception() is not None:
            self.logger.warning(
                f"Service '{client.srv_name}' failed: {future.exception()}"
            )
            return None

        return future.result()

    def _parameter_info(self, name: str, value: ParameterValue) -> ParameterInfo:
        return ParameterInfo(
            name=name,
            type_id=value.type,
            type_name=self._PARAMETER_TYPE_NAMES.get(value.type, "unknown"),
            value=self._parameter_value(value),
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
            return list(value.byte_array_value)
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
            message.byte_array_value = list(value)
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
