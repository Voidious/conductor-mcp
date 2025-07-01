import pytest
import json
from fastmcp import Client
import main


@pytest.mark.asyncio
async def test_tree_format_basic():
    """Test basic tree format parsing and goal creation."""
    async with Client(main.mcp) as client:
        tree_goals = [
            {
                "id": "project",
                "description": "Main project",
                "steps": """Goal: Main Project
├── Step: Phase 1
│   ├── Step: Task A
│   └── Step: Task B
└── Step: Phase 2
    └── Step: Task C""",
            }
        ]

        result = await client.call_tool("set_goals", {"goals": tree_goals})

        # Should succeed and show auto-created goals
        assert "Goals defined." in result[0].text
        assert "Auto-created 5 step goals:" in result[0].text

        # Verify all goals were created with correct names
        # Main goal should use the provided ID "project", not "Main Project" from tree
        expected_goals = ["project", "Phase 1", "Task A", "Task B", "Phase 2", "Task C"]
        for goal_name in expected_goals:
            assess = await client.call_tool("assess_goal", {"goal_id": goal_name})
            assert "not found" not in assess[0].text


@pytest.mark.asyncio
async def test_tree_format_dependencies():
    """Test that tree format creates correct dependency relationships."""
    async with Client(main.mcp) as client:
        tree_goals = [
            {
                "id": "root",
                "description": "Root goal",
                "steps": """Goal: Root
├── Step: Branch A
│   ├── Step: Leaf 1
│   └── Step: Leaf 2
└── Step: Branch B
    └── Step: Leaf 3""",
            }
        ]

        await client.call_tool("set_goals", {"goals": tree_goals})

        # Check plan shows correct dependency order
        plan_result = await client.call_tool(
            "plan_for_goal", {"goal_id": "root", "include_diagram": False}
        )
        plan_data = json.loads(plan_result[0].text)
        plan_steps = plan_data["plan"]

        # Leaves should come before branches, branches before root
        leaf_positions = []
        branch_positions = []
        root_position = None

        for i, step in enumerate(plan_steps):
            if "'Leaf " in step:
                leaf_positions.append(i)
            elif "'Branch " in step:
                branch_positions.append(i)
            elif "'Root'" in step or "'root'" in step:
                root_position = i

        # All leaves should come before all branches
        if leaf_positions and branch_positions:
            assert max(leaf_positions) < min(branch_positions)

        # All branches should come before root
        if branch_positions and root_position is not None:
            assert max(branch_positions) < root_position


@pytest.mark.asyncio
async def test_tree_format_natural_goal_ids():
    """Test that tree format preserves natural goal names as IDs."""
    async with Client(main.mcp) as client:
        tree_goals = [
            {
                "id": "test",
                "description": "Test natural IDs",
                "steps": """Goal: Test Project
├── Step: User Research Completed
├── Step: Design-Phase Work
└── Step: API Development & Testing""",
            }
        ]

        await client.call_tool("set_goals", {"goals": tree_goals})

        # Test that we can reference goals with their natural names
        natural_names = [
            "User Research Completed",
            "Design-Phase Work",
            "API Development & Testing",
        ]

        for goal_name in natural_names:
            assess = await client.call_tool("assess_goal", {"goal_id": goal_name})
            assert "All step goals are met" in assess[0].text
            assert "ready" in assess[0].text


@pytest.mark.asyncio
async def test_tree_format_empty_descriptions():
    """
    Test that auto-created goals have empty descriptions and show 'need definition'.
    """
    async with Client(main.mcp) as client:
        tree_goals = [
            {
                "id": "parent",
                "description": "Parent with tree steps",
                "steps": """Goal: Parent
└── Step: Auto Created Step""",
            }
        ]

        await client.call_tool("set_goals", {"goals": tree_goals})

        # Auto-created goal should have empty description
        assess = await client.call_tool("assess_goal", {"goal_id": "Auto Created Step"})
        assert "ready" in assess[0].text  # Empty description means ready

        # Parent should recognize it needs definition
        assess_parent = await client.call_tool("assess_goal", {"goal_id": "parent"})
        assert "need more definition" in assess_parent[0].text
        assert "Auto Created Step" in assess_parent[0].text


@pytest.mark.asyncio
async def test_tree_format_plan_generation():
    """Test that tree format goals show proper format in plan generation."""
    async with Client(main.mcp) as client:
        tree_goals = [
            {
                "id": "project",
                "description": "Project with tree structure",
                "steps": """Goal: Project
├── Step: Research Phase
└── Step: Development Phase
    └── Step: Testing Phase""",
            }
        ]

        await client.call_tool("set_goals", {"goals": tree_goals})

        # Check plan format
        plan_result = await client.call_tool(
            "plan_for_goal", {"goal_id": "project", "include_diagram": False}
        )
        plan_data = json.loads(plan_result[0].text)
        plan_steps = plan_data["plan"]

        # Auto-created goals should show "Define and complete goal" format
        auto_created_steps = [
            step for step in plan_steps if "Define and complete goal" in step
        ]
        regular_steps = [
            step
            for step in plan_steps
            if "Complete goal:" in step and "Define and complete" not in step
        ]

        # Should have auto-created steps (empty descriptions)
        assert len(auto_created_steps) > 0

        # Should have at least one regular step (the main project goal)
        assert len(regular_steps) > 0

        # Check specific format
        assert any(
            "'Research Phase' - Details to be determined" in step
            for step in auto_created_steps
        )


