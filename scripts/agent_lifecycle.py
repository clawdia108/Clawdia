#!/usr/bin/env python3
"""
Agent Lifecycle Manager — State machine + Performance Analytics + Smart Notifications
=======================================================================================
Manages the complete lifecycle of each agent:
  idle → assigned → working → reviewing → done → idle

Tracks performance metrics per agent over time.
Smart notifications: groups, suppresses, escalates.
"""

import json
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

BASE = Path("/Users/josefhofman/Clawdia")
AGENT_STATE_FILE = BASE / "control-plane" / "agent-states.json"
PERF_FILE = BASE / "logs" / "agent-performance.json"
NOTIFICATION_STATE = BASE / "logs" / "notification-state.json"
LIFECYCLE_LOG = BASE / "logs" / "agent-lifecycle.log"

# Agent definitions with capabilities
AGENTS = {
    "spojka": {"display": "Spojka", "tier": "economy", "capabilities": ["briefing", "synthesis"]},
    "obchodak": {"display": "Obchodák", "tier": "economy", "capabilities": ["crm", "scoring"]},
    "postak": {"display": "Pošťák", "tier": "standard", "capabilities": ["email", "drafting"]},
    "strateg": {"display": "Stratég", "tier": "standard", "capabilities": ["research", "intel"]},
    "kalendar": {"display": "Kalendář", "tier": "economy", "capabilities": ["calendar", "scheduling"]},
    "kontrolor": {"display": "Kontrolor", "tier": "economy", "capabilities": ["review", "quality"]},
    "archivar": {"display": "Archivář", "tier": "economy", "capabilities": ["knowledge", "archive"]},
    "udrzbar": {"display": "Údržbář", "tier": "economy", "capabilities": ["crm", "priorities"]},
    "textar": {"display": "Textař", "tier": "standard", "capabilities": ["writing", "email"]},
    "hlidac": {"display": "Hlídač", "tier": "free", "capabilities": ["tracking", "gamification"]},
    "planovac": {"display": "Plánovač", "tier": "economy", "capabilities": ["planning", "focus"]},
    "vyvojar": {"display": "Vývojář", "tier": "premium", "capabilities": ["code", "analysis"]},
}

# Valid state transitions
TRANSITIONS = {
    "idle": ["assigned"],
    "assigned": ["working", "idle"],
    "working": ["reviewing", "done", "failed", "idle"],
    "reviewing": ["done", "working", "failed"],
    "done": ["idle"],
    "failed": ["idle", "assigned"],
}

STUCK_THRESHOLDS = {
    "assigned": 30,   # minutes before escalation
    "working": 120,   # 2 hours
    "reviewing": 60,  # 1 hour
}


