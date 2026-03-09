#!/usr/bin/env python3
"""
Motivational Nudge System — ADHD-friendly dopamine hooks přes Telegram.

Posílá krátké, cílené notifikace v průběhu dne:
- Ranní kickstart (7:00) — "3 quick wins čekají"
- Mid-morning check (10:00) — "Zavolal jsi už? 1 call = 5min"
- Lunch break win (12:00) — "Polovina dne za tebou, tady je score"
- Afternoon push (15:00) — "Ještě 2 cally a máš splněno"
- Evening wrap (18:00) — "Co jsi dnes udělal? Quick recap"

Sleduje:
- Počet callů dnes (z Pipedrive aktivit)
- Pipeline value změny
- Streak (kolik dnů po sobě měl aktivitu)
- Quick win opportunities

Usage:
  python3 scripts/motivational_nudge.py morning     # ranní kickstart
  python3 scripts/motivational_nudge.py midday      # polední check
  python3 scripts/motivational_nudge.py afternoon   # odpolední push
  python3 scripts/motivational_nudge.py evening     # večerní recap
  python3 scripts/motivational_nudge.py auto        # auto-detect by time
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

LOG_FILE = LOGS_DIR / "motivational-nudge.log"
STREAK_FILE = WORKSPACE / "knowledge" / "streak.json"

QUOTES = [
    "Každý NE tě přibližuje k ANO.",
    "5 minut na telefonu > 2 hodiny na emailu.",
    "Nejhorší call je ten, co neuděláš.",
    "Pipeline je jako svaly — roste jen když trénuješ.",
    "Close rate 15% = každý 7. call = deal.",
    "Prodej není talent, je to systém. A ty ho máš.",
    "1 call denně = 20 callů za měsíc = 3 dealy.",
    "Nikdo nevyhraje tím, že bude čekat na správný moment.",
    "Tvůj konkurent zrovna volá tvého leada.",
    "Dneska je ten den, kdy se to změní.",
]


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def get_today_activities(token):
    """Get today's completed activities."""
    today = datetime.now().strftime("%Y-%m-%d")
    activities = pipedrive_api(token, "GET", "/activities", {
        "user_id": "24403638",
        "start_date": today,
        "end_date": today,
        "done": "1",
    })
    return activities or []


def get_today_scheduled(token):
    """Get today's scheduled (not done) activities."""
    today = datetime.now().strftime("%Y-%m-%d")
    activities = pipedrive_api(token, "GET", "/activities", {
        "user_id": "24403638",
        "start_date": today,
        "end_date": today,
        "done": "0",
    })
    return activities or []


def get_streak():
    """Get current activity streak."""
    if not STREAK_FILE.exists():
        return {"streak": 0, "last_active": "", "best_streak": 0}
    try:
        return json.loads(STREAK_FILE.read_text())
    except Exception:
        return {"streak": 0, "last_active": "", "best_streak": 0}


def update_streak(had_activity_today):
    """Update streak counter."""
    data = get_streak()
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    if had_activity_today:
        if data.get("last_active") == yesterday:
            data["streak"] = data.get("streak", 0) + 1
        elif data.get("last_active") != today:
            data["streak"] = 1
        data["last_active"] = today
        data["best_streak"] = max(data.get("best_streak", 0), data["streak"])
    elif data.get("last_active") not in (today, yesterday):
        data["streak"] = 0

    STREAK_FILE.parent.mkdir(parents=True, exist_ok=True)
    STREAK_FILE.write_text(json.dumps(data, indent=2))
    return data


def get_quick_wins(token):
    """Find quick win opportunities — warm deals with upcoming next steps."""
    deals = pipedrive_get_all(token, "/deals", {
        "status": "open",
        "user_id": "24403638",
    })

    quick_wins = []
    now = datetime.now()
    for d in deals:
        stage = d.get("stage_order_nr", 0)
        value = d.get("value", 0) or 0
        next_date = d.get("next_activity_date", "")
        last_date = d.get("last_activity_date", "")
        org = d.get("org_name", "") or d.get("title", "")

        days_silent = 999
        if last_date:
            try:
                days_silent = (now - datetime.strptime(last_date, "%Y-%m-%d")).days
            except ValueError:
                pass

        # Quick win = warm deal, recent contact, good stage
        if stage >= 3 and days_silent <= 7 and value > 0:
            quick_wins.append({"org": org, "value": value, "days": days_silent})
        elif stage >= 2 and days_silent <= 3:
            quick_wins.append({"org": org, "value": value, "days": days_silent})

    quick_wins.sort(key=lambda x: x["days"])
    return quick_wins[:5]


