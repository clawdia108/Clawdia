#!/usr/bin/env python3
"""
Notion Sync — syncs Pipedrive deals, daily digests and analyses to Notion.

Usage:
  python3 scripts/notion_sync.py                  # full sync
  python3 scripts/notion_sync.py --deals           # only deals
  python3 scripts/notion_sync.py --digest          # create today's digest
  python3 scripts/notion_sync.py --analysis FILE   # push analysis report
"""

import json
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.paths import WORKSPACE, LOGS_DIR
from lib.secrets import load_secrets
from lib.pipedrive import pipedrive_api, pipedrive_get_all
from lib.notifications import notify_telegram

LOG_FILE = LOGS_DIR / "notion-sync.log"
SIGNALS_DIR = WORKSPACE / "knowledge" / "signals"
HEALTH_DIR = WORKSPACE / "reports" / "health"

# Notion IDs
NOTION_BASE = "https://api.notion.com/v1"
SALES_HUB_ID = "31dcacf2-0357-81ea-a6e8-f7148706ed92"
DEALS_DB_ID = "31dcacf2-0357-81de-b4d7-c51787a2c146"
DIGEST_DB_ID = "31dcacf2-0357-81aa-a88a-c7e21c92475c"
ANALYSES_DB_ID = "31dcacf2-0357-8173-a092-f0f4aeb7fb62"
COACHING_DB_ID = "31ecacf2-0357-815e-8dcb-d3974563b5db"
WEEKLY_DB_ID = "31ecacf2-0357-81d1-8703-dedaa7be49ba"

# Page IDs for content pages
NOTION_PAGES = {
    "playbook": "31ecacf2-0357-81f4-9351-ed76da5e00ef",
    "coaching": "31ecacf2-0357-8136-b1fd-cc17cfa7162b",
    "weekly_reports": "31ecacf2-0357-8171-bef1-c558571e4488",
    "dashboard": "31ecacf2-0357-8118-8d88-e3a3de28735d",
    "meeting_prep": "31ecacf2-0357-81bf-b997-ccdccac20bc9",
    "knowledge_base": "31ecacf2-0357-81d3-8920-fe13afc92a09",
}

STAGE_MAP = {
    0: "Lead",
    1: "Lead",
    2: "Contacted",
    3: "Demo",
    4: "Proposal",
    5: "Negotiation",
}


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def notion_api(token, method, path, data=None):
    """Call Notion API."""
    url = f"{NOTION_BASE}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Notion-Version", "2022-06-28")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        error_body = e.read().decode()
        log(f"Notion API error {method} {path}: {e.code} {error_body[:200]}")
        return None
    except Exception as e:
        log(f"Notion API error {method} {path}: {e}")
        return None


def get_existing_deals(notion_token):
    """Get map of Pipedrive ID → Notion page ID for existing deals."""
    mapping = {}
    has_more = True
    start_cursor = None
    while has_more:
        payload = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor
        result = notion_api(notion_token, "POST",
                            f"/databases/{DEALS_DB_ID}/query", payload)
        if not result:
            break
        for page in result.get("results", []):
            props = page.get("properties", {})
            pd_id = props.get("Pipedrive ID", {}).get("number")
            if pd_id:
                mapping[pd_id] = page["id"]
        has_more = result.get("has_more", False)
        start_cursor = result.get("next_cursor")
    return mapping


def deal_to_priority(deal):
    """Quick priority classification."""
    stage = deal.get("stage_order_nr", 0)
    value = deal.get("value", 0)
    last_date = deal.get("last_activity_date", "")
    days_silent = 999
    if last_date:
        try:
            last_dt = datetime.strptime(last_date, "%Y-%m-%d")
            days_silent = (datetime.now() - last_dt).days
        except ValueError:
            pass

    if stage >= 3 and days_silent <= 7 and value > 0:
        return "🔥 HOT"
    elif stage >= 2 and days_silent <= 14:
        return "🟡 WARM"
    elif days_silent <= 21:
        return "🟢 NURTURE"
    return "❄️ COLD"


def get_deal_signals_text(deal_id):
    """Load cached signals summary."""
    fpath = SIGNALS_DIR / f"deal_{deal_id}.json"
    if not fpath.exists():
        return ""
    try:
        data = json.loads(fpath.read_text())
        signals = data.get("signals", [])
        if not signals:
            return ""
        parts = []
        for s in signals[:3]:
            parts.append(f"{s.get('type', '?')}: {s.get('relevance', '')[:60]}")
        return " | ".join(parts)
    except Exception:
        return ""


