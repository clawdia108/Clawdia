#!/usr/bin/env python3
"""
Dashboard Aggregator — Unified metrics API for all Clawdia data
================================================================
Single source of truth that collects metrics from every subsystem.
Used by: status_page, report_generator, health_server, CLI.

Reduces duplication by providing one clean JSON payload.

Usage:
  python3 scripts/dashboard_aggregator.py             # Full dashboard JSON
  python3 scripts/dashboard_aggregator.py summary      # Quick summary text
  python3 scripts/dashboard_aggregator.py section <x>  # Single section
"""

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

WORKSPACE = Path(__file__).resolve().parents[1]


def safe_json(path):
    try:
        p = Path(path)
        if p.exists():
            return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return None


def safe_md(path):
    try:
        p = Path(path)
        if p.exists():
            return p.read_text()
    except OSError:
        pass
    return ""


class DashboardAggregator:
    """Collect and serve all system metrics."""

    def __init__(self):
        self.timestamp = datetime.now().isoformat()
        self._cache = {}

    def collect_all(self):
        """Collect all metrics into a single payload."""
        return {
            "timestamp": self.timestamp,
            "system": self.system_status(),
            "pipeline": self.pipeline_metrics(),
            "agents": self.agent_metrics(),
            "scorecard": self.scorecard_metrics(),
            "costs": self.cost_metrics(),
            "bus": self.bus_metrics(),
            "tasks": self.task_metrics(),
            "workflows": self.workflow_metrics(),
            "velocity": self.velocity_metrics(),
            "predictions": self.prediction_metrics(),
            "timing": self.timing_metrics(),
        }

    def system_status(self):
        """Core system health."""
        orch_running = False
        orch_pid = None
        pid_file = WORKSPACE / "logs" / "orchestrator.pid"
        if pid_file.exists():
            try:
                pid = int(pid_file.read_text().strip())
                os.kill(pid, 0)  # check if process exists
                orch_running = True
                orch_pid = pid
            except (ValueError, ProcessLookupError, PermissionError):
                pass

        # Uptime from execution state
        exec_state = safe_json(WORKSPACE / "knowledge" / "EXECUTION_STATE.json") or {}
        last_run = exec_state.get("last_orchestrator_run", "unknown")

        # Ollama status
        ollama_up = False
        try:
            result = subprocess.run(["curl", "-s", "-m", "2", "http://localhost:11434/api/tags"],
                                   capture_output=True, text=True, timeout=3)
            ollama_up = result.returncode == 0
        except Exception:
            pass

        return {
            "orchestrator_running": orch_running,
            "orchestrator_pid": orch_pid,
            "last_orchestrator_run": last_run,
            "ollama_available": ollama_up,
            "hostname": os.uname().nodename,
        }

    def pipeline_metrics(self):
        """Sales pipeline data."""
        scoring_md = safe_md(WORKSPACE / "pipedrive" / "DEAL_SCORING.md")
        pipeline_md = safe_md(WORKSPACE / "pipedrive" / "PIPELINE_STATUS.md")

        result = {
            "total_deals": 0,
            "total_value": 0,
            "won": 0,
            "lost": 0,
            "by_stage": {},
            "top_deals": [],
        }

        if scoring_md:
            scores = re.findall(r"Score:\s*(\d+)", scoring_md)
            result["total_deals"] = len(scores)
            # Top deals
            deal_blocks = re.findall(r"##\s+(.+?)\n.*?Score:\s*(\d+).*?Value:\s*[€$]?([\d,.]+)", scoring_md, re.DOTALL)
            for title, score, value in deal_blocks[:10]:
                result["top_deals"].append({
                    "title": title.strip(),
                    "score": int(score),
                    "value": float(value.replace(",", "")),
                })

        if pipeline_md:
            for m in re.finditer(r"\*\*(.+?)\*\*:\s*(\d+)\s*deals?\s*\([\$€]?([\d,.]+)", pipeline_md):
                stage, count, value = m.group(1), int(m.group(2)), float(m.group(3).replace(",", ""))
                result["by_stage"][stage] = {"count": count, "value": value}
                result["total_value"] += value

            won_m = re.search(r"Won:\s*(\d+)", pipeline_md)
            lost_m = re.search(r"Lost:\s*(\d+)", pipeline_md)
            if won_m:
                result["won"] = int(won_m.group(1))
            if lost_m:
                result["lost"] = int(lost_m.group(1))

        return result

    def agent_metrics(self):
        """Agent health and performance."""
        agents_cfg = {
            "spojka": {"file": "knowledge/USER_DIGEST_AM.md", "max_h": 24},
            "obchodak": {"file": "pipedrive/PIPELINE_STATUS.md", "max_h": 48},
            "postak": {"file": "inbox/INBOX_DIGEST.md", "max_h": 24},
            "strateg": {"file": "intel/DAILY-INTEL.md", "max_h": 48},
            "kalendar": {"file": "calendar/TODAY.md", "max_h": 24},
            "kontrolor": {"file": "reviews/SYSTEM_HEALTH.md", "max_h": 72},
            "archivar": {"file": "knowledge/IMPROVEMENTS.md", "max_h": 72},
        }

        states = safe_json(WORKSPACE / "control-plane" / "agent-states.json") or {}
        now = time.time()
        results = []

        for name, cfg in agents_cfg.items():
            p = WORKSPACE / cfg["file"]
            age_h = None
            health = "dead"
            if p.exists() and p.stat().st_size > 50:
                age_h = round((now - p.stat().st_mtime) / 3600, 1)
                health = "healthy" if age_h <= cfg["max_h"] else "stale"
            elif p.exists():
                health = "empty"

            agent_state = states.get(name, {})
            results.append({
                "name": name,
                "health": health,
                "age_hours": age_h,
                "state": agent_state.get("state", "unknown"),
                "tasks_completed": agent_state.get("total_tasks_completed", 0),
                "tasks_failed": agent_state.get("total_tasks_failed", 0),
            })

        healthy = sum(1 for a in results if a["health"] == "healthy")
        return {
            "total": len(results),
            "healthy": healthy,
            "agents": results,
        }

    def scorecard_metrics(self):
        """ADHD scorecard data."""
        sc = safe_json(WORKSPACE / "reviews" / "daily-scorecard" / "score_state.json")
        if not sc:
            return {"total_points": 0, "level": 0, "streak": 0, "achievements": []}
        return {
            "total_points": sc.get("total_points", 0),
            "level": sc.get("level", 0),
            "title": sc.get("title", ""),
            "streak": sc.get("current_streak", 0),
            "best_streak": sc.get("best_streak", 0),
            "achievements": sc.get("achievements", []),
        }

    def cost_metrics(self):
        """API cost tracking data."""
        costs = safe_json(WORKSPACE / "logs" / "cost-tracker.json")
        if not costs:
            return {"total": 0, "today": 0, "week": 0, "by_model": {}}

        today_key = date.today().isoformat()
        daily = costs.get("daily", {})

        week_start = date.today() - timedelta(days=date.today().weekday())
        week_total = sum(daily.get((week_start + timedelta(days=d)).isoformat(), 0) for d in range(7))

        return {
            "total": costs.get("total", 0),
            "today": daily.get(today_key, 0),
            "week": week_total,
            "by_model": costs.get("by_model", {}),
        }

    def bus_metrics(self):
        """Message bus status."""
        outbox = WORKSPACE / "bus" / "outbox"
        dead = WORKSPACE / "bus" / "dead-letter"
        return {
            "pending_messages": len(list(outbox.glob("*.json"))) if outbox.exists() else 0,
            "dead_letters": len(list(dead.glob("*.json"))) if dead.exists() else 0,
        }

    def task_metrics(self):
        """Task queue status."""
        tq = safe_json(WORKSPACE / "control-plane" / "task-queue.json")
        if not tq:
            return {"total": 0, "pending": 0, "assigned": 0, "done": 0}

        tasks = tq.get("tasks", [])
        pending = sum(1 for t in tasks if isinstance(t, dict) and t.get("status") == "pending")
        assigned = sum(1 for t in tasks if isinstance(t, dict) and t.get("status") == "assigned")
        done = sum(1 for t in tasks if isinstance(t, dict) and t.get("status") == "done")

        return {"total": len(tasks), "pending": pending, "assigned": assigned, "done": done}

    def workflow_metrics(self):
        """Workflow engine status."""
        active_dir = WORKSPACE / "workflows" / "active"
        completed_dir = WORKSPACE / "workflows" / "completed"
        return {
            "active": len(list(active_dir.glob("*.json"))) if active_dir.exists() else 0,
            "completed": len(list(completed_dir.glob("*.json"))) if completed_dir.exists() else 0,
        }

    def velocity_metrics(self):
        """Deal velocity summary."""
        vel = safe_json(WORKSPACE / "pipedrive" / "deal_velocity.json")
        if not vel:
            return {"averages": {}, "total_tracked": 0}
        return {
            "averages": vel.get("stage_averages", {}),
            "total_tracked": len(vel.get("deals", {})),
            "updated_at": vel.get("updated_at", "unknown"),
        }

    def prediction_metrics(self):
        """Success prediction summary."""
        preds = safe_json(WORKSPACE / "knowledge" / "deal-predictions.json")
        if not preds:
            return {"total": 0, "high_risk": 0, "deals": []}

        deals = preds.get("predictions", [])
        return {
            "total": len(deals),
            "high_risk": sum(1 for d in deals if isinstance(d, dict) and d.get("probability", 100) < 30),
            "avg_probability": round(sum(d.get("probability", 50) for d in deals if isinstance(d, dict)) / max(1, len(deals)), 1),
        }

    def timing_metrics(self):
        """Execution timing summary."""
        tracker = safe_json(WORKSPACE / "logs" / "time-tracker.json")
        if not tracker:
            return {"cycles": 0, "avg_ms": 0}

        cycles = tracker.get("cycles", [])
        recent = cycles[-20:] if cycles else []
        return {
            "total_cycles": len(cycles),
            "recent_avg_ms": sum(c["total_ms"] for c in recent) // max(1, len(recent)) if recent else 0,
        }

    def summary_text(self):
        """Generate a text summary."""
        data = self.collect_all()

        sys_status = data["system"]
        pipe = data["pipeline"]
        agents = data["agents"]
        score = data["scorecard"]
        costs = data["costs"]

        orch = "RUNNING" if sys_status["orchestrator_running"] else "STOPPED"
        lines = [
            f"Clawdia Dashboard — {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            f"",
            f"System: Orchestrator {orch}, Ollama {'UP' if sys_status['ollama_available'] else 'DOWN'}",
            f"Pipeline: {pipe['total_deals']} deals, ${pipe['total_value']:,.0f} value, {pipe['won']}W/{pipe['lost']}L",
            f"Agents: {agents['healthy']}/{agents['total']} healthy",
            f"Scorecard: {score['total_points']} pts, Lv.{score['level']} {score.get('title', '')}",
            f"Costs: ${costs['total']:.2f} total, ${costs['week']:.2f} this week",
            f"Bus: {data['bus']['pending_messages']} pending, {data['bus']['dead_letters']} dead",
            f"Tasks: {data['tasks']['pending']} pending, {data['tasks']['done']} done",
        ]
        return "\n".join(lines)


def main():
    agg = DashboardAggregator()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "full"

    if cmd == "full":
        data = agg.collect_all()
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif cmd == "summary":
        print(agg.summary_text())
    elif cmd == "section" and len(sys.argv) > 2:
        section = sys.argv[2]
        data = agg.collect_all()
        if section in data:
            print(json.dumps(data[section], indent=2))
        else:
            print(f"Unknown section: {section}")
            print(f"Available: {', '.join(data.keys())}")
    elif cmd == "save":
        data = agg.collect_all()
        out = WORKSPACE / "logs" / "dashboard-snapshot.json"
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        print(f"Saved to {out}")
    else:
        print("Usage: dashboard_aggregator.py [full|summary|section <name>|save]")


if __name__ == "__main__":
    main()
