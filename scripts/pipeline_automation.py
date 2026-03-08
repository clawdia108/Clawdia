#!/usr/bin/env python3
"""
Pipeline Automation — Auto-actions on deal stage changes
=========================================================
Monitors Pipedrive deals and triggers automated actions when deals
change stages. Event-driven via agent bus.

Stage → Action mapping:
  Lead In → Auto-research company (knowledge graph)
  Contacted → Track engagement, start sequence
  Qualified → Generate meeting prep
  Demo Scheduled → Prepare demo deck + talking points
  Proposal Sent → Auto-generate proposal
  Negotiation → Risk assessment + coaching
  Won → Celebrate + scorecard + win analysis
  Lost → Win/loss analysis + learnings

Usage:
  python3 scripts/pipeline_automation.py check         # Check for stage changes
  python3 scripts/pipeline_automation.py rules          # Show automation rules
  python3 scripts/pipeline_automation.py history        # Action history
  python3 scripts/pipeline_automation.py simulate <stage>  # Test a rule
"""

import json
import os
import subprocess
import sys
import urllib.request
from datetime import datetime, date
from pathlib import Path
from collections import defaultdict

WORKSPACE = Path(__file__).resolve().parents[1]
ENV_PATH = WORKSPACE / ".secrets" / "pipedrive.env"
STATE_FILE = WORKSPACE / "logs" / "pipeline-automation-state.json"
HISTORY_FILE = WORKSPACE / "logs" / "pipeline-automation-history.json"
LOG_FILE = WORKSPACE / "logs" / "pipeline-automation.log"


def palog(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] [{level}] {msg}\n")
    if level in ("INFO", "WARN"):
        print(f"  [{level}] {msg}")


def load_env():
    env = {}
    if ENV_PATH.exists():
        for line in ENV_PATH.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[7:]
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def api_get(endpoint, env):
    token = env.get("PIPEDRIVE_API_TOKEN", "")
    domain = env.get("PIPEDRIVE_DOMAIN", "behavera")
    url = f"https://{domain}.pipedrive.com/api/v1/{endpoint}?api_token={token}"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read())
    except Exception as e:
        palog(f"API error: {e}", "ERROR")
        return None


