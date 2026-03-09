"""State management — persistent tracking of agent execution and task status."""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path

from .config import WORKSPACE
from .logging import get_logger

log = get_logger("state", "state.log")

STATE_FILE = WORKSPACE / "knowledge" / "EXECUTION_STATE.json"


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class TaskRecord:
    """Record of a task execution."""
    task_id: str
    agent: str
    task_type: str
    status: str = TaskStatus.PENDING
    started_at: str = ""
    completed_at: str = ""
    duration_seconds: float = 0
    result: str = ""
    error: str = ""
    metrics: dict = field(default_factory=dict)


class StateStore:
    """Persistent state store for agent execution tracking."""

    def __init__(self, state_file: Path | None = None):
        self.state_file = state_file or STATE_FILE
        self._state = self._load()

    def _load(self) -> dict:
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text())
            except Exception:
                pass
        return {
            "agents": {},
            "tasks": [],
            "last_overnight": None,
            "cycle_count": 0,
        }

    def _save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self._state, indent=2, ensure_ascii=False))

    def mark_agent_active(self, agent_name: str):
        """Record that an agent is currently active."""
        agents = self._state.setdefault("agents", {})
        agents[agent_name] = {
            "status": "active",
            "last_active": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
        self._save()

    def mark_agent_idle(self, agent_name: str, result: str = ""):
        """Record that an agent finished its work."""
        agents = self._state.setdefault("agents", {})
        if agent_name in agents:
            agents[agent_name]["status"] = "idle"
            agents[agent_name]["last_result"] = result
            agents[agent_name]["updated_at"] = datetime.now().isoformat()
        self._save()

    def mark_agent_error(self, agent_name: str, error: str):
        """Record an agent error."""
        agents = self._state.setdefault("agents", {})
        agents.setdefault(agent_name, {})
        agents[agent_name]["status"] = "error"
        agents[agent_name]["last_error"] = error
        agents[agent_name]["error_count"] = agents[agent_name].get("error_count", 0) + 1
        agents[agent_name]["updated_at"] = datetime.now().isoformat()
        self._save()

    def record_task(self, record: TaskRecord):
        """Add a task execution record."""
        tasks = self._state.setdefault("tasks", [])
        tasks.append(asdict(record))
        # Keep only last 200 tasks
        if len(tasks) > 200:
            self._state["tasks"] = tasks[-200:]
        self._save()

    def get_agent_status(self, agent_name: str) -> dict:
        """Get current status of an agent."""
        return self._state.get("agents", {}).get(agent_name, {"status": "unknown"})

    def get_all_agents(self) -> dict:
        """Get status of all agents."""
        return dict(self._state.get("agents", {}))

    def get_recent_tasks(self, limit: int = 20) -> list[dict]:
        """Get recent task records."""
        tasks = self._state.get("tasks", [])
        return tasks[-limit:]

    def increment_cycle(self):
        """Increment the global cycle counter."""
        self._state["cycle_count"] = self._state.get("cycle_count", 0) + 1
        self._state["last_cycle"] = datetime.now().isoformat()
        self._save()

    def get_summary(self) -> dict:
        """Get a summary of the current state."""
        agents = self._state.get("agents", {})
        tasks = self._state.get("tasks", [])
        return {
            "total_agents": len(agents),
            "active_agents": sum(1 for a in agents.values() if a.get("status") == "active"),
            "error_agents": sum(1 for a in agents.values() if a.get("status") == "error"),
            "total_tasks": len(tasks),
            "cycle_count": self._state.get("cycle_count", 0),
            "last_cycle": self._state.get("last_cycle"),
        }
