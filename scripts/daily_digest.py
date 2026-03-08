#!/usr/bin/env python3
"""
Daily Digest Email — Morning summary delivered to your inbox
=============================================================
Composes and sends a daily digest email at 7:30 AM with:
- Pipeline summary (new, won, lost, stalled)
- Actions needed today
- Agent health status
- Scorecard progress
- Anomalies detected
- Top 3 deal recommendations

Uses Resend API for delivery. HTML template matching Clawdia dark theme.

Usage:
  python3 scripts/daily_digest.py send                # Send today's digest
  python3 scripts/daily_digest.py preview             # Preview without sending
  python3 scripts/daily_digest.py test                # Send test email
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime, date
from pathlib import Path

from lib.agent_health import AGENT_OUTPUTS, collect_agent_health
from lib.paths import WORKSPACE
from lib.secrets import load_secrets
from lib.logger import make_logger

dlog = make_logger("daily-digest")


def safe_json(path):
    try:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return None


def safe_md(path):
    try:
        p = Path(path)
        if p.exists():
            return p.read_text()
    except OSError:
        pass
    return ""


def collect_digest_data():
    """Collect all data for the digest."""
    data = {}

    # Pipeline
    pipeline_md = safe_md(WORKSPACE / "pipedrive" / "PIPELINE_STATUS.md")
    data["pipeline_summary"] = pipeline_md[:500] if pipeline_md else "No pipeline data"

    # Scoring
    scoring_md = safe_md(WORKSPACE / "pipedrive" / "DEAL_SCORING.md")
    if scoring_md:
        import re
        scores = re.findall(r"##\s+(.+?)\n.*?Score:\s*(\d+)", scoring_md, re.DOTALL)
        data["top_deals"] = sorted(scores, key=lambda x: int(x[1]), reverse=True)[:5]
    else:
        data["top_deals"] = []

    # Agent health
    health = collect_agent_health(workspace=WORKSPACE)
    healthy = 0
    total = len(AGENT_OUTPUTS)
    agent_issues = []
    for name in AGENT_OUTPUTS:
        info = health.get(name, {})
        if info.get("status") == "OK":
            healthy += 1
            continue
        if info.get("age_hours") is not None:
            agent_issues.append(f"{name} ({info['status'].lower()} {info['age_hours']:.0f}h)")
        else:
            agent_issues.append(f"{name} ({info.get('output_status', 'missing')})")

    data["agents_healthy"] = healthy
    data["agents_total"] = total
    data["agent_issues"] = agent_issues

    # Scorecard
    sc = safe_json(WORKSPACE / "reviews" / "daily-scorecard" / "score_state.json")
    data["scorecard"] = sc or {"total_points": 0, "level": 0, "current_streak": 0}

    # Orchestrator
    pid_file = WORKSPACE / "logs" / "orchestrator.pid"
    data["orchestrator_running"] = False
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            data["orchestrator_running"] = True
        except (ValueError, ProcessLookupError, PermissionError):
            pass

    # Tasks
    tq = safe_json(WORKSPACE / "control-plane" / "task-queue.json")
    data["pending_tasks"] = 0
    if tq:
        data["pending_tasks"] = sum(1 for t in tq.get("tasks", [])
                                     if isinstance(t, dict) and t.get("status") == "pending")

    # Anomalies
    anomalies = safe_json(WORKSPACE / "logs" / "anomalies.json")
    data["anomalies_critical"] = 0
    data["anomalies_warning"] = 0
    if anomalies:
        for a in anomalies.get("anomalies", [])[-50:]:
            if isinstance(a, dict):
                sev = a.get("severity", "")
                if sev == "critical":
                    data["anomalies_critical"] += 1
                elif sev == "warning":
                    data["anomalies_warning"] += 1

    # Stale deals
    stale_md = safe_md(WORKSPACE / "pipedrive" / "STALE_DEALS.md")
    data["stale_deals"] = stale_md[:300] if stale_md else "No stale deals"

    return data


def generate_html(data):
    """Generate HTML email content."""
    today = date.today().strftime("%A, %B %d, %Y")

    sc = data.get("scorecard", {})
    points = sc.get("total_points", 0)
    streak = sc.get("current_streak", 0)
    level = sc.get("level", 0)
    title = sc.get("title", "")

    orch_status = "RUNNING" if data["orchestrator_running"] else "STOPPED"
    orch_color = "#4CAF50" if data["orchestrator_running"] else "#f44336"

    agent_color = "#4CAF50" if data["agents_healthy"] == data["agents_total"] else "#FF9800"

    # Top deals table
    deals_rows = ""
    for name, score in data.get("top_deals", [])[:5]:
        score_color = "#4CAF50" if int(score) > 70 else "#FF9800" if int(score) > 40 else "#f44336"
        deals_rows += f'<tr><td style="padding:6px 12px;border-bottom:1px solid #333;">{name.strip()[:40]}</td>'
        deals_rows += f'<td style="padding:6px 12px;border-bottom:1px solid #333;color:{score_color};font-weight:bold;">{score}</td></tr>'

    # Agent issues
    issues_html = ""
    if data["agent_issues"]:
        issues_html = '<div style="background:#1a1a2e;padding:12px;border-radius:8px;margin-top:12px;">'
        issues_html += '<span style="color:#FF9800;font-weight:bold;">Issues:</span> '
        issues_html += ", ".join(data["agent_issues"])
        issues_html += '</div>'

    # Anomaly warning
    anomaly_html = ""
    if data["anomalies_critical"] > 0 or data["anomalies_warning"] > 0:
        anomaly_html = f'''
        <div style="background:#2d1b1b;border:1px solid #f44336;padding:12px;border-radius:8px;margin:15px 0;">
          <span style="color:#f44336;font-weight:bold;">Anomalies:</span>
          {data["anomalies_critical"]} critical, {data["anomalies_warning"]} warnings
        </div>'''

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#0d1117;color:#e6e6e6;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">

<div style="max-width:600px;margin:0 auto;padding:20px;">

  <!-- Header -->
  <div style="text-align:center;padding:20px 0;border-bottom:2px solid #2196F3;">
    <h1 style="font-size:24px;color:#fff;margin:0;">Clawdia Daily Digest</h1>
    <p style="color:#888;font-size:13px;margin-top:8px;">{today}</p>
  </div>

  <!-- KPI Strip -->
  <div style="display:flex;justify-content:space-around;padding:20px 0;border-bottom:1px solid #222;">
    <div style="text-align:center;">
      <div style="font-size:28px;font-weight:bold;color:{orch_color};">{orch_status}</div>
      <div style="font-size:11px;color:#888;">Orchestrator</div>
    </div>
    <div style="text-align:center;">
      <div style="font-size:28px;font-weight:bold;color:{agent_color};">{data['agents_healthy']}/{data['agents_total']}</div>
      <div style="font-size:11px;color:#888;">Agents</div>
    </div>
    <div style="text-align:center;">
      <div style="font-size:28px;font-weight:bold;color:#2196F3;">{points}</div>
      <div style="font-size:11px;color:#888;">Points (Lv.{level})</div>
    </div>
    <div style="text-align:center;">
      <div style="font-size:28px;font-weight:bold;color:#FF9800;">{data['pending_tasks']}</div>
      <div style="font-size:11px;color:#888;">Tasks</div>
    </div>
  </div>

  {anomaly_html}
  {issues_html}

  <!-- Top Deals -->
  <div style="margin:20px 0;">
    <h2 style="font-size:16px;color:#2196F3;margin-bottom:10px;">Top Deals</h2>
    <table style="width:100%;border-collapse:collapse;">
      <tr>
        <th style="text-align:left;padding:6px 12px;border-bottom:2px solid #333;color:#888;font-size:11px;">DEAL</th>
        <th style="text-align:left;padding:6px 12px;border-bottom:2px solid #333;color:#888;font-size:11px;">SCORE</th>
      </tr>
      {deals_rows or '<tr><td colspan="2" style="padding:12px;color:#666;">No deals scored yet</td></tr>'}
    </table>
  </div>

  <!-- Actions -->
  <div style="margin:20px 0;">
    <h2 style="font-size:16px;color:#2196F3;margin-bottom:10px;">Actions Needed</h2>
    <div style="background:#161b22;border:1px solid #30363d;border-radius:8px;padding:15px;">
      <ul style="margin:0;padding-left:20px;line-height:1.8;">
        {'<li>Check stale agents: ' + ', '.join(data['agent_issues'][:3]) + '</li>' if data['agent_issues'] else ''}
        {'<li>Review ' + str(data["anomalies_critical"]) + ' critical anomalies</li>' if data["anomalies_critical"] else ''}
        {'<li>' + str(data['pending_tasks']) + ' tasks pending dispatch</li>' if data['pending_tasks'] else ''}
        <li>Run: <code>./scripts/clawdia.sh status</code> for full dashboard</li>
      </ul>
    </div>
  </div>

  <!-- Footer -->
  <div style="text-align:center;color:#555;font-size:11px;padding-top:20px;border-top:1px solid #222;">
    Clawdia Daily Digest | {datetime.now().strftime('%Y-%m-%d %H:%M')}
  </div>

</div>
</body>
</html>"""
    return html