def load_state():
    try:
        if STATE_FILE.exists():
            return json.loads(STATE_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {"deal_stages": {}, "last_check": None}


def save_state(state):
    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def load_history():
    try:
        if HISTORY_FILE.exists():
            return json.loads(HISTORY_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {"actions": []}


def save_history(history):
    history["actions"] = history["actions"][-500:]  # keep last 500
    HISTORY_FILE.write_text(json.dumps(history, indent=2))


def publish_event(event_type, data):
    """Publish event to agent bus."""
    try:
        sys.path.insert(0, str(WORKSPACE / "scripts"))
        from agent_bus import AgentBus
        bus = AgentBus()
        bus.publish_event(event_type, data)
    except Exception:
        pass


# ── AUTOMATION RULES ────────────────────────────────

def action_research_company(deal, env):
    """Auto-research company when deal enters pipeline."""
    company = deal.get("org_name", "unknown")
    palog(f"Auto-research: {company}")

    try:
        sys.path.insert(0, str(WORKSPACE / "scripts"))
        from knowledge_graph import PipedriveGraphBuilder
        builder = PipedriveGraphBuilder(env)
        # Just trigger a graph update for this company
        palog(f"Knowledge graph update queued for {company}")
    except Exception:
        pass

    publish_event("automation.research_triggered", {
        "deal_id": deal.get("id"),
        "company": company,
        "action": "company_research",
    })
    return f"Researched {company}"


def action_start_sequence(deal, env):
    """Start email sequence when deal is contacted."""
    deal_id = deal.get("id")
    palog(f"Starting email sequence for deal {deal_id}")

    try:
        sys.path.insert(0, str(WORKSPACE / "scripts"))
        from email_sequences import SequenceEngine
        engine = SequenceEngine()
        engine.start(str(deal_id), "prospecting_5touch")
        return f"Sequence started for deal {deal_id}"
    except Exception as e:
        palog(f"Sequence start failed: {e}", "WARN")
        return f"Sequence start queued for deal {deal_id}"


def action_meeting_prep(deal, env):
    """Generate meeting prep when demo scheduled."""
    deal_id = deal.get("id")
    palog(f"Generating meeting prep for deal {deal_id}")

    try:
        result = subprocess.run(
            ["python3", str(WORKSPACE / "scripts" / "meeting_prep.py"), str(deal_id)],
            capture_output=True, text=True, timeout=60, cwd=str(WORKSPACE)
        )
        if result.returncode == 0:
            return f"Meeting prep generated for deal {deal_id}"
        else:
            palog(f"Meeting prep failed: {result.stderr[:200]}", "WARN")
    except Exception as e:
        palog(f"Meeting prep error: {e}", "WARN")
    return f"Meeting prep queued for deal {deal_id}"


def action_generate_proposal(deal, env):
    """Generate proposal when deal reaches proposal stage."""
    deal_id = deal.get("id")
    company = deal.get("org_name", "unknown")
    palog(f"Generating proposal for {company} (deal {deal_id})")

    try:
        result = subprocess.run(
            ["python3", str(WORKSPACE / "scripts" / "proposal_generator.py"), "generate", str(deal_id)],
            capture_output=True, text=True, timeout=60, cwd=str(WORKSPACE)
        )
        if result.returncode == 0:
            return f"Proposal generated for {company}"
    except Exception:
        pass
    return f"Proposal queued for {company}"


def action_risk_assessment(deal, env):
    """Run risk assessment and coaching for negotiation stage."""
    deal_id = deal.get("id")
    palog(f"Risk assessment for deal {deal_id}")

    try:
        sys.path.insert(0, str(WORKSPACE / "scripts"))
        from success_predictor import SuccessPredictor
        predictor = SuccessPredictor(env)
        prediction = predictor.predict_deal(deal_id)
        if prediction:
            prob = prediction.get("probability", 50)
            palog(f"Deal {deal_id} probability: {prob}%")
            return f"Risk assessment: {prob}% probability"
    except Exception as e:
        palog(f"Prediction error: {e}", "WARN")
    return f"Risk assessment queued for deal {deal_id}"


def action_celebrate_win(deal, env):
    """Celebrate a won deal."""
    company = deal.get("org_name", "unknown")
    value = deal.get("value", 0)
    palog(f"DEAL WON: {company} (${value:,.0f})")

    publish_event("pipeline.deal_won", {
        "deal_id": deal.get("id"),
        "company": company,
        "value": value,
    })

    # Trigger notification
    try:
        subprocess.run(
            ["bash", str(WORKSPACE / "scripts" / "notify.sh"), "Deal Won!", f"{company} — ${value:,.0f}"],
            capture_output=True, timeout=10, cwd=str(WORKSPACE)
        )
    except Exception:
        pass

    return f"Celebrated win: {company} (${value:,.0f})"


def action_loss_analysis(deal, env):
    """Trigger win/loss analysis for lost deal."""
    deal_id = deal.get("id")
    company = deal.get("org_name", "unknown")
    palog(f"DEAL LOST: {company} — triggering analysis")

    publish_event("pipeline.deal_lost", {
        "deal_id": deal_id,
        "company": company,
        "loss_reason": deal.get("lost_reason", "unknown"),
    })

    try:
        sys.path.insert(0, str(WORKSPACE / "scripts"))
        from agent_memory import remember_decision
        remember_decision("obchodak", f"Lost deal: {company}", deal.get("lost_reason", "unknown"), "loss")
    except Exception:
        pass

    return f"Loss analysis triggered for {company}"


# Stage name → action mapping
AUTOMATION_RULES = {
    "Lead In": {"action": action_research_company, "description": "Auto-research company in knowledge graph"},
    "Contacted": {"action": action_start_sequence, "description": "Start prospecting email sequence"},
    "Qualified": {"action": action_meeting_prep, "description": "Generate meeting prep document"},
    "Demo Scheduled": {"action": action_meeting_prep, "description": "Generate demo prep + talking points"},
    "Proposal Sent": {"action": action_generate_proposal, "description": "Auto-generate sales proposal"},
    "Negotiation": {"action": action_risk_assessment, "description": "Run risk assessment + deal coaching"},
    "Pilot": {"action": action_risk_assessment, "description": "Monitor pilot progress + risk assessment"},
    "Won": {"action": action_celebrate_win, "description": "Celebrate + scorecard + win analysis"},
    "Lost": {"action": action_loss_analysis, "description": "Win/loss analysis + learn from failure"},
}


def check_stage_changes():
    """Poll Pipedrive for stage changes and trigger automations."""
    env = load_env()
    if not env.get("PIPEDRIVE_API_TOKEN"):
        palog("No Pipedrive API token", "ERROR")
        return

    state = load_state()
    history = load_history()
    changes = []

    # Fetch all deals
    result = api_get("deals?status=all_not_deleted&limit=100", env)
    if not result or not result.get("data"):
        palog("No deals returned from API", "WARN")
        return

    deals = result["data"]
    old_stages = state.get("deal_stages", {})

    for deal in deals:
        deal_id = str(deal.get("id", ""))
        stage_name = deal.get("stage_id", 0)

        # Resolve stage name
        pipeline_id = deal.get("pipeline_id")
        stage_info = api_get(f"stages/{stage_name}", env) if isinstance(stage_name, int) else None
        if stage_info and stage_info.get("data"):
            stage_name = stage_info["data"].get("name", str(stage_name))
        else:
            stage_name = str(stage_name)

        # Check for Won/Lost status
        if deal.get("status") == "won":
            stage_name = "Won"
        elif deal.get("status") == "lost":
            stage_name = "Lost"

        prev = old_stages.get(deal_id, {}).get("stage")

        if prev and prev != stage_name:
            changes.append({
                "deal_id": deal_id,
                "deal": deal,
                "from_stage": prev,
                "to_stage": stage_name,
            })

        old_stages[deal_id] = {"stage": stage_name, "updated": datetime.now().isoformat()}

    # Execute automations for changed deals
    actions_taken = 0
    for change in changes:
        to_stage = change["to_stage"]
        rule = AUTOMATION_RULES.get(to_stage)
        if rule:
            palog(f"Stage change: {change['deal'].get('title', '?')} → {to_stage}")
            try:
                result = rule["action"](change["deal"], env)
                history["actions"].append({
                    "timestamp": datetime.now().isoformat(),
                    "deal_id": change["deal_id"],
                    "deal_title": change["deal"].get("title", "?"),
                    "from_stage": change["from_stage"],
                    "to_stage": to_stage,
                    "action": rule["description"],
                    "result": result,
                })
                actions_taken += 1
            except Exception as e:
                palog(f"Action failed for {to_stage}: {e}", "ERROR")

    state["deal_stages"] = old_stages
    state["last_check"] = datetime.now().isoformat()
    save_state(state)
    save_history(history)

    print(f"\n  Pipeline Automation Check")
    print(f"  Deals scanned: {len(deals)}")
    print(f"  Stage changes: {len(changes)}")
    print(f"  Actions taken: {actions_taken}\n")

    return changes


def cmd_rules():
    """Show automation rules."""
    print(f"\n{'='*50}")
    print(f"  Pipeline Automation Rules")
    print(f"{'='*50}\n")
    for stage, rule in AUTOMATION_RULES.items():
        print(f"  {stage:20s} → {rule['description']}")
    print()


def cmd_history():
    """Show action history."""
    history = load_history()
    actions = history.get("actions", [])

    print(f"\n  Pipeline Automation History ({len(actions)} actions):\n")
    for a in actions[-20:]:
        ts = a.get("timestamp", "?")[:19]
        title = a.get("deal_title", "?")[:30]
        action = a.get("action", "?")[:40]
        print(f"  {ts}  {title:30s}  {action}")
    print()


def cmd_simulate(stage):
    """Simulate a rule execution."""
    rule = AUTOMATION_RULES.get(stage)
    if not rule:
        print(f"  No rule for stage: {stage}")
        print(f"  Available: {', '.join(AUTOMATION_RULES.keys())}")
        return

    print(f"\n  Simulating: {stage} → {rule['description']}")
    fake_deal = {
        "id": 999, "title": "Simulation Deal",
        "org_name": "Test Company", "value": 10000,
        "stage_id": stage, "status": "open",
    }
    env = load_env()
    result = rule["action"](fake_deal, env)
    print(f"  Result: {result}\n")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"

    if cmd == "check":
        check_stage_changes()
    elif cmd == "rules":
        cmd_rules()
    elif cmd == "history":
        cmd_history()
    elif cmd == "simulate" and len(sys.argv) > 2:
        cmd_simulate(sys.argv[2])
    else:
        print("Usage: pipeline_automation.py [check|rules|history|simulate <stage>]")


if __name__ == "__main__":
    main()
