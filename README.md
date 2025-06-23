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

Conductor MCP is designed to be used as a server with an MCP-compatible client, such as an AI coding assistant in an editor like Cursor or VS Code.

To configure the server, find the "MCP Tools" or "MCP Servers" settings in your editor's configuration. Then, add a new server configuration block like this:

```json
"conductor": {
  "command": "python",
  "args": ["/path/to/your/clone/of/conductor-mcp/main.py"]
}
```

Make sure to replace `/path/to/your/clone/of/conductor-mcp/main.py` with the actual path to the `main.py` file in your cloned repository.

Once configured, your AI coding assistant will be able to use the Conductor MCP tools.

### Available Tools
You can interact with the server using the following tools:

- `set_goal(id: str, description: str, prerequisites: List[str] = [])`: Defines a new goal or updates an existing one. If any prerequisites do not exist, it will notify you that they are undefined.
- `set_goals(goals: List[Dict])`: Defines or updates multiple goals at once, including their relationships. Accepts an arbitrary dependency graph. If there are cycles in the graph, it will return an error message listing the problematic goal IDs. If any prerequisites are undefined, it will return a warning listing them. Example usage:

    ```python
    set_goals([
        {"id": "a", "description": "A"},
        {"id": "b", "description": "B", "prerequisites": ["a"]},
        {"id": "c", "description": "C", "prerequisites": ["b"]},
        {"id": "d", "description": "D", "prerequisites": ["a", "c"]},
    ])
    # Returns: "Goals defined."
    ```
    If you try to create a deadlock:
    ```python
    set_goals([
        {"id": "x", "description": "X", "prerequisites": ["y"]},
        {"id": "y", "description": "Y", "prerequisites": ["x"]},
    ])
    # Returns: "Deadlock detected in prerequisites. The following goals could not be created due to deadlocks: x, y."
    ```
    If you include undefined prerequisites:
    ```python
    set_goals([
        {"id": "z", "description": "Z", "prerequisites": ["not_defined"]},
    ])
    # Returns: "Goals defined, but the following prerequisite goals are undefined: not_defined."
    ```
- `add_prerequisite_to_goal(goal_id: str, prerequisite_id: str)`: Adds a new prerequisite to an existing goal.
- `plan_goal(goal_id: str, max_steps: Optional[int] = None, include_diagram: bool = True)`: Generates an ordered execution plan and, optionally, a Mermaid diagram of the dependency graph. It returns a dictionary with two keys: `plan` (a list of steps) and `diagram` (a string with the Mermaid diagram, or an empty string if `include_diagram` is `False`).
- `mark_goal_complete(goal_id: str)`: Marks a goal as completed. If this goal was a prerequisite for other goals, it will suggest checking on the now-unblocked goals.
- `assess_goal(goal_id: str)`: Retrieves the current status of a goal. This provides a quick summary of its completion state and whether its prerequisites are met. It returns one of four statuses:
    1. The goal is complete.
    2. The goal is ready because all prerequisite goals have been met.
    3. The goal is well-defined, but some prerequisites are not yet complete.
    4. The goal has undefined prerequisites and requires more definition.
- `reopen_goal(goal_id: str)`: Reopens a goal, marking it and any goals that depend on it as incomplete.

### Example Workflow

Here is a simple example of how to use the tools to manage a plan:

1.  **Define all your goals**:
    - `set_goal(id="read_docs", description="Read the FastMCP documentation")`
    - `set_goal(id="build_server", description="Build a simple MCP server", prerequisites=["read_docs"])`
    - `set_goal(id="test_server", description="Test the server with a client", prerequisites=["build_server"])`
    - `set_goal(id="learn_mcp", description="Learn the Model Context Protocol", prerequisites=["test_server"])`
2.  **Check if your top-level goal is feasible**: `assess_goal(goal_id="learn_mcp")` -> Returns a message indicating the goal is well-defined but has incomplete prerequisites, along with a completion summary.
3.  **Execute the plan**:
    - Begin by getting the steps for the top-level goal: `plan_goal(goal_id="learn_mcp")` -> Returns a dictionary containing the plan and a Mermaid diagram:
      ```json
      {
        "plan": [
          "Complete goal: 'read_docs' - Read the FastMCP documentation",
          "Complete goal: 'build_server' - Build a simple MCP server",
          "Complete goal: 'test_server' - Test the server with a client",
          "Complete goal: 'learn_mcp' - Learn the Model Context Protocol"
        ],
        "diagram": "graph TD\n    read_docs[\"read_docs: Read the FastMCP documentation\"]\n    build_server[\"build_server: Build a simple MCP server\"]\n    read_docs --> build_server\n    test_server[\"test_server: Test the server with a client\"]\n    build_server --> test_server\n    learn_mcp[\"learn_mcp: Learn the Model Context Protocol\"]\n    test_server --> learn_mcp\n"
      }
      ```
    - You can omit the diagram by calling: `plan_goal(goal_id="learn_mcp", include_diagram=False)`
      ```json
      {
        "plan": [
          "Complete goal: 'read_docs' - Read the FastMCP documentation",
          "Complete goal: 'build_server' - Build a simple MCP server",
          "Complete goal: 'test_server' - Test the server with a client",
          "Complete goal: 'learn_mcp' - Learn the Model Context Protocol"
        ],
        "diagram": ""
      }
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
