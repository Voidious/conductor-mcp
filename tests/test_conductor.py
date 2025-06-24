import pytest  # type: ignore
from fastmcp import Client
import importlib
import json
import main
from main import ConductorMCP
from mcp.types import TextContent
from typing import List, Dict, Any


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
async def test_mark_goals(client: Client) -> None:
    """Tests the mark_goals tool."""
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal1", "description": "Goal 1"}]}
    )
    await client.call_tool(
        "set_goals",
        {"goals": [{"id": "goal2", "description": "Goal 2", "steps": ["goal1"]}]},
    )

    # Test completing a goal.
    result = await client.call_tool("mark_goals", {"goal_ids": ["goal1"]})
    assert result[0].text == (  # type: ignore
        "Goal 'goal1' completed.\nYou may want to call plan_for_goal for: goal2"
    )

    # Test completing a goal that was already completed.
    result_already_done = await client.call_tool("mark_goals", {"goal_ids": ["goal1"]})
    assert "Goal 'goal1' was already completed" in result_already_done[0].text  # type: ignore

    # Test completing a goal with no dependents.
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal3", "description": "Goal 3"}]}
    )
    result_no_deps = await client.call_tool("mark_goals", {"goal_ids": ["goal3"]})
    assert result_no_deps[0].text == "Goal 'goal3' completed."  # type: ignore

    # Test completing a non-existent goal
    result_no_goal = await client.call_tool("mark_goals", {"goal_ids": ["nonexistent"]})
    assert result_no_goal[0].text == "Goal 'nonexistent' not found."  # type: ignore

    # Test marking goals as incomplete
    result_incomplete = await client.call_tool(
        "mark_goals", {"goal_ids": ["goal1"], "completed": False}
    )
    assert "Goal 'goal1' marked as incomplete" in result_incomplete[0].text  # type: ignore


@pytest.mark.asyncio
async def test_plan_for_goal(client: Client) -> None:
    """Tests the plan_for_goal tool logic."""
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal1", "description": "Goal 1"}]}
    )
    await client.call_tool(
        "set_goals",
        {"goals": [{"id": "goal2", "description": "Goal 2", "steps": ["goal1"]}]},
    )

    # The steps for goal2 should be goal1, then goal2
    result = await client.call_tool("plan_for_goal", {"goal_id": "goal2"})
    result_text = result[0].text  # type: ignore
    data = json.loads(result_text)
    assert "plan" in data
    assert "diagram" in data
    steps = data["plan"]
    diagram = data["diagram"]

    assert steps == [
        "Complete goal: 'goal1' - Goal 1",
        "Complete goal: 'goal2' - Goal 2",
    ]

    assert "graph TD" in diagram
    assert 'goal1["goal1: Goal 1"]' in diagram
    assert 'goal2["goal2: Goal 2"]' in diagram
    assert "goal1 --> goal2" in diagram

    # Complete goal1, so only goal2 should be left
    await client.call_tool("mark_goals", {"goal_ids": ["goal1"]})
    result_unblocked = await client.call_tool("plan_for_goal", {"goal_id": "goal2"})
    result_unblocked_text = result_unblocked[0].text  # type: ignore
    data_unblocked = json.loads(result_unblocked_text)
    steps_unblocked = data_unblocked["plan"]
    diagram_unblocked = data_unblocked["diagram"]
    assert steps_unblocked == ["Complete goal: 'goal2' - Goal 2"]
    assert 'goal1["goal1: Goal 1 <br/> (Completed)"]' in diagram_unblocked

    # Complete goal2, no steps should be left
    await client.call_tool("mark_goals", {"goal_ids": ["goal2"]})
    result_complete = await client.call_tool("plan_for_goal", {"goal_id": "goal2"})
    result_complete_text = result_complete[0].text  # type: ignore
    data_complete = json.loads(result_complete_text)
    steps_complete = data_complete["plan"]
    assert steps_complete == ["Goal 'goal2' is already completed."]


