#!/usr/bin/env python3
"""
Clawdia Health Server — Lightweight HTTP monitoring endpoint
=============================================================
Serves system health data over HTTP for external monitoring,
dashboards, and Prometheus scraping.

Usage:
    python3 scripts/health_server.py                # Start on port 9090
    python3 scripts/health_server.py --port 8080    # Custom port
    python3 scripts/health_server.py --daemon       # Run in background
    python3 scripts/health_server.py --check        # Quick health check
"""

import argparse
import json
import os
import re
import signal
import sys
import time
from datetime import datetime, date, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse

from lib.agent_health import AGENT_OUTPUTS, collect_agent_health

BASE = Path("/Users/josefhofman/Clawdia")

# Data source paths
EXECUTION_STATE = BASE / "knowledge" / "EXECUTION_STATE.json"
ORCHESTRATOR_LOG = BASE / "logs" / "orchestrator.log"
ORCHESTRATOR_PID = BASE / "logs" / "orchestrator.pid"
COST_TRACKER = BASE / "logs" / "cost-tracker.json"
CIRCUIT_BREAKER = BASE / "logs" / "circuit-breaker.json"
SCORECARD_STATE = BASE / "reviews" / "daily-scorecard" / "score_state.json"
DEAL_SCORING = BASE / "pipedrive" / "DEAL_SCORING.md"
PIPELINE_STATUS = BASE / "pipedrive" / "PIPELINE_STATUS.md"
STALE_DEALS = BASE / "pipedrive" / "STALE_DEALS.md"
TASK_QUEUE = BASE / "control-plane" / "task-queue.json"
AGENT_STATES = BASE / "control-plane" / "agent-states.json"
EVENTS_LOG = BASE / "logs" / "events.jsonl"
HEARTBEAT = BASE / "memory" / "HEARTBEAT.md"
APPROVAL_PENDING = BASE / "approval-queue" / "pending"
APPROVAL_APPROVED = BASE / "approval-queue" / "approved"
TRIGGER_OUTBOX = BASE / "triggers" / "outbox"
TRIGGER_PROCESSED = BASE / "triggers" / "processed"

def safe_json_load(path):
    try:
        if path.exists():
            return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def safe_read(path):
    try:
        if path.exists():
            return path.read_text()
    except OSError:
        pass
    return ""


# ── DATA COLLECTORS ───────────────────────────────────

def get_agent_health():
    """Check agent health using runtime timestamps first."""
    return collect_agent_health(workspace=BASE)


def get_agent_states():
    """Load agent state machine data with performance scores."""
    states = safe_json_load(AGENT_STATES)
    health = get_agent_health()
    result = {}
    for agent in AGENT_OUTPUTS:
        agent_state = states.get(agent, {})
        agent_health = health.get(agent, {})
        # Performance score: 100 for OK, 50 for STALE, 0 for DEAD/EMPTY
        perf = {"OK": 100, "STALE": 50, "EMPTY": 10, "DEAD": 0}.get(agent_health.get("status", "DEAD"), 0)
        # Adjust for consecutive failures
        failures = agent_state.get("consecutive_failures", 0)
        perf = max(0, perf - failures * 10)
        result[agent] = {
            "state": agent_state.get("state", "unknown"),
            "current_task": agent_state.get("current_task"),
            "health_status": agent_health.get("status", "UNKNOWN"),
            "age_hours": agent_health.get("age_hours"),
            "performance_score": perf,
            "tasks_completed": agent_state.get("total_tasks_completed", 0),
            "tasks_failed": agent_state.get("total_tasks_failed", 0),
            "consecutive_failures": agent_state.get("consecutive_failures", 0),
        }
    return result


def is_orchestrator_running():
    """Check if orchestrator is alive."""
    if not ORCHESTRATOR_PID.exists():
        return False
    try:
        pid = int(ORCHESTRATOR_PID.read_text().strip())
        os.kill(pid, 0)
        return True
    except (ValueError, OSError):
        return False


def get_recent_errors(hours=1):
    """Count errors in orchestrator log within last N hours."""
    count = 0
    if not ORCHESTRATOR_LOG.exists():
        return 0
    cutoff = datetime.now() - timedelta(hours=hours)
    try:
        for line in ORCHESTRATOR_LOG.read_text().splitlines():
            if "[ERROR]" in line:
                m = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", line)
                if m:
                    try:
                        ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                        if ts > cutoff:
                            count += 1
                    except ValueError:
                        pass
    except OSError:
        pass
    return count


