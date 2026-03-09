"""Telegram notification tool — wraps scripts/lib/notifications.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from lib.notifications import notify_telegram

__all__ = ["notify_telegram", "send_alert"]


def send_alert(agent_name: str, level: str, message: str):
    """Send a structured alert via Telegram."""
    emoji = {"error": "🔴", "warn": "🟡", "info": "🟢"}.get(level, "📢")
    notify_telegram(f"{emoji} [{agent_name}] {message}")
