#!/usr/bin/env python3
"""
Post-Call Processor — automatické zpracování po hovoru.

Workflow:
1. Vezme TLDV transcript (z exportu nebo přímo JSON)
2. Analyzuje hovor přes Claude: klíčové body, rozhodnutí, objections, next steps
3. Zapíše strukturované poznámky do Pipedrive
4. Vygeneruje draft follow-up emailu (Josef's tone of voice)
5. Naplánuje next Pipedrive aktivitu

Usage:
  python3 scripts/post_call_processor.py --deal 360                    # najde transcript v TLDV exportu
  python3 scripts/post_call_processor.py --deal 360 --transcript call.json  # vlastní transcript
  python3 scripts/post_call_processor.py --deal 360 --paste             # vloží transcript z stdin
"""

import json
import sys
import re
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.paths import WORKSPACE, LOGS_DIR
from lib.secrets import load_secrets
import subprocess as _subprocess
from lib.notifications import notify_telegram
from lib.pipedrive import pipedrive_api


TLDV_EXPORT = Path("/Users/josefhofman/Desktop/tldv_full_export.json")
LOG_FILE = LOGS_DIR / "post-call.log"
DRAFTS_DIR = WORKSPACE / "drafts"


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")



def find_tldv_transcript(org_name, contact_name=None):
    """Find most recent TLDV transcript matching company/contact."""
    if not TLDV_EXPORT.exists():
        return None

    try:
        with open(TLDV_EXPORT) as f:
            data = json.load(f)
    except Exception:
        return None

    meetings = data.get("meetings", [])
    search_terms = []
    if org_name:
        search_terms.append(org_name.lower())
    if contact_name:
        parts = contact_name.strip().split()
        if parts:
            search_terms.append(parts[-1].lower())

    best = None
    for m in meetings:
        name = m.get("name", "").lower()
        invitees = m.get("invitees", [])
        inv_text = " ".join(
            f"{i.get('name','')} {i.get('email','')}".lower()
            for i in invitees
        )
        searchable = f"{name} {inv_text}"

        for term in search_terms:
            if len(term) >= 3 and term in searchable:
                tr = m.get("transcript", [])
                if tr and (not best or len(tr) > len(best.get("transcript", []))):
                    best = m
                break

    if best:
        return {
            "name": best.get("name", ""),
            "date": best.get("happenedAt", "")[:30],
            "duration_min": round(best.get("duration", 0) / 60, 1),
            "invitees": best.get("invitees", []),
            "transcript": best.get("transcript", []),
        }
    return None


def format_transcript(transcript_data):
    """Format transcript segments into readable text."""
    segments = transcript_data if isinstance(transcript_data, list) else transcript_data.get("transcript", [])
    lines = []
    for seg in segments:
        speaker = seg.get("speaker", seg.get("speaker_name", "?"))
        text = seg.get("text", "")
        ts_min = round(seg.get("startTime", 0) / 60, 1)
        lines.append(f"[{ts_min:.1f}m] {speaker}: {text}")
    return "\n".join(lines)


