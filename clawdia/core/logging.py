"""Structured JSON logging with correlation IDs."""

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

from .config import LOGS_DIR

# Global correlation ID for this execution
_correlation_id = str(uuid.uuid4())[:8]


def set_correlation_id(cid: str):
    global _correlation_id
    _correlation_id = cid


def get_correlation_id() -> str:
    return _correlation_id


class StructuredLogger:
    """JSON-structured logger with agent context."""

    def __init__(self, name: str, log_file: str | None = None):
        self.name = name
        self.log_dir = LOGS_DIR
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / (log_file or f"{name}.log")
        self.metrics = {"calls": 0, "errors": 0, "tokens": 0}

    def _emit(self, level: str, msg: str, **extra):
        entry = {
            "ts": datetime.now().isoformat(),
            "level": level,
            "agent": self.name,
            "cid": _correlation_id,
            "msg": msg,
        }
        if extra:
            entry["data"] = extra

        # Console output (human-readable)
        print(f"[{entry['ts'][:19]}] [{self.name}] {msg}")

        # File output (JSON)
        try:
            with open(self.log_file, "a") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def info(self, msg: str, **kw):
        self._emit("INFO", msg, **kw)

    def warn(self, msg: str, **kw):
        self._emit("WARN", msg, **kw)

    def error(self, msg: str, **kw):
        self.metrics["errors"] += 1
        self._emit("ERROR", msg, **kw)

    def track_tokens(self, count: int):
        self.metrics["tokens"] += count

    def track_api_call(self):
        self.metrics["calls"] += 1

    def get_metrics(self) -> dict:
        return dict(self.metrics)


def get_logger(name: str, log_file: str | None = None) -> StructuredLogger:
    """Create a structured logger for an agent or component."""
    return StructuredLogger(name, log_file)