def send_email(html, secrets):
    """Send email via Resend API."""
    resend_key = secrets.get("RESEND_API_KEY")
    if not resend_key:
        dlog("No RESEND_API_KEY found", "ERROR")
        return False

    recipient = secrets.get("DIGEST_EMAIL", secrets.get("JOSEF_EMAIL", "clawdia108@gmail.com"))
    if not recipient:
        dlog("No recipient email configured", "ERROR")
        return False

    payload = json.dumps({
        "from": f"Clawdia <{secrets.get('RESEND_FROM_EMAIL', 'onboarding@resend.dev')}>",
        "to": [recipient],
        "subject": f"Clawdia Daily Digest — {date.today().strftime('%b %d')}",
        "html": html,
    }).encode()

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={
            "Authorization": f"Bearer {resend_key}",
            "Content-Type": "application/json",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read())
            dlog(f"Email sent: {result.get('id', '?')}")
            print(f"  Email sent to {recipient}")
            return True
    except urllib.error.HTTPError as e:
        body = e.read().decode() if hasattr(e, 'read') else str(e)
        dlog(f"Resend API error: {e.code} {body}", "ERROR")
        print(f"  Send failed: {e.code}")
        return False
    except Exception as e:
        dlog(f"Send error: {e}", "ERROR")
        print(f"  Send failed: {e}")
        return False


