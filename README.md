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

This server is designed to be multi-tenant. It automatically creates a unique, isolated workspace for every client connection.

All objectives, tasks, and their states are automatically namespaced based on the connection. This means that multiple users or applications can interact with the server simultaneously without their data interfering with one another, ensuring a secure and predictable experience without any required client-side configuration.

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

    - `define_objective(id: str, description: str)`: Defines a new objective to be achieved.
    - `define_task(id: str, description: str, objective_id: str, prerequisites: List[str] = [])`: Defines a new task as a part of achieving an objective. You can specify a list of task IDs that are its prerequisites.
    - `define_prerequisite(task_id: str, prerequisite_id: str)`: Defines a new prerequisite for an existing task.
    - `get_next_task(objective_id: str)`: Finds the next available task for a given objective. Returns a message indicating the objective is complete if all tasks are done, or if the objective is blocked by a missing or incomplete prerequisite.
    - `complete_task(task_id: str)`: Marks a task as completed and returns the next available task.
    - `evaluate_feasibility(objective_id: str)`: Evaluates if an objective is feasible by checking for unknown prerequisites.

### Example Workflow

Here is a simple example of how to use the tools to manage an objective:

1.  **Define an objective**: `define_objective(id="learn_mcp", description="Learn the Model Context Protocol")`
2.  **Define tasks**:
    - `define_task(id="read_docs", description="Read the FastMCP documentation", objective_id="learn_mcp")`
    - `define_task(id="build_server", description="Build a simple MCP server", objective_id="learn_mcp", prerequisites=["read_docs"])`
    - `define_task(id="test_server", description="Test the server with a client", objective_id="learn_mcp", prerequisites=["build_server"])`
3.  **Execute the plan**:
    - `get_next_task(objective_id="learn_mcp")` -> Returns `"Next task for objective 'learn_mcp': read_docs - Read the FastMCP documentation"`.
    - `complete_task(task_id="read_docs")` -> Returns `"Task 'read_docs' marked as completed.\nNext task for objective 'learn_mcp': build_server - Build a simple MCP server"`.
    - `complete_task(task_id="build_server")` -> Returns `"Task 'build_server' marked as completed.\nNext task for objective 'learn_mcp': test_server - Test the server with a client"`.
    - `complete_task(task_id="test_server")` -> Returns `"Task 'test_server' marked as completed.\nObjective 'learn_mcp' is completed. All tasks are done."`.
4.  **Confirm completion**: `get_next_task(objective_id="learn_mcp")` -> Returns a message that the objective is complete.

## Running Tests

This project includes a test suite to verify its functionality. The tests use `pytest` and run in-memory without needing to keep the server running in a separate process.

To run the tests, execute the following command from the root directory:

```bash
pytest
``` 