def get_pipeline_summary():
    """Extract pipeline data from markdown files."""
    content = safe_read(PIPELINE_STATUS)
    result = {"sales_deals": 0, "sales_value_czk": 0, "onboarding_deals": 0, "partnerships_deals": 0, "churned_deals": 0}

    for line in content.splitlines():
        if line.startswith("- **Sales:**"):
            m = re.search(r"(\d+)\s*deals", line)
            if m:
                result["sales_deals"] = int(m.group(1))
            m = re.search(r"([\d,]+)\s*CZK", line)
            if m:
                result["sales_value_czk"] = int(m.group(1).replace(",", ""))
        elif line.startswith("- **Onboarding:**"):
            m = re.search(r"(\d+)\s*deals", line)
            if m:
                result["onboarding_deals"] = int(m.group(1))
        elif line.startswith("- **Partnerships:**"):
            m = re.search(r"(\d+)\s*deals", line)
            if m:
                result["partnerships_deals"] = int(m.group(1))
        elif line.startswith("- **Churned:**"):
            m = re.search(r"(\d+)\s*deals", line)
            if m:
                result["churned_deals"] = int(m.group(1))

    # Deal scoring summary
    scoring_content = safe_read(DEAL_SCORING)
    result["scored_total"] = 0
    result["hot_deals"] = 0
    result["warm_deals"] = 0
    result["cool_deals"] = 0
    result["cold_deals"] = 0

    for line in scoring_content.splitlines():
        if "**Total scored:**" in line:
            m = re.search(r"(\d+)", line)
            if m:
                result["scored_total"] = int(m.group(1))
        elif "HOT (80+)" in line:
            m = re.search(r"\*\*(\d+)\*\*", line)
            if m:
                result["hot_deals"] = int(m.group(1))
        elif "WARM (60-79)" in line:
            m = re.search(r"\*\*(\d+)\*\*", line)
            if m:
                result["warm_deals"] = int(m.group(1))
        elif "COOL (40-59)" in line:
            m = re.search(r"\*\*(\d+)\*\*", line)
            if m:
                result["cool_deals"] = int(m.group(1))
        elif "COLD (<40)" in line:
            m = re.search(r"\*\*(\d+)\*\*", line)
            if m:
                result["cold_deals"] = int(m.group(1))

    # Stale deals
    stale_content = safe_read(STALE_DEALS)
    m = re.search(r"\*\*(\d+) deals\*\*", stale_content)
    result["stale_deals"] = int(m.group(1)) if m else 0

    # Overdue count
    overdue = 0
    in_overdue = False
    for line in content.splitlines():
        if "Overdue" in line:
            in_overdue = True
            continue
        if in_overdue and line.startswith("- **"):
            overdue += 1
        elif in_overdue and line.startswith("##"):
            break
    result["overdue_activities"] = overdue

    return result


def get_task_queue_summary():
    """Summarize task queue."""
    tq = safe_json_load(TASK_QUEUE)
    tasks = tq.get("tasks", [])
    return {
        "total": len(tasks),
        "done": sum(1 for t in tasks if t.get("status") == "done"),
        "assigned": sum(1 for t in tasks if t.get("status") == "assigned"),
        "pending": sum(1 for t in tasks if t.get("status") == "pending"),
    }


def get_approval_summary():
    """Summarize approval queue."""
    pending = len(list(APPROVAL_PENDING.iterdir())) if APPROVAL_PENDING.exists() else 0
    approved = len(list(APPROVAL_APPROVED.iterdir())) if APPROVAL_APPROVED.exists() else 0
    return {"pending": pending, "approved": approved}


def get_cost_summary():
    """Load cost data."""
    data = safe_json_load(COST_TRACKER)
    today_str = date.today().isoformat()
    return {
        "today_usd": round(data.get("daily", {}).get(today_str, 0), 4),
        "total_usd": round(data.get("total", 0), 4),
        "by_model": data.get("by_model", {}),
    }


