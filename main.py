from fastmcp import FastMCP, Context
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

# --- Data Structures ---

class Task(BaseModel):
    id: str
    description: str
    dependencies: List[str] = []
    completed: bool = False

class Objective(BaseModel):
    id: str
    description: str
    tasks: List[str] = []
    completed: bool = False

class ServerState:
    """A class to hold the server's in-memory state."""
    def __init__(self):
        self.objectives: Dict[str, Objective] = {}
        self.tasks: Dict[str, Task] = {}
    
    def reset(self):
        self.objectives.clear()
        self.tasks.clear()

class ConductorMCP(FastMCP):
    """A custom FastMCP subclass that includes our server state."""
    server_state: ServerState

# --- MCP Server Setup ---

mcp = ConductorMCP("Conductor MCP")
mcp.server_state = ServerState()


# --- Tools ---

def _reset_state() -> str:
    """Resets the in-memory storage. For testing purposes only."""
    mcp.server_state.reset()
    return "State has been reset."

@mcp.tool()
def add_objective(id: str, description: str) -> str:
    """Adds a new objective."""
    state = mcp.server_state
    if id in state.objectives:
        return f"Objective '{id}' already exists."
    state.objectives[id] = Objective(id=id, description=description)
    return f"Objective '{id}' added."

def _check_for_cycles(new_task_id: str, new_dependencies: List[str], existing_tasks: Dict[str, Task]) -> bool:
    """
    Checks if adding a new task with its dependencies would create a cycle.
    Uses Depth First Search (DFS) to traverse the graph.
    """
    temp_tasks = existing_tasks.copy()
    temp_tasks[new_task_id] = Task(id=new_task_id, description="", dependencies=new_dependencies)

    visiting = set()
    visited = set()

    def dfs(task_id):
        visiting.add(task_id)
        
        task = temp_tasks.get(task_id)
        cycle_found = False
        if task:
            for dep_id in task.dependencies:
                if dep_id in visiting:
                    cycle_found = True
                    break
                if dep_id not in visited:
                    if dfs(dep_id):
                        cycle_found = True
                        break
        
        visiting.remove(task_id)
        visited.add(task_id)
        return cycle_found

    return dfs(new_task_id)

@mcp.tool()
def add_task(id: str, description: str, objective_id: str, dependencies: List[str] = []) -> str:
    """
    Adds a new task to an objective.
    This tool will reject tasks that would introduce a circular dependency.
    """
    state = mcp.server_state
    if id in state.tasks:
        return f"Task '{id}' already exists."
    if objective_id not in state.objectives:
        return f"Objective '{objective_id}' not found."

    if _check_for_cycles(id, dependencies, state.tasks):
        return f"Task '{id}' would create a circular dependency and was not added."

    state.tasks[id] = Task(id=id, description=description, dependencies=dependencies)
    obj = state.objectives[objective_id]
    obj.tasks.append(id)
    return f"Task '{id}' added to objective '{objective_id}'."

@mcp.tool()
def get_next_task(objective_id: str) -> str:
    """
    Finds the next available task for a given objective.

    This tool first checks if all task dependencies are defined. If a dependency
    is found to be missing, it will return a message asking for the task to be
    defined. Only when all dependencies are defined will it return the next
    unblocked task. If all tasks are completed, it declares the objective complete.
    """
    state = mcp.server_state
    objective = state.objectives.get(objective_id)

    if not objective:
        return f"Objective '{objective_id}' not found."

    if not objective.tasks:
        return f"Objective '{objective_id}' is completed. All tasks are done."

    # 1. First, check for any missing task definitions.
    for task_id in objective.tasks:
        task = state.tasks.get(task_id)
        if task:
            for dep_id in task.dependencies:
                if dep_id not in state.tasks:
                    return (
                        f"Objective '{objective_id}' is blocked. "
                        f"Please define the task for dependency '{dep_id}'."
                    )

    # 2. If all definitions exist, find the next runnable task.
    for task_id in objective.tasks:
        task = state.tasks.get(task_id)
        if not task or task.completed:
            continue

        dependencies_met = True
        for dep_id in task.dependencies:
            dep_task = state.tasks.get(dep_id)
            # This check is now safer because we've already validated all definitions exist.
            if not dep_task or not dep_task.completed:
                dependencies_met = False
                break
        
        if dependencies_met:
            return f"Next task for objective '{objective_id}': {task.id} - {task.description}"

    # 3. If no runnable tasks were found, check if the objective is complete.
    all_tasks_completed = all(
        state.tasks.get(task_id, Task(id="", description="")).completed
        for task_id in objective.tasks
    )

    if all_tasks_completed:
        objective.completed = True
        return f"Objective '{objective_id}' is completed. All tasks are done."
    else:
        return f"Objective '{objective_id}' is blocked. No tasks are currently available."

@mcp.tool()
def complete_task(task_id: str) -> str:
    """Marks a task as completed."""
    state = mcp.server_state
    if task_id not in state.tasks:
        return f"Task '{task_id}' not found."
    
    state.tasks[task_id].completed = True
    return f"Task '{task_id}' marked as completed."

@mcp.tool()
def evaluate_feasibility(objective_id: str) -> str:
    """Evaluates if an objective is feasible by checking for unknown dependencies."""
    state = mcp.server_state
    if objective_id not in state.objectives:
        return f"Objective '{objective_id}' not found."

    missing_deps = []
    obj = state.objectives[objective_id]
    for task_id in obj.tasks:
        task = state.tasks.get(task_id)
        if not task:
            continue
        for dep_id in task.dependencies:
            if dep_id not in state.tasks:
                missing_deps.append(dep_id)

    if missing_deps:
        return f"Objective '{objective_id}' is NOT feasible. Unknown dependencies: {list(set(missing_deps))}"
    else:
        return f"Objective '{objective_id}' appears feasible."

@mcp.tool()
def add_dependency(task_id: str, dependency_id: str) -> str:
    """Adds a new dependency to an existing task."""
    state = mcp.server_state

    if task_id not in state.tasks:
        return f"Task '{task_id}' not found."
    if task_id == dependency_id:
        return f"Task '{task_id}' cannot depend on itself."

    task = state.tasks[task_id]
    
    if dependency_id in task.dependencies:
        return f"Dependency '{dependency_id}' already exists for task '{task_id}'."

    # Check for circular dependencies before adding
    new_dependencies = task.dependencies + [dependency_id]
    if _check_for_cycles(task_id, new_dependencies, state.tasks):
        return f"Adding dependency '{dependency_id}' to task '{task_id}' would create a circular dependency."

    task.dependencies.append(dependency_id)
    return f"Added dependency '{dependency_id}' to task '{task_id}'."

if __name__ == "__main__":
    mcp.run() 
