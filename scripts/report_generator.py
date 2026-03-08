#!/usr/bin/env python3
"""
Weekly Report Generator — Comprehensive HTML business reports
==============================================================
Auto-generates weekly reports with:
- Pipeline changes (new, won, lost, stalled)
- Agent performance metrics
- System uptime & health trends
- Cost analysis
- Deal velocity analysis
- Top recommendations

Outputs self-contained HTML with inline SVG charts.

Usage:
  python3 scripts/report_generator.py generate       # Generate this week's report
  python3 scripts/report_generator.py list            # List all reports
  python3 scripts/report_generator.py latest          # Open latest report
"""

import json
import re
import sys
import time
import math
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

from lib.agent_health import AGENT_OUTPUTS, collect_agent_health

WORKSPACE = Path(__file__).resolve().parents[1]
REPORTS_DIR = WORKSPACE / "reports"
LOG_FILE = WORKSPACE / "logs" / "report-generator.log"
TODAY = date.today()
NOW = datetime.now()


def rlog(msg, level="INFO"):
    ts = NOW.strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] [{level}] {msg}\n")


def safe_json(path):
    try:
        if Path(path).exists():
            return json.loads(Path(path).read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return None


def safe_md(path):
    try:
        if Path(path).exists():
            return Path(path).read_text()
    except OSError:
        pass
    return ""


# ── DATA COLLECTORS ─────────────────────────────────

def collect_pipeline_data():
    """Collect pipeline metrics."""
    data = {"total_deals": 0, "total_value": 0, "by_stage": {}, "won": 0, "lost": 0, "new": 0}

    scoring = safe_md(WORKSPACE / "pipedrive" / "DEAL_SCORING.md")
    if scoring:
        deals = re.findall(r"Score:\s*(\d+)", scoring)
        data["total_deals"] = len(deals)

    pipeline = safe_md(WORKSPACE / "pipedrive" / "PIPELINE_STATUS.md")
    if pipeline:
        for m in re.finditer(r"\*\*(.+?)\*\*:\s*(\d+)\s*deals?\s*\([\$€]?([\d,.]+)", pipeline):
            stage, count, value = m.group(1), int(m.group(2)), m.group(3)
            val = float(value.replace(",", ""))
            data["by_stage"][stage] = {"count": int(count), "value": val}
            data["total_value"] += val

        won_m = re.search(r"[Ww]on.*?(\d+)", pipeline)
        lost_m = re.search(r"[Ll]ost.*?(\d+)", pipeline)
        if won_m:
            data["won"] = int(won_m.group(1))
        if lost_m:
            data["lost"] = int(lost_m.group(1))

    velocity = safe_json(WORKSPACE / "pipedrive" / "deal_velocity.json")
    if velocity:
        data["velocity"] = velocity.get("stage_averages", {})

    return data


def collect_agent_metrics():
    """Collect agent health and performance."""
    results = []
    health = collect_agent_health(workspace=WORKSPACE)
    status_map = {"OK": "healthy", "STALE": "stale", "EMPTY": "empty", "DEAD": "dead"}
    for name in AGENT_OUTPUTS:
        info = health.get(name, {})
        results.append({
            "name": name,
            "status": status_map.get(info.get("status"), "dead"),
            "age_h": info.get("age_hours"),
            "health_source": info.get("source"),
            "output_status": info.get("output_status"),
        })

    states = safe_json(WORKSPACE / "control-plane" / "agent-states.json") or {}
    for r in results:
        s = states.get(r["name"], {})
        r["tasks_completed"] = s.get("total_tasks_completed", 0)
        r["tasks_failed"] = s.get("total_tasks_failed", 0)
        r["current_state"] = s.get("state", "unknown")

    return results


def collect_system_health():
    """Collect system health metrics."""
    health = {
        "orchestrator_running": False,
        "bus_messages": 0,
        "dead_letters": 0,
        "circuit_breakers_open": 0,
        "workflows_active": 0,
        "tasks_pending": 0,
    }

    import subprocess
    try:
        out = subprocess.run(["pgrep", "-f", "orchestrator.py"], capture_output=True, text=True)
        health["orchestrator_running"] = out.returncode == 0
    except Exception:
        pass

    outbox = WORKSPACE / "bus" / "outbox"
    if outbox.exists():
        health["bus_messages"] = len(list(outbox.glob("*.json")))

    dead = WORKSPACE / "bus" / "dead-letter"
    if dead.exists():
        health["dead_letters"] = len(list(dead.glob("*.json")))

    cb = safe_json(WORKSPACE / "logs" / "circuit-breaker.json") or {}
    health["circuit_breakers_open"] = sum(1 for v in cb.values() if isinstance(v, dict) and v.get("open"))

    wf_active = WORKSPACE / "workflows" / "active"
    if wf_active.exists():
        health["workflows_active"] = len(list(wf_active.glob("*.json")))

    tq = safe_json(WORKSPACE / "control-plane" / "task-queue.json")
    if tq and "tasks" in tq:
        health["tasks_pending"] = sum(1 for t in tq["tasks"]
                                       if isinstance(t, dict) and t.get("status") != "done")

    return health


def collect_cost_data():
    """Collect cost tracking data."""
    costs = safe_json(WORKSPACE / "logs" / "cost-tracker.json")
    if not costs:
        return {"total": 0, "today": 0, "by_model": {}, "week": 0}

    today_key = TODAY.isoformat()
    daily = costs.get("daily", {})

    week_start = TODAY - timedelta(days=TODAY.weekday())
    week_total = 0
    for d in range(7):
        day_key = (week_start + timedelta(days=d)).isoformat()
        week_total += daily.get(day_key, 0)

    return {
        "total": costs.get("total", 0),
        "today": daily.get(today_key, 0),
        "week": week_total,
        "by_model": costs.get("by_model", {}),
        "daily_trend": {k: v for k, v in sorted(daily.items())[-14:]},
    }


def collect_scorecard():
    """Get scorecard data."""
    sc = safe_json(WORKSPACE / "reviews" / "daily-scorecard" / "score_state.json")
    if not sc:
        return {"total_points": 0, "level": 0, "streak": 0, "achievements": []}
    return {
        "total_points": sc.get("total_points", 0),
        "level": sc.get("level", 0),
        "title": sc.get("title", "Unknown"),
        "streak": sc.get("current_streak", 0),
        "achievements": sc.get("achievements", []),
    }


# ── SVG CHART GENERATORS ───────────────────────────

def svg_bar_chart(data, width=500, height=200, title=""):
    """Generate inline SVG bar chart."""
    if not data:
        return ""

    items = list(data.items())[:10]
    max_val = max(v for _, v in items) or 1
    bar_w = min(50, (width - 80) // len(items))
    gap = 10

    bars = []
    x = 60
    for label, value in items:
        bar_h = int((value / max_val) * (height - 60))
        y = height - 30 - bar_h
        color = "#4CAF50" if value > max_val * 0.7 else "#2196F3" if value > max_val * 0.3 else "#FF9800"
        bars.append(f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" fill="{color}" rx="3"/>')
        bars.append(f'<text x="{x + bar_w//2}" y="{height - 12}" text-anchor="middle" font-size="10" fill="#888">{label[:8]}</text>')
        bars.append(f'<text x="{x + bar_w//2}" y="{y - 5}" text-anchor="middle" font-size="10" fill="#ccc">{value:.0f}</text>')
        x += bar_w + gap

    svg = f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <text x="{width//2}" y="18" text-anchor="middle" font-size="14" fill="#fff" font-weight="bold">{title}</text>
  {''.join(bars)}
</svg>'''
    return svg


def svg_donut_chart(data, width=250, height=250, title=""):
    """Generate inline SVG donut chart."""
    if not data:
        return ""

    total = sum(data.values()) or 1
    colors = ["#4CAF50", "#2196F3", "#FF9800", "#E91E63", "#9C27B0", "#00BCD4", "#FF5722"]
    cx, cy, r = width // 2, height // 2 + 10, 80
    inner_r = 50

    paths = []
    legend = []
    angle = 0
    for i, (label, value) in enumerate(data.items()):
        pct = value / total
        end_angle = angle + pct * 2 * math.pi
        if pct >= 0.999:
            # Full circle
            paths.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{colors[i % len(colors)]}" />')
        elif pct > 0.001:
            x1 = cx + r * math.cos(angle - math.pi/2)
            y1 = cy + r * math.sin(angle - math.pi/2)
            x2 = cx + r * math.cos(end_angle - math.pi/2)
            y2 = cy + r * math.sin(end_angle - math.pi/2)
            ix1 = cx + inner_r * math.cos(end_angle - math.pi/2)
            iy1 = cy + inner_r * math.sin(end_angle - math.pi/2)
            ix2 = cx + inner_r * math.cos(angle - math.pi/2)
            iy2 = cy + inner_r * math.sin(angle - math.pi/2)
            large = 1 if pct > 0.5 else 0
            d = f"M{x1},{y1} A{r},{r} 0 {large},1 {x2},{y2} L{ix1},{iy1} A{inner_r},{inner_r} 0 {large},0 {ix2},{iy2} Z"
            paths.append(f'<path d="{d}" fill="{colors[i % len(colors)]}" />')

        legend.append(f'<rect x="{width + 10}" y="{20 + i * 22}" width="12" height="12" fill="{colors[i % len(colors)]}" rx="2"/>')
        legend.append(f'<text x="{width + 28}" y="{31 + i * 22}" font-size="11" fill="#ccc">{label} ({pct:.0%})</text>')
        angle = end_angle

    svg = f'''<svg width="{width + 160}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <text x="{cx}" y="14" text-anchor="middle" font-size="14" fill="#fff" font-weight="bold">{title}</text>
  <circle cx="{cx}" cy="{cy}" r="{inner_r}" fill="#1a1a2e" />
  {''.join(paths)}
  <circle cx="{cx}" cy="{cy}" r="{inner_r}" fill="#1a1a2e" />
  <text x="{cx}" y="{cy + 5}" text-anchor="middle" font-size="20" fill="#fff" font-weight="bold">{total}</text>
  {''.join(legend)}
</svg>'''
    return svg


def svg_trend_line(data, width=500, height=150, title=""):
    """Generate inline SVG trend line chart."""
    if not data or len(data) < 2:
        return ""

    items = sorted(data.items())[-14:]  # last 14 data points
    values = [v for _, v in items]
    labels = [k for k, _ in items]
    max_val = max(values) or 1
    min_val = min(values)
    val_range = max_val - min_val or 1

    points = []
    x_step = (width - 80) / (len(values) - 1) if len(values) > 1 else 0
    for i, v in enumerate(values):
        x = 50 + i * x_step
        y = height - 30 - ((v - min_val) / val_range) * (height - 60)
        points.append(f"{x},{y}")

    polyline = " ".join(points)

    # Area fill
    area_points = f"50,{height - 30} {polyline} {50 + (len(values) - 1) * x_step},{height - 30}"

    x_labels = []
    step = max(1, len(labels) // 5)
    for i in range(0, len(labels), step):
        x = 50 + i * x_step
        short = labels[i][-5:]  # MM-DD
        x_labels.append(f'<text x="{x}" y="{height - 10}" text-anchor="middle" font-size="9" fill="#888">{short}</text>')

    svg = f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
  <text x="{width//2}" y="16" text-anchor="middle" font-size="13" fill="#fff" font-weight="bold">{title}</text>
  <polygon points="{area_points}" fill="rgba(33,150,243,0.15)" />
  <polyline points="{polyline}" fill="none" stroke="#2196F3" stroke-width="2" />
  {''.join(x_labels)}
  <text x="10" y="35" font-size="9" fill="#888">{max_val:.2f}</text>
  <text x="10" y="{height - 32}" font-size="9" fill="#888">{min_val:.2f}</text>
</svg>'''
    return svg


# ── HTML REPORT GENERATION ──────────────────────────

def generate_report():
    """Generate the complete weekly report."""
    week_start = TODAY - timedelta(days=TODAY.weekday())
    week_end = week_start + timedelta(days=6)
    week_label = f"{week_start.isoformat()} to {week_end.isoformat()}"

    rlog(f"Generating weekly report for {week_label}")

    # Collect all data
    pipeline = collect_pipeline_data()
    agents = collect_agent_metrics()
    system = collect_system_health()
    costs = collect_cost_data()
    scorecard = collect_scorecard()

    healthy = sum(1 for a in agents if a["status"] == "healthy")
    total_agents = len(agents)
    total_tasks_done = sum(a.get("tasks_completed", 0) for a in agents)

    # Build charts
    stage_chart = ""
    if pipeline["by_stage"]:
        stage_data = {k: v["count"] for k, v in pipeline["by_stage"].items()}
        stage_chart = svg_donut_chart(stage_data, title="Deals by Stage")

    stage_value_chart = ""
    if pipeline["by_stage"]:
        val_data = {k: v["value"] for k, v in pipeline["by_stage"].items()}
        stage_value_chart = svg_bar_chart(val_data, title="Pipeline Value by Stage")

    cost_trend = ""
    if costs.get("daily_trend"):
        cost_trend = svg_trend_line(costs["daily_trend"], title="Daily API Costs (14d)")

    model_chart = ""
    if costs.get("by_model"):
        model_chart = svg_bar_chart(costs["by_model"], title="Cost by Model")

    # Agent status table
    agent_rows = ""
    for a in agents:
        status_color = {"healthy": "#4CAF50", "stale": "#FF9800", "dead": "#f44336", "empty": "#999"}.get(a["status"], "#999")
        age_str = f"{a['age_h']}h ago" if a["age_h"] is not None else "N/A"
        agent_rows += f"""
        <tr>
          <td style="padding:8px;border-bottom:1px solid #333;">{a['name']}</td>
          <td style="padding:8px;border-bottom:1px solid #333;"><span style="color:{status_color};font-weight:bold;">{a['status'].upper()}</span></td>
          <td style="padding:8px;border-bottom:1px solid #333;">{a['current_state']}</td>
          <td style="padding:8px;border-bottom:1px solid #333;">{age_str}</td>
          <td style="padding:8px;border-bottom:1px solid #333;">{a['tasks_completed']}</td>
          <td style="padding:8px;border-bottom:1px solid #333;">{a['tasks_failed']}</td>
        </tr>"""

    # Velocity table
    velocity_rows = ""
    if pipeline.get("velocity"):
        for stage, avg_days in sorted(pipeline["velocity"].items(), key=lambda x: x[1]):
            bar_w = min(200, int(avg_days * 3))
            velocity_rows += f"""
            <tr>
              <td style="padding:6px;border-bottom:1px solid #333;">{stage}</td>
              <td style="padding:6px;border-bottom:1px solid #333;">
                <div style="background:#2196F3;height:16px;width:{bar_w}px;border-radius:3px;display:inline-block;"></div>
                {avg_days:.1f} days
              </td>
            </tr>"""

    # Recommendations
    recommendations = []
    if healthy < total_agents:
        stale_names = [a["name"] for a in agents if a["status"] in ("stale", "dead")]
        recommendations.append(f"Fix {total_agents - healthy} unhealthy agent(s): {', '.join(stale_names)}")
    if system["dead_letters"] > 0:
        recommendations.append(f"Clear {system['dead_letters']} dead-letter message(s) — check bus/dead-letter/")
    if system["circuit_breakers_open"] > 0:
        recommendations.append(f"{system['circuit_breakers_open']} circuit breaker(s) OPEN — investigate service failures")
    if not system["orchestrator_running"]:
        recommendations.append("Orchestrator not running — `launchctl start com.clawdia.orchestrator`")
    if costs.get("week", 0) > 5.0:
        recommendations.append(f"Weekly API cost ${costs['week']:.2f} — consider routing more to Ollama")
    if pipeline.get("total_deals", 0) == 0:
        recommendations.append("No deals tracked — run `./scripts/clawdia.sh pipeline`")
    if not recommendations:
        recommendations.append("All systems nominal — keep the momentum going")

    recs_html = "\n".join(f'<li style="margin:8px 0;color:#ddd;">{r}</li>' for r in recommendations)

    # Achievements
    achievements_html = ""
    if scorecard.get("achievements"):
        badges = " ".join(f'<span style="background:#333;padding:4px 10px;border-radius:12px;font-size:12px;margin:3px;">{a}</span>'
                         for a in scorecard["achievements"])
        achievements_html = f'<div style="margin-top:8px;">{badges}</div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Clawdia Weekly Report — {week_label}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:#0d1117; color:#e6e6e6; padding:20px; max-width:1000px; margin:0 auto; }}
  .header {{ text-align:center; padding:30px 0; border-bottom:2px solid #2196F3; margin-bottom:30px; }}
  .header h1 {{ font-size:28px; color:#fff; }}
  .header .subtitle {{ color:#888; margin-top:8px; font-size:14px; }}
  .section {{ margin:30px 0; }}
  .section h2 {{ font-size:20px; color:#2196F3; margin-bottom:15px; padding-bottom:8px; border-bottom:1px solid #222; }}
  .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:15px; }}
  .card {{ background:#161b22; border:1px solid #30363d; border-radius:10px; padding:20px; }}
  .card .value {{ font-size:32px; font-weight:bold; color:#fff; }}
  .card .label {{ font-size:13px; color:#888; margin-top:5px; }}
  .card.green .value {{ color:#4CAF50; }}
  .card.blue .value {{ color:#2196F3; }}
  .card.orange .value {{ color:#FF9800; }}
  .card.red .value {{ color:#f44336; }}
  table {{ width:100%; border-collapse:collapse; }}
  th {{ text-align:left; padding:10px 8px; border-bottom:2px solid #333; color:#888; font-size:12px; text-transform:uppercase; }}
  .chart-row {{ display:flex; flex-wrap:wrap; gap:20px; justify-content:center; align-items:flex-start; }}
  .rec-list {{ list-style:none; padding:0; }}
  .rec-list li::before {{ content:"→ "; color:#2196F3; font-weight:bold; }}
  .footer {{ text-align:center; color:#555; font-size:12px; margin-top:40px; padding-top:20px; border-top:1px solid #222; }}
  @media (max-width:600px) {{ .grid {{ grid-template-columns:1fr 1fr; }} .chart-row {{ flex-direction:column; align-items:center; }} }}
</style>
</head>
<body>

<div class="header">
  <h1>Clawdia Weekly Report</h1>
  <div class="subtitle">{week_label} | Generated {NOW.strftime('%Y-%m-%d %H:%M')}</div>
</div>

<!-- KPI Cards -->
<div class="section">
  <h2>Key Metrics</h2>
  <div class="grid">
    <div class="card blue">
      <div class="value">{pipeline['total_deals']}</div>
      <div class="label">Active Deals</div>
    </div>
    <div class="card green">
      <div class="value">${pipeline['total_value']:,.0f}</div>
      <div class="label">Pipeline Value</div>
    </div>
    <div class="card green">
      <div class="value">{pipeline['won']}</div>
      <div class="label">Won This Period</div>
    </div>
    <div class="card {'red' if pipeline['lost'] > pipeline['won'] else 'orange'}">
      <div class="value">{pipeline['lost']}</div>
      <div class="label">Lost This Period</div>
    </div>
    <div class="card {'green' if healthy == total_agents else 'orange'}">
      <div class="value">{healthy}/{total_agents}</div>
      <div class="label">Healthy Agents</div>
    </div>
    <div class="card blue">
      <div class="value">{total_tasks_done}</div>
      <div class="label">Tasks Completed</div>
    </div>
    <div class="card {'green' if system['orchestrator_running'] else 'red'}">
      <div class="value">{'ON' if system['orchestrator_running'] else 'OFF'}</div>
      <div class="label">Orchestrator</div>
    </div>
    <div class="card orange">
      <div class="value">${costs.get('week', 0):.2f}</div>
      <div class="label">Weekly API Cost</div>
    </div>
  </div>
</div>

<!-- Pipeline Charts -->
<div class="section">
  <h2>Pipeline Analysis</h2>
  <div class="chart-row">
    {stage_chart}
    {stage_value_chart}
  </div>
</div>

<!-- Deal Velocity -->
{'<div class="section"><h2>Deal Velocity by Stage</h2><table>' + velocity_rows + '</table></div>' if velocity_rows else ''}

<!-- Agent Performance -->
<div class="section">
  <h2>Agent Performance</h2>
  <table>
    <tr>
      <th>Agent</th><th>Health</th><th>State</th><th>Last Update</th><th>Done</th><th>Failed</th>
    </tr>
    {agent_rows}
  </table>
</div>

<!-- Scorecard -->
<div class="section">
  <h2>ADHD Scorecard</h2>
  <div class="grid">
    <div class="card blue">
      <div class="value">{scorecard['total_points']}</div>
      <div class="label">Total Points</div>
    </div>
    <div class="card green">
      <div class="value">Lv.{scorecard['level']}</div>
      <div class="label">{scorecard.get('title', '')}</div>
    </div>
    <div class="card orange">
      <div class="value">{scorecard['streak']}d</div>
      <div class="label">Current Streak</div>
    </div>
  </div>
  {achievements_html}
</div>

<!-- Cost Analysis -->
<div class="section">
  <h2>Cost Analysis</h2>
  <div class="grid">
    <div class="card">
      <div class="value">${costs.get('total', 0):.2f}</div>
      <div class="label">Total Spend</div>
    </div>
    <div class="card">
      <div class="value">${costs.get('today', 0):.4f}</div>
      <div class="label">Today</div>
    </div>
  </div>
  <div class="chart-row" style="margin-top:20px;">
    {cost_trend}
    {model_chart}
  </div>
</div>

<!-- System Health -->
<div class="section">
  <h2>System Health</h2>
  <div class="grid">
    <div class="card {'green' if system['bus_messages'] == 0 else 'orange'}">
      <div class="value">{system['bus_messages']}</div>
      <div class="label">Pending Bus Messages</div>
    </div>
    <div class="card {'green' if system['dead_letters'] == 0 else 'red'}">
      <div class="value">{system['dead_letters']}</div>
      <div class="label">Dead Letters</div>
    </div>
    <div class="card">
      <div class="value">{system['workflows_active']}</div>
      <div class="label">Active Workflows</div>
    </div>
    <div class="card">
      <div class="value">{system['tasks_pending']}</div>
      <div class="label">Pending Tasks</div>
    </div>
  </div>
</div>

<!-- Recommendations -->
<div class="section">
  <h2>Recommendations</h2>
  <ul class="rec-list">
    {recs_html}
  </ul>
</div>

<div class="footer">
  Generated by Clawdia Report Generator | {NOW.strftime('%Y-%m-%d %H:%M:%S')}
</div>

</body>
</html>"""

    # Save
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"weekly_{week_start.isoformat()}.html"
    output = REPORTS_DIR / filename
    output.write_text(html)

    # Save manifest
    manifest_path = REPORTS_DIR / "manifest.json"
    manifest = safe_json(manifest_path) or {"reports": []}
    manifest["reports"].append({
        "file": filename,
        "week": week_label,
        "generated": NOW.isoformat(),
        "metrics": {
            "deals": pipeline["total_deals"],
            "pipeline_value": pipeline["total_value"],
            "healthy_agents": healthy,
            "weekly_cost": costs.get("week", 0),
        },
    })
    manifest_path.write_text(json.dumps(manifest, indent=2))

    rlog(f"Report generated: {output}")
    print(f"\nWeekly Report Generated")
    print(f"  File: {output}")
    print(f"  Period: {week_label}")
    print(f"  Pipeline: {pipeline['total_deals']} deals, ${pipeline['total_value']:,.0f}")
    print(f"  Agents: {healthy}/{total_agents} healthy")
    print(f"  Cost: ${costs.get('week', 0):.2f} this week")
    print(f"  Recommendations: {len(recommendations)}")

    return output


def list_reports():
    """List all generated reports."""
    manifest = safe_json(REPORTS_DIR / "manifest.json")
    if not manifest or not manifest.get("reports"):
        print("No reports generated yet. Run: python3 scripts/report_generator.py generate")
        return

    print(f"\nGenerated Reports ({len(manifest['reports'])}):\n")
    for r in manifest["reports"]:
        print(f"  {r['file']}")
        print(f"    Week: {r['week']}")
        print(f"    Deals: {r['metrics']['deals']}, Pipeline: ${r['metrics']['pipeline_value']:,.0f}")
        print()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "generate"

    if cmd == "generate":
        path = generate_report()
    elif cmd == "list":
        list_reports()
    elif cmd == "latest":
        manifest = safe_json(REPORTS_DIR / "manifest.json")
        if manifest and manifest.get("reports"):
            latest = REPORTS_DIR / manifest["reports"][-1]["file"]
            print(f"Latest: {latest}")
            import subprocess
            subprocess.run(["open", str(latest)], capture_output=True)
        else:
            print("No reports yet.")
    else:
        print("Usage: report_generator.py [generate|list|latest]")


if __name__ == "__main__":
    main()
