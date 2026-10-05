# SPDX-License-Identifier: GPL-3.0
# Copyright (c) 2026, João Turra

from textual.app import ComposeResult
from textual.message import Message
from textual.containers import Container, VerticalScroll
from textual.widget import Widget
from textual.widgets import (
    Button,
    Checkbox,
    Collapsible,
    Input,
    Label,
    ListItem,
    ListView,
    Static,
    TabPane,
)

from ros_tui.parameter_values import coerce_parameter_value, format_parameter_value
from ros_tui.ros_handler import CallStatus, ParameterInfo, ROS2Handler

TEXT_EDITOR_TYPES = {
    "integer",
    "double",
    "string",
    "byte_array",
    "bool_array",
    "integer_array",
    "double_array",
    "string_array",
}


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
        border-left: blank;
    }

    ParameterView:focus-within {
        background: $accent 20%;
    }

    ParameterView.-dirty {
        border-left: thick $warning;
    }

    ParameterView.-ok {
        border-left: thick $success;
    }

    ParameterView.-error {
        border-left: thick $error;
    }

    .parameter-name {
        width: 40%;
        content-align: left middle;
    }

    .parameter-type {
        width: 14;
        color: $text-muted;
        content-align: left middle;
    }

    .parameter-editor {
        width: 1fr;
    }
    """

    STATE_CLASSES = ("-dirty", "-ok", "-error")

    class Submitted(Message):
        def __init__(self, view: "ParameterView", value: object) -> None:
            super().__init__()
            self.view = view
            self.value = value

    def __init__(self, parameter: ParameterInfo) -> None:
        super().__init__()
        self.parameter = parameter

    def compose(self) -> ComposeResult:
        yield Label(self.parameter.name, classes="parameter-name")
        yield Label(self.parameter.type_name, classes="parameter-type")
        yield self._create_editor()

    def on_mount(self) -> None:
        tooltip = self._tooltip_text()
        if tooltip:
            self.tooltip = tooltip

    def _create_editor(self) -> Widget:
        parameter = self.parameter

        if parameter.type_name == "bool":
            return FilledCheckbox(
                "",
                bool(parameter.value),
                classes="parameter-editor",
                compact=True,
                disabled=parameter.read_only,
            )

        if parameter.type_name in TEXT_EDITOR_TYPES:
            return Input(
                value=format_parameter_value(parameter, parameter.value),
                classes="parameter-editor",
                compact=True,
                disabled=parameter.read_only,
            )

        return Static(
            "unset" if parameter.value is None else str(parameter.value),
            classes="parameter-editor",
        )

    def _tooltip_text(self) -> str:
        parameter = self.parameter
        lines = []
        if parameter.description:
            lines.append(parameter.description)
        if parameter.value_range is not None:
            value_range = parameter.value_range
            text = f"Range: [{value_range.from_value}, {value_range.to_value}]"
            if value_range.step:
                text += f", step {value_range.step}"
            lines.append(text)
        if parameter.additional_constraints:
            lines.append(f"Constraints: {parameter.additional_constraints}")
        if parameter.read_only:
            lines.append("Read-only")
        return "\n".join(lines)

    def on_input_changed(self, event: Input.Changed) -> None:
        event.stop()
        current = format_parameter_value(self.parameter, self.parameter.value)
        self.mark("-dirty" if event.value != current else None)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self.post_message(self.Submitted(self, event.value))

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        event.stop()
        self.post_message(self.Submitted(self, event.value))

    def mark(self, state: str | None) -> None:
        """Show the edit state: -dirty, -ok, -error, or None to clear it."""
        self.remove_class(*self.STATE_CLASSES)
        if state is not None:
            self.add_class(state)

    def reset_editor(self) -> None:
        """Show the parameter's last known value without submitting it again."""
        editor = self.query_one(".parameter-editor")
        if isinstance(editor, Checkbox):
            with editor.prevent(Checkbox.Changed):
                editor.value = bool(self.parameter.value)
        elif isinstance(editor, Input):
            with editor.prevent(Input.Changed):
                editor.value = format_parameter_value(self.parameter, self.parameter.value)


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

    #parameters-help {
        width: 100%;
        height: auto;
        color: $text-muted;
        margin: 0 0 1 0;
    }

    #parameters-filter {
        width: 100%;
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

        if event.button.id == "parameters-values-refresh" and self.selected_node_name is not None:
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
        result = self.ros_handler.get_parameters(node_name)
        values_container = self.query_one("#parameters-values", VerticalScroll)
        await values_container.remove_children()

        if not result.ok:
            message = f"Could not load parameters for {node_name}: {result.message}"
            await values_container.mount(Static(message, id="parameters-values-empty"))
            self.app.notify(message, title="Parameters", severity="error")
            return

        if not result.parameters:
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
            Static(
                "Edit a value and press Enter to apply it. Checkboxes apply immediately.",
                id="parameters-help",
            )
        )
        await values_container.mount(
            Input(placeholder="Filter parameters", id="parameters-filter", compact=True)
        )
        await values_container.mount_all(self._parameter_widgets(result.parameters))

    @staticmethod
    def _parameter_widgets(parameters: dict[str, ParameterInfo]) -> list[Widget]:
        """Build parameter views, grouping dotted names under their first segment."""
        ungrouped: list[Widget] = []
        groups: dict[str, list[ParameterView]] = {}
        for parameter in sorted(parameters.values(), key=lambda param: param.name):
            prefix, separator, _ = parameter.name.partition(".")
            if separator:
                groups.setdefault(prefix, []).append(ParameterView(parameter))
            else:
                ungrouped.append(ParameterView(parameter))

        return ungrouped + [
            Collapsible(*views, title=prefix, collapsed=False, classes="parameter-group")
            for prefix, views in groups.items()
        ]

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id != "parameters-filter":
            return

        query = event.value.strip().lower()
        for view in self.query(ParameterView):
            view.display = query in view.parameter.name.lower()
        for group in self.query(".parameter-group").results(Collapsible):
            group.display = any(view.display for view in group.query(ParameterView))

    def on_parameter_view_submitted(self, event: ParameterView.Submitted) -> None:
        view = event.view
        parameter = view.parameter
        if self.selected_node_name is None:
            self.app.notify("No node selected.", severity="warning")
            return

        if parameter.read_only:
            view.reset_editor()
            view.mark("-error")
            self.app.notify(f"{parameter.name} is read-only.", severity="warning")
            return

        try:
            value = coerce_parameter_value(parameter, event.value)
        except ValueError as exc:
            view.mark("-error")
            self.app.notify(
                f"Invalid value for {parameter.name}: {exc}",
                title=self.selected_node_name,
                severity="error",
            )
            return

        result = self.ros_handler.set_parameter(self.selected_node_name, parameter, value)
        if result.ok:
            parameter.value = value
            view.reset_editor()
            view.mark("-ok")
            self.app.notify(
                f"Updated {parameter.name} = {format_parameter_value(parameter, value)}",
                title=self.selected_node_name,
            )
            return

        view.reset_editor()
        view.mark("-error")
        self.app.notify(
            f"Failed to update {parameter.name}: {result.message}",
            title=self.selected_node_name,
            severity="warning" if result.status is CallStatus.REJECTED else "error",
        )
