"""Notion API helper — push analyses and updates to Notion Sales Hub."""

import json
import urllib.parse
import urllib.request
from datetime import datetime

NOTION_BASE = "https://api.notion.com/v1"
DEALS_DB_ID = "31dcacf2-0357-81de-b4d7-c51787a2c146"
DIGEST_DB_ID = "31dcacf2-0357-81aa-a88a-c7e21c92475c"
ANALYSES_DB_ID = "31dcacf2-0357-8173-a092-f0f4aeb7fb62"


def _notion_api(token, method, path, data=None):
    """Internal Notion API call."""
    url = f"{NOTION_BASE}{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Notion-Version", "2022-06-28")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception:
        return None


def push_analysis(token, title, category, findings, action_items="", deals_affected=0):
    """Push an analysis report to Notion Analyses & Intel database.

    category: "Deal Health", "Signal Intelligence", "Call Coaching",
              "Weekly Intel", "Pipeline Analysis", "Competitive Intel"
    """
    if not token:
        return None

    today = datetime.now().strftime("%Y-%m-%d")
    props = {
        "Title": {"title": [{"text": {"content": title[:100]}}]},
        "Category": {"select": {"name": category}},
        "Date": {"date": {"start": today}},
        "Key Findings": {"rich_text": [{"text": {"content": findings[:1990]}}]},
        "Action Items": {"rich_text": [{"text": {"content": (action_items or "")[:1990]}}]},
        "Deals Affected": {"number": deals_affected},
    }
    return _notion_api(token, "POST", "/pages", {
        "parent": {"database_id": ANALYSES_DB_ID},
        "properties": props,
    })


def push_digest(token, title, digest_type, hot=0, warm=0, total_value=0,
                actions="", highlights="", risks=""):
    """Push a daily digest entry to Notion Daily Digest database.

    digest_type: "Morning Briefing", "Evening Summary", "Weekly Report", "Alert"
    """
    if not token:
        return None

    props = {
        "Date": {"title": [{"text": {"content": title[:100]}}]},
        "Type": {"select": {"name": digest_type}},
        "Hot Deals": {"number": hot},
        "Warm Deals": {"number": warm},
        "Total Pipeline (CZK)": {"number": total_value},
        "Actions Today": {"rich_text": [{"text": {"content": (actions or "—")[:1990]}}]},
        "Highlights": {"rich_text": [{"text": {"content": (highlights or "—")[:1990]}}]},
        "Risks": {"rich_text": [{"text": {"content": (risks or "—")[:1990]}}]},
    }
    return _notion_api(token, "POST", "/pages", {
        "parent": {"database_id": DIGEST_DB_ID},
        "properties": props,
    })
