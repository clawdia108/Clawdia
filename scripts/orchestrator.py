#!/usr/bin/env python3
"""
OpenClaw Orchestrator v2 — Full Agent Lifecycle Manager
========================================================
The brain of Clawdia. Manages everything:
- Agent health monitoring & auto-recovery
- Task dispatch & lifecycle (assign → execute → review → complete)
- Inter-agent trigger system (event-driven, not just batch)
- Approval queue processing
- Circuit breaker for external APIs
- Cost tracking per model/task
- Nightly maintenance (git sync, knowledge sync, archival)
- ADHD scorecard integration

Runs as a KeepAlive launchd service with configurable cycle intervals.
"""

import json
import os
import signal
import subprocess
import sys
import time
import hashlib
import fcntl
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

# ── SHUTDOWN HANDLER ───────────────────────────────
_shutdown_requested = False
_current_cycle_running = False


def _signal_handler(signum, frame):
    """Handle SIGTERM/SIGINT gracefully — finish current cycle, then exit."""
    global _shutdown_requested
    sig_name = signal.Signals(signum).name
    _shutdown_requested = True
    if _current_cycle_running:
        # Let the current cycle finish
        print(f"\n[SHUTDOWN] {sig_name} received — finishing current cycle, then exiting...", flush=True)
    else:
        print(f"\n[SHUTDOWN] {sig_name} received — exiting cleanly.", flush=True)


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


