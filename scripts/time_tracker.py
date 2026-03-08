#!/usr/bin/env python3
"""
Agent Execution Time Tracker — Track and analyze performance timing
====================================================================
Records execution time per agent, per task type, per orchestrator cycle.
Identifies bottlenecks and provides optimization recommendations.

Usage:
  python3 scripts/time_tracker.py stats              # Show timing statistics
  python3 scripts/time_tracker.py agent <name>        # Agent-specific timing
  python3 scripts/time_tracker.py bottlenecks         # Identify bottlenecks
  python3 scripts/time_tracker.py trends              # Show timing trends
"""

import json
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

WORKSPACE = Path(__file__).resolve().parents[1]
TRACKER_FILE = WORKSPACE / "logs" / "time-tracker.json"
LOG_FILE = WORKSPACE / "logs" / "time-tracker.log"


def tlog(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] [{level}] {msg}\n")


def load_tracker():
    try:
        if TRACKER_FILE.exists():
            return json.loads(TRACKER_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {
        "cycles": [],
        "agent_timings": {},
        "task_type_timings": {},
        "daily_stats": {},
    }


def save_tracker(data):
    TRACKER_FILE.parent.mkdir(exist_ok=True)
    # Keep last 1000 cycles max
    if len(data.get("cycles", [])) > 1000:
        data["cycles"] = data["cycles"][-1000:]
    TRACKER_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


class Timer:
    """Context manager for timing operations."""

    def __init__(self, name, category="general"):
        self.name = name
        self.category = category
        self.start = None
        self.elapsed_ms = 0

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        self.elapsed_ms = int((time.time() - self.start) * 1000)
        record_timing(self.name, self.category, self.elapsed_ms)


class CycleTimer:
    """Track a full orchestrator cycle with sub-timings."""

    def __init__(self, cycle_id=None):
        self.cycle_id = cycle_id or datetime.now().strftime("%Y%m%d_%H%M%S")
        self.start = time.time()
        self.steps = []

    def step(self, name):
        return StepTimer(self, name)

    def finish(self):
        total_ms = int((time.time() - self.start) * 1000)
        tracker = load_tracker()
        cycle_data = {
            "id": self.cycle_id,
            "timestamp": datetime.now().isoformat(),
            "total_ms": total_ms,
            "steps": self.steps,
        }
        tracker["cycles"].append(cycle_data)

        # Update daily stats
        today = date.today().isoformat()
        daily = tracker.setdefault("daily_stats", {}).setdefault(today, {
            "cycles": 0, "total_ms": 0, "avg_ms": 0, "max_ms": 0, "min_ms": 999999,
        })
        daily["cycles"] += 1
        daily["total_ms"] += total_ms
        daily["avg_ms"] = daily["total_ms"] // daily["cycles"]
        daily["max_ms"] = max(daily["max_ms"], total_ms)
        daily["min_ms"] = min(daily["min_ms"], total_ms)

        save_tracker(tracker)
        return total_ms


class StepTimer:
    """Timer for individual steps within a cycle."""

    def __init__(self, cycle, name):
        self.cycle = cycle
        self.name = name
        self.start = None

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, *args):
        elapsed = int((time.time() - self.start) * 1000)
        self.cycle.steps.append({"name": self.name, "ms": elapsed})


def record_timing(name, category, elapsed_ms):
    """Record a timing event."""
    tracker = load_tracker()

    cat_timings = tracker.setdefault("agent_timings" if category == "agent" else "task_type_timings", {})
    entry = cat_timings.setdefault(name, {
        "count": 0, "total_ms": 0, "avg_ms": 0,
        "min_ms": 999999, "max_ms": 0, "last_ms": 0,
        "recent": [],
    })

    entry["count"] += 1
    entry["total_ms"] += elapsed_ms
    entry["avg_ms"] = entry["total_ms"] // entry["count"]
    entry["min_ms"] = min(entry["min_ms"], elapsed_ms)
    entry["max_ms"] = max(entry["max_ms"], elapsed_ms)
    entry["last_ms"] = elapsed_ms
    entry["recent"].append({"ts": datetime.now().isoformat(), "ms": elapsed_ms})
    entry["recent"] = entry["recent"][-50:]  # keep last 50

    save_tracker(tracker)


def analyze_bottlenecks():
    """Identify performance bottlenecks."""
    tracker = load_tracker()
    bottlenecks = []

    # Analyze cycle steps
    step_stats = defaultdict(list)
    for cycle in tracker.get("cycles", [])[-100:]:
        for step in cycle.get("steps", []):
            step_stats[step["name"]].append(step["ms"])

    for name, timings in step_stats.items():
        avg = sum(timings) // len(timings)
        max_t = max(timings)
        if avg > 5000:  # > 5 seconds average
            bottlenecks.append({
                "type": "slow_step",
                "name": name,
                "avg_ms": avg,
                "max_ms": max_t,
                "severity": "high" if avg > 15000 else "medium",
                "recommendation": f"Optimize {name} — averaging {avg}ms per cycle",
            })

    # Analyze agent timings
    for name, stats in tracker.get("agent_timings", {}).items():
        if stats["avg_ms"] > 10000:
            bottlenecks.append({
                "type": "slow_agent",
                "name": name,
                "avg_ms": stats["avg_ms"],
                "max_ms": stats["max_ms"],
                "severity": "high" if stats["avg_ms"] > 30000 else "medium",
                "recommendation": f"Agent {name} is slow — avg {stats['avg_ms']}ms",
            })

    # Analyze trends (getting slower?)
    daily = tracker.get("daily_stats", {})
    days = sorted(daily.keys())[-7:]
    if len(days) >= 3:
        avgs = [daily[d]["avg_ms"] for d in days]
        if avgs[-1] > avgs[0] * 1.5:
            bottlenecks.append({
                "type": "degradation",
                "name": "cycle_time",
                "trend": "increasing",
                "severity": "medium",
                "recommendation": f"Cycle time increased {avgs[0]}ms → {avgs[-1]}ms over {len(days)} days",
            })

    return bottlenecks


