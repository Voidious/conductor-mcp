import graphlib
from fastmcp import FastMCP, Context
from pydantic import BaseModel
from typing import List, Dict, Optional, Set, Union, Any, Callable, Tuple
import argparse

# --- MCP Parameter Description Monkey Patch ---
PARAM_DESCRIPTIONS = {
    "set_goals": {
        "goals": (
            "(List[Dict]) A list of goal dictionaries. Each goal dict should have 'id' "
            "(str) and 'description' (str), with optional 'steps' and 'required_for' "
            "(List[str]) attributes. The 'steps' can be either: (1) List[str] of step "
            "IDs, or (2) a tree-format string like 'Goal: Main\\n"
            "├── Step: Sub1\\n│   ├── Step: SubSub1\\n│   └── Step: SubSub2\\n"
            "└── Step: Sub2' which automatically creates goal hierarchy."
        ),
    },
    "mark_goals": {
        "goal_ids": "(List[str]) List of goal IDs to mark as completed or incomplete",
        "completed": (
            "(bool, default=True) Whether to mark goals as completed (True) or "
            "incomplete (False)"
        ),
        "complete_steps": (
            "(bool, default=False) If True and completed=True, also marks all "
            "prerequisite steps as completed"
        ),
    },
    "add_steps": {
        "goal_steps": (
            "(Dict[str, List[str]]) Dictionary mapping goal IDs to lists of step IDs "
            "to add to each goal"
        ),
    },
    "plan_for_goal": {
        "goal_id": "(str) The ID of the goal to generate an execution plan for",
        "max_steps": (
            "(int, optional) Maximum number of steps to include in the returned plan"
        ),
        "include_diagram": (
            "(bool, default=True) Whether to include a Mermaid diagram in the response"
        ),
    },
    "assess_goal": {
        "goal_id": "(str) The ID of the goal to assess and check status for",
    },
}

try:
    from fastmcp.tools.tool import ParsedFunction

    # Only store the original if not already stored
    if "_original_from_function" not in globals():
        _original_from_function = ParsedFunction.from_function

    def patched_from_function(fn, exclude_args=None, validate=True):
        parsed = _original_from_function(
            fn, exclude_args=exclude_args, validate=validate
        )
        tool_name = getattr(fn, "__name__", None)
        if tool_name in PARAM_DESCRIPTIONS:
            param_descs = PARAM_DESCRIPTIONS[tool_name]
            props = parsed.parameters.get("properties")
            if props:
                for param, desc in param_descs.items():
                    if param in props:
                        props[param]["description"] = desc
        return parsed

    ParsedFunction.from_function = staticmethod(patched_from_function)
except ImportError:
    pass
# --- End MCP Parameter Description Monkey Patch ---

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


