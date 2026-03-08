#!/usr/bin/env python3
"""
Agent Warm-Up Protocol — Pre-warm cold agents before first run
===============================================================
When an agent hasn't executed in >24h, run a pre-warm sequence:
1. Verify agent dependencies (files, services, APIs)
2. Load recent context from knowledge files
3. Check for pending bus messages
4. Validate state files
5. Pre-cache relevant data

Integrates with agent_lifecycle.py and orchestrator.

Usage:
  python3 scripts/agent_warmup.py warmup <agent>     # Warm up specific agent
  python3 scripts/agent_warmup.py warmup-all          # Warm up all cold agents
  python3 scripts/agent_warmup.py status              # Show warm/cold status
"""

import json
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
LOG_FILE = WORKSPACE / "logs" / "warmup.log"
WARMUP_STATE = WORKSPACE / "logs" / "warmup-state.json"

# Agent dependency definitions
AGENT_DEPS = {
    "spojka": {
        "files": [
            "knowledge/USER_DIGEST_AM.md",
            "knowledge/EXECUTION_STATE.json",
        ],
        "dirs": ["knowledge"],
        "services": [],
        "state_files": ["knowledge/EXECUTION_STATE.json"],
        "bus_subscriptions": ["daily.morning_briefing", "system.health_report"],
        "warm_data": ["pipedrive/PIPELINE_STATUS.md", "reviews/daily-scorecard/score_state.json"],
    },
    "obchodak": {
        "files": [
            "pipedrive/DEAL_SCORING.md",
            "pipedrive/PIPELINE_STATUS.md",
        ],
        "dirs": ["pipedrive"],
        "services": ["pipedrive_api"],
        "state_files": ["pipedrive/deal_velocity.json"],
        "bus_subscriptions": ["pipeline.deal_scored", "pipeline.deal_stalling"],
        "warm_data": ["pipedrive/DEAL_SCORING.md", "pipedrive/STALE_DEALS.md"],
    },
    "postak": {
        "files": ["inbox/INBOX_DIGEST.md"],
        "dirs": ["inbox"],
        "services": [],
        "state_files": [],
        "bus_subscriptions": ["inbox.new_email", "inbox.urgent"],
        "warm_data": [],
    },
    "strateg": {
        "files": ["intel/DAILY-INTEL.md"],
        "dirs": ["intel"],
        "services": [],
        "state_files": [],
        "bus_subscriptions": ["intel.new_report", "intel.market_signal"],
        "warm_data": ["knowledge/graph.json"],
    },
    "kalendar": {
        "files": ["calendar/TODAY.md"],
        "dirs": ["calendar"],
        "services": [],
        "state_files": [],
        "bus_subscriptions": ["calendar.upcoming", "calendar.conflict"],
        "warm_data": [],
    },
    "kontrolor": {
        "files": ["reviews/SYSTEM_HEALTH.md"],
        "dirs": ["reviews"],
        "services": [],
        "state_files": ["reviews/daily-scorecard/score_state.json"],
        "bus_subscriptions": ["system.health_check", "system.error"],
        "warm_data": ["logs/orchestrator.log"],
    },
    "archivar": {
        "files": ["knowledge/IMPROVEMENTS.md"],
        "dirs": ["knowledge"],
        "services": [],
        "state_files": ["knowledge/EXECUTION_STATE.json"],
        "bus_subscriptions": ["knowledge.update", "knowledge.sync"],
        "warm_data": ["knowledge/graph.json"],
    },
}

COLD_THRESHOLD_HOURS = 24


def wlog(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] [{level}] {msg}\n")


