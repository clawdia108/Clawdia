#!/usr/bin/env python3
"""
Standup Generator — Auto-generate daily standup summaries
==========================================================
Pulls from execution state, recovery logs, events, task queue,
cadences, and agent health to produce a 3-section standup.

Usage:
    python3 scripts/standup_generator.py           # Generate today's standup
    python3 scripts/standup_generator.py --slack    # Slack-formatted (with emoji)
    python3 scripts/standup_generator.py --history  # Last 5 standups
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

from lib.agent_health import AGENT_OUTPUTS, collect_agent_health

BASE = Path("/Users/josefhofman/Clawdia")

# Data source paths
EXECUTION_STATE = BASE / "knowledge" / "EXECUTION_STATE.json"
RECOVERY_LOG = BASE / "logs" / "recovery.log"
EVENTS_LOG = BASE / "logs" / "events.jsonl"
TASK_QUEUE = BASE / "control-plane" / "task-queue.json"
CADENCES = BASE / "pipedrive" / "cadences.json"
AGENT_STATES = BASE / "control-plane" / "agent-states.json"
ORCHESTRATOR_LOG = BASE / "logs" / "orchestrator.log"
COST_TRACKER = BASE / "logs" / "cost-tracker.json"
SCORECARD_STATE = BASE / "reviews" / "daily-scorecard" / "score_state.json"
DEAL_SCORING = BASE / "pipedrive" / "DEAL_SCORING.md"
PIPELINE_STATUS = BASE / "pipedrive" / "PIPELINE_STATUS.md"
STALE_DEALS = BASE / "pipedrive" / "STALE_DEALS.md"
CIRCUIT_BREAKER = BASE / "logs" / "circuit-breaker.json"
HEARTBEAT = BASE / "memory" / "HEARTBEAT.md"
APPROVAL_PENDING = BASE / "approval-queue" / "pending"
APPROVAL_EXPIRED = BASE / "approval-queue" / "expired"
STANDUP_DIR = BASE / "reviews" / "standup"

def safe_json_load(path):
    """Load JSON file, return empty dict on failure."""
    try:
        if path.exists():
            return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {}


def safe_read(path):
    """Read text file, return empty string on failure."""
    try:
        if path.exists():
            return path.read_text()
    except OSError:
        pass
    return ""


class StandupGenerator:
    def __init__(self, target_date=None):
        self.today = target_date or date.today()
        self.today_str = self.today.isoformat()
        self.yesterday = self.today - timedelta(days=1)
        self.yesterday_str = self.yesterday.isoformat()

    # ── DATA GATHERING ────────────────────────────────

    def _get_yesterday_events(self):
        """Parse events.jsonl for yesterday's activity."""
        events = []
        if not EVENTS_LOG.exists():
            return events
        try:
            for line in EVENTS_LOG.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    ts = e.get("ts", "")
                    if ts.startswith(self.yesterday_str):
                        events.append(e)
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass
        return events

    def _get_today_events(self):
        """Parse events.jsonl for today's activity (so far)."""
        events = []
        if not EVENTS_LOG.exists():
            return events
        try:
            for line in EVENTS_LOG.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    ts = e.get("ts", "")
                    if ts.startswith(self.today_str):
                        events.append(e)
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass
        return events

    def _get_recovery_events(self, target_date_str):
        """Get recovery events for a specific date."""
        recoveries = []
        if not RECOVERY_LOG.exists():
            return recoveries
        try:
            for line in RECOVERY_LOG.read_text().splitlines():
                if target_date_str in line:
                    recoveries.append(line.strip())
        except OSError:
            pass
        return recoveries

    def _get_execution_state(self):
        """Load current execution state."""
        return safe_json_load(EXECUTION_STATE)

    def _get_agent_health(self):
        """Check agent health from runtime state with output fallback."""
        return collect_agent_health(workspace=BASE)

    def _get_agent_states(self):
        """Load agent state machine data."""
        return safe_json_load(AGENT_STATES)

    def _get_task_queue(self):
        """Load control-plane task queue."""
        return safe_json_load(TASK_QUEUE)

    def _get_cadences_due(self):
        """Find cadence actions due today."""
        cadences = safe_json_load(CADENCES)
        due = []
        for deal_id, cadence in cadences.items():
            if cadence.get("status") != "active":
                continue
            for step in cadence.get("steps", []):
                if step.get("status") == "pending" and step.get("due_date") == self.today_str:
                    due.append({
                        "deal_id": deal_id,
                        "action": step.get("action", "unknown"),
                        "desc": step.get("desc", ""),
                    })
        return due

    def _get_pipeline_summary(self):
        """Extract pipeline summary from PIPELINE_STATUS.md."""
        content = safe_read(PIPELINE_STATUS)
        summary = {}
        for line in content.splitlines():
            if line.startswith("- **Sales:**"):
                summary["sales"] = line.replace("- **Sales:**", "").strip()
            elif line.startswith("- **Onboarding:**"):
                summary["onboarding"] = line.replace("- **Onboarding:**", "").strip()
            elif line.startswith("- **Partnerships:**"):
                summary["partnerships"] = line.replace("- **Partnerships:**", "").strip()
        return summary

    def _get_deal_scoring_summary(self):
        """Extract key scoring stats from DEAL_SCORING.md."""
        content = safe_read(DEAL_SCORING)
        result = {}
        for line in content.splitlines():
            if "**Total scored:**" in line:
                m = re.search(r"\*\*Total scored:\*\*\s*(\d+)", line)
                if m:
                    result["total_scored"] = int(m.group(1))
            elif "HOT (80+)" in line:
                m = re.search(r"\*\*(\d+)\*\*", line)
                if m:
                    result["hot"] = int(m.group(1))
            elif "WARM (60-79)" in line:
                m = re.search(r"\*\*(\d+)\*\*", line)
                if m:
                    result["warm"] = int(m.group(1))
            elif "Sales pipeline value" in line:
                m = re.search(r"[\d,]+\s*CZK", line)
                if m:
                    result["pipeline_value"] = m.group(0)
        return result

    def _get_scorecard(self):
        """Load scorecard state."""
        return safe_json_load(SCORECARD_STATE)

    def _get_cost_summary(self):
        """Load cost tracker."""
        data = safe_json_load(COST_TRACKER)
        today_cost = data.get("daily", {}).get(self.today_str, 0)
        return {
            "today": round(today_cost, 4),
            "total": round(data.get("total", 0), 4),
        }

    def _get_overdue_count(self):
        """Count overdue activities from PIPELINE_STATUS.md."""
        content = safe_read(PIPELINE_STATUS)
        count = 0
        in_overdue = False
        for line in content.splitlines():
            if "Overdue" in line:
                in_overdue = True
                continue
            if in_overdue and line.startswith("- **"):
                count += 1
            elif in_overdue and line.startswith("##"):
                break
        return count

    def _get_stale_deals_count(self):
        """Count deals without next activity."""
        content = safe_read(STALE_DEALS)
        m = re.search(r"\*\*(\d+) deals\*\*", content)
        if m:
            return int(m.group(1))
        return 0

    def _get_pending_approvals(self):
        """Count pending approvals."""
        if APPROVAL_PENDING.exists():
            return len(list(APPROVAL_PENDING.iterdir()))
        return 0

    def _get_expired_approvals(self):
        """Count expired approvals."""
        if APPROVAL_EXPIRED.exists():
            return len(list(APPROVAL_EXPIRED.iterdir()))
        return 0

    def _get_circuit_breakers(self):
        """Check circuit breaker state."""
        data = safe_json_load(CIRCUIT_BREAKER)
        open_circuits = []
        for service, info in data.items():
            if info.get("open"):
                open_circuits.append(service)
        return open_circuits

    def _is_orchestrator_running(self):
        """Check if orchestrator PID file exists and process is alive."""
        pid_file = BASE / "logs" / "orchestrator.pid"
        if not pid_file.exists():
            return False
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            return True
        except (ValueError, OSError):
            return False

    def _get_orchestrator_cycles(self):
        """Count orchestrator cycles from events."""
        events = self._get_today_events()
        return sum(1 for e in events if e.get("type") == "cycle_complete")

    def _get_error_logs(self, hours=24):
        """Get recent errors from orchestrator log."""
        errors = []
        if not ORCHESTRATOR_LOG.exists():
            return errors
        cutoff = datetime.now() - timedelta(hours=hours)
        try:
            for line in ORCHESTRATOR_LOG.read_text().splitlines():
                if "[ERROR]" in line:
                    # Parse timestamp
                    m = re.match(r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\]", line)
                    if m:
                        try:
                            ts = datetime.strptime(m.group(1), "%Y-%m-%d %H:%M:%S")
                            if ts > cutoff:
                                errors.append(line.strip())
                        except ValueError:
                            pass
        except OSError:
            pass
        return errors

    # ── SECTION GENERATORS ────────────────────────────

    def generate_done_yesterday(self):
        """What got done yesterday."""
        items = []

        # Recovery events
        yesterday_recoveries = self._get_recovery_events(self.yesterday_str)
        if yesterday_recoveries:
            success_count = sum(1 for r in yesterday_recoveries if "SUCCESS" in r)
            agents_recovered = []
            for r in yesterday_recoveries:
                m = re.search(r"\[([^\]]+)\]\s+SUCCESS", r)
                if m:
                    agents_recovered.append(m.group(1))
            if not agents_recovered:
                # Try alternate format
                for r in yesterday_recoveries:
                    if "SUCCESS" in r:
                        parts = r.split("SUCCESS")
                        if len(parts) > 1:
                            agent = parts[1].strip().split()[0] if parts[1].strip() else "unknown"
                            agents_recovered.append(agent)
            if success_count > 0:
                agent_list = ", ".join(list(set(agents_recovered))[:5]) if agents_recovered else f"{success_count} agents"
                items.append(f"Recovered {success_count} agent(s) ({agent_list})")

        # Events analysis
        yesterday_events = self._get_yesterday_events()
        cycle_count = sum(1 for e in yesterday_events if e.get("type") == "cycle_complete")
        if cycle_count > 0:
            items.append(f"Completed {cycle_count} orchestration cycle(s)")

        triggers_processed = sum(
            e.get("triggers_processed", 0) for e in yesterday_events
            if e.get("type") == "cycle_complete"
        )
        if triggers_processed > 0:
            items.append(f"Processed {triggers_processed} inter-agent trigger(s)")

        # Deal scoring
        scoring = self._get_deal_scoring_summary()
        if scoring.get("total_scored"):
            warm = scoring.get("warm", 0)
            hot = scoring.get("hot", 0)
            leads_text = f", {warm} warm" if warm else ""
            leads_text += f", {hot} hot" if hot else ""
            items.append(f"Scored {scoring['total_scored']} deals{leads_text}")

        # Execution state completed tasks
        state = self._get_execution_state()
        completed = state.get("recently_completed", [])
        for task in completed[:3]:
            items.append(f"Completed: {task.get('title', 'unknown task')}")

        # Task queue completions
        tq = self._get_task_queue()
        done_tasks = [t for t in tq.get("tasks", []) if t.get("status") == "done"]
        for t in done_tasks[:3]:
            items.append(f"Task done: {t.get('title', '?')}")

        # Cadence actions (check yesterday)
        cadences = safe_json_load(CADENCES)
        completed_steps = 0
        for deal_id, cadence in cadences.items():
            for step in cadence.get("steps", []):
                completed_at = step.get("completed_at", "")
                if completed_at and self.yesterday_str in str(completed_at):
                    completed_steps += 1
        if completed_steps > 0:
            items.append(f"Completed {completed_steps} cadence step(s)")

        # Scorecard
        scorecard = self._get_scorecard()
        yesterday_pts = scorecard.get("daily_scores", {}).get(self.yesterday_str, 0)
        if yesterday_pts > 0:
            items.append(f"Scorecard: {yesterday_pts} pts yesterday")

        if not items:
            items.append("No tracked activity found for yesterday")

        return items

    def generate_planned_today(self):
        """What's planned for today."""
        items = []

        # Morning briefing status
        briefing = BASE / "knowledge" / "USER_DIGEST_AM.md"
        if briefing.exists():
            mod_date = datetime.fromtimestamp(briefing.stat().st_mtime).date()
            if mod_date == self.today:
                items.append("Morning briefing generated")
            else:
                items.append("Morning briefing due at 7:00")
        else:
            items.append("Morning briefing due at 7:00")

        # Pipeline scoring
        scoring = self._get_deal_scoring_summary()
        if scoring:
            items.append("Pipeline scoring cycle")

        # Cadence actions due
        due_cadences = self._get_cadences_due()
        if due_cadences:
            items.append(f"{len(due_cadences)} cadence action(s) due today")
            for c in due_cadences[:3]:
                items.append(f"  - Deal #{c['deal_id']}: {c['desc']}")

        # Task queue (assigned/pending tasks)
        tq = self._get_task_queue()
        assigned = [t for t in tq.get("tasks", []) if t.get("status") in ("assigned", "pending")]
        for t in assigned[:3]:
            items.append(f"Task: {t.get('title', '?')} [{t.get('priority', '?')}] -> {t.get('assigned_to', '?')}")

        # Execution state open tasks
        state = self._get_execution_state()
        open_tasks = [t for t in state.get("tasks", []) if t.get("status") in ("todo", "in_progress")]
        p0_tasks = [t for t in open_tasks if t.get("priority") == "P0"]
        if p0_tasks:
            items.append(f"{len(p0_tasks)} P0 task(s) active:")
            for t in p0_tasks[:3]:
                items.append(f"  - {t.get('title', '?')} [{t.get('status')}] -> {t.get('owner', '?')}")

        # Overdue activities
        overdue = self._get_overdue_count()
        if overdue > 0:
            items.append(f"{overdue} overdue deal activities to clear")

        # Pending approvals
        pending = self._get_pending_approvals()
        if pending > 0:
            items.append(f"{pending} item(s) awaiting approval")

        # Orchestrator status
        if self._is_orchestrator_running():
            cycles_today = self._get_orchestrator_cycles()
            items.append(f"Orchestrator running ({cycles_today} cycles so far today)")

        return items

    def generate_blockers(self):
        """Current blockers and risks."""
        items = []

        # Agent health
        health = self._get_agent_health()
        healthy = sum(1 for v in health.values() if v["status"] == "OK")
        total = len(health)
        stale = [k for k, v in health.items() if v["status"] == "STALE"]
        dead = [k for k, v in health.items() if v["status"] in ("DEAD", "EMPTY")]

        if stale:
            items.append(f"{len(stale)} stale agent(s): {', '.join(stale)}")
        if dead:
            items.append(f"{len(dead)} dead/empty agent(s): {', '.join(dead)}")
        if not stale and not dead:
            items.append(f"All {total} agents healthy")

        # Stuck agents
        agent_states = self._get_agent_states()
        stuck = []
        for agent, info in agent_states.items():
            state = info.get("state", "")
            entered = info.get("entered_state_at", "")
            if state in ("assigned", "working") and entered:
                try:
                    entered_dt = datetime.fromisoformat(entered)
                    elapsed = (datetime.now() - entered_dt).total_seconds() / 60
                    if elapsed > 120:  # stuck > 2h
                        stuck.append(f"{agent} (in '{state}' for {int(elapsed)}min)")
                except (ValueError, TypeError):
                    pass
        if stuck:
            items.append(f"Stuck agents: {', '.join(stuck)}")

        # Blocked tasks
        state = self._get_execution_state()
        blocked = [t for t in state.get("tasks", []) if t.get("status") == "blocked"]
        if blocked:
            for t in blocked[:3]:
                blockers = t.get("blockers", [])
                blocker_text = f" ({', '.join(blockers[:2])})" if blockers else ""
                items.append(f"Blocked: {t.get('title', '?')}{blocker_text}")

        # Circuit breakers
        open_circuits = self._get_circuit_breakers()
        if open_circuits:
            items.append(f"Open circuits: {', '.join(open_circuits)}")

        # Expired approvals
        expired = self._get_expired_approvals()
        if expired > 0:
            items.append(f"{expired} expired approval(s)")

        # Recent errors
        errors = self._get_error_logs(hours=1)
        if errors:
            items.append(f"{len(errors)} error(s) in last hour")
            for e in errors[:2]:
                # Truncate long error messages
                msg = e[22:] if len(e) > 22 else e  # skip timestamp
                items.append(f"  - {msg[:80]}")

        # Stale deals
        stale_deals = self._get_stale_deals_count()
        if stale_deals > 0:
            items.append(f"{stale_deals} deals without next activity")

        # Orchestrator not running
        if not self._is_orchestrator_running():
            items.append("ORCHESTRATOR NOT RUNNING")

        if not items:
            items.append("No blockers detected")

        return items

    # ── OUTPUT FORMATTERS ─────────────────────────────

    def generate_standup(self, slack_format=False):
        """Generate full standup summary."""
        done = self.generate_done_yesterday()
        planned = self.generate_planned_today()
        blockers = self.generate_blockers()

        # Add pipeline context
        pipeline = self._get_pipeline_summary()
        scorecard = self._get_scorecard()
        costs = self._get_cost_summary()

        if slack_format:
            return self._format_slack(done, planned, blockers, pipeline, scorecard, costs)
        else:
            return self._format_markdown(done, planned, blockers, pipeline, scorecard, costs)

    def _format_markdown(self, done, planned, blockers, pipeline, scorecard, costs):
        """Standard markdown format for file storage."""
        lines = [
            f"# Daily Standup — {self.today_str}",
            f"> Generated {datetime.now().strftime('%H:%M')} | Clawdia Ops Engine",
            "",
            "## Done Yesterday",
        ]
        for item in done:
            lines.append(f"- {item}")

        lines.append("")
        lines.append("## Planned Today")
        for item in planned:
            if item.startswith("  "):
                lines.append(f"  {item.strip()}")
            else:
                lines.append(f"- {item}")

        lines.append("")
        lines.append("## Blockers")
        for item in blockers:
            if item.startswith("  "):
                lines.append(f"  {item.strip()}")
            else:
                lines.append(f"- {item}")

        # Footer with context
        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("### Context")
        if pipeline:
            for key, val in pipeline.items():
                lines.append(f"- **{key.title()}:** {val}")
        if scorecard.get("total_points"):
            streak = scorecard.get("current_streak", 0)
            title = scorecard.get("title", "?")
            today_pts = scorecard.get("daily_scores", {}).get(self.today_str, 0)
            lines.append(f"- **Scorecard:** {scorecard['total_points']} total pts, streak {streak}d, {title}")
            if today_pts > 0:
                lines.append(f"- **Today's score:** {today_pts} pts")
        if costs.get("today", 0) > 0:
            lines.append(f"- **API costs:** ${costs['today']:.4f} today / ${costs['total']:.4f} total")

        lines.append("")

        return "\n".join(lines)

    def _format_slack(self, done, planned, blockers, pipeline, scorecard, costs):
        """Slack-friendly format with emoji."""
        lines = [
            f":clipboard: *Daily Standup -- {self.today_str}*",
            "",
            ":white_check_mark: *Done Yesterday*",
        ]
        for item in done:
            lines.append(f"  {item}")

        lines.append("")
        lines.append(":dart: *Planned Today*")
        for item in planned:
            lines.append(f"  {item}")

        lines.append("")
        lines.append(":warning: *Blockers*")
        for item in blockers:
            lines.append(f"  {item}")

        # Compact context line
        context_parts = []
        if pipeline.get("sales"):
            context_parts.append(f"Pipeline: {pipeline['sales']}")
        if scorecard.get("total_points"):
            streak = scorecard.get("current_streak", 0)
            fire = "\U0001f525" * min(streak, 3) if streak > 0 else ""
            context_parts.append(f"Score: {scorecard['total_points']} pts {fire}")
        if context_parts:
            lines.append("")
            lines.append(f":bar_chart: {' | '.join(context_parts)}")

        lines.append("")

        return "\n".join(lines)

    def save_standup(self, content):
        """Save standup to reviews/standup/{date}.md"""
        STANDUP_DIR.mkdir(parents=True, exist_ok=True)
        path = STANDUP_DIR / f"{self.today_str}.md"
        path.write_text(content)
        return path

    def get_history(self, count=5):
        """Get last N standups."""
        if not STANDUP_DIR.exists():
            return []
        files = sorted(STANDUP_DIR.glob("*.md"), reverse=True)
        results = []
        for f in files[:count]:
            results.append({
                "date": f.stem,
                "path": str(f),
                "content": f.read_text(),
            })
        return results


def main():
    parser = argparse.ArgumentParser(description="Clawdia Daily Standup Generator")
    parser.add_argument("--slack", action="store_true", help="Slack-formatted output (with emoji)")
    parser.add_argument("--history", action="store_true", help="Show last 5 standups")
    parser.add_argument("--date", type=str, help="Generate for specific date (YYYY-MM-DD)")
    parser.add_argument("--no-save", action="store_true", help="Print only, don't save to file")
    args = parser.parse_args()

    if args.history:
        gen = StandupGenerator()
        history = gen.get_history()
        if not history:
            print("No standup history found.")
            return
        for entry in history:
            print(f"\n{'='*60}")
            print(f"  {entry['date']}")
            print(f"{'='*60}")
            print(entry["content"])
        return

    target_date = None
    if args.date:
        try:
            target_date = date.fromisoformat(args.date)
        except ValueError:
            print(f"Invalid date: {args.date} (use YYYY-MM-DD)")
            sys.exit(1)

    gen = StandupGenerator(target_date=target_date)
    content = gen.generate_standup(slack_format=args.slack)

    if not args.no_save:
        path = gen.save_standup(content)
        print(f"Standup saved to {path}")
        print()

    print(content)


if __name__ == "__main__":
    main()
