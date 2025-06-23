# Conductor MCP

Conductor MCP is a Python-based server that uses the Model Context Protocol (MCP) to help you define, track, and execute complex plans. It allows you to break down a large goal into a dependency graph of smaller, more manageable sub-goals, ensuring that they are executed in the correct order.

This tool is designed to be used with an MCP-compatible client or an LLM that can interact with MCP tools. It provides a simple yet powerful way to manage workflows and evaluate the feasibility of your plans.

## Purpose

The primary purpose of Conductor MCP is to provide a framework for:

- **Goal Management**: Defining a graph of goals, where each goal can have prerequisites (other goals that must be completed first).
- **Intelligent Execution**: Determining the next available goal based on the dependency graph and completed goals.
- **Feasibility Analysis**: Checking if a goal is achievable by verifying that all its prerequisites (and their prerequisites, recursively) are defined within the system.

## Multi-Session Support

This server is designed to be multi-tenant. It automatically creates a unique, isolated workspace for every client connection.

All goals and their states are automatically namespaced based on the connection. This means that multiple users or applications can interact with the server simultaneously without their data interfering with one another, ensuring a secure and predictable experience without any required client-side configuration.

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

    - `define_goal(id: str, description: str, prerequisites: List[str] = [])`: Defines a new goal, optionally with a list of prerequisite goals.
    - `define_prerequisite(goal_id: str, prerequisite_id: str)`: Defines a new prerequisite for an existing goal.
    - `get_next_goal(goal_id: str)`: Finds the next available goal to work on in order to complete the given goal.
    - `complete_goal(goal_id: str)`: Marks a goal as completed and returns the next available goal in the workflow, if there is one.
    - `evaluate_feasibility(goal_id: str)`: Evaluates if a goal is feasible by checking for unknown prerequisites.

### Example Workflow

Here is a simple example of how to use the tools to manage a plan:

1.  **Define all your goals**:
    - `define_goal(id="read_docs", description="Read the FastMCP documentation")`
    - `define_goal(id="build_server", description="Build a simple MCP server", prerequisites=["read_docs"])`
    - `define_goal(id="test_server", description="Test the server with a client", prerequisites=["build_server"])`
    - `define_goal(id="learn_mcp", description="Learn the Model Context Protocol", prerequisites=["test_server"])`
2.  **Check if your top-level goal is feasible**: `evaluate_feasibility(goal_id="learn_mcp")` -> Returns `"Goal 'learn_mcp' appears feasible."`.
3.  **Execute the plan**:
    - Begin by finding the first goal to work on: `get_next_goal(goal_id="learn_mcp")` -> Returns `"Next goal for 'learn_mcp': read_docs - Read the FastMCP documentation"`.
    - `complete_goal(goal_id="read_docs")` -> Returns `"Goal 'read_docs' marked as completed.\nNext goal for 'build_server': build_server - Build a simple MCP server"`.
    - `complete_goal(goal_id="build_server")` -> Returns `"Goal 'build_server' marked as completed.\nNext goal for 'test_server': test_server - Test the server with a client"`.
    - `complete_goal(goal_id="test_server")` -> Returns `"Goal 'test_server' marked as completed.\nNext goal for 'learn_mcp': learn_mcp - Learn the Model Context Protocol"`.
    - `complete_goal(goal_id="learn_mcp")` -> Returns `"Goal 'learn_mcp' marked as completed."`.
4.  **Confirm completion**: `get_next_goal(goal_id="learn_mcp")` -> Returns a message that the goal is already complete.

## Running Tests

This project includes a test suite to verify its functionality. The tests use `pytest` and run in-memory without needing to keep the server running in a separate process.

To run the tests, execute the following command from the root directory:

```bash
pytest
``` 
