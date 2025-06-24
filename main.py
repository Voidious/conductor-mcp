import sys
import graphlib
from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Set, Union, Any, Callable

# --- Data Structures ---


class Goal(BaseModel):
    id: str
    description: str
    steps: List[str] = []
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
    mcp_instance: ConductorMCP = ctx.fastmcp  # type: ignore

    session_key = None
    # Use the unique ID of the transport session object for automatic isolation.
    session_obj = getattr(ctx, "session", None)
    if session_obj and hasattr(session_obj, "id"):
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
    """
    Recursively find all goals that depend on the given goal (directly or
    transitively)."""
    dependents = set()
    for g in all_goals.values():
        if goal_id in g.steps:
            if g.id not in dependents:
                dependents.add(g.id)
                dependents.update(_find_all_dependents(g.id, all_goals))
    return dependents


@mcp.tool()
def set_goals(ctx: Context, goals: List[Dict[str, Any]]) -> str:
    """
    Defines or updates multiple goals at once, including their relationships. Accepts
    an arbitrary dependency graph.

    Args:
        goals: A list of dicts, each with 'id', 'description', and optional
            'steps' (list of ids) and 'required_for' (list of ids).

    Returns:
        A confirmation message if all goals are defined, or an error message listing
        problematic goals and reasons.
    """
    state = get_session_state(ctx)

    # First, add/update all goals in a temporary dict
    temp_goals = {
        gid: Goal(
            id=gid,
            description=goal.get("description", ""),
            steps=goal.get("steps", []),
            completed=(state.goals[gid].completed if gid in state.goals else False),
        )
        for goal in goals
        if (gid := goal["id"])
    }

    # Then, handle required_for relationships in the temp dict
    for goal in goals:
        goal_id = goal["id"]
        required_for = goal.get("required_for", [])
        for target_goal_id in required_for:
            if target_goal_id in temp_goals:
                if goal_id not in temp_goals[target_goal_id].steps:
                    temp_goals[target_goal_id].steps.append(goal_id)
            elif target_goal_id in state.goals:
                if goal_id not in state.goals[target_goal_id].steps:
                    state.goals[target_goal_id].steps.append(goal_id)
            else:
                temp_goals[target_goal_id] = Goal(
                    id=target_goal_id, description="", steps=[goal_id], completed=False
                )

    # Build a combined graph of existing and new goals for cycle detection
    combined_goals = {**state.goals, **temp_goals}

    # Check for cycles in the combined graph
    def get_neighbors(node_id: str) -> List[str]:
        return combined_goals.get(node_id, Goal(id="", description="")).steps

    # Get all nodes to check (temp_goals and their dependencies)
    all_nodes_to_check = set(temp_goals.keys())
    for goal in temp_goals.values():
        all_nodes_to_check.update(goal.steps)

    cycle_result = _has_cycle(all_nodes_to_check, get_neighbors)
    if cycle_result:
        # Find all nodes involved in cycles for error reporting
        cycle_nodes = _find_cycle_nodes(all_nodes_to_check, get_neighbors)
        # Remove any goals involved in the cycle from temp_goals
        for node in cycle_nodes:
            temp_goals.pop(node, None)
        return (
            f"Deadlock detected in steps. The following goals could not be "
            f"created due to deadlocks: {', '.join(sorted(cycle_nodes))}."
        )

    # Commit temp_goals to state.goals
    state.goals.update(temp_goals)

    # Check for undefined steps
    undefined = set()
    for goal in temp_goals.values():
        for step in goal.steps:
            if step not in state.goals:
                undefined.add(step)
    if undefined:
        return (
            f"Goals defined, but the following step goals are undefined: "
            f"{', '.join(sorted(undefined))}."
        )

    return "Goals defined."


