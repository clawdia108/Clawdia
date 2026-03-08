#!/usr/bin/env python3
"""
Structured Logging + Log Aggregator — Unified timeline from all sources
========================================================================
Replaces plain-text logging with structured JSON lines across the system.
Aggregates all log sources into a single chronological timeline.

Usage:
  # As a module
  from structured_log import slog, LogAggregator
  slog("message", level="INFO", source="orchestrator", meta={"cycle": 14})

  # CLI
  python3 scripts/structured_log.py tail [--source orchestrator] [--level ERROR] [-n 50]
  python3 scripts/structured_log.py aggregate [--hours 24]
  python3 scripts/structured_log.py stats
  python3 scripts/structured_log.py search <pattern>
"""

import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

BASE = Path("/Users/josefhofman/Clawdia")
LOG_DIR = BASE / "logs"
UNIFIED_LOG = LOG_DIR / "unified.jsonl"

# All log sources to aggregate
LOG_SOURCES = {
    "orchestrator": LOG_DIR / "orchestrator.log",
    "bus": LOG_DIR / "bus.log",
    "workflow": LOG_DIR / "workflow.log",
    "lifecycle": LOG_DIR / "agent-lifecycle.log",
    "learning": LOG_DIR / "learning.log",
    "recovery": LOG_DIR / "recovery.log",
    "lead_scorer": LOG_DIR / "lead-scorer.log",
    "events": LOG_DIR / "events.jsonl",
}

# Colors for terminal output
COLORS = {
    "ERROR": "\033[0;31m",
    "WARN": "\033[0;33m",
    "INFO": "\033[0;32m",
    "DEBUG": "\033[0;36m",
    "RESET": "\033[0m",
    "DIM": "\033[2m",
    "BOLD": "\033[1m",
}


