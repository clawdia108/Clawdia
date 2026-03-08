#!/usr/bin/env python3
"""
Cowork Bridge — Connect Claude Desktop scheduled tasks to Clawdia Agent Bus
=============================================================================
Polls /bus/cowork-status/ for task completion markers written by Cowork
scheduled tasks, then publishes corresponding events to the agent bus.

Runs as a daemon via launchd. Polls every 60 seconds.

Usage:
    python3 cowork_bridge.py              # Run once (check + publish)
    python3 cowork_bridge.py daemon       # Run as polling daemon
    python3 cowork_bridge.py status       # Show last known state
"""

import json
import sys
import time
import signal
from datetime import datetime
from pathlib import Path

from lib.paths import WORKSPACE, BUS_INBOX
from lib.logger import make_logger

log = make_logger("cowork-bridge")

# ── Paths ────────────────────────────────────────────────
COWORK_STATUS_DIR = WORKSPACE / "bus" / "cowork-status"
BUS_OUTBOX = WORKSPACE / "bus" / "outbox"
BRIDGE_STATE_FILE = WORKSPACE / "bus" / "cowork-status" / "_bridge_state.json"

POLL_INTERVAL = 60  # seconds

# ── Task → Agent mapping ────────────────────────────────
TASK_AGENT_MAP = {
    "morning-briefing": {
        "agent": "spojka",
        "topic": "system.cowork_complete",
        "output_file": "knowledge/USER_DIGEST_AM.md",
        "priority": "P2",
    },
    "evening-review": {
        "agent": "spojka",
        "topic": "system.cowork_complete",
        "output_file": "knowledge/USER_DIGEST_PM.md",
        "priority": "P2",
    },
    "inbox-triage": {
        "agent": "postak",
        "topic": "system.cowork_complete",
        "output_file": "inbox/INBOX_DIGEST.md",
        "priority": "P1",
    },
    "market-intel": {
        "agent": "strateg",
        "topic": "system.cowork_complete",
        "output_file": "intel/DAILY-INTEL.md",
        "priority": "P2",
    },
    "pipeline-hygiene": {
        "agent": "obchodak",
        "topic": "system.cowork_complete",
        "output_file": "pipedrive/PIPELINE_STATUS.md",
        "priority": "P1",
    },
    "scorecard-update": {
        "agent": "kontrolor",
        "topic": "system.cowork_complete",
        "output_file": "reviews/daily-scorecard/SCOREBOARD.md",
        "priority": "P3",
    },
    "agent-recovery": {
        "agent": "udrzbar",
        "topic": "system.cowork_complete",
        "output_file": "logs/recovery-report.md",
        "priority": "P1",
    },
    "spin-call-prep": {
        "agent": "obchodak",
        "topic": "system.cowork_complete",
        "output_file": "meeting-prep/",
        "priority": "P1",
    },
    "deal-follow-ups": {
        "agent": "textar",
        "topic": "system.cowork_complete",
        "output_file": "inbox/FOLLOW_UPS.md",
        "priority": "P1",
    },
    "weekly-forecast": {
        "agent": "kontrolor",
        "topic": "system.cowork_complete",
        "output_file": "reports/",
        "priority": "P2",
    },
}

# Secondary bus events to fire after specific tasks
SECONDARY_EVENTS = {
    "morning-briefing": {
        "topic": "system.morning_briefing",
        "priority": "P1",
    },
    "market-intel": {
        "topic": "research.intel_ready",
        "priority": "P2",
    },
    "pipeline-hygiene": {
        "topic": "pipeline.scored",
        "priority": "P1",
    },
    "agent-recovery": {
        "topic": "system.agent_recovered",
        "priority": "P2",
    },
    "scorecard-update": {
        "topic": "system.health_check",
        "priority": "P3",
    },
    "spin-call-prep": {
        "topic": "pipeline.call_prepped",
        "priority": "P1",
    },
    "deal-follow-ups": {
        "topic": "content.drafts_ready",
        "priority": "P1",
    },
    "weekly-forecast": {
        "topic": "system.weekly_forecast",
        "priority": "P2",
    },
}


# ── State management ────────────────────────────────────

