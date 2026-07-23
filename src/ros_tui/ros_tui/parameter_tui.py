# SPDX-License-Identifier: GPL-3.0
# Copyright (c) 2026, João Turra

import ast

from textual import events
from textual.app import ComposeResult
from textual.message import Message
from textual.containers import Container, VerticalScroll
from textual.widgets import (
    Button,
    Checkbox,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
    TabPane,
    TextArea,
)

from ros_tui.ros_handler import ParameterInfo, ROS2Handler


class NodeListItem(ListItem):
    def __init__(self, node_name: str) -> None:
        super().__init__(Label(node_name))
        self.node_name = node_name

class FilledCheckbox(Checkbox):
    FILLED_ICON = "✔"
    EMPTY_ICON = "o"

    def render(self) -> str:
        return self.FILLED_ICON if self.value else self.EMPTY_ICON

class ParameterView(Container):
    DEFAULT_CSS = """
    ParameterView {
        width: 100%;
        height: auto;
        layout: horizontal;
        padding: 0 1;
        margin: 0 0 1 0;
    }

    ParameterView:focus {
        background: $accent 20%;
    }

    .parameter-name {
        width: 40%;
        content-align: left middle;
    }

    .parameter-editor {
        width: 1fr;
    }
    """

    class Submitted(Message):
        def __init__(self, parameter: ParameterInfo, value: object) -> None:
            super().__init__()
            self.parameter = parameter
            self.value = value

    def __init__(self, parameter: ParameterInfo) -> None:
        super().__init__()
        self.parameter = parameter
        self.value = ParametersTab._coerce_parameter_value(parameter, parameter.value)
        self.value_str = ""

    def compose(self) -> ComposeResult:
        yield Label(self.parameter.name, classes="parameter-name")
        yield self._get_editor_widget()

    def _get_editor_widget(self):
        param_id = self.parameter.name.replace(".", "-").replace("/", "-")
        value = self.parameter.value

        if self.parameter.type_name == "bool":
            return FilledCheckbox("", self.value, classes="parameter-editor", id=param_id, compact=True)

        if self.parameter.type_name in {"integer", "double", "string"}:
            self.value_str = str(value)
            return Input(
                value=self.value_str,
                classes="parameter-editor",
                id=param_id,
                compact=True,
            )

        if self.parameter.type_name.endswith("_array") or self.parameter.type_name == "byte_array":
            self.value_str = ", ".join(str(item) for item in value) if value else ""
            return TextArea(self.value_str, classes="parameter-editor", id=param_id, compact=True)

        return Static(
            "unset" if value is None else str(value),
            classes="parameter-editor",
            id=param_id,
        )

    def on_key(self, event: events.Key) -> None:
        if event.key != "enter":
            return

        event.stop()
        self.post_message(self.Submitted(self.parameter, self._current_value()))

    def _current_value(self) -> object:
        editor = self.query_one(".parameter-editor")
        if isinstance(editor, Checkbox):
            return editor.value
        if isinstance(editor, Input):
            return editor.value
        if isinstance(editor, TextArea):
            return editor.text
        return self.parameter.value


