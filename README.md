# Conductor MCP

Conductor MCP is a Python-based server that uses the Model Context Protocol (MCP) to help you define, track, and execute complex plans. It allows you to break down a large goal into a dependency graph of smaller, more manageable sub-goals, ensuring that they are executed in the correct order.

This tool is designed to be used with an MCP-compatible client or an LLM that can interact with MCP tools. It provides a simple yet powerful way to manage workflows and evaluate the feasibility of your plans.

## Purpose

The primary purpose of Conductor MCP is to provide a framework for:

- **Goal Management**: Defining a graph of goals, where each goal can have steps (other goals that must be completed first).
- **Intelligent Execution**: Determining the next available goal based on the dependency graph and completed goals.
- **Feasibility Analysis**: Checking if a goal is achievable by verifying that all its steps (and their steps, recursively) are defined within the system.

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

**For macOS/Linux/Windows (Git Bash/WSL/Cygwin):**
```json
"conductor": {
  "command": "/path/to/your/clone/of/conductor-mcp/run.sh"
}
```

**For Windows (Command Prompt or PowerShell):**
```json
"conductor": {
  "command": "C:\\path\\to\\your\\clone\\of\\conductor-mcp\\run.bat"
}
```

Make sure to replace the path with the actual location of the script in your cloned repository. The script will automatically activate the virtual environment and run the server.

**Note:** Use `run.sh` for Unix-like shells (macOS, Linux, Git Bash, WSL, Cygwin) and `run.bat` for native Windows Command Prompt or PowerShell.

Once configured, your AI coding assistant will be able to use the Conductor MCP tools.

### Usage Rules for AI-Assisted Coding Editors

For best results with Conductor MCP, load the file `conductor-rules.md` into your AI-assisted coding editor (such as Cursor or Windsurf) as rules. This enables your coding assistant to follow best practices and use Conductor MCP efficiently and effectively. You may also read the file if you wish, but its main purpose is to serve as a ruleset for your coding assistant.

## Available Tools
You can interact with the server using the following tools:

- `set_goals(goals: List[Dict])`: Defines or updates multiple goals at once, including their relationships. Accepts an arbitrary dependency graph. If there are cycles in the graph, it will return an error message listing the problematic goal IDs. If any steps are undefined, it will return a warning listing them. Each goal can have optional `steps` (list of ids) and `required_for` (list of ids) attributes. Example usage:

    ```python
    set_goals([
        {"id": "a", "description": "A"},
        {"id": "b", "description": "B", "steps": ["a"]},
        {"id": "c", "description": "C", "steps": ["b"]},
        {"id": "d", "description": "D", "steps": ["a", "c"]},
    ])
    # Returns: "Goals defined. Next, you might want to focus on a: A. You can use plan_for_goal to see the full plan."
    ```
    
    Using the `required_for` attribute:
    ```python
    set_goals([
        {"id": "child1", "description": "Child 1", "required_for": ["parent"]},
        {"id": "child2", "description": "Child 2", "required_for": ["parent"]}
    ])
    # This adds child1 and child2 as steps for the "parent" goal
    ```
    
    If you try to create a deadlock:
    ```python
    set_goals([
        {"id": "x", "description": "X", "steps": ["y"]},
        {"id": "y", "description": "Y", "steps": ["x"]},
    ])
    # Returns: "Deadlock detected in steps. The following goals could not be created due to deadlocks: x, y. Review your goal dependencies to remove cycles, then try again."
    ```
    If you include undefined steps:
    ```python
    set_goals([
        {"id": "z", "description": "Z", "steps": ["not_defined"]},
    ])
    # Returns: "Goals defined, but the following step goals are undefined: not_defined. We don't know what's involved with not_defined. Maybe you could look into defining those as goals using set_goals."
    ```