@pytest.mark.asyncio
async def test_plan_for_goal_no_steps(client: Client) -> None:
    """Tests that a goal with no steps is its own step."""
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal_simple", "description": "Simple Goal"}]}
    )
    result = await client.call_tool("plan_for_goal", {"goal_id": "goal_simple"})
    result_text = result[0].text  # type: ignore
    data = json.loads(result_text)
    steps = data["plan"]
    diagram = data["diagram"]
    assert steps == ["Complete goal: 'goal_simple' - Simple Goal"]
    assert "graph TD" in diagram
    assert 'goal_simple["goal_simple: Simple Goal"]' in diagram


@pytest.mark.asyncio
async def test_plan_for_goal_max_steps(client: Client) -> None:
    """Tests the max_steps parameter of plan_for_goal."""
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal1", "description": "Goal 1"}]}
    )
    await client.call_tool(
        "set_goals",
        {"goals": [{"id": "goal2", "description": "Goal 2", "steps": ["goal1"]}]},
    )

    result = await client.call_tool(
        "plan_for_goal", {"goal_id": "goal2", "max_steps": 1}
    )
    result_text = result[0].text  # type: ignore
    data = json.loads(result_text)
    steps = data["plan"]
    assert steps == ["Complete goal: 'goal1' - Goal 1"]


@pytest.mark.asyncio
async def test_plan_for_goal_missing_definition(client: Client) -> None:
    """
    Tests that plan_for_goal correctly identifies a missing step goal definition.
    """
    await client.call_tool(
        "set_goals",
        {
            "goals": [
                {"id": "top_goal", "description": "Top", "steps": ["missing_goal"]}
            ]
        },
    )
    result = await client.call_tool("plan_for_goal", {"goal_id": "top_goal"})
    result_text = result[0].text  # type: ignore
    data = json.loads(result_text)
    steps = data["plan"]
    diagram = data["diagram"]
    assert steps == [
        "Define missing step goal: 'missing_goal'",
        "Complete steps for goal: 'missing_goal'",
        "Complete goal: 'missing_goal' - Details to be determined.",
        "Complete goal: 'top_goal' - Top",
    ]
    assert "graph TD" in diagram
    assert 'missing_goal["missing_goal (undefined)"]' in diagram
    assert 'top_goal["top_goal: Top"]' in diagram
    assert "missing_goal --> top_goal" in diagram

    # Test with multiple missing goals
    await client.call_tool(
        "set_goals",
        {
            "goals": [
                {
                    "id": "top_goal_2",
                    "description": "Top 2",
                    "steps": ["missing_goal_1", "missing_goal_2"],
                }
            ]
        },
    )
    result2 = await client.call_tool("plan_for_goal", {"goal_id": "top_goal_2"})
    result2_text = result2[0].text  # type: ignore
    data2 = json.loads(result2_text)
    steps2 = data2["plan"]
    assert len(steps2) == 7  # 2 missing goals * 3 steps each + 1 for top_goal_2


@pytest.mark.asyncio
async def test_assess_goal(client: Client) -> None:
    """Tests the assess_goal tool."""
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal1", "description": "Goal 1"}]}
    )
    await client.call_tool(
        "set_goals",
        {"goals": [{"id": "goal2", "description": "Goal 2", "steps": ["goal1"]}]},
    )

    # Test assessing a goal with incomplete steps
    result = await client.call_tool("assess_goal", {"goal_id": "goal2"})
    assert "incomplete" in result[0].text  # type: ignore
    assert "goal1" in result[0].text  # type: ignore

    # Test assessing a goal with all steps complete
    await client.call_tool("mark_goals", {"goal_ids": ["goal1"]})
    result_ready = await client.call_tool("assess_goal", {"goal_id": "goal2"})
    assert "ready" in result_ready[0].text  # type: ignore

    # Test assessing a completed goal
    await client.call_tool("mark_goals", {"goal_ids": ["goal2"]})
    result_complete = await client.call_tool("assess_goal", {"goal_id": "goal2"})
    assert "complete" in result_complete[0].text  # type: ignore

    # Test assessing a goal with undefined steps
    await client.call_tool(
        "set_goals",
        {
            "goals": [
                {"id": "goal3", "description": "Goal 3", "steps": ["undefined_goal"]}
            ]
        },
    )
    result_undefined = await client.call_tool("assess_goal", {"goal_id": "goal3"})
    assert "undefined" in result_undefined[0].text  # type: ignore
    assert "undefined_goal" in result_undefined[0].text  # type: ignore


