import sys
from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Set

# --- Data Structures ---

class Task(BaseModel):
    id: str
    description: str
    prerequisites: List[str] = []
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
    It automatically uses a unique identifier from the underlying connection
    session. If no identifier can be found (e.g., in tests), it falls back
    to a default shared session.
    """
    mcp_instance: ConductorMCP = ctx.fastmcp # type: ignore
    
    session_key = None
    # Use the unique ID of the transport session object for automatic isolation.
    session_obj = getattr(ctx, 'session', None)
    if session_obj and hasattr(session_obj, 'id'):
        session_key = session_obj.id

    # As a failsafe for test environments or non-compliant clients, use a default key.
    if not session_key:
        session_key = "default_session"

    if session_key not in mcp_instance.sessions:
        mcp_instance.sessions[session_key] = ServerState()
    
    return mcp_instance.sessions[session_key]

# --- Tools ---

def _reset_state(ctx: Context) -> str:
    """Resets the in-memory storage. For testing purposes only."""
    state = get_session_state(ctx)
    state.reset()
    return "State has been reset."

@mcp.tool()
def define_objective(ctx: Context, id: str, description: str) -> str:
    """Defines a new objective to be achieved."""
    state = get_session_state(ctx)
    if id in state.objectives:
        return f"Objective '{id}' already exists."
    state.objectives[id] = Objective(id=id, description=description)
    return f"Objective '{id}' defined."

def _check_for_deadlocks(task_id: str, prerequisites: List[str], all_tasks: Dict[str, Task]) -> bool:
    """Checks if adding a prerequisite would create a deadlock."""
    visited = set()
    recursion_stack = set()

    def check_node(node_id):
        visited.add(node_id)
        recursion_stack.add(node_id)

        # Get the prerequisites for the current node
        # If the node is the one we're checking, use its proposed new prerequisites
        current_prerequisites = prerequisites if node_id == task_id else all_tasks.get(node_id, Task(id="", description="")).prerequisites

        for prerequisite_id in current_prerequisites:
            if prerequisite_id not in visited:
                if check_node(prerequisite_id):
                    return True
            elif prerequisite_id in recursion_stack:
                return True
        
        recursion_stack.remove(node_id)
        return False

    return check_node(task_id)

@mcp.tool()
def define_task(ctx: Context, id: str, description: str, objective_id: str, prerequisites: List[str] = []) -> str:
    """Defines a new task as a part of achieving an objective."""
    state = get_session_state(ctx)
    obj = state.objectives.get(objective_id)
    if not obj:
        return f"Objective '{objective_id}' not found."

    if id in state.tasks:
        return f"Task '{id}' already exists."
    
    if _check_for_deadlocks(id, prerequisites, state.tasks):
        return f"Task '{id}' would create a deadlock and was not added."
    
    state.tasks[id] = Task(id=id, description=description, prerequisites=prerequisites)
    obj.tasks.append(id)
    return f"Task '{id}' added to objective '{objective_id}'."

@mcp.tool()
def complete_task(ctx: Context, task_id: str) -> str:
    """Marks a task as completed."""
    state = get_session_state(ctx)
    if task_id not in state.tasks:
        return f"Task '{task_id}' not found."
    state.tasks[task_id].completed = True
    return f"Task '{task_id}' marked as completed."

@mcp.tool()
def define_prerequisite(ctx: Context, task_id: str, prerequisite_id: str) -> str:
    """Defines a new prerequisite for an existing task."""
    state = get_session_state(ctx)
    if task_id not in state.tasks:
        return f"Task '{task_id}' not found."
    if task_id == prerequisite_id:
        return f"Task '{task_id}' cannot have itself as a prerequisite."

    task = state.tasks[task_id]
    
    if prerequisite_id in task.prerequisites:
        return f"Prerequisite '{prerequisite_id}' already exists for task '{task_id}'."

    new_prerequisites = task.prerequisites + [prerequisite_id]
    if _check_for_deadlocks(task_id, new_prerequisites, state.tasks):
        return f"Adding prerequisite '{prerequisite_id}' to task '{task_id}' would create a deadlock."

    task.prerequisites.append(prerequisite_id)
    return f"Added prerequisite '{prerequisite_id}' to task '{task_id}'."

@mcp.tool()
def get_next_task(ctx: Context, objective_id: str) -> str:
    """
    Finds the next available task for a given objective. Returns a message indicating
    the objective is complete if all tasks are done, or if the objective is blocked
    by a missing or incomplete prerequisite.
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
            for prerequisite_id in task.prerequisites:
                if prerequisite_id not in state.tasks:
                    return (
                        f"Objective '{objective_id}' is blocked. "
                        f"Please define the task for prerequisite '{prerequisite_id}'."
                    )

    for task_id in objective.tasks:
        task = state.tasks.get(task_id)
        if not task or task.completed:
            continue

        prerequisites_met = True
        for prerequisite_id in task.prerequisites:
            dep_task = state.tasks.get(prerequisite_id)
            if not dep_task or not dep_task.completed:
                prerequisites_met = False
                break
        
        if prerequisites_met:
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
    """Evaluates if an objective is feasible by checking for unknown prerequisites."""
    state = get_session_state(ctx)
    if objective_id not in state.objectives:
        return f"Objective '{objective_id}' not found."

    obj = state.objectives[objective_id]
    missing_prerequisites = []
    for task_id in obj.tasks:
        task = state.tasks.get(task_id)
        if task:
            for prerequisite_id in task.prerequisites:
                if prerequisite_id not in state.tasks:
                    missing_prerequisites.append(prerequisite_id)

    if missing_prerequisites:
        return f"Objective '{objective_id}' is NOT feasible. Unknown prerequisites: {sorted(list(set(missing_prerequisites)))}"
    else:
        return f"Objective '{objective_id}' appears feasible."

if __name__ == "__main__":
    mcp.run() 
