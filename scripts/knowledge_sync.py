#!/usr/bin/env python3
"""Knowledge sync: aggregate task state, detect stale outputs, archive learnings.

Generates:
  - knowledge/AGENT_INSIGHTS.md   — per-agent task snapshot + stale output warnings
  - knowledge/TODAY_SUMMARY.md    — priority view for the day
  - reviews/PENDING_REVIEWS.md    — tasks awaiting review or blocked
  - knowledge/IMPROVEMENTS.md     — learnings extracted from completed tasks (append-only)
"""
import json
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "control-plane" / "agent-registry.json"
TASKS_OPEN_DIR = ROOT / "tasks" / "open"
TASKS_DONE_DIR = ROOT / "tasks" / "done"
KNOWLEDGE_INSIGHTS = ROOT / "knowledge" / "AGENT_INSIGHTS.md"
TODAY_SUMMARY = ROOT / "knowledge" / "TODAY_SUMMARY.md"
PENDING_REVIEWS = ROOT / "reviews" / "PENDING_REVIEWS.md"
IMPROVEMENTS = ROOT / "knowledge" / "IMPROVEMENTS.md"
EXECUTION_STATE = ROOT / "knowledge" / "EXECUTION_STATE.json"


PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
ACTIVE_STATUSES = {"todo", "in_progress", "blocked", "needs_review"}
STALE_THRESHOLD_HOURS = 24


@dataclass
class Task:
    path: Path
    data: dict

    @property
    def task_id(self) -> str:
        return self.data.get("id", self.path.stem)

    @property
    def title(self) -> str:
        return self.data.get("title", "Untitled task")

    @property
    def owner(self) -> str:
        return self.data.get("owner", "unassigned")

    @property
    def status(self) -> str:
        return self.data.get("status", "todo")

    @property
    def priority(self) -> str:
        return self.data.get("priority", "P3")

    @property
    def complexity(self) -> str:
        return self.data.get("complexity", "medium")

    @property
    def task_type(self) -> str:
        return self.data.get("task_type", "general")

    @property
    def risk_level(self) -> str:
        return self.data.get("risk_level", "medium")

    @property
    def output_visibility(self) -> str:
        return self.data.get("output_visibility", "internal")

    @property
    def approval_state(self) -> str:
        return self.data.get("approval_state", "not_required")

    @property
    def depends_on(self) -> list:
        return self.data.get("depends_on", [])

    @property
    def due_at(self):
        raw = self.data.get("due_at")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None

    @property
    def updated_at(self):
        raw = self.data.get("updated_at")
        if not raw:
            return None
        try:
            return datetime.fromisoformat(raw)
        except ValueError:
            return None


def load_json(path: Path):
    return json.loads(path.read_text())


def load_registry():
    return load_json(REGISTRY_PATH)


def load_tasks(directory: Path):
    tasks = []
    if not directory.exists():
        return tasks
    for path in sorted(directory.glob("*.json")):
        try:
            tasks.append(Task(path=path, data=load_json(path)))
        except (json.JSONDecodeError, OSError):
            continue
    return tasks


def format_dt(value):
    if not value:
        return "n/a"
    return value.isoformat(timespec="minutes")


def sort_tasks(tasks):
    return sorted(
        tasks,
        key=lambda task: (
            PRIORITY_ORDER.get(task.priority, 99),
            task.due_at or datetime.max.replace(tzinfo=timezone.utc),
            task.task_id,
        ),
    )


# ──────────────────────────────────────────────────
# Stale output detection
# ──────────────────────────────────────────────────

