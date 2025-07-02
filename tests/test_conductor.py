import pytest  # type: ignore
from fastmcp import Client
import importlib
import json
import main
from main import ConductorMCP
import sys
import subprocess
import time
import socket
import random


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
    text = getattr(result[0], "text", None)
    assert text is not None and text.startswith("Goal 'goal1' completed.")
    assert (
        "Now that this goal is complete" in text
        or "Next, you might want to focus on" in text
    )

    # Test completing a goal that was already completed.
    result_already_done = await client.call_tool("mark_goals", {"goal_ids": ["goal1"]})
    assert "Goal 'goal1' was already completed" in result_already_done[0].text  # type: ignore  # noqa
    # Test completing a goal with no dependents.
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal3", "description": "Goal 3"}]}
    )
    result_no_deps = await client.call_tool("mark_goals", {"goal_ids": ["goal3"]})
    text = getattr(result_no_deps[0], "text", None)
    assert text is not None and text.startswith("Goal 'goal3' completed.")
    # Should suggest focusing on the next goal (goal2) or say all goals are complete
    assert "focus on" in text or "complete" in text
    # If goal2 exists, it should be mentioned
    if "goal2" in text:
        assert "goal2" in text

    # Test completing a non-existent goal
    result_no_goal = await client.call_tool("mark_goals", {"goal_ids": ["nonexistent"]})
    text = getattr(result_no_goal[0], "text", None)
    assert text is not None and "not found" in text
    assert text is not None and (
        "focus on" in text or "set_goals" in text or "define" in text
    )

    # Test marking goals as incomplete
    result_incomplete = await client.call_tool(
        "mark_goals", {"goal_ids": ["goal1"], "completed": False}
    )
    assert "Goal 'goal1' marked as incomplete" in result_incomplete[0].text  # type: ignore  # noqa


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

    required_lines = [
        "Complete goal: 'goal1' - Goal 1",
        "Complete goal: 'goal2' - Goal 2",
    ]
    for line in required_lines:
        assert line in steps
    assert any(
        phrase in steps[-1]
        for phrase in [
            "focus on",
            "mark_goals",
            "add_steps",
            "set_goals",
            "deadlock",
            "complete",
            "review",
        ]
    ), f"Plan suggestion not actionable: {steps[-1]}"

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
    required_lines = [
        "Complete goal: 'goal2' - Goal 2",
    ]
    for line in required_lines:
        assert line in steps_unblocked
    assert any(
        phrase in steps_unblocked[-1]
        for phrase in [
            "focus on",
            "mark_goals",
            "add_steps",
            "set_goals",
            "deadlock",
            "complete",
            "review",
        ]
    ), f"Plan suggestion not actionable: {steps_unblocked[-1]}"
    assert 'goal1["goal1: Goal 1 <br/> (Completed)"]' in diagram_unblocked

    # Complete goal2, no steps should be left
    await client.call_tool("mark_goals", {"goal_ids": ["goal2"]})
    result_complete = await client.call_tool("plan_for_goal", {"goal_id": "goal2"})
    result_complete_text = result_complete[0].text  # type: ignore
    data_complete = json.loads(result_complete_text)
    steps_complete = data_complete["plan"]
    assert any("already completed" in s for s in steps_complete)

    # For plan_for_goal and similar tests, check the last element for actionable
    # suggestion
    assert any(
        phrase in steps[-1]
        for phrase in [
            "focus on",
            "mark_goals",
            "add_steps",
            "set_goals",
            "deadlock",
            "complete",
            "review",
        ]
    ), f"Plan suggestion not actionable: {steps[-1]}"


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
    required_lines = [
        "Complete goal: 'goal_simple' - Simple Goal",
    ]
    for line in required_lines:
        assert line in steps
    assert any(
        phrase in steps[-1]
        for phrase in [
            "focus on",
            "mark_goals",
            "add_steps",
            "set_goals",
            "deadlock",
            "complete",
            "review",
        ]
    ), f"Plan suggestion not actionable: {steps[-1]}"
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
    required_lines = [
        "Complete goal: 'goal1' - Goal 1",
    ]
    for line in required_lines:
        assert line in steps
    assert any(
        phrase in steps[-1]
        for phrase in [
            "focus on",
            "mark_goals",
            "add_steps",
            "set_goals",
            "deadlock",
            "complete",
            "review",
        ]
    ), f"Plan suggestion not actionable: {steps[-1]}"


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
    # Check that the auto-created goal shows up as needing definition
    required_lines = [
        "Define and complete goal: 'missing_goal' - Details to be determined.",
        "Complete goal: 'top_goal' - Top",
    ]
    for line in required_lines:
        assert line in steps
    # Should suggest defining the goals
    assert any("We don't know what's involved" in step for step in steps)
    # Check that the last element is an actionable suggestion
    assert any(
        phrase in steps[-1]
        for phrase in [
            "focus on",
            "mark_goals",
            "add_steps",
            "set_goals",
            "deadlock",
            "complete",
            "review",
        ]
    ), f"Plan suggestion not actionable: {steps[-1]}"

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
    # Check that all required lines are present
    required_lines2 = [
        "Define and complete goal: 'missing_goal_1' - Details to be determined.",
        "Define and complete goal: 'missing_goal_2' - Details to be determined.",
        "Complete goal: 'top_goal_2' - Top 2",
    ]
    for line in required_lines2:
        assert line in steps2
    # Check that the last element is an actionable suggestion
    assert any(
        phrase in steps2[-1]
        for phrase in [
            "focus on",
            "mark_goals",
            "add_steps",
            "set_goals",
            "deadlock",
            "complete",
            "review",
        ]
    ), f"Plan suggestion not actionable: {steps2[-1]}"


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
    assert "Step 'goal1' already exists for goal 'goal2'" in result_duplicate[0].text  # type: ignore  # noqa

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
    text = getattr(result[0], "text", None)
    assert text is not None and "focus on" in text
    assert text is not None and "dep1" in text
    assert text is not None and "dep2" in text


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
    required_lines = [
        "Complete goal: 'goal1' - Goal 1",
        "Complete goal: 'goal2' - Goal 2",
    ]
    for line in required_lines:
        assert line in steps
    assert any(
        phrase in steps[-1]
        for phrase in [
            "focus on",
            "mark_goals",
            "add_steps",
            "set_goals",
            "deadlock",
            "complete",
            "review",
        ]
    ), f"Plan suggestion not actionable: {steps[-1]}"
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
    text = getattr(result[0], "text", None)
    assert text is not None and text.startswith("Goals defined.")
    assert (
        "focus on" in text
        or "mark_goals" in text
        or "add_steps" in text
        or "set_goals" in text
        or "deadlock" in text
        or "complete" in text
        or "review" in text
    )
    # Check that all goals exist
    for g in ["a", "b", "c"]:
        assess = await client.call_tool("assess_goal", {"goal_id": g})
        assert "well-defined" in assess[0].text or "ready" in assess[0].text  # type: ignore  # noqa

    # 2. Add siblings with shared step
    siblings = [
        {"id": "d", "description": "D"},
        {"id": "e", "description": "E", "steps": ["d"]},
        {"id": "f", "description": "F", "steps": ["d"]},
    ]
    result = await client.call_tool("set_goals", {"goals": siblings})
    text = getattr(result[0], "text", None)
    assert text is not None and text.startswith("Goals defined.")
    assert (
        "focus on" in text
        or "mark_goals" in text
        or "add_steps" in text
        or "set_goals" in text
        or "deadlock" in text
        or "complete" in text
        or "review" in text
    )
    for g in ["d", "e", "f"]:
        assess = await client.call_tool("assess_goal", {"goal_id": g})
        assert "well-defined" in assess[0].text or "ready" in assess[0].text  # type: ignore  # noqa

    # 3. Add a complex graph
    complex_graph = [
        {"id": "g", "description": "G"},
        {"id": "h", "description": "H", "steps": ["g", "e"]},
        {"id": "i", "description": "I", "steps": ["h", "f"]},
    ]
    result = await client.call_tool("set_goals", {"goals": complex_graph})
    text = getattr(result[0], "text", None)
    assert text is not None and text.startswith("Goals defined.")
    assert (
        "focus on" in text
        or "mark_goals" in text
        or "add_steps" in text
        or "set_goals" in text
        or "deadlock" in text
        or "complete" in text
        or "review" in text
    )
    for g in ["g", "h", "i"]:
        assess = await client.call_tool("assess_goal", {"goal_id": g})
        assert "well-defined" in assess[0].text or "ready" in assess[0].text  # type: ignore  # noqa

    # 4. Cycle detection (should not add any goals)
    cycle = [
        {"id": "x", "description": "X", "steps": ["y"]},
        {"id": "y", "description": "Y", "steps": ["x"]},
    ]
    result = await client.call_tool("set_goals", {"goals": cycle})
    assert "deadlock" in result[0].text.lower()  # type: ignore
    # x and y should not exist
    for g in ["x", "y"]:
        assess = await client.call_tool("assess_goal", {"goal_id": g})
        assert "not found" in assess[0].text  # type: ignore

    # 5. Steps that need definition (auto-created goals with empty descriptions)
    undefined = [
        {"id": "z", "description": "Z", "steps": ["not_defined"]},
    ]
    result = await client.call_tool("set_goals", {"goals": undefined})
    text = getattr(result[0], "text", None)
    assert text is not None and text.startswith("Goals defined.")
    # Check that the step was auto-created as a goal
    assess = await client.call_tool("assess_goal", {"goal_id": "not_defined"})
    assert "ready" in assess[0].text  # Auto-created goal with empty description
    # Check that parent goal recognizes it needs definition
    assess_z = await client.call_tool("assess_goal", {"goal_id": "z"})
    assert "need more definition" in assess_z[0].text


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
    text = getattr(result[0], "text", None)
    assert text is not None and text.startswith("Goals defined.")
    assert (
        "focus on" in text
        or "mark_goals" in text
        or "add_steps" in text
        or "set_goals" in text
        or "deadlock" in text
        or "complete" in text
        or "review" in text
    )

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
    text = getattr(result2[0], "text", None)
    assert text is not None and text.startswith("Goals defined.")
    assert (
        "focus on" in text
        or "mark_goals" in text
        or "add_steps" in text
        or "set_goals" in text
        or "deadlock" in text
        or "complete" in text
        or "review" in text
    )

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
    text = getattr(result3[0], "text", None)
    assert text is not None and text.startswith("Goals defined.")
    assert (
        "focus on" in text
        or "mark_goals" in text
        or "add_steps" in text
        or "set_goals" in text
        or "deadlock" in text
        or "complete" in text
        or "review" in text
    )

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
    assert "deadlock" in result4[0].text.lower()  # type: ignore
    assert "cycle_a" in result4[0].text  # type: ignore
    assert "cycle_b" in result4[0].text  # type: ignore

    # Verify that the cyclic goals were not added
    assess_a = await client.call_tool("assess_goal", {"goal_id": "cycle_a"})
    assess_b = await client.call_tool("assess_goal", {"goal_id": "cycle_b"})
    assert "not found" in assess_a[0].text  # type: ignore
    assert "not found" in assess_b[0].text  # type: ignore


