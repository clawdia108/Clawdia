#!/usr/bin/env python3
"""
Morning Sales Prep — 7:00 AM daily briefing for Josef
======================================================
Pulls real data from Pipedrive. Generates actionable call list with:
- Who to call (contact + phone)
- What to discuss (deal context + last interaction)
- SPIN prep per deal stage
- Email draft suggestions
- Pomodoro time blocks (ADHD-optimized)

Sends summary via Telegram, saves full prep to knowledge/MORNING_PREP.md

Usage:
    python3 scripts/morning_sales_prep.py          # Generate today's prep
    python3 scripts/morning_sales_prep.py --send    # Generate + send via Telegram
"""

import json
import random
import sys
import urllib.parse
import urllib.request
from datetime import datetime, date, timedelta

from lib.paths import WORKSPACE
from lib.secrets import load_secrets
from lib.logger import make_logger
from lib.notifications import notify_telegram

OUTPUT = WORKSPACE / "knowledge" / "MORNING_PREP.md"
CALL_LIST = WORKSPACE / "knowledge" / "CALL_LIST.md"

log = make_logger("morning-prep")

CZECH_DAYS = {
    0: "Pondělí", 1: "Úterý", 2: "Středa",
    3: "Čtvrtek", 4: "Pátek", 5: "Sobota", 6: "Neděle",
}

# SPIN questions in Czech, by deal stage
SPIN_CZ = {
    "discovery": {
        "situation": [
            "Jak aktuálně měříte engagement zaměstnanců?",
            "Jaké nástroje na zpětnou vazbu používáte?",
            "Kolik zaměstnanců máte a jak rychle rostete?",
        ],
        "problem": [
            "Co vás nejvíc trápí u fluktuace?",
            "Dostáváte od lidí upřímnou zpětnou vazbu?",
            "Vidíte problémy včas, nebo až když je pozdě?",
        ],
        "implication": [
            "Co vás stojí odchod jednoho seniora?",
            "Jak nízký engagement ovlivňuje produktivitu týmu?",
        ],
        "need_payoff": [
            "Co by pro vás znamenalo vědět 3 měsíce předem, kdo chce odejít?",
            "Jak by se změnila práce HR, kdyby měli data v reálném čase?",
        ],
    },
    "demo": {
        "situation": [
            "Co přesně vás zaujalo a chcete dnes vidět?",
            "Kdo další ve firmě bude rozhodovat?",
        ],
        "problem": [
            "Co vás přivedlo k tomu hledat řešení právě teď?",
            "Co nefunguje na současném přístupu?",
        ],
        "implication": [
            "Bez lepších dat — kde vidíte tým za rok?",
            "Kolik hodin týdně HR tráví manuálním zpracováním?",
        ],
        "need_payoff": [
            "Echo Pulse spustíte za 2 dny — jak rychle potřebujete výsledky?",
            "Co by znamenalo mít benchmarky vůči konkurenci v oboru?",
        ],
    },
    "closing": {
        "situation": [
            "Viděli už všichni rozhodovači náš návrh?",
            "Je něco v nabídce nejasné?",
        ],
        "problem": [
            "Jsou nějaké obavy, které brání rozhodnutí?",
            "Je rozpočet nebo timing problém?",
        ],
        "implication": [
            "Každý měsíc bez dat = další slepá místa. Co to stojí?",
            "Jak to ovlivní vaše Q2 cíle, když to odložíte?",
        ],
        "need_payoff": [
            "S 2-týdenním pilotem máte data pro vedení — pomůže to?",
            "Začneme tento měsíc = první výsledky do Q2 review.",
        ],
    },
}

# Stage ID → template mapping
STAGE_TEMPLATES = {
    7: "discovery",    # Interested/Qualified
    8: "demo",         # Demo Scheduled
    28: "discovery",   # Ongoing Discussion
    9: "closing",      # Proposal made
    10: "closing",     # Negotiation
    12: "closing",     # Pilot
    29: "closing",     # Contract Sent
}



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


def get_open_deals(base, token):
    """Get all open deals with activities."""
    deals = paged_get(base, token, "/api/v1/deals", {
        "status": "open",
        "sort": "next_activity_date ASC",
    })
    return deals


def get_deal_activities(base, token, deal_id):
    """Get recent activities for a deal."""
    return paged_get(base, token, f"/api/v1/deals/{deal_id}/activities", {
        "sort": "due_date DESC",
        "limit": 5,
    })


