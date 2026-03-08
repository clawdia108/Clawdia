#!/usr/bin/env python3
"""
TLDV → Pipedrive Sync — přepisuje TLDV transkripty do Pipedrive poznámek.

Pro každý sales call v TLDV exportu:
1. Najde odpovídající deal v Pipedrive (podle jména kontaktu/firmy)
2. Zkontroluje, jestli už tam transcript je
3. Pokud ne, zapíše transcript jako poznámku
4. Vygeneruje detailní post-call summary přes Claude CLI
5. Zapíše summary jako PINNED poznámku

Usage:
  python3 scripts/tldv_sync.py                    # sync all missing
  python3 scripts/tldv_sync.py --deal 360         # sync specific deal
  python3 scripts/tldv_sync.py --list              # list all TLDV sales calls
  python3 scripts/tldv_sync.py --dry-run           # preview without writing
"""

import json
import sys
import re
import subprocess
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.paths import WORKSPACE, LOGS_DIR
from lib.secrets import load_secrets
from lib.notifications import notify_telegram
from lib.pipedrive import pipedrive_api

TLDV_EXPORT = Path("/Users/josefhofman/Desktop/tldv_full_export.json")
LOG_FILE = LOGS_DIR / "tldv-sync.log"


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")



def load_tldv_sales_calls():
    """Load and filter sales calls from TLDV export."""
    if not TLDV_EXPORT.exists():
        log(f"TLDV export not found: {TLDV_EXPORT}")
        return []

    data = json.loads(TLDV_EXPORT.read_text())
    meetings = data.get("meetings", [])

    # Filter: has transcript, not a standup/internal meeting
    skip_words = [
        "stand up", "stand-up", "standup", "okrs", "product demo",
        "weekly", "sales stand", "monday weekly", "cena echo",
        "sales –", "web launch", "dosetupovani", "vybrat demičko",
        "budihstický", "customers feedback", "produkt demo",
    ]

    sales_calls = []
    for m in meetings:
        tr = m.get("transcript", [])
        if len(tr) < 10:
            continue
        name = m.get("name", "")
        if any(sw in name.lower() for sw in skip_words):
            continue
        sales_calls.append(m)

    sales_calls.sort(key=lambda x: x.get("happenedAt", ""), reverse=True)
    return sales_calls


def match_tldv_to_deal(meeting, deals_cache, token):
    """Try to match a TLDV meeting to a Pipedrive deal."""
    name = meeting.get("name", "").lower()
    invitees = meeting.get("invitees", [])

    # Extract contact names from meeting name (format: "Name / Josef Hofman - ...")
    contact_parts = name.split("/")[0].strip() if "/" in name else ""
    contact_parts2 = name.split(" - ")[0].strip() if " - " in name else ""

    # Try matching by invitee email
    for inv in invitees:
        email = inv.get("email", "").lower()
        if email and "behavera" not in email:
            # Search Pipedrive for this email
            result = pipedrive_api(token, "GET", "/persons/search", {
                "term": email, "fields": "email", "limit": "1",
            })
            if result and result.get("items"):
                person_id = result["items"][0].get("item", {}).get("id")
                if person_id:
                    # Find deals for this person
                    person_deals = pipedrive_api(token, "GET", f"/persons/{person_id}/deals", {
                        "status": "all_not_deleted", "limit": "5",
                    })
                    if person_deals:
                        return person_deals[0].get("id")

    # Try matching by contact name
    for search_name in [contact_parts, contact_parts2]:
        if len(search_name) > 3:
            # Extract last name
            parts = search_name.split()
            if parts:
                last = parts[-1]
                if len(last) >= 3:
                    result = pipedrive_api(token, "GET", "/persons/search", {
                        "term": last, "limit": "5",
                    })
                    if result and result.get("items"):
                        for item in result["items"]:
                            pid = item.get("item", {}).get("id")
                            if pid:
                                pd = pipedrive_api(token, "GET", f"/persons/{pid}/deals", {
                                    "status": "all_not_deleted", "limit": "3",
                                })
                                if pd:
                                    return pd[0].get("id")

    return None


