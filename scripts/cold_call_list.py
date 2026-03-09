#!/usr/bin/env python3
"""
Smart Cold Call List — denní prioritizovaný seznam hovorů s dopamine hooks.

Pro každý deal:
1. Vypočítá call priority score (signály, zdraví dealu, cadence timing)
2. Přidá "dopamine hook" — proč volat TEĎKA (quick win angle)
3. Vygeneruje one-liner opener + killer argument
4. Seskupí do 3 kategorií: HOT NOW / WARM / NURTURE

Usage:
  python3 scripts/cold_call_list.py                # today's call list
  python3 scripts/cold_call_list.py --top 5         # only top 5
  python3 scripts/cold_call_list.py --export        # save to reports/
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.paths import WORKSPACE, LOGS_DIR
from lib.secrets import load_secrets
from lib.notifications import notify_telegram
from lib.pipedrive import pipedrive_api, pipedrive_get_all

LOG_FILE = LOGS_DIR / "cold-call-list.log"
SIGNALS_DIR = WORKSPACE / "knowledge" / "signals"
HEALTH_DIR = WORKSPACE / "reports" / "health"


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_deal_signals(deal_id):
    """Load cached signals for a deal."""
    fpath = SIGNALS_DIR / f"deal_{deal_id}.json"
    if not fpath.exists():
        return []
    try:
        data = json.loads(fpath.read_text())
        return data.get("signals", [])
    except Exception:
        return []


def get_contact_info(token, deal):
    """Get contact name, email, phone from deal."""
    person_id = deal.get("person_id")
    if isinstance(person_id, dict):
        person_id = person_id.get("value")
    if not person_id:
        return deal.get("person_name", ""), "", ""

    person = pipedrive_api(token, "GET", f"/persons/{person_id}")
    if not person:
        return deal.get("person_name", ""), "", ""

    name = person.get("name", "")
    email = ""
    phone = ""
    emails = person.get("email", [])
    if emails and isinstance(emails, list) and emails:
        email = emails[0].get("value", "")
    phones = person.get("phone", [])
    if phones and isinstance(phones, list) and phones:
        phone = phones[0].get("value", "")

    return name, email, phone


def calculate_call_priority(deal, token):
    """Calculate call priority score (0-100) with dopamine hooks."""
    now = datetime.now()
    score = 0
    hooks = []
    risk_tags = []

    deal_id = deal["id"]
    org = deal.get("org_name", "") or deal.get("title", "")
    value = deal.get("value", 0)
    stage = deal.get("stage_order_nr", 0)
    next_date = deal.get("next_activity_date", "")
    last_date = deal.get("last_activity_date", "")

    # --- TIMING SIGNALS (max 30) ---

    # Overdue activity = call NOW
    if next_date:
        try:
            next_dt = datetime.strptime(next_date, "%Y-%m-%d")
            days_until = (next_dt - now).days
            if days_until < 0:
                score += 25
                hooks.append(f"OVERDUE {abs(days_until)}d — zavolej hned")
                risk_tags.append("OVERDUE")
            elif days_until == 0:
                score += 30
                hooks.append("DNES je naplánovaný call!")
            elif days_until == 1:
                score += 20
                hooks.append("Call je ZÍTRA — preparation call")
        except ValueError:
            pass
    else:
        # No next step = needs call
        score += 15
        hooks.append("Nemá next step — proaktivní call")
        risk_tags.append("NO_NEXT_STEP")

    # Stale detection
    days_silent = 0
    if last_date:
        try:
            last_dt = datetime.strptime(last_date, "%Y-%m-%d")
            days_silent = (now - last_dt).days
            if 3 <= days_silent <= 7:
                score += 15
                hooks.append(f"Perfect timing — {days_silent}d od posledního kontaktu")
            elif 7 < days_silent <= 14:
                score += 10
                hooks.append(f"Teplý ještě — {days_silent}d, připomeň se")
            elif days_silent > 21:
                score += 5
                hooks.append(f"Ghosting {days_silent}d — breakup call?")
                risk_tags.append("GHOSTING")
        except ValueError:
            pass

    # --- VALUE SIGNALS (max 20) ---
    if value >= 100000:
        score += 20
        hooks.append(f"High value: {value:,.0f} CZK")
    elif value >= 50000:
        score += 15
    elif value > 0:
        score += 10

    # --- STAGE SIGNALS (max 15) ---
    if stage >= 4:
        score += 15
        hooks.append("Close stage — push to close!")
    elif stage >= 3:
        score += 12
        hooks.append("Demo/Pilot stage — momentum")
    elif stage >= 2:
        score += 8

    # --- SIGNAL INTELLIGENCE (max 20) ---
    signals = get_deal_signals(deal_id)
    high_signals = [s for s in signals if s["priority"] == "high"]
    if high_signals:
        score += min(20, len(high_signals) * 7)
        best = high_signals[0]
        hooks.append(f"Signal: {best['type']} — {best['relevance'][:50]}")

    # --- DOPAMINE HOOKS (max 15) ---
    # Quick win detection
    if stage >= 3 and days_silent <= 7 and value > 0:
        score += 15
        hooks.insert(0, "QUICK WIN — warm deal, recent contact, has value")
    elif stage >= 2 and days_silent <= 3:
        score += 10
        hooks.insert(0, "HOT MOMENTUM — just talked, keep pushing")

    # Cap at 100
    score = min(100, score)

    # Generate opener
    opener = generate_opener(deal, signals, days_silent)

    return {
        "deal_id": deal_id,
        "org": org,
        "value": value,
        "stage": stage,
        "score": score,
        "hooks": hooks[:3],
        "risk_tags": risk_tags,
        "opener": opener,
        "days_silent": days_silent,
        "next_date": next_date,
    }


def generate_opener(deal, signals, days_silent):
    """Generate a one-liner opener for the call."""
    org = deal.get("org_name", "") or ""

    # Signal-based opener
    high_signals = [s for s in signals if s["priority"] == "high"]
    if high_signals:
        sig = high_signals[0]
        if sig["type"] == "hiring_hr":
            return f"Viděl jsem, že hledáte do HR týmu — proto volám, Echo Pulse by vám s tím mohl pomoct."
        elif sig["type"] == "employee_review":
            return f"Narazil jsem na recenze {org} na Atmoskop — zajímalo by mě, jak řešíte zpětnou vazbu od lidí."
        elif sig["type"] == "funding_growth":
            return f"Gratuluju k růstu {org} — jak řešíte engagement lidí při škálování?"
        elif sig["type"] == "leadership_change":
            return f"Zaregistroval jsem změny ve vedení — nový pohled = nové priority, proto volám."

    # Timing-based opener
    if days_silent <= 3:
        return f"Navazuju na náš poslední rozhovor — mám pro vás konkrétní návrh."
    elif days_silent <= 7:
        return f"Napadla mě jedna věc ohledně {org} — máte 2 minuty?"
    elif days_silent <= 14:
        return f"Připomínám se — měl jsem pro vás ještě jednu myšlenku."
    elif days_silent > 21:
        return f"Volám naposledy — chápu že to teď není priorita, jen chci nechat otevřené dveře."

    return f"Dobrý den, tady Josef z Behavery — volám ohledně Echo Pulse pro {org}."


def format_call_list(scored_deals, limit=None):
    """Format the call list with dopamine hooks."""
    if limit:
        scored_deals = scored_deals[:limit]

    hot = [d for d in scored_deals if d["score"] >= 70]
    warm = [d for d in scored_deals if 40 <= d["score"] < 70]
    nurture = [d for d in scored_deals if d["score"] < 40]

    lines = []
    lines.append("# Smart Cold Call List")
    lines.append(f"_{datetime.now().strftime('%d.%m.%Y %H:%M')} | {len(scored_deals)} dealů_\n")

    # Summary dopamine
    if hot:
        lines.append(f"🔥 **{len(hot)} HOT** — volej HNED (quick wins)")
    if warm:
        lines.append(f"🟡 **{len(warm)} WARM** — volej dnes/zítra")
    if nurture:
        lines.append(f"🟢 **{len(nurture)} NURTURE** — připravuj půdu")
    lines.append("")

    # Estimated call time
    total_calls = len(hot) + len(warm)
    lines.append(f"⏱️ Odhadovaný čas: **{total_calls * 5}min** ({total_calls} callů x 5min avg)\n")

    for category, emoji, deals in [
        ("HOT NOW", "🔥", hot),
        ("WARM", "🟡", warm),
        ("NURTURE", "🟢", nurture),
    ]:
        if not deals:
            continue

        lines.append(f"\n## {emoji} {category} ({len(deals)})\n")

        for i, d in enumerate(deals, 1):
            val_str = f"{d['value']:,.0f} CZK" if d['value'] > 0 else "—"
            tags = " ".join(f"`{t}`" for t in d["risk_tags"]) if d["risk_tags"] else ""

            lines.append(f"### {i}. {d['org']} — {d['score']}/100 {tags}")
            lines.append(f"**Deal {d['deal_id']}** | Value: {val_str} | Stage: {d['stage']} | Silent: {d['days_silent']}d")

            if d.get("contact_name"):
                phone_str = f" | {d['phone']}" if d.get("phone") else ""
                lines.append(f"📞 **{d['contact_name']}**{phone_str}")

            # Dopamine hooks
            for hook in d["hooks"]:
                lines.append(f"  💡 {hook}")

            # Opener
            lines.append(f"  🎯 *\"{d['opener']}\"*")
            lines.append("")

    # Motivational footer
    lines.append("\n---")
    if hot:
        lines.append(f"💪 **{len(hot)} quick winů čeká.** Jeden call = jeden krok blíž k dealu.")
    lines.append(f"📊 Průměrný close rate cold call: 2%. Tvůj (warm): ~15%. Volej warm first!")
    lines.append(f"\n_Generováno: {datetime.now().strftime('%d.%m.%Y %H:%M')}_")

    return "\n".join(lines)


def main():
    secrets = load_secrets()
    token = secrets.get("PIPEDRIVE_API_TOKEN") or secrets.get("PIPEDRIVE_TOKEN")
    if not token:
        log("No Pipedrive token found in secrets")
        return 1

    export_mode = "--export" in sys.argv
    top_n = None
    for i, arg in enumerate(sys.argv):
        if arg == "--top" and i + 1 < len(sys.argv):
            top_n = int(sys.argv[i + 1])

    # Fetch all open deals
    log("Fetching open deals...")
    deals = pipedrive_get_all(token, "/deals", {
        "status": "open",
        "user_id": "24403638",
    })
    log(f"  {len(deals)} open deals")

    # Score and prioritize
    log("Calculating call priorities...")
    scored = []
    for d in deals:
        result = calculate_call_priority(d, token)

        # Get contact info for top deals
        if result["score"] >= 40:
            name, email, phone = get_contact_info(token, d)
            result["contact_name"] = name
            result["email"] = email
            result["phone"] = phone

        scored.append(result)

    scored.sort(key=lambda x: x["score"], reverse=True)

    # Format
    report = format_call_list(scored, limit=top_n)
    print(report)

    # Save
    if export_mode:
        report_dir = WORKSPACE / "reports" / "call-lists"
        report_dir.mkdir(parents=True, exist_ok=True)
        fpath = report_dir / f"calls_{datetime.now().strftime('%Y-%m-%d')}.md"
        fpath.write_text(report)
        log(f"Report saved: {fpath}")

    # Telegram — only hot deals
    hot = [d for d in scored if d["score"] >= 70]
    if hot:
        tg_lines = [f"📞 Call List: {len(hot)} HOT dealů\n"]
        for d in hot[:5]:
            tg_lines.append(f"🔥 {d['org'][:20]} ({d['score']}/100)")
            if d["hooks"]:
                tg_lines.append(f"   → {d['hooks'][0][:50]}")
        tg_lines.append(f"\n⏱️ Est: {len(hot) * 5}min")
        notify_telegram("\n".join(tg_lines))

    return 0


if __name__ == "__main__":
    exit(main())
