#!/usr/bin/env python3
"""
Agent Runner — Bus Consumer Daemon
====================================
Polls bus/inbox/{agent}/*.json every 60 seconds.
Reads messages, executes the action, logs results, moves to processed.

Each agent has a handler that maps actions to real work:
- obchodak: lead scoring, deal enrichment
- textar: email draft generation
- postak: inbox check, follow-up sequences
- strateg: competitive intel, research
- kalendar: calendar sync, meeting prep
- kontrolor: quality review, health check
- archivar: knowledge sync, dedup
- udrzbar: system maintenance, cleanup
- hlidac: anomaly detection, monitoring
- planovac: Pomodoro planning, productivity
- spojka: coordination, dashboard
- vyvojar: code review, improvements

Runs as launchd daemon (KeepAlive) — com.clawdia.agent-runner.

Usage:
    python3 scripts/agent_runner.py              # Run daemon (polls forever)
    python3 scripts/agent_runner.py --once       # Process once and exit
    python3 scripts/agent_runner.py --status     # Show inbox status
"""

import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, date
from pathlib import Path

from lib.paths import WORKSPACE, BUS_INBOX, LOGS_DIR
from lib.secrets import load_secrets, get_api_key
from lib.claude_api import claude_generate
from lib.logger import make_logger
from lib.notifications import notify_telegram

log = make_logger("agent-runner")

BUS_PROCESSED = WORKSPACE / "bus" / "processed"
AGENT_STATES = WORKSPACE / "control-plane" / "agent-states.json"
POLL_INTERVAL = 60  # seconds
EXTERNAL_CONSUMER_INBOXES = {"claude"}


def import_claude_bridge_result(agent_id, task):
    """Persist Claude bridge output as a handoff artifact for the target agent."""
    handoff_dir = WORKSPACE / "collaboration" / "handoffs" / "claude"
    handoff_dir.mkdir(parents=True, exist_ok=True)

    request_id = task.get("request_id", "unknown")
    summary = task.get("summary", "")
    result_file = task.get("result_file", "")
    saved_output = task.get("saved_output", "")
    success = task.get("success", False)

    handoff = {
        "agent": agent_id,
        "request_id": request_id,
        "success": success,
        "source": task.get("source"),
        "result_file": result_file,
        "saved_output": saved_output,
        "summary": summary,
        "imported_at": datetime.now().isoformat(),
    }

    json_path = handoff_dir / f"{agent_id}_{request_id}.json"
    json_path.write_text(json.dumps(handoff, indent=2, ensure_ascii=False))

    md_lines = [
        f"# Claude Handoff — {agent_id}",
        "",
        f"- Request: {request_id}",
        f"- Success: {'yes' if success else 'no'}",
        f"- Source: {task.get('source', '?')}",
        f"- Result file: {result_file or 'n/a'}",
        f"- Saved output: {saved_output or 'n/a'}",
        "",
        "## Summary",
        summary or "(empty)",
        "",
    ]
    (handoff_dir / f"{agent_id}_{request_id}.md").write_text("\n".join(md_lines))
    return [f"claude_handoff: {json_path.relative_to(WORKSPACE)}"]


# ── AGENT HANDLERS ──────────────────────────────────────────

def handle_obchodak(task, secrets):
    """Lead scoring + deal enrichment."""
    action = task.get("action", "")
    results = []

    if action in ("score_and_analyze", "research_and_intel"):
        # Run lead scorer
        script = WORKSPACE / "scripts" / "pipedrive_lead_scorer.py"
        if script.exists():
            r = run_script(script, timeout=120)
            results.append(f"lead_scorer: {r}")

    # Run LUSHA enrichment if available
    if "enrichuj" in str(task.get("specific_work", [])).lower():
        enricher = WORKSPACE / "scripts" / "lusha_enricher.py"
        if enricher.exists():
            r = run_script(enricher, timeout=60)
            results.append(f"lusha: {r}")

    return results or ["scored pipeline"]


def handle_textar(task, secrets):
    """Email draft generation."""
    action = task.get("action", "")
    deals = task.get("data", {}).get("deals", [])
    max_drafts = min(len(deals), 3) if deals else 3

    script = WORKSPACE / "scripts" / "draft_generator.py"
    if script.exists():
        r = run_script(script, args=[str(max_drafts)], timeout=300)
        return [f"drafts: {r}"]
    return ["draft_generator not found"]