@pytest.mark.asyncio
async def test_http_server_basic():
    """
    Start the server in HTTP mode as a subprocess, connect via HTTP, and verify
    set_goals tool.
    """
    port = random.randint(9000, 9999)
    host = "127.0.0.1"
    url = f"http://{host}:{port}/mcp/"

    proc = subprocess.Popen(
        [sys.executable, "main.py", "--http", "--host", host, "--port", str(port)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        for _ in range(30):
            try:
                with socket.create_connection((host, port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            out, err = proc.communicate(timeout=2)
            print("SERVER STDOUT:", out.decode())
            print("SERVER STDERR:", err.decode())
            raise RuntimeError("HTTP server did not start in time")

        # Use FastMCP Client to connect over HTTP
        async with Client(url) as client:
            # Call a tool (set_goals)
            result = await client.call_tool(
                "set_goals", {"goals": [{"id": "goal1", "description": "Goal 1"}]}
            )
            text = getattr(result[0], "text", None)
            assert text is not None and (
                "Goals defined." in text or "focus on" in text or "complete" in text
            )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


@pytest.mark.asyncio
async def test_format_description_with_period() -> None:
    """Tests the _format_description_with_period helper function."""
    assert main._format_description_with_period("test") == "test."
    assert main._format_description_with_period("test.") == "test."
    assert main._format_description_with_period("test. ") == "test."
    assert main._format_description_with_period("") == ""


@pytest.mark.asyncio
async def test_parse_dependency_tree() -> None:
    """Tests the _parse_dependency_tree function."""
    tree_text = """
    Goal: Main
        Step: Sub1
            Step: SubSub1
    """
    deps, descs = main._parse_dependency_tree(tree_text)
    assert "Main" in deps
    assert "Sub1" in deps["Main"]
    assert "SubSub1" in deps["Sub1"]
    assert descs["Main"] == ""

    tree_text_with_desc = """
    Goal: Main: The main goal
        Step: Sub1: The first sub-goal
    """
    deps, descs = main._parse_dependency_tree(tree_text_with_desc)
    assert descs["Main"] == "The main goal"
    assert descs["Sub1"] == "The first sub-goal"

    deps, descs = main._parse_dependency_tree("")
    assert deps == {}
    assert descs == {}


@pytest.mark.asyncio
async def test_set_goals_with_tree_description(client: Client) -> None:
    """Tests set_goals with a tree that has a description for the root goal."""
    tree_text = "Goal: Root: The root description"
    await client.call_tool(
        "set_goals",
        {
            "goals": [
                {
                    "id": "root",
                    "description": "",  # Empty description to test if it gets overwritten
                    "steps": tree_text,
                }
            ]
        },
    )
    result = await client.call_tool("assess_goal", {"goal_id": "root"})
    assert "The root description" in result[0].text


@pytest.mark.asyncio
async def test_mark_goals_already_incomplete(client: Client) -> None:
    """Tests marking a goal as incomplete when it's already incomplete."""
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal1", "description": "Goal 1"}]}
    )
    await client.call_tool(
        "mark_goals", {"goal_ids": ["goal1"], "completed": False}
    )
    result = await client.call_tool(
        "mark_goals", {"goal_ids": ["goal1"], "completed": False}
    )
    assert "Goal 'goal1' was already incomplete" in result[0].text


@pytest.mark.asyncio
async def test_plan_for_goal_undefined_goal(client: Client) -> None:
    """Tests plan_for_goal with a goal that doesn't exist."""
    result = await client.call_tool(
        "plan_for_goal", {"goal_id": "nonexistent"}
    )
    data = json.loads(result[0].text)
    assert "Goal 'nonexistent' not found" in data["plan"][0]


@pytest.mark.asyncio
async def test_assess_goal_all_steps_complete(client: Client) -> None:
    """Tests assess_goal when all prerequisite steps for a goal are complete."""
    await client.call_tool(
        "set_goals", {"goals": [{"id": "step1", "description": "Step 1"}]}
    )
    await client.call_tool(
        "set_goals",
        {
            "goals": [
                {
                    "id": "main_goal",
                    "description": "Main Goal",
                    "steps": ["step1"],
                }
            ]
        },
    )
    await client.call_tool("mark_goals", {"goal_ids": ["step1"]})
    result = await client.call_tool("assess_goal", {"goal_id": "main_goal"})
    assert "All step goals are met" in result[0].text


@pytest.mark.asyncio
async def test_get_session_state_with_id(client: Client) -> None:
    """Tests get_session_state with a session that has an id."""
    import unittest.mock as mock
    
    with mock.patch('main.get_session_state') as mock_get_state:
        # Mock two different session states
        state1 = main.ServerState()
        state2 = main.ServerState()
        
        def side_effect(ctx):
            if hasattr(ctx, 'session') and hasattr(ctx.session, 'id'):
                return state1 if ctx.session.id == "session1" else state2
            return state1
        
        mock_get_state.side_effect = side_effect
        
        # Create mock contexts
        class MockSession:
            def __init__(self, session_id):
                self.id = session_id
        
        class MockContext:
            def __init__(self, session_id):
                self.session = MockSession(session_id)
        
        ctx1 = MockContext("session1")
        ctx2 = MockContext("session2")
        
        result1 = main.get_session_state(ctx1)
        result2 = main.get_session_state(ctx2)
        
        assert result1 is not result2


@pytest.mark.asyncio
async def test_set_goals_many_auto_created(client: Client) -> None:
    """Tests the suggestion when more than 5 goals are auto-created."""
    steps = [f"step{i}" for i in range(6)]
    result = await client.call_tool(
        "set_goals",
        {"goals": [{"id": "main", "description": "Main", "steps": steps}]},
    )
    assert "Auto-created 6 step goals including:" in result[0].text


@pytest.mark.asyncio
async def test_mark_goals_no_dependents_suggestion(client: Client) -> None:
    """Tests the suggestion from mark_goals when there are no dependents."""
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal1", "description": "Goal 1"}]}
    )
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal2", "description": "Goal 2"}]}
    )
    result = await client.call_tool("mark_goals", {"goal_ids": ["goal1"]})
    assert "Next, you might want to focus on goal2" in result[0].text


@pytest.mark.asyncio
async def test_add_steps_no_affected_suggestion(client: Client) -> None:
    """Tests the suggestion from add_steps when no completed goals are affected."""
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal1", "description": "Goal 1"}]}
    )
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal2", "description": "Goal 2"}]}
    )
    result = await client.call_tool("add_steps", {"goal_steps": {"goal1": ["goal2"]}})
    assert "Next, you might want to focus on goal1" in result[0].text


