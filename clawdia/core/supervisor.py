"""Supervisor — unified orchestration engine.

Merges orchestrator.py + agent_dispatcher.py + agent_runner.py into one clean class.

Three internal loops:
1. Dispatcher loop (30min) — scan pipeline, assign work to agents
2. Runner loop (60s) — consume bus messages, execute agent handlers
3. Health loop (10min) — check agent health, cleanup, metrics
"""

import json
import signal
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from .bus import MessageBus, Message
from .state import StateStore, TaskRecord, TaskStatus
from .logging import get_logger, set_correlation_id
from .config import WORKSPACE, load_secrets
from .metrics import MetricsCollector

log = get_logger("supervisor", "supervisor.log")

# Agent → script handler mapping (from agent_runner.py)
AGENT_HANDLERS = {
    "obchodak": [
        ("deal_scoring", "scripts/pipedrive_lead_scorer.py"),
        ("deal_health", "scripts/deal_health_scorer.py --snapshot"),
        ("stale_cleanup", "scripts/stale_deal_cleanup.py --report"),
        ("writeback", "scripts/pipedrive_writeback.py"),
    ],
    "textar": [
        ("email_draft", "scripts/draft_generator.py 3"),
        ("spin_prep", "scripts/spin_prep_generator.py"),
        ("followup", "scripts/followup_engine.py --scan"),
    ],
    "postak": [
        ("cold_calls", "scripts/cold_call_list.py --export"),
        ("morning_prep", "scripts/morning_sales_prep.py"),
        ("email_sequences", "scripts/email_sequences.py advance"),
    ],
    "strateg": [
        ("market_intel", "scripts/market_trends.py report"),
        ("competitive", "scripts/competitive_intel.py scan"),
        ("signals", "scripts/signal_scanner.py"),
    ],
    "kalendar": [
        ("meeting_prep", "scripts/meeting_prep.py --upcoming"),
        ("fathom_sync", "scripts/fathom_sync.py"),
        ("auto_next_step", "scripts/auto_next_step.py --days 3"),
    ],
    "kontrolor": [
        ("anomaly_scan", "scripts/anomaly_detector.py scan"),
        ("health_report", "scripts/deal_health_scorer.py"),
        ("schema_check", "scripts/schema_validator.py validate"),
    ],
    "archivar": [
        ("notion_sync", "scripts/notion_sync.py"),
        ("knowledge_graph", "scripts/knowledge_graph.py build"),
        ("dedup", "scripts/knowledge_dedup.py scan"),
    ],
    "udrzbar": [
        ("backup", "scripts/backup_system.py snapshot"),
        ("status_page", "scripts/status_page.py"),
    ],
    "hlidac": [
        ("pipeline_guard", "scripts/pipeline_automation.py check"),
        ("activity_guard", "scripts/pipedrive_open_deal_activity_guard.py"),
    ],
    "planovac": [
        ("strategic_brief", "scripts/strategic_brief.py generate"),
        ("weekly_intel", "scripts/weekly_intel.py"),
    ],
    "spojka": [
        ("daily_digest", "scripts/daily_digest.py preview"),
        ("standup", "scripts/standup_generator.py"),
        ("scorecard", "scripts/adhd-scorecard.py"),
        ("nudge", "scripts/motivational_nudge.py auto"),
    ],
    "vyvojar": [
        ("report", "scripts/report_generator.py generate"),
    ],
    "kouc": [
        ("coach_call", "scripts/sales_coach.py"),
        ("weekly_summary", "scripts/sales_coach.py --weekly"),
        ("trends", "scripts/sales_coach.py --trends"),
    ],
}

# All agent names
ALL_AGENTS = list(AGENT_HANDLERS.keys())