@pytest.mark.asyncio
async def test_add_steps(client: Client) -> None:
    """Tests the add_steps tool."""
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal1", "description": "Goal 1"}]}
    )
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal2", "description": "Goal 2"}]}
    )

    # Test adding a step to a goal
    result = await client.call_tool("add_steps", {"goal_steps": {"goal2": ["goal1"]}})
    assert "Added steps goal1 to goal 'goal2'" in result[0].text  # type: ignore

    # Test adding the same step again
    result_duplicate = await client.call_tool(
        "add_steps", {"goal_steps": {"goal2": ["goal1"]}}
    )
    assert "Step 'goal1' already exists for goal 'goal2'" in result_duplicate[0].text  # type: ignore

    # Test adding a step to a non-existent goal
    result_no_goal = await client.call_tool(
        "add_steps", {"goal_steps": {"nonexistent": ["goal1"]}}
    )
    assert "Goal 'nonexistent' not found" in result_no_goal[0].text  # type: ignore

    # Test adding a step that would create a deadlock
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal3", "description": "Goal 3"}]}
    )
    await client.call_tool("add_steps", {"goal_steps": {"goal3": ["goal2"]}})
    result_deadlock = await client.call_tool(
        "add_steps", {"goal_steps": {"goal1": ["goal3"]}}
    )
    assert "deadlock" in result_deadlock[0].text  # type: ignore

    # Test adding a goal to itself
    result_self = await client.call_tool(
        "add_steps", {"goal_steps": {"goal1": ["goal1"]}}
    )
    assert "cannot have itself as a step" in result_self[0].text  # type: ignore

    # Test adding different steps to different goals
    await client.call_tool(
        "set_goals", {"goals": [{"id": "step1", "description": "Step 1"}]}
    )
    await client.call_tool(
        "set_goals", {"goals": [{"id": "step2", "description": "Step 2"}]}
    )

    result_multi = await client.call_tool(
        "add_steps", {"goal_steps": {"goal1": ["step1"], "goal2": ["step2"]}}
    )
    assert "Added steps step1 to goal 'goal1'" in result_multi[0].text  # type: ignore
    assert "Added steps step2 to goal 'goal2'" in result_multi[0].text  # type: ignore


@pytest.mark.asyncio
async def test_full_workflow_with_goals(client: Client):
    """
    Tests the full workflow from goal creation to completion using the new model.
    """
    # 1. Define all goals with steps
    goals_to_add = [
        {"id": "toast_bread", "description": "Toast a slice of bread"},
        {"id": "boil_water", "description": "Boil water for tea"},
        {
            "id": "butter_toast",
            "description": "Butter the toast",
            "steps": ["toast_bread"],
        },
        {
            "id": "brew_tea",
            "description": "Brew a cup of tea",
            "steps": ["boil_water"],
        },
        {
            "id": "serve_breakfast",
            "description": "Serve the delicious breakfast",
            "steps": ["butter_toast", "brew_tea"],
        },
    ]

    await client.call_tool("set_goals", {"goals": goals_to_add})

    # 2. Check feasibility of the top-level goal
    feasibility_result = await client.call_tool(
        "assess_goal", {"goal_id": "serve_breakfast"}
    )
    assert "incomplete" in feasibility_result[0].text  # type: ignore

    # 3. Execute goals by following the plan_for_goal and mark_goals prompts
    # Start with the top-level goal to find the first action
    steps_result = await client.call_tool(
        "plan_for_goal", {"goal_id": "serve_breakfast"}
    )
    steps_text = steps_result[0].text  # type: ignore
    data = json.loads(steps_text)
    steps = data["plan"]

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
            await client.call_tool("mark_goals", {"goal_ids": [goal_id_to_complete]})

    # 4. Final check: All goals should now be complete.
    final_assessment = await client.call_tool(
        "assess_goal", {"goal_id": "serve_breakfast"}
    )
    assert "complete" in final_assessment[0].text  # type: ignore


