#!/usr/bin/env python3
"""
Fathom → Pipedrive Sync — stahuje transkripty a summary z Fathom AI,
páruje je s Pipedrive dealy a zapisuje jako poznámky.

Pro každý sales call z Fathom:
1. Stáhne transcript + summary přes Fathom API
2. Najde odpovídající deal v Pipedrive (podle emailu účastníka)
3. Zkontroluje, jestli už tam transcript je
4. Zapíše transcript jako poznámku
5. Vygeneruje detailní post-call summary přes Claude CLI
6. Zapíše summary jako PINNED poznámku

Usage:
  python3 scripts/fathom_sync.py                    # sync all new meetings
  python3 scripts/fathom_sync.py --list              # list all Fathom meetings
  python3 scripts/fathom_sync.py --deal 360          # sync specific deal
  python3 scripts/fathom_sync.py --recording 123     # sync specific recording
  python3 scripts/fathom_sync.py --dry-run           # preview without writing
  python3 scripts/fathom_sync.py --days 7            # only last N days
"""

import json
import os
import sys
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.paths import WORKSPACE, LOGS_DIR
from lib.secrets import load_secrets
from lib.notifications import notify_telegram
from lib.pipedrive import pipedrive_api, fathom_api

LOG_FILE = LOGS_DIR / "fathom-sync.log"
SYNC_STATE_FILE = WORKSPACE / "knowledge" / "fathom_sync_state.json"


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")



def load_sync_state():
    """Load previously synced recording IDs."""
    if SYNC_STATE_FILE.exists():
        return json.loads(SYNC_STATE_FILE.read_text())
    return {"synced_recordings": [], "last_sync": None}


def save_sync_state(state):
    """Save sync state."""
    SYNC_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["last_sync"] = datetime.now().isoformat()
    SYNC_STATE_FILE.write_text(json.dumps(state, indent=2))


def list_fathom_meetings(api_key, created_after=None):
    """List all meetings from Fathom with pagination."""
    meetings = []
    cursor = None
    params = {
        "include_summary": "true",
        "include_action_items": "true",
    }
    if created_after:
        params["created_after"] = created_after

    while True:
        if cursor:
            params["cursor"] = cursor
        result = fathom_api(api_key, "/meetings", params)
        if not result:
            break
        items = result.get("items", [])
        meetings.extend(items)
        cursor = result.get("next_cursor")
        if not cursor:
            break

    return meetings


def get_transcript(api_key, recording_id):
    """Get full transcript for a recording."""
    result = fathom_api(api_key, f"/recordings/{recording_id}/transcript")
    if result:
        return result.get("transcript", [])
    return []


def is_sales_call(meeting):
    """Filter: is this an external sales call?"""
    invitees = meeting.get("calendar_invitees", [])
    has_external = any(i.get("is_external", False) for i in invitees)
    if not has_external:
        return False

    # Skip internal meetings by title
    title = (meeting.get("title") or meeting.get("meeting_title") or "").lower()
    skip_words = [
        "stand up", "standup", "stand-up", "weekly", "okrs",
        "product demo", "internal", "team sync", "1:1", "1on1",
        "retro", "planning", "sprint", "fathom demo",
    ]
    if any(sw in title for sw in skip_words):
        return False

    return True


def match_meeting_to_deal(meeting, token):
    """Match Fathom meeting to Pipedrive deal by invitee email."""
    invitees = meeting.get("calendar_invitees", [])

    for inv in invitees:
        if not inv.get("is_external", False):
            continue
        email = inv.get("email", "")
        if not email:
            continue

        # Search person by email in Pipedrive
        result = pipedrive_api(token, "GET", "/persons/search", {
            "term": email, "fields": "email", "limit": "1",
        })
        if result and result.get("items"):
            person_id = result["items"][0].get("item", {}).get("id")
            if person_id:
                person_deals = pipedrive_api(token, "GET", f"/persons/{person_id}/deals", {
                    "status": "all_not_deleted", "limit": "5",
                })
                if person_deals:
                    return person_deals[0].get("id"), email

    # Fallback: search by name
    for inv in invitees:
        if not inv.get("is_external", False):
            continue
        name = inv.get("name", "")
        if not name or len(name) < 3:
            continue
        parts = name.split()
        last = parts[-1] if parts else ""
        if len(last) < 3:
            continue

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
                        return pd[0].get("id"), inv.get("email", "")

    return None, None


def deal_has_fathom_transcript(token, deal_id, recording_id):
    """Check if deal already has this Fathom transcript."""
    notes = pipedrive_api(token, "GET", f"/deals/{deal_id}/notes", {
        "limit": "20",
    })
    if not notes:
        return False

    rid_str = str(recording_id)
    for n in notes:
        content = n.get("content", "") or ""
        if rid_str in content and ("fathom" in content.lower() or "přepis" in content.lower()):
            return True
    return False


