#!/usr/bin/env python3
"""
Follow-up Engine (Loop 3) — automatický follow-up systém.

Workflow:
1. Scan všech open dealů v Pipedrive
2. Identifikuje: no next step, overdue, stale (7/14/21+ dní)
3. Pro každý deal určí typ follow-upu podle 3-7-7-17 cadence
4. Vygeneruje follow-up email draft přes Claude CLI
5. Uloží drafty jako JSON do fronty (drafts/followups/)
6. Pošle Telegram summary

Usage:
  python3 scripts/followup_engine.py                # full scan + generate drafts
  python3 scripts/followup_engine.py --scan          # only scan, no drafts
  python3 scripts/followup_engine.py --deal 360      # specific deal
  python3 scripts/followup_engine.py --dry-run       # preview without writing
"""

import json
import sys
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.paths import WORKSPACE, LOGS_DIR
from lib.secrets import load_secrets
from lib.notifications import notify_telegram
from lib.notion import push_analysis
from lib.pipedrive import pipedrive_api

LOG_FILE = LOGS_DIR / "followup-engine.log"
DRAFTS_DIR = WORKSPACE / "drafts" / "followups"
CADENCE_LOG = WORKSPACE / "knowledge" / "followup_cadence.json"


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")



def get_contact_email(token, deal):
    """Get contact email from deal's person."""
    person_id = deal.get("person_id")
    if isinstance(person_id, dict):
        person_id = person_id.get("value")
    if not person_id:
        return None, None

    person = pipedrive_api(token, "GET", f"/persons/{person_id}")
    if not person:
        return None, None

    name = person.get("name", "")
    emails = person.get("email", [])
    if emails and isinstance(emails, list):
        email = emails[0].get("value", "")
        if email:
            return name, email
    return name, None


def scan_pipeline(token):
    """Scan all open deals and categorize follow-up needs."""
    deals = []
    start = 0
    while True:
        batch = pipedrive_api(token, "GET", "/deals", {
            "status": "open",
            "user_id": "24403638",
            "start": str(start),
            "limit": "100",
        })
        if not batch:
            break
        deals.extend(batch)
        if len(batch) < 100:
            break
        start += 100

    now = datetime.now()
    results = {
        "no_next_step": [],
        "overdue": [],
        "stale_7d": [],     # value-add follow-up (day 3-7)
        "stale_14d": [],    # check-in follow-up (day 7-14)
        "ghosting": [],     # breakup/last attempt (day 17+)
    }

    for d in deals:
        deal_id = d["id"]
        title = d.get("title", "")
        org = d.get("org_name", "") or ""
        person = d.get("person_name", "") or ""
        next_date = d.get("next_activity_date", "")
        last_date = d.get("last_activity_date", "")
        value = d.get("value", 0)

        # Get person_id for email lookup later
        pid = d.get("person_id")
        if isinstance(pid, dict):
            pid = pid.get("value")

        info = {
            "deal_id": deal_id,
            "title": title,
            "org": org,
            "person": person,
            "person_id": pid,
            "value": value,
            "last_activity": last_date,
            "next_activity": next_date,
            "stage_order_nr": d.get("stage_order_nr", 0),
        }

        # No next step
        if not next_date:
            info["action"] = "schedule_next_step"
            info["urgency"] = "high"
            results["no_next_step"].append(info)
            continue

        # Overdue
        try:
            next_dt = datetime.strptime(next_date, "%Y-%m-%d")
            if next_dt < now - timedelta(days=1):
                info["days_overdue"] = (now - next_dt).days
                info["action"] = "complete_or_reschedule"
                info["urgency"] = "high"
                results["overdue"].append(info)
        except ValueError:
            pass

        # Stale (based on last activity)
        if last_date:
            try:
                last_dt = datetime.strptime(last_date, "%Y-%m-%d")
                days_silent = (now - last_dt).days
                info["days_silent"] = days_silent

                if days_silent >= 21:
                    info["action"] = "breakup_or_disqualify"
                    info["urgency"] = "low"
                    info["cadence_step"] = "breakup"
                    results["ghosting"].append(info)
                elif days_silent >= 14:
                    info["action"] = "check_in"
                    info["urgency"] = "medium"
                    info["cadence_step"] = "day_14"
                    results["stale_14d"].append(info)
                elif days_silent >= 7:
                    info["action"] = "value_add"
                    info["urgency"] = "medium"
                    info["cadence_step"] = "day_7"
                    results["stale_7d"].append(info)
            except ValueError:
                pass

    return results


