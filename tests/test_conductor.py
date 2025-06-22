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
async def test_define_objective(client: Client):
    """Tests the define_objective tool for success and failure cases."""
    # Test adding a new objective
    result = await client.call_tool("define_objective", {"id": "obj1", "description": "Test Objective"})
    assert result[0].text == "Objective 'obj1' defined."  # type: ignore

    # Test adding an objective that already exists
    result_exists = await client.call_tool("define_objective", {"id": "obj1", "description": "Duplicate Objective"})
    assert result_exists[0].text == "Objective 'obj1' already exists."  # type: ignore

@pytest.mark.asyncio
async def test_define_task(client: Client):
    """Tests the define_task tool for success and various failure cases."""
    await client.call_tool("define_objective", {"id": "obj1", "description": "Test Objective"})

    # Test adding a valid task
    result = await client.call_tool("define_task", {"id": "task1", "description": "Test Task", "objective_id": "obj1"})
    assert result[0].text == "Task 'task1' added to objective 'obj1'."  # type: ignore

    # Test adding a task that already exists
    result_exists = await client.call_tool("define_task", {"id": "task1", "description": "Duplicate Task", "objective_id": "obj1"})
    assert result_exists[0].text == "Task 'task1' already exists."  # type: ignore

    # Test adding a task to a non-existent objective
    result_no_obj = await client.call_tool("define_task", {"id": "task2", "description": "Another Task", "objective_id": "nonexistent"})
    assert result_no_obj[0].text == "Objective 'nonexistent' not found."  # type: ignore

    # Test adding a task with a missing prerequisite is allowed
    result_missing_dep = await client.call_tool("define_task", {
        "id": "task3",
        "description": "Task with missing dep",
        "objective_id": "obj1",
        "prerequisites": ["missing_task"]
    })
    assert result_missing_dep[0].text == "Task 'task3' added to objective 'obj1'."  # type: ignore

    # Test adding a task that would create a direct deadlock (A -> A)
    result_self_cycle = await client.call_tool("define_task", {
        "id": "task4",
        "description": "Self-referential task",
        "objective_id": "obj1",
        "prerequisites": ["task4"]
    })
    assert "deadlock" in result_self_cycle[0].text  # type: ignore

    # Test adding a task that would create an indirect deadlock (A -> B -> A)
    await client.call_tool("define_task", {"id": "taskA", "description": "Task A", "objective_id": "obj1", "prerequisites": ["taskB"]})
    result_indirect_cycle = await client.call_tool("define_task", {
        "id": "taskB",
        "description": "Task B",
        "objective_id": "obj1",
        "prerequisites": ["taskA"]
    })
    assert "deadlock" in result_indirect_cycle[0].text  # type: ignore

@pytest.mark.asyncio
async def test_complete_task(client: Client):
    """Tests the complete_task tool."""
    await client.call_tool("define_objective", {"id": "obj1", "description": "Test Objective"})
    await client.call_tool("define_task", {"id": "task1", "description": "Task 1", "objective_id": "obj1"})
    await client.call_tool("define_task", {"id": "task2", "description": "Task 2", "objective_id": "obj1", "prerequisites": ["task1"]})

    # Test completing an existing task, which should now return a combined message.
    result = await client.call_tool("complete_task", {"task_id": "task1"})
    assert "Task 'task1' marked as completed." in result[0].text  # type: ignore
    assert "Next task for objective 'obj1': task2 - Task 2" in result[0].text  # type: ignore

    # Test completing the final task, which should return the objective completion message.
    result_final = await client.call_tool("complete_task", {"task_id": "task2"})
    assert "Task 'task2' marked as completed." in result_final[0].text  # type: ignore
    assert "Objective 'obj1' is completed" in result_final[0].text  # type: ignore

    # Test completing a non-existent task
    result_no_task = await client.call_tool("complete_task", {"task_id": "nonexistent"})
    assert result_no_task[0].text == "Task 'nonexistent' not found."  # type: ignore