def analyze_call(deal, transcript_text, secrets):
    """Analyze call transcript using Claude Code CLI (claude -p)."""
    title = deal.get("title", "")
    org_name = deal.get("org_name", "")
    person_name = deal.get("person_name", "")
    value = deal.get("value", 0)

    prompt = f"""Jsi sales analytik pro Behavera (Echo Pulse — měření spokojenosti zaměstnanců).
Analyzuješ transkripty prodejních hovorů. Připrav dvě části oddělené řádkem "===EMAIL===".

Josef's tone of voice pro email:
- Profesionální ale neformální, lowercase vykání (vy, vám, vaše — malým)
- Žádný corporate speak, žádné AI patterns
- Stručný, konkrétní, přátelský, čeština bez chyb
- NIKDY: "Děkuji za váš čas", "Rád bych navázal", vykřičníky

**Deal:** {title}
**Firma:** {org_name}
**Kontakt:** {person_name}
**Hodnota:** {value} CZK

---
TRANSCRIPT:
{transcript_text[:8000]}
---

## ČÁST 1: CRM Poznámky (HTML pro Pipedrive)

<h2>📋 Post-Call Summary — {person_name} ({org_name})</h2>
<h3>📝 Shrnutí hovoru</h3> [2-3 věty]
<h3>🟦 SITUATION</h3> [co jsme zjistili]
<h3>🟧 PROBLEM</h3> [problémy]
<h3>🟥 IMPLICATION</h3> [důsledky]
<h3>🟩 NEED-PAYOFF</h3> [hodnota]
<h3>💬 Klíčové citace</h3> [3-5 doslovných citací z přepisu]
<h3>⚠️ Objections</h3> [námitky]
<h3>✅ Next Steps</h3> [co bylo domluveno]
<h3>🏥 Deal Health</h3> [ADVANCE/CONTINUATION/STALL + vysvětlení]

===EMAIL===

## ČÁST 2: Follow-up Email Draft

Předmět: [konkrétní]

[Email v češtině, max 150 slov, rovnou k věci.]"""

    try:
        import os as _os
        env = {k: v for k, v in _os.environ.items() if k != "CLAUDECODE"}
        result = _subprocess.run(
            ["claude", "-p", "--model", "claude-sonnet-4-6",
             "--dangerously-skip-permissions"],
            input=prompt,
            capture_output=True, text=True, timeout=120,
            env=env,
        )
        if result.returncode != 0 or not result.stdout.strip():
            log(f"Claude CLI error: {result.stderr[:200]}")
            return None, None
        output = result.stdout.strip()
    except Exception as e:
        log(f"Claude CLI error: {e}")
        return None, None

    # Split into notes and email
    parts = output.split("===EMAIL===")
    notes = parts[0].strip() if parts else output
    email = parts[1].strip() if len(parts) > 1 else None

    return notes, email


def parse_next_activity(notes_text):
    """Extract next activity recommendation from notes."""
    lines = notes_text.split("\n")
    in_next = False
    activity = {"type": "call", "due_days": 3, "subject": "Follow-up"}

    for line in lines:
        if "next activity" in line.lower() or "doporučená" in line.lower():
            in_next = True
            continue
        if in_next and line.strip():
            text = line.strip().lstrip("- ")
            if "call" in text.lower() or "zavolat" in text.lower():
                activity["type"] = "call"
            elif "email" in text.lower() or "mail" in text.lower():
                activity["type"] = "email"
            elif "meeting" in text.lower() or "schůzka" in text.lower():
                activity["type"] = "meeting"

            # Try to find timing
            if "zítra" in text.lower() or "1 den" in text.lower():
                activity["due_days"] = 1
            elif "3 dn" in text.lower() or "za 3" in text.lower():
                activity["due_days"] = 3
            elif "týden" in text.lower() or "7 dn" in text.lower():
                activity["due_days"] = 7
            elif "14 dn" in text.lower() or "2 týdn" in text.lower():
                activity["due_days"] = 14

            activity["subject"] = text[:80]
            break

    return activity