@pytest.mark.asyncio
async def test_completion_with_multiple_dependents(client: Client):
    """Tests completing a goal with several dependents."""
    await client.call_tool(
        "set_goals", {"goals": [{"id": "base", "description": "Base Goal"}]}
    )
    await client.call_tool(
        "set_goals",
        {"goals": [{"id": "dep1", "description": "Dependent 1", "steps": ["base"]}]},
    )
    await client.call_tool(
        "set_goals",
        {"goals": [{"id": "dep2", "description": "Dependent 2", "steps": ["base"]}]},
    )

    result = await client.call_tool("mark_goals", {"goal_ids": ["base"]})
    # The order of dependents is not guaranteed, so check for both.
    assert "You may want to call plan_for_goal for" in result[0].text  # type: ignore
    assert "dep1" in result[0].text  # type: ignore
    assert "dep2" in result[0].text  # type: ignore


@pytest.mark.asyncio
async def test_plan_for_goal_no_diagram(client: Client):
    """Tests that plan_for_goal omits the diagram when include_diagram is False."""
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal1", "description": "Goal 1"}]}
    )
    await client.call_tool(
        "set_goals",
        {"goals": [{"id": "goal2", "description": "Goal 2", "steps": ["goal1"]}]},
    )
    result = await client.call_tool(
        "plan_for_goal", {"goal_id": "goal2", "include_diagram": False}
    )
    result_text = result[0].text  # type: ignore
    data = json.loads(result_text)
    steps = data["plan"]
    diagram = data["diagram"]
    assert steps == [
        "Complete goal: 'goal1' - Goal 1",
        "Complete goal: 'goal2' - Goal 2",
    ]
    assert diagram == ""


@pytest.mark.asyncio
async def test_set_goals(client: Client):
    """
    Tests the set_goals tool for batch and graph creation, cycle detection, and error
    handling.
    """
    # 1. Add a simple chain in one call
    chain = [
        {"id": "a", "description": "A"},
        {"id": "b", "description": "B", "steps": ["a"]},
        {"id": "c", "description": "C", "steps": ["b"]},
    ]
    result = await client.call_tool("set_goals", {"goals": chain})
    assert result[0].text == "Goals defined."  # type: ignore
    # Check that all goals exist
    for g in ["a", "b", "c"]:
        assess = await client.call_tool("assess_goal", {"goal_id": g})
        assert "well-defined" in assess[0].text or "ready" in assess[0].text  # type: ignore

    # 2. Add siblings with shared step
    siblings = [
        {"id": "d", "description": "D"},
        {"id": "e", "description": "E", "steps": ["d"]},
        {"id": "f", "description": "F", "steps": ["d"]},
    ]
    result = await client.call_tool("set_goals", {"goals": siblings})
    assert result[0].text == "Goals defined."  # type: ignore
    for g in ["d", "e", "f"]:
        assess = await client.call_tool("assess_goal", {"goal_id": g})
        assert "well-defined" in assess[0].text or "ready" in assess[0].text  # type: ignore

    # 3. Add a complex graph
    complex_graph = [
        {"id": "g", "description": "G"},
        {"id": "h", "description": "H", "steps": ["g", "e"]},
        {"id": "i", "description": "I", "steps": ["h", "f"]},
    ]
    result = await client.call_tool("set_goals", {"goals": complex_graph})
    assert result[0].text == "Goals defined."  # type: ignore
    for g in ["g", "h", "i"]:
        assess = await client.call_tool("assess_goal", {"goal_id": g})
        assert "well-defined" in assess[0].text or "ready" in assess[0].text  # type: ignore

    # 4. Cycle detection (should not add any goals)
    cycle = [
        {"id": "x", "description": "X", "steps": ["y"]},
        {"id": "y", "description": "Y", "steps": ["x"]},
    ]
    result = await client.call_tool("set_goals", {"goals": cycle})
    assert "Deadlock detected" in result[0].text  # type: ignore
    # x and y should not exist
    for g in ["x", "y"]:
        assess = await client.call_tool("assess_goal", {"goal_id": g})
        assert "not found" in assess[0].text  # type: ignore

    # 5. Undefined steps
    undefined = [
        {"id": "z", "description": "Z", "steps": ["not_defined"]},
    ]
    result = await client.call_tool("set_goals", {"goals": undefined})
    assert "undefined" in result[0].text  # type: ignore
    # z should exist, not_defined should not
    assess_z = await client.call_tool("assess_goal", {"goal_id": "z"})
    assert "undefined step goals: not_defined" in assess_z[0].text  # type: ignore