def get_deal_notes(base, token, deal_id):
    """Get notes for a deal."""
    return paged_get(base, token, f"/api/v1/deals/{deal_id}/notes", {
        "sort": "add_time DESC",
        "limit": 3,
    })


def days_since(date_str):
    if not date_str:
        return 999
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return (date.today() - d).days
    except (ValueError, TypeError):
        return 999


def extract_contact(deal):
    """Extract contact name, phone, email from deal."""
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


def extract_org(deal):
    """Extract org name from deal."""
    org = deal.get("org_id") or {}
    if isinstance(org, dict):
        return org.get("name", "Neznámá firma")
    return "Neznámá firma"


def classify_deal_priority(deal):
    """Classify deal into priority tiers."""
    stage_id = deal.get("stage_id", 0)
    value = deal.get("value") or 0
    last_act = deal.get("last_activity_date")
    next_act = deal.get("next_activity_date")
    days_stale = days_since(last_act)

    score = 0

    # Higher stage = higher priority
    stage_order = {7: 1, 8: 3, 28: 2, 9: 4, 10: 5, 12: 4, 29: 5, 11: 5}
    score += stage_order.get(stage_id, 0) * 10

    # Value bonus
    if value >= 50000:
        score += 20
    elif value >= 20000:
        score += 10
    elif value >= 5000:
        score += 5

    # Stale penalty / freshness bonus
    if days_stale <= 3:
        score += 15
    elif days_stale <= 7:
        score += 5
    elif days_stale > 14:
        score -= 5  # Still needs attention but lower priority

    # Has activity today
    if next_act == date.today().isoformat():
        score += 30  # TOP priority — scheduled for today

    # Has activity this week
    elif next_act:
        try:
            next_date = datetime.strptime(next_act[:10], "%Y-%m-%d").date()
            if next_date <= date.today() + timedelta(days=2):
                score += 20
        except ValueError:
            pass

    return score


def get_spin_template(stage_id):
    return STAGE_TEMPLATES.get(stage_id, "discovery")


def format_deal_prep(deal, rank, base, token):
    """Format a single deal for the morning prep."""
    org = extract_org(deal)
    contact = extract_contact(deal)
    stage_id = deal.get("stage_id", 0)
    value = deal.get("value") or 0
    currency = deal.get("currency", "CZK")
    last_act = deal.get("last_activity_date", "")
    next_act = deal.get("next_activity_date", "")
    days_stale = days_since(last_act)

    # Stage name
    stage_names = {
        7: "Kvalifikován", 8: "Demo naplánováno", 28: "V jednání",
        9: "Nabídka odeslána", 10: "Vyjednávání", 12: "Pilot",
        29: "Smlouva odeslána", 11: "Faktura",
    }
    stage = stage_names.get(stage_id, f"Stage {stage_id}")

    # SPIN template
    template_key = get_spin_template(stage_id)
    spin = SPIN_CZ.get(template_key, SPIN_CZ["discovery"])

    lines = []
    lines.append(f"### {rank}. {org}")
    lines.append(f"**Kontakt:** {contact['name']}")
    if contact['phone']:
        lines.append(f"**Telefon:** {contact['phone']}")
    if contact['email']:
        lines.append(f"**Email:** {contact['email']}")
    lines.append(f"**Stage:** {stage} | **Hodnota:** {value:,.0f} {currency}")
    lines.append(f"**Poslední aktivita:** {last_act or 'nikdy'} ({days_stale} dní)")
    if next_act:
        lines.append(f"**Další aktivita:** {next_act}")

    # What to do
    lines.append("")
    if next_act == date.today().isoformat():
        lines.append("**Co udělat:** 📞 Máš naplánovaný hovor/schůzku DNES")
    elif days_stale > 14:
        lines.append("**Co udělat:** ⚠️ Stale deal — pošli follow-up email nebo zavolej")
    elif days_stale > 7:
        lines.append("**Co udělat:** 📧 Poslat follow-up email")
    elif template_key == "demo":
        lines.append("**Co udělat:** 📋 Připravit se na demo")
    elif template_key == "closing":
        lines.append("**Co udělat:** 🎯 Push to close — domluvit další kroky")
    else:
        lines.append("**Co udělat:** 📞 Zavolat a zjistit stav")

    # SPIN otázky (randomized, not always the same)
    lines.append("")
    lines.append("**SPIN otázky:**")
    if template_key == "discovery":
        lines.append(f"- S: {random.choice(spin['situation'])}")
        lines.append(f"- P: {random.choice(spin['problem'])}")
    elif template_key == "demo":
        lines.append(f"- S: {random.choice(spin['situation'])}")
        lines.append(f"- I: {random.choice(spin['implication'])}")
    else:
        lines.append(f"- P: {random.choice(spin['problem'])}")
        lines.append(f"- NP: {random.choice(spin['need_payoff'])}")

    # Top objection + rebuttal per stage
    lines.append("")
    if template_key == "closing":
        lines.append("**Námitka:** *\"Musím to projednat s vedením.\"*")
        lines.append("→ Mám one-pager pro CEO — 3 čísla, ROI kalkulačka.")
    elif template_key == "demo":
        lines.append("**Námitka:** *\"Už něco používáme.\"*")
        lines.append("→ Setup za 2 dny vs 4-6 týdnů. Můžeme běžet paralelně a porovnat.")
    else:
        lines.append("**Námitka:** *\"Nemáme problém s engagementem.\"*")
        lines.append("→ Gallup: 77 % zaměstnanců není angažovaných. Máte data, nebo pocit?")

    return "\n".join(lines)


