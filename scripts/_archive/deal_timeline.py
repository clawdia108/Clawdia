#!/usr/bin/env python3
"""
Deal Activity Timeline Visualizer
===================================
Generates SVG timelines showing deal activity history, stage changes,
and activity gaps. Wraps in dark-themed HTML pages.

Usage:
  python3 scripts/deal_timeline.py deal <deal_id>   # Single deal timeline
  python3 scripts/deal_timeline.py all               # Pipeline overview (all active deals)
  python3 scripts/deal_timeline.py gaps              # Deals with activity gaps
"""

import json
import math
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
ENV_PATH = WORKSPACE / ".secrets" / "pipedrive.env"
STATUS_DIR = WORKSPACE / "status"
LOG_FILE = WORKSPACE / "logs" / "deal-timeline.log"

TODAY = date.today()
NOW = datetime.now()

ACTIVITY_COLORS = {
    "email": "#2196F3",
    "call": "#4CAF50",
    "meeting": "#9C27B0",
    "demo": "#FF9800",
    "note": "#9E9E9E",
    "proposal": "#f44336",
    "task": "#00BCD4",
    "deadline": "#E91E63",
    "lunch": "#8BC34A",
}

DEFAULT_ACTIVITY_COLOR = "#607D8B"

STAGE_NAMES = {
    7: "Interested/Qualified",
    8: "Demo Scheduled",
    28: "Ongoing Discussion",
    9: "Proposal Made",
    10: "Negotiation",
    12: "Pilot",
    29: "Contract Sent",
    11: "Invoice Sent",
}

GAP_YELLOW_DAYS = 7
GAP_RED_DAYS = 14


# -- ENV & API ---------------------------------------------------------------

def load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def api_request(base, token, method, path, params=None, retry=3):
    params = dict(params or {})
    params["api_token"] = token
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method=method)
    for i in range(retry):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < retry - 1:
                time.sleep(2 * (i + 1))
                continue
            raise
    return None


def paged_get(base, token, path, params=None):
    out = []
    start = 0
    while True:
        p = dict(params or {})
        p.update({"start": start, "limit": 500})
        j = api_request(base, token, "GET", path, params=p)
        if not j or not j.get("success"):
            break
        out.extend(j.get("data") or [])
        pag = (j.get("additional_data") or {}).get("pagination") or {}
        if not pag.get("more_items_in_collection"):
            break
        start = pag.get("next_start", start + 500)
    return out


