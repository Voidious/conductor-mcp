# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Development Commands

### Testing
- `pytest` - Run all tests
- `pytest tests/test_conductor.py` - Run specific test file
- `pytest -v` - Run tests with verbose output

### Code Quality
- `black .` - Format Python code
- `flake8` - Check Python code style and linting
- `pre-commit run --all-files` - Run pre-commit hooks

### Running the Server
- `python main.py` - Run server with stdio transport (default)
- `python main.py --http` - Run server with HTTP transport
- `python main.py --http --host 0.0.0.0 --port 9000` - Run HTTP server with custom host/port
- `./run.sh` - Use shell script to run with proper environment
- `run.bat` - Use batch script for Windows

## Architecture Overview

This is a Python-based MCP (Model Context Protocol) server that provides goal management and dependency tracking capabilities. The codebase is structured as follows:

### MCP Parameter Description Enhancement

The codebase includes a monkey patch for FastMCP that adds detailed parameter descriptions to tool schemas. This addresses a limitation where MCP tools show "No description" for parameters. The patch:

- Intercepts `ParsedFunction.from_function` during tool registration
- Adds comprehensive parameter descriptions for all Conductor MCP tools
- Provides detailed type information and usage guidance for each parameter
- Is implemented as a try/catch block to gracefully handle missing FastMCP imports

### Core Components

**main.py** - Single-file application containing:
- `Goal` - Pydantic model for goal data structure
- `ServerState` - Session state management
- `ConductorMCP` - Custom FastMCP server subclass
- Tool implementations for goal management
- Graph algorithms for cycle detection and dependency resolution

### Key Features

1. **Multi-tenant Architecture**: Each client connection gets isolated state using unique session IDs
2. **Dependency Graph Management**: Goals can have steps (prerequisites) with automatic cycle detection
3. **Tree Format Support**: Define complex goal hierarchies using ASCII tree structures
4. **Automatic Goal Creation**: Steps are automatically created as goals with empty descriptions
5. **Simplified Step Handling**: Unified treatment of goals regardless of how they were created
6. **Topological Sorting**: Uses Python's `graphlib` for dependency resolution
7. **Comprehensive Testing**: Full test suite with async fixtures

### MCP Tools Available

- `set_goals()` - Define/update multiple goals with dependencies (supports list and tree formats for steps)
- `mark_goals()` - Mark goals as completed/incomplete
- `add_steps()` - Add prerequisite steps to existing goals
- `plan_for_goal()` - Generate execution plan with optional Mermaid diagram
- `assess_goal()` - Check goal status and completion state

### Tree Format for Goal Hierarchies

The `set_goals()` tool now supports two formats for the `steps` parameter:

**List Format** (traditional):
```python
{"id": "parent", "description": "Parent goal", "steps": ["step1", "step2"]}
```

**Tree Format** (new):
```python
{"id": "launch", "description": "Launch product", "steps": """Goal: Launch New Product
├── Step: Finalize Product Design
│   ├── Step: User Research Completed
│   └── Step: Design Mockups Approved
├── Step: Develop Marketing Strategy
│   ├── Step: Market Analysis Done
│   └── Step: Marketing Team Assembled
└── Step: Secure Funding
    ├── Step: Business Plan Approved
    └── Step: Investor Pitches Conducted"""}
```

**Goal ID Generation**: Tree format uses step names directly as goal IDs (preserving original formatting):
- `"User Research Completed"` → goal ID `"User Research Completed"` 
- `"Market Analysis Done"` → goal ID `"Market Analysis Done"`
- `"Business Plan Approved"` → goal ID `"Business Plan Approved"`

The `set_goals` response immediately shows all auto-created goal IDs.

**Behavior Changes:**
- Both formats automatically create goals for all steps with empty descriptions
- Goals with empty descriptions show "need more definition" in `assess_goal()`
- `plan_for_goal()` shows "Define and complete goal" for goals needing definition
- Simplified codebase removes special "undefined step" handling

### Session Management

The server automatically creates isolated workspaces for each client connection. Session state is managed through:
- `get_session_state(ctx)` - Retrieves/creates session-specific state
- Connection-based session IDs for automatic isolation
- Fallback to "default_session" for test environments

### Testing Strategy

Tests use FastMCP's `Client` class with async fixtures:
- Each test gets a fresh server instance via `importlib.reload()`
- Session state is reset using the `_reset_state` tool
- Comprehensive coverage of tool functionality and edge cases

## Usage Rules Integration

The repository includes `conductor-rules.md` which provides best practices for AI-assisted coding editors. Key principles:
- Always define high-level goals before taking action
- Use `plan_for_goal` for complex multi-step tasks
- Mark goals as completed immediately after finishing
- Regularly check status with `assess_goal`
- Break down large goals using `add_steps`

## Dependencies

- `fastmcp` - Core MCP framework
- `pydantic` - Data validation and serialization
- `graphlib` - Built-in Python graph algorithms
- `pytest` + `pytest-asyncio` - Testing framework
- `black` - Code formatting
- `flake8` - Linting
- `pre-commit` - Git hooks

## Configuration Files

- `pytest.ini` - Pytest configuration with asyncio mode
- `setup.cfg` - Flake8 linting rules (max line length 88, excludes .venv)
- `requirements.txt` - Runtime dependencies
- `requirements-dev.txt` - Development dependencies