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

    - `set_goal(id: str, description: str, prerequisites: List[str] = [])`: Defines a new goal or updates an existing one. If any prerequisites do not exist, it will notify you that they are undefined.
    - `add_prerequisite_to_goal(goal_id: str, prerequisite_id: str)`: Adds a new prerequisite to an existing goal.
    - `plan_goal(goal_id: str, max_steps: Optional[int] = None)`: Returns an ordered list of all steps needed to accomplish the goal by running a topological sort on the graph of goals. Each step in the returned list is either to define a missing prerequisite goal or to complete a defined goal.
    - `mark_goal_complete(goal_id: str)`: Marks a goal as completed. If this goal was a prerequisite for other goals, it will suggest checking on the now-unblocked goals.
    - `assess_goal(goal_id: str)`: Evaluates if a goal is well-defined and achievable. It returns one of four statuses:
        1. The goal is complete.
        2. The goal is ready because all prerequisite goals have been met.
        3. The goal is well-defined, but some prerequisites are not yet complete.
        4. The goal has undefined prerequisites and requires more definition.
    - `mark_goal_incomplete(goal_id: str)`: Marks a goal as incomplete.

### Example Workflow

Here is a simple example of how to use the tools to manage a plan:

1.  **Define all your goals**:
    - `set_goal(id="read_docs", description="Read the FastMCP documentation")`
    - `set_goal(id="build_server", description="Build a simple MCP server", prerequisites=["read_docs"])`
    - `set_goal(id="test_server", description="Test the server with a client", prerequisites=["build_server"])`
    - `set_goal(id="learn_mcp", description="Learn the Model Context Protocol", prerequisites=["test_server"])`
2.  **Check if your top-level goal is feasible**: `assess_goal(goal_id="learn_mcp")` -> Returns a message indicating the goal is well-defined but has incomplete prerequisites, along with a completion summary.
3.  **Execute the plan**:
    - Begin by getting the steps for the top-level goal: `plan_goal(goal_id="learn_mcp")` -> Returns a list of steps, starting with the first goal to work on:
      ```json
      [
        "Complete goal: 'read_docs' - Read the FastMCP documentation",
        "Complete goal: 'build_server' - Build a simple MCP server",
        "Complete goal: 'test_server' - Test the server with a client",
        "Complete goal: 'learn_mcp' - Learn the Model Context Protocol"
      ]
      ```
    - `mark_goal_complete(goal_id="read_docs")` -> Returns `"Goal 'read_docs' marked as completed.\nYou may want to call plan_goal for: build_server"`.
    - `mark_goal_complete(goal_id="build_server")` -> Returns `"Goal 'build_server' marked as completed.\nYou may want to call plan_goal for: test_server"`.
    - `mark_goal_complete(goal_id="test_server")` -> Returns `"Goal 'test_server' marked as completed.\nYou may want to call plan_goal for: learn_mcp"`.
    - `mark_goal_complete(goal_id="learn_mcp")` -> Returns `"Goal 'learn_mcp' marked as completed."`.
4.  **Confirm completion**: `assess_goal(goal_id="learn_mcp")` -> Returns a message that the goal is complete.

## Running Tests

This project includes a test suite to verify its functionality. The tests use `pytest` and run in-memory without needing to keep the server running in a separate process.

To run the tests, execute the following command from the root directory:

```bash
pytest
``` 