def determine_followup_type(deal_info):
    """Determine what type of follow-up email to send."""
    action = deal_info.get("action", "")
    cadence = deal_info.get("cadence_step", "")

    if action == "breakup_or_disqualify":
        return "breakup"
    elif action == "check_in" or cadence == "day_14":
        return "check_in"
    elif action == "value_add" or cadence == "day_7":
        return "value_add"
    elif action == "schedule_next_step":
        return "schedule"
    elif action == "complete_or_reschedule":
        return "reschedule"
    return "generic"


FOLLOWUP_TEMPLATES = {
    "value_add": """Typ: VALUE-ADD (den 3-7 po posledním kontaktu)
Tón: přátelský, přinášející hodnotu, ne "jen se ptám"
Obsah: sdílej konkrétní insight relevantní pro jejich odvětví/situaci
Příklad: článek, benchmark, case study, relevantní data
NIKDY: "Chtěl jsem se zeptat jestli jste se rozhodli" """,

    "check_in": """Typ: CHECK-IN (den 7-14)
Tón: stručný, přímý, profesionální
Obsah: krátká připomínka + konkrétní otázka
Příklad: "Přemýšlel jste o tom, co jsme řešili? Rád bych se domluvil na dalším kroku."
NIKDY: "Doufám že jste v pořádku" nebo "Píšu si jenom ověřit" """,

    "breakup": """Typ: BREAKUP EMAIL (den 17-21+)
Tón: přímý, respektující, bez tlaku
Obsah: přiznej že to asi není priorita, nech otevřené dveře
Příklad: "Chápu že to teď asi není priorita. Nechám vám na sebe kontakt, kdyby se to změnilo."
NIKDY: "Napsal jsem vám už 5x" nebo jakýkoliv guilt-trip """,

    "schedule": """Typ: SCHEDULE NEXT STEP
Tón: proaktivní, konkrétní
Obsah: navrhni konkrétní termín a důvod
Příklad: "Co kdybychom se spojili v [den]? Mám pro vás [konkrétní věc]."
NIKDY: "Kdy by se vám hodilo?" (příliš vágní) """,

    "reschedule": """Typ: RESCHEDULE (overdue aktivita)
Tón: bez výčitek, konkrétní
Obsah: připomeň co se řešilo, navrhni nový termín
NIKDY: "Zapomněl jsem se ozvat" """,
}


def get_deal_context(token, deal_id):
    """Get recent notes and activities for context."""
    notes = pipedrive_api(token, "GET", f"/deals/{deal_id}/notes", {"limit": "5"})
    activities = pipedrive_api(token, "GET", f"/deals/{deal_id}/activities", {
        "limit": "5", "done": "1",
    })
    context = []
    if notes:
        for n in notes[:3]:
            content = n.get("content", "")[:200]
            context.append(f"Poznámka: {content}")
    if activities:
        for a in activities[:3]:
            atype = a.get("type", "")
            asubj = a.get("subject", "")
            adate = a.get("due_date", "")
            context.append(f"Aktivita {adate}: {atype} — {asubj}")
    return "\n".join(context) if context else "Žádný předchozí kontext."


