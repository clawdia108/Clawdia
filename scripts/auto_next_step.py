#!/usr/bin/env python3
"""
Auto Next-Step Generator — po každém hovoru automaticky vytvoří next step.

Analyzuje Fathom post-call summary a vytvoří odpovídající Pipedrive aktivitu:
- Call outcome ADVANCE → schedule follow-up meeting
- Call outcome CONTINUATION → schedule follow-up call
- Call outcome STALL → schedule re-engagement email
- No outcome → default follow-up in 3 days

Integrace:
- Volá se po fathom_sync.py v overnight_run.sh
- Čte Fathom action items + summary
- Vytváří Pipedrive aktivity s kontextem

Usage:
  python3 scripts/auto_next_step.py                # process recent calls
  python3 scripts/auto_next_step.py --deal 360     # specific deal
  python3 scripts/auto_next_step.py --dry-run      # preview only
  python3 scripts/auto_next_step.py --days 7       # last N days
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.paths import WORKSPACE, LOGS_DIR
from lib.secrets import load_secrets
from lib.notifications import notify_telegram
from lib.pipedrive import pipedrive_api, fathom_api

LOG_FILE = LOGS_DIR / "auto-next-step.log"
STATE_FILE = WORKSPACE / "knowledge" / "next_step_state.json"


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def next_business_day(days_ahead=1):
    """Get next business day N days ahead."""
    d = datetime.now().date() + timedelta(days=days_ahead)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.isoformat()


def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"processed_recordings": [], "last_run": None}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["last_run"] = datetime.now().isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2))


def match_meeting_to_deal(meeting, token):
    """Match Fathom meeting to Pipedrive deal by invitee email."""
    invitees = meeting.get("calendar_invitees", [])

    for inv in invitees:
        if not inv.get("is_external", False):
            continue
        email = inv.get("email", "")
        if not email:
            continue

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
                    return person_deals[0], email

    return None, None


def analyze_call_outcome(meeting):
    """Determine call outcome from Fathom data."""
    summary = meeting.get("default_summary", {})
    summary_text = (summary.get("markdown_formatted", "") or "").lower() if summary else ""
    action_items = meeting.get("action_items", [])
    action_text = " ".join(a.get("text", "").lower() for a in action_items)

    combined = f"{summary_text} {action_text}"

    # Detect outcome type
    advance_signals = [
        "demo", "pilot", "proposal", "nabídka", "zkouška", "test",
        "smlouva", "contract", "next meeting", "schůzka", "prezentace",
        "send proposal", "připravit nabídku",
    ]
    stall_signals = [
        "not interested", "no budget", "nemají zájem", "rozpočet",
        "later", "příští rok", "next year", "maybe", "zvážíme",
        "need to think", "rozmyslet",
    ]

    advance_count = sum(1 for s in advance_signals if s in combined)
    stall_count = sum(1 for s in stall_signals if s in combined)

    if advance_count >= 2:
        return "advance"
    elif stall_count >= 2:
        return "stall"
    elif action_items:
        return "continuation"
    else:
        return "unknown"


def determine_next_step(outcome, deal, meeting):
    """Determine the right next step based on call outcome."""
    org = deal.get("org_name") or deal.get("title", "?") if deal else "?"
    stage = deal.get("stage_order_nr", 0) if deal else 0
    action_items = meeting.get("action_items", [])

    if outcome == "advance":
        # Schedule follow-up meeting in 2-3 days
        subject = f"Follow-up meeting: {org[:30]}"
        if stage >= 4:
            subject = f"Proposal review: {org[:30]}"
        return {
            "subject": subject,
            "type": "meeting",
            "due_date": next_business_day(2),
            "note": "ADVANCE — domluvit schůzku / demo / pilot",
        }

    elif outcome == "stall":
        # Re-engagement email in 7 days
        return {
            "subject": f"Re-engage: {org[:30]} — check-in email",
            "type": "email",
            "due_date": next_business_day(7),
            "note": "STALL — poslat check-in za týden",
        }

    elif outcome == "continuation":
        # Follow up on action items in 3 days
        action_summary = ""
        if action_items:
            action_summary = action_items[0].get("text", "")[:60]
        return {
            "subject": f"Follow-up: {org[:30]} — {action_summary}" if action_summary else f"Follow-up: {org[:30]}",
            "type": "call",
            "due_date": next_business_day(3),
            "note": f"CONTINUATION — {action_summary}" if action_summary else "CONTINUATION — follow-up call",
        }

    else:
        # Default: follow-up call in 3 days
        return {
            "subject": f"Follow-up call: {org[:30]}",
            "type": "call",
            "due_date": next_business_day(3),
            "note": "Auto-generated next step",
        }


def deal_has_upcoming_activity(token, deal_id):
    """Check if deal already has an upcoming activity."""
    activities = pipedrive_api(token, "GET", f"/deals/{deal_id}/activities", {
        "done": "0", "limit": "5",
    })
    return bool(activities)


def create_next_step(token, deal_id, step_info):
    """Create the next step activity in Pipedrive."""
    activity = pipedrive_api(token, "POST", "/activities", {
        "deal_id": deal_id,
        "subject": step_info["subject"],
        "type": step_info["type"],
        "due_date": step_info["due_date"],
        "user_id": 24403638,
        "note": step_info.get("note", ""),
    })
    return activity


def main():
    secrets = load_secrets()
    token = secrets.get("PIPEDRIVE_API_TOKEN") or secrets.get("PIPEDRIVE_TOKEN")
    fathom_key = secrets.get("FATHOM_API_KEY")

    if not token or not fathom_key:
        log("Missing Pipedrive or Fathom token")
        return 1

    dry_run = "--dry-run" in sys.argv
    specific_deal = None
    days_back = 7

    for i, arg in enumerate(sys.argv):
        if arg == "--deal" and i + 1 < len(sys.argv):
            specific_deal = int(sys.argv[i + 1])
        if arg == "--days" and i + 1 < len(sys.argv):
            days_back = int(sys.argv[i + 1])

    # Load state
    state = load_state()
    processed = set(state.get("processed_recordings", []))

    # Fetch recent Fathom meetings
    created_after = (datetime.now() - timedelta(days=days_back)).isoformat() + "Z"
    log(f"Fetching Fathom meetings from last {days_back} days...")

    result = fathom_api(fathom_key, "/meetings", {
        "include_summary": "true",
        "include_action_items": "true",
        "created_after": created_after,
    })

    if not result:
        log("No Fathom data")
        return 0

    meetings = result.get("items", [])
    log(f"Found {len(meetings)} meetings")

    created = 0
    skipped = 0

    for meeting in meetings:
        rid = meeting.get("recording_id")
        title = meeting.get("title") or meeting.get("meeting_title") or ""

        # Skip already processed
        if rid in processed:
            continue

        # Skip internal meetings
        invitees = meeting.get("calendar_invitees", [])
        has_external = any(i.get("is_external", False) for i in invitees)
        if not has_external:
            continue

        log(f"Processing: {title} (rid:{rid})")

        # Match to Pipedrive deal
        deal, matched_email = match_meeting_to_deal(meeting, token)
        if not deal:
            log(f"  No Pipedrive match — skipping")
            processed.add(rid)
            continue

        deal_id = deal.get("id")
        org = deal.get("org_name") or deal.get("title", "?")

        if specific_deal and deal_id != specific_deal:
            continue

        # Check if deal already has upcoming activity
        if deal_has_upcoming_activity(token, deal_id):
            log(f"  {org} already has upcoming activity — skipping")
            processed.add(rid)
            skipped += 1
            continue

        # Analyze call outcome
        outcome = analyze_call_outcome(meeting)
        log(f"  Outcome: {outcome}")

        # Determine next step
        step = determine_next_step(outcome, deal, meeting)
        log(f"  Next step: {step['type']} — {step['subject'][:50]}")

        if dry_run:
            log(f"  [DRY RUN] Would create: {step['subject']}")
        else:
            result = create_next_step(token, deal_id, step)
            if result:
                created += 1
                log(f"  ✅ Activity created (id: {result.get('id', '?')})")

                # Add note about auto-generated step
                pipedrive_api(token, "POST", "/notes", {
                    "deal_id": deal_id,
                    "content": (
                        f"<p><b>🤖 Auto Next-Step</b> ({outcome.upper()})</p>"
                        f"<p>{step['note']}</p>"
                        f"<p><i>Vytvořeno automaticky po hovoru {title[:40]}</i></p>"
                    ),
                })
            else:
                log(f"  ❌ Failed to create activity")

        processed.add(rid)

    # Save state
    state["processed_recordings"] = list(processed)
    save_state(state)

    log(f"\nDone: {created} next steps created, {skipped} skipped (already have activity)")

    if created > 0 and not dry_run:
        notify_telegram(
            f"🎯 Auto Next-Step: {created} aktivit vytvořeno\n"
            f"Z {len(meetings)} hovorů, {skipped} přeskočeno"
        )

    return 0


if __name__ == "__main__":
    exit(main())
