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
async def test_add_objective(client: Client):
    """Tests the add_objective tool for success and failure cases."""
    # Test adding a new objective
    result = await client.call_tool("add_objective", {"id": "obj1", "description": "Test Objective"})
    assert result[0].text == "Objective 'obj1' added."  # type: ignore

    # Test adding an objective that already exists
    result_exists = await client.call_tool("add_objective", {"id": "obj1", "description": "Duplicate Objective"})
    assert result_exists[0].text == "Objective 'obj1' already exists."  # type: ignore

@pytest.mark.asyncio
async def test_add_task(client: Client):
    """Tests the add_task tool for success and various failure cases."""
    await client.call_tool("add_objective", {"id": "obj1", "description": "Test Objective"})

    # Test adding a valid task
    result = await client.call_tool("add_task", {"id": "task1", "description": "Test Task", "objective_id": "obj1"})
    assert result[0].text == "Task 'task1' added to objective 'obj1'."  # type: ignore

    # Test adding a task that already exists
    result_exists = await client.call_tool("add_task", {"id": "task1", "description": "Duplicate Task", "objective_id": "obj1"})
    assert result_exists[0].text == "Task 'task1' already exists."  # type: ignore

    # Test adding a task to a non-existent objective
    result_no_obj = await client.call_tool("add_task", {"id": "task2", "description": "Another Task", "objective_id": "nonexistent"})
    assert result_no_obj[0].text == "Objective 'nonexistent' not found."  # type: ignore

    # Test adding a task with a missing dependency is allowed
    result_missing_dep = await client.call_tool("add_task", {
        "id": "task3",
        "description": "Task with missing dep",
        "objective_id": "obj1",
        "dependencies": ["missing_task"]
    })
    assert result_missing_dep[0].text == "Task 'task3' added to objective 'obj1'."  # type: ignore

    # Test adding a task that would create a direct circular dependency (A -> A)
    result_self_cycle = await client.call_tool("add_task", {
        "id": "task4",
        "description": "Self-referential task",
        "objective_id": "obj1",
        "dependencies": ["task4"]
    })
    assert "circular dependency" in result_self_cycle[0].text  # type: ignore

    # Test adding a task that would create an indirect circular dependency (A -> B -> A)
    await client.call_tool("add_task", {"id": "taskA", "description": "Task A", "objective_id": "obj1", "dependencies": ["taskB"]})
    result_indirect_cycle = await client.call_tool("add_task", {
        "id": "taskB",
        "description": "Task B",
        "objective_id": "obj1",
        "dependencies": ["taskA"]
    })
    assert "circular dependency" in result_indirect_cycle[0].text  # type: ignore

@pytest.mark.asyncio
async def test_complete_task(client: Client):
    """Tests the complete_task tool."""
    await client.call_tool("add_objective", {"id": "obj1", "description": "Test Objective"})
    await client.call_tool("add_task", {"id": "task1", "description": "Test Task", "objective_id": "obj1"})

    # Test completing an existing task
    result = await client.call_tool("complete_task", {"task_id": "task1"})
    assert result[0].text == "Task 'task1' marked as completed."  # type: ignore

    # Test completing a non-existent task
    result_no_task = await client.call_tool("complete_task", {"task_id": "nonexistent"})
    assert result_no_task[0].text == "Task 'nonexistent' not found."  # type: ignore

@pytest.mark.asyncio
async def test_get_next_task(client: Client):
    """Tests the get_next_task tool logic."""
    await client.call_tool("add_objective", {"id": "obj1", "description": "Test Objective"})
    await client.call_tool("add_task", {"id": "task1", "description": "Task 1", "objective_id": "obj1"})
    await client.call_tool("add_task", {"id": "task2", "description": "Task 2", "objective_id": "obj1", "dependencies": ["task1"]})

    # The first available task should be task1
    result = await client.call_tool("get_next_task", {"objective_id": "obj1"})
    assert result[0].text == "Next task for objective 'obj1': task1 - Task 1"  # type: ignore

    # Complete task1, making task2 available
    await client.call_tool("complete_task", {"task_id": "task1"})
    result_unblocked = await client.call_tool("get_next_task", {"objective_id": "obj1"})
    assert result_unblocked[0].text == "Next task for objective 'obj1': task2 - Task 2"  # type: ignore

    # Complete task2, no tasks should be left
    await client.call_tool("complete_task", {"task_id": "task2"})
    result_complete = await client.call_tool("get_next_task", {"objective_id": "obj1"})
    assert result_complete[0].text == "Objective 'obj1' is completed. All tasks are done."  # type: ignore

