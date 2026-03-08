"""Notification helpers — Telegram, etc."""

import subprocess
from .paths import WORKSPACE


def notify_telegram(message):
    """Send message via Telegram using telegram_notify.py."""
    script = WORKSPACE / "scripts" / "telegram_notify.py"
    if script.exists():
        try:
            subprocess.run(
                ["python3", str(script), "send", message],
                capture_output=True, timeout=15,
            )
        except Exception:
            pass
