import sys
import graphlib
from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Set, Union

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

def _find_all_dependents(goal_id: str, all_goals: Dict[str, Goal]) -> Set[str]:
    """Recursively find all goals that depend on the given goal (directly or transitively)."""
    dependents = set()
    for g in all_goals.values():
        if goal_id in g.prerequisites:
            if g.id not in dependents:
                dependents.add(g.id)
                dependents.update(_find_all_dependents(g.id, all_goals))
    return dependents

@mcp.tool()
def set_goal(ctx: Context, id: str, description: str, prerequisites: List[str] = []) -> str:
    """
    Defines a new goal or updates an existing one. Goals are the fundamental building blocks for planning and execution, representing tasks or objectives.

    Args:
        id: A unique string identifier for the goal (e.g., 'deploy_staging').
        description: A human-readable summary of what the goal entails.
        prerequisites: (Optional) A list of goal IDs that must be completed before this goal can be started.
    
    Returns:
        A confirmation message indicating that the goal has been defined.
    """
    state = get_session_state(ctx)
    
    if _check_for_deadlocks(id, prerequisites, state.goals):
        return f"Goal '{id}' would create a deadlock and was not added."
    
    state.goals[id] = Goal(id=id, description=description, prerequisites=prerequisites)
    
    undefined_prerequisites = [p for p in prerequisites if p not in state.goals]
    if undefined_prerequisites:
        return f"Goal '{id}' defined with the following undefined prerequisite goals: {', '.join(undefined_prerequisites)}."
    
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
def mark_goal_complete(ctx: Context, goal_id: str, complete_prerequisites: bool = False) -> str:
    """
    Marks a goal as completed, signifying its successful resolution.

    Args:
        goal_id: The ID of the goal to mark as complete.
        complete_prerequisites: (Optional) If True, also marks any of this goal's incomplete prerequisites as completed. Defaults to False.

    Returns:
        A confirmation message. If completing this goal unblocks other goals, suggests the next goal to work on.
    """
    state = get_session_state(ctx)
    def _mark_goal_complete_internal(goal_id: str):
        if goal_id not in state.goals:
            return
        goal = state.goals[goal_id]
        if goal.completed:
            return
        all_prereqs = _get_all_prerequisites(goal_id, state.goals)
        undefined_prereqs = [p for p in all_prereqs if p not in state.goals]
        for p in undefined_prereqs:
            state.goals[p] = Goal(id=p, description="", prerequisites=[], completed=True)
        for p in all_prereqs:
            if p in state.goals and not state.goals[p].completed:
                _mark_goal_complete_internal(p)
        state.goals[goal_id].completed = True
    if goal_id not in state.goals:
        return f"Goal '{goal_id}' not found."
    goal = state.goals.get(goal_id)
    if goal and goal.completed:
         return f"Goal '{goal_id}' was already completed."
    all_prereqs = _get_all_prerequisites(goal_id, state.goals)
    undefined_prereqs = [p for p in all_prereqs if p not in state.goals]
    incomplete_prereqs = [p for p in all_prereqs if p in state.goals and not state.goals[p].completed]
    if (undefined_prereqs or incomplete_prereqs) and not complete_prerequisites:
        return ("You must complete all prerequisites before marking this goal as complete. "
                "Run plan_goal to see the required steps. "
                "To override, call mark_goal_complete with complete_prerequisites=True (this will mark all prerequisites as completed).")
    if complete_prerequisites:
        _mark_goal_complete_internal(goal_id)
    else:
        state.goals[goal_id].completed = True
    completion_message = f"Goal '{goal_id}' marked as completed."
    dependents = [g.id for g in state.goals.values() if goal_id in g.prerequisites]
    if dependents:
        return completion_message + "\nYou may want to call plan_goal for: " + ", ".join(dependents)
    else:
        return completion_message

@mcp.tool()
def add_prerequisite_to_goal(ctx: Context, goal_id: str, prerequisite_id: str) -> str:
    """
    Adds a prerequisite to a goal.

    Args:
        goal_id: The ID of the goal to which the prerequisite will be added.
        prerequisite_id: The ID of the prerequisite goal to add.
    
    Returns:
        A confirmation message, indicating if any dependent goals were marked as incomplete.
    """
    state = get_session_state(ctx)
    if goal_id not in state.goals:
        return f"Goal '{goal_id}' not found."
    if goal_id == prerequisite_id:
        return f"Goal '{goal_id}' cannot have itself as a prerequisite."
    goal = state.goals[goal_id]
    if prerequisite_id in goal.prerequisites:
        return f"Prerequisite goal '{prerequisite_id}' already exists for goal '{goal_id}'."
    new_prerequisites = goal.prerequisites + [prerequisite_id]
    if _check_for_deadlocks(goal_id, new_prerequisites, state.goals):
        return f"Adding prerequisite goal '{prerequisite_id}' to goal '{goal_id}' would create a deadlock."
    goal.prerequisites.append(prerequisite_id)
    # Mark goal and all dependents as incomplete if they were complete
    affected = set()
    if goal.completed:
        goal.completed = False
        affected.add(goal_id)
    dependents = _find_all_dependents(goal_id, state.goals)
    for dep_id in dependents:
        if state.goals[dep_id].completed:
            state.goals[dep_id].completed = False
            affected.add(dep_id)
    msg = f"Added prerequisite goal '{prerequisite_id}' to goal '{goal_id}'."
    if affected:
        msg += f" The following goals were marked as incomplete due to dependency changes: {', '.join(sorted(affected))}."
    return msg

