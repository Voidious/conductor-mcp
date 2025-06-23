import pytest
from fastmcp import Client
import importlib
import main
from main import ConductorMCP

@pytest.fixture
async def client():
    """
    Provides an isolated FastMCP client for each test by reloading the main
    module and explicitly resetting the application state for the session.
    """
    importlib.reload(main)
    mcp_instance: ConductorMCP = main.mcp
    # Register the reset tool dynamically for testing only.
    mcp_instance.tool()(main._reset_state)
    async with Client(mcp_instance) as c:
        # We call the session-aware reset tool to ensure a clean slate.
        # The main.py logic will handle the test environment's lack of a real client_id.
        await c.call_tool("_reset_state")
        yield c

@pytest.mark.asyncio
async def test_set_goal(client: Client):
    """Tests the set_goal tool for success and failure cases."""
    # Test adding a new goal
    result = await client.call_tool("set_goal", {"id": "goal1", "description": "Test Goal"})
    assert result[0].text == "Goal 'goal1' defined."  # type: ignore

    # Test updating a goal
    result_exists = await client.call_tool("set_goal", {"id": "goal1", "description": "Updated Goal"})
    assert result_exists[0].text == "Goal 'goal1' defined."  # type: ignore

    # Test adding a goal with a missing prerequisite is allowed and returns the correct message
    result_missing_dep = await client.call_tool("set_goal", {
        "id": "goal2",
        "description": "Goal with missing dep",
        "prerequisites": ["missing_goal"]
    })
    assert "undefined prerequisite goals: missing_goal" in result_missing_dep[0].text  # type: ignore

    # Test adding a goal that would create a direct deadlock (A -> A)
    result_self_cycle = await client.call_tool("set_goal", {
        "id": "goal3",
        "description": "Self-referential goal",
        "prerequisites": ["goal3"]
    })
    assert "deadlock" in result_self_cycle[0].text  # type: ignore

    # Test adding a goal that would create an indirect deadlock (A -> B -> A)
    await client.call_tool("set_goal", {"id": "goalA", "description": "Goal A", "prerequisites": ["goalB"]})
    result_indirect_cycle = await client.call_tool("set_goal", {
        "id": "goalB",
        "description": "Goal B",
        "prerequisites": ["goalA"]
    })
    assert "deadlock" in result_indirect_cycle[0].text  # type: ignore

@pytest.mark.asyncio
async def test_mark_goal_complete(client: Client):
    """Tests the mark_goal_complete tool."""
    await client.call_tool("set_goal", {"id": "goal1", "description": "Goal 1"})
    await client.call_tool("set_goal", {"id": "goal2", "description": "Goal 2", "prerequisites": ["goal1"]})

    # Test completing a goal that unblocks another.
    result = await client.call_tool("mark_goal_complete", {"goal_id": "goal1"})
    assert "Goal 'goal1' marked as completed" in result[0].text  # type: ignore
    assert "Next goal for 'goal2': goal2 - Goal 2" in result[0].text  # type: ignore

    # Test completing a goal that was already completed.
    result_already_done = await client.call_tool("mark_goal_complete", {"goal_id": "goal1"})
    assert "Goal 'goal1' was already completed" in result_already_done[0].text  # type: ignore

    # Test completing a goal with no dependents.
    await client.call_tool("set_goal", {"id": "goal3", "description": "Goal 3"})
    result_no_deps = await client.call_tool("mark_goal_complete", {"goal_id": "goal3"})
    assert result_no_deps[0].text == "Goal 'goal3' marked as completed."  # type: ignore

    # Test completing a non-existent goal
    result_no_goal = await client.call_tool("mark_goal_complete", {"goal_id": "nonexistent"})
    assert result_no_goal[0].text == "Goal 'nonexistent' not found."  # type: ignore

@pytest.mark.asyncio
async def test_next_goal_in_workflow(client: Client):
    """Tests the next_goal_in_workflow tool logic."""
    await client.call_tool("set_goal", {"id": "goal1", "description": "Goal 1"})
    await client.call_tool("set_goal", {"id": "goal2", "description": "Goal 2", "prerequisites": ["goal1"]})

    # The first available sub-goal for goal2 is goal1
    result = await client.call_tool("next_goal_in_workflow", {"goal_id": "goal2"})
    assert result[0].text == "Next goal for 'goal2': goal1 - Goal 1"  # type: ignore

    # Complete goal1, making goal2 itself the next goal
    await client.call_tool("mark_goal_complete", {"goal_id": "goal1"})
    result_unblocked = await client.call_tool("next_goal_in_workflow", {"goal_id": "goal2"})
    assert result_unblocked[0].text == "Next goal for 'goal2': goal2 - Goal 2"  # type: ignore

    # Complete goal2, no goals should be left
    await client.call_tool("mark_goal_complete", {"goal_id": "goal2"})
    result_complete = await client.call_tool("next_goal_in_workflow", {"goal_id": "goal2"})
    assert result_complete[0].text == "Goal 'goal2' is completed."  # type: ignore

