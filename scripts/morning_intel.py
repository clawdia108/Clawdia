#!/usr/bin/env python3
"""
9:00 AM Intel Email — Daily deal intelligence for Josef
========================================================
Precise daily intel: deals to contact, key context per deal,
cold call count, SPIN questions, competitor notes.
Sends via Telegram + saves to knowledge/DAILY_INTEL.md

This runs at 9:00 AM sharp — Josef should be ready to call.

Usage:
    python3 scripts/morning_intel.py             # Generate intel
    python3 scripts/morning_intel.py --send      # Generate + Telegram
"""

import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, date, timedelta

from lib.paths import WORKSPACE
from lib.secrets import load_secrets
from lib.logger import make_logger
from lib.claude_api import claude_generate
from lib.notifications import notify_telegram

OUTPUT = WORKSPACE / "knowledge" / "DAILY_INTEL.md"

log = make_logger("morning-intel")


def api_get(base, token, path, params=None):
    params = dict(params or {})
    params["api_token"] = token
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        log(f"API error {path}: {e}", "ERROR")
        return None


def paged_get(base, token, path, params=None):
    out = []
    start = 0
    while True:
        p = dict(params or {})
        p.update({"start": start, "limit": 500})
        j = api_get(base, token, path, p)
        if not j or not j.get("success"):
            break
        out.extend(j.get("data") or [])
        pag = (j.get("additional_data") or {}).get("pagination") or {}
        if not pag.get("more_items_in_collection"):
            break
        start = pag.get("next_start", start + 500)
    return out


def days_since(date_str):
    if not date_str:
        return 999
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return (date.today() - d).days
    except (ValueError, TypeError):
        return 999


def extract_org(deal):
    org = deal.get("org_id") or {}
    return org.get("name", "Neznámá firma") if isinstance(org, dict) else "Neznámá firma"


def extract_contact(deal):
    person = deal.get("person_id") or {}
    if isinstance(person, dict):
        name = person.get("name", "")
        emails = person.get("email", [])
        phones = person.get("phone", [])
        email = ""
        phone = ""
        if isinstance(emails, list):
            for e in emails:
                if isinstance(e, dict) and e.get("value"):
                    email = e["value"]
                    break
        if isinstance(phones, list):
            for p in phones:
                if isinstance(p, dict) and p.get("value"):
                    phone = p["value"]
                    break
        return {"name": name, "email": email, "phone": phone}
    return {"name": "", "email": "", "phone": ""}


def get_today_activities(base, token):
    """Get activities scheduled for today."""
    today = date.today().isoformat()
    params = {
        "start_date": today,
        "end_date": today,
        "done": 0,
    }
    return paged_get(base, token, "/api/v1/activities", params)


def get_week_activities(base, token):
    """Get activities for this week."""
    today = date.today()
    end = today + timedelta(days=5)
    params = {
        "start_date": today.isoformat(),
        "end_date": end.isoformat(),
        "done": 0,
    }
    return paged_get(base, token, "/api/v1/activities", params)


def get_recent_won_lost(base, token, days=7):
    """Get recently won/lost deals for context."""
    won = paged_get(base, token, "/api/v1/deals", {
        "status": "won",
        "sort": "won_time DESC",
        "limit": 5,
    })
    lost = paged_get(base, token, "/api/v1/deals", {
        "status": "lost",
        "sort": "lost_time DESC",
        "limit": 5,
    })
    return won[:3], lost[:3]


