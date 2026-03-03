# Tasks

Structured task files are the control-plane handoff layer for this workspace.

## Layout

- `tasks/open/` holds active task JSON files
- `tasks/done/` holds completed task JSON files
- `tasks/templates/task.json` is the canonical shape

## Rules

- One file per task
- File name: `<priority>-<task-id>.json`
- Use agent ids from `control-plane/agent-registry.json`
- Keep task content sanitized for git
- Store identifiers, categories, and workflow state
- Do not store live customer names, emails, phones, or message bodies
- Prefer structured fields over prose notes
- Every task should be routable without rereading long markdown history

## Required fields

- `id`
- `title`
- `task_type`
- `status`
- `priority`
- `owner`
- `created_at`
- `updated_at`
- `summary`
- `complexity`
- `risk_level`
- `coordination_pattern`
- `expected_output_contract`
- `approval_state`

## Status values

- `todo`
- `in_progress`
- `blocked`
- `needs_review`
- `done`

## Suggested workflow

1. Bridge or a specialist creates a task in `tasks/open/`
2. Owning agent updates `status`, `artifacts`, and `blockers`
3. Reviewer uses `needs_review` when a deliverable must be checked
4. Completed tasks move to `tasks/done/`
5. `scripts/knowledge_sync.py` turns task state into dashboards
6. `scripts/resolve_task_route.py` resolves the execution pattern and model route

## New routing fields

- `task_type` – stable classifier used by the router
- `risk_level` – `low`, `medium`, `high`, `critical`
- `coordination_pattern` – one of `control-plane/coordination-patterns.json`
- `expected_output_contract` – one of `control-plane/output-contracts.json`
- `approval_state` – `not_required`, `pending_bridge`, `pending_human`, `approved`, `rejected`
- `session_id` / `trace_id` – runtime continuity and observability hooks
- `route_snapshot` – frozen routing decision for audits and resumability
