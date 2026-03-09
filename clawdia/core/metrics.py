"""Metrics collection and reporting for Clawdia agents."""

import json
from datetime import datetime, timedelta
from pathlib import Path

from .config import WORKSPACE, LOGS_DIR, KNOWLEDGE_DIR

METRICS_FILE = KNOWLEDGE_DIR / "metrics.json"


class MetricsCollector:
    """Collects and persists agent execution metrics."""

    def __init__(self):
        self._data = self._load()

    def _load(self) -> dict:
        if METRICS_FILE.exists():
            try:
                return json.loads(METRICS_FILE.read_text())
            except Exception:
                pass
        return {"agents": {}, "daily": {}, "updated_at": ""}

    def _save(self):
        self._data["updated_at"] = datetime.now().isoformat()
        METRICS_FILE.parent.mkdir(parents=True, exist_ok=True)
        METRICS_FILE.write_text(json.dumps(self._data, indent=2, ensure_ascii=False))

    def record_execution(self, agent: str, task_type: str, duration: float,
                         success: bool, error: str = ""):
        """Record a single task execution."""
        agents = self._data.setdefault("agents", {})
        a = agents.setdefault(agent, {
            "total_runs": 0, "total_success": 0, "total_failures": 0,
            "total_duration": 0, "avg_duration": 0,
            "last_run": "", "tasks": {},
        })

        a["total_runs"] += 1
        a["total_duration"] = round(a["total_duration"] + duration, 1)
        a["avg_duration"] = round(a["total_duration"] / a["total_runs"], 1)
        a["last_run"] = datetime.now().isoformat()

        if success:
            a["total_success"] += 1
        else:
            a["total_failures"] += 1

        # Per-task metrics
        t = a["tasks"].setdefault(task_type, {"runs": 0, "success": 0, "failures": 0})
        t["runs"] += 1
        if success:
            t["success"] += 1
        else:
            t["failures"] += 1

        # Daily aggregate
        today = datetime.now().strftime("%Y-%m-%d")
        daily = self._data.setdefault("daily", {})
        d = daily.setdefault(today, {"runs": 0, "success": 0, "failures": 0, "duration": 0})
        d["runs"] += 1
        d["duration"] = round(d["duration"] + duration, 1)
        if success:
            d["success"] += 1
        else:
            d["failures"] += 1

        # Keep only last 30 days
        cutoff = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        self._data["daily"] = {k: v for k, v in daily.items() if k >= cutoff}

        self._save()

    def get_agent_metrics(self, agent: str) -> dict:
        """Get metrics for a specific agent."""
        return self._data.get("agents", {}).get(agent, {})

    def get_all_metrics(self) -> dict:
        """Get all metrics data."""
        return dict(self._data)

    def get_summary(self) -> dict:
        """Get a high-level summary."""
        agents = self._data.get("agents", {})
        today = datetime.now().strftime("%Y-%m-%d")
        today_data = self._data.get("daily", {}).get(today, {})

        total_runs = sum(a.get("total_runs", 0) for a in agents.values())
        total_success = sum(a.get("total_success", 0) for a in agents.values())
        total_failures = sum(a.get("total_failures", 0) for a in agents.values())

        return {
            "total_agents": len(agents),
            "total_runs": total_runs,
            "total_success": total_success,
            "total_failures": total_failures,
            "success_rate": round(total_success / total_runs * 100, 1) if total_runs > 0 else 0,
            "today": today_data,
            "updated_at": self._data.get("updated_at", ""),
        }

    def print_dashboard(self):
        """Print a metrics dashboard to console."""
        agents = self._data.get("agents", {})
        summary = self.get_summary()

        print(f"\n{'='*60}")
        print(f"  CLAWDIA METRICS DASHBOARD")
        print(f"{'='*60}")

        print(f"\n  Total runs: {summary['total_runs']}")
        print(f"  Success rate: {summary['success_rate']}%")
        print(f"  Today: {summary['today'].get('runs', 0)} runs, "
              f"{summary['today'].get('success', 0)} ok, "
              f"{summary['today'].get('failures', 0)} fail")

        if agents:
            print(f"\n  {'Agent':12s} │ {'Runs':>5s} │ {'OK':>4s} │ {'Fail':>4s} │ {'Rate':>5s} │ {'Avg':>6s} │ Last run")
            print(f"  {'─'*12}─┼─{'─'*5}─┼─{'─'*4}─┼─{'─'*4}─┼─{'─'*5}─┼─{'─'*6}─┼─{'─'*16}")
            for name in sorted(agents.keys()):
                a = agents[name]
                runs = a.get("total_runs", 0)
                ok = a.get("total_success", 0)
                fail = a.get("total_failures", 0)
                rate = f"{ok/runs*100:.0f}%" if runs > 0 else "–"
                avg = f"{a.get('avg_duration', 0):.1f}s"
                last = a.get("last_run", "")[:16]
                print(f"  {name:12s} │ {runs:5d} │ {ok:4d} │ {fail:4d} │ {rate:>5s} │ {avg:>6s} │ {last}")

        # Daily trend (last 7 days)
        daily = self._data.get("daily", {})
        recent = sorted(daily.items())[-7:]
        if recent:
            print(f"\n  Daily trend (last 7 days):")
            for day, d in recent:
                runs = d.get("runs", 0)
                ok = d.get("success", 0)
                bar = "█" * min(runs, 30)
                print(f"  {day} │ {runs:3d} runs │ {ok:3d} ok │ {bar}")

        print()