@pytest.mark.asyncio
async def test_tree_format_mixed_with_list():
    """Test tree format works alongside traditional list format."""
    async with Client(main.mcp) as client:
        mixed_goals = [
            {
                "id": "list_goal",
                "description": "Goal with list steps",
                "steps": ["step1", "step2"],
            },
            {
                "id": "tree_goal",
                "description": "Goal with tree steps",
                "steps": """Goal: Tree Goal
├── Step: Tree Step 1
└── Step: Tree Step 2""",
            },
        ]

        result = await client.call_tool("set_goals", {"goals": mixed_goals})

        # Should show auto-created goals from both formats
        assert "Goals defined." in result[0].text
        assert "Auto-created" in result[0].text

        # Verify all goals exist
        all_goal_names = [
            "list_goal",
            "tree_goal",
            "step1",
            "step2",
            "Tree Step 1",
            "Tree Step 2",
        ]
        for goal_name in all_goal_names:
            assess = await client.call_tool("assess_goal", {"goal_id": goal_name})
            assert "not found" not in assess[0].text


@pytest.mark.asyncio
async def test_tree_format_complex_hierarchy():
    """Test complex multi-level tree hierarchy."""
    async with Client(main.mcp) as client:
        complex_tree = [
            {
                "id": "enterprise_project",
                "description": "Large enterprise project",
                "steps": """Goal: Enterprise Project
├── Step: Requirements Gathering
│   ├── Step: Stakeholder Interviews
│   ├── Step: Business Analysis
│   └── Step: Technical Requirements
├── Step: System Design
│   ├── Step: Architecture Design
│   │   ├── Step: Database Schema
│   │   └── Step: API Design
│   └── Step: UI/UX Design
└── Step: Implementation
    ├── Step: Backend Development
    ├── Step: Frontend Development
    └── Step: Integration Testing""",
            }
        ]

        result = await client.call_tool("set_goals", {"goals": complex_tree})

        # Should handle complex hierarchy
        assert "Goals defined." in result[0].text
        assert "Auto-created" in result[0].text

        # Test deeply nested goal exists
        assess = await client.call_tool("assess_goal", {"goal_id": "Database Schema"})
        assert "not found" not in assess[0].text

        # Test plan respects hierarchy
        plan_result = await client.call_tool(
            "plan_for_goal",
            {
                "goal_id": "enterprise_project",
                "include_diagram": False,
                "max_steps": 15,
            },
        )
        plan_data = json.loads(plan_result[0].text)

        # Should include multiple levels
        assert len([step for step in plan_data["plan"] if "goal:" in step]) >= 10


@pytest.mark.asyncio
async def test_tree_format_malformed_input():
    """Test graceful handling of malformed tree input."""
    async with Client(main.mcp) as client:
        # Test with malformed tree (should still work, just less structured)
        malformed_goals = [
            {
                "id": "malformed",
                "description": "Goal with malformed tree",
                "steps": """This is not really a tree
Just some text
Maybe: Something that looks like steps
├── But: Not consistent formatting""",
            }
        ]

        result = await client.call_tool("set_goals", {"goals": malformed_goals})

        # Should still succeed (parser is robust)
        assert "Goals defined." in result[0].text

        # May or may not create auto-goals depending on what parser extracts
        # Main goal should exist
        assess = await client.call_tool("assess_goal", {"goal_id": "malformed"})
        assert "not found" not in assess[0].text


def test_parse_dependency_tree_function():
    """Test the tree parsing function directly."""
    tree_text = """Goal: Main Goal
├── Step: Sub Step 1
│   ├── Step: Sub Sub Step 1
│   └── Step: Sub Sub Step 2
├── Step: Sub Step 2
└── Step: Sub Step 3"""

    result, descriptions = main._parse_dependency_tree(tree_text)

    # Check structure
    assert "Main Goal" in result
    assert "Sub Step 1" in result
    assert "Sub Sub Step 1" in result

    # Check dependencies
    assert "Sub Step 1" in result["Main Goal"]
    assert "Sub Step 2" in result["Main Goal"]
    assert "Sub Step 3" in result["Main Goal"]
    assert "Sub Sub Step 1" in result["Sub Step 1"]
    assert "Sub Sub Step 2" in result["Sub Step 1"]

    # Leaf nodes should have no dependencies
    assert result["Sub Sub Step 1"] == []
    assert result["Sub Sub Step 2"] == []
    assert result["Sub Step 2"] == []
    assert result["Sub Step 3"] == []


