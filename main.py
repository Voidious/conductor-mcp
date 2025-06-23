import sys
from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Set

# --- Data Structures ---

class Goal(BaseModel):
    id: str
    description: str
    prerequisites: List[str] = []
    completed: bool = False

class ServerState:
    """A class to hold the server's in-memory state."""
    def __init__(self):
        self.goals: Dict[str, Goal] = {}
    
    def reset(self):
        self.goals.clear()

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
def define_goal(ctx: Context, id: str, description: str, prerequisites: List[str] = []) -> str:
    """Defines a new goal, optionally with a list of prerequisite goals."""
    state = get_session_state(ctx)
    if id in state.goals:
        return f"Goal '{id}' already exists."
    
    if _check_for_deadlocks(id, prerequisites, state.goals):
        return f"Goal '{id}' would create a deadlock and was not added."
    
    state.goals[id] = Goal(id=id, description=description, prerequisites=prerequisites)
    return f"Goal '{id}' defined."

def _check_for_deadlocks(goal_id: str, prerequisites: List[str], all_goals: Dict[str, Goal]) -> bool:
    """Checks if adding a prerequisite would create a deadlock."""
    visited = set()
    recursion_stack = set()

    def check_node(node_id):
        visited.add(node_id)
        recursion_stack.add(node_id)

        current_prerequisites = prerequisites if node_id == goal_id else all_goals.get(node_id, Goal(id="", description="")).prerequisites

        for prerequisite_id in current_prerequisites:
            if prerequisite_id not in visited:
                if check_node(prerequisite_id):
                    return True
            elif prerequisite_id in recursion_stack:
                return True
        
        recursion_stack.remove(node_id)
        return False

    return check_node(goal_id)

@mcp.tool()
def complete_goal(ctx: Context, goal_id: str) -> str:
    """
    Marks a goal as completed and returns the next available goal in the
    workflow, if there is one.
    """
    state = get_session_state(ctx)
    if goal_id not in state.goals:
        return f"Goal '{goal_id}' not found."
    
    goal = state.goals.get(goal_id)
    if goal and goal.completed:
         return f"Goal '{goal_id}' was already completed."

    state.goals[goal_id].completed = True
    completion_message = f"Goal '{goal_id}' marked as completed"

    # Find a dependent goal to determine the next step in the workflow.
    dependent_goal_id = None
    for g_id in state.goals:
        g = state.goals[g_id]
        if goal_id in g.prerequisites:
            dependent_goal_id = g_id
            break
    
    if dependent_goal_id:
        next_goal_message = _get_next_goal_logic(ctx, dependent_goal_id)
        return f"{completion_message}.\n{next_goal_message}"
    
    return f"{completion_message}."

@mcp.tool()
def define_prerequisite(ctx: Context, goal_id: str, prerequisite_id: str) -> str:
    """Defines a new prerequisite for an existing goal."""
    state = get_session_state(ctx)
    if goal_id not in state.goals:
        return f"Goal '{goal_id}' not found."
    if prerequisite_id not in state.goals:
        return f"Prerequisite goal '{prerequisite_id}' not found."
    if goal_id == prerequisite_id:
        return f"Goal '{goal_id}' cannot have itself as a prerequisite."

    goal = state.goals[goal_id]
    
    if prerequisite_id in goal.prerequisites:
        return f"Prerequisite '{prerequisite_id}' already exists for goal '{goal_id}'."

    new_prerequisites = goal.prerequisites + [prerequisite_id]
    if _check_for_deadlocks(goal_id, new_prerequisites, state.goals):
        return f"Adding prerequisite '{prerequisite_id}' to goal '{goal_id}' would create a deadlock."

    goal.prerequisites.append(prerequisite_id)
    return f"Added prerequisite '{prerequisite_id}' to goal '{goal_id}'."

def _get_all_prerequisites(goal_id: str, all_goals: Dict[str, Goal]) -> Set[str]:
    """Recursively fetches all prerequisites for a given goal."""
    prereqs = set()
    for prereq_id in all_goals.get(goal_id, Goal(id="", description="")).prerequisites:
        if prereq_id not in prereqs:
            prereqs.add(prereq_id)
            prereqs.update(_get_all_prerequisites(prereq_id, all_goals))
    return prereqs

def _get_next_goal_logic(ctx: Context, goal_id: str) -> str:
    """Contains the core logic for finding the next available goal."""
    state = get_session_state(ctx)
    if goal_id not in state.goals:
        return f"Goal '{goal_id}' not found."

    top_level_goal = state.goals[goal_id]
    if top_level_goal.completed:
        return f"Goal '{goal_id}' is already completed."

    all_prereqs = _get_all_prerequisites(goal_id, state.goals)
    all_prereqs.add(goal_id)

    for current_goal_id in sorted(list(all_prereqs)):
        current_goal = state.goals.get(current_goal_id)
        if not current_goal or current_goal.completed:
            continue

        prerequisites_met = all(
            state.goals.get(prereq_id, Goal(id="", description="")).completed
            for prereq_id in current_goal.prerequisites
        )
        
        if prerequisites_met:
            return f"Next goal for '{goal_id}': {current_goal.id} - {current_goal.description}"

    return f"Goal '{goal_id}' is blocked because no actionable task could be found in its dependency tree."

@mcp.tool()
def get_next_goal(ctx: Context, goal_id: str) -> str:
    """Finds the next available goal to work on in order to complete the given goal."""
    return _get_next_goal_logic(ctx, goal_id)

@mcp.tool()
def evaluate_feasibility(ctx: Context, goal_id: str) -> str:
    """Evaluates if a goal is feasible by checking for unknown prerequisites."""
    state = get_session_state(ctx)
    if goal_id not in state.goals:
        return f"Goal '{goal_id}' not found."

    all_prereqs = _get_all_prerequisites(goal_id, state.goals)
    unknown_prereqs = [prereq for prereq in all_prereqs if prereq not in state.goals]

    if unknown_prereqs:
        return f"Goal '{goal_id}' is NOT feasible. Unknown prerequisites: {sorted(list(set(unknown_prereqs)))}"
    else:
        return f"Goal '{goal_id}' appears feasible."

if __name__ == "__main__":
    mcp.run() 