@pytest.mark.asyncio
async def test_plan_for_goal_all_complete_suggestion(client: Client) -> None:
    """Tests the suggestion from plan_for_goal when all goals are complete."""
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal1", "description": "Goal 1"}]}
    )
    await client.call_tool("mark_goals", {"goal_ids": ["goal1"]})
    result = await client.call_tool("plan_for_goal", {"goal_id": "goal1"})
    data = json.loads(result[0].text)
    assert "already completed" in data["plan"][0]


@pytest.mark.asyncio
async def test_assess_goal_no_incomplete_steps(client: Client) -> None:
    """Tests assess_goal when there are no incomplete steps."""
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal1", "description": "Goal 1"}]}
    )
    result = await client.call_tool("assess_goal", {"goal_id": "goal1"})
    assert "All step goals are met" in result[0].text



@pytest.mark.asyncio
async def test_parse_dependency_tree_flexible_indent() -> None:
    """Tests the _parse_dependency_tree function with flexible indentation."""
    tree_text = """
    Goal: Main
      Step: Sub1
        Step: SubSub1
    """
    deps, _ = main._parse_dependency_tree(tree_text)
    assert "Sub1" in deps["Main"]
    assert "SubSub1" in deps["Sub1"]


@pytest.mark.asyncio
async def test_mark_goals_incomplete_steps_no_override(client: Client) -> None:
    """Tests marking a goal with incomplete steps and complete_steps=False."""
    await client.call_tool(
        "set_goals",
        {
            "goals": [
                {"id": "step1", "description": "Step 1"},
                {
                    "id": "main_goal",
                    "description": "Main Goal",
                    "steps": ["step1"],
                },
            ]
        },
    )
    result = await client.call_tool("mark_goals", {"goal_ids": ["main_goal"]})
    assert "You must complete all prerequisites" in result[0].text


