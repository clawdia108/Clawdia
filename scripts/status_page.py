#!/usr/bin/env python3
"""
Mobile-Friendly Status Page Generator
=======================================
Generates a self-contained HTML status page that shows:
- System health at a glance
- Pipeline summary
- Agent states
- Task queue
- Recent events
- Scorecard

Auto-refreshes every 5 minutes. Designed for phone screens.
"""

import json
import time
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/josefhofman/Clawdia")
OUTPUT = BASE / "status" / "index.html"


def get_agent_health():
    """Get agent health data."""
    agents = {
        "spojka": {"file": "knowledge/USER_DIGEST_AM.md", "max_hours": 24},
        "obchodak": {"file": "pipedrive/PIPELINE_STATUS.md", "max_hours": 48},
        "postak": {"file": "inbox/INBOX_DIGEST.md", "max_hours": 24},
        "strateg": {"file": "intel/DAILY-INTEL.md", "max_hours": 48},
        "kalendar": {"file": "calendar/TODAY.md", "max_hours": 24},
        "kontrolor": {"file": "reviews/SYSTEM_HEALTH.md", "max_hours": 72},
        "archivar": {"file": "knowledge/IMPROVEMENTS.md", "max_hours": 72},
    }
    results = []
    now = time.time()
    for name, config in agents.items():
        path = BASE / config["file"]
        if not path.exists():
            results.append({"name": name, "status": "dead", "age": None})
        elif path.stat().st_size < 50:
            results.append({"name": name, "status": "empty", "age": None})
        else:
            age_h = int((now - path.stat().st_mtime) / 3600)
            status = "ok" if age_h <= config["max_hours"] else "stale"
            results.append({"name": name, "status": status, "age": age_h})
    return results


def get_pipeline():
    """Get pipeline summary from DEAL_SCORING.md."""
    path = BASE / "pipedrive" / "DEAL_SCORING.md"
    if not path.exists():
        return None
    content = path.read_text()
    lines = content.splitlines()
    stats = {}
    for line in lines:
        if "Total scored:" in line:
            stats["total"] = line.split(":")[-1].strip().strip("*")
        elif "Sales pipeline:" in line:
            stats["deals"] = line.split(":")[-1].strip().strip("*")
        elif "HOT" in line:
            stats["hot"] = line.split(":")[-1].strip().strip("*")
        elif "WARM" in line:
            stats["warm"] = line.split(":")[-1].strip().strip("*")
        elif "COOL" in line:
            stats["cool"] = line.split(":")[-1].strip().strip("*")
        elif "COLD" in line:
            stats["cold"] = line.split(":")[-1].strip().strip("*")
        elif "pipeline value:" in line:
            stats["value"] = line.split(":")[-1].strip().strip("*")
    return stats


def get_scorecard():
    """Get scorecard data."""
    path = BASE / "reviews" / "daily-scorecard" / "score_state.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def get_execution_state():
    """Get execution state."""
    path = BASE / "knowledge" / "EXECUTION_STATE.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def get_recent_events(n=10):
    """Get recent events."""
    path = BASE / "logs" / "events.jsonl"
    if not path.exists():
        return []
    try:
        lines = path.read_text().splitlines()
        events = []
        for line in lines[-n:]:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events
    except OSError:
        return []


def get_orchestrator_status():
    """Check if orchestrator is running."""
    pid_file = BASE / "logs" / "orchestrator.pid"
    if not pid_file.exists():
        return {"running": False}
    try:
        pid = int(pid_file.read_text().strip())
        import subprocess
        r = subprocess.run(["kill", "-0", str(pid)], capture_output=True)
        return {"running": r.returncode == 0, "pid": pid}
    except (ValueError, OSError):
        return {"running": False}


