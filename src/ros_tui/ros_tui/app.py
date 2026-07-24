# SPDX-License-Identifier: GPL-3.0
# Copyright (c) 2026, João Turra

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import (
    Button,
    Header,
    Footer,
    TabbedContent,
    TabPane,
)

from ros_tui.ros_handler import ROS2Handler
from ros_tui.parameter_tui import ParametersTab
from ros_tui.service_tui import ServicesTab

class RosTuiApp(App[None]):
    TITLE = "ROS2 TUI"

    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("t", "switch_theme", "Switch theme"),
    ]

    CSS = """
    Screen {
        layout: vertical;
        background: #0f172a;
    }

    Header {
        dock: top;
    }

    #views {
        width: 100%;
        height: 1fr;
    }

    #home-tab {
        width: 1fr;
        height: 1fr;
        align: center middle;
    }

    #home-menu {
        width: 24;
        height: auto;
        layout: vertical;
    }

    #home-menu Button {
        width: 100%;
        margin: 1 0;
    }

    #footer {
        dock: bottom;
        align: left middle;
        layout: horizontal;
    }
    """

    ros_node: Node
    ros_executor: SingleThreadedExecutor
    ros_handler: ROS2Handler

    def __init__(self) -> None:
        super().__init__()
        rclpy.init()
        self.ros_node = Node("ros_tui")
        self.ros_executor = SingleThreadedExecutor()
        self.ros_executor.add_node(self.ros_node)
        self.ros_handler = ROS2Handler(self.ros_node, self.ros_executor)

    def __del__(self):
        self.ros_executor.remove_node(self.ros_node)
        self.ros_node.destroy_node()
        rclpy.shutdown()

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True, time_format="%H:%M:%S", icon="🤖")
        yield Footer(id="footer", show_command_palette=False)
        with TabbedContent(id="views"):
            with TabPane(title="Home", id="home-tab"):
                with VerticalScroll(id="home-menu"):
                    yield Button("Parameters", id="parameters")
                    yield Button("Services", id="services")
                    yield Button("Topics", id="topics")
        

    def on_mount(self) -> None:
        self.theme = "nord"
        self.set_interval(0.1, self._spin_ros)

    def action_switch_theme(self) -> None:
        self.theme = "gruvbox" if self.theme == "nord" else "nord"

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "parameters":
            await self.show_tab("parameters-tab", ParametersTab)
        if event.button.id == "services":
            await self.show_tab("services-tab", ServicesTab)
        elif event.button.id.endswith("-tab-close"):
            tab_name = event.button.id[:-len("-close")]
            tab_content = self.query_one("#views", TabbedContent)
            await tab_content.remove_pane(tab_name)

    async def show_tab(self, tab_name: str, tab_class: type[TabPane] = TabPane) -> None:
        tab_content = self.query_one("#views", TabbedContent)
        try:
            tab_content.query_one(f"#{tab_name}")
        except NoMatches:
            await tab_content.add_pane(tab_class(self.ros_handler))

    def _spin_ros(self) -> None:
        if rclpy.ok():
            self.ros_executor.spin_once(timeout_sec=0.0)


def main() -> None:
    RosTuiApp().run()


if __name__ == "__main__":
    main()