def tlog(msg, level="INFO"):
    ts = NOW.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    try:
        if LOG_FILE.stat().st_size > 200_000:
            lines = LOG_FILE.read_text().splitlines()
            LOG_FILE.write_text("\n".join(lines[-500:]) + "\n")
    except OSError:
        pass


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def escape_html(s):
    return (str(s)
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


# -- DATA FETCHING -----------------------------------------------------------

def fetch_deal(base, token, deal_id):
    resp = api_request(base, token, "GET", f"/api/v1/deals/{deal_id}")
    if resp and resp.get("success"):
        return resp.get("data")
    return None


def fetch_deal_activities(base, token, deal_id):
    return paged_get(base, token, f"/api/v1/deals/{deal_id}/activities", {"done": "1"})


def fetch_deal_updates(base, token, deal_id):
    """Fetch deal flow (stage changes etc.)."""
    return paged_get(base, token, f"/api/v1/deals/{deal_id}/flow")


def fetch_all_open_deals(base, token):
    return paged_get(base, token, "/api/v1/deals", {"status": "open"})


def extract_stage_changes(flow_items):
    """Extract stage change events from deal flow data."""
    changes = []
    for item in (flow_items or []):
        obj = item.get("object") or item.get("data") or item
        change_source = item.get("change_source") or ""
        timestamp = item.get("timestamp") or obj.get("log_time") or obj.get("update_time") or ""

        if item.get("field_key") == "stage_id" or item.get("change_source") == "stage_change":
            old_val = item.get("old_value") or ""
            new_val = item.get("new_value") or ""
            dt = parse_date(timestamp)
            if dt:
                old_name = ""
                new_name = ""
                try:
                    old_name = STAGE_NAMES.get(int(old_val), str(old_val))
                except (ValueError, TypeError):
                    old_name = str(old_val)
                try:
                    new_name = STAGE_NAMES.get(int(new_val), str(new_val))
                except (ValueError, TypeError):
                    new_name = str(new_val)
                changes.append({
                    "date": dt,
                    "from_stage": old_name,
                    "to_stage": new_name,
                })
            continue

        if isinstance(obj, dict) and "stage_id" in obj:
            pass

    # Deduplicate by date + to_stage
    seen = set()
    unique = []
    for c in changes:
        key = (c["date"], c["to_stage"])
        if key not in seen:
            seen.add(key)
            unique.append(c)

    return sorted(unique, key=lambda x: x["date"])


def normalize_activity_type(raw_type):
    if not raw_type:
        return "note"
    t = raw_type.lower().strip()
    mapping = {
        "email": "email",
        "e-mail": "email",
        "mail": "email",
        "call": "call",
        "phone": "call",
        "meeting": "meeting",
        "demo": "demo",
        "note": "note",
        "proposal": "proposal",
        "task": "task",
        "deadline": "deadline",
        "lunch": "lunch",
    }
    return mapping.get(t, t)


def build_activity_list(raw_activities):
    activities = []
    for a in (raw_activities or []):
        due_date = parse_date(a.get("due_date"))
        if not due_date:
            due_date = parse_date(a.get("add_time"))
        if not due_date:
            continue

        atype = normalize_activity_type(a.get("type"))
        subject = a.get("subject") or a.get("note") or ""
        activities.append({
            "date": due_date,
            "type": atype,
            "subject": subject[:80],
            "done": a.get("done", False),
        })

    return sorted(activities, key=lambda x: x["date"])


def find_activity_gaps(activities):
    """Find gaps > GAP_YELLOW_DAYS between consecutive activities."""
    gaps = []
    if len(activities) < 2:
        return gaps

    for i in range(len(activities) - 1):
        d1 = activities[i]["date"]
        d2 = activities[i + 1]["date"]
        delta = (d2 - d1).days
        if delta >= GAP_YELLOW_DAYS:
            severity = "red" if delta >= GAP_RED_DAYS else "yellow"
            gaps.append({
                "start": d1,
                "end": d2,
                "days": delta,
                "severity": severity,
            })

    # Check gap from last activity to today
    if activities:
        last = activities[-1]["date"]
        delta = (TODAY - last).days
        if delta >= GAP_YELLOW_DAYS:
            severity = "red" if delta >= GAP_RED_DAYS else "yellow"
            gaps.append({
                "start": last,
                "end": TODAY,
                "days": delta,
                "severity": severity,
            })

    return gaps


# -- SVG GENERATION ----------------------------------------------------------

class DealTimeline:
    """Generates an SVG timeline for a single deal."""

    def __init__(self, base_url, api_token):
        self.base = base_url
        self.token = api_token

    def generate(self, deal_id):
        tlog(f"Generating timeline for deal {deal_id}")

        deal = fetch_deal(self.base, self.token, deal_id)
        if not deal:
            tlog(f"Deal {deal_id} not found", "ERROR")
            return None

        raw_activities = fetch_deal_activities(self.base, self.token, deal_id)
        flow = fetch_deal_updates(self.base, self.token, deal_id)

        activities = build_activity_list(raw_activities)
        stage_changes = extract_stage_changes(flow)
        gaps = find_activity_gaps(activities)

        deal_title = deal.get("title", f"Deal #{deal_id}")
        org_name = deal.get("org_name") or ""
        value = deal.get("value") or 0
        currency = deal.get("currency", "CZK")
        current_stage = STAGE_NAMES.get(deal.get("stage_id"), "Unknown")
        add_date = parse_date(deal.get("add_time"))

        svg = self._render_timeline_svg(
            deal_id=deal_id,
            deal_title=deal_title,
            org_name=org_name,
            value=value,
            currency=currency,
            current_stage=current_stage,
            add_date=add_date,
            activities=activities,
            stage_changes=stage_changes,
            gaps=gaps,
        )

        html = self._wrap_html(
            title=f"Timeline: {deal_title}",
            body_content=svg,
            subtitle=f"{org_name} | {current_stage} | {value:,.0f} {currency}",
        )

        STATUS_DIR.mkdir(parents=True, exist_ok=True)
        output = STATUS_DIR / f"timeline_{deal_id}.html"
        output.write_text(html)

        tlog(f"Timeline saved: {output}")
        return output

    def _render_timeline_svg(self, deal_id, deal_title, org_name, value,
                             currency, current_stage, add_date, activities,
                             stage_changes, gaps):
        # Determine time range
        all_dates = [a["date"] for a in activities]
        all_dates += [c["date"] for c in stage_changes]
        if add_date:
            all_dates.append(add_date)
        all_dates.append(TODAY)

        if not all_dates:
            return '<div style="color:#888;text-align:center;padding:40px;">No activity data</div>'

        min_date = min(all_dates)
        max_date = max(all_dates)
        total_days = max((max_date - min_date).days, 1)

        width = max(800, min(1600, total_days * 8 + 200))
        height = 280
        margin_left = 60
        margin_right = 60
        margin_top = 60
        axis_y = 160
        track_width = width - margin_left - margin_right

        def date_to_x(d):
            if total_days == 0:
                return margin_left
            frac = (d - min_date).days / total_days
            return margin_left + frac * track_width

        parts = []
        parts.append(f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">')
        parts.append(f'<style>')
        parts.append(f'  .tooltip {{ display: none; }}')
        parts.append(f'  .dot-group:hover .tooltip {{ display: block; }}')
        parts.append(f'  .dot-group:hover circle {{ r: 8; }}')
        parts.append(f'</style>')

        # Background
        parts.append(f'<rect width="{width}" height="{height}" fill="#0d1117" rx="8"/>')

        # Title
        parts.append(f'<text x="{width//2}" y="28" text-anchor="middle" font-size="16" '
                      f'fill="#e6edf3" font-weight="bold" font-family="system-ui,sans-serif">'
                      f'{escape_html(deal_title[:60])}</text>')
        parts.append(f'<text x="{width//2}" y="46" text-anchor="middle" font-size="12" '
                      f'fill="#8b949e" font-family="system-ui,sans-serif">'
                      f'{escape_html(org_name)} | {escape_html(current_stage)} | '
                      f'{value:,.0f} {currency}</text>')

        # Gap highlights (behind everything)
        for gap in gaps:
            x1 = date_to_x(gap["start"])
            x2 = date_to_x(gap["end"])
            color = "#f4433633" if gap["severity"] == "red" else "#ff980033"
            border = "#f4433666" if gap["severity"] == "red" else "#ff980066"
            parts.append(f'<rect x="{x1}" y="{axis_y - 35}" width="{max(x2-x1, 2)}" '
                         f'height="70" fill="{color}" stroke="{border}" stroke-width="1" rx="3"/>')
            mid_x = (x1 + x2) / 2
            parts.append(f'<text x="{mid_x}" y="{axis_y + 52}" text-anchor="middle" '
                         f'font-size="9" fill="{"#f44336" if gap["severity"] == "red" else "#ff9800"}" '
                         f'font-family="system-ui,sans-serif">{gap["days"]}d gap</text>')

        # Time axis line
        parts.append(f'<line x1="{margin_left}" y1="{axis_y}" x2="{margin_left + track_width}" '
                      f'y2="{axis_y}" stroke="#30363d" stroke-width="2"/>')

        # Axis tick marks and labels
        num_ticks = min(12, max(4, total_days // 7))
        for i in range(num_ticks + 1):
            frac = i / num_ticks
            x = margin_left + frac * track_width
            tick_date = min_date + timedelta(days=int(frac * total_days))
            parts.append(f'<line x1="{x}" y1="{axis_y - 4}" x2="{x}" y2="{axis_y + 4}" '
                         f'stroke="#30363d" stroke-width="1"/>')
            parts.append(f'<text x="{x}" y="{axis_y + 18}" text-anchor="middle" font-size="9" '
                         f'fill="#8b949e" font-family="monospace">{tick_date.strftime("%m/%d")}</text>')

        # Stage change markers (vertical dashed lines)
        for sc in stage_changes:
            x = date_to_x(sc["date"])
            parts.append(f'<line x1="{x}" y1="{margin_top}" x2="{x}" y2="{axis_y + 25}" '
                         f'stroke="#58a6ff" stroke-width="1" stroke-dasharray="4,3"/>')
            label = escape_html(sc["to_stage"][:18])
            parts.append(f'<text x="{x + 3}" y="{margin_top + 4}" font-size="9" fill="#58a6ff" '
                         f'font-family="system-ui,sans-serif" transform="rotate(-35,{x+3},{margin_top+4})">'
                         f'{label}</text>')

        # Activity dots
        for act in activities:
            x = date_to_x(act["date"])
            atype = act["type"]
            color = ACTIVITY_COLORS.get(atype, DEFAULT_ACTIVITY_COLOR)
            subject = escape_html(act["subject"][:50])
            date_str = act["date"].strftime("%Y-%m-%d")

            parts.append(f'<g class="dot-group" style="cursor:pointer;">')
            parts.append(f'  <circle cx="{x}" cy="{axis_y}" r="5" fill="{color}" '
                         f'stroke="#0d1117" stroke-width="1.5"/>')
            # Tooltip
            tt_width = max(len(subject) * 6.5, 120)
            tt_x = min(x - 10, width - tt_width - 20)
            tt_x = max(tt_x, 5)
            parts.append(f'  <g class="tooltip">')
            parts.append(f'    <rect x="{tt_x}" y="{axis_y - 75}" width="{tt_width}" height="34" '
                         f'rx="4" fill="#161b22" stroke="#30363d" stroke-width="1"/>')
            parts.append(f'    <text x="{tt_x + 6}" y="{axis_y - 58}" font-size="10" fill="{color}" '
                         f'font-weight="bold" font-family="system-ui,sans-serif">'
                         f'{atype.upper()} - {date_str}</text>')
            parts.append(f'    <text x="{tt_x + 6}" y="{axis_y - 46}" font-size="9" fill="#e6edf3" '
                         f'font-family="system-ui,sans-serif">{subject}</text>')
            parts.append(f'  </g>')
            parts.append(f'</g>')

        # Today marker
        if min_date <= TODAY <= max_date:
            x_today = date_to_x(TODAY)
            parts.append(f'<line x1="{x_today}" y1="{axis_y - 15}" x2="{x_today}" y2="{axis_y + 15}" '
                         f'stroke="#4CAF50" stroke-width="2"/>')
            parts.append(f'<text x="{x_today}" y="{axis_y - 20}" text-anchor="middle" font-size="9" '
                         f'fill="#4CAF50" font-family="system-ui,sans-serif">today</text>')

        # Legend
        legend_x = margin_left
        legend_y = height - 20
        for atype, color in ACTIVITY_COLORS.items():
            parts.append(f'<circle cx="{legend_x}" cy="{legend_y}" r="4" fill="{color}"/>')
            parts.append(f'<text x="{legend_x + 8}" y="{legend_y + 3}" font-size="9" '
                         f'fill="#8b949e" font-family="system-ui,sans-serif">{atype}</text>')
            legend_x += len(atype) * 7 + 24

        parts.append('</svg>')
        return "\n".join(parts)

    def _wrap_html(self, title, body_content, subtitle=""):
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape_html(title)}</title>
<style>
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: -apple-system,BlinkMacSystemFont,'SF Pro',system-ui,sans-serif;
    background: #0d1117;
    color: #e6edf3;
    padding: 20px;
    max-width: 1200px;
    margin: 0 auto;
  }}
  .header {{
    text-align: center;
    padding: 20px 0;
    border-bottom: 1px solid #30363d;
    margin-bottom: 24px;
  }}
  .header h1 {{ font-size: 22px; color: #fff; }}
  .header .subtitle {{ color: #8b949e; margin-top: 6px; font-size: 13px; }}
  .timeline-container {{
    overflow-x: auto;
    margin: 20px 0;
    padding: 10px 0;
  }}
  .stats-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
    gap: 12px;
    margin: 20px 0;
  }}
  .stat-card {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 16px;
    text-align: center;
  }}
  .stat-card .value {{ font-size: 24px; font-weight: 700; color: #58a6ff; }}
  .stat-card .label {{ font-size: 11px; color: #8b949e; text-transform: uppercase; margin-top: 4px; }}
  .stat-card.warn .value {{ color: #ff9800; }}
  .stat-card.danger .value {{ color: #f44336; }}
  .stat-card.ok .value {{ color: #4CAF50; }}
  .gap-list {{
    margin: 20px 0;
  }}
  .gap-item {{
    display: flex;
    align-items: center;
    padding: 10px 14px;
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    margin: 8px 0;
    gap: 12px;
    font-size: 13px;
  }}
  .gap-badge {{
    padding: 3px 10px;
    border-radius: 12px;
    font-size: 11px;
    font-weight: 600;
  }}
  .gap-badge.yellow {{ background: #ff980022; color: #ff9800; border: 1px solid #ff980044; }}
  .gap-badge.red {{ background: #f4433622; color: #f44336; border: 1px solid #f4433644; }}
  .footer {{
    text-align: center;
    color: #484f58;
    font-size: 12px;
    margin-top: 30px;
    padding-top: 16px;
    border-top: 1px solid #21262d;
  }}
  .mini-timeline {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 16px;
    margin: 12px 0;
  }}
  .mini-timeline .deal-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
  }}
  .mini-timeline .deal-title {{
    font-size: 14px;
    font-weight: 600;
    color: #e6edf3;
  }}
  .mini-timeline .deal-meta {{
    font-size: 12px;
    color: #8b949e;
  }}
  .mini-timeline .deal-stage {{
    font-size: 11px;
    color: #58a6ff;
    padding: 2px 8px;
    background: #58a6ff22;
    border-radius: 10px;
  }}
</style>
</head>
<body>
<div class="header">
  <h1>{escape_html(title)}</h1>
  <div class="subtitle">{escape_html(subtitle)} | Generated {NOW.strftime('%Y-%m-%d %H:%M')}</div>
</div>
{body_content}
<div class="footer">
  Clawdia Deal Timeline | {NOW.strftime('%Y-%m-%d %H:%M:%S')}
</div>
</body>
</html>"""


# -- PIPELINE DASHBOARD ------------------------------------------------------

class PipelineDashboard:
    """Overview of ALL active deals as mini-timelines."""

    def __init__(self, base_url, api_token):
        self.base = base_url
        self.token = api_token

    def generate(self):
        tlog("Generating pipeline overview")
        deals = fetch_all_open_deals(self.base, self.token)
        tlog(f"Fetched {len(deals)} open deals")

        # Collect per-deal activity data
        deal_summaries = []
        for deal in deals:
            deal_id = deal["id"]
            deal_title = deal.get("title", f"Deal #{deal_id}")
            org_name = deal.get("org_name") or ""
            value = deal.get("value") or 0
            currency = deal.get("currency", "CZK")
            stage_id = deal.get("stage_id")
            stage_name = STAGE_NAMES.get(stage_id, "Unknown")
            add_date = parse_date(deal.get("add_time"))
            last_activity_date = parse_date(deal.get("last_activity_date"))

            raw_activities = fetch_deal_activities(self.base, self.token, deal_id)
            activities = build_activity_list(raw_activities)
            gaps = find_activity_gaps(activities)

            days_since_last = (TODAY - last_activity_date).days if last_activity_date else 999
            max_gap = max((g["days"] for g in gaps), default=0)
            has_red_gap = any(g["severity"] == "red" for g in gaps)

            deal_summaries.append({
                "deal_id": deal_id,
                "title": deal_title,
                "org": org_name,
                "value": value,
                "currency": currency,
                "stage_name": stage_name,
                "add_date": add_date,
                "last_activity_date": last_activity_date,
                "days_since_last": days_since_last,
                "activities": activities,
                "gaps": gaps,
                "max_gap": max_gap,
                "has_red_gap": has_red_gap,
                "activity_count": len(activities),
            })

        # Sort by most recent activity (most recent first)
        deal_summaries.sort(key=lambda d: d["days_since_last"])

        body = self._render_overview(deal_summaries)

        tl = DealTimeline(self.base, self.token)
        html = tl._wrap_html(
            title="Pipeline Overview",
            body_content=body,
            subtitle=f"{len(deal_summaries)} active deals",
        )

        STATUS_DIR.mkdir(parents=True, exist_ok=True)
        output = STATUS_DIR / "pipeline_overview.html"
        output.write_text(html)
        tlog(f"Pipeline overview saved: {output}")
        return output, deal_summaries

    def _render_overview(self, summaries):
        parts = []

        # KPI cards
        total = len(summaries)
        with_gaps = sum(1 for d in summaries if d["has_red_gap"])
        no_activity_7d = sum(1 for d in summaries if d["days_since_last"] >= 7)
        total_activities = sum(d["activity_count"] for d in summaries)

        parts.append('<div class="stats-grid">')
        parts.append(f'<div class="stat-card"><div class="value">{total}</div>'
                     f'<div class="label">Active Deals</div></div>')
        parts.append(f'<div class="stat-card ok"><div class="value">{total_activities}</div>'
                     f'<div class="label">Total Activities</div></div>')
        parts.append(f'<div class="stat-card {"danger" if with_gaps > 0 else "ok"}">'
                     f'<div class="value">{with_gaps}</div>'
                     f'<div class="label">With 14d+ Gaps</div></div>')
        parts.append(f'<div class="stat-card {"warn" if no_activity_7d > 0 else "ok"}">'
                     f'<div class="value">{no_activity_7d}</div>'
                     f'<div class="label">No Activity 7d+</div></div>')
        parts.append('</div>')

        # Mini timelines per deal
        for d in summaries:
            mini_svg = self._render_mini_timeline(d)
            gap_indicator = ""
            if d["has_red_gap"]:
                gap_indicator = '<span class="gap-badge red">GAP 14d+</span>'
            elif d["max_gap"] >= GAP_YELLOW_DAYS:
                gap_indicator = '<span class="gap-badge yellow">GAP 7d+</span>'

            last_str = d["last_activity_date"].strftime("%Y-%m-%d") if d["last_activity_date"] else "never"

            parts.append(f'''<div class="mini-timeline">
  <div class="deal-header">
    <div>
      <span class="deal-title">{escape_html(d["title"][:40])}</span>
      <span class="deal-meta"> - {escape_html(d["org"])}</span>
    </div>
    <div style="display:flex;gap:8px;align-items:center;">
      {gap_indicator}
      <span class="deal-stage">{escape_html(d["stage_name"])}</span>
    </div>
  </div>
  <div style="font-size:12px;color:#8b949e;margin-bottom:6px;">
    {d["activity_count"]} activities | Last: {last_str} ({d["days_since_last"]}d ago) |
    {d["value"]:,.0f} {d["currency"]}
  </div>
  <div class="timeline-container">{mini_svg}</div>
</div>''')

        return "\n".join(parts)

    def _render_mini_timeline(self, deal_data):
        activities = deal_data["activities"]
        gaps = deal_data["gaps"]
        add_date = deal_data["add_date"]

        all_dates = [a["date"] for a in activities]
        if add_date:
            all_dates.append(add_date)
        all_dates.append(TODAY)

        if not all_dates:
            return '<div style="color:#8b949e;font-size:12px;">No data</div>'

        min_date = min(all_dates)
        max_date = max(all_dates)
        total_days = max((max_date - min_date).days, 1)

        width = 700
        height = 40
        margin_left = 10
        margin_right = 10
        axis_y = 20
        track_width = width - margin_left - margin_right

        def date_to_x(d):
            frac = (d - min_date).days / total_days
            return margin_left + frac * track_width

        parts = []
        parts.append(f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">')

        # Gap highlights
        for gap in gaps:
            x1 = date_to_x(gap["start"])
            x2 = date_to_x(gap["end"])
            color = "#f4433633" if gap["severity"] == "red" else "#ff980033"
            parts.append(f'<rect x="{x1}" y="2" width="{max(x2-x1, 2)}" height="36" '
                         f'fill="{color}" rx="2"/>')

        # Axis
        parts.append(f'<line x1="{margin_left}" y1="{axis_y}" '
                      f'x2="{margin_left + track_width}" y2="{axis_y}" '
                      f'stroke="#30363d" stroke-width="1"/>')

        # Dots
        for act in activities:
            x = date_to_x(act["date"])
            color = ACTIVITY_COLORS.get(act["type"], DEFAULT_ACTIVITY_COLOR)
            parts.append(f'<circle cx="{x}" cy="{axis_y}" r="3" fill="{color}"/>')

        # Date labels
        parts.append(f'<text x="{margin_left}" y="38" font-size="8" fill="#8b949e" '
                      f'font-family="monospace">{min_date.strftime("%m/%d")}</text>')
        parts.append(f'<text x="{margin_left + track_width}" y="38" text-anchor="end" '
                      f'font-size="8" fill="#8b949e" font-family="monospace">'
                      f'{max_date.strftime("%m/%d")}</text>')

        parts.append('</svg>')
        return "\n".join(parts)


# -- GAPS REPORT --------------------------------------------------------------

def generate_gaps_report(base, token):
    """Show deals with activity gaps, sorted by worst gap."""
    tlog("Generating gaps report")
    deals = fetch_all_open_deals(base, token)

    gap_deals = []
    for deal in deals:
        deal_id = deal["id"]
        raw_activities = fetch_deal_activities(base, token, deal_id)
        activities = build_activity_list(raw_activities)
        gaps = find_activity_gaps(activities)

        if not gaps:
            continue

        max_gap = max(g["days"] for g in gaps)
        last_activity = parse_date(deal.get("last_activity_date"))

        gap_deals.append({
            "deal_id": deal_id,
            "title": deal.get("title", f"Deal #{deal_id}"),
            "org": deal.get("org_name") or "",
            "stage": STAGE_NAMES.get(deal.get("stage_id"), "Unknown"),
            "gaps": gaps,
            "max_gap": max_gap,
            "last_activity": last_activity,
            "value": deal.get("value") or 0,
            "currency": deal.get("currency", "CZK"),
        })

    gap_deals.sort(key=lambda d: d["max_gap"], reverse=True)

    # Build HTML body
    parts = []

    # Stats
    total_gaps = sum(len(d["gaps"]) for d in gap_deals)
    red_deals = sum(1 for d in gap_deals if d["max_gap"] >= GAP_RED_DAYS)
    yellow_deals = sum(1 for d in gap_deals if GAP_YELLOW_DAYS <= d["max_gap"] < GAP_RED_DAYS)

    parts.append('<div class="stats-grid">')
    parts.append(f'<div class="stat-card danger"><div class="value">{red_deals}</div>'
                 f'<div class="label">Critical (14d+)</div></div>')
    parts.append(f'<div class="stat-card warn"><div class="value">{yellow_deals}</div>'
                 f'<div class="label">Warning (7-13d)</div></div>')
    parts.append(f'<div class="stat-card"><div class="value">{total_gaps}</div>'
                 f'<div class="label">Total Gaps</div></div>')
    parts.append(f'<div class="stat-card"><div class="value">{len(gap_deals)}</div>'
                 f'<div class="label">Deals Affected</div></div>')
    parts.append('</div>')

    # Gap list
    parts.append('<div class="gap-list">')
    for d in gap_deals:
        worst = max(d["gaps"], key=lambda g: g["days"])
        severity_class = "red" if worst["severity"] == "red" else "yellow"
        last_str = d["last_activity"].strftime("%Y-%m-%d") if d["last_activity"] else "never"

        parts.append(f'''<div class="gap-item">
  <span class="gap-badge {severity_class}">{d["max_gap"]}d</span>
  <div style="flex:1;">
    <div style="font-weight:600;">{escape_html(d["title"][:40])}</div>
    <div style="font-size:12px;color:#8b949e;">
      {escape_html(d["org"])} | {escape_html(d["stage"])} |
      Last activity: {last_str} | {d["value"]:,.0f} {d["currency"]}
    </div>
  </div>
  <div style="text-align:right;font-size:12px;color:#8b949e;">
    {len(d["gaps"])} gap{"s" if len(d["gaps"]) != 1 else ""}
  </div>
</div>''')
    parts.append('</div>')

    if not gap_deals:
        parts.append('<div style="text-align:center;color:#4CAF50;padding:40px;">'
                     'No activity gaps found. Pipeline is active.</div>')

    tl = DealTimeline(base, token)
    html = tl._wrap_html(
        title="Activity Gap Report",
        body_content="\n".join(parts),
        subtitle=f"{len(gap_deals)} deals with gaps | {red_deals} critical",
    )

    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    output = STATUS_DIR / "gaps_report.html"
    output.write_text(html)
    tlog(f"Gaps report saved: {output}")
    return output, gap_deals


# -- CLI ----------------------------------------------------------------------

def main():
    env = load_env(ENV_PATH)
    base = env.get("PIPEDRIVE_BASE_URL", "").rstrip("/")
    token = env.get("PIPEDRIVE_API_TOKEN", "")

    if not base or not token:
        print("ERROR: Missing PIPEDRIVE_BASE_URL or PIPEDRIVE_API_TOKEN in .secrets/pipedrive.env")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage:")
        print("  deal_timeline.py deal <deal_id>   Single deal timeline")
        print("  deal_timeline.py all              Pipeline overview")
        print("  deal_timeline.py gaps             Activity gap report")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "deal":
        if len(sys.argv) < 3:
            print("Usage: deal_timeline.py deal <deal_id>")
            sys.exit(1)
        deal_id = sys.argv[2]
        timeline = DealTimeline(base, token)
        output = timeline.generate(deal_id)
        if output:
            print(f"Timeline generated: {output}")
            print(f"Open: file://{output}")
        else:
            print(f"Failed to generate timeline for deal {deal_id}")
            sys.exit(1)

    elif cmd == "all":
        dashboard = PipelineDashboard(base, token)
        output, summaries = dashboard.generate()
        print(f"Pipeline overview generated: {output}")
        print(f"  {len(summaries)} active deals")
        red = sum(1 for d in summaries if d["has_red_gap"])
        if red:
            print(f"  {red} deals with critical gaps (14d+)")
        print(f"Open: file://{output}")

    elif cmd == "gaps":
        output, gap_deals = generate_gaps_report(base, token)
        print(f"Gap report generated: {output}")
        if gap_deals:
            print(f"  {len(gap_deals)} deals with gaps")
            for d in gap_deals[:5]:
                print(f"    [{d['deal_id']}] {d['title'][:30]} — {d['max_gap']}d max gap")
            if len(gap_deals) > 5:
                print(f"    ... +{len(gap_deals) - 5} more (see HTML report)")
        else:
            print("  No activity gaps found.")
        print(f"Open: file://{output}")

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: deal_timeline.py [deal <id>|all|gaps]")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        LOG_FILE.parent.mkdir(exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] [FATAL] {e}\n")
            f.write(traceback.format_exc() + "\n")
        print(f"FATAL: {e}", file=sys.stderr)
        raise