def format_transcript_html(meeting, transcript):
    """Format Fathom transcript as HTML for Pipedrive note."""
    title = meeting.get("title") or meeting.get("meeting_title") or ""
    created = meeting.get("created_at", "")[:10]
    recording_id = meeting.get("recording_id", "")
    url = meeting.get("url", "")
    share_url = meeting.get("share_url", "")

    start = meeting.get("recording_start_time", "")
    end = meeting.get("recording_end_time", "")
    duration_min = ""
    if start and end:
        try:
            s = datetime.fromisoformat(start.replace("Z", "+00:00"))
            e = datetime.fromisoformat(end.replace("Z", "+00:00"))
            duration_min = f"{(e - s).seconds // 60} min"
        except (ValueError, TypeError):
            pass

    invitees = ", ".join(
        f"{i.get('name', '')} ({i.get('email', '')})"
        for i in meeting.get("calendar_invitees", [])
        if i.get("name")
    )

    lines = [
        f"<h2>📝 Kompletní přepis — Fathom #{recording_id}</h2>",
        f"<p><b>Meeting:</b> {title}</p>",
        f"<p><b>Datum:</b> {created} | <b>Délka:</b> {duration_min} | "
        f"<b>Segmentů:</b> {len(transcript)}</p>",
        f"<p><b>Účastníci:</b> {invitees}</p>",
    ]
    if share_url:
        lines.append(f'<p><b>Fathom link:</b> <a href="{share_url}">{share_url}</a></p>')
    lines.append("<hr>")

    for seg in transcript:
        speaker = seg.get("speaker", {}).get("display_name", "?")
        text = seg.get("text", "")
        ts = seg.get("timestamp", "")
        lines.append(f"<p><b>[{ts}] {speaker}:</b> {text}</p>")

    return "\n".join(lines)


