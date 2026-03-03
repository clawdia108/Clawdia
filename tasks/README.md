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

## Required fields

- `id`
- `title`
- `status`
- `priority`
- `owner`
- `created_at`
- `updated_at`
- `summary`

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