def generate_followup_email(deal_info, followup_type, secrets, token=None):
    """Generate follow-up email using Claude CLI."""
    org = deal_info.get("org", "")
    person = deal_info.get("person", "")
    title = deal_info.get("title", "")
    days = deal_info.get("days_silent", deal_info.get("days_overdue", 0))

    template = FOLLOWUP_TEMPLATES.get(followup_type, FOLLOWUP_TEMPLATES["check_in"])

    # Get deal context for personalization
    context = ""
    if token:
        context = get_deal_context(token, deal_info["deal_id"])

    prompt = f"""Napiš follow-up email pro Josefa Hofmana z Behavery (Echo Pulse — měření spokojenosti zaměstnanců).

PRAVIDLA (Josef's tone of voice):
- Profesionální ale neformální, lowercase vykání (vy, vám — malým)
- Žádný corporate speak, žádné AI patterns, žádné vykřičníky
- Stručný, konkrétní, max 80 slov
- Čeština bez chyb
- Podpis: Josef Hofman, Behavera
- NIKDY: "Děkuji za váš čas", "Rád bych navázal", "Doufám že se máte dobře"

{template}

KONTEXT DEALU:
- Firma: {org}
- Kontakt: {person}
- Deal: {title}
- Dní od posledního kontaktu: {days}
- Produkt: Echo Pulse (měření angažovanosti, 99-129 Kč/osoba/měsíc, pilot 29,900 Kč/3 měsíce)

PŘEDCHOZÍ INTERAKCE:
{context}

Vrať POUZE dva řádky (žádný jiný text):
SUBJECT: [předmět emailu — krátký, konkrétní, bez Echo Pulse v názvu pokud to není první kontakt]
BODY: [text emailu, max 80 slov, přímý, konkrétní, personalizovaný]"""

    try:
        import os as _os
        env = {k: v for k, v in _os.environ.items() if k != "CLAUDECODE"}
        result = subprocess.run(
            ["claude", "-p", "--model", "claude-sonnet-4-6",
             "--dangerously-skip-permissions"],
            input=prompt,
            capture_output=True, text=True, timeout=60,
            env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            output = result.stdout.strip()
            lines = output.split("\n")
            subject = ""
            body_lines = []
            for line in lines:
                if line.upper().startswith("SUBJECT:"):
                    subject = line.split(":", 1)[1].strip()
                elif line.upper().startswith("BODY:"):
                    body_lines.append(line.split(":", 1)[1].strip())
                elif body_lines:
                    body_lines.append(line)
            body = "\n".join(body_lines).strip() if body_lines else output
            if not subject:
                subject = f"Echo Pulse — {org}"
            return subject, body
    except Exception as e:
        log(f"Claude CLI error for {org}: {e}")

    # Fallback
    return f"Echo Pulse — {org}", f"Dobrý den,\n\nchtěl jsem navázat na náš předchozí kontakt ohledně Echo Pulse.\n\nS pozdravem,\nJosef Hofman\nBehavera"


def get_multichannel_actions(deal_info, followup_type):
    """Get recommended multichannel actions alongside email."""
    days = deal_info.get("days_silent", deal_info.get("days_overdue", 0))
    person = deal_info.get("person", "")
    actions = []

    if followup_type == "value_add":
        actions.append(f"📱 LinkedIn: Podívej se na profil {person}, lajkni/komentuj post")
        actions.append(f"📞 Call za 2 dny pokud neodpoví na email")
    elif followup_type == "check_in":
        actions.append(f"📞 Call: Zavolej {person} dopoledne (10-11h je nejlepší)")
        actions.append(f"📱 LinkedIn: Pošli connection request s osobní zprávou")
    elif followup_type == "breakup":
        actions.append(f"📞 Poslední call: Zavolej než pošleš breakup email")
        actions.append(f"📱 LinkedIn: Poslední view profilu (social proof)")
    elif followup_type == "schedule":
        actions.append(f"📞 Call: Zavolej s konkrétním návrhem termínu (St/Čt 10-11h)")
    elif followup_type == "reschedule":
        actions.append(f"📞 Call: Zavolej dnes 16-17h (Gong: 71% lepší connect rate)")

    return actions


def save_draft(deal_info, followup_type, subject, body, email):
    """Save draft to queue for Gmail creation."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    multichannel = get_multichannel_actions(deal_info, followup_type)
    draft = {
        "deal_id": deal_info["deal_id"],
        "org": deal_info.get("org", ""),
        "person": deal_info.get("person", ""),
        "email": email,
        "subject": subject,
        "body": body,
        "followup_type": followup_type,
        "multichannel_actions": multichannel,
        "generated_at": datetime.now().isoformat(),
        "status": "pending",  # pending → approved → sent
    }
    fname = f"fu_{deal_info['deal_id']}_{datetime.now().strftime('%Y%m%d_%H%M')}.json"
    fpath = DRAFTS_DIR / fname
    fpath.write_text(json.dumps(draft, ensure_ascii=False, indent=2))
    return fpath


def main():
    secrets = load_secrets()
    token = secrets.get("PIPEDRIVE_API_TOKEN") or secrets.get("PIPEDRIVE_TOKEN")
    if not token:
        log("No Pipedrive token found in secrets")
        return 1

    scan_only = "--scan" in sys.argv
    dry_run = "--dry-run" in sys.argv
    stdout_mode = "--stdout" in sys.argv
    specific_deal = None
    for i, arg in enumerate(sys.argv):
        if arg == "--deal" and i + 1 < len(sys.argv):
            specific_deal = int(sys.argv[i + 1])

    # Scan pipeline
    log("Scanning pipeline for follow-up needs...")
    results = scan_pipeline(token)

    total = sum(len(v) for v in results.values())
    log(f"Pipeline scan: {total} deals need attention")
    log(f"  ❌ No next step: {len(results['no_next_step'])}")
    log(f"  ⏰ Overdue: {len(results['overdue'])}")
    log(f"  🟡 Stale 7d: {len(results['stale_7d'])}")
    log(f"  🟠 Stale 14d: {len(results['stale_14d'])}")
    log(f"  🔴 Ghosting 21d+: {len(results['ghosting'])}")

    if scan_only:
        # Print detailed scan
        total_deals = 0
        scan_summary = []
        for category, deals in results.items():
            if deals:
                total_deals += len(deals)
                scan_summary.append(f"{category}: {len(deals)}")
                print(f"\n{'='*50}")
                print(f"  {category.upper()} ({len(deals)} deals)")
                print(f"{'='*50}")
                for d in deals:
                    days = d.get("days_silent", d.get("days_overdue", ""))
                    days_str = f" ({days}d)" if days else ""
                    print(f"  {d['deal_id']:4d} | {d['org'][:25]:25s} | {d['person'][:20]:20s} | {d['action']}{days_str}")

        # Push to Notion
        notion_token = secrets.get("NOTION_TOKEN")
        if notion_token and total_deals > 0:
            findings = " | ".join(scan_summary)
            push_analysis(notion_token, f"Follow-up Scan {datetime.now().strftime('%d.%m')}",
                           "Pipeline Analysis", findings,
                           deals_affected=total_deals)
        return 0

    # Generate follow-up drafts
    all_deals = []
    # Priority order: overdue first, then no next step, then stale
    for category in ["overdue", "no_next_step", "stale_7d", "stale_14d", "ghosting"]:
        all_deals.extend(results[category])

    if specific_deal:
        all_deals = [d for d in all_deals if d["deal_id"] == specific_deal]

    drafts_created = 0
    draft_files = []

    for deal_info in all_deals:
        did = deal_info["deal_id"]
        org = deal_info.get("org", "")

        # Get contact email
        pid = deal_info.get("person_id")
        person_name, email = get_contact_email(token, {"person_id": pid}) if pid else (None, None)
        if not email:
            deal_data = pipedrive_api(token, "GET", f"/deals/{did}")
            if deal_data:
                person_name, email = get_contact_email(token, deal_data)

        if not email:
            log(f"  ⚠️ No email for {org} (deal {did}) — skipping")
            continue

        followup_type = determine_followup_type(deal_info)
        log(f"  Generating {followup_type} for {org} ({email})...")

        if dry_run:
            log(f"  [DRY RUN] Would generate {followup_type} draft")
            continue

        subject, body = generate_followup_email(deal_info, followup_type, secrets, token)
        fpath = save_draft(deal_info, followup_type, subject, body, email)
        draft_files.append(fpath)
        drafts_created += 1
        log(f"  ✅ Draft saved: {fpath.name}")

    log(f"\nDone: {drafts_created} drafts created")

    # Telegram summary
    if drafts_created > 0 and not dry_run:
        msg_lines = [f"📧 Follow-up Engine: {drafts_created} draftů připraveno\n"]
        for category, emoji in [("overdue", "⏰"), ("no_next_step", "❌"),
                                 ("stale_7d", "🟡"), ("stale_14d", "🟠"), ("ghosting", "🔴")]:
            count = len(results[category])
            if count > 0:
                msg_lines.append(f"{emoji} {category}: {count} dealů")
        msg_lines.append(f"\n📂 Drafty v: drafts/followups/")
        msg_lines.append("Spusť `claude` a řekni 'odešli follow-up drafty' pro Gmail.")
        notify_telegram("\n".join(msg_lines))

    # Print draft summary for Claude Code to pick up
    if draft_files:
        print(f"\n{'='*50}")
        print(f"  {len(draft_files)} DRAFTS READY FOR GMAIL")
        print(f"{'='*50}")
        for f in draft_files:
            d = json.loads(f.read_text())
            print(f"\n  📧 {d['org'][:25]:25s} → {d['email'][:30]:30s} | {d['followup_type']}")
            print(f"     Subject: {d['subject'][:60]}")
            if stdout_mode:
                print(f"     ---")
                for line in d['body'].split('\n'):
                    print(f"     {line}")
                if d.get('multichannel_actions'):
                    print(f"     ---")
                    for action in d['multichannel_actions']:
                        print(f"     {action}")

    return 0


if __name__ == "__main__":
    exit(main())