def cmd_send():
    """Generate and send daily digest."""
    secrets = load_secrets()
    data = collect_digest_data()
    html = generate_html(data)

    print(f"\n  Daily Digest — {date.today()}")
    print(f"  Agents: {data['agents_healthy']}/{data['agents_total']}")
    print(f"  Orchestrator: {'Running' if data['orchestrator_running'] else 'STOPPED'}")
    print(f"  Top deals: {len(data.get('top_deals', []))}")
    print(f"  Anomalies: {data['anomalies_critical']}c / {data['anomalies_warning']}w")

    success = send_email(html, secrets)
    if not success:
        # Save locally as fallback
        out = WORKSPACE / "logs" / f"digest_{date.today()}.html"
        out.write_text(html)
        print(f"  Saved locally: {out}")


def cmd_preview():
    """Preview digest without sending."""
    data = collect_digest_data()
    html = generate_html(data)

    out = WORKSPACE / "status" / "digest_preview.html"
    out.parent.mkdir(exist_ok=True)
    out.write_text(html)
    print(f"\n  Preview saved: {out}")

    import subprocess
    subprocess.run(["open", str(out)], capture_output=True)


def cmd_test():
    """Send a test email."""
    secrets = load_secrets()
    html = "<h1>Clawdia Test Email</h1><p>If you see this, email delivery works.</p>"

    resend_key = secrets.get("RESEND_API_KEY")
    if not resend_key:
        print("  No RESEND_API_KEY — cannot send test email")
        return

    recipient = secrets.get("DIGEST_EMAIL", secrets.get("JOSEF_EMAIL", ""))
    if not recipient:
        print("  No recipient email configured")
        return

    payload = json.dumps({
        "from": "Clawdia <clawdia@resend.dev>",
        "to": [recipient],
        "subject": "Clawdia Test Email",
        "html": html,
    }).encode()

    req = urllib.request.Request(
        "https://api.resend.com/emails",
        data=payload,
        headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            print(f"  Test email sent to {recipient}")
    except Exception as e:
        print(f"  Failed: {e}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "send"

    if cmd == "send":
        cmd_send()
    elif cmd == "preview":
        cmd_preview()
    elif cmd == "test":
        cmd_test()
    else:
        print("Usage: daily_digest.py [send|preview|test]")


if __name__ == "__main__":
    main()