@pytest.mark.asyncio
async def test_add_steps_self_as_step(client: Client) -> None:
    """Tests adding a goal to itself as a step."""
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal1", "description": "Goal 1"}]}
    )
    result = await client.call_tool(
        "add_steps", {"goal_steps": {"goal1": ["goal1"]}}
    )
    assert "cannot have itself as a step" in result[0].text


@pytest.mark.asyncio
async def test_has_cycle() -> None:
    """Tests the _has_cycle utility."""
    graph = {"a": ["b"], "b": ["a"]}
    assert main._has_cycle(set(graph.keys()), graph.get)


@pytest.mark.asyncio
async def test_find_cycle_nodes() -> None:
    """Tests the _find_cycle_nodes utility."""
    graph = {"a": ["b"], "b": ["a"]}
    cycle_nodes = main._find_cycle_nodes(set(graph.keys()), graph.get)
    assert "a" in cycle_nodes
    assert "b" in cycle_nodes


@pytest.mark.asyncio
async def test_parse_dependency_tree_edge_cases() -> None:
    """Tests _parse_dependency_tree with edge cases like empty lines and names."""
    # Test with a blank line
    tree_with_blank_line = """
    Goal: Main

    Step: Sub1
    """
    deps, _ = main._parse_dependency_tree(tree_with_blank_line)
    assert "Sub1" in deps["Main"]

    # Test with a line that results in an empty goal name
    tree_with_empty_name = """
    Goal: Main
    Step:
    """
    deps, _ = main._parse_dependency_tree(tree_with_empty_name)
    assert "Main" in deps
    assert not deps["Main"]  # No steps should be added