def deal_has_transcript(token, deal_id):
    """Check if deal already has a transcript note."""
    notes = pipedrive_api(token, "GET", f"/deals/{deal_id}/notes", {
        "limit": "20",
    })
    if not notes:
        return False

    for n in notes:
        content = n.get("content", "") or ""
        if "přepis" in content.lower() or "transcript" in content.lower():
            if len(content) > 2000:  # substantial transcript
                return True
    return False


def format_transcript_for_pipedrive(meeting):
    """Format TLDV transcript as HTML for Pipedrive note."""
    name = meeting.get("name", "")
    date = meeting.get("happenedAt", "")[:10]
    duration = round(meeting.get("duration", 0) / 60, 1)
    segments = meeting.get("transcript", [])

    lines = [
        f"<h2>📝 Kompletní přepis: {name}</h2>",
        f"<p><b>Datum:</b> {date} | <b>Délka:</b> {duration} min | "
        f"<b>Segmentů:</b> {len(segments)}</p><hr>",
    ]

    for seg in segments:
        speaker = seg.get("speaker", seg.get("speaker_name", "?"))
        text = seg.get("text", "")
        ts_min = round(seg.get("startTime", 0) / 60, 1)
        lines.append(
            f"<p><b>[{ts_min:.1f}m] {speaker}:</b> {text}</p>"
        )

    return "\n".join(lines)