@pytest.mark.asyncio
async def test_next_goal_in_workflow_no_prereqs(client: Client):
    """Tests that a goal with no prerequisites is its own next goal."""
    await client.call_tool("set_goal", {"id": "goal_simple", "description": "Simple Goal"})
    result = await client.call_tool("next_goal_in_workflow", {"goal_id": "goal_simple"})
    assert result[0].text == "Next goal for 'goal_simple': goal_simple - Simple Goal"  # type: ignore

@pytest.mark.asyncio
async def test_check_goal_feasibility(client: Client):
    """Tests the check_goal_feasibility tool."""
    await client.call_tool("set_goal", {"id": "goal1", "description": "Goal 1"})
    await client.call_tool("set_goal", {"id": "goal2", "description": "Goal 2", "prerequisites": ["goal1"]})

    # 1. Test a goal that is well-defined but has incomplete prerequisites.
    result_incomplete = await client.call_tool("check_goal_feasibility", {"goal_id": "goal2"})
    assert "The goal is well-defined, but some prerequisite goals are incomplete." in result_incomplete[0].text  # type: ignore
    assert "Completion: 0/2 (0%) goals completed." in result_incomplete[0].text  # type: ignore
    assert "Incomplete prerequisite goals: goal1." in result_incomplete[0].text  # type: ignore

    # 2. Test a goal that is ready (all prerequisites met).
    await client.call_tool("mark_goal_complete", {"goal_id": "goal1"})
    result_ready = await client.call_tool("check_goal_feasibility", {"goal_id": "goal2"})
    assert result_ready[0].text == "All prerequisite goals are met. The goal is ready: Goal 2"  # type: ignore

    # 3. Test a goal that is already complete.
    await client.call_tool("mark_goal_complete", {"goal_id": "goal2"})
    result_complete = await client.call_tool("check_goal_feasibility", {"goal_id": "goal2"})
    assert result_complete[0].text == "The goal is complete."  # type: ignore

    # 4. Test a goal with undefined prerequisites.
    await client.call_tool("set_goal", {"id": "goal3", "description": "Goal 3", "prerequisites": ["missing_goal"]})
    result_undefined = await client.call_tool("check_goal_feasibility", {"goal_id": "goal3"})
    assert "The goal has undefined prerequisite goals: missing_goal." in result_undefined[0].text  # type: ignore

@pytest.mark.asyncio
async def test_add_prerequisite_to_goal(client: Client):
    """Tests the add_prerequisite_to_goal tool."""
    await client.call_tool("set_goal", {"id": "goal1", "description": "Goal 1"})
    await client.call_tool("set_goal", {"id": "goal2", "description": "Goal 2"})
    await client.call_tool("set_goal", {"id": "goal3", "description": "Goal 3", "prerequisites": ["goal1"]})

    # Test adding a valid prerequisite
    result = await client.call_tool("add_prerequisite_to_goal", {"goal_id": "goal2", "prerequisite_id": "goal1"})
    assert result[0].text == "Added prerequisite goal 'goal1' to goal 'goal2'."  # type: ignore

    # Test adding a prerequisite that already exists
    result_exists = await client.call_tool("add_prerequisite_to_goal", {"goal_id": "goal2", "prerequisite_id": "goal1"})
    assert result_exists[0].text == "Prerequisite goal 'goal1' already exists for goal 'goal2'."  # type: ignore

    # Test adding a prerequisite to a non-existent goal
    result_no_goal = await client.call_tool("add_prerequisite_to_goal", {"goal_id": "nonexistent", "prerequisite_id": "goal1"})
    assert result_no_goal[0].text == "Goal 'nonexistent' not found."  # type: ignore
    
    # Test adding a prerequisite that creates a deadlock
    result_direct_cycle = await client.call_tool("add_prerequisite_to_goal", {"goal_id": "goal1", "prerequisite_id": "goal3"})
    assert "would create a deadlock" in result_direct_cycle[0].text  # type: ignore

    # Test adding a self-prerequisite
    result_self_cycle = await client.call_tool("add_prerequisite_to_goal", {"goal_id": "goal1", "prerequisite_id": "goal1"})
    assert result_self_cycle[0].text == "Goal 'goal1' cannot have itself as a prerequisite."  # type: ignore