def llog(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    LIFECYCLE_LOG.parent.mkdir(exist_ok=True)
    with open(LIFECYCLE_LOG, "a") as f:
        f.write(line + "\n")


# ── AGENT STATE MACHINE ────────────────────────────
class AgentStateMachine:
    def __init__(self):
        self.states = self._load()

    def _load(self):
        if AGENT_STATE_FILE.exists():
            try:
                return json.loads(AGENT_STATE_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return self._init_states()

    def _init_states(self):
        states = {}
        for agent_id, config in AGENTS.items():
            states[agent_id] = {
                "state": "idle",
                "current_task": None,
                "entered_state_at": datetime.now().isoformat(),
                "total_tasks_completed": 0,
                "total_tasks_failed": 0,
                "total_time_working_minutes": 0,
                "last_completed_at": None,
                "consecutive_failures": 0,
            }
        return states

    def _save(self):
        AGENT_STATE_FILE.parent.mkdir(exist_ok=True)
        AGENT_STATE_FILE.write_text(json.dumps(self.states, indent=2))

    def transition(self, agent_id, new_state, task_id=None, context=None):
        """Transition agent to new state with validation"""
        if agent_id not in self.states:
            self.states[agent_id] = self._init_states().get(agent_id, {
                "state": "idle", "entered_state_at": datetime.now().isoformat(),
            })

        current = self.states[agent_id]["state"]
        valid = TRANSITIONS.get(current, [])

        if new_state not in valid:
            llog(f"Invalid transition: {agent_id} {current} → {new_state}", "WARN")
            return False

        old_entered = self.states[agent_id].get("entered_state_at")

        # Track time in previous state
        if old_entered and current in ("working", "reviewing"):
            elapsed = (datetime.now() - datetime.fromisoformat(old_entered)).total_seconds() / 60
            self.states[agent_id]["total_time_working_minutes"] = \
                self.states[agent_id].get("total_time_working_minutes", 0) + elapsed

        self.states[agent_id]["state"] = new_state
        self.states[agent_id]["entered_state_at"] = datetime.now().isoformat()

        if new_state == "assigned":
            self.states[agent_id]["current_task"] = task_id

        elif new_state == "done":
            self.states[agent_id]["total_tasks_completed"] = \
                self.states[agent_id].get("total_tasks_completed", 0) + 1
            self.states[agent_id]["last_completed_at"] = datetime.now().isoformat()
            self.states[agent_id]["consecutive_failures"] = 0
            self.states[agent_id]["current_task"] = None

        elif new_state == "failed":
            self.states[agent_id]["total_tasks_failed"] = \
                self.states[agent_id].get("total_tasks_failed", 0) + 1
            self.states[agent_id]["consecutive_failures"] = \
                self.states[agent_id].get("consecutive_failures", 0) + 1

        elif new_state == "idle":
            self.states[agent_id]["current_task"] = None

        self._save()
        llog(f"Transition: {agent_id} {current} → {new_state}" + (f" (task={task_id})" if task_id else ""))
        return True

    def check_stuck_agents(self):
        """Find agents stuck in a state too long"""
        stuck = []
        now = datetime.now()

        for agent_id, state in self.states.items():
            current = state.get("state", "idle")
            threshold = STUCK_THRESHOLDS.get(current)
            if not threshold:
                continue

            entered = state.get("entered_state_at")
            if not entered:
                continue

            elapsed_min = (now - datetime.fromisoformat(entered)).total_seconds() / 60
            if elapsed_min > threshold:
                stuck.append({
                    "agent": agent_id,
                    "state": current,
                    "elapsed_minutes": int(elapsed_min),
                    "threshold": threshold,
                    "task": state.get("current_task"),
                })

        return stuck

    def get_available_agents(self, capability=None):
        """Find idle agents, optionally filtered by capability"""
        available = []
        for agent_id, state in self.states.items():
            if state.get("state") != "idle":
                continue
            if capability:
                agent_caps = AGENTS.get(agent_id, {}).get("capabilities", [])
                if capability not in agent_caps:
                    continue
            available.append(agent_id)
        return available

    def summary(self):
        """Get agent status summary"""
        by_state = defaultdict(list)
        for agent_id, state in self.states.items():
            by_state[state.get("state", "unknown")].append(agent_id)
        return dict(by_state)


# ── PERFORMANCE ANALYTICS ──────────────────────────
class PerformanceTracker:
    def __init__(self):
        self.data = self._load()

    def _load(self):
        if PERF_FILE.exists():
            try:
                return json.loads(PERF_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {"agents": {}, "daily": {}}

    def _save(self):
        PERF_FILE.parent.mkdir(exist_ok=True)
        PERF_FILE.write_text(json.dumps(self.data, indent=2))

    def record_completion(self, agent_id, task_type, duration_minutes, success=True):
        """Record a task completion for an agent"""
        agents = self.data.setdefault("agents", {})
        agent = agents.setdefault(agent_id, {
            "total_completed": 0, "total_failed": 0,
            "avg_duration_minutes": 0, "task_types": {},
        })

        if success:
            agent["total_completed"] += 1
            # Running average
            old_avg = agent.get("avg_duration_minutes", 0)
            n = agent["total_completed"]
            agent["avg_duration_minutes"] = round((old_avg * (n - 1) + duration_minutes) / n, 1)
        else:
            agent["total_failed"] += 1

        # Track by task type
        types = agent.setdefault("task_types", {})
        tt = types.setdefault(task_type, {"completed": 0, "failed": 0})
        tt["completed" if success else "failed"] += 1

        # Daily tracking
        today = date.today().isoformat()
        daily = self.data.setdefault("daily", {})
        day = daily.setdefault(today, {"completions": 0, "failures": 0, "agents_active": set()})
        if isinstance(day.get("agents_active"), set):
            day["agents_active"] = list(day["agents_active"])
        day["completions" if success else "failures"] += 1
        if agent_id not in day.get("agents_active", []):
            day.setdefault("agents_active", []).append(agent_id)

        self._save()

    def agent_score(self, agent_id):
        """Calculate agent effectiveness score (0-100)"""
        agent = self.data.get("agents", {}).get(agent_id, {})
        completed = agent.get("total_completed", 0)
        failed = agent.get("total_failed", 0)
        total = completed + failed

        if total == 0:
            return 50  # No data, neutral score

        success_rate = completed / total
        avg_duration = agent.get("avg_duration_minutes", 60)

        # Score: 70% success rate + 30% speed
        speed_score = max(0, min(100, (120 - avg_duration) / 120 * 100))
        return round(success_rate * 70 + (speed_score / 100) * 30)

    def weekly_report(self):
        """Generate weekly performance report"""
        today = date.today()
        report = {"week_start": (today - timedelta(days=today.weekday())).isoformat()}

        # Agent rankings
        rankings = []
        for agent_id in AGENTS:
            score = self.agent_score(agent_id)
            agent_data = self.data.get("agents", {}).get(agent_id, {})
            rankings.append({
                "agent": agent_id,
                "score": score,
                "completed": agent_data.get("total_completed", 0),
                "failed": agent_data.get("total_failed", 0),
                "avg_minutes": agent_data.get("avg_duration_minutes", 0),
            })

        rankings.sort(key=lambda x: x["score"], reverse=True)
        report["rankings"] = rankings

        # Daily trend
        daily = self.data.get("daily", {})
        week_days = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
        report["daily_trend"] = {
            d: daily.get(d, {"completions": 0, "failures": 0})
            for d in week_days
        }

        return report

    def identify_bottlenecks(self):
        """Find agents that are slowing things down"""
        bottlenecks = []
        for agent_id, agent_data in self.data.get("agents", {}).items():
            completed = agent_data.get("total_completed", 0)
            failed = agent_data.get("total_failed", 0)
            total = completed + failed

            if total < 3:
                continue

            fail_rate = failed / total if total > 0 else 0
            avg_duration = agent_data.get("avg_duration_minutes", 0)

            if fail_rate > 0.3:
                bottlenecks.append({
                    "agent": agent_id,
                    "issue": "high_failure_rate",
                    "fail_rate": round(fail_rate * 100, 1),
                    "total": total,
                })
            elif avg_duration > 120:
                bottlenecks.append({
                    "agent": agent_id,
                    "issue": "slow",
                    "avg_minutes": round(avg_duration, 1),
                })

        return bottlenecks


# ── SMART NOTIFICATIONS ────────────────────────────
class SmartNotifier:
    """Context-aware notification engine: groups, suppresses, escalates"""

    FOCUS_HOURS = (9, 12)  # Don't interrupt during deep work
    MIN_INTERVAL_MINUTES = 15  # Min time between notifications
    BATCH_DELAY_SECONDS = 30  # Wait before sending to batch
    ESCALATION_THRESHOLD = 3  # Critical alerts bypass all suppression

    def __init__(self):
        self.state = self._load()

    def _load(self):
        if NOTIFICATION_STATE.exists():
            try:
                return json.loads(NOTIFICATION_STATE.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "last_sent_at": None,
            "pending": [],
            "sent_today": 0,
            "suppressed_today": 0,
            "daily_digest": [],
        }

    def _save(self):
        NOTIFICATION_STATE.parent.mkdir(exist_ok=True)
        NOTIFICATION_STATE.write_text(json.dumps(self.state, indent=2))

    def _should_suppress(self, priority):
        """Check if notification should be suppressed"""
        now = datetime.now()
        hour = now.hour

        # Never suppress P0
        if priority == "P0":
            return False

        # Suppress during focus hours for non-critical
        if self.FOCUS_HOURS[0] <= hour <= self.FOCUS_HOURS[1] and priority != "P1":
            return True

        # Rate limit
        last_sent = self.state.get("last_sent_at")
        if last_sent:
            elapsed = (now - datetime.fromisoformat(last_sent)).total_seconds() / 60
            if elapsed < self.MIN_INTERVAL_MINUTES and priority not in ("P0", "P1"):
                return True

        return False

    def queue(self, title, message, priority="P2", source="system"):
        """Queue a notification. May be suppressed, batched, or sent immediately."""
        notification = {
            "title": title,
            "message": message,
            "priority": priority,
            "source": source,
            "timestamp": datetime.now().isoformat(),
        }

        if self._should_suppress(priority):
            self.state["suppressed_today"] = self.state.get("suppressed_today", 0) + 1
            self.state.setdefault("daily_digest", []).append(notification)
            llog(f"Notification suppressed: [{priority}] {title}")
            self._save()
            return "suppressed"

        # P0: send immediately
        if priority == "P0":
            self._send(title, message, "Basso")
            return "sent"

        # P1: send with small delay
        if priority == "P1":
            self._send(title, message, "Ping")
            return "sent"

        # P2/P3: batch into pending
        self.state.setdefault("pending", []).append(notification)
        self._save()

        # If we have 3+ pending, send batch
        if len(self.state.get("pending", [])) >= 3:
            self._send_batch()
            return "batched"

        return "queued"

    def _send(self, title, message, sound="default"):
        """Actually send a macOS notification"""
        import subprocess
        try:
            subprocess.run(
                ["bash", str(BASE / "scripts" / "notify.sh"), title, message, sound],
                capture_output=True, timeout=10,
            )
            self.state["last_sent_at"] = datetime.now().isoformat()
            self.state["sent_today"] = self.state.get("sent_today", 0) + 1
            self._save()
            llog(f"Notification sent: {title}")
        except Exception:
            pass

    def _send_batch(self):
        """Send batched notifications as a single summary"""
        pending = self.state.get("pending", [])
        if not pending:
            return

        count = len(pending)
        titles = [n["title"] for n in pending[:3]]
        summary = f"{count} aktualizací: {', '.join(titles)}"
        self._send("Clawdia", summary, "Pop")
        self.state["pending"] = []
        self._save()

    def send_daily_digest(self):
        """Send daily summary of suppressed notifications"""
        digest = self.state.get("daily_digest", [])
        if not digest:
            return

        self._send(
            "Denní souhrn",
            f"{len(digest)} notifikací během dne. Check system-status.sh pro detaily.",
            "Glass",
        )

        # Reset daily counters
        self.state["daily_digest"] = []
        self.state["sent_today"] = 0
        self.state["suppressed_today"] = 0
        self._save()

    def stats(self):
        return {
            "sent_today": self.state.get("sent_today", 0),
            "suppressed_today": self.state.get("suppressed_today", 0),
            "pending": len(self.state.get("pending", [])),
            "daily_digest": len(self.state.get("daily_digest", [])),
        }


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "states":
            sm = AgentStateMachine()
            print(json.dumps(sm.summary(), indent=2))

        elif cmd == "stuck":
            sm = AgentStateMachine()
            stuck = sm.check_stuck_agents()
            if stuck:
                for s in stuck:
                    print(f"  STUCK: {s['agent']} in '{s['state']}' for {s['elapsed_minutes']}min (threshold: {s['threshold']}min)")
            else:
                print("  No stuck agents")

        elif cmd == "available":
            sm = AgentStateMachine()
            cap = sys.argv[2] if len(sys.argv) > 2 else None
            available = sm.get_available_agents(cap)
            print(f"Available agents: {', '.join(available) or 'none'}")

        elif cmd == "perf":
            pt = PerformanceTracker()
            report = pt.weekly_report()
            print(json.dumps(report, indent=2, default=str))

        elif cmd == "bottlenecks":
            pt = PerformanceTracker()
            bottlenecks = pt.identify_bottlenecks()
            if bottlenecks:
                for b in bottlenecks:
                    print(f"  {b['agent']}: {b['issue']}")
            else:
                print("  No bottlenecks detected")

        elif cmd == "notify":
            sn = SmartNotifier()
            print(json.dumps(sn.stats(), indent=2))

        else:
            print("Usage: agent_lifecycle.py [states|stuck|available [cap]|perf|bottlenecks|notify]")
    else:
        sm = AgentStateMachine()
        print("Agent States:", json.dumps(sm.summary(), indent=2))