# ── FILE LOCKING ──────────────────────────────────
class FileLock:
    """Advisory file locking to prevent concurrent writes to state files."""

    def __init__(self, path):
        self.path = Path(str(path) + ".lock")
        self._fd = None

    def __enter__(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fd = open(self.path, "w")
        try:
            fcntl.flock(self._fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            # Another process holds the lock — wait up to 10s
            fcntl.flock(self._fd, fcntl.LOCK_EX)
        return self

    def __exit__(self, *args):
        if self._fd:
            fcntl.flock(self._fd, fcntl.LOCK_UN)
            self._fd.close()
            self._fd = None
            try:
                self.path.unlink(missing_ok=True)
            except OSError:
                pass


def safe_json_write(path, data):
    """Atomically write JSON with file locking and backup."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # Backup current version
    if path.exists():
        bak = path.with_suffix(path.suffix + ".bak")
        try:
            bak.write_text(path.read_text())
        except OSError:
            pass

    with FileLock(path):
        tmp = path.with_suffix(path.suffix + ".tmp")
        try:
            content = json.dumps(data, indent=2, ensure_ascii=False)
            tmp.write_text(content)
            tmp.rename(path)  # Atomic on same filesystem
        except Exception:
            # Restore from backup
            if path.with_suffix(path.suffix + ".bak").exists():
                path.with_suffix(path.suffix + ".bak").rename(path)
            raise


# ── PATHS ──────────────────────────────────────────
BASE = Path("/Users/josefhofman/Clawdia")
LOG = BASE / "logs" / "orchestrator.log"
PID_FILE = BASE / "logs" / "orchestrator.pid"
COST_LOG = BASE / "logs" / "cost-tracker.json"
CIRCUIT_STATE = BASE / "logs" / "circuit-breaker.json"
TRIGGER_DIR = BASE / "triggers"
TRIGGER_OUTBOX = TRIGGER_DIR / "outbox"
TRIGGER_PROCESSED = TRIGGER_DIR / "processed"
APPROVAL_DIR = BASE / "approval-queue"
STATE_FILE = BASE / "knowledge" / "EXECUTION_STATE.json"
HEARTBEAT_FILE = BASE / "memory" / "HEARTBEAT.md"
EVENT_LOG = BASE / "logs" / "events.jsonl"
RECOVERY_LOG = BASE / "logs" / "recovery.log"

# ── CONFIG ─────────────────────────────────────────
CYCLE_SECONDS = 1800  # 30 min cycles (was 1h)
WORK_HOURS = (7, 20)  # Work hours range
NIGHTLY_HOUR = 23  # Run nightly tasks at 11 PM
MAX_RECOVERY_ATTEMPTS = 3
CIRCUIT_BREAKER_THRESHOLD = 3  # failures before opening circuit
CIRCUIT_BREAKER_RESET_SECONDS = 300  # 5 min cooldown

# Agent output definitions: (file_path, max_age_hours, recovery_script)
AGENT_OUTPUTS = {
    "spojka": {
        "file": "knowledge/USER_DIGEST_AM.md",
        "max_hours": 24,
        "recovery": "morning-briefing.sh",
    },
    "obchodak": {
        "file": "pipedrive/PIPELINE_STATUS.md",
        "max_hours": 48,
        "recovery": "pipedrive_lead_scorer.py",
    },
    "postak": {
        "file": "inbox/INBOX_DIGEST.md",
        "max_hours": 24,
        "recovery": "recover_inbox.py",
    },
    "strateg": {
        "file": "intel/DAILY-INTEL.md",
        "max_hours": 48,
        "recovery": "recover_intel.py",
    },
    "kalendar": {
        "file": "calendar/TODAY.md",
        "max_hours": 24,
        "recovery": "recover_calendar.py",
    },
    "kontrolor": {
        "file": "reviews/SYSTEM_HEALTH.md",
        "max_hours": 72,
        "recovery": "recover_kontrolor.py",
    },
    "archivar": {
        "file": "knowledge/IMPROVEMENTS.md",
        "max_hours": 72,
        "recovery": "knowledge_sync.py",
    },
}


# ── LOGGING ────────────────────────────────────────
def log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line, flush=True)
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(line + "\n")
    # Keep log file under 500KB
    if LOG.stat().st_size > 500_000:
        _rotate_log()


def _rotate_log():
    backup = LOG.with_suffix(".log.old")
    if backup.exists():
        backup.unlink()
    LOG.rename(backup)
    LOG.touch()
    log("Log rotated")


def log_event(event_type, data):
    """Append structured event to events.jsonl for analytics"""
    event = {
        "ts": datetime.now().isoformat(),
        "type": event_type,
        **data,
    }
    EVENT_LOG.parent.mkdir(exist_ok=True)
    with open(EVENT_LOG, "a") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")


# ── NOTIFICATIONS ──────────────────────────────────
def notify(title, message, sound="default"):
    """Send notification via Telegram + macOS fallback."""
    # Telegram first
    try:
        subprocess.run(
            ["python3", str(BASE / "scripts" / "telegram_notify.py"), "send",
             f"⚙️ *{title}*\n{message}"],
            capture_output=True, timeout=15,
        )
    except Exception:
        pass
    # macOS fallback
    try:
        subprocess.run(
            ["bash", str(BASE / "scripts" / "notify.sh"), title, message, sound],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass


def notify_uncertain(agent_id, question, context=None):
    """When an agent doesn't know what to do — ask Josef directly via Telegram."""
    try:
        from telegram_notify import agent_uncertain
        agent_uncertain(agent_id, question, context)
    except ImportError:
        try:
            subprocess.run(
                ["python3", str(BASE / "scripts" / "telegram_notify.py"),
                 "uncertain", agent_id, question],
                capture_output=True, timeout=15,
            )
        except Exception:
            pass


# ── CIRCUIT BREAKER ────────────────────────────────
class CircuitBreaker:
    """Track API failures per service. Open circuit after N failures, auto-reset after cooldown."""

    def __init__(self):
        self.state = self._load()

    def _load(self):
        if CIRCUIT_STATE.exists():
            try:
                return json.loads(CIRCUIT_STATE.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save(self):
        safe_json_write(CIRCUIT_STATE, self.state)

    def record_failure(self, service):
        entry = self.state.setdefault(service, {"failures": 0, "last_failure": None, "open": False})
        entry["failures"] += 1
        entry["last_failure"] = datetime.now().isoformat()
        if entry["failures"] >= CIRCUIT_BREAKER_THRESHOLD:
            entry["open"] = True
            log(f"CIRCUIT OPEN: {service} ({entry['failures']} consecutive failures)", "WARN")
            log_event("circuit_open", {"service": service, "failures": entry["failures"]})
        self._save()

    def record_success(self, service):
        if service in self.state:
            self.state[service] = {"failures": 0, "last_failure": None, "open": False}
            self._save()

    def is_open(self, service):
        entry = self.state.get(service)
        if not entry or not entry.get("open"):
            return False
        # Auto-reset after cooldown
        last = entry.get("last_failure")
        if last:
            elapsed = (datetime.now() - datetime.fromisoformat(last)).total_seconds()
            if elapsed > CIRCUIT_BREAKER_RESET_SECONDS:
                entry["open"] = False
                entry["failures"] = 0
                self._save()
                log(f"CIRCUIT RESET: {service} (cooldown elapsed)", "INFO")
                return False
        return True

    def status(self):
        return {k: {"open": v.get("open", False), "failures": v.get("failures", 0)}
                for k, v in self.state.items()}


# ── COST TRACKER ───────────────────────────────────
class CostTracker:
    """Track API costs per model, per task, per day."""

    PRICING = {
        "claude-opus-4-6": {"input": 0.015, "output": 0.075},
        "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
        "claude-3-5-haiku-latest": {"input": 0.0008, "output": 0.004},
        "gpt-5.2": {"input": 0.00175, "output": 0.007},
        "gpt-5-mini": {"input": 0.0004, "output": 0.0016},
        "gpt-5-nano": {"input": 0.00005, "output": 0.0002},
        "ollama/llama3.1:8b": {"input": 0, "output": 0},
    }

    DAILY_BUDGETS = {
        "free": 0,
        "economy": 3.0,
        "standard": 8.0,
        "premium": 20.0,
    }

    def __init__(self):
        self.data = self._load()

    def _load(self):
        if COST_LOG.exists():
            try:
                return json.loads(COST_LOG.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {"daily": {}, "total": 0, "by_model": {}, "by_task_type": {}}

    def _save(self):
        safe_json_write(COST_LOG, self.data)

    def record(self, model, task_type, input_tokens=0, output_tokens=0):
        pricing = self.PRICING.get(model, {"input": 0.003, "output": 0.015})
        cost = (input_tokens / 1_000_000) * pricing["input"] + (output_tokens / 1_000_000) * pricing["output"]

        today = date.today().isoformat()
        daily = self.data.setdefault("daily", {})
        daily.setdefault(today, 0)
        daily[today] += cost
        self.data["total"] = self.data.get("total", 0) + cost

        by_model = self.data.setdefault("by_model", {})
        by_model.setdefault(model, 0)
        by_model[model] += cost

        by_task = self.data.setdefault("by_task_type", {})
        by_task.setdefault(task_type, 0)
        by_task[task_type] += cost

        self._save()
        return cost

    def today_spend(self):
        today = date.today().isoformat()
        return self.data.get("daily", {}).get(today, 0)

    def summary(self):
        today = date.today().isoformat()
        return {
            "today": round(self.data.get("daily", {}).get(today, 0), 4),
            "total": round(self.data.get("total", 0), 4),
            "top_models": dict(sorted(
                self.data.get("by_model", {}).items(),
                key=lambda x: x[1], reverse=True
            )[:5]),
        }


# ── OLLAMA INTEGRATION ─────────────────────────────
def ollama_call(subcommand, text, timeout=60):
    """Call Ollama router for free local classification"""
    try:
        result = subprocess.run(
            [str(BASE / "scripts" / "ollama-router.sh"), subcommand, text],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        log(f"Ollama timeout on {subcommand}", "WARN")
        return None
    except Exception as e:
        log(f"Ollama error: {e}", "ERROR")
        return None


def ollama_available():
    """Quick health check for Ollama"""
    try:
        result = subprocess.run(
            ["curl", "-s", "-m", "3", "http://localhost:11434/api/tags"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return len(data.get("models", [])) > 0
    except Exception:
        pass
    return False


# ── AGENT HEALTH & RECOVERY ────────────────────────
def check_agent_health():
    """Check all agent outputs, return health status"""
    now = time.time()
    results = {}

    for agent, config in AGENT_OUTPUTS.items():
        path = BASE / config["file"]
        max_hours = config["max_hours"]

        if not path.exists():
            results[agent] = {"status": "DEAD", "reason": "file missing", "age_hours": None}
            continue

        size = path.stat().st_size
        if size < 50:
            results[agent] = {"status": "EMPTY", "reason": f"placeholder ({size}B)", "age_hours": None}
            continue

        age_hours = (now - path.stat().st_mtime) / 3600
        if age_hours > max_hours:
            results[agent] = {"status": "STALE", "reason": f"{int(age_hours)}h old (max {max_hours}h)", "age_hours": age_hours}
        else:
            results[agent] = {"status": "OK", "reason": f"{int(age_hours)}h old", "age_hours": age_hours}

    return results


def attempt_recovery(agent, config, circuit_breaker):
    """Try to auto-recover a stale/dead agent by running its recovery script"""
    recovery_script = config.get("recovery")
    if not recovery_script:
        log(f"No recovery script for {agent}", "WARN")
        return False

    # Check circuit breaker
    service_key = f"recovery_{agent}"
    if circuit_breaker.is_open(service_key):
        log(f"Circuit open for {agent} recovery, skipping", "WARN")
        return False

    script_path = BASE / "scripts" / recovery_script
    if not script_path.exists():
        log(f"Recovery script not found: {recovery_script}", "ERROR")
        return False

    log(f"Attempting recovery for {agent} via {recovery_script}")
    log_event("recovery_attempt", {"agent": agent, "script": recovery_script})

    try:
        if recovery_script.endswith(".py"):
            cmd = ["python3", str(script_path)]
        else:
            cmd = ["bash", str(script_path)]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            cwd=str(BASE),
        )

        if result.returncode == 0:
            log(f"Recovery SUCCESS for {agent}: {result.stdout[:200]}")
            circuit_breaker.record_success(service_key)
            log_event("recovery_success", {"agent": agent})

            # Log to recovery log
            with open(RECOVERY_LOG, "a") as f:
                f.write(f"[{datetime.now().isoformat()}] SUCCESS {agent} via {recovery_script}\n")
            return True
        else:
            log(f"Recovery FAILED for {agent}: {result.stderr[:200]}", "ERROR")
            circuit_breaker.record_failure(service_key)
            log_event("recovery_failure", {"agent": agent, "error": result.stderr[:200]})
            notify_uncertain(agent, f"Recovery selhala. Chyba: {result.stderr[:150]}", f"Script: {recovery_script}")
            return False

    except subprocess.TimeoutExpired:
        log(f"Recovery TIMEOUT for {agent}", "ERROR")
        circuit_breaker.record_failure(service_key)
        return False
    except Exception as e:
        log(f"Recovery ERROR for {agent}: {e}", "ERROR")
        circuit_breaker.record_failure(service_key)
        return False


def run_health_and_recovery(circuit_breaker):
    """Full health check cycle with auto-recovery for stale agents"""
    health = check_agent_health()

    ok = sum(1 for v in health.values() if v["status"] == "OK")
    total = len(health)
    stale = [k for k, v in health.items() if v["status"] in ("STALE", "DEAD", "EMPTY")]

    log(f"Health: {ok}/{total} healthy, {len(stale)} need attention")

    # Try to recover stale agents
    recovered = []
    for agent in stale:
        config = AGENT_OUTPUTS[agent]
        if config.get("recovery"):
            success = attempt_recovery(agent, config, circuit_breaker)
            if success:
                recovered.append(agent)

    if recovered:
        log(f"Recovered {len(recovered)} agents: {', '.join(recovered)}")
        notify("Clawdia", f"Obnoveno {len(recovered)} agentů: {', '.join(recovered)}", "Glass")

    # Run heartbeat script to generate HEARTBEAT.md
    try:
        subprocess.run(
            ["bash", str(BASE / "scripts" / "heartbeat-check.sh")],
            capture_output=True, timeout=30,
        )
    except Exception as e:
        log(f"Heartbeat script error: {e}", "ERROR")

    return health, recovered


# ── TRIGGER SYSTEM ──────────────────────────────────
def setup_trigger_dirs():
    """Ensure trigger directories exist"""
    for d in [TRIGGER_DIR, TRIGGER_OUTBOX, TRIGGER_PROCESSED]:
        d.mkdir(parents=True, exist_ok=True)


def emit_trigger(source_agent, event_type, payload=None):
    """Emit an inter-agent trigger event"""
    setup_trigger_dirs()
    trigger = {
        "source": source_agent,
        "event": event_type,
        "payload": payload or {},
        "timestamp": datetime.now().isoformat(),
        "id": hashlib.md5(f"{source_agent}:{event_type}:{time.time()}".encode()).hexdigest()[:12],
    }
    filename = f"{trigger['id']}_{event_type}.json"
    (TRIGGER_OUTBOX / filename).write_text(json.dumps(trigger, indent=2))
    log(f"Trigger emitted: {source_agent} → {event_type}")
    log_event("trigger_emitted", {"source": source_agent, "event": event_type})
    return trigger


# Trigger routing rules: event → list of (agent, action_script)
TRIGGER_ROUTES = {
    "pipeline_scored": [
        ("postak", "generate_follow_ups"),
        ("udrzbar", "update_priorities"),
    ],
    "stale_deals_found": [
        ("postak", "draft_follow_ups"),
    ],
    "morning_briefing_ready": [
        ("kalendar", "update_today"),
        ("planovac", "generate_plan"),
    ],
    "deal_won": [
        ("hlidac", "log_achievement"),
        ("textar", "draft_onboarding"),
    ],
    "approval_approved": [
        ("postak", "send_approved_emails"),
    ],
    "agent_recovered": [
        ("kontrolor", "log_recovery"),
    ],
    "knowledge_synced": [
        ("archivar", "process_insights"),
    ],
}


def process_triggers():
    """Process all pending triggers in outbox"""
    setup_trigger_dirs()
    processed = 0

    for trigger_file in sorted(TRIGGER_OUTBOX.glob("*.json")):
        try:
            trigger = json.loads(trigger_file.read_text())
            event = trigger.get("event", "")
            routes = TRIGGER_ROUTES.get(event, [])

            if routes:
                log(f"Processing trigger {event} → {len(routes)} target(s)")
                for target_agent, action in routes:
                    log_event("trigger_dispatched", {
                        "event": event,
                        "source": trigger.get("source"),
                        "target": target_agent,
                        "action": action,
                    })

            # Move to processed
            dest = TRIGGER_PROCESSED / trigger_file.name
            trigger_file.rename(dest)
            processed += 1

        except (json.JSONDecodeError, OSError) as e:
            log(f"Invalid trigger file {trigger_file.name}: {e}", "WARN")
            trigger_file.unlink(missing_ok=True)

    if processed:
        log(f"Processed {processed} triggers")
    return processed


# ── APPROVAL QUEUE ──────────────────────────────────
def process_approval_queue():
    """Check for pending and approved items, process approved ones"""
    pending_dir = APPROVAL_DIR / "pending"
    approved_dir = APPROVAL_DIR / "approved"
    rejected_dir = APPROVAL_DIR / "rejected"
    expired_dir = APPROVAL_DIR / "expired"

    for d in [pending_dir, approved_dir, rejected_dir, expired_dir]:
        d.mkdir(parents=True, exist_ok=True)

    pending = list(pending_dir.glob("*.json")) + list(pending_dir.glob("*.md"))
    approved = list(approved_dir.glob("*.json")) + list(approved_dir.glob("*.md"))

    # Expire old pending items (> 48h)
    now = time.time()
    expired_count = 0
    for item in pending:
        age_hours = (now - item.stat().st_mtime) / 3600
        if age_hours > 48:
            item.rename(expired_dir / item.name)
            expired_count += 1
            log(f"Expired approval: {item.name} ({int(age_hours)}h old)")

    # Process approved items
    processed_count = 0
    for item in approved:
        try:
            if item.suffix == ".json":
                data = json.loads(item.read_text())
                action_type = data.get("action_type", "unknown")
                log(f"Executing approved action: {action_type} ({item.name})")
                log_event("approval_executed", {"action": action_type, "file": item.name})

                # Emit trigger for downstream agents
                emit_trigger("approval_queue", "approval_approved", {
                    "action_type": action_type,
                    "file": item.name,
                })
            processed_count += 1
        except Exception as e:
            log(f"Error processing approved item {item.name}: {e}", "ERROR")

    result = {
        "pending": len(pending) - expired_count,
        "approved": len(approved),
        "expired": expired_count,
        "processed": processed_count,
    }

    if pending or approved or expired_count:
        log(f"Approval queue: {result['pending']} pending, {result['approved']} approved, {result['expired']} expired")

    return result


# ── TASK DISPATCHER ─────────────────────────────────
def load_execution_state():
    """Load current task state"""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"tasks": [], "counts": {}}


def dispatch_tasks(state):
    """Check tasks, update statuses, handle timeouts and reassignment"""
    tasks = state.get("tasks", [])
    if not tasks:
        return state

    now = datetime.now()
    changes = []

    for task in tasks:
        task_id = task.get("task_id", "?")
        status = task.get("status", "todo")
        owner = task.get("owner", "unassigned")
        due_at = task.get("due_at")

        # Skip completed tasks
        if status in ("done", "completed"):
            continue

        # Check for overdue tasks
        if due_at and due_at != "n/a":
            try:
                due = datetime.fromisoformat(due_at.replace("+01:00", "+01:00"))
                if now > due and status == "todo":
                    overdue_hours = (now - due).total_seconds() / 3600
                    if overdue_hours > 72:
                        # Auto-escalate severely overdue tasks
                        task["priority"] = "P0"
                        changes.append(f"{task_id}: escalated to P0 (overdue {int(overdue_hours)}h)")
                        log_event("task_escalated", {"task_id": task_id, "overdue_hours": int(overdue_hours)})
            except (ValueError, TypeError):
                pass

        # Check blocked tasks — can any be unblocked?
        if status == "blocked":
            blockers = task.get("blockers", [])
            if not blockers:
                task["status"] = "todo"
                changes.append(f"{task_id}: unblocked (no remaining blockers)")
                log_event("task_unblocked", {"task_id": task_id})

    if changes:
        log(f"Task dispatch: {len(changes)} changes — {'; '.join(changes[:5])}")

    return state


def update_execution_state(health_results, approval_queue, cost_summary):
    """Update the central execution state with latest data"""
    state = load_execution_state()

    # Update metadata
    state["last_orchestrator_run"] = datetime.now().isoformat()
    state["system_health"] = {
        agent: {"status": info["status"], "age_hours": info.get("age_hours")}
        for agent, info in health_results.items()
    }
    state["approval_queue"] = approval_queue
    state["cost_summary"] = cost_summary

    # Dispatch tasks
    state = dispatch_tasks(state)

    # Check stale outputs
    stale = []
    for agent, info in health_results.items():
        if info["status"] in ("STALE", "DEAD", "EMPTY"):
            stale.append({
                "agent": agent,
                "path": AGENT_OUTPUTS[agent]["file"],
                "reason": info["reason"],
            })
    state["stale_outputs"] = stale

    # Update counts
    tasks = state.get("tasks", [])
    state["counts"] = {
        "open": sum(1 for t in tasks if t.get("status") in ("todo", "in_progress", "blocked")),
        "done": sum(1 for t in tasks if t.get("status") in ("done", "completed")),
        "blocked": sum(1 for t in tasks if t.get("status") == "blocked"),
        "needs_review": sum(1 for t in tasks if t.get("status") == "needs_review"),
        "stale_outputs": len(stale),
        "healthy_agents": sum(1 for v in health_results.values() if v["status"] == "OK"),
        "total_agents": len(health_results),
    }

    safe_json_write(STATE_FILE, state)
    log(f"Execution state updated: {state['counts']}")


# ── SALES AUTOPILOT ────────────────────────────────
def run_sales_autopilot(circuit_breaker):
    """Run sales automation pipeline with circuit breaker protection"""
    if circuit_breaker.is_open("pipedrive_api"):
        log("Skipping sales autopilot — Pipedrive circuit open", "WARN")
        return "circuit_open"

    try:
        result = subprocess.run(
            ["bash", str(BASE / "scripts" / "sales-autopilot.sh")],
            capture_output=True, text=True, timeout=180,
            cwd=str(BASE),
        )
        output = result.stdout.strip()
        if result.returncode == 0:
            circuit_breaker.record_success("pipedrive_api")
            log(f"Sales autopilot: {output[:200]}")

            # Emit triggers based on results
            if "stale" in output.lower() or "without next activity" in output.lower():
                emit_trigger("sales_autopilot", "stale_deals_found", {"output": output[:500]})

            return output
        else:
            circuit_breaker.record_failure("pipedrive_api")
            log(f"Sales autopilot error: {result.stderr[:200]}", "ERROR")
            return "error"
    except subprocess.TimeoutExpired:
        log("Sales autopilot timeout", "ERROR")
        circuit_breaker.record_failure("pipedrive_api")
        return "timeout"
    except Exception as e:
        log(f"Sales autopilot exception: {e}", "ERROR")
        return "error"


# ── SCORECARD ──────────────────────────────────────
def run_scorecard():
    """Run ADHD gamification scorecard"""
    try:
        result = subprocess.run(
            ["python3", str(BASE / "scripts" / "adhd-scorecard.py")],
            capture_output=True, text=True, timeout=30,
            cwd=str(BASE),
        )
        if result.returncode == 0:
            log(f"Scorecard: {result.stdout.strip()}")

            # Check for milestone notifications
            output = result.stdout.strip()
            if "pts today" in output:
                try:
                    pts = int(output.split("pts today")[0].split()[-1].replace(",", ""))
                    if pts >= 50:
                        notify("Scorecard", f"{pts} bodů dnes!", "Glass")
                except (ValueError, IndexError):
                    pass
            return output
        else:
            log(f"Scorecard error: {result.stderr[:200]}", "WARN")
            return None
    except Exception as e:
        log(f"Scorecard error: {e}", "ERROR")
        return None


# ── KNOWLEDGE SYNC ─────────────────────────────────
def run_knowledge_sync():
    """Run knowledge sync to aggregate state and archive learnings"""
    script = BASE / "scripts" / "knowledge_sync.py"
    if not script.exists():
        return None

    try:
        result = subprocess.run(
            ["python3", str(script)],
            capture_output=True, text=True, timeout=60,
            cwd=str(BASE),
        )
        if result.returncode == 0:
            log(f"Knowledge sync: {result.stdout.strip()}")
            emit_trigger("orchestrator", "knowledge_synced")
            return result.stdout.strip()
        else:
            log(f"Knowledge sync error: {result.stderr[:300]}", "WARN")
            return None
    except Exception as e:
        log(f"Knowledge sync error: {e}", "ERROR")
        return None


# ── NIGHTLY TASKS ──────────────────────────────────
def run_nightly_tasks():
    """Run once per day at NIGHTLY_HOUR: git sync, knowledge sync, cleanup"""
    log("=== NIGHTLY TASKS STARTING ===")
    log_event("nightly_start", {})

    # 1. Knowledge sync
    run_knowledge_sync()

    # 2. Git auto-commit state files
    try:
        result = subprocess.run(
            ["bash", "-c", """
                cd /Users/josefhofman/Clawdia
                git add -A knowledge/ memory/ pipedrive/*.md reviews/ logs/cost-tracker.json logs/events.jsonl 2>/dev/null
                if ! git diff --cached --quiet 2>/dev/null; then
                    git commit -m "chore: nightly state sync $(date '+%Y-%m-%d %H:%M')" 2>/dev/null
                    echo "committed"
                else
                    echo "no changes"
                fi
            """],
            capture_output=True, text=True, timeout=30,
        )
        log(f"Nightly git sync: {result.stdout.strip()}")
    except Exception as e:
        log(f"Git sync error: {e}", "WARN")

    # 3. Cleanup old trigger files (> 7 days)
    if TRIGGER_PROCESSED.exists():
        now = time.time()
        cleaned = 0
        for f in TRIGGER_PROCESSED.glob("*.json"):
            if (now - f.stat().st_mtime) > 7 * 86400:
                f.unlink()
                cleaned += 1
        if cleaned:
            log(f"Cleaned {cleaned} old trigger files")

    # 4. Cleanup old events (keep last 10000 lines)
    if EVENT_LOG.exists() and EVENT_LOG.stat().st_size > 1_000_000:
        lines = EVENT_LOG.read_text().splitlines()
        if len(lines) > 10000:
            EVENT_LOG.write_text("\n".join(lines[-10000:]) + "\n")
            log(f"Trimmed event log from {len(lines)} to 10000 lines")

    # 5. Cost tracker daily summary
    cost = CostTracker()
    today_spend = cost.today_spend()
    if today_spend > 0:
        log(f"Today's API spend: ${today_spend:.4f}")

    log("=== NIGHTLY TASKS COMPLETE ===")
    log_event("nightly_complete", {"today_spend": today_spend})


# ── MORNING BRIEFING ───────────────────────────────
def run_morning_briefing():
    """Generate morning briefing"""
    script = BASE / "scripts" / "morning-briefing.sh"
    if not script.exists():
        return None

    try:
        result = subprocess.run(
            ["bash", str(script)],
            capture_output=True, text=True, timeout=120,
            cwd=str(BASE),
        )
        if result.returncode == 0:
            log(f"Morning briefing: generated")
            emit_trigger("orchestrator", "morning_briefing_ready")
            return result.stdout.strip()
        else:
            log(f"Morning briefing error: {result.stderr[:200]}", "WARN")
            return None
    except Exception as e:
        log(f"Morning briefing error: {e}", "ERROR")
        return None


# ── BUS & WORKFLOW INTEGRATION ──────────────────────
def run_bus_routing():
    """Route messages through agent communication bus"""
    try:
        sys.path.insert(0, str(BASE / "scripts"))
        from agent_bus import AgentBus
        bus = AgentBus()
        result = bus.route_messages()
        if result["routed"] > 0 or result["expired"] > 0:
            log(f"Bus: routed {result['routed']}, expired {result['expired']}, dead {result['dead']}")
        return result
    except Exception as e:
        log(f"Bus routing error: {e}", "ERROR")
        return {"routed": 0, "expired": 0, "dead": 0}


def check_agent_lifecycle():
    """Check agent state machine for stuck agents, update states"""
    try:
        sys.path.insert(0, str(BASE / "scripts"))
        from agent_lifecycle import AgentStateMachine, SmartNotifier
        sm = AgentStateMachine()

        # Check for stuck agents
        stuck = sm.check_stuck_agents()
        if stuck:
            notifier = SmartNotifier()
            for s in stuck:
                log(f"STUCK AGENT: {s['agent']} in '{s['state']}' for {s['elapsed_minutes']}min", "WARN")
                notifier.queue(
                    f"Agent stuck: {s['agent']}",
                    f"Ve stavu '{s['state']}' {s['elapsed_minutes']}min",
                    priority="P1",
                    source="orchestrator",
                )
                # Auto-reset to idle if stuck too long (3x threshold)
                if s['elapsed_minutes'] > s['threshold'] * 3:
                    sm.transition(s['agent'], 'idle')
                    log(f"Auto-reset {s['agent']} to idle (stuck {s['elapsed_minutes']}min)")
            log_event("stuck_agents", {"count": len(stuck), "agents": [s['agent'] for s in stuck]})

        return sm.summary()
    except Exception as e:
        log(f"Agent lifecycle error: {e}", "ERROR")
        return {}


def advance_workflows():
    """Advance all active workflow DAGs"""
    try:
        sys.path.insert(0, str(BASE / "scripts"))
        from workflow_engine import WorkflowEngine
        engine = WorkflowEngine()
        dispatched = engine.advance_all()
        if dispatched:
            log(f"Workflows: dispatched {len(dispatched)} steps")
            for d in dispatched:
                log(f"  → [{d['run_id']}] {d['step_id']} → {d['agent']}.{d['action']}")
                # Emit trigger for each dispatched step
                emit_trigger("workflow_engine", f"workflow.step.{d['action']}", {
                    "run_id": d["run_id"],
                    "step_id": d["step_id"],
                    "agent": d["agent"],
                })
        return dispatched
    except Exception as e:
        log(f"Workflow engine error: {e}", "ERROR")
        return []


# ── TASK QUEUE & COLLABORATION INTEGRATION ────────────
def dispatch_task_queue():
    """Auto-dispatch tasks from priority queue to best-fit agents"""
    try:
        sys.path.insert(0, str(BASE / "scripts"))
        from task_queue import TaskDispatcher
        dispatcher = TaskDispatcher()
        results = dispatcher.auto_assign()
        if results:
            count = len(results) if isinstance(results, list) else 0
            log(f"Task queue: dispatched {count} tasks")
            if isinstance(results, list):
                for r in results:
                    if isinstance(r, dict):
                        log(f"  → {r.get('task_id', '?')} → {r.get('agent', '?')}")
        return results
    except Exception as e:
        log(f"Task queue error: {e}", "ERROR")
        return []


def advance_collaborations():
    """Advance active collaboration sessions"""
    try:
        sys.path.insert(0, str(BASE / "scripts"))
        from agent_collaboration import CollaborationEngine, SESSIONS_DIR
        engine = CollaborationEngine()
        advanced = 0
        # Find active sessions from disk
        if SESSIONS_DIR.exists():
            for f in SESSIONS_DIR.glob("*.json"):
                try:
                    data = json.loads(f.read_text())
                    if data.get("status") == "active":
                        engine.advance_session(data.get("session_id", f.stem))
                        advanced += 1
                except Exception:
                    pass
        if advanced:
            log(f"Collaboration: advanced {advanced} sessions")
        return advanced
    except Exception as e:
        log(f"Collaboration engine error: {e}", "ERROR")
        return 0


def escalate_aged_tasks():
    """Escalate aged tasks in priority queue"""
    try:
        sys.path.insert(0, str(BASE / "scripts"))
        from task_queue import TaskPriorityQueue
        queue = TaskPriorityQueue()
        escalated = queue.escalate_aged()
        if escalated:
            log(f"Task escalation: {escalated} tasks escalated")
            log_event("tasks_escalated", {"count": escalated})
        return escalated
    except Exception as e:
        log(f"Task escalation error: {e}", "ERROR")
        return 0


# ── MAIN ORCHESTRATION CYCLE ────────────────────────
def orchestration_cycle(circuit_breaker, cost_tracker, cycle_count, last_nightly_date):
    """One full orchestration cycle — the heartbeat of the system"""
    hour = datetime.now().hour
    is_work_hours = WORK_HOURS[0] <= hour <= WORK_HOURS[1]
    today = date.today().isoformat()

    log(f"--- Cycle #{cycle_count} starting (hour={hour}, work={is_work_hours}) ---")

    # 0. Start cycle timer
    cycle_timer = None
    try:
        from time_tracker import CycleTimer
        cycle_timer = CycleTimer(f"cycle_{cycle_count}")
    except ImportError:
        pass

    # 0b. Warm up cold agents before doing anything else
    try:
        from agent_warmup import warmup_all
        warmup_all(verbose=False)
    except ImportError:
        pass
    except Exception as e:
        log(f"Warmup error: {e}", "WARN")

    # 1. Health check + auto-recovery
    health, recovered = run_health_and_recovery(circuit_breaker)

    # Emit recovery triggers
    for agent in recovered:
        emit_trigger("orchestrator", "agent_recovered", {"agent": agent})

    # 2. Process inter-agent triggers
    process_triggers()

    # 3. Process approval queue
    approval = process_approval_queue()

    # 4. Update ADHD scorecard
    run_scorecard()

    # 5. Check agent lifecycle (stuck agents, state machine)
    check_agent_lifecycle()

    # 6. Route messages through agent bus
    run_bus_routing()

    # 7. Advance workflow DAGs
    advance_workflows()

    # 8. Auto-dispatch tasks from priority queue
    dispatch_task_queue()

    # 9. Advance collaboration sessions
    advance_collaborations()

    # 10. Escalate aged tasks
    escalate_aged_tasks()

    # 11. During work hours: run sales autopilot
    if is_work_hours:
        run_sales_autopilot(circuit_breaker)

    # 8. Morning briefing (7-9 AM, once per day)
    if 7 <= hour <= 9:
        digest = BASE / "knowledge" / "USER_DIGEST_AM.md"
        if not digest.exists() or datetime.fromtimestamp(digest.stat().st_mtime).date() != date.today():
            run_morning_briefing()

    # 9. Update central execution state
    update_execution_state(health, approval, cost_tracker.summary())

    # 10. Nightly tasks (once per day at NIGHTLY_HOUR)
    if hour >= NIGHTLY_HOUR and last_nightly_date != today:
        run_nightly_tasks()
        last_nightly_date = today

    # 11. Work hours notifications + Telegram alerts
    if is_work_hours:
        ok_count = sum(1 for v in health.values() if v["status"] == "OK")
        total = len(health)
        if ok_count < 3:
            stale_names = [k for k, v in health.items() if v["status"] != "OK"]
            notify("Clawdia", f"Pozor: jen {ok_count}/{total} agentů zdravých\nProblémy: {', '.join(stale_names)}", "Ping")

    # Record cycle timing
    cycle_ms = 0
    if cycle_timer:
        try:
            cycle_ms = cycle_timer.finish()
        except Exception:
            pass

    log(f"--- Cycle #{cycle_count} complete ({cycle_ms}ms) ---")
    log_event("cycle_complete", {
        "cycle": cycle_count,
        "healthy": sum(1 for v in health.values() if v["status"] == "OK"),
        "recovered": len(recovered),
        "triggers_processed": process_triggers(),
        "cycle_ms": cycle_ms,
    })

    return last_nightly_date


# ── MAIN ────────────────────────────────────────────
def main():
    log("=" * 60)
    log("OpenClaw Orchestrator v2 starting")
    log(f"Base: {BASE}")
    log(f"PID: {os.getpid()}")
    log(f"Cycle: {CYCLE_SECONDS}s ({CYCLE_SECONDS // 60}min)")
    log("=" * 60)

    # Write PID file
    PID_FILE.parent.mkdir(exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))

    # Initialize subsystems
    circuit_breaker = CircuitBreaker()
    cost_tracker = CostTracker()
    setup_trigger_dirs()

    # Ensure required directories exist
    for d in ["logs", "triggers/outbox", "triggers/processed",
              "approval-queue/pending", "approval-queue/approved",
              "approval-queue/rejected", "approval-queue/expired",
              "inbox", "intel"]:
        (BASE / d).mkdir(parents=True, exist_ok=True)

    log_event("orchestrator_start", {"pid": os.getpid(), "cycle_seconds": CYCLE_SECONDS})

    global _current_cycle_running
    cycle_count = 0
    last_nightly_date = None

    # Check if we missed nightly tasks
    if datetime.now().hour >= NIGHTLY_HOUR:
        last_nightly_date = None  # Force nightly run on first cycle if after nightly hour

    # Initial cycle
    cycle_count += 1
    last_nightly_date = orchestration_cycle(circuit_breaker, cost_tracker, cycle_count, last_nightly_date)

    # Continuous loop with graceful shutdown support
    while not _shutdown_requested:
        try:
            log(f"Sleeping {CYCLE_SECONDS // 60}min until next cycle...")
            # Sleep in 5s intervals so we can check for shutdown
            for _ in range(CYCLE_SECONDS // 5):
                if _shutdown_requested:
                    break
                time.sleep(5)
            if _shutdown_requested:
                break
            cycle_count += 1
            _current_cycle_running = True
            last_nightly_date = orchestration_cycle(
                circuit_breaker, cost_tracker, cycle_count, last_nightly_date
            )
            _current_cycle_running = False
        except KeyboardInterrupt:
            break
        except Exception as e:
            _current_cycle_running = False
            log(f"Orchestration error: {e}", "ERROR")
            log_event("orchestrator_error", {"error": str(e), "cycle": cycle_count})
            time.sleep(300)  # Wait 5 min on error, then retry

    # Clean shutdown
    log("=" * 60)
    log(f"Orchestrator shutting down gracefully after {cycle_count} cycles")
    shutdown_state = {
        "shutdown_at": datetime.now().isoformat(),
        "reason": "signal" if _shutdown_requested else "keyboard_interrupt",
        "cycles_completed": cycle_count,
        "clean_shutdown": True,
    }
    safe_json_write(BASE / "logs" / "last-shutdown.json", shutdown_state)
    PID_FILE.unlink(missing_ok=True)
    log_event("orchestrator_stop", {
        "reason": shutdown_state["reason"],
        "cycles": cycle_count,
        "clean": True,
    })
    log("Goodbye.")


if __name__ == "__main__":
    main()