def show_stats():
    """Display timing statistics."""
    tracker = load_tracker()
    cycles = tracker.get("cycles", [])

    print(f"\n{'='*50}")
    print(f"  Time Tracker Statistics")
    print(f"{'='*50}\n")

    if not cycles:
        print("  No timing data recorded yet.")
        print("  Timings are recorded by the orchestrator during cycles.\n")
        return

    # Overall
    total_cycles = len(cycles)
    recent = cycles[-20:]
    avg_cycle = sum(c["total_ms"] for c in recent) // len(recent)
    max_cycle = max(c["total_ms"] for c in recent)
    min_cycle = min(c["total_ms"] for c in recent)

    print(f"  Cycles Recorded: {total_cycles}")
    print(f"  Recent Avg Cycle: {avg_cycle}ms")
    print(f"  Recent Min/Max: {min_cycle}ms / {max_cycle}ms\n")

    # Step breakdown
    step_stats = defaultdict(list)
    for c in recent:
        for s in c.get("steps", []):
            step_stats[s["name"]].append(s["ms"])

    if step_stats:
        print("  Step Breakdown (last 20 cycles):")
        for name, timings in sorted(step_stats.items(), key=lambda x: sum(x[1]) / len(x[1]), reverse=True):
            avg = sum(timings) // len(timings)
            mx = max(timings)
            bar = "#" * min(40, avg // 100)
            print(f"    {name:30s} avg:{avg:6d}ms  max:{mx:6d}ms  {bar}")
        print()

    # Agent timings
    at = tracker.get("agent_timings", {})
    if at:
        print("  Agent Timings:")
        for name, stats in sorted(at.items(), key=lambda x: x[1]["avg_ms"], reverse=True):
            print(f"    {name:20s} avg:{stats['avg_ms']:6d}ms  runs:{stats['count']:4d}  last:{stats['last_ms']:6d}ms")
        print()

    # Daily stats
    daily = tracker.get("daily_stats", {})
    days = sorted(daily.keys())[-7:]
    if days:
        print("  Daily Summary (last 7 days):")
        for d in days:
            s = daily[d]
            print(f"    {d}: {s['cycles']} cycles, avg:{s['avg_ms']}ms, max:{s['max_ms']}ms")
        print()


def show_agent(name):
    """Show timing for a specific agent."""
    tracker = load_tracker()
    at = tracker.get("agent_timings", {}).get(name)
    if not at:
        print(f"  No timing data for agent '{name}'")
        return

    print(f"\n  Agent: {name}")
    print(f"  Runs: {at['count']}")
    print(f"  Avg: {at['avg_ms']}ms")
    print(f"  Min/Max: {at['min_ms']}ms / {at['max_ms']}ms")
    print(f"  Last: {at['last_ms']}ms")

    if at.get("recent"):
        print(f"\n  Recent Timings:")
        for r in at["recent"][-10:]:
            print(f"    {r['ts'][:19]} — {r['ms']}ms")


def show_trends():
    """Show timing trends."""
    tracker = load_tracker()
    daily = tracker.get("daily_stats", {})
    days = sorted(daily.keys())[-14:]

    if not days:
        print("  No trend data yet.")
        return

    print(f"\n  Timing Trends (14 days):\n")
    max_avg = max(daily[d]["avg_ms"] for d in days) or 1

    for d in days:
        s = daily[d]
        bar_len = int((s["avg_ms"] / max_avg) * 40)
        bar = "#" * bar_len
        print(f"  {d}  {bar}  {s['avg_ms']}ms ({s['cycles']} cycles)")

    print()
    bottlenecks = analyze_bottlenecks()
    if bottlenecks:
        print(f"  Bottlenecks Detected ({len(bottlenecks)}):")
        for b in bottlenecks:
            sev = {"high": "\033[0;31mHIGH\033[0m", "medium": "\033[0;33mMED\033[0m"}.get(b["severity"], "LOW")
            print(f"    [{sev}] {b['recommendation']}")
    else:
        print("  No bottlenecks detected.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "stats"

    if cmd == "stats":
        show_stats()
    elif cmd == "agent" and len(sys.argv) > 2:
        show_agent(sys.argv[2])
    elif cmd == "bottlenecks":
        bottlenecks = analyze_bottlenecks()
        if bottlenecks:
            print(f"\n  Bottlenecks ({len(bottlenecks)}):\n")
            for b in bottlenecks:
                print(f"  [{b['severity'].upper()}] {b['type']}: {b['recommendation']}")
        else:
            print("\n  No bottlenecks detected.\n")
    elif cmd == "trends":
        show_trends()
    else:
        print("Usage: time_tracker.py [stats|agent <name>|bottlenecks|trends]")


if __name__ == "__main__":
    main()