def morning_nudge(token):
    """7:00 — Morning kickstart."""
    scheduled = get_today_scheduled(token)
    quick_wins = get_quick_wins(token)
    streak = get_streak()
    quote_idx = datetime.now().day % len(QUOTES)

    calls = [a for a in scheduled if a.get("type") in ("call", "meeting")]

    lines = ["Dobré ráno! Denní kickstart:\n"]

    if calls:
        lines.append(f"📞 {len(calls)} callů naplánovaných na dnes")
        for c in calls[:3]:
            org = c.get("org_name", "") or c.get("subject", "?")
            lines.append(f"  → {org}")
    else:
        lines.append("📞 Žádné cally — přidej aspoň 3 z call listu!")

    if quick_wins:
        lines.append(f"\n🎯 {len(quick_wins)} quick winů:")
        for qw in quick_wins[:3]:
            lines.append(f"  💰 {qw['org'][:25]} ({qw['value']:,.0f} CZK)")

    if streak.get("streak", 0) > 1:
        lines.append(f"\n🔥 Streak: {streak['streak']} dnů po sobě!")
        if streak["streak"] >= streak.get("best_streak", 0):
            lines.append("  ⭐ Tvůj nejlepší streak ever!")

    lines.append(f"\n💪 {QUOTES[quote_idx]}")

    msg = "\n".join(lines)
    notify_telegram(msg)
    log(f"Morning nudge sent: {len(calls)} calls, {len(quick_wins)} quick wins")


def midday_nudge(token):
    """12:00 — Half-day check."""
    done = get_today_activities(token)
    scheduled = get_today_scheduled(token)
    streak = get_streak()

    calls_done = [a for a in done if a.get("type") in ("call", "meeting")]
    calls_left = [a for a in scheduled if a.get("type") in ("call", "meeting")]
    emails_done = [a for a in done if a.get("type") == "email"]

    lines = ["Polovina dne — quick update:\n"]

    if calls_done:
        lines.append(f"✅ {len(calls_done)} callů hotovo")
    else:
        lines.append("⚠️ Zatím 0 callů — stihneš ještě odpoledne!")

    if emails_done:
        lines.append(f"📧 {len(emails_done)} emailů odesláno")

    if calls_left:
        lines.append(f"\n📋 Zbývá: {len(calls_left)} callů")
        for c in calls_left[:3]:
            org = c.get("org_name", "") or c.get("subject", "?")
            lines.append(f"  → {org}")

    total = len(calls_done) + len(emails_done)
    if total >= 5:
        lines.append("\n🏆 Super tempo! Drž to.")
    elif total >= 2:
        lines.append("\n👍 Dobrý start, odpoledne přidej.")
    else:
        lines.append("\n⏰ Ještě máš čas — jeden call = 5 minut.")

    msg = "\n".join(lines)
    notify_telegram(msg)
    log(f"Midday nudge: {len(calls_done)} calls done, {len(calls_left)} left")


