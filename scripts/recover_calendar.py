#!/usr/bin/env python3
"""
Calendar Agent — Generates TODAY.md from real Google Calendar data
==================================================================
Uses Google Calendar MCP via Claude Code to pull actual events.
Falls back to Pipedrive priorities if calendar unavailable.

When calendar data isn't available, sends Telegram notification
asking Josef for manual input instead of generating fake data.

v2: Real calendar integration, no more fake placeholders (March 2026)
"""

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path("/Users/josefhofman/Clawdia")
OUTPUT = BASE / "calendar" / "TODAY.md"
TOMORROW_OUTPUT = BASE / "calendar" / "TOMORROW_PREP.md"
RECOVERY_LOG = BASE / "logs" / "recovery.log"
CALENDAR_CACHE = BASE / "calendar" / "events_cache.json"

CZECH_DAYS = {
    0: "Pondělí", 1: "Úterý", 2: "Středa",
    3: "Čtvrtek", 4: "Pátek", 5: "Sobota", 6: "Neděle",
}


def log_recovery(msg):
    RECOVERY_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(RECOVERY_LOG, "a") as f:
        f.write(f"[{ts}] [recover_calendar] {msg}\n")


def notify_telegram(message):
    """Notify Josef via Telegram when calendar agent needs input"""
    notify_script = BASE / "scripts" / "telegram_notify.py"
    if notify_script.exists():
        try:
            subprocess.run(
                ["python3", str(notify_script), "uncertain", "kalendar", message],
                capture_output=True, timeout=10,
            )
        except Exception:
            pass


def load_cached_events():
    """Load events from cache file (written by MCP integration or manual input)"""
    if not CALENDAR_CACHE.exists():
        return None
    try:
        data = json.loads(CALENDAR_CACHE.read_text())
        cached_at = data.get("cached_at", "")
        if cached_at:
            cached_time = datetime.fromisoformat(cached_at)
            # Cache valid for 4 hours
            if (datetime.now() - cached_time).total_seconds() > 14400:
                return None
        return data.get("events", [])
    except (json.JSONDecodeError, ValueError):
        return None


def get_scoring_priorities():
    """Pull top deals from DEAL_SCORING.md for today's call list"""
    scoring = BASE / "pipedrive" / "DEAL_SCORING.md"
    if scoring.exists() and scoring.stat().st_size > 100:
        content = scoring.read_text()
        priorities = []
        for line in content.splitlines():
            stripped = line.strip()
            if stripped and (stripped.startswith("1.") or stripped.startswith("2.") or stripped.startswith("3.")):
                priorities.append(stripped)
            if len(priorities) >= 3:
                break
        return priorities
    return []


def get_stale_deal_count():
    """Count stale deals for urgency indication"""
    stale = BASE / "pipedrive" / "STALE_DEALS.md"
    if stale.exists():
        content = stale.read_text()
        return content.count("- **")
    return 0


def get_pending_drafts_count():
    """Count pending email drafts"""
    drafts = BASE / "drafts"
    if drafts.exists():
        return len(list(drafts.glob("*.json")))
    return 0


def format_event(event):
    """Format a calendar event for display"""
    start = event.get("start", {})
    end = event.get("end", {})
    summary = event.get("summary", "Bez názvu")
    location = event.get("location", "")

    start_time = ""
    end_time = ""

    if start.get("dateTime"):
        st = datetime.fromisoformat(start["dateTime"])
        start_time = st.strftime("%H:%M")
    if end.get("dateTime"):
        et = datetime.fromisoformat(end["dateTime"])
        end_time = et.strftime("%H:%M")

    time_str = f"{start_time}-{end_time}" if start_time and end_time else "celý den"
    loc_str = f" 📍 {location}" if location else ""
    attendees = event.get("numAttendees", 0)
    att_str = f" ({attendees} lidí)" if attendees > 1 else ""

    return f"| {time_str} | {summary}{att_str} | {loc_str} |"