def get_scorecard_summary():
    """Load scorecard state."""
    data = safe_json_load(SCORECARD_STATE)
    today_str = date.today().isoformat()
    return {
        "total_points": data.get("total_points", 0),
        "today_points": data.get("daily_scores", {}).get(today_str, 0),
        "current_streak": data.get("current_streak", 0),
        "best_streak": data.get("best_streak", 0),
        "title": data.get("title", "Unknown"),
        "achievements": len(data.get("achievements", [])),
    }


def get_circuit_breaker_summary():
    """Load circuit breaker state."""
    data = safe_json_load(CIRCUIT_BREAKER)
    result = {}
    for service, info in data.items():
        result[service] = {
            "open": info.get("open", False),
            "failures": info.get("failures", 0),
        }
    return result


def get_orchestrator_cycles_today():
    """Count cycles completed today from events log."""
    today_str = date.today().isoformat()
    count = 0
    if not EVENTS_LOG.exists():
        return 0
    try:
        for line in EVENTS_LOG.read_text().splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                if e.get("type") == "cycle_complete" and e.get("ts", "").startswith(today_str):
                    count += 1
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return count


def get_trigger_summary():
    """Summarize trigger queue."""
    outbox = len(list(TRIGGER_OUTBOX.glob("*.json"))) if TRIGGER_OUTBOX.exists() else 0
    processed = len(list(TRIGGER_PROCESSED.glob("*.json"))) if TRIGGER_PROCESSED.exists() else 0
    return {"pending": outbox, "processed": processed}


# ── HEALTH DETERMINATION ─────────────────────────────

def determine_health():
    """
    Determine overall system health.
    OK: orchestrator running + >=5/7 agents healthy + no P0 errors in last hour
    DEGRADED: orchestrator running but <5 agents healthy OR recent errors
    DOWN: orchestrator not running OR critical failures
    """
    orch_running = is_orchestrator_running()
    health = get_agent_health()
    healthy_count = sum(1 for v in health.values() if v["status"] == "OK")
    total = len(health)
    p0_errors = get_recent_errors(hours=1)

    # Check circuit breakers for critical opens
    circuits = get_circuit_breaker_summary()
    critical_circuits_open = any(v.get("open") for v in circuits.values())

    if not orch_running:
        return "DOWN", f"Orchestrator not running"

    # Check for critical failures (multiple agents dead)
    dead = sum(1 for v in health.values() if v["status"] in ("DEAD", "EMPTY"))
    if dead >= 4:
        return "DOWN", f"{dead}/{total} agents dead/empty"

    if healthy_count >= 5 and p0_errors == 0 and not critical_circuits_open:
        return "OK", f"{healthy_count}/{total} agents healthy"

    reasons = []
    if healthy_count < 5:
        reasons.append(f"{healthy_count}/{total} agents healthy")
    if p0_errors > 0:
        reasons.append(f"{p0_errors} errors in last hour")
    if critical_circuits_open:
        reasons.append("circuit breaker(s) open")

    return "DEGRADED", "; ".join(reasons)


def get_full_status():
    """Build complete status JSON (equivalent to system-status.sh)."""
    health = get_agent_health()
    healthy = sum(1 for v in health.values() if v["status"] == "OK")
    total = len(health)
    overall_status, status_reason = determine_health()

    return {
        "status": overall_status,
        "status_reason": status_reason,
        "timestamp": datetime.now().isoformat(),
        "orchestrator": {
            "running": is_orchestrator_running(),
            "cycles_today": get_orchestrator_cycles_today(),
        },
        "agent_health": {
            "healthy": healthy,
            "total": total,
            "agents": health,
        },
        "pipeline_summary": get_pipeline_summary(),
        "task_queue": get_task_queue_summary(),
        "approval_queue": get_approval_summary(),
        "triggers": get_trigger_summary(),
        "costs": get_cost_summary(),
        "scorecard": get_scorecard_summary(),
        "circuit_breakers": get_circuit_breaker_summary(),
    }


# ── PROMETHEUS METRICS ────────────────────────────────

