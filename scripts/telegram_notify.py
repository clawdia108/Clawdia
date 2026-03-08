#!/usr/bin/env python3
"""
Telegram Notification System for Clawdia Agents
=================================================
Direct line from every agent to Josef's Telegram.

Usage:
    # Send a message
    python3 telegram_notify.py send "Zpráva pro Josefa"

    # Agent asks for help (high priority, expects response)
    python3 telegram_notify.py ask "obchodak" "Mám 3 dealy se stejným skóre, který mám upřednostnit?"

    # Agent reports uncertainty
    python3 telegram_notify.py uncertain "textar" "Email pro CEO Kebooly — mám být formální nebo casual?"

    # System alert
    python3 telegram_notify.py alert "Orchestrátor spadl, recovery failed"

    # From Python:
    from telegram_notify import notify, ask_josef, agent_uncertain, system_alert
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/josefhofman/Clawdia")
SECRETS_FILE = BASE / ".secrets" / "ALL_CREDENTIALS.env"
TELEGRAM_LOG = BASE / "logs" / "telegram.log"
PENDING_QUESTIONS = BASE / "bus" / "telegram-pending"

# Agent display names for messages
AGENT_NAMES = {
    "spojka": "🔗 Spojka",
    "obchodak": "📊 Obchodák",
    "postak": "📮 Pošťák",
    "strateg": "🎯 Stratég",
    "kalendar": "📅 Kalendář",
    "kontrolor": "✅ Kontrolor",
    "archivar": "📚 Archivář",
    "udrzbar": "🔧 Údržbář",
    "textar": "✍️ Textař",
    "hlidac": "👁️ Hlídač",
    "planovac": "⏰ Plánovač",
    "vyvojar": "💻 Vývojář",
    "system": "⚙️ Systém",
}


def tlog(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    TELEGRAM_LOG.parent.mkdir(exist_ok=True)
    with open(TELEGRAM_LOG, "a") as f:
        f.write(f"[{ts}] [{level}] {msg}\n")


def load_telegram_config():
    """Load Telegram bot token and chat ID from secrets"""
    config = {"token": None, "chat_id": None}
    if not SECRETS_FILE.exists():
        return config
    for line in SECRETS_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            config["token"] = line.split("=", 1)[1].strip().strip('"').strip("'")
        elif line.startswith("TELEGRAM_CHAT_ID="):
            config["chat_id"] = line.split("=", 1)[1].strip().strip('"').strip("'")
    return config


def send_telegram(message, parse_mode="Markdown"):
    """Send message to Josef's Telegram"""
    config = load_telegram_config()
    if not config["token"] or not config["chat_id"]:
        tlog("Telegram not configured (missing token or chat_id)", "WARN")
        # Fallback to macOS notification
        _macos_notify("Clawdia", message[:200])
        return False

    url = f"https://api.telegram.org/bot{config['token']}/sendMessage"
    payload = json.dumps({
        "chat_id": config["chat_id"],
        "text": message,
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    })

    try:
        result = subprocess.run(
            ["curl", "-s", "-m", "10", url,
             "-H", "content-type: application/json",
             "-d", payload],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data.get("ok"):
                tlog(f"Sent: {message[:80]}...")
                return True
            else:
                tlog(f"Telegram API error: {data.get('description', 'unknown')}", "ERROR")
        return False
    except Exception as e:
        tlog(f"Send failed: {e}", "ERROR")
        _macos_notify("Clawdia", message[:200])
        return False


def _macos_notify(title, message):
    """Fallback to macOS notification"""
    try:
        subprocess.run(
            ["osascript", "-e", f'display notification "{message}" with title "{title}"'],
            capture_output=True, timeout=5,
        )
    except Exception:
        pass


# ── PUBLIC API ───────────────────────────────────────

def notify(message):
    """Simple notification to Josef"""
    return send_telegram(message)


def agent_uncertain(agent_id, question, context=None):
    """Agent doesn't know what to do — asks Josef directly.
    This is the core ADHD-friendly feature: agents don't guess, they ask.
    """
    agent_name = AGENT_NAMES.get(agent_id, f"🤖 {agent_id}")
    msg = f"❓ *{agent_name} potřebuje tvůj vstup:*\n\n{question}"
    if context:
        msg += f"\n\n📋 Kontext: {context}"
    msg += f"\n\n⏰ {datetime.now().strftime('%H:%M')}"

    # Save pending question for tracking
    PENDING_QUESTIONS.mkdir(parents=True, exist_ok=True)
    q_file = PENDING_QUESTIONS / f"{agent_id}_{int(time.time())}.json"
    q_file.write_text(json.dumps({
        "agent": agent_id,
        "question": question,
        "context": context,
        "asked_at": datetime.now().isoformat(),
        "status": "pending",
    }, ensure_ascii=False, indent=2))

    return send_telegram(msg)


def ask_josef(agent_id, question, options=None):
    """Agent needs a decision from Josef. Can include options.
    For ADHD: options reduce decision fatigue — present max 3 choices.
    """
    agent_name = AGENT_NAMES.get(agent_id, f"🤖 {agent_id}")
    msg = f"🎯 *{agent_name} — rozhodnutí:*\n\n{question}"

    if options:
        msg += "\n"
        for i, opt in enumerate(options[:3], 1):
            msg += f"\n{i}. {opt}"

    msg += f"\n\n💬 Odpověz číslem nebo vlastní odpovědí"
    return send_telegram(msg)


def system_alert(message, severity="warning"):
    """System-level alert — always delivered regardless of focus time"""
    icons = {"critical": "🚨", "warning": "⚠️", "info": "ℹ️"}
    icon = icons.get(severity, "⚠️")
    msg = f"{icon} *Systémový alert:*\n\n{message}\n\n⏰ {datetime.now().strftime('%H:%M')}"
    return send_telegram(msg)


def daily_summary(stats):
    """End-of-day summary — ADHD dopamine hit for completed work"""
    msg = "📊 *Denní shrnutí Clawdia:*\n\n"

    if stats.get("drafts_generated"):
        msg += f"✍️ {stats['drafts_generated']} emailů napsáno\n"
    if stats.get("deals_scored"):
        msg += f"📊 {stats['deals_scored']} dealů oskórováno\n"
    if stats.get("tasks_completed"):
        msg += f"✅ {stats['tasks_completed']} úkolů splněno\n"
    if stats.get("score"):
        msg += f"🏆 Skóre dne: {stats['score']} bodů\n"
    if stats.get("streak"):
        msg += f"🔥 Streak: {stats['streak']} dní\n"

    msg += f"\n💪 Dobrá práce, Josefe."
    return send_telegram(msg)


def morning_nudge(top_actions):
    """Morning nudge — 3 things to do RIGHT NOW. ADHD-critical.
    No wall of text. No options. Just: do this, then this, then this.
    """
    msg = "🌅 *Dobré ráno. Tady je tvůj plán:*\n\n"
    for i, action in enumerate(top_actions[:3], 1):
        msg += f"*{i}.* {action}\n"
    msg += f"\n⏰ Start teď. Prvních 90 minut = sacred time."
    return send_telegram(msg)


def focus_interrupt(reason):
    """Only for truly urgent things during focus time.
    ADHD: interruptions are expensive. Use sparingly.
    """
    msg = f"🔴 *Přerušení focus time:*\n\n{reason}\n\n_(Omlouvám se za přerušení, tohle nemůže čekat.)_"
    return send_telegram(msg)


def deal_won_celebration(deal_name, value):
    """Celebrate a won deal — dopamine boost!"""
    msg = f"🎉🎉🎉\n\n*DEAL WON: {deal_name}*\nHodnota: {value}\n\n🏆 Jsi mašina, Josefe!"
    return send_telegram(msg)


# ── CLI ──────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: telegram_notify.py <command> [args]")
        print("Commands: send, ask, uncertain, alert, test")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "send" and len(sys.argv) > 2:
        notify(" ".join(sys.argv[2:]))

    elif cmd == "ask" and len(sys.argv) > 3:
        agent = sys.argv[2]
        question = " ".join(sys.argv[3:])
        ask_josef(agent, question)

    elif cmd == "uncertain" and len(sys.argv) > 3:
        agent = sys.argv[2]
        question = " ".join(sys.argv[3:])
        agent_uncertain(agent, question)

    elif cmd == "alert" and len(sys.argv) > 2:
        system_alert(" ".join(sys.argv[2:]))

    elif cmd == "test":
        print("Testing Telegram connection...")
        ok = notify("🧪 Clawdia test — Telegram funguje!")
        print(f"Result: {'OK' if ok else 'FAILED'}")
        if not ok:
            config = load_telegram_config()
            if not config["token"]:
                print("Missing TELEGRAM_BOT_TOKEN in .secrets/ALL_CREDENTIALS.env")
            if not config["chat_id"]:
                print("Missing TELEGRAM_CHAT_ID in .secrets/ALL_CREDENTIALS.env")

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)