@mcp.tool()
def mark_goals(
    ctx: Context,
    goal_ids: List[str],
    completed: bool = True,
    complete_steps: bool = False,
) -> str:
    """
    Marks multiple goals as completed or incomplete, signifying their resolution status.

    Args:
        goal_ids: List of goal IDs to mark.
        completed: Whether to mark the goals as completed (True) or incomplete (False).
        complete_steps: (Optional) If True and completed=True, also marks any of these goals'
            incomplete steps as completed. Defaults to False.

    Returns:
        A confirmation message. If completing goals unblocks other goals, suggests
        the next goals to work on.
    """
    state = get_session_state(ctx)

    def _mark_goal_complete_internal(goal_id: str):
        if goal_id not in state.goals:
            return
        goal = state.goals[goal_id]
        if goal.completed:
            return
        all_steps = _get_all_steps(goal_id, state.goals)
        undefined_steps = [p for p in all_steps if p not in state.goals]
        for p in undefined_steps:
            state.goals[p] = Goal(id=p, description="", steps=[], completed=True)
        for p in all_steps:
            if p in state.goals and not state.goals[p].completed:
                _mark_goal_complete_internal(p)
        state.goals[goal_id].completed = True

    results = []
    all_dependents = set()

    for goal_id in goal_ids:
        if goal_id not in state.goals:
            results.append(f"Goal '{goal_id}' not found.")
            continue

        goal = state.goals.get(goal_id)
        if goal and goal.completed == completed:
            status = "completed" if completed else "incomplete"
            results.append(f"Goal '{goal_id}' was already {status}.")
            continue

        if completed:
            all_steps = _get_all_steps(goal_id, state.goals)
            undefined_steps = [p for p in all_steps if p not in state.goals]
            incomplete_steps = [
                p
                for p in all_steps
                if p in state.goals and not state.goals[p].completed
            ]
            if (undefined_steps or incomplete_steps) and not complete_steps:
                results.append(
                    f"Goal '{goal_id}': You must complete all prerequisites before marking this goal as complete. "
                    "Run plan_for_goal to see the required steps. "
                    "To override, call mark_goals with complete_steps=True "
                    "(this will mark all prerequisites as completed)."
                )
                continue
            if complete_steps:
                _mark_goal_complete_internal(goal_id)
            else:
                state.goals[goal_id].completed = True
        else:
            state.goals[goal_id].completed = False

        status = "completed" if completed else "marked as incomplete"
        results.append(f"Goal '{goal_id}' {status}.")

        # Collect dependents for final message
        dependents = [g.id for g in state.goals.values() if goal_id in g.steps]
        all_dependents.update(dependents)

    result_message = "\n".join(results)

    if completed and all_dependents:
        return (
            result_message
            + "\nYou may want to call plan_for_goal for: "
            + ", ".join(sorted(all_dependents))
        )
    else:
        return result_message


@mcp.tool()
def add_steps(ctx: Context, goal_steps: Dict[str, List[str]]) -> str:
    """
    Adds steps to multiple goals, with different steps for each goal.

    Args:
        goal_steps: A dictionary mapping goal IDs to lists of step IDs to add to each goal.

    Returns:
        A confirmation message, indicating if any dependent goals were marked as
        incomplete.
    """
    state = get_session_state(ctx)
    results = []
    all_affected = set()

    for goal_id, steps in goal_steps.items():
        if goal_id not in state.goals:
            results.append(f"Goal '{goal_id}' not found.")
            continue

        goal = state.goals[goal_id]
        added_steps = []

        for step_id in steps:
            if goal_id == step_id:
                results.append(f"Goal '{goal_id}' cannot have itself as a step.")
                continue
            if step_id in goal.steps:
                results.append(f"Step '{step_id}' already exists for goal '{goal_id}'.")
                continue

            new_steps = goal.steps + [step_id]
            if _check_for_deadlocks(goal_id, new_steps, state.goals):
                results.append(
                    f"Adding step '{step_id}' to goal '{goal_id}' would create a deadlock."
                )
                continue

            goal.steps.append(step_id)
            added_steps.append(step_id)

        if added_steps:
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
            all_affected.update(affected)

            results.append(f"Added steps {', '.join(added_steps)} to goal '{goal_id}'.")

    result_message = "\n".join(results)

    if all_affected:
        result_message += (
            f"\nThe following goals were marked as incomplete due to dependency "
            f"changes: {', '.join(sorted(all_affected))}."
        )

    return result_message


def _check_for_deadlocks(
    goal_id: str, steps: List[str], all_goals: Dict[str, Goal]
) -> bool:
    """Checks if adding a step would create a deadlock."""

    def get_neighbors(node_id: str) -> List[str]:
        if node_id == goal_id:
            return steps
        return all_goals.get(node_id, Goal(id="", description="")).steps

    return _has_cycle({goal_id}, get_neighbors)


def _get_all_steps(goal_id: str, all_goals: Dict[str, Goal]) -> Set[str]:
    """Recursively fetches all steps for a given goal."""
    steps = set()
    visited = set()

    def _get_steps_recursive(current_id: str):
        if current_id in visited:
            return  # Prevent infinite recursion
        visited.add(current_id)

        current_goal = all_goals.get(current_id)
        if not current_goal:
            return

        for step_id in current_goal.steps:
            if step_id not in steps:
                steps.add(step_id)
                _get_steps_recursive(step_id)

    _get_steps_recursive(goal_id)
    return steps


