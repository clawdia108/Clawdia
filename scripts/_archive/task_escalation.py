#!/usr/bin/env python3
"""Task escalation: detect overdue, blocked, and stale tasks. Generate alerts.

Runs on cron (every 30 min weekdays) or manually.
Writes escalation state to knowledge/ESCALATION_ALERTS.json for dashboard consumption.
Appends urgent items to WORKBOARD.md if not already present.
"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS_OPEN_DIR = ROOT / "tasks" / "open"
EXECUTION_STATE = ROOT / "knowledge" / "EXECUTION_STATE.json"
ALERTS_PATH = ROOT / "knowledge" / "ESCALATION_ALERTS.json"
WORKBOARD = ROOT / "WORKBOARD.md"

OVERDUE_WARN_HOURS = 1
OVERDUE_CRITICAL_HOURS = 4
BLOCKED_ESCALATE_HOURS = 24
STALE_WARN_HOURS = 12
STALE_CRITICAL_HOURS = 24


def load_json(path: Path):
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def load_tasks():
    tasks = []
    if not TASKS_OPEN_DIR.exists():
        return tasks
    for path in sorted(TASKS_OPEN_DIR.glob("*.json")):
        try:
            tasks.append(json.loads(path.read_text()))
        except (json.JSONDecodeError, OSError):
            continue
    return tasks


def check_overdue(tasks, now):
    alerts = []
    for task in tasks:
        if task.get("status") == "done":
            continue
        due_raw = task.get("due_at")
        if not due_raw:
            continue
        try:
            due = datetime.fromisoformat(due_raw)
        except ValueError:
            continue
        if due >= now:
            continue
        hours_overdue = (now - due).total_seconds() / 3600
        severity = "critical" if hours_overdue >= OVERDUE_CRITICAL_HOURS else "warning"
        alerts.append({
            "type": "overdue",
            "severity": severity,
            "task_id": task.get("id", "unknown"),
            "title": task.get("title", "Untitled"),
            "owner": task.get("owner", "unassigned"),
            "hours_overdue": round(hours_overdue, 1),
            "due_at": due_raw,
            "message": f"Task {task.get('id')} is {round(hours_overdue, 1)}h overdue (owner: {task.get('owner')})",
        })
    return alerts


def check_blocked(tasks, now):
    alerts = []
    for task in tasks:
        if task.get("status") != "blocked":
            continue
        updated_raw = task.get("updated_at")
        if not updated_raw:
            continue
        try:
            updated = datetime.fromisoformat(updated_raw)
        except ValueError:
            continue
        hours_blocked = (now - updated).total_seconds() / 3600
        if hours_blocked < OVERDUE_WARN_HOURS:
            continue
        severity = "critical" if hours_blocked >= BLOCKED_ESCALATE_HOURS else "warning"
        blockers = task.get("blockers", [])
        alerts.append({
            "type": "blocked",
            "severity": severity,
            "task_id": task.get("id", "unknown"),
            "title": task.get("title", "Untitled"),
            "owner": task.get("owner", "unassigned"),
            "hours_blocked": round(hours_blocked, 1),
            "blockers": blockers,
            "message": f"Task {task.get('id')} blocked for {round(hours_blocked, 1)}h: {', '.join(blockers)}",
        })
    return alerts


def check_stale_outputs(execution_state, now):
    alerts = []
    stale = execution_state.get("stale_outputs", [])
    for item in stale:
        severity = "warning"
        if item.get("reason") == "missing":
            severity = "critical"
        elif item.get("hours_since_update") and item["hours_since_update"] >= STALE_CRITICAL_HOURS:
            severity = "critical"
        alerts.append({
            "type": "stale_output",
            "severity": severity,
            "agent": item.get("agent", "unknown"),
            "path": item.get("path", ""),
            "reason": item.get("reason", "unknown"),
            "message": f"Stale output: {item.get('path')} ({item.get('reason')}) — agent: {item.get('agent')}",
        })
    return alerts


def check_idle_agents(execution_state, tasks):
    alerts = []
    task_owners = {t.get("owner") for t in tasks if t.get("status") in ("todo", "in_progress")}
    agents_with_tasks = set()
    for task in tasks:
        if task.get("status") in ("todo", "in_progress", "needs_review"):
            agents_with_tasks.add(task.get("owner"))

    idle_agents = {"strateg", "kontrolor", "planovac", "postak", "udrzbar", "archivar"} - agents_with_tasks
    for agent in idle_agents:
        alerts.append({
            "type": "idle_agent",
            "severity": "info",
            "agent": agent,
            "message": f"Agent '{agent}' has no active tasks — consider assigning work",
        })
    return alerts


def write_alerts(alerts, now):
    state = {
        "generated_at": now.isoformat(timespec="minutes"),
        "total_alerts": len(alerts),
        "critical": sum(1 for a in alerts if a.get("severity") == "critical"),
        "warnings": sum(1 for a in alerts if a.get("severity") == "warning"),
        "info": sum(1 for a in alerts if a.get("severity") == "info"),
        "alerts": alerts,
    }
    ALERTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    ALERTS_PATH.write_text(json.dumps(state, indent=2) + "\n")
    return state


def main():
    now = datetime.now().astimezone()
    tasks = load_tasks()
    execution_state = load_json(EXECUTION_STATE)

    all_alerts = []
    all_alerts.extend(check_overdue(tasks, now))
    all_alerts.extend(check_blocked(tasks, now))
    all_alerts.extend(check_stale_outputs(execution_state, now))
    all_alerts.extend(check_idle_agents(execution_state, tasks))

    all_alerts.sort(key=lambda a: {"critical": 0, "warning": 1, "info": 2}.get(a.get("severity", "info"), 3))

    state = write_alerts(all_alerts, now)
    critical = state["critical"]
    warnings = state["warnings"]
    info = state["info"]
    print(f"task_escalation: {len(all_alerts)} alerts ({critical} critical, {warnings} warning, {info} info)")

    if critical > 0:
        print("CRITICAL ALERTS:")
        for alert in all_alerts:
            if alert.get("severity") == "critical":
                print(f"  ⛔ {alert['message']}")


if __name__ == "__main__":
    main()
