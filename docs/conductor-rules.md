# Conductor MCP Tool Usage Rules

**Purpose:**
These rules guide the use of Conductor MCP tools for effective, goal-oriented project management in AI-assisted coding environments. They ensure clarity, efficiency, and best practices when working with goals, plans, and progress tracking.

## 1. Goal-Oriented Actions
- **Always start by defining or clarifying the high-level goal before taking action.**
- Use `set_goals` to register new goals or update existing ones.
  - *Example: To start a new feature, first define it as a goal using `set_goals`.*
- **NEW**: Use tree format for complex hierarchical goals with dependencies:
  ```
  set_goals([{
    "id": "implement_feature",
    "description": "Implement user authentication feature",
    "steps": """Goal: User Authentication
    ├── Backend: Set up authentication backend
    │   ├── Database: User schema and migrations
    │   ├── API: Authentication endpoints
    │   └── Security: Password hashing and JWT
    ├── Frontend: Create authentication UI
    │   ├── Login: Login form component
    │   ├── Register: Registration form component
    │   └── Profile: User profile management
    └── Testing: Comprehensive test coverage
        ├── Unit Tests: Backend unit tests
        └── Integration: End-to-end user flows"""
  }])
  ```

## 2. Planning and Dependencies
- Use `plan_for_goal` to generate an execution plan and visualize dependencies before starting work on a complex goal.
  - *Example: Before implementing a multi-step feature, call `plan_for_goal` to see all required steps and their order.*
- If a goal is blocked, use `assess_goal` to check its status and prerequisites.
- **NEW**: Tree format automatically creates goal hierarchies - the response shows all auto-created goal IDs immediately.

## 3. Stepwise Progression
- Mark goals or steps as completed using `mark_goals` immediately after finishing them.
  - *Example: After completing a subtask, call `mark_goals` to update its status.*
- Use `add_steps` to break down large goals into actionable steps.
  - *Example: For a large refactor, use `add_steps` to list each file or module to update.*
- **NEW**: Goals created from tree steps automatically get empty descriptions. Use `assess_goal` to identify which goals "need more definition" and expand them with `set_goals`.

## 4. Tree Format Features
- **Flexible Syntax**: Tree format accepts various prefixes and indentation styles:
  ```
  Goal: Main Task
  ├── Step: Subtask 1
  ├── Phase: Another approach
  │   └── Implementation details
  └── Final: Wrap up
  ```
- **Descriptions in Trees**: Add descriptions directly in the tree:
  ```
  Research Phase: Gather requirements and analyze market
  ├── Market Analysis: Study competitor offerings and pricing
  ├── User Interviews: Conduct 10+ user interviews
  └── Technical Research: Evaluate implementation options
  ```
- **Goal ID Preservation**: Tree-created goals use natural names as IDs:
  - "User Research Completed" becomes goal ID "User Research Completed"
  - "API Development & Testing" becomes goal ID "API Development & Testing"

## 5. Status and Progress Tracking
- Regularly check the status of goals with `assess_goal` to ensure alignment and progress.
  - *Example: Use `assess_goal` before starting new work to avoid duplicating effort.*
- Use status checks before starting new work to avoid duplicating effort or working on blocked items.
- **NEW**: `assess_goal` provides four distinct status types:
  1. **"Goal is ready"** - No steps required or all steps completed
  2. **"Needs more definition"** - Has step goals with empty descriptions
  3. **"Well-defined but incomplete"** - Has defined steps but some incomplete
  4. **"Goal is complete"** - Goal has been marked as completed

## 6. Documentation and Rationale
- Document each tool call with a brief explanation of its purpose and expected outcome.
  - *Example: "Calling `plan_for_goal` to visualize dependencies before starting implementation."*

## 7. Error Handling
- If a tool call fails or a goal is blocked, check prerequisites, input formats, and dependencies before retrying or escalating.
  - *Example: If `mark_goals` fails, use `assess_goal` to check for unmet prerequisites.*
- **NEW**: Cycle detection prevents deadlocks - if cycles are detected, problematic goals are listed for review.

## 8. Efficiency
- Avoid redundant tool calls by caching recent results where appropriate.
  - *Example: If you already have a plan for a goal, reuse it instead of calling `plan_for_goal` again unless something has changed.*
- **NEW**: Auto-created goals from both list and tree formats are automatically excluded from "auto-created" counts when they represent the main goal.

## Best Practices for Tree Format
1. **Start Simple**: Begin with list format for simple dependencies, use tree format for complex hierarchies
2. **Natural Names**: Use descriptive, natural goal names that are meaningful to humans and LLMs
3. **Iterative Refinement**: Create basic tree structure first, then expand goals that "need more definition"
4. **Consistent Indentation**: While flexible indentation is supported, consistent spacing improves readability
5. **Meaningful Descriptions**: Add descriptions to provide context and reduce ambiguity

## Examples

### Simple Goal Chain (List Format)
```python
set_goals([
  {"id": "setup", "description": "Set up development environment"},
  {"id": "implement", "description": "Implement core feature", "steps": ["setup"]},
  {"id": "test", "description": "Test the implementation", "steps": ["implement"]},
  {"id": "deploy", "description": "Deploy to production", "steps": ["test"]}
])
```

### Complex Project (Tree Format)
```python
set_goals([{
  "id": "launch_product",
  "description": "Launch new product successfully",
  "steps": """Goal: Product Launch
  ├── Market Research: Validate product-market fit
  │   ├── Competitor Analysis: Study 5 main competitors
  │   ├── User Surveys: Survey 100+ potential users
  │   └── Pricing Strategy: Determine optimal pricing model
  ├── Product Development: Build MVP with core features
  │   ├── Backend API: RESTful API with authentication
  │   ├── Frontend App: React-based user interface
  │   ├── Database: PostgreSQL with proper schemas
  │   └── Testing: Unit, integration, and E2E tests
  ├── Marketing Preparation: Prepare go-to-market strategy
  │   ├── Content Creation: Blog posts, demos, and docs
  │   ├── Social Media: Set up accounts and content calendar
  │   └── Launch Campaign: Email and advertising campaigns
  └── Operations Setup: Prepare for user onboarding
      ├── Support System: Help desk and documentation
      ├── Analytics: User tracking and business metrics
      └── Monitoring: Error tracking and performance monitoring"""
}])
```

### Workflow Example
1. `set_goals` with tree format to create complex hierarchy
2. `assess_goal` on main goal to see completion status
3. `plan_for_goal` to see execution order and next steps
4. Work on first incomplete goal from plan
5. `mark_goals` when goals are completed
6. Repeat until main goal is achieved