@pytest.mark.asyncio
async def test_get_next_task_no_tasks(client: Client):
    """Tests that an objective with no tasks is considered complete."""
    await client.call_tool("add_objective", {"id": "obj_no_tasks", "description": "Objective without tasks"})
    result = await client.call_tool("get_next_task", {"objective_id": "obj_no_tasks"})
    assert result[0].text == "Objective 'obj_no_tasks' is completed. All tasks are done."  # type: ignore

@pytest.mark.asyncio
async def test_get_next_task_blocked(client: Client):
    """Tests that get_next_task correctly identifies a missing dependency."""
    await client.call_tool("add_objective", {"id": "obj1", "description": "Test Objective"})
    await client.call_tool("add_task", {"id": "task1", "description": "Task 1", "objective_id": "obj1", "dependencies": ["missing_def"]})

    # The tool should immediately report the missing definition.
    result = await client.call_tool("get_next_task", {"objective_id": "obj1"})
    expected_text = (
        "Objective 'obj1' is blocked. "
        "Please define the task for dependency 'missing_def'."
    )
    assert result[0].text == expected_text  # type: ignore

    # Add another task with a different missing dependency. The tool should still report the first one it finds.
    await client.call_tool("add_task", {"id": "task0", "description": "Task 0", "objective_id": "obj1", "dependencies": ["another_missing_def"]})
    
    # Re-run the check. The order of checking is not guaranteed, so we accept either missing dependency.
    result_rerun = await client.call_tool("get_next_task", {"objective_id": "obj1"})
    possible_outcomes = [
        "Objective 'obj1' is blocked. Please define the task for dependency 'missing_def'.",
        "Objective 'obj1' is blocked. Please define the task for dependency 'another_missing_def'."
    ]
    assert result_rerun[0].text in possible_outcomes # type: ignore

@pytest.mark.asyncio
async def test_evaluate_feasibility(client: Client):
    """Tests the evaluate_feasibility tool."""
    await client.call_tool("add_objective", {"id": "obj1", "description": "Test Objective"})
    await client.call_tool("add_task", {"id": "task1", "description": "Task 1", "objective_id": "obj1"})
    await client.call_tool("add_task", {"id": "task2", "description": "Task 2", "objective_id": "obj1", "dependencies": ["task1"]})

    # Test a feasible objective
    result_feasible = await client.call_tool("evaluate_feasibility", {"objective_id": "obj1"})
    assert result_feasible[0].text == "Objective 'obj1' appears feasible."  # type: ignore

    # Add a task with a dependency that doesn't exist
    await client.call_tool("add_task", {"id": "task3", "description": "Task 3", "objective_id": "obj1", "dependencies": ["missing_task"]})
    result_infeasible = await client.call_tool("evaluate_feasibility", {"objective_id": "obj1"})
    assert "Objective 'obj1' is NOT feasible. Unknown dependencies: ['missing_task']" in result_infeasible[0].text  # type: ignore

    # Test on a non-existent objective
    result_no_obj = await client.call_tool("evaluate_feasibility", {"objective_id": "nonexistent"})
    assert result_no_obj[0].text == "Objective 'nonexistent' not found."  # type: ignore

@pytest.mark.asyncio
async def test_add_dependency(client: Client):
    """Tests the add_dependency tool."""
    await client.call_tool("add_objective", {"id": "obj1", "description": "Test Objective"})
    await client.call_tool("add_task", {"id": "task1", "description": "Task 1", "objective_id": "obj1"})
    await client.call_tool("add_task", {"id": "task2", "description": "Task 2", "objective_id": "obj1"})
    await client.call_tool("add_task", {"id": "task3", "description": "Task 3", "objective_id": "obj1", "dependencies": ["task1"]})

    # Test adding a valid dependency
    result = await client.call_tool("add_dependency", {"task_id": "task2", "dependency_id": "task1"})
    assert result[0].text == "Added dependency 'task1' to task 'task2'."  # type: ignore

    # Test adding a dependency that already exists
    result_exists = await client.call_tool("add_dependency", {"task_id": "task2", "dependency_id": "task1"})
    assert result_exists[0].text == "Dependency 'task1' already exists for task 'task2'."  # type: ignore

    # Test adding a dependency to a non-existent task
    result_no_task = await client.call_tool("add_dependency", {"task_id": "nonexistent", "dependency_id": "task1"})
    assert result_no_task[0].text == "Task 'nonexistent' not found."  # type: ignore
    
    # Test adding a dependency that creates a direct circular dependency
    result_direct_cycle = await client.call_tool("add_dependency", {"task_id": "task1", "dependency_id": "task3"})
    assert "would create a circular dependency" in result_direct_cycle[0].text  # type: ignore

    # Test adding a self-dependency
    result_self_cycle = await client.call_tool("add_dependency", {"task_id": "task1", "dependency_id": "task1"})
    assert result_self_cycle[0].text == "Task 'task1' cannot depend on itself."  # type: ignore