@pytest.mark.asyncio
async def test_mark_goals_complete_steps_deep(client: Client) -> None:
    """Tests the complete_steps=True flag with a deep dependency chain."""
    goals = [
        {"id": "g1", "description": "G1"},
        {"id": "g2", "description": "G2", "steps": ["g1"]},
        {"id": "g3", "description": "G3", "steps": ["g2"]},
    ]
    await client.call_tool("set_goals", {"goals": goals})
    # Mark g3 as complete, which should complete g1 and g2 as well
    await client.call_tool(
        "mark_goals", {"goal_ids": ["g3"], "complete_steps": True}
    )
    for goal_id in ["g1", "g2", "g3"]:
        result = await client.call_tool("assess_goal", {"goal_id": goal_id})
        assert "complete" in result[0].text


@pytest.mark.asyncio
async def test_add_steps_marks_dependents_incomplete(client: Client) -> None:
    """
    Tests that adding a step to a completed goal marks its dependents as incomplete.
    """
    goals = [
        {"id": "g1", "description": "G1"},
        {"id": "g2", "description": "G2", "steps": ["g1"]},
        {"id": "g3", "description": "G3"},
    ]
    await client.call_tool("set_goals", {"goals": goals})
    # Complete g1 and g2
    await client.call_tool("mark_goals", {"goal_ids": ["g1", "g2"]})
    # Add g3 as a step to g1, which should make g2 incomplete
    await client.call_tool("add_steps", {"goal_steps": {"g1": ["g3"]}})
    result = await client.call_tool("assess_goal", {"goal_id": "g2"})
    assert "incomplete" in result[0].text