@pytest.mark.asyncio
async def test_full_workflow_with_goals(client: Client):
    """
    Tests the full workflow from goal creation to completion using the new model.
    """
    # 1. Define all goals with prerequisites
    goals_to_add = [
        {"id": "toast_bread", "description": "Toast a slice of bread"},
        {"id": "boil_water", "description": "Boil water for tea"},
        {"id": "butter_toast", "description": "Butter the toast", "prerequisites": ["toast_bread"]},
        {"id": "brew_tea", "description": "Brew a cup of tea", "prerequisites": ["boil_water"]},
        {"id": "serve_breakfast", "description": "Serve the delicious breakfast", "prerequisites": ["butter_toast", "brew_tea"]},
    ]
    
    for goal in goals_to_add:
        await client.call_tool("set_goal", goal)

    # 2. Check feasibility of the top-level goal
    feasibility_result = await client.call_tool("check_goal_feasibility", {"goal_id": "serve_breakfast"})
    assert "The goal is well-defined, but some prerequisite goals are incomplete." in feasibility_result[0].text  # type: ignore

    # 3. Execute goals by following the next_goal_in_workflow and mark_goal_complete prompts
    # Start with the top-level goal to find the first action
    next_goal_str = await client.call_tool("next_goal_in_workflow", {"goal_id": "serve_breakfast"})
    assert "boil_water" in next_goal_str[0].text or "toast_bread" in next_goal_str[0].text  # type: ignore # Order is not guaranteed

    # Complete the un-ordered goals first and follow prompts
    completion_1 = await client.call_tool("mark_goal_complete", {"goal_id": "toast_bread"})
    assert "butter_toast" in completion_1[0].text # type: ignore

    completion_2 = await client.call_tool("mark_goal_complete", {"goal_id": "boil_water"})
    assert "brew_tea" in completion_2[0].text # type: ignore

    # Now complete the next set of goals. The order doesn't matter.
    await client.call_tool("mark_goal_complete", {"goal_id": "brew_tea"})
    
    # After butter_toast is done, the next goal for serve_breakfast should be serve_breakfast itself.
    completion_4 = await client.call_tool("mark_goal_complete", {"goal_id": "butter_toast"})
    assert "serve_breakfast" in completion_4[0].text # type: ignore
    
    # Finally, complete the 'serve_breakfast' goal itself
    completion_5 = await client.call_tool("mark_goal_complete", {"goal_id": "serve_breakfast"})
    assert "marked as completed" in completion_5[0].text  # type: ignore
    assert "Next goal" not in completion_5[0].text # It has no dependents

    # 4. Confirm final completion
    final_status = await client.call_tool("next_goal_in_workflow", {"goal_id": "serve_breakfast"})
    assert "is completed" in final_status[0].text  # type: ignore

@pytest.mark.asyncio
async def test_completion_with_multiple_dependents(client: Client):
    """
    Tests that completing a goal with multiple dependent goals correctly
    suggests a next step for one of the dependents.
    """
    await client.call_tool("set_goal", {"id": "get_supplies", "description": "Get supplies"})
    await client.call_tool("set_goal", {"id": "make_cake", "description": "Make a cake", "prerequisites": ["get_supplies"]})
    await client.call_tool("set_goal", {"id": "make_cookies", "description": "Make cookies", "prerequisites": ["get_supplies"]})

    # Completing "get_supplies" could lead to either "make_cake" or "make_cookies"
    result = await client.call_tool("mark_goal_complete", {"goal_id": "get_supplies"})
    result_text = result[0].text  # type: ignore
    
    assert "Goal 'get_supplies' marked as completed" in result_text
    
    cake_next = "Next goal for 'make_cake': make_cake - Make a cake"
    cookies_next = "Next goal for 'make_cookies': make_cookies - Make cookies"
    
    assert cake_next in result_text or cookies_next in result_text

@pytest.mark.asyncio
async def test_get_next_goal_blocked_by_missing_definition(client: Client):
    """Tests that next_goal_in_workflow correctly identifies a missing prerequisite goal definition."""
    await client.call_tool("set_goal", {"id": "top_goal", "description": "Top", "prerequisites": ["missing_goal"]})
    
    # get_next_goal should not return anything as the prereq is not defined. But feasibility should fail.
    # This is a key difference in the new model. The agent must use check_goal_feasibility.
    feasibility = await client.call_tool("check_goal_feasibility", {"goal_id": "top_goal"})
    assert "has undefined prerequisite goals" in feasibility[0].text  # type: ignore
    assert "missing_goal" in feasibility[0].text  # type: ignore

    next_goal = await client.call_tool("next_goal_in_workflow", {"goal_id": "top_goal"})
    assert "is blocked" in next_goal[0].text  # type: ignore