class ParametersTab(TabPane):
    DEFAULT_CSS = """
    VerticalScroll {
        width: 1fr;
        height: 1fr;    
    }

    #parameters-tab {
        width: 1fr;
        height: 1fr;
    }

    #parameters-scroll {
        width: 1fr;
        height: 1fr;
        layout: horizontal;
    }

    #parameters-nodes {
        width: 25%;
        height: auto;
        layout: vertical;
        padding: 1;
    }

    #parameters-tab-close,
    #parameters-nodes-refresh {
        width: 100%;
        margin: 0 0 1 0;
    }

    #parameters-nodes-list {
        width: 100%;
        height: 1fr;
    }

    #parameters-values {
        width: 75%;
        height: auto;
        border: ascii #FFFFFF;
        padding: 1;
    }

    #parameters-values-empty {
        width: 100%;
        height: auto;
        content-align: center middle;
        color: $text-muted;
    }

    #parameters-help,
    #parameters-save-status {
        width: 100%;
        height: auto;
        color: $text-muted;
        margin: 0 0 1 0;
    }

    #parameters-values-header {
        width: 100%;
        height: auto;
        layout: horizontal;
        align: center middle;
    }

    #parameters-values-refresh {
        margin: 0 2;
    }
    
    """

    def __init__(self, handler: ROS2Handler, **kwargs) -> None:
        super().__init__(title="Parameters", id="parameters-tab", **kwargs)
        self.ros_handler = handler
        self.selected_node_name: str | None = None

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="parameters-scroll"):
            with Container(id="parameters-nodes"):
                yield Button("Close Params", id="parameters-tab-close", compact=True)
                yield Button("Refresh Nodes", id="parameters-nodes-refresh", compact=True)
                yield ListView(id="parameters-nodes-list")
            with VerticalScroll(id="parameters-values"):
                yield Static("Select a node to inspect its parameters.", id="parameters-values-empty")

    async def on_mount(self) -> None:
        await self.refresh_node_list()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "parameters-nodes-refresh":
            await self.refresh_node_list()

        if event.button.id == "parameters-values-refresh":
            await self.show_parameters(self.selected_node_name)

        if event.button.id == "parameters-values-close":
            values_container = self.query_one("#parameters-values", VerticalScroll)
            await values_container.remove_children()
            await values_container.mount(
                Static("Select a node to inspect its parameters.", id="parameters-values-empty")
            )

    async def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.list_view.id != "parameters-nodes-list":
            return

        if not isinstance(event.item, NodeListItem):
            return

        await self.show_parameters(event.item.node_name)

    async def refresh_node_list(self) -> None:
        nodes = self.ros_handler.list_nodes(include_parameters=False)
        node_list = self.query_one("#parameters-nodes-list", ListView)
        items = [
            NodeListItem(node.full_name)
            for node in sorted(nodes.values(), key=lambda node: node.full_name)
        ]
        await node_list.clear()
        await node_list.extend(items)

    async def show_parameters(self, node_name: str) -> None:
        self.selected_node_name = node_name
        parameters = self.ros_handler.get_parameters(node_name)
        values_container = self.query_one("#parameters-values", VerticalScroll)
        await values_container.remove_children()

        if not parameters:
            await values_container.mount(
                Static(f"No parameters available for {node_name}.", id="parameters-values-empty")
            )
            return

        await values_container.mount(
            Container(
                Label(node_name),
                Button("Refresh Params", id="parameters-values-refresh", compact=True),
                Button("Close", id="parameters-values-close", compact=True),
                id="parameters-values-header",
            )
        )
        await values_container.mount(
            Static("Focus a parameter and press Enter to apply the edited value.", id="parameters-help")
        )
        await values_container.mount(Static("", id="parameters-save-status"))
        for parameter in sorted(parameters.values(), key=lambda param: param.name):
            await values_container.mount(ParameterView(parameter))

    def on_parameter_view_submitted(self, event: ParameterView.Submitted) -> None:
        status = self.query_one("#parameters-save-status", Static)
        if self.selected_node_name is None:
            status.update("No node selected.")
            return

        try:
            value = self._coerce_parameter_value(event.parameter, event.value)
        except ValueError as exc:
            status.update(f"Invalid value for {event.parameter.name}: {exc}")
            return

        success, reason = self.ros_handler.set_parameter(
            self.selected_node_name,
            event.parameter,
            value,
        )
        if success:
            event.parameter.value = value
            status.update(f"Updated {event.parameter.name} = {value}")
            return

        status.update(
            f"Failed to update {event.parameter.name}: "
            f"{reason or 'parameter update rejected'}"
        )

    @staticmethod
    def _coerce_parameter_value(parameter: ParameterInfo, raw_value: object) -> object:
        if parameter.type_name == "bool":
            if isinstance(raw_value, bool):
                return raw_value
            return ParametersTab._parse_bool(raw_value)
        if parameter.type_name == "integer":
            return int(str(raw_value).strip())
        if parameter.type_name == "double":
            return float(str(raw_value).strip())
        if parameter.type_name == "string":
            return "" if raw_value is None else str(raw_value)
        if parameter.type_name == "byte_array":
            return [int(item) for item in ParametersTab._parse_array(raw_value)]
        if parameter.type_name == "bool_array":
            return [ParametersTab._parse_bool(item) for item in ParametersTab._parse_array(raw_value)]
        if parameter.type_name == "integer_array":
            return [int(item) for item in ParametersTab._parse_array(raw_value)]
        if parameter.type_name == "double_array":
            return [float(item) for item in ParametersTab._parse_array(raw_value)]
        if parameter.type_name == "string_array":
            return [str(item) for item in ParametersTab._parse_array(raw_value)]
        return raw_value

    @staticmethod
    def _parse_array(raw_value: object) -> list[object]:
        text = "" if raw_value is None else str(raw_value).strip()
        if not text:
            return []
        if text.startswith("["):
            parsed = ast.literal_eval(text)
            if not isinstance(parsed, list):
                raise ValueError("expected a list")
            return parsed
        return [item.strip() for item in text.split(",")]

    @staticmethod
    def _parse_bool(value: object) -> bool:
        text = str(value).strip().lower()
        if text in {"true", "1", "yes", "on"}:
            return True
        if text in {"false", "0", "no", "off"}:
            return False
        raise ValueError(f"invalid boolean '{value}'")