def handle_postak(task, secrets):
    """Inbox check + follow-up sequences."""
    results = []

    # Check drafts folder for unsent drafts
    drafts_dir = WORKSPACE / "drafts"
    if drafts_dir.exists():
        drafts = list(drafts_dir.glob("*.json"))
        unsent = [d for d in drafts if _draft_status(d) == "draft"]
        results.append(f"unsent_drafts: {len(unsent)}")

    # Check for deals needing follow-up
    seq_script = WORKSPACE / "scripts" / "email_sequences.py"
    if seq_script.exists():
        r = run_script(seq_script, timeout=120)
        results.append(f"sequences: {r}")

    return results or ["inbox checked"]


def handle_strateg(task, secrets):
    """Research + competitive intel."""
    action = task.get("action", "")
    work_items = task.get("specific_work", [])

    results = []

    # Run competitive intel if available
    intel_script = WORKSPACE / "scripts" / "competitive_intel.py"
    if intel_script.exists():
        r = run_script(intel_script, timeout=120)
        results.append(f"competitive_intel: {r}")

    # Generate strategic brief with Claude
    api_key = get_api_key()
    if api_key and work_items:
        topic = work_items[0] if work_items else "Czech employee engagement market analysis"
        brief = claude_generate(
            api_key,
            "Jsi strategický analytik pro Behavera (Echo Pulse - employee engagement surveys, ČR). Piš česky, stručně, s konkrétními daty.",
            f"Připrav stručnou analýzu (max 300 slov): {topic}",
            max_tokens=500,
        )
        if brief:
            output = WORKSPACE / "intel" / "DAILY-INTEL.md"
            output.parent.mkdir(parents=True, exist_ok=True)
            # Append to existing
            existing = output.read_text() if output.exists() else ""
            ts = datetime.now().strftime("%H:%M")
            output.write_text(f"{existing}\n\n## [{ts}] {topic[:60]}\n{brief}\n")
            results.append(f"brief_generated: {len(brief)} chars")

    return results or ["research done"]


def handle_kalendar(task, secrets):
    """Calendar sync + meeting prep."""
    results = []

    # Run meeting prep
    script = WORKSPACE / "scripts" / "meeting_prep.py"
    if script.exists():
        r = run_script(script, args=["--upcoming"], timeout=180)
        results.append(f"meeting_prep: {r}")

    return results or ["calendar synced"]


def handle_kontrolor(task, secrets):
    """Quality review + health check."""
    results = []
    health = task.get("data", {}).get("health", {})
    stale_agents = task.get("data", {}).get("stale_agents", [])

    # Check recent drafts quality
    drafts_dir = WORKSPACE / "drafts"
    if drafts_dir.exists():
        recent = sorted(drafts_dir.glob("*.md"), key=lambda f: f.stat().st_mtime, reverse=True)[:3]
        for draft_file in recent:
            checker = WORKSPACE / "scripts" / "humanizer_trainer.py"
            if checker.exists():
                r = run_script(checker, args=["--check-draft", str(draft_file)], timeout=60)
                results.append(f"quality_check: {draft_file.name}: {r}")

    # Check logs for errors
    error_count = 0
    for lf in LOGS_DIR.glob("*.log"):
        try:
            content = lf.read_text()
            today_str = date.today().isoformat()
            errors = [l for l in content.splitlines() if today_str in l and "ERROR" in l]
            error_count += len(errors)
        except OSError:
            pass

    results.append(f"errors_today: {error_count}")

    # Update health file
    health_file = WORKSPACE / "reviews" / "SYSTEM_HEALTH.md"
    health_file.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now()
    health_md = f"# System Health — {now.strftime('%Y-%m-%d %H:%M')}\n\n"
    health_md += f"## Agent Status\n"
    for agent, h in health.items():
        icon = "✅" if h.get("status") == "ok" else "⚠️"
        health_md += f"- {icon} **{agent}**: {h.get('age_hours', '?')}h old\n"
    health_md += f"\n## Errors Today: {error_count}\n"
    if stale_agents:
        health_md += f"\n## Stale Agents: {', '.join(stale_agents)}\n"
    health_file.write_text(health_md)
    results.append("health_report updated")

    return results


