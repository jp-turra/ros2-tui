# ROS TUI

A terminal user interface for inspecting a ROS 2 graph using Python, `rclpy`, and [Textual](https://textual.textualize.io/).

This project is still in its early stages. At the moment, the only implemented feature is the **Parameters** tab. The application lists all visible ROS 2 nodes, allows selecting a node, and displays its available parameters using an appropriate editor for each basic parameter type.

## Current Features

- Starts a ROS 2 node named `/ros_tui`.
- Keeps the ROS executor running while the TUI is active.
- Lists ROS 2 nodes discovered in the graph.
- Retrieves parameters through the standard ROS 2 services:
  - `/<node>/list_parameters`
  - `/<node>/get_parameters`
- Updates parameters through the standard ROS 2 services:
  - `/<node>/set_parameters`
- Displays boolean parameters as checkboxes.
- Displays `integer`, `double`, and `string` parameters as text input fields.
- Displays array parameters as text areas with comma-separated values.
- Switches between the `nord` and `gruvbox` themes using the `t` key.

The **Services** and **Topics** buttons are already present on the main screen, but their corresponding views have not yet been implemented.

## Running the Application

Inside a configured ROS 2 workspace:

```bash
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
pip install -r requirements.txt
colcon build
source install/setup.bash
ros2 run ros_tui ros_tui
```

It can also be run directly during development, provided the ROS 2 environment has already been sourced:

```bash
python3 -m venv .venv --system-site-packages
source .venv/bin/activate
python src/ros_tui/ros_tui/app.py
```

## Reference JSON Format for Parameters

The original README described a JSON format intended to represent node parameters. While not currently implemented, it can serve as the basis for a future import/export feature.

```json
{
    "/controller": {
        "parameters": {
            "use_sim_time": {
                "type": "bool",
                "value": false
            },
            "wheel_radius": {
                "type": "double",
                "value": 0.165
            }
        }
    },
    "/camera": {
        "parameters": {
            "fps": {
                "type": "integer",
                "value": 30
            }
        }
    }
}
```

## Roadmap

- Improve user interface for editing parameters.
- Validate and convert edited values according to the original ROS 2 parameter type.
- Provide visual feedback for successful updates, failures, and timeouts when changing parameters.
- Implement a **Services** view:
  - list available services;
  - display each service type;
  - allow users to compose and send service requests.
- Implement a **Topics** view:
  - list available topics;
  - display topic types along with publishers and subscribers;
  - inspect recently received messages;
  - manually publish messages to selected topics.
- Implement a **Actions** sender view:
  - list available actions;
  - display each action type;
  - allow users to compose and send action requests.
- Improve installation documentation for different ROS 2 distributions.
- Add unit tests for `ROS2Handler` using mocked ROS clients.
- Complete the remaining metadata in `package.xml` and `setup.py`, including the project description, license, and maintainer information.