def afternoon_nudge(token):
    """15:00 — Afternoon push."""
    done = get_today_activities(token)
    scheduled = get_today_scheduled(token)
    quick_wins = get_quick_wins(token)

    calls_done = [a for a in done if a.get("type") in ("call", "meeting")]
    calls_left = [a for a in scheduled if a.get("type") in ("call", "meeting")]

    lines = []

    if not calls_done and not calls_left:
        lines.append("🔴 Ani jeden call dnes!")
        lines.append("Stačí 1 call — 5 minut, 1 quick win:")
        if quick_wins:
            qw = quick_wins[0]
            lines.append(f"  💰 {qw['org'][:25]} ({qw['value']:,.0f} CZK, {qw['days']}d)")
        lines.append("\nProstě zvedni telefon. Teď.")
    elif calls_left:
        lines.append(f"📞 Ještě {len(calls_left)} callů na dnešek:")
        for c in calls_left[:3]:
            org = c.get("org_name", "") or c.get("subject", "?")
            lines.append(f"  → {org}")
        lines.append(f"\n✅ Už máš {len(calls_done)} hotových. Dokonči to!")
    else:
        lines.append(f"✅ Všechny cally hotové! ({len(calls_done)} dnes)")
        lines.append("💡 Bonus: napiš 1 follow-up email")

    msg = "\n".join(lines)
    notify_telegram(msg)
    log(f"Afternoon nudge: {len(calls_done)} done, {len(calls_left)} left")


def evening_nudge(token):
    """18:00 — Evening wrap-up."""
    done = get_today_activities(token)
    calls_done = [a for a in done if a.get("type") in ("call", "meeting")]
    emails_done = [a for a in done if a.get("type") == "email"]

    had_activity = len(done) > 0
    streak = update_streak(had_activity)

    # Calculate simple score
    score = len(calls_done) * 20 + len(emails_done) * 10 + min(len(done), 10) * 5
    score = min(score, 100)

    lines = [f"Denní recap ({datetime.now().strftime('%d.%m')}):\n"]

    if score >= 80:
        lines.append(f"🏆 BEAST MODE — {score}/100 bodů!")
    elif score >= 50:
        lines.append(f"👍 Solidní den — {score}/100 bodů")
    elif score >= 20:
        lines.append(f"🟡 Mohl být lepší — {score}/100 bodů")
    else:
        lines.append(f"🔴 Tichý den — {score}/100 bodů")

    lines.append(f"\n📞 {len(calls_done)} callů")
    lines.append(f"📧 {len(emails_done)} emailů")
    lines.append(f"📊 Celkem {len(done)} aktivit")

    if streak["streak"] > 0:
        lines.append(f"\n🔥 Streak: {streak['streak']} dnů")
        if streak["streak"] >= 5:
            lines.append("  ⭐ 5+ dnů v řadě — jsi mašina!")
        elif streak["streak"] >= 3:
            lines.append("  💪 3+ dnů — momentum roste!")

    # Tomorrow preview
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
    tomorrow_acts = pipedrive_api(token, "GET", "/activities", {
        "user_id": "24403638",
        "start_date": tomorrow,
        "end_date": tomorrow,
        "done": "0",
    }) or []
    if tomorrow_acts:
        lines.append(f"\n📅 Zítra: {len(tomorrow_acts)} aktivit naplánovaných")

    lines.append("\nDobrý večer! Odpočiň si, Clawdia pracuje přes noc.")

    msg = "\n".join(lines)
    notify_telegram(msg)
    log(f"Evening nudge: score {score}, streak {streak['streak']}, {len(done)} activities")


def auto_detect(token):
    """Auto-detect which nudge to send based on current time."""
    hour = datetime.now().hour
    if hour < 9:
        morning_nudge(token)
    elif hour < 13:
        midday_nudge(token)
    elif hour < 17:
        afternoon_nudge(token)
    else:
        evening_nudge(token)


def main():
    secrets = load_secrets()
    token = secrets.get("PIPEDRIVE_API_TOKEN") or secrets.get("PIPEDRIVE_TOKEN")
    if not token:
        log("No Pipedrive token")
        return 1

    mode = sys.argv[1] if len(sys.argv) > 1 else "auto"

    if mode == "morning":
        morning_nudge(token)
    elif mode == "midday":
        midday_nudge(token)
    elif mode == "afternoon":
        afternoon_nudge(token)
    elif mode == "evening":
        evening_nudge(token)
    elif mode == "auto":
        auto_detect(token)
    else:
        print(f"Unknown mode: {mode}")
        print("Usage: motivational_nudge.py [morning|midday|afternoon|evening|auto]")
        return 1

    return 0


if __name__ == "__main__":
    exit(main())