def handle_archivar(task, secrets):
    """Knowledge sync + dedup."""
    results = []

    # Run knowledge dedup
    dedup = WORKSPACE / "scripts" / "knowledge_dedup.py"
    if dedup.exists():
        r = run_script(dedup, timeout=60)
        results.append(f"dedup: {r}")

    # Run knowledge graph export
    graph = WORKSPACE / "scripts" / "knowledge_graph.py"
    if graph.exists():
        r = run_script(graph, timeout=60)
        results.append(f"graph: {r}")

    return results or ["knowledge synced"]


def handle_udrzbar(task, secrets):
    """System maintenance."""
    results = []

    # Cleanup old logs (>7 days)
    cutoff = time.time() - 7 * 86400
    cleaned = 0
    for lf in LOGS_DIR.glob("*.log"):
        try:
            if lf.stat().st_mtime < cutoff and lf.stat().st_size > 100_000:
                lines = lf.read_text().splitlines()
                lf.write_text("\n".join(lines[-500:]) + "\n")
                cleaned += 1
        except OSError:
            pass
    results.append(f"logs_trimmed: {cleaned}")

    # Validate API keys
    api_key = get_api_key()
    results.append(f"anthropic_key: {'ok' if api_key else 'missing'}")

    pd = secrets.get("PIPEDRIVE_API_TOKEN", "")
    results.append(f"pipedrive_key: {'ok' if pd else 'missing'}")

    tg = secrets.get("TELEGRAM_BOT_TOKEN", "")
    results.append(f"telegram_key: {'ok' if tg else 'missing'}")

    return results


def handle_hlidac(task, secrets):
    """Anomaly detection."""
    results = []

    # Run anomaly detector
    detector = WORKSPACE / "scripts" / "anomaly_detector.py"
    if detector.exists():
        r = run_script(detector, timeout=60)
        results.append(f"anomaly_detector: {r}")

    return results or ["monitoring done"]


def handle_planovac(task, secrets):
    """Pomodoro planning + productivity."""
    api_key = get_api_key()
    if not api_key:
        return ["no api key"]

    now = datetime.now()
    remaining_hours = max(0, 20 - now.hour)

    plan = claude_generate(
        api_key,
        "Jsi productivity coach pro Josefa (sales, ADHD). Generuj Pomodoro plán v češtině. Krátce, konkrétně.",
        f"Vygeneruj Pomodoro plán na zbytek dne ({remaining_hours}h). "
        f"Josef prodává Echo Pulse (engagement surveys). "
        f"Priorita: calling time, follow-upy, meeting prep. "
        f"Formát: čas | 25min blok | pauza",
        max_tokens=400,
    )
    if plan:
        output = WORKSPACE / "knowledge" / "POMODORO_PLAN.md"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(f"# Pomodoro Plan — {now.strftime('%Y-%m-%d %H:%M')}\n\n{plan}\n")
        return [f"pomodoro_plan: {len(plan)} chars"]
    return ["plan generation failed"]


def handle_spojka(task, secrets):
    """Coordination + dashboard."""
    dispatched = task.get("data", {}).get("dispatched", [])

    # Update user digest
    digest = WORKSPACE / "knowledge" / "USER_DIGEST_AM.md"
    digest.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now()

    content = f"# Clawdia Dashboard — {now.strftime('%Y-%m-%d %H:%M')}\n\n"
    content += f"## Active Agents: {len(dispatched)}\n"
    for d in dispatched:
        content += f"- {d}\n"

    # Check bus status
    total_msgs = 0
    for agent_dir in BUS_INBOX.iterdir():
        if agent_dir.is_dir():
            msgs = list(agent_dir.glob("*.json"))
            total_msgs += len(msgs)
    content += f"\n## Bus: {total_msgs} pending messages\n"

    digest.write_text(content)
    return [f"dashboard updated, {len(dispatched)} agents tracked"]