@pytest.mark.asyncio
async def test_full_workflow(client: Client):
    """
    Tests the full workflow from objective creation to completion as an
    integration test.
    """
    # 1. Add the main objective
    add_obj_result = await client.call_tool("add_objective", {"id": "make_breakfast", "description": "Make a delicious breakfast"})
    assert add_obj_result[0].text == "Objective 'make_breakfast' added."  # type: ignore

    # 2. Add all tasks with dependencies
    tasks_to_add = [
        {"id": "toast_bread", "description": "Toast a slice of bread", "dependencies": []},
        {"id": "boil_water", "description": "Boil water for tea", "dependencies": []},
        {"id": "butter_toast", "description": "Butter the toast", "dependencies": ["toast_bread"]},
        {"id": "brew_tea", "description": "Brew a cup of tea", "dependencies": ["boil_water"]},
        {"id": "serve_breakfast", "description": "Serve the delicious breakfast", "dependencies": ["butter_toast", "brew_tea"]},
    ]

    for task in tasks_to_add:
        params = {"objective_id": "make_breakfast", **task}
        await client.call_tool("add_task", params)

    # 3. Check feasibility
    feasibility_result = await client.call_tool("evaluate_feasibility", {"objective_id": "make_breakfast"})
    assert feasibility_result[0].text == "Objective 'make_breakfast' appears feasible."  # type: ignore

    # 4. Execute tasks in a valid order
    # First, the tasks with no dependencies should be available
    next_task_1 = await client.call_tool("get_next_task", {"objective_id": "make_breakfast"})
    assert next_task_1[0].text in [  # type: ignore
        "Next task for objective 'make_breakfast': toast_bread - Toast a slice of bread",
        "Next task for objective 'make_breakfast': boil_water - Boil water for tea"
    ]
    await client.call_tool("complete_task", {"task_id": "toast_bread"})

    next_task_2 = await client.call_tool("get_next_task", {"objective_id": "make_breakfast"})
    assert next_task_2[0].text == "Next task for objective 'make_breakfast': boil_water - Boil water for tea"  # type: ignore
    await client.call_tool("complete_task", {"task_id": "boil_water"})
    
    # Now the dependent tasks should become available
    next_task_3 = await client.call_tool("get_next_task", {"objective_id": "make_breakfast"})
    assert next_task_3[0].text in [  # type: ignore
        "Next task for objective 'make_breakfast': butter_toast - Butter the toast",
        "Next task for objective 'make_breakfast': brew_tea - Brew a cup of tea"
    ]
    await client.call_tool("complete_task", {"task_id": "butter_toast"})

    next_task_4 = await client.call_tool("get_next_task", {"objective_id": "make_breakfast"})
    assert next_task_4[0].text == "Next task for objective 'make_breakfast': brew_tea - Brew a cup of tea"  # type: ignore
    await client.call_tool("complete_task", {"task_id": "brew_tea"})
    
    # Finally, the last task
    next_task_5 = await client.call_tool("get_next_task", {"objective_id": "make_breakfast"})
    assert next_task_5[0].text == "Next task for objective 'make_breakfast': serve_breakfast - Serve the delicious breakfast"  # type: ignore
    await client.call_tool("complete_task", {"task_id": "serve_breakfast"})

    # 5. Confirm completion
    final_task = await client.call_tool("get_next_task", {"objective_id": "make_breakfast"})
    assert final_task[0].text == "Objective 'make_breakfast' is completed. All tasks are done."  # type: ignore 
