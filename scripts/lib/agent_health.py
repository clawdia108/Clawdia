#!/usr/bin/env python3
"""Shared agent health helpers."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from .paths import WORKSPACE

AGENT_OUTPUTS = {
    "spojka": {"file": "knowledge/USER_DIGEST_AM.md", "max_hours": 24},
    "obchodak": {"file": "pipedrive/PIPELINE_STATUS.md", "max_hours": 48},
    "postak": {"file": "inbox/INBOX_DIGEST.md", "max_hours": 24},
    "strateg": {"file": "intel/DAILY-INTEL.md", "max_hours": 48},
    "kalendar": {"file": "calendar/TODAY.md", "max_hours": 24},
    "kontrolor": {"file": "reviews/SYSTEM_HEALTH.md", "max_hours": 72},
    "archivar": {"file": "knowledge/IMPROVEMENTS.md", "max_hours": 72},
}

AGENT_STATES = WORKSPACE / "control-plane" / "agent-states.json"


def safe_json_load(path: Path) -> dict:
    try:
        if path.exists():
            return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def _parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _runtime_timestamp(states: dict, agent: str) -> tuple[datetime | None, str | None]:
    nested = states.get("agents", {}).get(agent, {})
    for field in ("updated_at", "last_completed_at", "entered_state_at"):
        dt = _parse_iso8601(nested.get(field))
        if dt:
            return dt, f"agents.{agent}.{field}"

    top_level = states.get(agent, {})
    for field in ("last_completed_at", "entered_state_at", "updated_at"):
        dt = _parse_iso8601(top_level.get(field))
        if dt:
            return dt, f"{agent}.{field}"

    return None, None


def collect_agent_health(
    *,
    workspace: Path = WORKSPACE,
    outputs: dict | None = None,
    states_path: Path = AGENT_STATES,
) -> dict:
    """Return runtime-first agent health with file freshness as fallback."""
    outputs = outputs or AGENT_OUTPUTS
    states = safe_json_load(states_path)
    now = time.time()
    results = {}

    for agent, config in outputs.items():
        path = workspace / config["file"]
        max_hours = config["max_hours"]
        runtime_dt, runtime_source = _runtime_timestamp(states, agent)

        file_exists = path.exists()
        file_size = path.stat().st_size if file_exists else 0
        file_age_hours = None
        if file_exists:
            file_age_hours = round((now - path.stat().st_mtime) / 3600, 1)

        output_status = "missing"
        if file_exists and file_size >= 50:
            output_status = "fresh" if file_age_hours is not None and file_age_hours <= max_hours else "stale"
        elif file_exists:
            output_status = "empty"

        if runtime_dt:
            runtime_age_hours = round((now - runtime_dt.timestamp()) / 3600, 1)
            status = "OK" if runtime_age_hours <= max_hours else "STALE"
            reason = f"runtime {runtime_age_hours}h ago via {runtime_source}"
            if output_status not in {"fresh", "missing"}:
                reason += f"; output {output_status}"
            elif output_status == "missing":
                reason += "; output missing"
            results[agent] = {
                "status": status,
                "age_hours": runtime_age_hours,
                "source": runtime_source,
                "reason": reason,
                "output_status": output_status,
                "output_age_hours": file_age_hours,
                "output_file": config["file"],
            }
            continue

        if not file_exists:
            results[agent] = {
                "status": "DEAD",
                "age_hours": None,
                "source": "output_file",
                "reason": "no runtime timestamp and file missing",
                "output_status": "missing",
                "output_age_hours": None,
                "output_file": config["file"],
            }
            continue

        if file_size < 50:
            results[agent] = {
                "status": "EMPTY",
                "age_hours": None,
                "source": "output_file",
                "reason": f"no runtime timestamp and placeholder ({file_size}B)",
                "output_status": "empty",
                "output_age_hours": file_age_hours,
                "output_file": config["file"],
            }
            continue

        status = "OK" if file_age_hours is not None and file_age_hours <= max_hours else "STALE"
        results[agent] = {
            "status": status,
            "age_hours": file_age_hours,
            "source": "output_file",
            "reason": f"output {file_age_hours}h old",
            "output_status": output_status,
            "output_age_hours": file_age_hours,
            "output_file": config["file"],
        }

    return results
