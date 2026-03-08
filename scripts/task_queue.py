#!/usr/bin/env python3
"""
Task Priority Queue + Skill Router + Load Balancer + Dispatcher
================================================================
Central task management for the Clawdia agent system.

- TaskPriorityQueue: P0-P3 priority queue with age escalation
- SkillRouter: Matches tasks to agents by capability/load/history
- AgentLoadBalancer: Per-agent concurrency limits
- TaskDispatcher: Ties it all together — pull, route, assign, dispatch
"""

import json
import sys
import time
import uuid
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

# Resolve project root and add scripts to path
BASE = Path("/Users/josefhofman/Clawdia")
sys.path.insert(0, str(BASE / "scripts"))

from agent_lifecycle import AGENTS, AgentStateMachine, PerformanceTracker
from agent_bus import AgentBus, publish

TASK_QUEUE_FILE = BASE / "control-plane" / "task-queue.json"
AGENT_LOAD_FILE = BASE / "control-plane" / "agent-load.json"
PERF_FILE = BASE / "logs" / "agent-performance.json"
DISPATCH_LOG = BASE / "logs" / "task-dispatch.log"

PRIORITIES = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
PRIORITY_LABELS = {"P0": "CRITICAL", "P1": "HIGH", "P2": "MEDIUM", "P3": "LOW"}

# Age escalation thresholds (hours)
ESCALATION_RULES = {
    "P2": {"threshold_hours": 4, "escalate_to": "P1"},
    "P1": {"threshold_hours": 8, "escalate_to": "P0"},
}

# Concurrency limits by tier
CONCURRENCY_LIMITS = {
    "premium": 2,
    "standard": 1,
    "economy": 1,
    "free": 1,
}