def load_state():
    try:
        if WARMUP_STATE.exists():
            return json.loads(WARMUP_STATE.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {"agents": {}, "last_warmup": None}


def save_state(state):
    WARMUP_STATE.parent.mkdir(exist_ok=True)
    WARMUP_STATE.write_text(json.dumps(state, indent=2))


def is_cold(agent_name):
    """Check if an agent is cold (hasn't run recently)."""
    deps = AGENT_DEPS.get(agent_name)
    if not deps:
        return False

    # Check primary output file age
    for f in deps["files"]:
        p = WORKSPACE / f
        if p.exists():
            age_h = (time.time() - p.stat().st_mtime) / 3600
            if age_h <= COLD_THRESHOLD_HOURS:
                return False

    # Also check agent-states.json
    states_file = WORKSPACE / "control-plane" / "agent-states.json"
    if states_file.exists():
        try:
            states = json.loads(states_file.read_text())
            agent_state = states.get(agent_name, {})
            entered = agent_state.get("entered_state_at")
            if entered:
                entered_dt = datetime.fromisoformat(entered)
                if (datetime.now() - entered_dt).total_seconds() < COLD_THRESHOLD_HOURS * 3600:
                    return False
        except (json.JSONDecodeError, OSError, ValueError):
            pass

    return True


def warmup_agent(agent_name, verbose=True):
    """Run warm-up sequence for an agent."""
    deps = AGENT_DEPS.get(agent_name)
    if not deps:
        if verbose:
            print(f"  Unknown agent: {agent_name}")
        return {"agent": agent_name, "success": False, "error": "unknown agent"}

    results = {
        "agent": agent_name,
        "success": True,
        "checks": [],
        "warnings": [],
        "data_loaded": [],
        "timestamp": datetime.now().isoformat(),
    }

    wlog(f"Warming up agent: {agent_name}")

    # Step 1: Verify directories exist
    for d in deps["dirs"]:
        p = WORKSPACE / d
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            results["checks"].append(f"Created directory: {d}")
        else:
            results["checks"].append(f"Directory OK: {d}")

    # Step 2: Verify file existence (create empty if missing)
    for f in deps["files"]:
        p = WORKSPACE / f
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            if f.endswith(".json"):
                p.write_text("{}")
            else:
                p.write_text(f"# {agent_name} — Initialized by warmup\n\nNo data yet.\n")
            results["warnings"].append(f"Created missing file: {f}")
            wlog(f"  Created missing file: {f}", "WARN")
        else:
            results["checks"].append(f"File OK: {f}")

    # Step 3: Validate state files
    for sf in deps["state_files"]:
        p = WORKSPACE / sf
        if p.exists():
            try:
                data = json.loads(p.read_text())
                if isinstance(data, dict):
                    results["checks"].append(f"State valid: {sf}")
                else:
                    results["warnings"].append(f"State non-dict: {sf}")
            except json.JSONDecodeError:
                results["warnings"].append(f"State corrupt: {sf} — resetting")
                p.write_text("{}")
                wlog(f"  Reset corrupt state: {sf}", "WARN")

    # Step 4: Check for pending bus messages
    inbox = WORKSPACE / "bus" / "inbox" / agent_name
    pending = 0
    if inbox.exists():
        pending = len(list(inbox.glob("*.json")))
    results["pending_messages"] = pending
    if pending > 0:
        results["checks"].append(f"Pending messages: {pending}")

    # Step 5: Pre-load warm data (verify readable)
    for wd in deps["warm_data"]:
        p = WORKSPACE / wd
        if p.exists():
            try:
                content = p.read_text()
                size = len(content)
                results["data_loaded"].append({"file": wd, "size": size})
            except OSError:
                results["warnings"].append(f"Cannot read warm data: {wd}")

    # Step 6: Check services
    for svc in deps["services"]:
        if svc == "pipedrive_api":
            env_path = WORKSPACE / ".secrets" / "pipedrive.env"
            if env_path.exists():
                content = env_path.read_text()
                if "PIPEDRIVE_API_TOKEN" in content:
                    results["checks"].append(f"Service OK: {svc} (token found)")
                else:
                    results["warnings"].append(f"Service WARN: {svc} (no token)")
            else:
                results["warnings"].append(f"Service WARN: {svc} (env file missing)")

    # Step 7: Record warmup in state
    state = load_state()
    state["agents"][agent_name] = {
        "last_warmup": datetime.now().isoformat(),
        "checks": len(results["checks"]),
        "warnings": len(results["warnings"]),
        "success": len(results["warnings"]) == 0,
    }
    state["last_warmup"] = datetime.now().isoformat()
    save_state(state)

    # Determine success
    results["success"] = len(results["warnings"]) <= 2  # allow minor warnings

    if verbose:
        status = "\033[0;32mWARM\033[0m" if results["success"] else "\033[0;33mWARN\033[0m"
        print(f"  {status}  {agent_name}")
        print(f"    Checks: {len(results['checks'])} passed")
        if results["warnings"]:
            for w in results["warnings"]:
                print(f"    ⚠ {w}")
        if results["pending_messages"]:
            print(f"    Pending messages: {results['pending_messages']}")
        if results["data_loaded"]:
            total_kb = sum(d["size"] for d in results["data_loaded"]) / 1024
            print(f"    Data pre-loaded: {len(results['data_loaded'])} files ({total_kb:.1f}KB)")

    wlog(f"  Warmup complete: {agent_name} — {'OK' if results['success'] else 'WARNINGS'}")
    return results


def warmup_all(verbose=True):
    """Warm up all cold agents."""
    cold_agents = [name for name in AGENT_DEPS if is_cold(name)]

    if verbose:
        print(f"\n{'='*50}")
        print(f"  Agent Warm-Up Protocol")
        print(f"{'='*50}\n")

    if not cold_agents:
        if verbose:
            print("  All agents are warm — no warm-up needed.\n")
        return []

    if verbose:
        print(f"  Cold agents: {len(cold_agents)}/{len(AGENT_DEPS)}\n")

    results = []
    for name in cold_agents:
        r = warmup_agent(name, verbose=verbose)
        results.append(r)

    if verbose:
        warmed = sum(1 for r in results if r["success"])
        print(f"\n  Warmed: {warmed}/{len(results)} agents\n")

    return results


def show_status():
    """Show warm/cold status for all agents."""
    print(f"\n{'='*50}")
    print(f"  Agent Temperature Status")
    print(f"{'='*50}\n")

    state = load_state()

    for name in AGENT_DEPS:
        cold = is_cold(name)
        status = "\033[0;31mCOLD\033[0m" if cold else "\033[0;32mWARM\033[0m"

        # Get last warmup time
        agent_state = state.get("agents", {}).get(name, {})
        last = agent_state.get("last_warmup", "never")
        if last != "never":
            last = last[:19]

        # Get file age
        deps = AGENT_DEPS[name]
        age = "N/A"
        for f in deps["files"]:
            p = WORKSPACE / f
            if p.exists():
                h = (time.time() - p.stat().st_mtime) / 3600
                age = f"{h:.1f}h"
                break

        print(f"  {status}  {name:20s}  age:{age:>8s}  warmup:{last}")

    print()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"

    if cmd == "warmup" and len(sys.argv) > 2:
        warmup_agent(sys.argv[2])
    elif cmd == "warmup-all":
        warmup_all()
    elif cmd == "status":
        show_status()
    else:
        print("Usage: agent_warmup.py [warmup <agent>|warmup-all|status]")


if __name__ == "__main__":
    main()
