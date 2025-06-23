import pytest
from fastmcp import Client
import importlib
import json
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

    # Test completing a goal.
    result = await client.call_tool("mark_goal_complete", {"goal_id": "goal1"})
    assert result[0].text == "Goal 'goal1' marked as completed.\nYou may want to call plan_goal for: goal2"  # type: ignore

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
async def test_plan_goal(client: Client):
    """Tests the plan_goal tool logic."""
    await client.call_tool("set_goal", {"id": "goal1", "description": "Goal 1"})
    await client.call_tool("set_goal", {"id": "goal2", "description": "Goal 2", "prerequisites": ["goal1"]})

    # The steps for goal2 should be goal1, then goal2
    result = await client.call_tool("plan_goal", {"goal_id": "goal2"})
    steps_text = result[0].text
    steps = json.loads(steps_text) if steps_text.startswith('[') else [steps_text]
    assert steps == [
        "Complete goal: 'goal1' - Goal 1",
        "Complete goal: 'goal2' - Goal 2",
    ]

    # Complete goal1, so only goal2 should be left
    await client.call_tool("mark_goal_complete", {"goal_id": "goal1"})
    result_unblocked = await client.call_tool("plan_goal", {"goal_id": "goal2"})
    steps_unblocked_text = result_unblocked[0].text
    steps_unblocked = json.loads(steps_unblocked_text) if steps_unblocked_text.startswith('[') else [steps_unblocked_text]
    assert steps_unblocked == ["Complete goal: 'goal2' - Goal 2"]

    # Complete goal2, no steps should be left
    await client.call_tool("mark_goal_complete", {"goal_id": "goal2"})
    result_complete = await client.call_tool("plan_goal", {"goal_id": "goal2"})
    steps_complete_text = result_complete[0].text
    steps_complete = json.loads(steps_complete_text) if steps_complete_text.startswith('[') else [steps_complete_text]
    assert steps_complete == ["Goal 'goal2' is already completed."]

@pytest.mark.asyncio
async def test_plan_goal_no_prereqs(client: Client):
    """Tests that a goal with no prerequisites is its own step."""
    await client.call_tool("set_goal", {"id": "goal_simple", "description": "Simple Goal"})
    result = await client.call_tool("plan_goal", {"goal_id": "goal_simple"})
    steps_text = result[0].text
    steps = json.loads(steps_text) if steps_text.startswith('[') else [steps_text]
    assert steps == ["Complete goal: 'goal_simple' - Simple Goal"]

@pytest.mark.asyncio
async def test_plan_goal_max_steps(client: Client):
    """Tests the max_steps parameter of plan_goal."""
    await client.call_tool("set_goal", {"id": "goal1", "description": "Goal 1"})
    await client.call_tool("set_goal", {"id": "goal2", "description": "Goal 2", "prerequisites": ["goal1"]})
    
    result = await client.call_tool("plan_goal", {"goal_id": "goal2", "max_steps": 1})
    steps_text = result[0].text
    steps = json.loads(steps_text) if steps_text.startswith('[') else [steps_text]
    assert steps == ["Complete goal: 'goal1' - Goal 1"]

@pytest.mark.asyncio
async def test_plan_goal_missing_definition(client: Client):
    """Tests that plan_goal correctly identifies a missing prerequisite goal definition."""
    await client.call_tool("set_goal", {"id": "top_goal", "description": "Top", "prerequisites": ["missing_goal"]})
    result = await client.call_tool("plan_goal", {"goal_id": "top_goal"})
    steps_text = result[0].text
    steps = json.loads(steps_text) if steps_text.startswith('[') else [steps_text]
    assert steps == [
        "Define missing prerequisite goal: 'missing_goal'",
        "Complete prerequisites for goal: 'missing_goal'",
        "Complete goal: 'missing_goal' - Details to be determined.",
        "Complete goal: 'top_goal' - Top",
    ]

    # Test with multiple missing prerequisites, ensuring it orders them correctly.
    await client.call_tool("set_goal", {"id": "top_goal_2", "description": "Top 2", "prerequisites": ["z_missing", "a_missing"]})
    result2 = await client.call_tool("plan_goal", {"goal_id": "top_goal_2"})
    steps2_text = result2[0].text
    steps2 = json.loads(steps2_text) if steps2_text.startswith('[') else [steps2_text]
    # The order of undefined goals depends on graph traversal, but they must come before goals that depend on them.
    assert "Define missing prerequisite goal: 'z_missing'" in steps2
    assert "Define missing prerequisite goal: 'a_missing'" in steps2
    assert "Complete goal: 'top_goal_2' - Top 2" in steps2
    assert steps2.index("Define missing prerequisite goal: 'a_missing'") < steps2.index("Complete goal: 'top_goal_2' - Top 2")
    assert steps2.index("Define missing prerequisite goal: 'z_missing'") < steps2.index("Complete goal: 'top_goal_2' - Top 2")

