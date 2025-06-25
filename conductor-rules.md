# Conductor MCP Tool Usage Rules

**Purpose:**
These rules guide the use of Conductor MCP tools for effective, goal-oriented project management in AI-assisted coding environments. They ensure clarity, efficiency, and best practices when working with goals, plans, and progress tracking.

## 1. Goal-Oriented Actions
- **Always start by defining or clarifying the high-level goal before taking action.**
- Use `set_goals` to register new goals or update existing ones.
  - *Example: To start a new feature, first define it as a goal using `set_goals`.*

## 2. Planning and Dependencies
- Use `plan_for_goal` to generate an execution plan and visualize dependencies before starting work on a complex goal.
  - *Example: Before implementing a multi-step feature, call `plan_for_goal` to see all required steps and their order.*
- If a goal is blocked, use `assess_goal` to check its status and prerequisites.

## 3. Stepwise Progression
- Mark goals or steps as completed using `mark_goals` immediately after finishing them.
  - *Example: After completing a subtask, call `mark_goals` to update its status.*
- Use `add_steps` to break down large goals into actionable steps.
  - *Example: For a large refactor, use `add_steps` to list each file or module to update.*

## 4. Status and Progress Tracking
- Regularly check the status of goals with `assess_goal` to ensure alignment and progress.
  - *Example: Use `assess_goal` before starting new work to avoid duplicating effort.*
- Use status checks before starting new work to avoid duplicating effort or working on blocked items.

## 5. Documentation and Rationale
- Document each tool call with a brief explanation of its purpose and expected outcome.
  - *Example: "Calling `plan_for_goal` to visualize dependencies before starting implementation."*

## 6. Error Handling
- If a tool call fails or a goal is blocked, check prerequisites, input formats, and dependencies before retrying or escalating.
  - *Example: If `mark_goals` fails, use `assess_goal` to check for unmet prerequisites.*

## 7. Efficiency
- Avoid redundant tool calls by caching recent results where appropriate.
  - *Example: If you already have a plan for a goal, reuse it instead of calling `plan_for_goal` again unless something has changed.*