@mcp.tool()
def reopen_goal(ctx: Context, goal_id: str) -> str:
    """
    Reopens a goal, marking it and any goals that depend on it as incomplete. This is useful if a completed goal needs to be revisited due to new information or changed circumstances.

    Args:
        goal_id: The ID of the goal to reopen.

    Returns:
        A confirmation message, indicating if any dependent goals were also marked as incomplete.
    """
    state = get_session_state(ctx)
    if goal_id not in state.goals:
        return f"Goal '{goal_id}' not found."
    
    goal = state.goals[goal_id]
    if not goal.completed:
        return f"Goal '{goal_id}' is already open."

    affected = set()
    if state.goals[goal_id].completed:
        state.goals[goal_id].completed = False
        affected.add(goal_id)
    
    dependents = _find_all_dependents(goal_id, state.goals)
    for dep_id in dependents:
        if state.goals[dep_id].completed:
            state.goals[dep_id].completed = False
            affected.add(dep_id)
    
    msg = f"Goal '{goal_id}' has been reopened."
    if affected:
        msg += f" The following dependent goals were also reopened: {', '.join(sorted(affected))}."
    return msg

def _get_all_prerequisites(goal_id: str, all_goals: Dict[str, Goal]) -> Set[str]:
    """Recursively fetches all prerequisites for a given goal."""
    prereqs = set()
    for prereq_id in all_goals.get(goal_id, Goal(id="", description="")).prerequisites:
        if prereq_id not in prereqs:
            prereqs.add(prereq_id)
            prereqs.update(_get_all_prerequisites(prereq_id, all_goals))
    return prereqs

@mcp.tool()
def plan_goal(ctx: Context, goal_id: str, max_steps: Optional[int] = None) -> List[str]:
    """
    Generates an ordered execution plan to accomplish a goal. The plan lists the goal and all its prerequisites in the required order of completion.

    Args:
        goal_id: The ID of the final goal you want to achieve.
        max_steps: (Optional) The maximum number of steps (goals) to include in the returned plan.
    
    Returns:
        An ordered list of goal descriptions that must be completed.
    """
    state = get_session_state(ctx)
    if goal_id not in state.goals:
        return [f"Goal '{goal_id}' not found."]
    goal = state.goals[goal_id]
    if goal.completed:
        return [f"Goal '{goal_id}' is already completed."]
    nodes = set()
    queue = [goal_id]
    visited = set()
    while queue:
        current_id = queue.pop(0)
        if current_id in visited:
            continue
        visited.add(current_id)
        nodes.add(current_id)
        if current_id in state.goals:
            for prereq in state.goals[current_id].prerequisites:
                queue.append(prereq)
    graph = {}
    for node_id in nodes:
        if node_id in state.goals:
            graph[node_id] = state.goals[node_id].prerequisites
        else:
            graph[node_id] = []
    try:
        ts = graphlib.TopologicalSorter(graph)
        sorted_goals = list(ts.static_order())
    except graphlib.CycleError:
        return ["Error: A deadlock was detected in the goal dependencies. Please review your goals and prerequisites."]
    steps = []
    for g_id in sorted_goals:
        g = state.goals.get(g_id)
        if not g:
            steps.append(f"Define missing prerequisite goal: '{g_id}'")
            steps.append(f"Complete prerequisites for goal: '{g_id}'")
            steps.append(f"Complete goal: '{g_id}' - Details to be determined.")
        elif not g.completed:
            steps.append(f"Complete goal: '{g_id}' - {g.description}")
    if max_steps is not None:
        return steps[:max_steps]
    return steps

@mcp.tool()
def assess_goal(ctx: Context, goal_id: str) -> str:
    """
    Retrieves the current status of a goal. This provides a quick summary of its completion state and whether its prerequisites are met.

    Args:
        goal_id: The ID of the goal to check.

    Returns:
        A human-readable string summarizing the goal's status (e.g., 'Completed', 'Blocked by prerequisites', 'Ready to be worked on').
    """
    state = get_session_state(ctx)
    if goal_id not in state.goals:
        return f"Goal '{goal_id}' not found."
    goal = state.goals[goal_id]
    if goal.completed:
        return "The goal is complete."
    all_prereqs = _get_all_prerequisites(goal_id, state.goals)
    undefined_prereqs = sorted([p for p in all_prereqs if p not in state.goals])
    if undefined_prereqs:
        return f"The goal has undefined prerequisite goals: {', '.join(undefined_prereqs)}. More work is required to properly define the goal."
    all_goals_in_workflow = all_prereqs.union({goal_id})
    incomplete_prereqs = sorted([g for g in all_prereqs if g in state.goals and not state.goals[g].completed])
    if not incomplete_prereqs:
        return f"All prerequisite goals are met. The goal is ready: {goal.description}"
    completed_count = len(all_goals_in_workflow) - len(incomplete_prereqs) -1
    total_count = len(all_goals_in_workflow)
    percentage = (completed_count / total_count) * 100
    return (
        f"The goal is well-defined, but some prerequisite goals are incomplete. "
        f"Completion: {completed_count}/{total_count} ({percentage:.0f}%) goals completed. "
        f"Incomplete prerequisite goals: {', '.join(incomplete_prereqs)}."
    )

if __name__ == "__main__":
    mcp.run() 
