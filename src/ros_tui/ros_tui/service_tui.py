import re

from textual.containers import VerticalScroll, Container, Vertical
from textual.app import ComposeResult
from textual.widgets import (
    Button,
    Select,
    Static,
    TabPane
)

from ros_tui.ros_handler import ROS2Handler

SERVICES_TAB_ID: str = "services-tab"
SERVICES_LAYOUT_ID: str = f"{SERVICES_TAB_ID}-layout"
SERVICE_LIST_ID: str = f"{SERVICES_TAB_ID}-list"
CLOSE_BTN_ID: str = f"{SERVICES_TAB_ID}-close"
REFRESH_BTN_ID: str = f"{SERVICES_TAB_ID}-refresh"
HEADER_ID: str = f"{SERVICES_TAB_ID}-header"
BODY_ID: str = f"{SERVICES_TAB_ID}-body"

class ServicesTab(TabPane):
    DEFAULT_CSS = """
Button {
    width: 100%;
    margin: 0 0 1 0;
}

VerticalScroll {
    width: 1fr;
    height: 1fr;
    margin: 0 1;
}

#services-header {
    width: 100%;
    height: auto;
    layout: vertical;
    border: ascii #0000FF;
    padding: 1;
}

#services-body {
    width: 100%;
    height: auto;
    border: ascii #FFFFFF;
    padding: 1;
    align: left top;
}
"""

    def __init__(self, ros_handler: ROS2Handler) -> None:
        super().__init__(id=SERVICES_TAB_ID, title="Services")
        self.handler = ros_handler

    def compose(self) -> ComposeResult:
        with VerticalScroll():
            with Vertical(id=HEADER_ID):
                yield Button("Refresh Services", id=REFRESH_BTN_ID, compact=True)
                yield Button("Close Services", id=CLOSE_BTN_ID, compact=True)
                yield Select(id=SERVICE_LIST_ID, compact=True, allow_blank=True, options=[], prompt="Select a service to call.")
            with Container(id=BODY_ID):
                yield Static("Body of services tab")
            

    async def on_mount(self) -> None:
        self.list_services()
        await self.set_service_list_view()

    def list_services(self):
        self.handler.list_services()

    async def set_service_list_view(self):
        services = self.handler.get_servives()
        dropdown = self.query_one(f"#{SERVICE_LIST_ID}", Select)
        dropdown.clear()

        options = []
        if len(services) > 0:
            options = [(service_name, service_name) for service_name in services]
        
        dropdown.set_options(options)
