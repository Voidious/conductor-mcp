import sys
from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Set

# --- Data Structures ---

class Task(BaseModel):
    id: str
    description: str
    dependencies: List[str] = []
    completed: bool = False

class Objective(BaseModel):
    id: str
    description: str
    tasks: List[str] = []
    completed: bool = False

class ServerState:
    """A class to hold the server's in-memory state for a single session."""
    def __init__(self):
        self.objectives: Dict[str, Objective] = {}
        self.tasks: Dict[str, Task] = {}
    
    def reset(self):
        self.objectives.clear()
        self.tasks.clear()

class ConductorMCP(FastMCP):
    """A custom FastMCP subclass that will hold all session states."""
    sessions: Dict[str, ServerState]

# --- MCP Server Setup ---

mcp = ConductorMCP("Conductor MCP")
mcp.sessions = {}  # type: ignore

# --- Session Management ---

def get_session_state(ctx: Context) -> ServerState:
    """
    Gets or creates the state for the current session, ensuring data isolation.
    It uses the session_id or, as a fallback, the client_id to namespace the data.
    """
    mcp_instance: ConductorMCP = ctx.fastmcp # type: ignore
    
    # Safely get the session key, preferring session_id but falling back to client_id.
    session_key = getattr(ctx, 'session_id', None) or getattr(ctx, 'client_id', None)

    # If no key is found and we are in a test environment, use a default key.
    if not session_key and 'pytest' in sys.modules:
        session_key = "test_session"

    if not session_key:
        # This case should only happen if no identifier can be found.
        raise ValueError("Could not determine a unique session or client ID for state management.")

    if session_key not in mcp_instance.sessions:
        mcp_instance.sessions[session_key] = ServerState()
    
    return mcp_instance.sessions[session_key]

# --- Tools ---

def _reset_state(ctx: Context) -> str:
    """Resets the in-memory storage for the current session. For testing purposes only."""
    state = get_session_state(ctx)
    state.reset()
    return "State for the current session has been reset."

@mcp.tool()
def add_objective(ctx: Context, id: str, description: str) -> str:
    """Adds a new objective to the current session."""
    state = get_session_state(ctx)
    if id in state.objectives:
        return f"Objective '{id}' already exists."
    state.objectives[id] = Objective(id=id, description=description)
    return f"Objective '{id}' added."

def _check_for_cycles(task_id: str, dependencies: List[str], all_tasks: Dict[str, Task]) -> bool:
    """Checks if adding a dependency would create a cycle."""
    visited = set()
    recursion_stack = set()

    def check_node(node_id):
        visited.add(node_id)
        recursion_stack.add(node_id)

        # Get the dependencies for the current node
        # If the node is the one we're checking, use its proposed new dependencies
        current_deps = dependencies if node_id == task_id else all_tasks.get(node_id, Task(id="", description="")).dependencies

        for dep_id in current_deps:
            if dep_id not in visited:
                if check_node(dep_id):
                    return True
            elif dep_id in recursion_stack:
                return True
        
        recursion_stack.remove(node_id)
        return False

    return check_node(task_id)

@mcp.tool()
def add_task(ctx: Context, id: str, description: str, objective_id: str, dependencies: List[str] = []) -> str:
    """Adds a new task to an objective in the current session."""
    state = get_session_state(ctx)
    obj = state.objectives.get(objective_id)
    if not obj:
        return f"Objective '{objective_id}' not found."

    if id in state.tasks:
        return f"Task '{id}' already exists."
    
    if _check_for_cycles(id, dependencies, state.tasks):
        return f"Task '{id}' would create a circular dependency and was not added."
    
    state.tasks[id] = Task(id=id, description=description, dependencies=dependencies)
    obj.tasks.append(id)
    return f"Task '{id}' added to objective '{objective_id}'."

@mcp.tool()
def complete_task(ctx: Context, task_id: str) -> str:
    """Marks a task as completed in the current session."""
    state = get_session_state(ctx)
    if task_id not in state.tasks:
        return f"Task '{task_id}' not found."
    state.tasks[task_id].completed = True
    return f"Task '{task_id}' marked as completed."

@mcp.tool()
def add_dependency(ctx: Context, task_id: str, dependency_id: str) -> str:
    """Adds a new dependency to an existing task in the current session."""
    state = get_session_state(ctx)
    if task_id not in state.tasks:
        return f"Task '{task_id}' not found."
    if task_id == dependency_id:
        return f"Task '{task_id}' cannot depend on itself."

    task = state.tasks[task_id]
    
    if dependency_id in task.dependencies:
        return f"Dependency '{dependency_id}' already exists for task '{task_id}'."

    new_dependencies = task.dependencies + [dependency_id]
    if _check_for_cycles(task_id, new_dependencies, state.tasks):
        return f"Adding dependency '{dependency_id}' to task '{task_id}' would create a circular dependency."

    task.dependencies.append(dependency_id)
    return f"Added dependency '{dependency_id}' to task '{task_id}'."

@mcp.tool()
def get_next_task(ctx: Context, objective_id: str) -> str:
    """
    Finds the next available task for a given objective in the current session.
    This tool first checks if all task dependencies are defined. If a dependency
    is found to be missing, it will return a message asking for the task to be
    defined. Only when all dependencies are defined will it return the next
    unblocked task. If all tasks are completed, it declares the objective complete.
    """
    state = get_session_state(ctx)
    objective = state.objectives.get(objective_id)

    if not objective:
        return f"Objective '{objective_id}' not found."

    if not objective.tasks:
        return f"Objective '{objective_id}' is completed. All tasks are done."

    for task_id in objective.tasks:
        task = state.tasks.get(task_id)
        if task:
            for dep_id in task.dependencies:
                if dep_id not in state.tasks:
                    return (
                        f"Objective '{objective_id}' is blocked. "
                        f"Please define the task for dependency '{dep_id}'."
                    )

    for task_id in objective.tasks:
        task = state.tasks.get(task_id)
        if not task or task.completed:
            continue

        dependencies_met = True
        for dep_id in task.dependencies:
            dep_task = state.tasks.get(dep_id)
            if not dep_task or not dep_task.completed:
                dependencies_met = False
                break
        
        if dependencies_met:
            return f"Next task for objective '{objective_id}': {task.id} - {task.description}"

    all_tasks_completed = all(
        state.tasks.get(task_id, Task(id="", description="")).completed
        for task_id in objective.tasks
    )

    if all_tasks_completed:
        objective.completed = True
        return f"Objective '{objective_id}' is completed. All tasks are done."
    else:
        return f"Objective '{objective_id}' is blocked. No tasks are currently available."

@mcp.tool()
def evaluate_feasibility(ctx: Context, objective_id: str) -> str:
    """Evaluates if an objective is feasible by checking for unknown dependencies in the current session."""
    state = get_session_state(ctx)
    if objective_id not in state.objectives:
        return f"Objective '{objective_id}' not found."

    obj = state.objectives[objective_id]
    missing_deps = []
    for task_id in obj.tasks:
        task = state.tasks.get(task_id)
        if task:
            for dep_id in task.dependencies:
                if dep_id not in state.tasks:
                    missing_deps.append(dep_id)

    if missing_deps:
        return f"Objective '{objective_id}' is NOT feasible. Unknown dependencies: {sorted(list(set(missing_deps)))}"
    else:
        return f"Objective '{objective_id}' appears feasible."

if __name__ == "__main__":
    mcp.run() 
