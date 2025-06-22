# Conductor MCP

Conductor MCP is a Python-based server that uses the Model Context Protocol (MCP) to help you define, track, and execute complex objectives. It allows you to break down a large goal into smaller, manageable tasks with specified dependencies, ensuring that they are executed in the correct order.

This tool is designed to be used with an MCP-compatible client or an LLM that can interact with MCP tools. It provides a simple yet powerful way to manage workflows and evaluate the feasibility of your plans.

## Purpose

The primary purpose of Conductor MCP is to provide a framework for:

- **Objective Tracking**: Defining high-level objectives.
- **Dependency Management**: Creating a graph of tasks that depend on one another.
- **Intelligent Task Execution**: Determining the next available task based on completed dependencies.
- **Feasibility Analysis**: Checking if an objective is achievable by verifying that all task dependencies are defined within the system.

## Multi-Session Support

This server is designed to be multi-tenant. It uses the `session_id` (or `client_id` as a fallback) provided by the client to create a unique, isolated workspace for each user session.

All objectives, tasks, and their states are automatically namespaced. This means that multiple users or applications can interact with the server simultaneously without their data interfering with one another, ensuring a secure and predictable experience.

## Installation

To get started with Conductor MCP, follow these installation instructions.

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/Voidious/conductor-mcp.git
    cd conductor-mcp
    ```

2.  **Create and Activate a Virtual Environment**:

    For macOS/Linux:
    ```bash
    python3 -m venv .venv
    source .venv/bin/activate
    ```

    For Windows:
    ```bash
    python -m venv .venv
    .\.venv\Scripts\activate
    ```

3.  **Install Dependencies**:
    Install the required Python packages using the `requirements.txt` file.
    ```bash
    pip install -r requirements.txt
    ```

## Usage

Once the installation is complete, you can run the server and start interacting with its tools.

1.  **Run the Server**:
    From the root directory of the project, run the following command:
    ```bash
    python main.py
    ```
    The server will start and be ready to accept requests from an MCP client.

2.  **Available Tools**:
    You can interact with the server using the following tools:

    - `add_objective(id: str, description: str)`: Creates a new objective to track.
    - `add_task(id: str, description: str, objective_id: str, dependencies: List[str] = [])`: Adds a new task to an existing objective. You can specify a list of task IDs that it depends on.
    - `add_dependency(task_id: str, dependency_id: str)`: Adds a new dependency to a task that has already been created.
    - `get_next_task(objective_id: str)`: Finds the next step for an objective. It first checks for any undefined task dependencies and, if any are found, instructs the user to define the missing task. Only when all tasks are defined does it return the next unblocked task to be executed. This approach front-loads the work of resolving unknown dependencies and ambiguity.
    - `complete_task(task_id: str)`: Marks a specific task as completed.
    - `evaluate_feasibility(objective_id: str)`: Checks if all dependencies for all tasks in an objective are recognized by the system.

### Example Workflow

Here is a simple example of how to use the tools to manage an objective:

1.  **Add an objective**: `add_objective(id="learn_mcp", description="Learn the Model Context Protocol")`
2.  **Add tasks**:
    - `add_task(id="read_docs", description="Read the FastMCP documentation", objective_id="learn_mcp")`
    - `add_task(id="build_server", description="Build a simple MCP server", objective_id="learn_mcp", dependencies=["read_docs"])`
    - `add_task(id="test_server", description="Test the server with a client", objective_id="learn_mcp", dependencies=["build_server"])`
3.  **Execute the plan**:
    - `get_next_task(objective_id="learn_mcp")` -> Returns `read_docs`.
    - `complete_task(task_id="read_docs")`
    - `get_next_task(objective_id="learn_mcp")` -> Returns `build_server`.
    - `complete_task(task_id="build_server")`
    - `get_next_task(objective_id="learn_mcp")` -> Returns `test_server`.
    - `complete_task(task_id="test_server")`
4.  **Confirm completion**: `get_next_task(objective_id="learn_mcp")` -> Returns a message that no tasks are available.

## Running Tests

This project includes a test suite to verify its functionality. The tests use `pytest` and run in-memory without needing to keep the server running in a separate process.

To run the tests, execute the following command from the root directory:

```bash
pytest
``` 