def generate_prometheus_metrics():
    """Generate Prometheus-compatible metrics."""
    health = get_agent_health()
    healthy = sum(1 for v in health.values() if v["status"] == "OK")
    total = len(health)
    pipeline = get_pipeline_summary()
    scorecard = get_scorecard_summary()
    costs = get_cost_summary()
    tq = get_task_queue_summary()
    approval = get_approval_summary()
    triggers = get_trigger_summary()
    circuits = get_circuit_breaker_summary()
    orch_running = 1 if is_orchestrator_running() else 0
    cycles = get_orchestrator_cycles_today()
    errors_1h = get_recent_errors(hours=1)

    overall_status, _ = determine_health()
    status_code = {"OK": 0, "DEGRADED": 1, "DOWN": 2}.get(overall_status, 2)

    lines = [
        "# HELP clawdia_status Overall system status (0=OK, 1=DEGRADED, 2=DOWN)",
        "# TYPE clawdia_status gauge",
        f"clawdia_status {status_code}",
        "",
        "# HELP clawdia_orchestrator_running Whether orchestrator is alive (0/1)",
        "# TYPE clawdia_orchestrator_running gauge",
        f"clawdia_orchestrator_running {orch_running}",
        "",
        "# HELP clawdia_orchestrator_cycles_total Orchestrator cycles completed today",
        "# TYPE clawdia_orchestrator_cycles_total counter",
        f"clawdia_orchestrator_cycles_total {cycles}",
        "",
        "# HELP clawdia_agents_healthy Number of healthy agents",
        "# TYPE clawdia_agents_healthy gauge",
        f"clawdia_agents_healthy {healthy}",
        "",
        "# HELP clawdia_agents_total Total number of agents",
        "# TYPE clawdia_agents_total gauge",
        f"clawdia_agents_total {total}",
        "",
        "# HELP clawdia_errors_1h Errors in last hour",
        "# TYPE clawdia_errors_1h gauge",
        f"clawdia_errors_1h {errors_1h}",
        "",
        "# HELP clawdia_pipeline_deals_total Total scored deals",
        "# TYPE clawdia_pipeline_deals_total gauge",
        f"clawdia_pipeline_deals_total {pipeline.get('scored_total', 0)}",
        "",
        "# HELP clawdia_pipeline_sales_deals Sales pipeline deals",
        "# TYPE clawdia_pipeline_sales_deals gauge",
        f"clawdia_pipeline_sales_deals {pipeline.get('sales_deals', 0)}",
        "",
        "# HELP clawdia_pipeline_value_czk Sales pipeline value in CZK",
        "# TYPE clawdia_pipeline_value_czk gauge",
        f"clawdia_pipeline_value_czk {pipeline.get('sales_value_czk', 0)}",
        "",
        "# HELP clawdia_pipeline_hot_deals HOT deals (80+ score)",
        "# TYPE clawdia_pipeline_hot_deals gauge",
        f"clawdia_pipeline_hot_deals {pipeline.get('hot_deals', 0)}",
        "",
        "# HELP clawdia_pipeline_warm_deals WARM deals (60-79 score)",
        "# TYPE clawdia_pipeline_warm_deals gauge",
        f"clawdia_pipeline_warm_deals {pipeline.get('warm_deals', 0)}",
        "",
        "# HELP clawdia_pipeline_overdue Overdue deal activities",
        "# TYPE clawdia_pipeline_overdue gauge",
        f"clawdia_pipeline_overdue {pipeline.get('overdue_activities', 0)}",
        "",
        "# HELP clawdia_pipeline_stale Deals without next activity",
        "# TYPE clawdia_pipeline_stale gauge",
        f"clawdia_pipeline_stale {pipeline.get('stale_deals', 0)}",
        "",
        "# HELP clawdia_scorecard_points Total scorecard points",
        "# TYPE clawdia_scorecard_points gauge",
        f"clawdia_scorecard_points {scorecard.get('total_points', 0)}",
        "",
        "# HELP clawdia_scorecard_today Today's scorecard points",
        "# TYPE clawdia_scorecard_today gauge",
        f"clawdia_scorecard_today {scorecard.get('today_points', 0)}",
        "",
        "# HELP clawdia_scorecard_streak Current streak in days",
        "# TYPE clawdia_scorecard_streak gauge",
        f"clawdia_scorecard_streak {scorecard.get('current_streak', 0)}",
        "",
        "# HELP clawdia_costs_today_usd API costs today in USD",
        "# TYPE clawdia_costs_today_usd gauge",
        f"clawdia_costs_today_usd {costs.get('today_usd', 0)}",
        "",
        "# HELP clawdia_costs_total_usd Total API costs in USD",
        "# TYPE clawdia_costs_total_usd gauge",
        f"clawdia_costs_total_usd {costs.get('total_usd', 0)}",
        "",
        "# HELP clawdia_tasks_total Tasks in queue",
        "# TYPE clawdia_tasks_total gauge",
        f"clawdia_tasks_total {tq.get('total', 0)}",
        "",
        "# HELP clawdia_tasks_done Tasks completed",
        "# TYPE clawdia_tasks_done gauge",
        f"clawdia_tasks_done {tq.get('done', 0)}",
        "",
        "# HELP clawdia_approvals_pending Pending approvals",
        "# TYPE clawdia_approvals_pending gauge",
        f"clawdia_approvals_pending {approval.get('pending', 0)}",
        "",
        "# HELP clawdia_triggers_pending Pending triggers",
        "# TYPE clawdia_triggers_pending gauge",
        f"clawdia_triggers_pending {triggers.get('pending', 0)}",
        "",
        "# HELP clawdia_circuits_open Number of open circuit breakers",
        "# TYPE clawdia_circuits_open gauge",
        f"clawdia_circuits_open {sum(1 for v in circuits.values() if v.get('open'))}",
        "",
    ]

    # Per-agent health metrics
    lines.append("# HELP clawdia_agent_healthy Per-agent health (1=OK, 0=not OK)")
    lines.append("# TYPE clawdia_agent_healthy gauge")
    for agent, info in health.items():
        val = 1 if info["status"] == "OK" else 0
        lines.append(f'clawdia_agent_healthy{{agent="{agent}"}} {val}')

    lines.append("")

    return "\n".join(lines) + "\n"