- `add_steps(goal_steps: Dict[str, List[str]])`: Adds steps to multiple goals, with different steps for each goal. Takes a dictionary mapping goal IDs to lists of step IDs.
- `plan_for_goal(goal_id: str, max_steps: Optional[int] = None, include_diagram: bool = True)`: Generates an ordered execution plan and, optionally, a Mermaid diagram of the dependency graph. It returns a dictionary with two keys: `plan` (a list of steps) and `diagram` (a string with the Mermaid diagram, or an empty string if `include_diagram` is `False`).
- `mark_goals(goal_ids: List[str], completed: bool = True, complete_steps: bool = False)`: Marks multiple goals as completed or incomplete. If this goal was a step for other goals, it will suggest focusing on all now-unblocked goals (listing all dependents if there are multiple).
- `assess_goal(goal_id: str)`: Retrieves the current status of a goal. This provides a quick summary of its completion state and whether its steps are met. It returns one of four statuses:
    1. The goal is complete.
    2. The goal is ready because all step goals have been met.
    3. The goal is well-defined, but some steps are not yet complete.
    4. The goal has undefined steps and requires more definition.

### Example Workflow

Here is a simple example of how to use the tools to manage a plan:

1.  **Define all your goals**:
    ```python
    set_goals([
        {"id": "read_docs", "description": "Read the FastMCP documentation"},
        {"id": "build_server", "description": "Build a simple MCP server", "steps": ["read_docs"]},
        {"id": "test_server", "description": "Test the server with a client", "steps": ["build_server"]},
        {"id": "learn_mcp", "description": "Learn the Model Context Protocol", "steps": ["test_server"]}
    ])
    ```
2.  **Check if your top-level goal is feasible**: `assess_goal(goal_id="learn_mcp")` -> Returns a message indicating the goal is well-defined but has incomplete steps, along with a completion summary.
3.  **Execute the plan**:
    - Begin by getting the steps for the top-level goal: `plan_for_goal(goal_id="learn_mcp")` -> Returns a dictionary containing the plan and a Mermaid diagram:
      ```json
      {
        "plan": [
          "Complete goal: 'read_docs' - Read the FastMCP documentation",
          "Complete goal: 'build_server' - Build a simple MCP server",
          "Complete goal: 'test_server' - Test the server with a client",
          "Complete goal: 'learn_mcp' - Learn the Model Context Protocol",
          "Start by working on the first incomplete goal in the plan."
        ],
        "diagram": "graph TD\n    read_docs[\"read_docs: Read the FastMCP documentation\"]\n    build_server[\"build_server: Build a simple MCP server\"]\n    read_docs --> build_server\n    test_server[\"test_server: Test the server with a client\"]\n    build_server --> test_server\n    learn_mcp[\"learn_mcp: Learn the Model Context Protocol\"]\n    test_server --> learn_mcp\n"
      }
      ```
    - You can omit the diagram by calling: `plan_for_goal(goal_id="learn_mcp", include_diagram=False)`
      ```json
      {
        "plan": [
          "Complete goal: 'read_docs' - Read the FastMCP documentation",
          "Complete goal: 'build_server' - Build a simple MCP server",
          "Complete goal: 'test_server' - Test the server with a client",
          "Complete goal: 'learn_mcp' - Learn the Model Context Protocol",
          "Start by working on the first incomplete goal in the plan."
        ],
        "diagram": ""
      }
      ```
    - `mark_goals(goal_ids=["read_docs"])` -> Returns `"Goal 'read_docs' completed. Now that this goal is complete, you might want to focus on build_server. Use plan_for_goal to see what else is required."`.
    - `mark_goals(goal_ids=["build_server"])` -> Returns `"Goal 'build_server' completed. Now that this goal is complete, you might want to focus on test_server. Use plan_for_goal to see what else is required."`.
    - `mark_goals(goal_ids=["test_server"])` -> Returns `"Goal 'test_server' completed. Now that this goal is complete, you might want to focus on learn_mcp. Use plan_for_goal to see what else is required."`.
    - `mark_goals(goal_ids=["learn_mcp"])` -> Returns `"Goal 'learn_mcp' completed. All goals are complete."`.
    - If you complete a goal with multiple dependents, e.g. `mark_goals(goal_ids=["base"])` where both `dep1` and `dep2` depend on `base`, you'll get: `Goal 'base' completed. Now that this goal is complete, you might want to focus on dep1, dep2. Use plan_for_goal to see what else is required.`
4.  **Confirm completion**: `assess_goal(goal_id="learn_mcp")` -> Returns a message that the goal is complete. (e.g., `"The goal is complete. Choose another goal to work on or review completed work."`)

## Running Tests

This project includes a test suite to verify its functionality. The tests use `pytest` and run in-memory without needing to keep the server running in a separate process.

To run the tests, execute the following command from the root directory:

```