def detect_stale_outputs(registry) -> list[dict]:
    """Check agent output files for staleness (not updated within threshold)."""
    now = datetime.now().astimezone()
    threshold = now - timedelta(hours=STALE_THRESHOLD_HOURS)
    stale = []

    for agent_id, meta in registry["agents"].items():
        for output_path in meta.get("writes_to", []):
            full_path = ROOT / output_path
            if output_path.endswith("/"):
                continue
            if not full_path.exists():
                stale.append({
                    "agent": agent_id,
                    "path": output_path,
                    "reason": "missing",
                    "last_modified": None,
                })
                continue
            size = full_path.stat().st_size
            mtime = datetime.fromtimestamp(full_path.stat().st_mtime).astimezone()
            if size < 50:
                stale.append({
                    "agent": agent_id,
                    "path": output_path,
                    "reason": "empty_placeholder",
                    "last_modified": format_dt(mtime),
                    "size_bytes": size,
                })
            elif mtime < threshold:
                stale.append({
                    "agent": agent_id,
                    "path": output_path,
                    "reason": "stale",
                    "last_modified": format_dt(mtime),
                    "hours_since_update": round((now - mtime).total_seconds() / 3600, 1),
                })

    return stale


# ──────────────────────────────────────────────────
# Done-task archival and learning extraction
# ──────────────────────────────────────────────────

def archive_done_tasks(open_tasks) -> list[dict]:
    """Move done tasks from open/ to done/ and extract learnings."""
    archived = []
    for task in open_tasks:
        if task.status != "done":
            continue
        dest = TASKS_DONE_DIR / task.path.name
        shutil.move(str(task.path), str(dest))
        archived.append({
            "task_id": task.task_id,
            "title": task.title,
            "owner": task.owner,
            "complexity": task.complexity,
        })
    return archived


def write_improvements(archived_tasks):
    """Append learnings from archived tasks to IMPROVEMENTS.md."""
    if not archived_tasks:
        return

    now = datetime.now().astimezone()
    existing = ""
    if IMPROVEMENTS.exists():
        existing = IMPROVEMENTS.read_text()

    if not existing.strip() or existing.strip() == "#":
        lines = ["# IMPROVEMENTS", "", "Learnings extracted from completed tasks.", ""]
    else:
        lines = [existing.rstrip(), ""]

    lines.append(f"## {now.strftime('%Y-%m-%d')}")
    for task in archived_tasks:
        lines.append(
            f"- `{task['task_id']}` ({task['owner']}, {task['complexity']}): {task['title']}"
        )
    lines.append("")

    IMPROVEMENTS.write_text("\n".join(lines))


# ──────────────────────────────────────────────────
# Cross-agent dependency analysis
# ──────────────────────────────────────────────────

def analyze_dependencies(open_tasks) -> list[str]:
    """Detect dependency issues: missing deps, blocked chains."""
    open_ids = {t.task_id for t in open_tasks}
    status_map = {t.task_id: t.status for t in open_tasks}
    issues = []

    for task in open_tasks:
        for dep_id in task.depends_on:
            if dep_id not in open_ids:
                done_matches = list(TASKS_DONE_DIR.glob(f"*{dep_id}*"))
                if not done_matches:
                    issues.append(
                        f"`{task.task_id}` depends on `{dep_id}` which is neither open nor done"
                    )
            elif status_map.get(dep_id) == "blocked":
                issues.append(
                    f"`{task.task_id}` depends on `{dep_id}` which is blocked — chain stall"
                )

    return issues


# ──────────────────────────────────────────────────
# Output generators
# ──────────────────────────────────────────────────

def summarize_agent_outputs(outputs):
    lines = []
    for output in outputs:
        if output.endswith("/"):
            continue
        path = ROOT / output
        if path.exists():
            mtime = datetime.fromtimestamp(path.stat().st_mtime).astimezone()
            size = path.stat().st_size
            if size < 50:
                lines.append(f"- `{output}` placeholder ({size}B)")
            else:
                lines.append(f"- `{output}` updated {format_dt(mtime)}")
        else:
            lines.append(f"- `{output}` missing")
    return lines