def slog(message, level="INFO", source="system", meta=None):
    """Write a structured JSON log entry."""
    entry = {
        "ts": datetime.now().isoformat(),
        "level": level,
        "source": source,
        "msg": message,
    }
    if meta:
        entry["meta"] = meta

    LOG_DIR.mkdir(exist_ok=True)
    with open(UNIFIED_LOG, "a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return entry


def slog_error(message, source="system", error=None, meta=None):
    """Convenience: log an error with optional exception details."""
    m = meta or {}
    if error:
        m["error"] = str(error)
        m["error_type"] = type(error).__name__
    return slog(message, level="ERROR", source=source, meta=m)


def slog_event(event_type, source="system", meta=None):
    """Convenience: log a structured event."""
    m = meta or {}
    m["event_type"] = event_type
    return slog(f"Event: {event_type}", level="INFO", source=source, meta=m)


class LogAggregator:
    """Merge all log sources into a unified chronological timeline."""

    # Parse patterns for different log formats
    PLAIN_PATTERN = re.compile(
        r"\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[(\w+)\] (.+)"
    )
    RECOVERY_PATTERN = re.compile(
        r"\[(\d{4}-\d{2}-\d{2}T[\d:.]+)\] (\w+) (.+)"
    )

    def parse_plain_log(self, path, source_name):
        """Parse plain-text log format: [timestamp] [LEVEL] message"""
        entries = []
        if not path.exists():
            return entries

        try:
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue

                match = self.PLAIN_PATTERN.match(line)
                if match:
                    ts_str, level, msg = match.groups()
                    entries.append({
                        "ts": ts_str,
                        "level": level,
                        "source": source_name,
                        "msg": msg,
                    })
                else:
                    # Recovery log format
                    match2 = self.RECOVERY_PATTERN.match(line)
                    if match2:
                        ts_str, status, msg = match2.groups()
                        entries.append({
                            "ts": ts_str[:19].replace("T", " "),
                            "level": "INFO" if status == "SUCCESS" else "ERROR",
                            "source": source_name,
                            "msg": f"{status} {msg}",
                        })
        except OSError:
            pass

        return entries

    def parse_jsonl_log(self, path, source_name):
        """Parse JSON lines log format."""
        entries = []
        if not path.exists():
            return entries

        try:
            for line in path.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    ts = data.get("ts", "")
                    if "T" in ts and len(ts) > 19:
                        ts = ts[:19].replace("T", " ")

                    entry = {
                        "ts": ts,
                        "level": data.get("level", "INFO"),
                        "source": source_name,
                        "msg": data.get("msg") or data.get("type", "event"),
                    }
                    # Include extra fields as meta
                    meta = {k: v for k, v in data.items()
                            if k not in ("ts", "level", "source", "msg", "type")}
                    if meta:
                        entry["meta"] = meta
                    entries.append(entry)
                except json.JSONDecodeError:
                    continue
        except OSError:
            pass

        return entries

    def aggregate(self, hours=24, sources=None, level_filter=None):
        """Aggregate all logs into chronological order."""
        all_entries = []
        cutoff = (datetime.now() - timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")

        for source_name, path in LOG_SOURCES.items():
            if sources and source_name not in sources:
                continue

            if path.suffix == ".jsonl":
                entries = self.parse_jsonl_log(path, source_name)
            else:
                entries = self.parse_plain_log(path, source_name)

            # Also parse unified log if it exists
            all_entries.extend(entries)

        # Add unified log entries
        if UNIFIED_LOG.exists():
            all_entries.extend(self.parse_jsonl_log(UNIFIED_LOG, "unified"))

        # Filter by time
        all_entries = [e for e in all_entries if e.get("ts", "") >= cutoff]

        # Filter by level
        if level_filter:
            level_order = {"ERROR": 0, "WARN": 1, "INFO": 2, "DEBUG": 3}
            min_level = level_order.get(level_filter, 2)
            all_entries = [e for e in all_entries
                          if level_order.get(e.get("level", "INFO"), 2) <= min_level]

        # Sort chronologically
        all_entries.sort(key=lambda e: e.get("ts", ""))

        # Deduplicate (same timestamp + source + message)
        seen = set()
        deduped = []
        for e in all_entries:
            key = (e.get("ts", ""), e.get("source", ""), e.get("msg", ""))
            if key not in seen:
                seen.add(key)
                deduped.append(e)

        return deduped

    def search(self, pattern, hours=24):
        """Search across all logs for a pattern."""
        entries = self.aggregate(hours=hours)
        regex = re.compile(pattern, re.IGNORECASE)
        return [e for e in entries if regex.search(e.get("msg", ""))]

    def stats(self, hours=24):
        """Get statistics across all log sources."""
        entries = self.aggregate(hours=hours)

        by_source = defaultdict(int)
        by_level = defaultdict(int)
        by_hour = defaultdict(int)

        for e in entries:
            by_source[e.get("source", "unknown")] += 1
            by_level[e.get("level", "INFO")] += 1
            ts = e.get("ts", "")
            if len(ts) >= 13:
                by_hour[ts[:13]] += 1

        return {
            "total_entries": len(entries),
            "by_source": dict(sorted(by_source.items(), key=lambda x: -x[1])),
            "by_level": dict(by_level),
            "busiest_hours": dict(sorted(by_hour.items(), key=lambda x: -x[1])[:5]),
            "error_count": by_level.get("ERROR", 0),
            "warn_count": by_level.get("WARN", 0),
        }

    def tail(self, n=20, source=None, level=None):
        """Get the last n entries, optionally filtered."""
        entries = self.aggregate(hours=24, sources=[source] if source else None,
                                level_filter=level)
        return entries[-n:]


def format_entry(entry, colorize=True):
    """Format a log entry for terminal display."""
    ts = entry.get("ts", "?")
    level = entry.get("level", "INFO")
    source = entry.get("source", "?")
    msg = entry.get("msg", "")

    if colorize:
        level_color = COLORS.get(level, "")
        reset = COLORS["RESET"]
        dim = COLORS["DIM"]
        return f"{dim}{ts}{reset} {level_color}{level:5s}{reset} {dim}[{source}]{reset} {msg}"
    else:
        return f"{ts} {level:5s} [{source}] {msg}"


def main():
    agg = LogAggregator()

    if len(sys.argv) < 2:
        # Default: show last 20 entries
        entries = agg.tail(20)
        for e in entries:
            print(format_entry(e))
        return

    cmd = sys.argv[1]

    if cmd == "tail":
        n = 20
        source = None
        level = None
        i = 2
        while i < len(sys.argv):
            if sys.argv[i] == "-n" and i + 1 < len(sys.argv):
                n = int(sys.argv[i + 1])
                i += 2
            elif sys.argv[i] == "--source" and i + 1 < len(sys.argv):
                source = sys.argv[i + 1]
                i += 2
            elif sys.argv[i] == "--level" and i + 1 < len(sys.argv):
                level = sys.argv[i + 1].upper()
                i += 2
            else:
                i += 1

        entries = agg.tail(n, source, level)
        for e in entries:
            print(format_entry(e))

    elif cmd == "aggregate":
        hours = 24
        if "--hours" in sys.argv:
            idx = sys.argv.index("--hours")
            if idx + 1 < len(sys.argv):
                hours = int(sys.argv[idx + 1])

        entries = agg.aggregate(hours=hours)
        for e in entries:
            print(format_entry(e))
        print(f"\n--- {len(entries)} entries in last {hours}h ---")

    elif cmd == "stats":
        hours = 24
        if "--hours" in sys.argv:
            idx = sys.argv.index("--hours")
            if idx + 1 < len(sys.argv):
                hours = int(sys.argv[idx + 1])

        stats = agg.stats(hours)
        print(f"\n{'='*50}")
        print(f"  LOG STATISTICS (last {hours}h)")
        print(f"{'='*50}")
        print(f"\n  Total entries: {stats['total_entries']}")
        print(f"  Errors: {stats['error_count']}")
        print(f"  Warnings: {stats['warn_count']}")
        print(f"\n  By source:")
        for src, count in stats["by_source"].items():
            print(f"    {src}: {count}")
        print(f"\n  By level:")
        for lvl, count in stats["by_level"].items():
            print(f"    {lvl}: {count}")
        if stats["busiest_hours"]:
            print(f"\n  Busiest hours:")
            for hour, count in stats["busiest_hours"].items():
                print(f"    {hour}: {count}")

    elif cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: structured_log.py search <pattern>")
            return
        pattern = sys.argv[2]
        results = agg.search(pattern)
        for e in results:
            print(format_entry(e))
        print(f"\n--- {len(results)} matches for '{pattern}' ---")

    elif cmd == "export":
        entries = agg.aggregate(hours=24 * 7)
        output = LOG_DIR / "aggregated.jsonl"
        with open(output, "w") as f:
            for e in entries:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        print(f"Exported {len(entries)} entries to {output}")

    else:
        print("Usage: structured_log.py [tail|aggregate|stats|search|export]")
        print("  tail [-n 20] [--source orchestrator] [--level ERROR]")
        print("  aggregate [--hours 24]")
        print("  stats [--hours 24]")
        print("  search <pattern>")
        print("  export")


if __name__ == "__main__":
    main()