@mcp.tool()
def plan_for_goal(
    ctx: Context,
    goal_id: str,
    max_steps: Optional[int] = None,
    include_diagram: bool = True,
) -> Dict[str, Union[List[str], str]]:
    """
    Generates an ordered execution plan to accomplish a goal. The plan lists the goal
    and all its steps in the required order of completion.

    Args:
        goal_id: The ID of the final goal you want to achieve.
        max_steps: (Optional) The maximum number of steps (goals) to include in the
            returned plan.
        include_diagram: (Optional) If False, the Mermaid diagram is omitted from the
            response. Defaults to True.

    Returns:
        A dictionary containing:
        - 'plan': An ordered list of goal descriptions that must be completed.
        - 'diagram': A Mermaid diagram of the goal dependencies, or an empty string if
            include_diagram is False.
    """
    state = get_session_state(ctx)
    if goal_id not in state.goals:
        return {"plan": [f"Goal '{goal_id}' not found."], "diagram": ""}
    goal = state.goals[goal_id]
    if goal.completed:
        return {"plan": [f"Goal '{goal_id}' is already completed."], "diagram": ""}

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
            for step in state.goals[current_id].steps:
                queue.append(step)

    graph = {}
    for node_id in nodes:
        if node_id in state.goals:
            graph[node_id] = state.goals[node_id].steps
        else:
            graph[node_id] = []

    try:
        ts = graphlib.TopologicalSorter(graph)
        sorted_goals = list(ts.static_order())
    except graphlib.CycleError:
        return {
            "plan": [
                "Error: A deadlock was detected in the goal dependencies. Please "
                "review your goals and steps."
            ],
            "diagram": "",
        }

    steps = []
    for g_id in sorted_goals:
        g = state.goals.get(g_id)
        if not g:
            steps.append(f"Define missing step goal: '{g_id}'")
            steps.append(f"Complete steps for goal: '{g_id}'")
            steps.append(f"Complete goal: '{g_id}' - Details to be determined.")
        elif not g.completed:
            steps.append(f"Complete goal: '{g_id}' - {g.description}")

    diagram = ""
    if include_diagram:
        diagram = "graph TD\n"
        for node_id in nodes:
            g = state.goals.get(node_id)
            if g:
                if g.completed:
                    diagram += (
                        f'    {node_id}["{node_id}: {g.description} <br/> '
                        '(Completed)"]\n'
                    )
                else:
                    diagram += f'    {node_id}["{node_id}: {g.description}"]\n'
            else:
                diagram += f'    {node_id}["{node_id} (undefined)"]\n'

            if node_id in state.goals:
                for step in state.goals[node_id].steps:
                    diagram += f"    {step} --> {node_id}\n"

    if max_steps is not None:
        steps = steps[:max_steps]

    return {"plan": steps, "diagram": diagram}


@mcp.tool()
def assess_goal(ctx: Context, goal_id: str) -> str:
    """
    Retrieves the current status of a goal. This provides a quick summary of its
    completion state and whether its prerequisites are met.

    Args:
        goal_id: The ID of the goal to check.

    Returns:
        A human-readable string summarizing the goal's status (e.g., 'Completed',
        'Blocked by prerequisites', 'Ready to be worked on').
    """
    state = get_session_state(ctx)
    if goal_id not in state.goals:
        return f"Goal '{goal_id}' not found."
    goal = state.goals[goal_id]
    if goal.completed:
        return "The goal is complete."
    all_steps = _get_all_steps(goal_id, state.goals)
    undefined_steps = sorted([p for p in all_steps if p not in state.goals])
    if undefined_steps:
        return (
            f"The goal has undefined step goals: "
            f"{', '.join(undefined_steps)}. More work is required to properly "
            "define the goal."
        )
    all_goals_in_workflow = all_steps.union({goal_id})
    incomplete_steps = sorted(
        [g for g in all_steps if g in state.goals and not state.goals[g].completed]
    )
    if not incomplete_steps:
        return f"All step goals are met. The goal is ready: {goal.description}"
    completed_count = len(all_goals_in_workflow) - len(incomplete_steps) - 1
    total_count = len(all_goals_in_workflow)
    percentage = (completed_count / total_count) * 100
    return (
        f"The goal is well-defined, but some step goals are incomplete. "
        f"Completion: {completed_count}/{total_count} ({percentage:.0f}%) goals "
        f"completed. Incomplete step goals: {', '.join(incomplete_steps)}."
    )


# --- Graph Traversal Utilities ---


def _has_cycle(
    start_nodes: Set[str], get_neighbors: Callable[[str], List[str]]
) -> bool:
    """
    Generic DFS cycle detection that returns a boolean.

    Args:
        start_nodes: Set of node IDs to start traversal from
        get_neighbors: Function that takes a node_id and returns list of neighbor IDs

    Returns:
        True if cycle exists, False otherwise
    """
    visited = set()
    stack = set()

    def visit(node_id):
        if node_id in stack:
            return True
        if node_id in visited:
            return False
        visited.add(node_id)
        stack.add(node_id)

        for neighbor in get_neighbors(node_id):
            if visit(neighbor):
                return True

        stack.remove(node_id)
        return False

    for node_id in start_nodes:
        if visit(node_id):
            return True

    return False


def _find_cycle_nodes(
    start_nodes: Set[str], get_neighbors: Callable[[str], List[str]]
) -> Set[str]:
    """
    Generic DFS cycle detection that returns nodes involved in cycles.

    Args:
        start_nodes: Set of node IDs to start traversal from
        get_neighbors: Function that takes a node_id and returns list of neighbor IDs

    Returns:
        Set of node IDs involved in cycles
    """
    visited = set()
    stack = set()
    cycle_nodes = set()

    def visit(node_id):
        if node_id in stack:
            cycle_nodes.add(node_id)
            return True
        if node_id in visited:
            return False
        visited.add(node_id)
        stack.add(node_id)

        for neighbor in get_neighbors(node_id):
            if visit(neighbor):
                cycle_nodes.add(node_id)
                return True

        stack.remove(node_id)
        return False

    for node_id in start_nodes:
        visit(node_id)

    return cycle_nodes


if __name__ == "__main__":
    mcp.run()