def get_deal_health(deal_id):
    """Load health score if available."""
    fpath = HEALTH_DIR / f"deal_{deal_id}.json"
    if not fpath.exists():
        # Try consolidated health report
        consolidated = WORKSPACE / "reports" / "health" / "latest.json"
        if consolidated.exists():
            try:
                data = json.loads(consolidated.read_text())
                for d in data.get("deals", []):
                    if d.get("id") == deal_id:
                        return d.get("health_score", 0)
            except Exception:
                pass
        return 0
    try:
        data = json.loads(fpath.read_text())
        return data.get("health_score", 0)
    except Exception:
        return 0


def truncate(text, max_len=1990):
    """Notion rich_text limit (2000 chars max, with safety margin)."""
    if not text:
        return ""
    return text[:max_len]


def build_deal_properties(deal):
    """Build Notion page properties from Pipedrive deal."""
    stage_nr = deal.get("stage_order_nr", 0)
    stage_name = STAGE_MAP.get(stage_nr, "Lead")
    priority = deal_to_priority(deal)
    org = deal.get("org_name", "") or ""
    title = deal.get("title", "") or org or f"Deal #{deal['id']}"
    value = deal.get("value", 0) or 0
    person_name = deal.get("person_name", "") or ""
    next_date = deal.get("next_activity_date", "")
    last_date = deal.get("last_activity_date", "")
    signals = get_deal_signals_text(deal["id"])
    health = get_deal_health(deal["id"])

    days_silent = 0
    if last_date:
        try:
            days_silent = (datetime.now() - datetime.strptime(last_date, "%Y-%m-%d")).days
        except ValueError:
            pass

    next_step = ""
    if next_date:
        next_step = f"Next activity: {next_date}"
    elif days_silent > 14:
        next_step = f"⚠️ No next step — {days_silent}d silent"

    props = {
        "Deal": {"title": [{"text": {"content": title[:100]}}]},
        "Company": {"rich_text": [{"text": {"content": org[:100]}}]},
        "Value (CZK)": {"number": value},
        "Stage": {"select": {"name": stage_name}},
        "Health Score": {"number": health},
        "Priority": {"select": {"name": priority}},
        "Contact": {"rich_text": [{"text": {"content": person_name[:100]}}]},
        "Days Silent": {"number": days_silent},
        "Next Step": {"rich_text": [{"text": {"content": next_step[:200]}}]},
        "Signals": {"rich_text": [{"text": {"content": truncate(signals)}}]},
        "Last Updated": {"date": {"start": datetime.now().strftime("%Y-%m-%d")}},
        "Pipedrive ID": {"number": deal["id"]},
    }

    # Add email/phone if available
    person_id = deal.get("person_id")
    if isinstance(person_id, dict):
        person_id = person_id.get("value")
    email = deal.get("person_email", "") or ""
    if isinstance(email, list) and email:
        email = email[0].get("value", "") if isinstance(email[0], dict) else str(email[0])
    if email:
        props["Email"] = {"email": email}

    return props


def sync_deals(notion_token, pipedrive_token):
    """Sync all open deals from Pipedrive to Notion."""
    log("Fetching open deals from Pipedrive...")
    deals = pipedrive_get_all(pipedrive_token, "/deals", {"status": "open"})
    log(f"  {len(deals)} open deals")

    log("Loading existing Notion deals...")
    existing = get_existing_deals(notion_token)
    log(f"  {len(existing)} already in Notion")

    created = 0
    updated = 0
    errors = 0

    for deal in deals:
        deal_id = deal["id"]
        props = build_deal_properties(deal)

        if deal_id in existing:
            # Update existing
            page_id = existing[deal_id]
            result = notion_api(notion_token, "PATCH",
                                f"/pages/{page_id}", {"properties": props})
            if result:
                updated += 1
            else:
                errors += 1
        else:
            # Create new
            result = notion_api(notion_token, "POST", "/pages", {
                "parent": {"database_id": DEALS_DB_ID},
                "properties": props,
            })
            if result:
                created += 1
            else:
                errors += 1

    log(f"Deals sync: {created} created, {updated} updated, {errors} errors")
    return created, updated, errors