def generate_pomodoro_blocks(deal_count):
    """Generate Pomodoro time blocks for ADHD-friendly scheduling."""
    now = datetime.now()
    # Start from current time or 9:00, whichever is later
    start = now.replace(hour=9, minute=0, second=0, microsecond=0)
    if now > start:
        # Round up to next 30-min block
        mins = now.minute
        if mins < 30:
            start = now.replace(minute=30, second=0, microsecond=0)
        else:
            start = (now + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

    blocks = []
    current = start
    calls_done = 0

    for i in range(min(deal_count, 8)):
        # 25min focus block
        end = current + timedelta(minutes=25)
        blocks.append(f"- **{current.strftime('%H:%M')}-{end.strftime('%H:%M')}** 🍅 Call #{i+1}")
        current = end

        # 5min break
        end = current + timedelta(minutes=5)
        blocks.append(f"- **{current.strftime('%H:%M')}-{end.strftime('%H:%M')}** ☕ Pauza")
        current = end

        calls_done += 1

        # After 4 pomodoros, 15min break
        if calls_done % 4 == 0 and i < deal_count - 1:
            end = current + timedelta(minutes=15)
            blocks.append(f"- **{current.strftime('%H:%M')}-{end.strftime('%H:%M')}** 🧘 Dlouhá pauza")
            current = end

    return "\n".join(blocks)



def generate_call_list(deals_prep):
    """Generate a quick-reference call list."""
    lines = [f"# Call List — {date.today().isoformat()}", ""]
    for i, (deal, _) in enumerate(deals_prep, 1):
        org = extract_org(deal)
        contact = extract_contact(deal)
        phone = contact["phone"] or "📵 bez čísla"
        lines.append(f"{i}. **{org}** — {contact['name']} — {phone}")
    lines.append(f"\n---\n*{len(deals_prep)} hovorů naplánováno*")
    return "\n".join(lines)


def main(send_telegram=False):
    secrets = load_secrets()
    base = secrets.get("PIPEDRIVE_BASE_URL", "").rstrip("/")
    token = secrets.get("PIPEDRIVE_API_TOKEN", "")

    if not base or not token:
        log("Missing Pipedrive credentials", "ERROR")
        print("ERROR: Missing PIPEDRIVE_BASE_URL or PIPEDRIVE_API_TOKEN")
        return 1

    now = datetime.now()
    today = date.today()
    day_name = CZECH_DAYS.get(today.weekday(), "")
    is_weekend = today.weekday() >= 5

    log(f"Starting morning prep for {today}")

    # Weekend mode
    if is_weekend:
        content = f"# {day_name} {today.isoformat()}\n\n"
        content += "## Weekend\n"
        content += "- Žádné hovory naplánované\n"
        content += "- Volitelně: projdi pipeline, naplánuj pondělí\n"
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(content)
        log("Weekend mode — no calls")
        print(f"Weekend mode — saved to {OUTPUT}")
        return 0

    # Pull deals
    print("Pulling deals from Pipedrive...")
    deals = get_open_deals(base, token)
    if not deals:
        log("No open deals found")
        print("No open deals in pipeline!")
        return 1

    log(f"Found {len(deals)} open deals")

    # Score and sort deals
    scored = []
    for deal in deals:
        score = classify_deal_priority(deal)
        scored.append((deal, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    # Top deals for today (max 10)
    top_deals = scored[:10]

    # Count deals needing action
    today_str = today.isoformat()
    today_calls = sum(1 for d, _ in scored if d.get("next_activity_date") == today_str)
    stale_deals = sum(1 for d, _ in scored if days_since(d.get("last_activity_date")) > 14)
    total_cold_calls = sum(1 for d, _ in scored
                          if d.get("stage_id") == 7 and days_since(d.get("last_activity_date")) > 3)

    # Generate content
    sections = []
    sections.append(f"# 🌅 Morning Prep — {day_name} {today.isoformat()}")
    sections.append(f"*Vygenerováno: {now.strftime('%H:%M')}*\n")

    # Quick stats
    sections.append("## Přehled dne")
    sections.append(f"- 📞 **{today_calls}** hovorů naplánovaných na dnes")
    sections.append(f"- 🔥 **{len(top_deals)}** top dealů k oslovení")
    sections.append(f"- ⚠️ **{stale_deals}** stale dealů (>14 dní bez aktivity)")
    sections.append(f"- ❄️ **{total_cold_calls}** cold callů k vyřízení")
    sections.append(f"- 💰 **{len(deals)}** celkem open dealů v pipeline")

    # TOP 3 priorities (ADHD — max 3 things to focus on)
    sections.append("\n## 🎯 TOP 3 na teď")
    for i, (deal, score) in enumerate(top_deals[:3], 1):
        org = extract_org(deal)
        contact = extract_contact(deal)
        phone = contact["phone"] or "📵"
        next_act = deal.get("next_activity_date", "")
        if next_act == today_str:
            tag = "📞 DNES"
        elif days_since(deal.get("last_activity_date")) > 14:
            tag = "⚠️ STALE"
        else:
            tag = "🔥 HOT"
        sections.append(f"**{i}. {org}** — {contact['name']} — {phone} [{tag}]")

    # Pomodoro schedule
    sections.append("\n## 🍅 Pomodoro plán")
    sections.append(generate_pomodoro_blocks(min(len(top_deals), 8)))

    # Detailed prep per deal
    sections.append("\n## 📋 Detailní příprava")
    for i, (deal, score) in enumerate(top_deals, 1):
        sections.append("")
        sections.append(format_deal_prep(deal, i, base, token))
        sections.append("")
        sections.append("---")

    # Cold calls section
    if total_cold_calls > 0:
        sections.append("\n## ❄️ Cold calls")
        cold_deals = [(d, s) for d, s in scored if d.get("stage_id") == 7 and days_since(d.get("last_activity_date")) > 3]
        for d, _ in cold_deals[:5]:
            org = extract_org(d)
            contact = extract_contact(d)
            sections.append(f"- **{org}** — {contact['name']} — {contact['phone'] or '📵'}")

    sections.append(f"\n---\n*Morning Sales Prep v1 | {now.strftime('%Y-%m-%d %H:%M')}*")

    content = "\n".join(sections)

    # Save
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content)
    log(f"Prep saved: {len(content)}B")

    # Save call list
    call_list_content = generate_call_list(top_deals)
    CALL_LIST.write_text(call_list_content)

    print(f"Morning prep saved to {OUTPUT}")
    print(f"Call list saved to {CALL_LIST}")
    print(f"Top deals: {len(top_deals)} | Today's calls: {today_calls} | Cold calls: {total_cold_calls}")

    # Telegram notification
    if send_telegram:
        tg_msg = f"🌅 *Morning Prep — {day_name}*\n\n"
        tg_msg += f"📞 {today_calls} hovorů dnes\n"
        tg_msg += f"🔥 {len(top_deals)} top dealů\n"
        tg_msg += f"❄️ {total_cold_calls} cold callů\n\n"

        tg_msg += "*TOP 3:*\n"
        for i, (deal, _) in enumerate(top_deals[:3], 1):
            org = extract_org(deal)
            contact = extract_contact(deal)
            tg_msg += f"{i}. {org} — {contact['name']}\n"

        tg_msg += f"\n⏰ Start teď. Prvních 90 min = sacred time."
        notify_telegram(tg_msg)
        log("Telegram notification sent")

    return 0


if __name__ == "__main__":
    send = "--send" in sys.argv
    exit(main(send_telegram=send))