class Supervisor:
    """Unified orchestration engine for all Clawdia agents."""

    def __init__(self):
        self.bus = MessageBus()
        self.state = StateStore()
        self.metrics = MetricsCollector()
        self.secrets = load_secrets()
        self.shutdown_requested = False
        self._setup_signals()

        # Timing
        self.dispatch_interval = 1800  # 30 minutes
        self.runner_interval = 60      # 1 minute
        self.health_interval = 600     # 10 minutes
        self._last_dispatch = 0
        self._last_health = 0

        # Metrics
        self.cycle_count = 0
        self.tasks_executed = 0
        self.errors = 0

    def _setup_signals(self):
        """Graceful shutdown on SIGTERM/SIGINT."""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, frame):
        log.info(f"Received signal {signum}, shutting down gracefully...")
        self.shutdown_requested = True

    # ─── MAIN LOOP ────────────────────────────────────────────

    def run(self):
        """Main daemon loop — runs all three internal loops."""
        log.info("Supervisor starting", agents=len(ALL_AGENTS))

        while not self.shutdown_requested:
            now = time.time()

            # Runner loop (every 60s) — consume and execute
            self._runner_cycle()

            # Dispatcher loop (every 30min) — assign new work
            if now - self._last_dispatch >= self.dispatch_interval:
                self._dispatcher_cycle()
                self._last_dispatch = now

            # Health loop (every 10min) — monitor and clean
            if now - self._last_health >= self.health_interval:
                self._health_cycle()
                self._last_health = now

            self.cycle_count += 1
            self.state.increment_cycle()

            # Sleep until next runner cycle
            time.sleep(self.runner_interval)

        log.info("Supervisor stopped", cycles=self.cycle_count, tasks=self.tasks_executed)

    def run_once(self):
        """Run a single cycle of all loops (for testing/manual runs)."""
        log.info("Running single cycle")
        self._dispatcher_cycle()
        self._runner_cycle()
        self._health_cycle()

    # ─── DISPATCHER ───────────────────────────────────────────

    def _dispatcher_cycle(self):
        """Scan pipeline state, assign work to agents."""
        set_correlation_id(f"disp_{int(time.time()) % 100000}")
        log.info("Dispatcher cycle starting")

        try:
            context = self._get_pipeline_context()
            if not context:
                log.warn("No pipeline context available")
                return

            assigned = 0

            # Assign work based on pipeline state
            for agent_name in ALL_AGENTS:
                tasks = self._determine_work(agent_name, context)
                for task_topic, task_payload in tasks:
                    msg = Message(
                        topic=task_topic,
                        payload=task_payload,
                        source="supervisor",
                        target=agent_name,
                        priority=task_payload.get("priority", 2),
                    )
                    self.bus.publish(msg)
                    assigned += 1

            log.info(f"Dispatcher: {assigned} tasks assigned to {len(ALL_AGENTS)} agents")

        except Exception as e:
            log.error(f"Dispatcher error: {e}")
            self.errors += 1

    def _get_pipeline_context(self) -> dict | None:
        """Fetch current pipeline state from Pipedrive."""
        token = self.secrets.get("PIPEDRIVE_API_TOKEN") or self.secrets.get("PIPEDRIVE_TOKEN")
        if not token:
            log.error("No Pipedrive token")
            return None

        try:
            from ..tools.pipedrive import get_open_deals
            deals = get_open_deals(token)

            now = datetime.now()
            hot = warm = stale = no_next = 0
            total_value = 0

            for d in deals:
                value = d.get("value") or 0
                total_value += value
                stage = d.get("stage_order_nr", 0)
                last = d.get("last_activity_date", "")

                if not d.get("next_activity_date"):
                    no_next += 1

                silent_days = 999
                if last:
                    try:
                        silent_days = (now - datetime.strptime(last, "%Y-%m-%d")).days
                    except ValueError:
                        pass

                if stage >= 5 and silent_days <= 7:
                    hot += 1
                elif stage >= 3 and silent_days <= 14:
                    warm += 1
                elif silent_days >= 30:
                    stale += 1

            return {
                "total_deals": len(deals),
                "hot": hot,
                "warm": warm,
                "stale": stale,
                "no_next_step": no_next,
                "total_value": total_value,
                "timestamp": now.isoformat(),
            }
        except Exception as e:
            log.error(f"Pipeline context error: {e}")
            return None

    def _determine_work(self, agent_name: str, context: dict) -> list[tuple[str, dict]]:
        """Determine what work to assign to an agent based on context."""
        tasks = []
        now = datetime.now()
        hour = now.hour
        weekday = now.weekday()  # 0=Mon

        # Only assign during work hours (6-20)
        if hour < 6 or hour > 20:
            return tasks

        # Check inbox — don't assign if agent already has pending work
        pending = self.bus.peek(agent_name)
        if pending >= 3:
            return tasks

        # Agent-specific work assignment
        if agent_name == "obchodak":
            if hour == 6 or (hour % 4 == 0):
                tasks.append(("deal.score", {"action": "score_all", "priority": 2}))

        elif agent_name == "textar":
            if hour == 8:
                tasks.append(("email.draft", {"action": "generate_drafts", "count": 3, "priority": 2}))

        elif agent_name == "postak":
            if hour == 7:
                tasks.append(("outreach.morning", {"action": "morning_prep", "priority": 1}))
            if hour == 14:
                tasks.append(("outreach.followup", {"action": "followup_scan", "priority": 2}))

        elif agent_name == "strateg":
            if weekday in (0, 2, 4) and hour == 12:  # Mon/Wed/Fri noon
                tasks.append(("intel.signals", {"action": "signal_scan", "priority": 2}))

        elif agent_name == "kalendar":
            if hour == 7:
                tasks.append(("calendar.prep", {"action": "meeting_prep", "priority": 1}))
            if hour == 13:
                tasks.append(("calendar.sync", {"action": "fathom_sync", "priority": 2}))

        elif agent_name == "kontrolor":
            if hour == 12:
                tasks.append(("health.check", {"action": "health_report", "priority": 2}))

        elif agent_name == "archivar":
            if hour == 8 or hour == 18:
                tasks.append(("sync.notion", {"action": "notion_sync", "priority": 2}))

        elif agent_name == "spojka":
            # Motivational nudges at specific hours
            if hour in (7, 12, 15, 18):
                tasks.append(("nudge.send", {"action": "nudge", "priority": 3}))

        elif agent_name == "hlidac":
            if hour % 3 == 0:
                tasks.append(("guard.pipeline", {"action": "pipeline_check", "priority": 2}))

        elif agent_name == "planovac":
            if weekday == 6 and hour == 18:  # Sunday evening
                tasks.append(("plan.weekly", {"action": "weekly_intel", "priority": 1}))

        return tasks

    # ─── RUNNER ───────────────────────────────────────────────

    def _runner_cycle(self):
        """Consume bus messages and execute agent handlers."""
        for agent_name in ALL_AGENTS:
            messages = self.bus.consume(agent_name, limit=3)
            for msg in messages:
                self._execute_task(agent_name, msg)

    def _execute_task(self, agent_name: str, msg: Message):
        """Execute a task for an agent."""
        set_correlation_id(msg.id[:8])
        log.info(f"Executing: {agent_name} ← {msg.topic}")
        self.state.mark_agent_active(agent_name)

        start = time.time()
        record = TaskRecord(
            task_id=msg.id,
            agent=agent_name,
            task_type=msg.topic,
            status=TaskStatus.RUNNING,
            started_at=datetime.now().isoformat(),
        )

        try:
            # Find matching handler script
            script = self._find_handler(agent_name, msg)
            if not script:
                log.warn(f"No handler for {agent_name}:{msg.topic}")
                record.status = TaskStatus.SKIPPED
                record.result = "no handler"
                self.state.record_task(record)
                self.state.mark_agent_idle(agent_name, "no handler")
                return

            # Run script with timeout
            result = self._run_script(script)

            duration = time.time() - start
            record.duration_seconds = round(duration, 1)
            record.completed_at = datetime.now().isoformat()

            if result["success"]:
                record.status = TaskStatus.COMPLETED
                record.result = result.get("output", "")[:200]
                self.tasks_executed += 1
                log.info(f"Done: {agent_name}:{msg.topic} in {duration:.1f}s")
                self.state.mark_agent_idle(agent_name, record.result)
            else:
                record.status = TaskStatus.FAILED
                record.error = result.get("error", "")[:200]
                self.errors += 1
                log.error(f"Failed: {agent_name}:{msg.topic} — {record.error}")
                self.state.mark_agent_error(agent_name, record.error)

            # Record metrics
            self.metrics.record_execution(
                agent_name, msg.topic, duration,
                result["success"], result.get("error", ""))

        except Exception as e:
            duration = time.time() - start
            record.status = TaskStatus.FAILED
            record.duration_seconds = round(duration, 1)
            record.completed_at = datetime.now().isoformat()
            record.error = str(e)
            self.errors += 1
            log.error(f"Exception: {agent_name}:{msg.topic} — {e}")
            self.state.mark_agent_error(agent_name, str(e))

        self.state.record_task(record)

    def _find_handler(self, agent_name: str, msg: Message) -> str | None:
        """Find the right script handler for a message."""
        handlers = AGENT_HANDLERS.get(agent_name, [])

        # Try to match by action in payload
        action = msg.payload.get("action", "")
        for handler_key, script in handlers:
            if action == handler_key or handler_key in msg.topic:
                return script

        # Default to first handler
        if handlers:
            return handlers[0][1]

        return None

    def _run_script(self, script_cmd: str, timeout: int = 300) -> dict:
        """Run a Python script with timeout."""
        parts = script_cmd.split()
        cmd = ["python3"] + parts

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(WORKSPACE),
            )
            return {
                "success": result.returncode == 0,
                "output": result.stdout[-500:] if result.stdout else "",
                "error": result.stderr[-300:] if result.stderr else "",
                "exit_code": result.returncode,
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": f"Timeout ({timeout}s)", "output": ""}
        except Exception as e:
            return {"success": False, "error": str(e), "output": ""}

    # ─── HEALTH MONITORING ────────────────────────────────────

    def _health_cycle(self):
        """Check agent health, clean up bus, report metrics."""
        log.info("Health check cycle")

        # Clean expired messages
        cleaned = self.bus.cleanup(max_age_hours=48)
        if cleaned:
            log.info(f"Cleaned {cleaned} expired messages")

        # Bus stats
        stats = self.bus.stats()
        log.info("Bus stats", **stats)

        # Agent health summary
        agents = self.state.get_all_agents()
        active = sum(1 for a in agents.values() if a.get("status") == "active")
        errors = sum(1 for a in agents.values() if a.get("status") == "error")
        idle = sum(1 for a in agents.values() if a.get("status") == "idle")

        log.info(f"Agents: {idle} idle, {active} active, {errors} error")

        # Alert on errors
        if errors >= 3:
            try:
                from ..tools.telegram import send_alert
                error_agents = [n for n, a in agents.items() if a.get("status") == "error"]
                send_alert("supervisor", "warn",
                           f"{errors} agents in error state: {', '.join(error_agents)}")
            except Exception:
                pass

    # ─── STATUS / REPORTING ──────────────────────────────────

    def status(self) -> dict:
        """Get full supervisor status."""
        return {
            "supervisor": {
                "cycle_count": self.cycle_count,
                "tasks_executed": self.tasks_executed,
                "errors": self.errors,
                "uptime_cycles": self.cycle_count,
            },
            "bus": self.bus.stats(),
            "agents": self.state.get_all_agents(),
            "state": self.state.get_summary(),
            "recent_tasks": self.state.get_recent_tasks(10),
        }

    def print_status(self):
        """Print human-readable status."""
        s = self.status()

        print("\n" + "=" * 50)
        print("  CLAWDIA SUPERVISOR STATUS")
        print("=" * 50)

        print(f"\nCycles: {s['supervisor']['cycle_count']}")
        print(f"Tasks executed: {s['supervisor']['tasks_executed']}")
        print(f"Errors: {s['supervisor']['errors']}")

        print(f"\nBus: {s['bus']['total_inbox']} inbox, "
              f"{s['bus']['outbox']} outbox, "
              f"{s['bus']['dead_letter']} dead-letter")

        agents = s.get("agents", {})
        print(f"\nAgents ({len(agents)}):")
        for name, info in sorted(agents.items()):
            status = info.get("status", "?")
            emoji = {"idle": "🟢", "active": "🔵", "error": "🔴"}.get(status, "⚪")
            last = info.get("last_active", "")[:16] if info.get("last_active") else "never"
            print(f"  {emoji} {name:12s} | {status:6s} | last: {last}")

        recent = s.get("recent_tasks", [])
        if recent:
            print(f"\nRecent tasks ({len(recent)}):")
            for t in recent[-5:]:
                emoji = {"completed": "✅", "failed": "❌", "skipped": "⏭️"}.get(t.get("status"), "⬜")
                print(f"  {emoji} {t.get('agent','?'):12s} | {t.get('task_type','?'):20s} | "
                      f"{t.get('duration_seconds',0):.1f}s")

        print()