def create_daily_digest(notion_token, pipedrive_token):
    """Create today's daily digest entry."""
    today = datetime.now().strftime("%Y-%m-%d")
    log(f"Creating daily digest for {today}...")

    # Get pipeline stats
    deals = pipedrive_get_all(pipedrive_token, "/deals", {"status": "open"})
    total_value = sum(d.get("value", 0) or 0 for d in deals)

    hot = 0
    warm = 0
    actions = []
    highlights = []
    risks = []

    for d in deals:
        priority = deal_to_priority(d)
        if "HOT" in priority:
            hot += 1
        elif "WARM" in priority:
            warm += 1

        # Check for actions needed today
        next_date = d.get("next_activity_date", "")
        if next_date == today:
            org = d.get("org_name", "") or d.get("title", "")
            actions.append(f"Call {org}")

        # Check for overdue
        if next_date and next_date < today:
            org = d.get("org_name", "") or d.get("title", "")
            risks.append(f"Overdue: {org}")

        # Recent activity = highlight
        last_date = d.get("last_activity_date", "")
        if last_date == today or last_date == (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d"):
            org = d.get("org_name", "") or d.get("title", "")
            highlights.append(f"Active: {org}")

    # Load any analysis reports from today
    today_reports = []
    report_dirs = [
        WORKSPACE / "reports" / "call-lists",
        WORKSPACE / "reports" / "health",
    ]
    for rd in report_dirs:
        if rd.exists():
            for f in rd.iterdir():
                if today in f.name:
                    today_reports.append(f.name)

    if today_reports:
        highlights.append(f"Reports: {', '.join(today_reports[:3])}")

    props = {
        "Date": {"title": [{"text": {"content": f"{today} Morning Briefing"}}]},
        "Type": {"select": {"name": "Morning Briefing"}},
        "Hot Deals": {"number": hot},
        "Warm Deals": {"number": warm},
        "Total Pipeline (CZK)": {"number": total_value},
        "Actions Today": {"rich_text": [{"text": {"content": truncate(" | ".join(actions[:10]) or "No scheduled actions")}}]},
        "Highlights": {"rich_text": [{"text": {"content": truncate(" | ".join(highlights[:5]) or "—")}}]},
        "Risks": {"rich_text": [{"text": {"content": truncate(" | ".join(risks[:5]) or "—")}}]},
    }

    result = notion_api(notion_token, "POST", "/pages", {
        "parent": {"database_id": DIGEST_DB_ID},
        "properties": props,
    })

    if result:
        log(f"Daily digest created: {hot} HOT, {warm} WARM, pipeline {total_value:,.0f} CZK")
    else:
        log("Failed to create daily digest")

    return result


def push_analysis(notion_token, title, category, findings, action_items="", deals_affected=0):
    """Push an analysis report to Notion."""
    today = datetime.now().strftime("%Y-%m-%d")

    props = {
        "Title": {"title": [{"text": {"content": title[:100]}}]},
        "Category": {"select": {"name": category}},
        "Date": {"date": {"start": today}},
        "Key Findings": {"rich_text": [{"text": {"content": truncate(findings)}}]},
        "Action Items": {"rich_text": [{"text": {"content": truncate(action_items)}}]},
        "Deals Affected": {"number": deals_affected},
    }

    result = notion_api(notion_token, "POST", "/pages", {
        "parent": {"database_id": ANALYSES_DB_ID},
        "properties": props,
    })

    if result:
        log(f"Analysis pushed: {title}")
    return result


def push_coaching_report(notion_token, call_name, deal_name, score, talk_ratio,
                         spin_score, feedback, improvement_area="Overall"):
    """Push coaching report to Notion Coaching Reports DB."""
    today = datetime.now().strftime("%Y-%m-%d")
    props = {
        "Call": {"title": [{"text": {"content": call_name[:100]}}]},
        "Date": {"date": {"start": today}},
        "Deal": {"rich_text": [{"text": {"content": (deal_name or "")[:100]}}]},
        "Score": {"number": score or 0},
        "Talk Ratio": {"number": round(talk_ratio / 100, 2) if talk_ratio else 0},
        "SPIN Score": {"number": spin_score or 0},
        "Key Feedback": {"rich_text": [{"text": {"content": truncate(feedback or "")}}]},
        "Improvement Area": {"select": {"name": improvement_area}},
        "Status": {"select": {"name": "New"}},
    }
    result = notion_api(notion_token, "POST", "/pages", {
        "parent": {"database_id": COACHING_DB_ID},
        "properties": props,
    })
    if result:
        log(f"Coaching report pushed: {call_name} (score: {score})")
    return result


def push_weekly_summary(notion_token, week_label, pipeline_value, hot, warm,
                        won, lost, calls, emails, win_rate, health,
                        top_priority="", key_insight=""):
    """Push weekly summary to Notion Weekly Summaries DB."""
    props = {
        "Week": {"title": [{"text": {"content": week_label[:100]}}]},
        "Pipeline Value": {"number": pipeline_value or 0},
        "Hot Deals": {"number": hot or 0},
        "Warm Deals": {"number": warm or 0},
        "Deals Won": {"number": won or 0},
        "Deals Lost": {"number": lost or 0},
        "Calls Made": {"number": calls or 0},
        "Emails Sent": {"number": emails or 0},
        "Win Rate": {"number": round(win_rate / 100, 2) if win_rate else 0},
        "Health Score": {"number": health or 0},
        "Top Priority": {"rich_text": [{"text": {"content": truncate(top_priority)}}]},
        "Key Insight": {"rich_text": [{"text": {"content": truncate(key_insight)}}]},
    }
    result = notion_api(notion_token, "POST", "/pages", {
        "parent": {"database_id": WEEKLY_DB_ID},
        "properties": props,
    })
    if result:
        log(f"Weekly summary pushed: {week_label}")
    return result


def push_analysis_from_file(notion_token, filepath):
    """Push an analysis from a markdown file."""
    fpath = Path(filepath)
    if not fpath.exists():
        log(f"File not found: {filepath}")
        return None

    content = fpath.read_text()
    title = fpath.stem.replace("_", " ").replace("-", " ").title()

    # Detect category from filename/path
    name_lower = fpath.name.lower()
    if "health" in name_lower:
        category = "Deal Health"
    elif "signal" in name_lower or "intel" in name_lower:
        category = "Signal Intelligence"
    elif "call" in name_lower or "coach" in name_lower:
        category = "Call Coaching"
    elif "weekly" in name_lower:
        category = "Weekly Intel"
    elif "pipeline" in name_lower:
        category = "Pipeline Analysis"
    elif "compet" in name_lower:
        category = "Competitive Intel"
    else:
        category = "Pipeline Analysis"

    return push_analysis(notion_token, title, category, content[:2000])


def main():
    secrets = load_secrets()
    notion_token = secrets.get("NOTION_TOKEN")
    if not notion_token:
        log("ERROR: NOTION_TOKEN not found in secrets")
        return 1
    pipedrive_token = secrets.get("PIPEDRIVE_API_TOKEN") or secrets.get("PIPEDRIVE_TOKEN")
    if not pipedrive_token:
        log("No Pipedrive token found in secrets")
        return 1

    mode = "full"
    analysis_file = None
    for i, arg in enumerate(sys.argv):
        if arg == "--deals":
            mode = "deals"
        elif arg == "--digest":
            mode = "digest"
        elif arg == "--analysis" and i + 1 < len(sys.argv):
            mode = "analysis"
            analysis_file = sys.argv[i + 1]

    created, updated, errors = 0, 0, 0

    if mode == "deals":
        created, updated, errors = sync_deals(notion_token, pipedrive_token)
    elif mode == "digest":
        create_daily_digest(notion_token, pipedrive_token)
    elif mode == "analysis":
        push_analysis_from_file(notion_token, analysis_file)
    else:
        # Full sync
        created, updated, errors = sync_deals(notion_token, pipedrive_token)
        create_daily_digest(notion_token, pipedrive_token)

        # Push any existing reports
        report_files = [
            WORKSPACE / "pipedrive" / "PIPELINE_STATUS.md",
            WORKSPACE / "pipedrive" / "DEAL_SCORING.md",
            WORKSPACE / "intel" / "DAILY-INTEL.md",
        ]
        for rf in report_files:
            if rf.exists():
                push_analysis_from_file(notion_token, str(rf))

    notify_telegram(f"Notion Sync: {created} new, {updated} updated, {errors} errors")
    return 0


if __name__ == "__main__":
    exit(main())