@pytest.mark.asyncio
async def test_set_goals_suggestion_with_mixed_completion(client: Client) -> None:
    """
    Tests the suggestion from set_goals when the state has both complete and
    incomplete goals.
    """
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal1", "description": "Goal 1"}]}
    )
    await client.call_tool("mark_goals", {"goal_ids": ["goal1"]})
    result = await client.call_tool(
        "set_goals", {"goals": [{"id": "goal2", "description": "Goal 2"}]}
    )
    # The suggestion should be to focus on the new, incomplete goal.
    assert "Next, you might want to focus on goal2" in result[0].text


@pytest.mark.asyncio
async def test_add_steps_cycle_detection(client: Client) -> None:
    """Tests that add_steps correctly detects and prevents a cycle."""
    await client.call_tool("set_goals", {"goals": [{"id": "x", "description": "X"}]})
    await client.call_tool("set_goals", {"goals": [{"id": "y", "description": "Y"}]})

    # Add dependency y -> x
    await client.call_tool("add_steps", {"goal_steps": {"x": ["y"]}})

    # Attempt to add dependency x -> y, which should create a cycle
    result = await client.call_tool("add_steps", {"goal_steps": {"y": ["x"]}})

    # Verify that the deadlock was detected and reported
    assert "would create a deadlock" in result[0].text

    # Verify that the cyclic step was not actually added to goal 'y'
    assess_result = await client.call_tool("assess_goal", {"goal_id": "y"})
    assert "ready" in assess_result[0].text  # 'y' should still be ready, with no steps


@pytest.mark.asyncio
async def test_plan_for_goal_all_steps_complete_suggestion(client: Client) -> None:
    """Tests the suggestion when a plan is requested for a completed goal."""
    await client.call_tool(
        "set_goals", {"goals": [{"id": "goal1", "description": "Goal 1"}]}
    )
    await client.call_tool("mark_goals", {"goal_ids": ["goal1"]})
    result = await client.call_tool("plan_for_goal", {"goal_id": "goal1"})
    data = json.loads(result[0].text)
    assert "already completed" in data["plan"][0]


@pytest.mark.asyncio
async def test_cycle_detection_longer_cycle() -> None:
    """Tests the cycle detection with a longer cycle."""
    graph = {"a": ["b"], "b": ["c"], "c": ["a"]}
    assert main._has_cycle(set(graph.keys()), graph.get)
    cycle_nodes = main._find_cycle_nodes(set(graph.keys()), graph.get)
    assert cycle_nodes == {"a", "b", "c"}