def _parse_dependency_tree(
    tree_text: str, root_goal_id: str = None
) -> Tuple[Dict[str, List[str]], Dict[str, str]]:
    """
    Parses a tree-like dependency hierarchy into a goal dependency map.

    Expected format (flexible indentation and prefixes):
    Goal: Main Goal
    ├── Step: Sub Step 1
    │   ├── Step: Sub Sub Step 1
    │   └── Step: Sub Sub Step 2
    ├── Step: Sub Step 2
    └── Step: Sub Step 3

    Args:
        tree_text: The tree structure text
        root_goal_id: Optional goal ID to use for the root goal instead of parsed name

    Returns:
        Tuple of (goal_dependencies dict, goal_descriptions dict)
        goal_dependencies: Dict mapping goal IDs to their direct dependencies (steps)
        goal_descriptions: Dict mapping goal IDs to their descriptions
    """
    lines = tree_text.strip().split("\n")
    if not lines:
        return {}, {}

    # Stack to track parent goals at each indentation level
    parent_stack = []
    goal_dependencies = {}
    goal_descriptions = {}
    first_goal = True

    for line in lines:
        if not line.strip():
            continue

        # Remove tree characters and calculate indentation
        clean_line = line.replace("├──", "").replace("└──", "").replace("│", "").strip()

        # Calculate indentation more flexibly - any amount of whitespace
        original_clean = line
        for char in ["├", "─", "└", "│"]:
            original_clean = original_clean.replace(char, " ")
        indent_level = len(original_clean) - len(original_clean.lstrip())

        # Extract goal name and description from various formats
        goal_name = ""
        description = ""

        if ":" in clean_line:
            # Split on first colon to separate prefix from content
            parts = clean_line.split(":", 1)
            prefix = parts[0].strip()
            content = parts[1].strip() if len(parts) > 1 else ""

            # If prefix looks like a goal type (Goal, Step, Task, etc.), use content as
            # goal name. Otherwise, use prefix as goal name and content as description.
            prefix_lower = prefix.lower()
            if prefix_lower in [
                "goal",
                "step",
                "task",
                "subtask",
                "phase",
                "stage",
                "final",
            ]:
                # Check if content has another colon for description
                if ":" in content:
                    goal_name, description = content.split(":", 1)
                    goal_name = goal_name.strip()
                    description = description.strip()
                else:
                    goal_name = content
            else:
                # Use prefix as goal name, content as description
                goal_name = prefix
                description = content
        else:
            # No colon - treat whole thing as goal name
            goal_name = clean_line.strip()

        if not goal_name:
            continue

        # Use provided root_goal_id for the first goal if specified
        if first_goal and root_goal_id:
            goal_id = root_goal_id
            first_goal = False
        else:
            goal_id = goal_name

        # Determine depth level - be more flexible with indentation
        # Consider any indentation change as a new level
        if indent_level == 0:
            depth = 0
        else:
            # Find appropriate depth based on existing stack
            depth = 1
            for i, stack_indent in enumerate(
                [0] + [4 * (j + 1) for j in range(len(parent_stack))]
            ):
                if indent_level <= stack_indent:
                    depth = i
                    break
            else:
                depth = len(parent_stack) + 1

        # Adjust parent stack to match current depth
        parent_stack = parent_stack[:depth]

        # Initialize goal dependencies and description if not exists
        if goal_id not in goal_dependencies:
            goal_dependencies[goal_id] = []
        goal_descriptions[goal_id] = description

        # If we have a parent, add this goal as a step to the parent
        if parent_stack:
            parent_id = parent_stack[-1]
            if parent_id not in goal_dependencies:
                goal_dependencies[parent_id] = []
            if goal_id not in goal_dependencies[parent_id]:
                goal_dependencies[parent_id].append(goal_id)

        # Add this goal to the parent stack for potential children
        parent_stack.append(goal_id)
        first_goal = False

    return goal_dependencies, goal_descriptions