def main():
    secrets = load_secrets()
    token = secrets.get("PIPEDRIVE_API_TOKEN") or secrets.get("PIPEDRIVE_TOKEN")
    if not token:
        token = "8a21711bcee8c0a34e7cfeefbeba2e554444d5d0"

    deal_id = None
    transcript_file = None
    paste_mode = "--paste" in sys.argv
    dry_run = "--dry-run" in sys.argv

    for i, arg in enumerate(sys.argv):
        if arg == "--deal" and i + 1 < len(sys.argv):
            deal_id = int(sys.argv[i + 1])
        elif arg == "--transcript" and i + 1 < len(sys.argv):
            transcript_file = sys.argv[i + 1]

    if not deal_id:
        print("Usage: python3 scripts/post_call_processor.py --deal DEAL_ID [--transcript FILE] [--paste] [--dry-run]")
        return 1

    # Get deal info
    log(f"Processing post-call for deal {deal_id}...")
    deal = pipedrive_api(token, "GET", f"/deals/{deal_id}")
    if not deal:
        log(f"Deal {deal_id} not found")
        return 1

    org_name = deal.get("org_name", "")
    person_name = deal.get("person_name", "")
    log(f"Deal: {deal.get('title','')} ({org_name})")

    # Get transcript
    transcript_text = None

    if paste_mode:
        log("Reading transcript from stdin...")
        transcript_text = sys.stdin.read()
    elif transcript_file:
        log(f"Reading transcript from {transcript_file}...")
        fpath = Path(transcript_file)
        if fpath.exists():
            content = fpath.read_text()
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    transcript_text = format_transcript(data)
                elif isinstance(data, dict) and "transcript" in data:
                    transcript_text = format_transcript(data["transcript"])
                else:
                    transcript_text = content
            except json.JSONDecodeError:
                transcript_text = content
        else:
            log(f"File not found: {transcript_file}")
            return 1
    else:
        log(f"Searching TLDV export for {org_name} / {person_name}...")
        tldv = find_tldv_transcript(org_name, person_name)
        if tldv:
            log(f"Found: {tldv['name']} ({tldv['date']}, {tldv['duration_min']}min, {len(tldv['transcript'])} segments)")
            transcript_text = format_transcript(tldv["transcript"])
        else:
            log("No TLDV transcript found. Use --transcript or --paste.")
            return 1

    if not transcript_text or len(transcript_text) < 50:
        log("Transcript too short or empty")
        return 1

    log(f"Transcript: {len(transcript_text)} chars")

    # Analyze
    log("Analyzing call with Claude...")
    notes, email_draft = analyze_call(deal, transcript_text, secrets)

    if not notes:
        log("ERROR: Claude analysis failed")
        return 1

    log(f"Analysis complete: {len(notes)} chars notes" + (f", {len(email_draft)} chars email" if email_draft else ""))

    if dry_run:
        print("\n" + "="*60)
        print("NOTES:")
        print("="*60)
        print(notes)
        if email_draft:
            print("\n" + "="*60)
            print("EMAIL DRAFT:")
            print("="*60)
            print(email_draft)
        return 0

    # Write notes to Pipedrive
    html_notes = notes.replace("\n", "<br>\n")
    result = pipedrive_api(token, "POST", "/notes", {
        "deal_id": deal_id,
        "content": f"📞 Post-call analýza ({datetime.now().strftime('%-d.%-m.%Y %H:%M')})<br><br>{html_notes}",
    })
    if result:
        log(f"Notes written to Pipedrive deal {deal_id}")
    else:
        log("ERROR: Failed to write notes to Pipedrive")

    # Save email draft
    if email_draft:
        DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
        draft_file = DRAFTS_DIR / f"followup_{deal_id}_{datetime.now().strftime('%Y%m%d_%H%M')}.md"
        draft_file.write_text(email_draft)
        log(f"Email draft saved: {draft_file}")

    # Schedule next activity
    next_act = parse_next_activity(notes)
    due_date = (datetime.now() + timedelta(days=next_act["due_days"])).strftime("%Y-%m-%d")

    act_result = pipedrive_api(token, "POST", "/activities", {
        "deal_id": deal_id,
        "type": next_act["type"],
        "subject": f"📞 FU {org_name} — {next_act['subject'][:50]}",
        "due_date": due_date,
        "due_time": "09:30",
        "user_id": 24403638,
        "done": 0,
    })
    if act_result:
        log(f"Next activity scheduled: {next_act['type']} on {due_date}")
    else:
        log("WARNING: Failed to schedule next activity")

    # Telegram notification
    notify_telegram(
        f"📞 Post-call zpracován: {deal.get('title','')}\n"
        f"📝 Poznámky → Pipedrive\n"
        f"📧 Email draft → {draft_file.name if email_draft else 'N/A'}\n"
        f"📅 Next: {next_act['type']} {due_date}"
    )

    log("Done!")
    return 0


if __name__ == "__main__":
    exit(main())