def write_agent_insights(registry, open_tasks, done_tasks, stale_outputs, dep_issues):
    now = datetime.now().astimezone()
    by_owner = defaultdict(list)
    for task in open_tasks:
        by_owner[task.owner].append(task)

    lines = [
        "# AGENT_INSIGHTS",
        "",
        f"Generated by `scripts/knowledge_sync.py` at {format_dt(now)}.",
        "",
        "## System Snapshot",
        f"- Open tasks: {len(open_tasks)}",
        f"- Completed tasks archived: {len(done_tasks)}",
        f"- Blocked tasks: {sum(1 for t in open_tasks if t.status == 'blocked')}",
        f"- Tasks awaiting review: {sum(1 for t in open_tasks if t.status == 'needs_review')}",
        f"- Stale/missing outputs: {len(stale_outputs)}",
        f"- Dependency issues: {len(dep_issues)}",
        "",
    ]

    if stale_outputs:
        lines.append("## Stale Outputs")
        for item in stale_outputs:
            reason = item["reason"]
            if reason == "missing":
                lines.append(f"- **{item['agent']}**: `{item['path']}` — file missing")
            elif reason == "empty_placeholder":
                lines.append(
                    f"- **{item['agent']}**: `{item['path']}` — "
                    f"empty placeholder ({item['size_bytes']}B)"
                )
            elif reason == "stale":
                lines.append(
                    f"- **{item['agent']}**: `{item['path']}` — "
                    f"{item['hours_since_update']}h since update"
                )
        lines.append("")

    if dep_issues:
        lines.append("## Dependency Issues")
        for issue in dep_issues:
            lines.append(f"- {issue}")
        lines.append("")

    for agent_id, meta in registry["agents"].items():
        if agent_id == registry["main_agent"]:
            continue
        tasks = sort_tasks(by_owner.get(agent_id, []))
        display_name = meta["display_name"]
        tier = meta.get("preferred_model_tier", "standard")
        lines.append(f"## {display_name}")
        lines.append(f"- Agent id: `{agent_id}` | Model tier: `{tier}`")
        lines.append(f"- Active tasks: {len(tasks)}")
        if tasks:
            lines.append(
                "- Top tasks: "
                + ", ".join(
                    f"`{t.task_id}` ({t.status}, {t.priority}, {t.complexity})"
                    for t in tasks[:3]
                )
            )
        else:
            lines.append("- Top tasks: none")
        lines.extend(summarize_agent_outputs(meta.get("writes_to", []))[:3])
        lines.append("")

    KNOWLEDGE_INSIGHTS.write_text("\n".join(lines).rstrip() + "\n")


def write_today_summary(open_tasks, dep_issues):
    now = datetime.now().astimezone()
    active = sort_tasks([t for t in open_tasks if t.status in ACTIVE_STATUSES])
    blocked = [t for t in active if t.status == "blocked"]
    due_soon = [t for t in active if t.due_at][:5]

    lines = [
        "# TODAY_SUMMARY",
        "",
        f"Generated by `scripts/knowledge_sync.py` at {format_dt(now)}.",
        "",
        "## Priorities",
    ]
    if active:
        for task in active[:5]:
            lines.append(
                f"- `{task.task_id}` `{task.priority}` `{task.complexity}` "
                f"`{task.owner}` due {format_dt(task.due_at)}: {task.title}"
            )
    else:
        lines.append("- No open tasks.")

    lines.extend(["", "## Blockers"])
    if blocked:
        for task in blocked:
            blocker_text = ", ".join(task.data.get("blockers", [])) or "unspecified blocker"
            lines.append(f"- `{task.task_id}` `{task.owner}`: {blocker_text}")
    else:
        lines.append("- No blocked tasks.")

    if dep_issues:
        lines.extend(["", "## Dependency Chains"])
        for issue in dep_issues:
            lines.append(f"- {issue}")

    lines.extend(["", "## Next Deadlines"])
    if due_soon:
        for task in due_soon:
            lines.append(f"- `{task.task_id}` due {format_dt(task.due_at)}")
    else:
        lines.append("- No dated tasks.")

    TODAY_SUMMARY.write_text("\n".join(lines).rstrip() + "\n")