def generate_deal_intel(deal, api_key, base, token):
    """Generate AI-powered intel for a specific deal."""
    org = extract_org(deal)
    contact = extract_contact(deal)
    value = deal.get("value") or 0
    stage_id = deal.get("stage_id", 0)
    days_stale = days_since(deal.get("last_activity_date"))
    title = deal.get("title", "")

    stage_names = {
        7: "Kvalifikován", 8: "Demo", 28: "V jednání",
        9: "Nabídka", 10: "Vyjednávání", 12: "Pilot",
        29: "Smlouva", 11: "Faktura",
    }
    stage = stage_names.get(stage_id, f"Stage {stage_id}")

    # Get recent notes for context
    notes = paged_get(base, token, f"/api/v1/deals/{deal.get('id')}/notes", {
        "sort": "add_time DESC", "limit": 2,
    })
    note_context = ""
    for n in notes[:2]:
        content = (n.get("content") or "").replace("\n", " ")[:150]
        if content:
            note_context += f"\nPoznámka: {content}"

    # Generate personalized insight with Claude
    insight = ""
    if api_key:
        system = "Jsi sales advisor. Napiš 1 větu — co je klíčové pro tento deal DNES. Česky, krátce, akčně."
        prompt = f"Deal: {title}\nFirma: {org}\nKontakt: {contact['name']}\nStage: {stage}\nHodnota: {value} CZK\nDní bez aktivity: {days_stale}{note_context}"
        insight = claude_generate(api_key, system, prompt, max_tokens=100)

    return {
        "org": org,
        "contact": contact,
        "value": value,
        "stage": stage,
        "stage_id": stage_id,
        "days_stale": days_stale,
        "title": title,
        "insight": insight or "",
        "deal_id": deal.get("id"),
    }