def test_parse_dependency_tree_edge_cases():
    """Test tree parsing edge cases."""
    # Empty input
    assert main._parse_dependency_tree("") == ({}, {})
    assert main._parse_dependency_tree("   ") == ({}, {})

    # Single line
    result, descriptions = main._parse_dependency_tree("Goal: Single Goal")
    assert result == {"Single Goal": []}

    # No colons
    result, descriptions = main._parse_dependency_tree("├── Just text\n└── More text")
    assert "Just text" in result
    assert "More text" in result


def test_parse_dependency_tree_with_descriptions():
    """Test tree parsing with descriptions after colons."""
    tree_text = """Goal: Main Goal: Complete the main objective
├── Step: Sub Step 1: First sub-task with details
│   ├── Step: Sub Sub Step 1: Nested task
│   └── Step: Sub Sub Step 2
├── Step: Sub Step 2: Another important step
└── Step: Sub Step 3"""

    result, descriptions = main._parse_dependency_tree(tree_text)

    # Check that descriptions are captured
    assert descriptions["Main Goal"] == "Complete the main objective"
    assert descriptions["Sub Step 1"] == "First sub-task with details"
    assert descriptions["Sub Sub Step 1"] == "Nested task"
    assert descriptions["Sub Step 2"] == "Another important step"
    assert descriptions["Sub Sub Step 2"] == ""  # No description
    assert descriptions["Sub Step 3"] == ""  # No description


def test_parse_dependency_tree_flexible_prefixes():
    """Test tree parsing with flexible or missing prefixes."""
    tree_text = """Main Goal
├── Task: Sub Step 1
│   ├── Subtask: Sub Sub Step 1
│   └── Sub Sub Step 2
├── Sub Step 2
└── Final: Sub Step 3"""

    result, descriptions = main._parse_dependency_tree(tree_text)

    # Should work regardless of prefix
    assert "Main Goal" in result
    assert "Sub Step 1" in result["Main Goal"]
    assert "Sub Sub Step 1" in result["Sub Step 1"]
    assert "Sub Sub Step 2" in result["Sub Step 1"]
    assert "Sub Step 2" in result["Main Goal"]
    assert "Sub Step 3" in result["Main Goal"]


def test_parse_dependency_tree_with_root_goal_id():
    """Test tree parsing with custom root goal ID."""
    tree_text = """Goal: Original Name
├── Step: Sub Step 1
└── Step: Sub Step 2"""

    result, descriptions = main._parse_dependency_tree(tree_text, "custom_root")

    # Root should use custom ID instead of parsed name
    assert "custom_root" in result
    assert "Original Name" not in result
    assert "Sub Step 1" in result["custom_root"]
    assert "Sub Step 2" in result["custom_root"]


@pytest.mark.asyncio
async def test_tree_format_improved_features():
    """Test all the improved tree format features together."""
    async with Client(main.mcp) as client:
        tree_goals = [
            {
                "id": "my_project",
                "description": "My custom project",
                "steps": """Goal: Original Tree Name: This description should be ignored
    Research Phase: Gather requirements and analyze
      Market Analysis: Study the competition
      User Interviews
    Development: Build the solution
      Frontend Work: Create the UI
      Backend Development
    Launch Phase: Go to market""",
            }
        ]

        result = await client.call_tool("set_goals", {"goals": tree_goals})

        # Should succeed and show auto-created goals (but not count main goal)
        assert "Goals defined." in result[0].text
        # Should be 7 auto-created goals (not 8, since main goal isn't counted)
        assert "Auto-created 7 step goals" in result[0].text

        # Main goal should use the provided ID, not tree name
        assess_main = await client.call_tool("assess_goal", {"goal_id": "my_project"})
        assert "not found" not in assess_main[0].text

        # Tree name should not exist as a separate goal
        assess_tree = await client.call_tool(
            "assess_goal", {"goal_id": "Original Tree Name"}
        )
        assert "not found" in assess_tree[0].text

        # Verify goals with descriptions from tree were created
        assess_research = await client.call_tool(
            "assess_goal", {"goal_id": "Research Phase"}
        )
        assert "not found" not in assess_research[0].text

        assess_market = await client.call_tool(
            "assess_goal", {"goal_id": "Market Analysis"}
        )
        assert "not found" not in assess_market[0].text

        # Check that flexible indentation worked
        assess_frontend = await client.call_tool(
            "assess_goal", {"goal_id": "Frontend Work"}
        )
        assert "not found" not in assess_frontend[0].text

        # Check plan generation includes main goal correctly
        plan_result = await client.call_tool(
            "plan_for_goal", {"goal_id": "my_project", "include_diagram": False}
        )
        plan_data = json.loads(plan_result[0].text)
        plan_steps = plan_data["plan"]

        # Should include the main goal with its original description
        main_goal_step = None
        for step in plan_steps:
            if "'my_project'" in step and "My custom project" in step:
                main_goal_step = step
                break
        assert main_goal_step is not None, f"Main goal not found in plan: {plan_steps}"