def generate_today(events=None):
    """Generate TODAY.md from real calendar events + pipeline data"""
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    day_name = CZECH_DAYS.get(now.weekday(), "")
    time_str = now.strftime("%H:%M")
    is_weekend = now.weekday() >= 5

    sections = []
    sections.append(f"# {day_name} {date_str}")

    if is_weekend:
        sections.append("\n## Weekend")
        sections.append("- Žádné naplánované sales bloky")
        sections.append("- Volitelně: review pipeline, plán na příští týden")

        # Still show pipeline context even on weekends
        stale_count = get_stale_deal_count()
        if stale_count > 0:
            sections.append(f"\n> ⚠️ {stale_count} stale dealů čeká na follow-up v pondělí")

    else:
        # ── CALENDAR EVENTS ──
        if events:
            sections.append("\n## Kalendář")
            sections.append("| Čas | Co | Kde |")
            sections.append("|-----|-----|-----|")
            for event in sorted(events, key=lambda e: e.get("start", {}).get("dateTime", "")):
                sections.append(format_event(event))
        else:
            sections.append("\n## Kalendář")
            sections.append("⚠️ **Nemám přístup ke kalendáři** — zkontroluj ručně Google Calendar")
            notify_telegram(
                "Nemám aktuální data z Google Calendar. "
                "Můžeš mi říct co máš dnes v plánu?"
            )

        # ── TOP PRIORITIES ──
        sections.append("\n## Top 3 priority dne")
        scoring_priorities = get_scoring_priorities()
        if scoring_priorities:
            for p in scoring_priorities:
                sections.append(p)
        else:
            sections.append("1. Zkontroluj `pipedrive/DEAL_SCORING.md`")
            sections.append("2. Projdi stale dealy")
            sections.append("3. Follow-up na pending emaily")

        # ── STALE DEALS ──
        stale_count = get_stale_deal_count()
        if stale_count > 0:
            sections.append(f"\n> ⚠️ **{stale_count} stale dealů** — follow-up needed!")

        # ── PENDING DRAFTS ──
        drafts_count = get_pending_drafts_count()
        if drafts_count > 0:
            sections.append(f"\n> ✍️ **{drafts_count} email draftů** ke kontrole v `drafts/`")

        # ── ADHD FOCUS BLOCKS ──
        sections.append("\n## Focus bloky (ADHD)")

        # Calculate free blocks from events
        if events:
            busy_times = []
            for event in events:
                start = event.get("start", {}).get("dateTime")
                end = event.get("end", {}).get("dateTime")
                if start and end:
                    busy_times.append((
                        datetime.fromisoformat(start),
                        datetime.fromisoformat(end),
                    ))
            busy_times.sort()

            # Find gaps > 45 min for focus blocks
            work_start = now.replace(hour=8, minute=0, second=0, microsecond=0)
            work_end = now.replace(hour=17, minute=30, second=0, microsecond=0)
            current = max(work_start, now)

            focus_blocks = []
            for busy_start, busy_end in busy_times:
                if busy_start > current and (busy_start - current).total_seconds() >= 2700:
                    focus_blocks.append((current, busy_start))
                current = max(current, busy_end)
            if work_end > current and (work_end - current).total_seconds() >= 2700:
                focus_blocks.append((current, work_end))

            if focus_blocks:
                for start, end in focus_blocks[:4]:
                    duration = int((end - start).total_seconds() / 60)
                    sections.append(
                        f"- **{start.strftime('%H:%M')}-{end.strftime('%H:%M')}** "
                        f"({duration} min) — volný blok pro deep work"
                    )
            else:
                sections.append("- ❌ Dnes nemáš žádný volný blok > 45 min")
                sections.append("- Zkus přesunout nebo zkrátit meeting")
        else:
            sections.append("- 08:00-10:45 — Prospecting (sacred time, žádné meetingy)")
            sections.append("- 15:30-16:30 — Creative blok")

    sections.append(f"\n---\n*Aktualizováno: {now.strftime('%H:%M')}*")
    return "\n".join(sections)


def main():
    try:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)

        # Try to load cached calendar events
        events = load_cached_events()

        content = generate_today(events)
        OUTPUT.write_text(content)
        log_recovery(f"SUCCESS — wrote {len(content)}B to {OUTPUT}")
        print(f"OK: TODAY.md updated ({len(content)}B)")
        return 0
    except Exception as e:
        log_recovery(f"FAILED — {e}")
        print(f"ERROR: {e}", flush=True)
        return 1


if __name__ == "__main__":
    exit(main())