def generate_html():
    """Generate the complete HTML status page."""
    agents = get_agent_health()
    pipeline = get_pipeline() or {}
    scorecard = get_scorecard() or {}
    state = get_execution_state() or {}
    events = get_recent_events()
    orch = get_orchestrator_status()
    now = datetime.now()

    healthy = sum(1 for a in agents if a["status"] == "ok")
    total = len(agents)
    overall = "ok" if healthy >= 5 else "degraded" if healthy >= 3 else "down"

    # Agent rows
    agent_rows = ""
    for a in agents:
        icon = {"ok": "check_circle", "stale": "warning", "dead": "cancel", "empty": "radio_button_unchecked"}
        color = {"ok": "#4caf50", "stale": "#ff9800", "dead": "#f44336", "empty": "#9e9e9e"}
        age_str = f"{a['age']}h" if a['age'] is not None else "N/A"
        agent_rows += f"""
        <div class="agent-row">
            <span class="material-icons" style="color:{color[a['status']]}">{icon[a['status']]}</span>
            <span class="agent-name">{a['name']}</span>
            <span class="agent-age">{age_str}</span>
        </div>"""

    # Event rows
    event_rows = ""
    for e in reversed(events):
        ts = e.get("ts", "")[:16].replace("T", " ")
        etype = e.get("type", "?")
        event_rows += f'<div class="event-row"><span class="event-time">{ts}</span><span class="event-type">{etype}</span></div>\n'

    # Scorecard
    total_pts = scorecard.get("total_points", 0)
    streak = scorecard.get("streak_days", 0)
    level = scorecard.get("level", "unknown")

    # Pipeline stats
    pipe_deals = pipeline.get("deals", "?")
    pipe_value = pipeline.get("value", "?")
    pipe_hot = pipeline.get("hot", "0")
    pipe_warm = pipeline.get("warm", "0")

    # Task counts
    counts = state.get("counts", {})
    tasks_open = counts.get("open", 0)
    tasks_done = counts.get("done", 0)

    # Overall status
    status_color = {"ok": "#4caf50", "degraded": "#ff9800", "down": "#f44336"}
    status_text = {"ok": "ALL SYSTEMS GO", "degraded": "DEGRADED", "down": "DOWN"}
    orch_status = "Running" if orch.get("running") else "Stopped"
    orch_color = "#4caf50" if orch.get("running") else "#f44336"

    html = f"""<!DOCTYPE html>
<html lang="cs">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="300">
    <title>Clawdia Status</title>
    <link href="https://fonts.googleapis.com/icon?family=Material+Icons" rel="stylesheet">
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'SF Pro', system-ui, sans-serif;
            background: #0d1117;
            color: #e6edf3;
            padding: 16px;
            max-width: 600px;
            margin: 0 auto;
        }}
        .header {{
            text-align: center;
            padding: 20px 0;
            border-bottom: 1px solid #30363d;
        }}
        .status-badge {{
            display: inline-block;
            padding: 8px 24px;
            border-radius: 20px;
            font-weight: 700;
            font-size: 14px;
            letter-spacing: 1px;
            background: {status_color[overall]}22;
            color: {status_color[overall]};
            border: 1px solid {status_color[overall]}44;
        }}
        .header h1 {{
            font-size: 24px;
            margin: 12px 0 4px;
            font-weight: 600;
        }}
        .header .time {{
            color: #8b949e;
            font-size: 13px;
        }}
        .card {{
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 16px;
            margin: 16px 0;
        }}
        .card h2 {{
            font-size: 14px;
            color: #8b949e;
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 12px;
        }}
        .stat-grid {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }}
        .stat-box {{
            background: #0d1117;
            border-radius: 8px;
            padding: 12px;
            text-align: center;
        }}
        .stat-value {{
            font-size: 28px;
            font-weight: 700;
            color: #58a6ff;
        }}
        .stat-label {{
            font-size: 11px;
            color: #8b949e;
            text-transform: uppercase;
            margin-top: 4px;
        }}
        .agent-row {{
            display: flex;
            align-items: center;
            padding: 8px 0;
            border-bottom: 1px solid #21262d;
            gap: 8px;
        }}
        .agent-row:last-child {{ border-bottom: none; }}
        .agent-name {{
            flex: 1;
            font-size: 14px;
            font-weight: 500;
        }}
        .agent-age {{
            color: #8b949e;
            font-size: 13px;
            font-family: monospace;
        }}
        .material-icons {{ font-size: 20px; }}
        .event-row {{
            display: flex;
            gap: 8px;
            padding: 6px 0;
            border-bottom: 1px solid #21262d;
            font-size: 13px;
        }}
        .event-row:last-child {{ border-bottom: none; }}
        .event-time {{ color: #8b949e; font-family: monospace; white-space: nowrap; }}
        .event-type {{ color: #e6edf3; }}
        .orch-status {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            background: #0d1117;
            border-radius: 8px;
            margin-bottom: 12px;
        }}
        .orch-dot {{
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: {orch_color};
        }}
        .pipeline-bar {{
            display: flex;
            height: 8px;
            border-radius: 4px;
            overflow: hidden;
            margin: 8px 0;
            background: #21262d;
        }}
        .pipeline-hot {{ background: #f44336; }}
        .pipeline-warm {{ background: #ff9800; }}
        .pipeline-cool {{ background: #2196f3; }}
        .pipeline-cold {{ background: #607d8b; }}
        .footer {{
            text-align: center;
            padding: 16px 0;
            color: #484f58;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <div class="status-badge">{status_text[overall]}</div>
        <h1>Clawdia</h1>
        <div class="time">{now.strftime('%d.%m.%Y %H:%M')}</div>
    </div>

    <div class="card">
        <div class="orch-status">
            <div class="orch-dot"></div>
            <span>Orchestrator: {orch_status}</span>
            {"<span style='color:#8b949e;margin-left:auto'>PID " + str(orch.get('pid', '')) + "</span>" if orch.get('running') else ""}
        </div>
        <div class="stat-grid">
            <div class="stat-box">
                <div class="stat-value">{healthy}/{total}</div>
                <div class="stat-label">Agents Healthy</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">{total_pts}</div>
                <div class="stat-label">Score Points</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">{pipe_deals}</div>
                <div class="stat-label">Active Deals</div>
            </div>
            <div class="stat-box">
                <div class="stat-value">{streak}</div>
                <div class="stat-label">Day Streak</div>
            </div>
        </div>
    </div>

    <div class="card">
        <h2>Pipeline</h2>
        <div style="display:flex;justify-content:space-between;font-size:13px;margin-bottom:4px">
            <span style="color:#f44336">Hot {pipe_hot}</span>
            <span style="color:#ff9800">Warm {pipe_warm}</span>
            <span style="color:#2196f3">Cool {pipeline.get('cool', '?')}</span>
            <span style="color:#607d8b">Cold {pipeline.get('cold', '?')}</span>
        </div>
        <div class="pipeline-bar">
            <div class="pipeline-hot" style="width:{int(pipe_hot) if pipe_hot.isdigit() else 0}%"></div>
            <div class="pipeline-warm" style="width:{int(pipe_warm) if pipe_warm.isdigit() else 0}%"></div>
            <div class="pipeline-cool" style="width:{int(pipeline.get('cool','0')) if pipeline.get('cool','0').isdigit() else 0}%"></div>
            <div class="pipeline-cold" style="width:{int(pipeline.get('cold','0')) if pipeline.get('cold','0').isdigit() else 0}%"></div>
        </div>
        <div style="text-align:center;font-size:13px;color:#8b949e">Value: {pipe_value}</div>
    </div>

    <div class="card">
        <h2>Agents ({healthy}/{total})</h2>
        {agent_rows}
    </div>

    <div class="card">
        <h2>Scorecard</h2>
        <div style="display:flex;justify-content:space-between;align-items:center">
            <div>
                <div style="font-size:24px;font-weight:700;color:#58a6ff">{total_pts} pts</div>
                <div style="font-size:13px;color:#8b949e">Level: {level}</div>
            </div>
            <div style="text-align:right">
                <div style="font-size:20px">{"&#128293;" * min(streak, 5)}</div>
                <div style="font-size:13px;color:#8b949e">{streak} day streak</div>
            </div>
        </div>
    </div>

    <div class="card">
        <h2>Tasks</h2>
        <div class="stat-grid">
            <div class="stat-box">
                <div class="stat-value" style="color:#ff9800">{tasks_open}</div>
                <div class="stat-label">Open</div>
            </div>
            <div class="stat-box">
                <div class="stat-value" style="color:#4caf50">{tasks_done}</div>
                <div class="stat-label">Done</div>
            </div>
        </div>
    </div>

    <div class="card">
        <h2>Recent Events</h2>
        {event_rows if event_rows else '<div style="color:#8b949e;font-size:13px">No recent events</div>'}
    </div>

    <div class="footer">
        Auto-refreshes every 5 minutes<br>
        Clawdia v2 &mdash; {now.strftime('%Y')}
    </div>
</body>
</html>"""

    return html


def main():
    import sys

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    html = generate_html()
    OUTPUT.write_text(html)
    print(f"Status page generated: {OUTPUT}")
    print(f"Open: file://{OUTPUT}")

    if "--serve" in sys.argv:
        import http.server
        import functools
        port = 8080
        for i, arg in enumerate(sys.argv):
            if arg == "--port" and i + 1 < len(sys.argv):
                port = int(sys.argv[i + 1])

        handler = functools.partial(http.server.SimpleHTTPRequestHandler,
                                     directory=str(OUTPUT.parent))
        with http.server.HTTPServer(("", port), handler) as httpd:
            print(f"Serving at http://localhost:{port}")
            httpd.serve_forever()


if __name__ == "__main__":
    main()