def dlog(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    DISPATCH_LOG.parent.mkdir(exist_ok=True)
    with open(DISPATCH_LOG, "a") as f:
        f.write(line + "\n")


# ── TASK PRIORITY QUEUE ──────────────────────────────
class TaskPriorityQueue:
    """Priority queue with P0 > P1 > P2 > P3, FIFO within each level, age escalation."""

    def __init__(self):
        self.tasks = self._load()

    def _load(self):
        if TASK_QUEUE_FILE.exists():
            try:
                data = json.loads(TASK_QUEUE_FILE.read_text())
                return data.get("tasks", [])
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def _save(self):
        TASK_QUEUE_FILE.parent.mkdir(exist_ok=True)
        data = {
            "version": 1,
            "updated_at": datetime.now().isoformat(),
            "task_count": len(self.tasks),
            "tasks": self.tasks,
        }
        TASK_QUEUE_FILE.write_text(json.dumps(data, indent=2))

    def _sort_key(self, task):
        """Sort by priority (lower = higher priority), then by created_at (FIFO)."""
        p = PRIORITIES.get(task.get("priority", "P3"), 3)
        created = task.get("created_at", "")
        return (p, created)

    def enqueue(self, title, description="", priority="P2", required_capabilities=None, deadline=None):
        """Add a task to the queue. Returns the new task."""
        task = {
            "task_id": uuid.uuid4().hex[:12],
            "title": title,
            "description": description,
            "priority": priority,
            "original_priority": priority,
            "required_capabilities": required_capabilities or [],
            "created_at": datetime.now().isoformat(),
            "assigned_to": None,
            "status": "pending",
            "deadline": deadline,
            "escalation_count": 0,
        }
        self.tasks.append(task)
        self.tasks.sort(key=self._sort_key)
        self._save()
        dlog(f"ENQUEUE [{priority}] {title} (id={task['task_id']})")
        return task

    def dequeue(self):
        """Remove and return the highest-priority pending task."""
        self.tasks.sort(key=self._sort_key)
        for i, task in enumerate(self.tasks):
            if task.get("status") == "pending":
                task["status"] = "dequeued"
                self._save()
                dlog(f"DEQUEUE [{task['priority']}] {task['title']} (id={task['task_id']})")
                return task
        return None

    def peek(self):
        """View the highest-priority pending task without removing it."""
        self.tasks.sort(key=self._sort_key)
        for task in self.tasks:
            if task.get("status") == "pending":
                return task
        return None

    def escalate_aged(self):
        """Auto-escalate tasks that have been sitting too long."""
        now = datetime.now()
        escalated = []

        for task in self.tasks:
            if task.get("status") != "pending":
                continue

            priority = task.get("priority", "P3")
            rule = ESCALATION_RULES.get(priority)
            if not rule:
                continue

            created = datetime.fromisoformat(task["created_at"])
            age_hours = (now - created).total_seconds() / 3600

            if age_hours >= rule["threshold_hours"]:
                old_priority = task["priority"]
                task["priority"] = rule["escalate_to"]
                task["escalation_count"] = task.get("escalation_count", 0) + 1
                escalated.append({
                    "task_id": task["task_id"],
                    "title": task["title"],
                    "from": old_priority,
                    "to": rule["escalate_to"],
                    "age_hours": round(age_hours, 1),
                })
                dlog(f"ESCALATE {task['task_id']} {old_priority} → {rule['escalate_to']} (age={round(age_hours, 1)}h)")

        if escalated:
            self.tasks.sort(key=self._sort_key)
            self._save()

        return escalated

    def reassign(self, task_id, new_agent_id):
        """Reassign a task to a different agent."""
        for task in self.tasks:
            if task["task_id"] == task_id:
                old_agent = task.get("assigned_to")
                task["assigned_to"] = new_agent_id
                task["status"] = "assigned"
                self._save()
                dlog(f"REASSIGN {task_id} {old_agent} → {new_agent_id}")
                return task
        return None

    def cancel(self, task_id):
        """Cancel a task by ID."""
        for task in self.tasks:
            if task["task_id"] == task_id:
                task["status"] = "cancelled"
                task["cancelled_at"] = datetime.now().isoformat()
                self._save()
                dlog(f"CANCEL {task_id} ({task['title']})")
                return task
        return None

    def complete(self, task_id):
        """Mark a task as done."""
        for task in self.tasks:
            if task["task_id"] == task_id:
                task["status"] = "done"
                task["completed_at"] = datetime.now().isoformat()
                self._save()
                dlog(f"COMPLETE {task_id} ({task['title']})")
                return task
        return None

    def get_task(self, task_id):
        """Get a task by ID."""
        for task in self.tasks:
            if task["task_id"] == task_id:
                return task
        return None

    def list_tasks(self, status=None):
        """List tasks, optionally filtered by status."""
        self.tasks.sort(key=self._sort_key)
        if status:
            return [t for t in self.tasks if t.get("status") == status]
        return list(self.tasks)

    def stats(self):
        """Queue statistics."""
        by_status = defaultdict(int)
        by_priority = defaultdict(int)
        for t in self.tasks:
            by_status[t.get("status", "unknown")] += 1
            if t.get("status") == "pending":
                by_priority[t.get("priority", "P3")] += 1
        return {
            "total": len(self.tasks),
            "by_status": dict(by_status),
            "pending_by_priority": dict(by_priority),
        }


# ── SKILL ROUTER ─────────────────────────────────────
class SkillRouter:
    """Routes tasks to best-fit agents based on capabilities, load, and history.

    Scoring weights:
      - Capability match: 60%
      - Current load (lower = better): 20%
      - Past success rate: 20%
    """

    WEIGHT_CAPABILITY = 0.60
    WEIGHT_LOAD = 0.20
    WEIGHT_SUCCESS = 0.20

    def __init__(self):
        self.perf = PerformanceTracker()
        self.load_balancer = AgentLoadBalancer()

    def _capability_score(self, agent_id, task):
        """Score 0-100 based on capability overlap."""
        required = set(task.get("required_capabilities", []))
        if not required:
            return 50  # No requirements = neutral score

        agent_caps = set(AGENTS.get(agent_id, {}).get("capabilities", []))
        if not agent_caps:
            return 0

        overlap = required & agent_caps
        return int(len(overlap) / len(required) * 100)

    def _load_score(self, agent_id):
        """Score 0-100 based on current load (lower load = higher score)."""
        status = self.load_balancer.load_status()
        agent_info = status.get(agent_id, {})
        active = agent_info.get("active_tasks", 0)
        limit = agent_info.get("limit", 1)

        if active >= limit:
            return 0  # At capacity
        return int((1 - active / limit) * 100)

    def _success_score(self, agent_id):
        """Score 0-100 based on past success rate."""
        return self.perf.agent_score(agent_id)

    def score_agent(self, agent_id, task):
        """Calculate composite score for an agent on a given task."""
        cap = self._capability_score(agent_id, task)
        load = self._load_score(agent_id)
        success = self._success_score(agent_id)

        composite = (
            cap * self.WEIGHT_CAPABILITY +
            load * self.WEIGHT_LOAD +
            success * self.WEIGHT_SUCCESS
        )

        return {
            "agent_id": agent_id,
            "display": AGENTS.get(agent_id, {}).get("display", agent_id),
            "composite": round(composite, 1),
            "capability": cap,
            "load": load,
            "success": success,
            "can_accept": load > 0,
        }

    def route(self, task):
        """Return ranked list of agents for a given task, best-fit first."""
        scores = []
        for agent_id in AGENTS:
            score = self.score_agent(agent_id, task)
            # Only include agents with at least some capability match
            # (or if no capabilities are required)
            if score["capability"] > 0 or not task.get("required_capabilities"):
                scores.append(score)

        scores.sort(key=lambda s: s["composite"], reverse=True)
        return scores

    def get_best_agent(self, task):
        """Return the single best available agent for a task, or None."""
        ranked = self.route(task)
        for agent in ranked:
            if agent["can_accept"]:
                return agent
        return None


# ── AGENT LOAD BALANCER ──────────────────────────────
class AgentLoadBalancer:
    """Tracks and enforces per-agent concurrency limits."""

    def __init__(self):
        self.data = self._load()

    def _load(self):
        if AGENT_LOAD_FILE.exists():
            try:
                return json.loads(AGENT_LOAD_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {"agents": {}}

    def _save(self):
        AGENT_LOAD_FILE.parent.mkdir(exist_ok=True)
        self.data["updated_at"] = datetime.now().isoformat()
        AGENT_LOAD_FILE.write_text(json.dumps(self.data, indent=2))

    def _get_limit(self, agent_id):
        """Get concurrency limit for an agent based on tier."""
        tier = AGENTS.get(agent_id, {}).get("tier", "economy")
        return CONCURRENCY_LIMITS.get(tier, 1)

    def _ensure_agent(self, agent_id):
        agents = self.data.setdefault("agents", {})
        if agent_id not in agents:
            agents[agent_id] = {"active_tasks": [], "total_assigned": 0, "total_released": 0}
        return agents[agent_id]

    def can_accept(self, agent_id):
        """Check if agent can accept another task."""
        agent = self._ensure_agent(agent_id)
        limit = self._get_limit(agent_id)
        return len(agent.get("active_tasks", [])) < limit

    def assign(self, agent_id, task_id):
        """Assign a task to an agent. Returns True if successful."""
        if not self.can_accept(agent_id):
            dlog(f"LOAD REJECT {agent_id} cannot accept {task_id} (at capacity)", "WARN")
            return False

        agent = self._ensure_agent(agent_id)
        if task_id not in agent["active_tasks"]:
            agent["active_tasks"].append(task_id)
        agent["total_assigned"] = agent.get("total_assigned", 0) + 1
        agent["last_assigned_at"] = datetime.now().isoformat()
        self._save()
        dlog(f"LOAD ASSIGN {agent_id} ← {task_id} (active: {len(agent['active_tasks'])})")
        return True

    def release(self, agent_id, task_id):
        """Release a task from an agent."""
        agent = self._ensure_agent(agent_id)
        if task_id in agent["active_tasks"]:
            agent["active_tasks"].remove(task_id)
            agent["total_released"] = agent.get("total_released", 0) + 1
            agent["last_released_at"] = datetime.now().isoformat()
            self._save()
            dlog(f"LOAD RELEASE {agent_id} → {task_id} (active: {len(agent['active_tasks'])})")
            return True
        return False

    def load_status(self):
        """Get load status for all agents."""
        status = {}
        for agent_id in AGENTS:
            agent = self._ensure_agent(agent_id)
            limit = self._get_limit(agent_id)
            active = agent.get("active_tasks", [])
            status[agent_id] = {
                "display": AGENTS[agent_id].get("display", agent_id),
                "tier": AGENTS[agent_id].get("tier", "economy"),
                "limit": limit,
                "active_tasks": len(active),
                "tasks": active,
                "available": len(active) < limit,
                "utilization": round(len(active) / limit * 100) if limit else 0,
            }
        return status


# ── TASK DISPATCHER ──────────────────────────────────
class TaskDispatcher:
    """Pulls tasks, routes to agents, assigns, and publishes events."""

    def __init__(self):
        self.queue = TaskPriorityQueue()
        self.router = SkillRouter()
        self.balancer = AgentLoadBalancer()
        self.lifecycle = AgentStateMachine()
        self.bus = AgentBus()

    def dispatch_next(self):
        """Dispatch the highest-priority pending task."""
        # First, run escalation
        self.queue.escalate_aged()

        task = self.queue.peek()
        if not task:
            return {"status": "empty", "message": "No pending tasks"}

        best = self.router.get_best_agent(task)
        if not best:
            return {
                "status": "no_agent",
                "message": f"No available agent for task '{task['title']}'",
                "task_id": task["task_id"],
            }

        agent_id = best["agent_id"]

        # Assign in load balancer
        if not self.balancer.assign(agent_id, task["task_id"]):
            return {
                "status": "load_rejected",
                "message": f"{agent_id} at capacity",
                "task_id": task["task_id"],
            }

        # Dequeue the task
        self.queue.dequeue()
        task["status"] = "assigned"
        task["assigned_to"] = agent_id
        task["assigned_at"] = datetime.now().isoformat()
        self.queue._save()

        # Transition agent state
        self.lifecycle.transition(agent_id, "assigned", task_id=task["task_id"])

        # Publish assignment event
        self.bus.publish(
            source="dispatcher",
            topic="system.task_assigned",
            payload={
                "task_id": task["task_id"],
                "title": task["title"],
                "agent_id": agent_id,
                "priority": task["priority"],
                "capabilities": task.get("required_capabilities", []),
                "score": best["composite"],
            },
            priority=task["priority"],
        )

        dlog(f"DISPATCH {task['task_id']} → {agent_id} (score={best['composite']})")

        return {
            "status": "dispatched",
            "task_id": task["task_id"],
            "title": task["title"],
            "agent": agent_id,
            "agent_display": best["display"],
            "score": best["composite"],
            "priority": task["priority"],
        }

    def dispatch_all_ready(self):
        """Dispatch all pending tasks that have available agents."""
        results = []
        max_iterations = 50  # safety cap

        for _ in range(max_iterations):
            result = self.dispatch_next()
            if result["status"] in ("empty", "no_agent", "load_rejected"):
                break
            results.append(result)

        return {
            "dispatched": len(results),
            "assignments": results,
            "remaining_pending": len(self.queue.list_tasks(status="pending")),
        }

    def auto_assign(self):
        """Full cycle: escalate aged tasks, then dispatch all ready."""
        escalated = self.queue.escalate_aged()
        dispatch_result = self.dispatch_all_ready()

        return {
            "escalated": len(escalated),
            "escalation_details": escalated,
            **dispatch_result,
        }


# ── CLI ──────────────────────────────────────────────
def build_parser():
    parser = argparse.ArgumentParser(
        prog="task_queue.py",
        description="Clawdia Task Queue — priority queue + skill router + load balancer",
    )
    sub = parser.add_subparsers(dest="command")

    # add
    add_p = sub.add_parser("add", help="Add a task to the queue")
    add_p.add_argument("title", help="Task title")
    add_p.add_argument("--priority", "-p", default="P2", choices=["P0", "P1", "P2", "P3"])
    add_p.add_argument("--caps", "-c", default="", help="Required capabilities (comma-separated)")
    add_p.add_argument("--desc", "-d", default="", help="Task description")
    add_p.add_argument("--deadline", default=None, help="Deadline (ISO format)")

    # list
    list_p = sub.add_parser("list", help="List tasks")
    list_p.add_argument("--status", "-s", default=None,
                        choices=["pending", "assigned", "dequeued", "done", "cancelled"])

    # dispatch
    sub.add_parser("dispatch", help="Dispatch next task (or all ready)")
    # route
    route_p = sub.add_parser("route", help="Show routing scores for a task")
    route_p.add_argument("task_id", help="Task ID to route")

    # load
    sub.add_parser("load", help="Show agent load status")

    # escalate
    sub.add_parser("escalate", help="Escalate aged tasks")

    # complete
    complete_p = sub.add_parser("complete", help="Mark a task as done")
    complete_p.add_argument("task_id", help="Task ID to complete")

    # cancel
    cancel_p = sub.add_parser("cancel", help="Cancel a task")
    cancel_p.add_argument("task_id", help="Task ID to cancel")

    # stats
    sub.add_parser("stats", help="Queue statistics")

    # auto
    sub.add_parser("auto", help="Full auto cycle: escalate + dispatch all")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    if args.command == "add":
        q = TaskPriorityQueue()
        caps = [c.strip() for c in args.caps.split(",") if c.strip()] if args.caps else []
        task = q.enqueue(
            title=args.title,
            description=args.desc,
            priority=args.priority,
            required_capabilities=caps,
            deadline=args.deadline,
        )
        label = PRIORITY_LABELS[task["priority"]]
        print(f"Added [{task['priority']}/{label}] {task['title']}")
        print(f"  ID: {task['task_id']}")
        if caps:
            print(f"  Caps: {', '.join(caps)}")

    elif args.command == "list":
        q = TaskPriorityQueue()
        tasks = q.list_tasks(status=args.status)
        if not tasks:
            status_str = f" (status={args.status})" if args.status else ""
            print(f"No tasks{status_str}")
            return

        print(f"{'ID':<14} {'P':>3} {'Status':<12} {'Agent':<18} {'Title'}")
        print("-" * 75)
        for t in tasks:
            agent = t.get("assigned_to") or "-"
            print(f"{t['task_id']:<14} {t['priority']:>3} {t['status']:<12} {agent:<18} {t['title']}")

    elif args.command == "dispatch":
        d = TaskDispatcher()
        result = d.dispatch_next()
        if result["status"] == "dispatched":
            print(f"Dispatched: {result['title']}")
            print(f"  Task: {result['task_id']}")
            print(f"  Agent: {result['agent_display']} ({result['agent']})")
            print(f"  Priority: {result['priority']}")
            print(f"  Score: {result['score']}")
        elif result["status"] == "empty":
            print("Queue empty — nothing to dispatch")
        elif result["status"] == "no_agent":
            print(f"No available agent for: {result.get('task_id', '?')}")
        elif result["status"] == "load_rejected":
            print(f"Best agent at capacity: {result.get('message', '')}")

    elif args.command == "route":
        q = TaskPriorityQueue()
        task = q.get_task(args.task_id)
        if not task:
            print(f"Task not found: {args.task_id}")
            return

        router = SkillRouter()
        scores = router.route(task)

        print(f"Routing: [{task['priority']}] {task['title']}")
        if task.get("required_capabilities"):
            print(f"Required: {', '.join(task['required_capabilities'])}")
        print()
        print(f"{'#':<4} {'Agent':<20} {'Score':>6} {'Cap':>5} {'Load':>5} {'Hist':>5} {'Available'}")
        print("-" * 65)
        for i, s in enumerate(scores, 1):
            avail = "YES" if s["can_accept"] else "NO"
            print(f"{i:<4} {s['display']:<20} {s['composite']:>6.1f} {s['capability']:>5} {s['load']:>5} {s['success']:>5} {avail}")

    elif args.command == "load":
        lb = AgentLoadBalancer()
        status = lb.load_status()

        print(f"{'Agent':<20} {'Tier':<10} {'Active':>7} {'Limit':>6} {'Util':>6} {'Available'}")
        print("-" * 65)
        for agent_id, info in sorted(status.items()):
            avail = "YES" if info["available"] else "FULL"
            print(f"{info['display']:<20} {info['tier']:<10} {info['active_tasks']:>7} {info['limit']:>6} {info['utilization']:>5}% {avail}")

    elif args.command == "escalate":
        q = TaskPriorityQueue()
        escalated = q.escalate_aged()
        if not escalated:
            print("No tasks to escalate")
        else:
            for e in escalated:
                print(f"Escalated: {e['title']} {e['from']} → {e['to']} (age: {e['age_hours']}h)")

    elif args.command == "complete":
        q = TaskPriorityQueue()
        task = q.complete(args.task_id)
        if task:
            # Release from load balancer if assigned
            if task.get("assigned_to"):
                lb = AgentLoadBalancer()
                lb.release(task["assigned_to"], args.task_id)
                sm = AgentStateMachine()
                sm.transition(task["assigned_to"], "done")
                sm.transition(task["assigned_to"], "idle")
            print(f"Completed: {task['title']}")
        else:
            print(f"Task not found: {args.task_id}")

    elif args.command == "cancel":
        q = TaskPriorityQueue()
        task = q.cancel(args.task_id)
        if task:
            if task.get("assigned_to"):
                lb = AgentLoadBalancer()
                lb.release(task["assigned_to"], args.task_id)
                sm = AgentStateMachine()
                sm.transition(task["assigned_to"], "idle")
            print(f"Cancelled: {task['title']}")
        else:
            print(f"Task not found: {args.task_id}")

    elif args.command == "stats":
        q = TaskPriorityQueue()
        s = q.stats()
        print(f"Total tasks: {s['total']}")
        print(f"By status: {json.dumps(s['by_status'])}")
        print(f"Pending by priority: {json.dumps(s['pending_by_priority'])}")

    elif args.command == "auto":
        d = TaskDispatcher()
        result = d.auto_assign()
        print(f"Escalated: {result['escalated']} tasks")
        for e in result.get("escalation_details", []):
            print(f"  {e['title']}: {e['from']} → {e['to']}")
        print(f"Dispatched: {result['dispatched']} tasks")
        for a in result.get("assignments", []):
            print(f"  {a['title']} → {a['agent_display']} (score={a['score']})")
        print(f"Remaining pending: {result['remaining_pending']}")


if __name__ == "__main__":
    main()