@pytest.mark.asyncio
async def test_reopen_goal(client: Client):
    """Tests the reopen_goal tool."""
    await client.call_tool("set_goal", {"id": "goal1", "description": "Goal 1"})
    await client.call_tool("set_goal", {"id": "goal2", "description": "Goal 2", "prerequisites": ["goal1"]})

    # Complete both goals
    await client.call_tool("mark_goal_complete", {"goal_id": "goal1"})
    await client.call_tool("mark_goal_complete", {"goal_id": "goal2"})

    # Reopen goal1
    result = await client.call_tool("reopen_goal", {"goal_id": "goal1"})
    assert "Goal 'goal1' has been reopened." in result[0].text  # type: ignore
    assert "The following dependent goals were also reopened: goal1, goal2" in result[0].text # type: ignore

    # Assess goal2, it should now be incomplete
    assess_result = await client.call_tool("assess_goal", {"goal_id": "goal2"})
    assert "Incomplete prerequisite goals: goal1." in assess_result[0].text  # type: ignore

    # Reopening an already open goal should yield a specific message.
    result_already_open = await client.call_tool("reopen_goal", {"goal_id": "goal1"})
    assert "Goal 'goal1' is already open." in result_already_open[0].text  # type: ignore

@pytest.mark.asyncio
async def test_assess_goal(client: Client):
    """Tests the assess_goal tool."""
    await client.call_tool("set_goal", {"id": "goal1", "description": "Goal 1"})
    await client.call_tool("set_goal", {"id": "goal2", "description": "Goal 2", "prerequisites": ["goal1"]})

    # 1. Test a goal that is well-defined but has incomplete prerequisites.
    result_incomplete = await client.call_tool("assess_goal", {"goal_id": "goal2"})
    assert "The goal is well-defined, but some prerequisite goals are incomplete." in result_incomplete[0].text  # type: ignore
    assert "Completion: 0/2 (0%) goals completed." in result_incomplete[0].text  # type: ignore
    assert "Incomplete prerequisite goals: goal1." in result_incomplete[0].text  # type: ignore

    # 2. Test a goal that is ready (all prerequisites met).
    await client.call_tool("mark_goal_complete", {"goal_id": "goal1"})
    result_ready = await client.call_tool("assess_goal", {"goal_id": "goal2"})
    assert result_ready[0].text == "All prerequisite goals are met. The goal is ready: Goal 2"  # type: ignore

    # 3. Test a goal that is already complete.
    await client.call_tool("mark_goal_complete", {"goal_id": "goal2"})
    result_complete = await client.call_tool("assess_goal", {"goal_id": "goal2"})
    assert result_complete[0].text == "The goal is complete."  # type: ignore

    # 4. Test a goal with undefined prerequisites.
    await client.call_tool("set_goal", {"id": "goal3", "description": "Goal 3", "prerequisites": ["missing_goal"]})
    result_undefined = await client.call_tool("assess_goal", {"goal_id": "goal3"})
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
    feasibility_result = await client.call_tool("assess_goal", {"goal_id": "serve_breakfast"})
    assert "The goal is well-defined, but some prerequisite goals are incomplete." in feasibility_result[0].text  # type: ignore

    # 3. Execute goals by following the plan_goal and mark_goal_complete prompts
    # Start with the top-level goal to find the first action
    steps_result = await client.call_tool("plan_goal", {"goal_id": "serve_breakfast"})
    steps_text = steps_result[0].text
    steps = json.loads(steps_text) if steps_text.startswith('[') else [steps_text]
    
    # The first steps should be to complete the base goals. Order is not guaranteed.
    assert "Complete goal: 'toast_bread' - Toast a slice of bread" in steps
    assert "Complete goal: 'boil_water' - Boil water for tea" in steps

    # Let's complete the goals one by one according to the steps
    for step in steps:
        if "Define" in step:
            # This test case has no undefined goals
            pass
        elif "Complete" in step:
            goal_id_to_complete = step.split("'")[1]
            await client.call_tool("mark_goal_complete", {"goal_id": goal_id_to_complete})

    # 4. Final check: All goals should now be complete.
    final_assessment = await client.call_tool("assess_goal", {"goal_id": "serve_breakfast"})
    assert "The goal is complete." in final_assessment[0].text  # type: ignore

@pytest.mark.asyncio
async def test_completion_with_multiple_dependents(client: Client):
    """Tests completing a goal with several dependents."""
    await client.call_tool("set_goal", {"id": "base", "description": "Base Goal"})
    await client.call_tool("set_goal", {"id": "dep1", "description": "Dependent 1", "prerequisites": ["base"]})
    await client.call_tool("set_goal", {"id": "dep2", "description": "Dependent 2", "prerequisites": ["base"]})
    
    result = await client.call_tool("mark_goal_complete", {"goal_id": "base"})
    # The order of dependents is not guaranteed, so check for both.
    assert "You may want to call plan_goal for" in result[0].text  # type: ignore
    assert "dep1" in result[0].text  # type: ignore
    assert "dep2" in result[0].text  # type: ignore
