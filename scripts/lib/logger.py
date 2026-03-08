"""Unified logging for Clawdia scripts."""

from datetime import datetime
from pathlib import Path
from .paths import LOGS_DIR


def make_logger(log_name):
    """Create a logger function that writes to logs/{log_name}.log."""
    log_file = LOGS_DIR / f"{log_name}.log"

    def log(msg, level="INFO"):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_file.parent.mkdir(exist_ok=True, parents=True)
        with open(log_file, "a") as f:
            f.write(f"[{ts}] [{level}] {msg}\n")

    return log