def generate_post_call_summary(meeting, transcript, deal, token):
    """Generate detailed SPIN-style post-call summary using Claude CLI."""
    title = meeting.get("title") or meeting.get("meeting_title") or ""
    created = meeting.get("created_at", "")[:10]
    recording_id = meeting.get("recording_id", "")

    start = meeting.get("recording_start_time", "")
    end = meeting.get("recording_end_time", "")
    duration_min = ""
    if start and end:
        try:
            s = datetime.fromisoformat(start.replace("Z", "+00:00"))
            e = datetime.fromisoformat(end.replace("Z", "+00:00"))
            duration_min = f"{(e - s).seconds // 60}"
        except (ValueError, TypeError):
            pass

    deal_title = deal.get("title", "") if deal else ""
    org_name = deal.get("org_name", "") if deal else ""
    person_name = deal.get("person_name", "") if deal else ""

    invitees = ", ".join(
        i.get("name", "") for i in meeting.get("calendar_invitees", [])
        if i.get("name")
    )

    # Fathom summary if available
    fathom_summary = ""
    default_summary = meeting.get("default_summary")
    if default_summary and default_summary.get("markdown_formatted"):
        fathom_summary = f"\nFATHOM AI SUMMARY:\n{default_summary['markdown_formatted'][:1000]}"

    # Action items
    action_items = ""
    items = meeting.get("action_items", [])
    if items:
        action_items = "\nACTION ITEMS (from Fathom):\n" + "\n".join(
            f"- {a.get('text', '')}" for a in items[:10]
        )

    # Transcript text (limit to ~60 segments for context window)
    transcript_text = "\n".join(
        f"[{s.get('timestamp', '')}] {s.get('speaker', {}).get('display_name', '?')}: {s.get('text', '')}"
        for s in transcript[:60]
    )

    prompt = f"""Analyzuj tento prodejní hovor pro Behavera (Echo Pulse — měření spokojenosti zaměstnanců).
Piš ČESKY. Výstup formátuj jako HTML pro Pipedrive.

Meeting: {title}
Datum: {created} | Délka: {duration_min} min
Deal: {deal_title} | Firma: {org_name} | Kontakt: {person_name}
Účastníci: {invitees}
Fathom Recording ID: {recording_id}
{fathom_summary}
{action_items}

TRANSCRIPT:
{transcript_text[:6000]}

---

Vygeneruj detailní post-call summary v tomto formátu:

<h2>📋 Post-Call Summary — {person_name or title}</h2>
<p><b>Datum:</b> {created} | <b>Délka:</b> {duration_min} min | <b>Zdroj:</b> Fathom #{recording_id}</p>

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
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        result = subprocess.run(
            ["claude", "-p", "--model", "claude-sonnet-4-6",
             "--dangerously-skip-permissions"],
            input=prompt,
            capture_output=True, text=True, timeout=120,
            env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            log(f"Claude CLI error: rc={result.returncode}, stderr={result.stderr[:200]}")
    except Exception as e:
        log(f"Claude CLI error: {e}")

    # Fallback: use Fathom's own summary if available
    if fathom_summary:
        return (
            f"<h2>📋 Post-Call Summary — {person_name or title}</h2>"
            f"<p><b>Datum:</b> {created} | <b>Délka:</b> {duration_min} min | "
            f"<b>Zdroj:</b> Fathom #{recording_id} (auto-summary)</p>"
            f"<hr>{fathom_summary.replace(chr(10), '<br>')}"
        )
    return None


def main():
    secrets = load_secrets()
    token = secrets.get("PIPEDRIVE_API_TOKEN") or secrets.get("PIPEDRIVE_TOKEN")
    if not token:
        log("No Pipedrive token found in secrets")
        return 1

    fathom_key = secrets.get("FATHOM_API_KEY")
    if not fathom_key:
        log("No Fathom API key found in secrets")
        return 1

    list_mode = "--list" in sys.argv
    dry_run = "--dry-run" in sys.argv
    all_mode = "--all" in sys.argv
    specific_deal = None
    specific_recording = None
    days_back = None

    for i, arg in enumerate(sys.argv):
        if arg == "--deal" and i + 1 < len(sys.argv):
            specific_deal = int(sys.argv[i + 1])
        if arg == "--recording" and i + 1 < len(sys.argv):
            specific_recording = int(sys.argv[i + 1])
        if arg == "--days" and i + 1 < len(sys.argv):
            days_back = int(sys.argv[i + 1])

    # Default: last 30 days
    created_after = None
    if days_back:
        created_after = (datetime.now() - timedelta(days=days_back)).isoformat() + "Z"
    elif not all_mode:
        created_after = (datetime.now() - timedelta(days=30)).isoformat() + "Z"

    log("Fetching meetings from Fathom...")
    meetings = list_fathom_meetings(fathom_key, created_after)
    log(f"Found {len(meetings)} meetings")

    if list_mode:
        for m in meetings:
            title = m.get("title") or m.get("meeting_title") or ""
            created = m.get("created_at", "")[:10]
            rid = m.get("recording_id", "")
            invitees = [i.get("name", "") for i in m.get("calendar_invitees", [])]
            external = any(i.get("is_external") for i in m.get("calendar_invitees", []))
            ext_mark = "EXT" if external else "INT"
            has_summary = "SUM" if m.get("default_summary") else "   "
            print(f"  {created} | rid:{rid:>10} | {ext_mark} | {has_summary} | {title[:45]:45s} | {str(invitees)[:50]}")
        return 0

    # Load sync state
    state = load_sync_state()
    synced_rids = set(state.get("synced_recordings", []))

    synced = 0
    errors = 0

    for meeting in meetings:
        rid = meeting.get("recording_id")
        title = meeting.get("title") or meeting.get("meeting_title") or ""

        # Skip already synced
        if rid in synced_rids and not specific_recording:
            continue

        # Filter specific recording
        if specific_recording and rid != specific_recording:
            continue

        # Filter external sales calls
        if not is_sales_call(meeting) and not specific_recording:
            continue

        log(f"Processing: {title} (rid:{rid})")

        # Match to Pipedrive deal
        deal_id, matched_email = match_meeting_to_deal(meeting, token)
        if not deal_id:
            log(f"  No Pipedrive deal match found — skipping")
            continue

        if specific_deal and deal_id != specific_deal:
            continue

        # Check if already synced to this deal
        if deal_has_fathom_transcript(token, deal_id, rid):
            log(f"  Transcript already exists for deal {deal_id}")
            synced_rids.add(rid)
            continue

        deal = pipedrive_api(token, "GET", f"/deals/{deal_id}")
        org = deal.get("org_name", "") if deal else ""
        log(f"  Matched → deal {deal_id} ({org}) via {matched_email}")

        if dry_run:
            log(f"  [DRY RUN] Would sync transcript + summary")
            continue

        # Get full transcript
        log(f"  Fetching transcript...")
        transcript = get_transcript(fathom_key, rid)
        if not transcript:
            log(f"  WARNING: No transcript available")
            continue
        log(f"  Got {len(transcript)} segments")

        # Write transcript to Pipedrive
        transcript_html = format_transcript_html(meeting, transcript)
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

        # Generate and write post-call summary
        log(f"  Generating post-call summary...")
        summary = generate_post_call_summary(meeting, transcript, deal, token)
        if summary:
            sum_note = pipedrive_api(token, "POST", "/notes", {
                "deal_id": deal_id,
                "content": summary,
                "pinned_to_deal_flag": 1,
            })
            if sum_note:
                log(f"  Summary written and PINNED (note {sum_note.get('id', '?')})")
                synced += 1
            else:
                log(f"  ERROR: Failed to write summary")
                errors += 1
        else:
            log(f"  WARNING: Summary generation failed, transcript still saved")
            synced += 1

        # Mark as synced
        synced_rids.add(rid)

    # Save sync state
    state["synced_recordings"] = list(synced_rids)
    save_sync_state(state)

    log(f"Done: {synced} synced, {errors} errors")

    if synced > 0 and not dry_run:
        notify_telegram(
            f"🎙️ Fathom Sync: {synced} hovorů synchronizováno do Pipedrive\n"
            f"Celkem synced: {len(synced_rids)} recordings"
        )

    return 0


if __name__ == "__main__":
    exit(main())