@pytest.mark.asyncio
async def test_get_next_task(client: Client):
    """Tests the get_next_task tool logic."""
    await client.call_tool("define_objective", {"id": "obj1", "description": "Test Objective"})
    await client.call_tool("define_task", {"id": "task1", "description": "Task 1", "objective_id": "obj1"})
    await client.call_tool("define_task", {"id": "task2", "description": "Task 2", "objective_id": "obj1", "prerequisites": ["task1"]})

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
    await client.call_tool("define_objective", {"id": "obj_no_tasks", "description": "Objective without tasks"})
    result = await client.call_tool("get_next_task", {"objective_id": "obj_no_tasks"})
    assert result[0].text == "Objective 'obj_no_tasks' is completed. All tasks are done."  # type: ignore

@pytest.mark.asyncio
async def test_get_next_task_blocked(client: Client):
    """Tests that get_next_task correctly identifies a missing prerequisite."""
    await client.call_tool("define_objective", {"id": "obj1", "description": "Test Objective"})
    await client.call_tool("define_task", {"id": "task1", "description": "Task 1", "objective_id": "obj1", "prerequisites": ["missing_def"]})

    # The tool should immediately report the missing definition.
    result = await client.call_tool("get_next_task", {"objective_id": "obj1"})
    expected_text = (
        "Objective 'obj1' is blocked. "
        "Please define the task for prerequisite 'missing_def'."
    )
    assert result[0].text == expected_text  # type: ignore

    # Add another task with a different missing prerequisite. The tool should still report the first one it finds.
    await client.call_tool("define_task", {"id": "task0", "description": "Task 0", "objective_id": "obj1", "prerequisites": ["another_missing_def"]})
    
    # Re-run the check. The order of checking is not guaranteed, so we accept either missing prerequisite.
    result_rerun = await client.call_tool("get_next_task", {"objective_id": "obj1"})
    possible_outcomes = [
        "Objective 'obj1' is blocked. Please define the task for prerequisite 'missing_def'.",
        "Objective 'obj1' is blocked. Please define the task for prerequisite 'another_missing_def'."
    ]
    assert result_rerun[0].text in possible_outcomes # type: ignore

@pytest.mark.asyncio
async def test_evaluate_feasibility(client: Client):
    """Tests the evaluate_feasibility tool."""
    await client.call_tool("define_objective", {"id": "obj1", "description": "Test Objective"})
    await client.call_tool("define_task", {"id": "task1", "description": "Task 1", "objective_id": "obj1"})
    await client.call_tool("define_task", {"id": "task2", "description": "Task 2", "objective_id": "obj1", "prerequisites": ["task1"]})

    # Test a feasible objective
    result_feasible = await client.call_tool("evaluate_feasibility", {"objective_id": "obj1"})
    assert result_feasible[0].text == "Objective 'obj1' appears feasible."  # type: ignore

    # Add a task with a prerequisite that doesn't exist
    await client.call_tool("define_task", {"id": "task3", "description": "Task 3", "objective_id": "obj1", "prerequisites": ["missing_task"]})
    result_infeasible = await client.call_tool("evaluate_feasibility", {"objective_id": "obj1"})
    assert "Objective 'obj1' is NOT feasible. Unknown prerequisites: ['missing_task']" in result_infeasible[0].text  # type: ignore

    # Test on a non-existent objective
    result_no_obj = await client.call_tool("evaluate_feasibility", {"objective_id": "nonexistent"})
    assert result_no_obj[0].text == "Objective 'nonexistent' not found."  # type: ignore

@pytest.mark.asyncio
async def test_define_prerequisite(client: Client):
    """Tests the define_prerequisite tool."""
    await client.call_tool("define_objective", {"id": "obj1", "description": "Test Objective"})
    await client.call_tool("define_task", {"id": "task1", "description": "Task 1", "objective_id": "obj1"})
    await client.call_tool("define_task", {"id": "task2", "description": "Task 2", "objective_id": "obj1"})
    await client.call_tool("define_task", {"id": "task3", "description": "Task 3", "objective_id": "obj1", "prerequisites": ["task1"]})

    # Test adding a valid prerequisite
    result = await client.call_tool("define_prerequisite", {"task_id": "task2", "prerequisite_id": "task1"})
    assert result[0].text == "Added prerequisite 'task1' to task 'task2'."  # type: ignore

    # Test adding a prerequisite that already exists
    result_exists = await client.call_tool("define_prerequisite", {"task_id": "task2", "prerequisite_id": "task1"})
    assert result_exists[0].text == "Prerequisite 'task1' already exists for task 'task2'."  # type: ignore

    # Test adding a prerequisite to a non-existent task
    result_no_task = await client.call_tool("define_prerequisite", {"task_id": "nonexistent", "prerequisite_id": "task1"})
    assert result_no_task[0].text == "Task 'nonexistent' not found."  # type: ignore
    
    # Test adding a prerequisite that creates a direct deadlock
    result_direct_cycle = await client.call_tool("define_prerequisite", {"task_id": "task1", "prerequisite_id": "task3"})
    assert "would create a deadlock" in result_direct_cycle[0].text  # type: ignore

    # Test adding a self-prerequisite
    result_self_cycle = await client.call_tool("define_prerequisite", {"task_id": "task1", "prerequisite_id": "task1"})
    assert result_self_cycle[0].text == "Task 'task1' cannot have itself as a prerequisite."  # type: ignore