def _format_description_with_period(description: str) -> str:
    """
    Helper function to ensure description ends with exactly one period.
    Prevents double periods when concatenating descriptions with text that starts with
    periods.
    """
    if not description:
        return description
    description = description.rstrip()
    if description.endswith("."):
        return description
    return f"{description}."


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
    an arbitrary dependency graph with automatic goal creation for all steps.

    Args:
        goals: A list of dicts, each with 'id', 'description', and optional
            'steps' and 'required_for' (list of ids) attributes. The 'steps' can be:
            - List format: ["step1", "step2"] - creates goals for each step with empty
              descriptions
            - Tree format: Multi-line string with ASCII tree structure:
              ```
              Goal: Main Goal
              ├── Step: Sub Step 1
              │   ├── Step: Sub Sub Step 1
              │   └── Step: Sub Sub Step 2
              ├── Step: Sub Step 2
              └── Step: Sub Step 3
              ```
              The tree format automatically creates the full goal hierarchy with proper
              dependencies. Step names are used directly as goal IDs (preserving
              original formatting): "Sub Step 1" becomes goal ID "Sub Step 1", "User
              Research Completed" becomes "User Research Completed", etc. The response
              immediately shows all auto-created goal IDs.

    Returns:
        A confirmation message if all goals are defined, or an error message listing
        problematic goals and reasons. All step references automatically create goals
        with empty descriptions that can be expanded later. The response always includes
        an actionable suggestion for what to do next.
    """
    state = get_session_state(ctx)

    # First, process goals and handle tree-format steps
    processed_goals = []
    all_tree_goals = {}  # Store goals created from tree parsing

    for goal in goals:
        processed_goal = goal.copy()
        steps = goal.get("steps", [])

        # Handle tree-format steps (string input)
        if isinstance(steps, str) and steps.strip():
            # Use the main goal's ID as the root goal ID
            main_goal_id = processed_goal["id"]
            tree_dependencies, tree_descriptions = _parse_dependency_tree(
                steps, main_goal_id
            )

            # Create goals for all nodes in the tree, excluding the main goal
            for goal_id, deps in tree_dependencies.items():
                if goal_id == main_goal_id:
                    # This is the main goal - just set its steps
                    processed_goal["steps"] = deps
                    # If tree has a description for main goal and main goal has no
                    # description, use it
                    if not processed_goal.get("description") and tree_descriptions.get(
                        goal_id
                    ):
                        processed_goal["description"] = tree_descriptions[goal_id]
                elif goal_id not in all_tree_goals:
                    all_tree_goals[goal_id] = {
                        "id": goal_id,
                        "description": tree_descriptions.get(goal_id, ""),
                        "steps": deps,
                    }
                else:
                    # Merge dependencies if goal already exists
                    existing_steps = set(all_tree_goals[goal_id]["steps"])
                    existing_steps.update(deps)
                    all_tree_goals[goal_id]["steps"] = list(existing_steps)
                    # Update description if we have one from tree and none exists
                    if not all_tree_goals[goal_id][
                        "description"
                    ] and tree_descriptions.get(goal_id):
                        all_tree_goals[goal_id]["description"] = tree_descriptions[
                            goal_id
                        ]

        # Handle list-format steps - now auto-create goals for consistency
        elif isinstance(steps, list):
            # Create goals for any step IDs that don't exist yet
            existing_goal_ids = {g["id"] for g in goals}
            for step_id in steps:
                if (
                    step_id not in all_tree_goals
                    and step_id not in existing_goal_ids
                    and step_id not in state.goals
                ):
                    all_tree_goals[step_id] = {
                        "id": step_id,
                        "description": "",
                        "steps": [],
                    }

        processed_goals.append(processed_goal)

    # Add tree-generated goals to the processed goals list
    processed_goals.extend(all_tree_goals.values())

    # Create temporary goals dict
    temp_goals = {
        gid: Goal(
            id=gid,
            description=goal.get("description", ""),
            steps=goal.get("steps", []),
            completed=(state.goals[gid].completed if gid in state.goals else False),
        )
        for goal in processed_goals
        if (gid := goal["id"])
    }

    # Then, handle required_for relationships in the temp dict
    for goal in processed_goals:
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
            f"created due to deadlocks: {', '.join(sorted(cycle_nodes))}.\n"
            "Suggestion: Review your goal dependencies to remove cycles, then try "
            "again."
        )

    # Commit temp_goals to state.goals
    state.goals.update(temp_goals)

    # Build response with created goal information
    response_parts = ["Goals defined."]

    # Show information about auto-created goals from steps
    original_goal_ids = {goal["id"] for goal in goals}
    auto_created_goals = [
        gid for gid in temp_goals.keys() if gid not in original_goal_ids
    ]

    if auto_created_goals:
        auto_created_count = len(auto_created_goals)
        if auto_created_count <= 5:
            # Show all IDs if 5 or fewer
            auto_created_list = ", ".join(sorted(auto_created_goals))
            response_parts.append(
                f"Auto-created {auto_created_count} step goals: {auto_created_list}"
            )
        else:
            # Show count and first few if many
            first_few = ", ".join(sorted(auto_created_goals)[:3])
            response_parts.append(
                f"Auto-created {auto_created_count} step goals including: "
                f"{first_few}... (use plan_for_goal to see all)"
            )

    # Suggest the first incomplete goal to focus on
    incomplete_goals = [g for g in state.goals.values() if not g.completed]
    if incomplete_goals:
        g = incomplete_goals[0]
        suggestion = (
            f"Next, you might want to focus on {g.id}: "
            f"{_format_description_with_period(g.description)} You can use "
            "plan_for_goal to see the full plan."
        )
    else:
        suggestion = "All goals are complete. If you want to add more, use set_goals."

    response_parts.append(suggestion)
    return "\n".join(response_parts)


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
        complete_steps: (Optional) If True and completed=True, also marks any of these
            goals' incomplete steps as completed. Defaults to False.

    Returns:
        A confirmation message. If completing goals unblocks other goals, the response
        includes an actionable suggestion for what to do next. If a goal has multiple
        dependents, all are listed in the suggestion.
    """
    state = get_session_state(ctx)

    def _mark_goal_complete_internal(goal_id: str):
        if goal_id not in state.goals:
            return
        goal = state.goals[goal_id]
        if goal.completed:
            return
        all_steps = _get_all_steps(goal_id, state.goals)
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
            incomplete_steps = [
                p
                for p in all_steps
                if p in state.goals and not state.goals[p].completed
            ]
            if incomplete_steps and not complete_steps:
                results.append(
                    f"Goal '{goal_id}': You must complete all prerequisites before "
                    "marking this goal as complete. "
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
        # Suggest all dependent goals to focus on
        dependents_list = sorted(all_dependents)
        if dependents_list:
            dependents_str = ", ".join(dependents_list)
            suggestion = (
                "Now that this goal is complete, you might want to focus on "
                f"{dependents_str}. Use plan_for_goal to see what else is required."
            )
        else:
            suggestion = "All dependents are complete."
        return result_message + f"\n{suggestion}"
    else:
        # Suggest the next incomplete goal
        incomplete_goals = [g for g in state.goals.values() if not g.completed]
        if incomplete_goals:
            g = incomplete_goals[0]
            suggestion = (
                f"Next, you might want to focus on {g.id}: "
                f"{_format_description_with_period(g.description)}"
            )
        else:
            suggestion = "All goals are complete."
        return result_message + f"\n{suggestion}"


@mcp.tool()
def add_steps(ctx: Context, goal_steps: Dict[str, List[str]]) -> str:
    """
    Adds steps to multiple goals, with different steps for each goal.

    Args:
        goal_steps: A dictionary mapping goal IDs to lists of step IDs to add to each
            goal.

    Returns:
        A confirmation message, indicating if any dependent goals were marked as
        incomplete. The response always includes an actionable suggestion for what to
        do next.
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
                    f"Adding step '{step_id}' to goal '{goal_id}' would create a "
                    "deadlock."
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
        next_goal = sorted(all_affected)[0] if all_affected else None
        if next_goal:
            suggestion = (
                "Some goals were marked incomplete. You might want to focus on "
                f"{next_goal} next. Use assess_goal or plan_for_goal to check the "
                "updated workflow."
            )
        else:
            suggestion = "All affected goals are complete."
        result_message += f"\n{suggestion}"
    else:
        # Suggest the next incomplete goal
        incomplete_goals = [g for g in state.goals.values() if not g.completed]
        if incomplete_goals:
            g = incomplete_goals[0]
            suggestion = (
                f"Next, you might want to focus on {g.id}: "
                f"{_format_description_with_period(g.description)} Use "
                "assess_goal or plan_for_goal to check the updated workflow."
            )
        else:
            suggestion = "All goals are complete."
        result_message += f"\n{suggestion}"
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
    Generates an ordered execution plan to accomplish a goal. The plan lists all
    goals in the dependency tree in the required order of completion, with clear next
    steps.

    Args:
        goal_id: The ID of the final goal you want to achieve.
        max_steps: (Optional) The maximum number of steps (goals) to include in the
            returned plan.
        include_diagram: (Optional) If False, the Mermaid diagram is omitted from the
            response. Defaults to True.

    Returns:
        A dictionary containing:
        - 'plan': An ordered list of execution steps. Each step shows either:
            * "Complete goal: 'goal_id' - description" for well-defined goals
            * "Define and complete goal: 'goal_id' - Details to be determined." for
              goals that need more definition (empty descriptions)
            The last element is always an actionable suggestion for what to do next.
        - 'diagram': A Mermaid diagram of the goal dependencies, or an empty string if
            include_diagram is False.

        Goals created from step references (list or tree format) that have empty
        descriptions will appear as "Define and complete goal" entries, prompting
        users to expand their definitions using set_goals.
    """
    state = get_session_state(ctx)
    if goal_id not in state.goals:
        return {
            "plan": [
                f"Goal '{goal_id}' not found. You may want to define this goal first "
                "using set_goals."
            ],
            "diagram": "",
        }
    goal = state.goals[goal_id]
    if goal.completed:
        return {
            "plan": [
                f"Goal '{goal_id}' is already completed. You can choose another goal "
                "to work on or review completed work."
            ],
            "diagram": "",
        }

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
            # This shouldn't happen now since we auto-create goals, but handle
            # gracefully
            steps.append(f"Complete goal: '{g_id}' - Details to be determined.")
        elif not g.completed:
            if g.description.strip():
                steps.append(f"Complete goal: '{g_id}' - {g.description}")
            else:
                steps.append(
                    f"Define and complete goal: '{g_id}' - Details to be determined."
                )

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

    if steps:
        first_action = steps[0]
        if "Define and complete goal" in first_action:
            suggestion = (
                "We don't know what's involved with one or more steps. Maybe you could "
                "look into defining those as goals using set_goals."
            )
        elif "Complete goal" in first_action:
            next_goal = None
            next_desc = None
            for s in steps:
                if s.startswith("Complete goal: "):
                    next_goal = s.split("'")[1]
                    # Try to get the description from the string
                    parts = s.split("- ")
                    if len(parts) > 1:
                        next_desc = parts[1]
                    break
            if next_goal:
                suggestion = (
                    f"Next, you might want to focus on {next_goal}: {next_desc}. Once "
                    "you've made progress, you can call mark_goals. Call add_steps or "
                    "set_goals if you discover additional requirements."
                )
            else:
                suggestion = "All goals are complete."
        elif "Error" in first_action:
            suggestion = (
                "There is a deadlock in your goal dependencies. Please review your "
                "goals and steps."
            )
        else:
            suggestion = (
                "All steps are complete. Consider reviewing or adding new goals."
            )
    else:
        suggestion = "All steps are complete. Consider reviewing or adding new goals."

    return {"plan": steps + ([suggestion] if suggestion else []), "diagram": diagram}


@mcp.tool()
def assess_goal(ctx: Context, goal_id: str) -> str:
    """
    Evaluates a goal's readiness and provides actionable guidance. Returns one of four
    distinct status types based on the goal's current state and dependencies.

    Args:
        goal_id: The ID of the goal to check.

    Returns:
        A human-readable status message with actionable guidance. Returns one of:

        1. **"Goal is ready"** - No steps required or all steps completed. Ready to
            work on.
        2. **"Needs more definition"** - Has step goals with empty descriptions that
            need expansion.
        3. **"Well-defined but incomplete"** - Has defined steps but some are not yet
            completed. Includes completion percentage and specific incomplete steps.
        4. **"Goal is complete"** - Goal has been marked as completed.

        Each status includes specific next-step recommendations (mark as complete,
        define steps, focus on specific incomplete steps, etc.).
    """
    state = get_session_state(ctx)
    if goal_id not in state.goals:
        return (
            f"Goal '{goal_id}' not found. You may want to define this goal first using "
            "set_goals."
        )
    goal = state.goals[goal_id]
    if goal.completed:
        return (
            "The goal is complete. You can choose another goal to work on or review "
            "completed work."
        )
    all_steps = _get_all_steps(goal_id, state.goals)
    # Check if any step goals have empty descriptions (need more definition)
    empty_desc_steps = sorted(
        [
            p
            for p in all_steps
            if p in state.goals and not state.goals[p].description.strip()
        ]
    )
    if empty_desc_steps:
        missing = ", ".join(empty_desc_steps)
        return (
            f"The goal has step goals that need more definition: {missing}. "
            f"We don't know what's involved with {missing}. "
            "Maybe you could look into defining those as goals using set_goals."
        )
    all_goals_in_workflow = all_steps.union({goal_id})
    incomplete_steps = sorted(
        [g for g in all_steps if g in state.goals and not state.goals[g].completed]
    )
    if not incomplete_steps:
        return (
            f"All step goals are met. The goal is ready: {goal.description}\nWhen the "
            "goal is complete, you can mark it as complete using mark_goals."
        )
    completed_count = len(all_goals_in_workflow) - len(incomplete_steps) - 1
    total_count = len(all_goals_in_workflow)
    percentage = (completed_count / total_count) * 100
    if incomplete_steps:
        suggestion = (
            f"You might want to focus on completing the step goal: "
            f"{incomplete_steps[0]}. Use plan_for_goal to see the required steps, or "
            "mark completed steps as done."
        )
    else:
        suggestion = "All step goals are complete."
    return (
        f"The goal is well-defined, but some step goals are incomplete. "
        f"Completion: {completed_count}/{total_count} ({percentage:.0f}%) goals "
        f"completed. Incomplete step goals: {', '.join(incomplete_steps)}.\n"
        f"{suggestion}"
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
    parser = argparse.ArgumentParser(description="Start the Lever MCP server.")
    parser.add_argument(
        "--http",
        action="store_true",
        help="Start the server with Streamable HTTP (instead of stdio)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host for HTTP server (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port for HTTP server (default: 8000)",
    )
    args = parser.parse_args()

    if args.http:
        mcp.run(transport="http", host=args.host, port=args.port)
    else:
        mcp.run()