def load_state():
    """Load last-seen timestamps for each task."""
    if BRIDGE_STATE_FILE.exists():
        try:
            return json.loads(BRIDGE_STATE_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_state(state):
    """Persist state to disk."""
    BRIDGE_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    BRIDGE_STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


# ── Bus message publishing ──────────────────────────────

def publish_to_bus(source, topic, payload, priority="P2"):
    """Write a message directly to the bus outbox."""
    import hashlib
    msg_id = hashlib.md5(f"{time.time()}:{topic}:{source}".encode()).hexdigest()[:16]

    message = {
        "id": msg_id,
        "source": f"cowork:{source}",
        "topic": topic,
        "type": "EVENT",
        "payload": payload,
        "target": None,
        "priority": priority,
        "ttl_hours": 24,
        "reply_to": None,
        "correlation_id": msg_id,
        "created_at": datetime.now().isoformat(),
        "status": "pending",
        "delivery_attempts": 0,
        "max_retries": 3,
    }

    BUS_OUTBOX.mkdir(parents=True, exist_ok=True)
    filename = f"{priority}_{msg_id}_{topic.replace('.', '_')}.json"
    outbox_path = BUS_OUTBOX / filename
    outbox_path.write_text(json.dumps(message, indent=2, ensure_ascii=False))

    log(f"PUBLISH [{topic}] from cowork:{source} (id={msg_id}, pri={priority})")
    return msg_id


# ── Core polling logic ──────────────────────────────────

def check_cowork_status():
    """Check for new/updated cowork status files and publish bus events."""
    COWORK_STATUS_DIR.mkdir(parents=True, exist_ok=True)
    state = load_state()
    published = 0

    for task_name, mapping in TASK_AGENT_MAP.items():
        status_file = COWORK_STATUS_DIR / f"{task_name}.json"

        if not status_file.exists():
            continue

        try:
            status = json.loads(status_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            log(f"Bad status file for {task_name}: {e}", "WARN")
            continue

        completed_at = status.get("completed_at", "")
        last_seen = state.get(task_name, {}).get("completed_at", "")

        # Skip if we already processed this completion
        if completed_at and completed_at == last_seen:
            continue

        # New completion — publish primary event
        payload = {
            "task": task_name,
            "agent": mapping["agent"],
            "output_file": status.get("files_written", [mapping["output_file"]]),
            "completed_at": completed_at,
            "status": status.get("status", "ok"),
        }

        publish_to_bus(
            source=task_name,
            topic=mapping["topic"],
            payload=payload,
            priority=mapping["priority"],
        )
        published += 1

        # Fire secondary event if defined (e.g., morning-briefing → system.morning_briefing)
        if task_name in SECONDARY_EVENTS:
            sec = SECONDARY_EVENTS[task_name]
            publish_to_bus(
                source=task_name,
                topic=sec["topic"],
                payload=payload,
                priority=sec["priority"],
            )
            published += 1

        # Update state
        state[task_name] = {
            "completed_at": completed_at,
            "bridged_at": datetime.now().isoformat(),
            "agent": mapping["agent"],
        }

        log(f"Bridged {task_name} → {mapping['agent']} ({mapping['topic']})")

    save_state(state)
    return published


# ── Daemon mode ─────────────────────────────────────────

def run_daemon():
    """Poll cowork-status every POLL_INTERVAL seconds."""
    running = True

    def handle_signal(signum, frame):
        nonlocal running
        log("Received shutdown signal, stopping.")
        running = False

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    log("Cowork Bridge daemon started (poll every {}s)".format(POLL_INTERVAL))

    while running:
        try:
            n = check_cowork_status()
            if n > 0:
                log(f"Cycle complete: {n} events published")
        except Exception as e:
            log(f"Error in poll cycle: {e}", "ERROR")

        # Sleep in small chunks so we catch signals quickly
        for _ in range(POLL_INTERVAL):
            if not running:
                break
            time.sleep(1)

    log("Cowork Bridge daemon stopped.")


def show_status():
    """Print current bridge state."""
    state = load_state()
    if not state:
        print("No cowork tasks bridged yet.")
        return

    print("Cowork Bridge Status")
    print("=" * 50)
    for task, info in sorted(state.items()):
        agent = info.get("agent", "?")
        completed = info.get("completed_at", "?")
        bridged = info.get("bridged_at", "?")
        print(f"  {task:20s} → {agent:10s}  last: {completed[:19] if len(completed) > 19 else completed}")
    print()

    # Check what's pending in cowork-status/
    pending = []
    for f in COWORK_STATUS_DIR.glob("*.json"):
        if f.name.startswith("_"):
            continue
        task = f.stem
        if task not in state:
            pending.append(task)
    if pending:
        print(f"Unbridged status files: {', '.join(pending)}")


# ── Main ────────────────────────────────────────────────

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "once"

    if cmd == "daemon":
        run_daemon()
    elif cmd == "status":
        show_status()
    else:
        n = check_cowork_status()
        print(f"Bridged {n} cowork events to agent bus.")