# ── HTML DASHBOARD ────────────────────────────────────

def generate_dashboard_html():
    """Auto-refreshing phone-friendly dashboard."""
    status = get_full_status()
    overall = status["status"]
    reason = status["status_reason"]

    # Status colors
    colors = {"OK": "#22c55e", "DEGRADED": "#eab308", "DOWN": "#ef4444"}
    bg_colors = {"OK": "#052e16", "DEGRADED": "#422006", "DOWN": "#450a0a"}
    status_color = colors.get(overall, "#ef4444")
    bg_color = bg_colors.get(overall, "#450a0a")

    agents = status["agent_health"]["agents"]
    pipeline = status["pipeline_summary"]
    scorecard = status["scorecard"]
    costs = status["costs"]
    tq = status["task_queue"]
    approval = status["approval_queue"]

    agent_rows = ""
    for agent, info in agents.items():
        s = info["status"]
        dot_color = {"OK": "#22c55e", "STALE": "#eab308", "DEAD": "#ef4444", "EMPTY": "#ef4444"}.get(s, "#6b7280")
        age = f"{info['age_hours']}h" if info.get("age_hours") is not None else "--"
        agent_rows += f"""
        <div class="agent-row">
            <span class="dot" style="background:{dot_color}"></span>
            <span class="agent-name">{agent}</span>
            <span class="agent-status">{s}</span>
            <span class="agent-age">{age}</span>
        </div>"""

    orch_status = "RUNNING" if status["orchestrator"]["running"] else "STOPPED"
    orch_color = "#22c55e" if status["orchestrator"]["running"] else "#ef4444"
    cycles = status["orchestrator"]["cycles_today"]

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta http-equiv="refresh" content="30">
<title>Clawdia Status</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: #0a0a0a; color: #e5e5e5; font-family: -apple-system, system-ui, sans-serif; padding: 12px; }}
  .header {{ background: {bg_color}; border: 1px solid {status_color}; border-radius: 8px; padding: 16px; margin-bottom: 12px; text-align: center; }}
  .header h1 {{ font-size: 18px; color: {status_color}; margin-bottom: 4px; }}
  .header .status {{ font-size: 28px; font-weight: bold; color: {status_color}; }}
  .header .reason {{ font-size: 12px; color: #a3a3a3; margin-top: 4px; }}
  .header .time {{ font-size: 11px; color: #737373; margin-top: 4px; }}
  .section {{ background: #171717; border: 1px solid #262626; border-radius: 8px; padding: 12px; margin-bottom: 10px; }}
  .section-title {{ font-size: 13px; font-weight: 600; color: #a3a3a3; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 8px; }}
  .stat-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
  .stat {{ background: #0a0a0a; border-radius: 6px; padding: 10px; }}
  .stat .label {{ font-size: 11px; color: #737373; }}
  .stat .value {{ font-size: 20px; font-weight: bold; color: #fafafa; }}
  .stat .sub {{ font-size: 11px; color: #525252; }}
  .agent-row {{ display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid #1f1f1f; }}
  .agent-row:last-child {{ border-bottom: none; }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
  .agent-name {{ flex: 1; font-size: 13px; font-weight: 500; }}
  .agent-status {{ font-size: 12px; color: #737373; }}
  .agent-age {{ font-size: 12px; color: #525252; min-width: 35px; text-align: right; }}
  .orch-bar {{ display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }}
  .orch-dot {{ width: 10px; height: 10px; border-radius: 50%; background: {orch_color}; }}
  .orch-label {{ font-size: 14px; font-weight: 600; color: {orch_color}; }}
  .footer {{ text-align: center; font-size: 11px; color: #404040; margin-top: 10px; }}
</style>
</head>
<body>
  <div class="header">
    <h1>CLAWDIA</h1>
    <div class="status">{overall}</div>
    <div class="reason">{reason}</div>
    <div class="time">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
  </div>

  <div class="section">
    <div class="orch-bar">
      <div class="orch-dot"></div>
      <div class="orch-label">Orchestrator {orch_status}</div>
    </div>
    <div class="stat-grid">
      <div class="stat">
        <div class="label">Cycles Today</div>
        <div class="value">{cycles}</div>
      </div>
      <div class="stat">
        <div class="label">Agents</div>
        <div class="value">{status['agent_health']['healthy']}/{status['agent_health']['total']}</div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Agents</div>
    {agent_rows}
  </div>

  <div class="section">
    <div class="section-title">Pipeline</div>
    <div class="stat-grid">
      <div class="stat">
        <div class="label">Sales Deals</div>
        <div class="value">{pipeline.get('sales_deals', 0)}</div>
        <div class="sub">{pipeline.get('sales_value_czk', 0):,} CZK</div>
      </div>
      <div class="stat">
        <div class="label">Warm / Hot</div>
        <div class="value">{pipeline.get('warm_deals', 0)} / {pipeline.get('hot_deals', 0)}</div>
        <div class="sub">{pipeline.get('overdue_activities', 0)} overdue</div>
      </div>
      <div class="stat">
        <div class="label">Onboarding</div>
        <div class="value">{pipeline.get('onboarding_deals', 0)}</div>
      </div>
      <div class="stat">
        <div class="label">Stale</div>
        <div class="value">{pipeline.get('stale_deals', 0)}</div>
        <div class="sub">no next activity</div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Scorecard</div>
    <div class="stat-grid">
      <div class="stat">
        <div class="label">Total Points</div>
        <div class="value">{scorecard.get('total_points', 0):,}</div>
        <div class="sub">{scorecard.get('title', '?')}</div>
      </div>
      <div class="stat">
        <div class="label">Today</div>
        <div class="value">{scorecard.get('today_points', 0)}</div>
        <div class="sub">streak: {scorecard.get('current_streak', 0)}d</div>
      </div>
    </div>
  </div>

  <div class="section">
    <div class="section-title">Operations</div>
    <div class="stat-grid">
      <div class="stat">
        <div class="label">Tasks</div>
        <div class="value">{tq.get('done', 0)}/{tq.get('total', 0)}</div>
        <div class="sub">{tq.get('assigned', 0)} assigned</div>
      </div>
      <div class="stat">
        <div class="label">Approvals</div>
        <div class="value">{approval.get('pending', 0)}</div>
        <div class="sub">pending</div>
      </div>
      <div class="stat">
        <div class="label">API Cost</div>
        <div class="value">${costs.get('today_usd', 0):.4f}</div>
        <div class="sub">total: ${costs.get('total_usd', 0):.4f}</div>
      </div>
      <div class="stat">
        <div class="label">Achievements</div>
        <div class="value">{scorecard.get('achievements', 0)}</div>
      </div>
    </div>
  </div>

  <div class="footer">Auto-refresh 30s | Clawdia Ops Engine</div>
</body>
</html>"""

    return html


# ── HTTP SERVER ───────────────────────────────────────

class HealthHandler(BaseHTTPRequestHandler):
    """Handle health check HTTP requests."""

    def log_message(self, format, *args):
        """Suppress default logging for clean output."""
        pass

    def _cors_headers(self):
        """Add CORS headers for browser access."""
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _respond_json(self, data, status_code=200):
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self._cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2, ensure_ascii=False).encode())

    def _respond_text(self, text, content_type="text/plain", status_code=200):
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self._cors_headers()
        self.end_headers()
        self.wfile.write(text.encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors_headers()
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/")

        try:
            if path == "" or path == "/":
                html = generate_dashboard_html()
                self._respond_text(html, content_type="text/html")

            elif path == "/health":
                status, reason = determine_health()
                status_codes = {"OK": 200, "DEGRADED": 503, "DOWN": 500}
                http_code = status_codes.get(status, 500)
                self._respond_json({
                    "status": status,
                    "reason": reason,
                    "timestamp": datetime.now().isoformat(),
                }, status_code=http_code)

            elif path == "/status":
                self._respond_json(get_full_status())

            elif path == "/agents":
                self._respond_json(get_agent_states())

            elif path == "/pipeline":
                self._respond_json(get_pipeline_summary())

            elif path == "/metrics":
                metrics = generate_prometheus_metrics()
                self._respond_text(metrics, content_type="text/plain; version=0.0.4; charset=utf-8")

            else:
                self._respond_json({"error": "not found", "endpoints": [
                    "/", "/health", "/status", "/agents", "/pipeline", "/metrics",
                ]}, status_code=404)

        except Exception as e:
            self._respond_json({"error": str(e)}, status_code=500)


class HealthServer:
    def __init__(self, port=9090):
        self.port = port
        self.server = None

    def start(self, daemon=False):
        """Start the health server."""
        if daemon:
            self._daemonize()

        self.server = HTTPServer(("0.0.0.0", self.port), HealthHandler)
        import subprocess
        try:
            local_ip = subprocess.check_output(
                ["ipconfig", "getifaddr", "en0"], text=True
            ).strip()
        except Exception:
            local_ip = "0.0.0.0"
        print(f"Clawdia Health Server running on http://{local_ip}:{self.port}")
        print(f"Endpoints: /health /status /agents /pipeline /metrics")
        print(f"Dashboard: http://{local_ip}:{self.port}/")

        # Graceful shutdown on signals
        def shutdown_handler(signum, frame):
            print("\nShutting down health server...")
            self.server.shutdown()
            sys.exit(0)

        signal.signal(signal.SIGTERM, shutdown_handler)
        signal.signal(signal.SIGINT, shutdown_handler)

        try:
            self.server.serve_forever()
        except KeyboardInterrupt:
            print("\nHealth server stopped.")

    def _daemonize(self):
        """Fork into background."""
        pid = os.fork()
        if pid > 0:
            print(f"Health server daemonized (PID: {pid})")
            sys.exit(0)
        os.setsid()
        # Redirect stdio
        devnull = open(os.devnull, "r+b")
        os.dup2(devnull.fileno(), sys.stdin.fileno())
        os.dup2(devnull.fileno(), sys.stdout.fileno())
        os.dup2(devnull.fileno(), sys.stderr.fileno())

    @staticmethod
    def quick_check(port=9090):
        """Quick health check (like curl)."""
        import urllib.request
        try:
            url = f"http://localhost:{port}/health"
            req = urllib.request.Request(url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                status = data.get("status", "UNKNOWN")
                reason = data.get("reason", "")
                code = resp.status

                status_symbols = {"OK": "+", "DEGRADED": "~", "DOWN": "!"}
                sym = status_symbols.get(status, "?")
                print(f"[{sym}] {status} (HTTP {code}) — {reason}")
                return 0 if status == "OK" else 1
        except urllib.error.URLError:
            print("[!] DOWN — Health server not reachable")
            return 2
        except Exception as e:
            print(f"[!] ERROR — {e}")
            return 2


def main():
    parser = argparse.ArgumentParser(description="Clawdia Health Server")
    parser.add_argument("--port", type=int, default=9090, help="Port to listen on (default: 9090)")
    parser.add_argument("--daemon", action="store_true", help="Run in background")
    parser.add_argument("--check", action="store_true", help="Quick health check (curl-like)")
    args = parser.parse_args()

    if args.check:
        sys.exit(HealthServer.quick_check(port=args.port))

    server = HealthServer(port=args.port)
    server.start(daemon=args.daemon)


if __name__ == "__main__":
    main()