def generate_summary(meeting, deal, token):
    """Generate detailed post-call summary using Claude CLI."""
    transcript = meeting.get("transcript", [])
    transcript_text = "\n".join(
        f"[{round(s.get('startTime', 0)/60, 1):.1f}m] "
        f"{s.get('speaker', '?')}: {s.get('text', '')}"
        for s in transcript[:60]  # limit to 60 segments for context
    )

    name = meeting.get("name", "")
    date = meeting.get("happenedAt", "")[:10]
    duration = round(meeting.get("duration", 0) / 60, 1)
    deal_title = deal.get("title", "") if deal else ""
    org_name = deal.get("org_name", "") if deal else ""
    person_name = deal.get("person_name", "") if deal else ""
    invitees = ", ".join(
        i.get("name", "") for i in meeting.get("invitees", [])
        if i.get("name")
    )

    prompt = f"""Analyzuj tento prodejní hovor pro Behavera (Echo Pulse — měření spokojenosti zaměstnanců).
Piš ČESKY. Výstup formátuj jako HTML pro Pipedrive.

Meeting: {name}
Datum: {date} | Délka: {duration} min
Deal: {deal_title} | Firma: {org_name} | Kontakt: {person_name}
Účastníci: {invitees}

TRANSCRIPT:
{transcript_text[:6000]}

---

Vygeneruj detailní post-call summary v tomto formátu:

<h2>📋 Post-Call Summary — {person_name or name}</h2>
<p><b>Datum:</b> {date} | <b>Délka:</b> {duration} min</p>

<h3>📝 Shrnutí hovoru (3-5 vět)</h3>
[Co se řešilo, jaký byl výsledek, na čem se dohodli]

<h3>🟦 SITUATION</h3>
[Co jsme zjistili o firmě — konkrétní fakta z hovoru]

<h3>🟧 PROBLEM</h3>
[Jaké problémy zmínili — konkrétně]

<h3>🟥 IMPLICATION</h3>
[Jaké důsledky si uvědomují]

<h3>🟩 NEED-PAYOFF</h3>
[Co by jim řešení přineslo, co rezonovalo]

<h3>💬 Klíčové citace</h3>
[3-5 důležitých DOSLOVNÝCH citací z přepisu — přesně co řekl klient]

<h3>⚠️ Objections / Obavy</h3>
[Co namítali, jaké měli pochybnosti]

<h3>✅ Rozhodnutí a Next Steps</h3>
[Na čem jsme se dohodli]

<h3>🏥 Deal Health</h3>
[ADVANCE / CONTINUATION / STALL — s vysvětlením]

Piš výstup PŘÍMO jako HTML, žádný markdown."""

    try:
        import os as _os
        env = {k: v for k, v in _os.environ.items() if k != "CLAUDECODE"}
        result = subprocess.run(
            ["claude", "-p", "--model", "claude-sonnet-4-6",
             "--dangerously-skip-permissions"],
            input=prompt,
            capture_output=True, text=True, timeout=120,
            env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception as e:
        log(f"Claude CLI error: {e}")
    return None


def main():
    secrets = load_secrets()
    token = secrets.get("PIPEDRIVE_API_TOKEN") or secrets.get("PIPEDRIVE_TOKEN")
    if not token:
        token = "8a21711bcee8c0a34e7cfeefbeba2e554444d5d0"

    list_mode = "--list" in sys.argv
    dry_run = "--dry-run" in sys.argv
    specific_deal = None

    for i, arg in enumerate(sys.argv):
        if arg == "--deal" and i + 1 < len(sys.argv):
            specific_deal = int(sys.argv[i + 1])

    sales_calls = load_tldv_sales_calls()
    log(f"Found {len(sales_calls)} sales calls in TLDV export")

    if list_mode:
        for m in sales_calls:
            name = m.get("name", "")
            date = m.get("happenedAt", "")[:10]
            dur = round(m.get("duration", 0) / 60, 1)
            segs = len(m.get("transcript", []))
            inv = ", ".join(i.get("name", "") for i in m.get("invitees", []) if i.get("name"))[:50]
            print(f"  {date} | {dur:5.1f}min | {segs:3d} seg | {name[:50]:50s} | {inv}")
        return 0

    synced = 0
    errors = 0

    for meeting in sales_calls:
        name = meeting.get("name", "")
        date = meeting.get("happenedAt", "")[:10]

        # Match to deal
        deal_id = match_tldv_to_deal(meeting, {}, token)
        if not deal_id:
            continue

        if specific_deal and deal_id != specific_deal:
            continue

        # Check if transcript already exists
        if deal_has_transcript(token, deal_id):
            continue

        deal = pipedrive_api(token, "GET", f"/deals/{deal_id}")
        org = deal.get("org_name", "") if deal else ""

        log(f"Syncing: {name} → deal {deal_id} ({org})")

        if dry_run:
            log(f"  [DRY RUN] Would sync transcript + summary")
            continue

        # Write transcript
        transcript_html = format_transcript_for_pipedrive(meeting)
        tr_note = pipedrive_api(token, "POST", "/notes", {
            "deal_id": deal_id,
            "content": transcript_html,
        })
        if tr_note:
            log(f"  Transcript written (note {tr_note.get('id', '?')})")
        else:
            log(f"  ERROR: Failed to write transcript")
            errors += 1
            continue

        # Generate and write summary
        summary = generate_summary(meeting, deal, token)
        if summary:
            sum_note = pipedrive_api(token, "POST", "/notes", {
                "deal_id": deal_id,
                "content": summary,
                "pinned_to_deal_flag": 1,
            })
            if sum_note:
                log(f"  Summary written and pinned (note {sum_note.get('id', '?')})")
                synced += 1
            else:
                log(f"  ERROR: Failed to write summary")
                errors += 1
        else:
            log(f"  WARNING: Summary generation failed, transcript still saved")
            synced += 1

    log(f"Done: {synced} synced, {errors} errors")

    if synced > 0 and not dry_run:
        notify_telegram(f"📝 TLDV Sync: {synced} přepisů synchronizováno do Pipedrive")

    return 0


if __name__ == "__main__":
    exit(main())