@pytest.mark.asyncio
async def test_full_workflow(client: Client):
    """
    Tests the full workflow from objective creation to completion as an
    integration test.
    """
    # 1. Define the main objective
    add_obj_result = await client.call_tool("define_objective", {"id": "make_breakfast", "description": "Make a delicious breakfast"})
    assert add_obj_result[0].text == "Objective 'make_breakfast' defined."  # type: ignore

    # 2. Define all tasks with prerequisites
    tasks_to_add = [
        {"id": "toast_bread", "description": "Toast a slice of bread", "prerequisites": []},
        {"id": "boil_water", "description": "Boil water for tea", "prerequisites": []},
        {"id": "butter_toast", "description": "Butter the toast", "prerequisites": ["toast_bread"]},
        {"id": "brew_tea", "description": "Brew a cup of tea", "prerequisites": ["boil_water"]},
        {"id": "serve_breakfast", "description": "Serve the delicious breakfast", "prerequisites": ["butter_toast", "brew_tea"]},
    ]

    for task in tasks_to_add:
        params = {"objective_id": "make_breakfast", **task}
        await client.call_tool("define_task", params)

    # 3. Check feasibility
    feasibility_result = await client.call_tool("evaluate_feasibility", {"objective_id": "make_breakfast"})
    assert feasibility_result[0].text == "Objective 'make_breakfast' appears feasible."  # type: ignore

    # 4. Execute tasks by following the next_task prompts from complete_task
    # The first task is retrieved separately.
    next_task_str = await client.call_tool("get_next_task", {"objective_id": "make_breakfast"})
    assert next_task_str[0].text == "Next task for objective 'make_breakfast': toast_bread - Toast a slice of bread" # type: ignore
    
    # Complete tasks in sequence, verifying the next task is returned each time.
    next_task_str = await client.call_tool("complete_task", {"task_id": "toast_bread"})
    assert "Task 'toast_bread' marked as completed." in next_task_str[0].text  # type: ignore
    assert "Next task for objective 'make_breakfast': boil_water - Boil water for tea" in next_task_str[0].text  # type: ignore
    
    next_task_str = await client.call_tool("complete_task", {"task_id": "boil_water"})
    assert "Task 'boil_water' marked as completed." in next_task_str[0].text # type: ignore
    assert "Next task for objective 'make_breakfast': butter_toast - Butter the toast" in next_task_str[0].text  # type: ignore

    next_task_str = await client.call_tool("complete_task", {"task_id": "butter_toast"})
    assert "Task 'butter_toast' marked as completed." in next_task_str[0].text # type: ignore
    assert "Next task for objective 'make_breakfast': brew_tea - Brew a cup of tea" in next_task_str[0].text  # type: ignore
    
    next_task_str = await client.call_tool("complete_task", {"task_id": "brew_tea"})
    assert "Task 'brew_tea' marked as completed." in next_task_str[0].text # type: ignore
    assert "Next task for objective 'make_breakfast': serve_breakfast - Serve the delicious breakfast" in next_task_str[0].text  # type: ignore

    # 5. Complete the final task and confirm the objective is done
    final_result = await client.call_tool("complete_task", {"task_id": "serve_breakfast"})
    assert "Task 'serve_breakfast' marked as completed." in final_result[0].text # type: ignore
    assert "Objective 'make_breakfast' is completed. All tasks are done." in final_result[0].text  # type: ignore 