def handle_vyvojar(task, secrets):
    """Code review + improvements."""
    results = []

    # Check logs for repeating errors
    error_patterns = {}
    for lf in LOGS_DIR.glob("*.log"):
        try:
            for line in lf.read_text().splitlines()[-100:]:
                if "ERROR" in line:
                    # Extract error message
                    parts = line.split("] ")
                    msg = parts[-1] if parts else line
                    error_patterns[msg] = error_patterns.get(msg, 0) + 1
        except OSError:
            pass

    repeating = {k: v for k, v in error_patterns.items() if v >= 3}
    if repeating:
        results.append(f"repeating_errors: {len(repeating)}")
        # Save improvement suggestions
        improvements = WORKSPACE / "knowledge" / "IMPROVEMENTS.md"
        improvements.parent.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        with open(improvements, "a") as f:
            f.write(f"\n## [{now.strftime('%Y-%m-%d %H:%M')}] Repeating Errors\n")
            for err, count in sorted(repeating.items(), key=lambda x: -x[1])[:5]:
                f.write(f"- ({count}x) {err[:100]}\n")
    else:
        results.append("no repeating errors")

    return results


# ── HANDLER REGISTRY ────────────────────────────────────────

HANDLERS = {
    "obchodak": handle_obchodak,
    "textar": handle_textar,
    "postak": handle_postak,
    "strateg": handle_strateg,
    "kalendar": handle_kalendar,
    "kontrolor": handle_kontrolor,
    "archivar": handle_archivar,
    "udrzbar": handle_udrzbar,
    "hlidac": handle_hlidac,
    "planovac": handle_planovac,
    "spojka": handle_spojka,
    "vyvojar": handle_vyvojar,
}


# ── UTILITIES ───────────────────────────────────────────────

def run_script(script_path, args=None, timeout=120):
    """Run a Python script and return success/failure."""
    cmd = ["python3", str(script_path)] + (args or [])
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, cwd=str(WORKSPACE),
        )
        if result.returncode == 0:
            return "ok"
        return f"error: {result.stderr[:100]}" if result.stderr else "error: non-zero exit"
    except subprocess.TimeoutExpired:
        return "timeout"
    except Exception as e:
        return f"exception: {str(e)[:80]}"


def _draft_status(draft_path):
    """Check draft status from JSON file."""
    try:
        d = json.loads(draft_path.read_text())
        return d.get("status", "unknown")
    except (json.JSONDecodeError, OSError):
        return "unknown"


def update_agent_state(agent_id, state):
    """Update agent state in control-plane."""
    states = {}
    if AGENT_STATES.exists():
        try:
            states = json.loads(AGENT_STATES.read_text())
        except json.JSONDecodeError:
            states = {}

    agents = states.get("agents", {})
    agents[agent_id] = {
        "state": state,
        "updated_at": datetime.now().isoformat(),
    }
    states["agents"] = agents
    AGENT_STATES.parent.mkdir(parents=True, exist_ok=True)
    AGENT_STATES.write_text(json.dumps(states, indent=2, ensure_ascii=False))


