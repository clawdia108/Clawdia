"""BaseAgent — common interface for all Clawdia agents."""

import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from ..core.logging import get_logger, StructuredLogger
from ..core.state import StateStore, TaskRecord, TaskStatus
from ..core.bus import MessageBus, Message
from ..core.config import load_secrets, WORKSPACE
from ..core.metrics import MetricsCollector


class AgentStatus(str, Enum):
    IDLE = "idle"
    ACTIVE = "active"
    ERROR = "error"
    DISABLED = "disabled"


@dataclass
class Task:
    """A unit of work for an agent."""
    type: str                    # e.g., "deal_scoring", "email_draft"
    params: dict = field(default_factory=dict)
    priority: int = 2           # 1=urgent, 2=normal, 3=low
    source: str = ""            # who created this task
    id: str = ""


@dataclass
class Result:
    """Result of executing a task."""
    success: bool
    output: str = ""
    data: dict = field(default_factory=dict)
    error: str = ""
    metrics: dict = field(default_factory=dict)


class BaseAgent:
    """Base class for all Clawdia agents.

    Subclasses must implement:
    - name: str (unique identifier)
    - czech_name: str (Czech display name)
    - capabilities: list[str] (task types this agent can handle)
    - execute(task) -> Result

    Optional overrides:
    - setup() — one-time initialization
    - teardown() — cleanup after execution
    - can_handle(task) -> bool — custom routing logic
    """

    name: str = "base"
    czech_name: str = "základ"
    capabilities: list[str] = []
    description: str = ""
    model: str = "claude-sonnet-4-6"
    max_concurrent: int = 1

    def __init__(self):
        self.log: StructuredLogger = get_logger(self.name, f"agent-{self.name}.log")
        self.status = AgentStatus.IDLE
        self._secrets: dict | None = None
        self._metrics: MetricsCollector | None = None
        self._start_time: float = 0

    @property
    def secrets(self) -> dict:
        """Lazy-load secrets."""
        if self._secrets is None:
            self._secrets = load_secrets()
        return self._secrets

    @property
    def metrics(self) -> MetricsCollector:
        """Lazy-load metrics collector."""
        if self._metrics is None:
            self._metrics = MetricsCollector()
        return self._metrics

    def can_handle(self, task: Task) -> bool:
        """Check if this agent can handle a task type."""
        return task.type in self.capabilities

    def setup(self):
        """Called before execute. Override for initialization."""
        pass

    def teardown(self):
        """Called after execute. Override for cleanup."""
        pass

    def execute(self, task: Task) -> Result:
        """Main entry point. Must be overridden by subclass."""
        raise NotImplementedError(f"{self.name} must implement execute()")

    def run(self, task: Task, state: StateStore | None = None) -> Result:
        """Execute a task with full lifecycle management."""
        self.status = AgentStatus.ACTIVE
        self._start_time = time.time()
        self.log.info(f"Starting task: {task.type}", params=task.params)

        if state:
            state.mark_agent_active(self.name)

        record = TaskRecord(
            task_id=task.id or f"{self.name}_{int(time.time())}",
            agent=self.name,
            task_type=task.type,
            status=TaskStatus.RUNNING,
            started_at=datetime.now().isoformat(),
        )

        try:
            self.setup()
            result = self.execute(task)
            self.teardown()

            duration = time.time() - self._start_time
            record.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
            record.completed_at = datetime.now().isoformat()
            record.duration_seconds = round(duration, 1)
            record.result = result.output[:200]
            record.error = result.error
            record.metrics = {**result.metrics, **self.log.get_metrics()}

            # Record metrics
            self.metrics.record_execution(
                self.name, task.type, duration, result.success, result.error)

            if result.success:
                self.log.info(f"Completed: {task.type} in {duration:.1f}s", output=result.output[:100])
                self.status = AgentStatus.IDLE
                if state:
                    state.mark_agent_idle(self.name, result.output[:100])
            else:
                self.log.error(f"Failed: {task.type} — {result.error}")
                self.status = AgentStatus.ERROR
                if state:
                    state.mark_agent_error(self.name, result.error)

        except Exception as e:
            duration = time.time() - self._start_time
            record.status = TaskStatus.FAILED
            record.completed_at = datetime.now().isoformat()
            record.duration_seconds = round(duration, 1)
            record.error = str(e)
            self.log.error(f"Exception in {task.type}: {e}")
            self.status = AgentStatus.ERROR
            if state:
                state.mark_agent_error(self.name, str(e))
            result = Result(success=False, error=str(e))

        if state:
            state.record_task(record)

        return result

    def report(self) -> dict:
        """Health/status report for this agent."""
        return {
            "name": self.name,
            "czech_name": self.czech_name,
            "status": self.status.value,
            "capabilities": self.capabilities,
            "metrics": self.log.get_metrics(),
        }

    def run_script(self, script_cmd: str, timeout: int = 300) -> Result:
        """Run a Python script and return a Result. Shared by all script-based agents."""
        parts = script_cmd.split()
        try:
            r = subprocess.run(
                ["python3"] + parts,
                capture_output=True, text=True, timeout=timeout,
                cwd=str(WORKSPACE),
            )
            return Result(
                success=r.returncode == 0,
                output=r.stdout[-500:] if r.stdout else "",
                error=r.stderr[-300:] if r.stderr else "",
                metrics={"exit_code": r.returncode},
            )
        except subprocess.TimeoutExpired:
            return Result(success=False, error=f"Timeout ({timeout}s)")
        except Exception as e:
            return Result(success=False, error=str(e))

    def __repr__(self):
        return f"<{self.__class__.__name__} '{self.name}' ({self.czech_name}) [{self.status.value}]>"