def main(send_telegram=False):
    secrets = load_secrets()
    base = secrets.get("PIPEDRIVE_BASE_URL", "").rstrip("/")
    token = secrets.get("PIPEDRIVE_API_TOKEN", "")
    api_key = secrets.get("ANTHROPIC_API_KEY", "")

    if not base or not token:
        log("Missing Pipedrive credentials", "ERROR")
        print("ERROR: Missing Pipedrive credentials")
        return 1

    today = date.today()
    now = datetime.now()
    is_weekend = today.weekday() >= 5

    if is_weekend:
        print("Weekend — no intel generated")
        return 0

    log("Generating 9:00 AM intel...")

    # Pull data
    print("Pulling Pipedrive data...")
    all_deals = paged_get(base, token, "/api/v1/deals", {"status": "open"})
    today_activities = get_today_activities(base, token)
    week_activities = get_week_activities(base, token)
    won_recent, lost_recent = get_recent_won_lost(base, token)

    # Deals with activity today
    today_deal_ids = set()
    for act in today_activities:
        if act.get("deal_id"):
            today_deal_ids.add(act["deal_id"])

    # Classify deals
    today_deals = [d for d in all_deals if d.get("id") in today_deal_ids]
    stale_deals = [d for d in all_deals if days_since(d.get("last_activity_date")) > 14]
    hot_deals = [d for d in all_deals if d.get("stage_id") in (9, 10, 12, 29)]
    cold_calls = [d for d in all_deals if d.get("stage_id") == 7 and days_since(d.get("last_activity_date")) > 3]

    # Generate intel for top deals
    intel_deals = []

    # Priority 1: Today's scheduled deals
    for deal in today_deals[:5]:
        intel = generate_deal_intel(deal, api_key, base, token)
        intel["priority"] = "📞 DNES"
        intel_deals.append(intel)
        time.sleep(0.3)  # Rate limit

    # Priority 2: Hot deals not already included
    today_ids = {d.get("id") for d in today_deals}
    for deal in hot_deals[:3]:
        if deal.get("id") not in today_ids:
            intel = generate_deal_intel(deal, api_key, base, token)
            intel["priority"] = "🔥 HOT"
            intel_deals.append(intel)
            time.sleep(0.3)

    # Priority 3: Stale deals needing revival
    for deal in stale_deals[:3]:
        if deal.get("id") not in today_ids:
            intel = generate_deal_intel(deal, api_key, base, token)
            intel["priority"] = "⚠️ STALE"
            intel_deals.append(intel)
            time.sleep(0.3)

    # Build output
    sections = []
    sections.append(f"# 🎯 Daily Intel — {today.isoformat()}")
    sections.append(f"*9:00 AM briefing | {now.strftime('%H:%M')}*\n")

    # Quick numbers
    sections.append("## Čísla dne")
    sections.append(f"| Metrika | Počet |")
    sections.append(f"|---------|-------|")
    sections.append(f"| 📞 Hovory dnes | **{len(today_deals)}** |")
    sections.append(f"| 🔥 Hot deals | **{len(hot_deals)}** |")
    sections.append(f"| ⚠️ Stale deals (>14d) | **{len(stale_deals)}** |")
    sections.append(f"| ❄️ Cold calls | **{len(cold_calls)}** |")
    sections.append(f"| 💰 Open deals celkem | **{len(all_deals)}** |")
    sections.append(f"| 📅 Aktivity tento týden | **{len(week_activities)}** |")

    # Pipeline value
    total_value = sum(d.get("value") or 0 for d in all_deals)
    sections.append(f"| 💎 Pipeline value | **{total_value:,.0f} CZK** |")

    # Recent wins/losses
    if won_recent:
        sections.append(f"\n### ✅ Nedávno vyhrané")
        for d in won_recent:
            org = extract_org(d)
            val = d.get("value") or 0
            sections.append(f"- {org} — {val:,.0f} CZK")

    if lost_recent:
        sections.append(f"\n### ❌ Nedávno ztracené")
        for d in lost_recent:
            org = extract_org(d)
            sections.append(f"- {org}")

    # Deal intel
    sections.append("\n## 📋 Deal Intel")
    for intel in intel_deals:
        sections.append(f"\n### {intel['priority']} {intel['org']}")
        sections.append(f"**Kontakt:** {intel['contact']['name']} | **Tel:** {intel['contact']['phone'] or '📵'}")
        sections.append(f"**Stage:** {intel['stage']} | **Hodnota:** {intel['value']:,.0f} CZK")
        sections.append(f"**Dní bez aktivity:** {intel['days_stale']}")
        if intel.get("insight"):
            sections.append(f"**💡 Insight:** {intel['insight']}")
        sections.append("")

    # Cold call list
    if cold_calls:
        sections.append("\n## ❄️ Cold Call List")
        sections.append("| # | Firma | Kontakt | Telefon |")
        sections.append("|---|-------|---------|---------|")
        for i, d in enumerate(cold_calls[:10], 1):
            org = extract_org(d)
            contact = extract_contact(d)
            sections.append(f"| {i} | {org} | {contact['name']} | {contact['phone'] or '📵'} |")

    sections.append(f"\n---\n*Daily Intel v1 | {now.strftime('%Y-%m-%d %H:%M')}*")

    content = "\n".join(sections)

    # Save
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content)
    log(f"Intel saved: {len(content)}B, {len(intel_deals)} deals analyzed")
    print(f"Intel saved to {OUTPUT}")

    # Send email via Resend
    if send_telegram:
        resend_key = secrets.get("RESEND_API_KEY")
        recipient = secrets.get("DIGEST_EMAIL", "clawdia108@gmail.com")
        if resend_key:
            try:
                import urllib.request
                html_content = content.replace("\n", "<br>").replace("**", "<b>").replace("##", "<h3>").replace("# ", "<h2>")
                email_payload = json.dumps({
                    "from": f"Clawdia <{secrets.get('RESEND_FROM_EMAIL', 'onboarding@resend.dev')}>",
                    "to": [recipient],
                    "subject": f"🎯 Daily Intel — {today.isoformat()}",
                    "html": f"<div style='font-family:sans-serif;max-width:600px;'>{html_content}</div>",
                }).encode()
                req = urllib.request.Request(
                    "https://api.resend.com/emails",
                    data=email_payload,
                    headers={"Authorization": f"Bearer {resend_key}", "Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    log("Resend email sent")
            except Exception as e:
                log(f"Resend failed: {e}", "WARN")

    # Telegram
    if send_telegram:
        tg = f"🎯 *Daily Intel — {today.isoformat()}*\n\n"
        tg += f"📞 {len(today_deals)} hovorů dnes\n"
        tg += f"🔥 {len(hot_deals)} hot dealů\n"
        tg += f"❄️ {len(cold_calls)} cold callů\n"
        tg += f"💰 Pipeline: {total_value:,.0f} CZK\n\n"

        if intel_deals:
            tg += "*Hlavní dealy:*\n"
            for intel in intel_deals[:5]:
                tg += f"• {intel['org']} [{intel['priority']}]\n"

        tg += f"\n⏰ Go time. Start calling."
        notify_telegram(tg)
        log("Telegram notification sent")

    return 0


if __name__ == "__main__":
    send = "--send" in sys.argv
    exit(main(send_telegram=send))