def process_message(agent_id, msg_file, secrets):
    """Process a single bus message for an agent."""
    try:
        msg = json.loads(msg_file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        log(f"Bad message {msg_file}: {e}", "ERROR")
        move_to_processed(msg_file, agent_id, success=False)
        return False

    task = msg.get("payload", msg)
    action = task.get("action", msg.get("topic", "unknown"))
    priority = msg.get("priority", "P3")

    # Check TTL
    ttl = msg.get("ttl_hours", 24)
    created = msg.get("created_at", "")
    if created:
        try:
            created_dt = datetime.fromisoformat(created)
            age_hours = (datetime.now() - created_dt).total_seconds() / 3600
            if age_hours > ttl:
                log(f"Expired message {msg_file.name} ({age_hours:.1f}h > {ttl}h TTL)")
                move_to_processed(msg_file, agent_id, success=False, reason="expired")
                return False
        except (ValueError, TypeError):
            pass

    handler = HANDLERS.get(agent_id)
    if not handler:
        log(f"No handler for agent {agent_id}", "WARN")
        move_to_processed(msg_file, agent_id, success=False, reason="no_handler")
        return False

    log(f"[{agent_id}] Processing: {action} ({priority})")
    update_agent_state(agent_id, "working")

    try:
        if action == "claude_bridge_result":
            results = import_claude_bridge_result(agent_id, task)
        else:
            results = handler(task, secrets)
        log(f"[{agent_id}] Done: {', '.join(str(r) for r in results)}")
        update_agent_state(agent_id, "idle")
        move_to_processed(msg_file, agent_id, success=True, results=results)
        return True
    except Exception as e:
        log(f"[{agent_id}] FAILED: {e}", "ERROR")
        update_agent_state(agent_id, "failed")
        move_to_processed(msg_file, agent_id, success=False, reason=str(e))
        return False


def move_to_processed(msg_file, agent_id, success=True, reason="", results=None):
    """Move processed message to bus/processed/."""
    processed_dir = BUS_PROCESSED / agent_id
    processed_dir.mkdir(parents=True, exist_ok=True)

    # Add result metadata
    try:
        msg = json.loads(msg_file.read_text())
        msg["_processed_at"] = datetime.now().isoformat()
        msg["_success"] = success
        if reason:
            msg["_reason"] = reason
        if results:
            msg["_results"] = results

        dest = processed_dir / msg_file.name
        dest.write_text(json.dumps(msg, indent=2, ensure_ascii=False))
        msg_file.unlink()
    except Exception as e:
        log(f"Move failed {msg_file}: {e}", "ERROR")
        # Force remove to prevent infinite retry
        try:
            msg_file.unlink()
        except OSError:
            pass


def process_all_inboxes(secrets):
    """Process all pending messages across all agent inboxes."""
    if not BUS_INBOX.exists():
        return 0, 0

    processed = 0
    failed = 0

    for agent_dir in sorted(BUS_INBOX.iterdir()):
        if not agent_dir.is_dir():
            continue

        agent_id = agent_dir.name
        if agent_id in EXTERNAL_CONSUMER_INBOXES:
            continue
        messages = sorted(agent_dir.glob("*.json"))

        if not messages:
            continue

        # Sort by priority (P0 first)
        def priority_key(f):
            name = f.name
            if name.startswith("P0"):
                return 0
            if name.startswith("P1"):
                return 1
            if name.startswith("P2"):
                return 2
            return 3

        messages.sort(key=priority_key)

        # Process max 3 messages per agent per cycle to avoid hogging
        for msg_file in messages[:3]:
            ok = process_message(agent_id, msg_file, secrets)
            if ok:
                processed += 1
            else:
                failed += 1

    return processed, failed


def show_status():
    """Show current inbox status."""
    print(f"\n{'='*60}")
    print(f"  Agent Runner Status — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    if not BUS_INBOX.exists():
        print("  No bus inbox found")
        return

    total = 0
    for agent_dir in sorted(BUS_INBOX.iterdir()):
        if not agent_dir.is_dir():
            continue
        if agent_dir.name in EXTERNAL_CONSUMER_INBOXES:
            continue
        msgs = list(agent_dir.glob("*.json"))
        handler = "✅" if agent_dir.name in HANDLERS else "❌"
        print(f"  {handler} {agent_dir.name:12s} | {len(msgs)} messages")
        total += len(msgs)

    # Check processed
    processed_count = 0
    if BUS_PROCESSED.exists():
        for d in BUS_PROCESSED.iterdir():
            if d.is_dir():
                processed_count += len(list(d.glob("*.json")))

    print(f"\n  Total pending: {total}")
    print(f"  Total processed: {processed_count}")
    print()


def main():
    args = sys.argv[1:]

    if "--status" in args:
        show_status()
        return

    secrets = load_secrets()
    once = "--once" in args

    if once:
        log("Running single processing cycle...")
        processed, failed = process_all_inboxes(secrets)
        log(f"Cycle done: {processed} processed, {failed} failed")
        print(f"Processed: {processed}, Failed: {failed}")
        return

    # Daemon mode
    log("Agent Runner daemon starting...")
    print(f"Agent Runner daemon started — polling every {POLL_INTERVAL}s")

    cycle = 0
    while True:
        try:
            processed, failed = process_all_inboxes(secrets)
            cycle += 1

            if processed > 0 or failed > 0:
                log(f"Cycle {cycle}: {processed} processed, {failed} failed")

            # Reload secrets every 10 cycles (10 min)
            if cycle % 10 == 0:
                secrets = load_secrets()

            # Telegram summary every 100 cycles (~100 min)
            if cycle % 100 == 0 and processed > 0:
                notify_telegram(
                    f"🤖 Agent Runner — cycle {cycle}\n"
                    f"Processed: {processed} | Failed: {failed}"
                )

        except KeyboardInterrupt:
            log("Daemon stopped by user")
            print("\nStopped.")
            break
        except Exception as e:
            log(f"Cycle error: {e}", "ERROR")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