def write_pending_reviews(open_tasks):
    review_tasks = sort_tasks(
        [t for t in open_tasks if t.status in {"blocked", "needs_review"}]
    )
    review_required = sort_tasks(
        [t for t in open_tasks if t.data.get("review_required") and t.status == "in_progress"]
    )
    now = datetime.now().astimezone()
    lines = [
        "# PENDING_REVIEWS",
        "",
        f"Generated by `scripts/knowledge_sync.py` at {format_dt(now)}.",
        "",
    ]

    if review_tasks:
        lines.append("## Blocked / Needs Review")
        for task in review_tasks:
            reviewer = task.data.get("reviewer", "reviewer")
            lines.append(
                f"- `{task.task_id}` owned by `{task.owner}` "
                f"status `{task.status}` reviewer `{reviewer}`"
            )
        lines.append("")

    if review_required:
        lines.append("## In-Progress (review required on completion)")
        for task in review_required:
            reviewer = task.data.get("reviewer", "reviewer")
            lines.append(
                f"- `{task.task_id}` owned by `{task.owner}` "
                f"complexity `{task.complexity}` reviewer `{reviewer}`"
            )
        lines.append("")

    if not review_tasks and not review_required:
        lines.append("- No pending reviews.")

    PENDING_REVIEWS.write_text("\n".join(lines).rstrip() + "\n")


def serialize_task(task: Task) -> dict:
    return {
        "task_id": task.task_id,
        "title": task.title,
        "task_type": task.task_type,
        "status": task.status,
        "priority": task.priority,
        "owner": task.owner,
        "complexity": task.complexity,
        "risk_level": task.risk_level,
        "approval_state": task.approval_state,
        "output_visibility": task.output_visibility,
        "summary": task.data.get("summary"),
        "user_summary": task.data.get("user_summary"),
        "due_at": format_dt(task.due_at),
        "updated_at": format_dt(task.updated_at),
        "blockers": task.data.get("blockers", []),
        "route_snapshot": task.data.get("route_snapshot", {}),
    }


def write_execution_state(open_tasks, done_tasks, archived, stale_outputs, dep_issues):
    active = sort_tasks([t for t in open_tasks if t.status in ACTIVE_STATUSES])
    blocked = [t for t in active if t.status == "blocked"]
    needs_review = [t for t in active if t.status == "needs_review"]
    recent_done = sort_tasks(done_tasks)[-3:]
    state = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="minutes"),
        "counts": {
            "open": len(open_tasks),
            "done": len(done_tasks),
            "blocked": len(blocked),
            "needs_review": len(needs_review),
            "stale_outputs": len(stale_outputs),
            "dependency_issues": len(dep_issues),
        },
        "top_priorities": [serialize_task(task) for task in active[:5]],
        "blocked_tasks": [serialize_task(task) for task in blocked[:5]],
        "needs_review": [serialize_task(task) for task in needs_review[:5]],
        "recently_completed": [serialize_task(task) for task in recent_done],
        "recently_archived": archived,
        "stale_outputs": stale_outputs,
        "dependency_issues": dep_issues,
        "tasks": [serialize_task(task) for task in active],
    }
    EXECUTION_STATE.write_text(json.dumps(state, indent=2) + "\n")


# ──────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────

def main():
    registry = load_registry()
    open_tasks = load_tasks(TASKS_OPEN_DIR)
    done_tasks = load_tasks(TASKS_DONE_DIR)

    # Archive done tasks from open/ to done/
    archived = archive_done_tasks(open_tasks)
    if archived:
        write_improvements(archived)
        open_tasks = load_tasks(TASKS_OPEN_DIR)
        done_tasks = load_tasks(TASKS_DONE_DIR)

    # Detect stale outputs
    stale_outputs = detect_stale_outputs(registry)

    # Analyze dependency chains
    dep_issues = analyze_dependencies(open_tasks)

    # Generate reports
    write_agent_insights(registry, open_tasks, done_tasks, stale_outputs, dep_issues)
    write_today_summary(open_tasks, dep_issues)
    write_pending_reviews(open_tasks)
    write_execution_state(open_tasks, done_tasks, archived, stale_outputs, dep_issues)

    # Print summary for cron logs
    print(
        f"knowledge_sync: {len(open_tasks)} open, {len(done_tasks)} done, "
        f"{len(archived)} archived, {len(stale_outputs)} stale, {len(dep_issues)} dep issues"
    )


if __name__ == "__main__":
    main()