@pytest.mark.asyncio
async def test_set_goals_required_for(client: Client):
    """Tests the required_for attribute of set_goals."""
    # Test adding goals as steps to existing goals
    await client.call_tool(
        "set_goals", {"goals": [{"id": "parent", "description": "Parent Goal"}]}
    )

    result = await client.call_tool(
        "set_goals",
        {
            "goals": [
                {"id": "child1", "description": "Child 1", "required_for": ["parent"]},
                {"id": "child2", "description": "Child 2", "required_for": ["parent"]},
            ]
        },
    )
    assert result[0].text == "Goals defined."  # type: ignore

    # Check that parent now has both children as steps
    assess = await client.call_tool("assess_goal", {"goal_id": "parent"})
    assert "incomplete" in assess[0].text  # type: ignore
    assert "child1" in assess[0].text  # type: ignore
    assert "child2" in assess[0].text  # type: ignore

    # Test adding goals as steps to non-existent goals (should create them)
    result2 = await client.call_tool(
        "set_goals",
        {
            "goals": [
                {
                    "id": "new_child",
                    "description": "New Child",
                    "required_for": ["new_parent"],
                }
            ]
        },
    )
    assert result2[0].text == "Goals defined."  # type: ignore

    # Check that new_parent was created and has new_child as a step
    assess_new = await client.call_tool("assess_goal", {"goal_id": "new_parent"})
    assert "incomplete" in assess_new[0].text  # type: ignore
    assert "new_child" in assess_new[0].text  # type: ignore

    # Test multiple required_for relationships
    result3 = await client.call_tool(
        "set_goals",
        {
            "goals": [
                {
                    "id": "shared_step",
                    "description": "Shared Step",
                    "required_for": ["parent", "new_parent"],
                }
            ]
        },
    )
    assert result3[0].text == "Goals defined."  # type: ignore

    # Check that both parents now have shared_step as a step
    assess_parent = await client.call_tool("assess_goal", {"goal_id": "parent"})
    assess_new_parent = await client.call_tool("assess_goal", {"goal_id": "new_parent"})
    assert "shared_step" in assess_parent[0].text  # type: ignore
    assert "shared_step" in assess_new_parent[0].text  # type: ignore

    # Test deadlock detection with required_for relationships
    result4 = await client.call_tool(
        "set_goals",
        {
            "goals": [
                {
                    "id": "cycle_a",
                    "description": "Cycle A",
                    "required_for": ["cycle_b"],
                },
                {
                    "id": "cycle_b",
                    "description": "Cycle B",
                    "required_for": ["cycle_a"],
                },
            ]
        },
    )
    assert "Deadlock detected" in result4[0].text  # type: ignore
    assert "cycle_a" in result4[0].text  # type: ignore
    assert "cycle_b" in result4[0].text  # type: ignore

    # Verify that the cyclic goals were not added
    assess_a = await client.call_tool("assess_goal", {"goal_id": "cycle_a"})
    assess_b = await client.call_tool("assess_goal", {"goal_id": "cycle_b"})
    assert "not found" in assess_a[0].text  # type: ignore
    assert "not found" in assess_b[0].text  # type: ignore
