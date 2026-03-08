#!/usr/bin/env python3
"""
Strategic Brief Generator — Weekly intelligence synthesis
==========================================================
Pulls data from all Clawdia subsystems (pipeline, win/loss, agents,
system health, scorecard, logs) and generates a comprehensive brief
with executive summary, analysis sections, and prioritized recommendations.

Optionally uses Ollama (llama3.1:8b) for synthesis when available.

Usage:
  python3 scripts/strategic_brief.py generate [--week current]
  python3 scripts/strategic_brief.py latest
  python3 scripts/strategic_brief.py history
"""

import json
import re
import sys
import urllib.request
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

WORKSPACE = Path(__file__).resolve().parents[1]
ENV_PATH = WORKSPACE / ".secrets" / "pipedrive.env"
BRIEF_DIR = WORKSPACE / "reviews" / "strategic_brief"
LOG_FILE = WORKSPACE / "logs" / "strategic-brief.log"

TODAY = date.today()
NOW = datetime.now()


def load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def blog(msg, level="INFO"):
    ts = NOW.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    try:
        if LOG_FILE.stat().st_size > 200_000:
            lines = LOG_FILE.read_text().splitlines()
            LOG_FILE.write_text("\n".join(lines[-500:]) + "\n")
    except OSError:
        pass


def safe_read_json(path):
    """Read a JSON file, return None on failure."""
    try:
        if path.exists():
            return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        blog(f"Failed to read {path}: {e}", "WARN")
    return None


def safe_read_md(path):
    """Read a markdown file, return empty string on failure."""
    try:
        if path.exists():
            return path.read_text()
    except OSError as e:
        blog(f"Failed to read {path}: {e}", "WARN")
    return ""


def ollama_synthesize(prompt, max_tokens=1024):
    """Use local Ollama to synthesize text. Returns None if unavailable."""
    try:
        data = json.dumps({
            "model": "llama3.1:8b",
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.3},
        }).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=60)
        result = json.loads(resp.read())
        return result.get("response", "").strip()
    except Exception:
        return None


# ── DATA COLLECTORS ───────────────────────────────────

class DataCollector:
    """Collect intelligence from all Clawdia subsystems."""

    def __init__(self):
        self.data = {}

    def collect_all(self):
        """Gather data from every available source."""
        self.data["pipeline"] = self._collect_pipeline()
        self.data["win_loss"] = self._collect_win_loss()
        self.data["agents"] = self._collect_agent_performance()
        self.data["system_health"] = self._collect_system_health()
        self.data["scorecard"] = self._collect_scorecard()
        self.data["logs"] = self._collect_log_stats()
        self.data["stale_deals"] = self._collect_stale_deals()
        return self.data

    def _collect_pipeline(self):
        """Read pipeline status, deal scoring, and velocity data."""
        result = {"available": False}

        # PIPELINE_STATUS.md
        pipeline_md = safe_read_md(WORKSPACE / "pipedrive" / "PIPELINE_STATUS.md")
        if pipeline_md:
            result["available"] = True
            result["pipeline_status_raw"] = pipeline_md[:2000]

            # Extract key numbers from markdown
            numbers = {}
            for line in pipeline_md.splitlines():
                if "Sales:" in line:
                    m = re.search(r"(\d+)\s*deals.*?([\d,]+)\s*CZK", line)
                    if m:
                        numbers["sales_count"] = int(m.group(1))
                        numbers["sales_value"] = int(m.group(2).replace(",", ""))
                if "Onboarding:" in line:
                    m = re.search(r"(\d+)\s*deals", line)
                    if m:
                        numbers["onboarding_count"] = int(m.group(1))
            result["numbers"] = numbers

        # DEAL_SCORING.md
        scoring_md = safe_read_md(WORKSPACE / "pipedrive" / "DEAL_SCORING.md")
        if scoring_md:
            result["available"] = True
            # Extract summary
            hot = len(re.findall(r"HOT", scoring_md))
            warm = len(re.findall(r"WARM", scoring_md))
            cool = len(re.findall(r"COOL", scoring_md))
            cold = len(re.findall(r"COLD \(", scoring_md))

            # Better extraction from summary section
            for line in scoring_md.splitlines():
                if "HOT (80+):" in line:
                    m = re.search(r"\*\*(\d+)\*\*", line)
                    if m:
                        hot = int(m.group(1))
                if "WARM (60-79):" in line:
                    m = re.search(r"\*\*(\d+)\*\*", line)
                    if m:
                        warm = int(m.group(1))
                if "COOL (40-59):" in line:
                    m = re.search(r"\*\*(\d+)\*\*", line)
                    if m:
                        cool = int(m.group(1))
                if "COLD (<40):" in line:
                    m = re.search(r"\*\*(\d+)\*\*", line)
                    if m:
                        cold = int(m.group(1))
                if "pipeline value:" in line.lower():
                    m = re.search(r"([\d,]+)\s*CZK", line)
                    if m:
                        result.setdefault("numbers", {})["pipeline_value"] = int(m.group(1).replace(",", ""))

            result["scoring"] = {"hot": hot, "warm": warm, "cool": cool, "cold": cold}

        # deal_velocity.json
        velocity = safe_read_json(WORKSPACE / "pipedrive" / "deal_velocity.json")
        if velocity:
            result["available"] = True
            deals = velocity.get("deals", {})
            stalling = sum(1 for d in deals.values() if d.get("velocity_status") == "stalling")
            hot_vel = sum(1 for d in deals.values() if d.get("velocity_status") == "hot")
            result["velocity"] = {
                "total_tracked": len(deals),
                "stalling": stalling,
                "hot": hot_vel,
                "normal": len(deals) - stalling - hot_vel,
                "stage_stats": velocity.get("stage_stats", {}),
            }

        return result

    def _collect_win_loss(self):
        """Read win/loss patterns."""
        result = {"available": False}

        patterns = safe_read_json(WORKSPACE / "reviews" / "win_loss" / "patterns.json")
        if patterns:
            result["available"] = True
            result["total_analyzed"] = patterns.get("total_analyzed", 0)
            result["win_rate"] = patterns.get("overall_win_rate", 0)
            result["won"] = patterns.get("won", 0)
            result["lost"] = patterns.get("lost", 0)
            result["insights"] = patterns.get("insights", [])[:3]
            result["recommendations"] = patterns.get("recommendations", [])[:3]
            result["correlations"] = patterns.get("correlations", {})

        # Count individual analyses
        wl_dir = WORKSPACE / "reviews" / "win_loss"
        if wl_dir.exists():
            analyses = [f for f in wl_dir.glob("*.json") if f.name != "patterns.json"]
            result["analysis_count"] = len(analyses)

            # Summarize recent wins/losses
            recent = []
            for f in sorted(analyses, key=lambda x: x.stat().st_mtime, reverse=True)[:5]:
                try:
                    data = json.loads(f.read_text())
                    recent.append({
                        "title": data.get("title", "?"),
                        "outcome": data.get("outcome", "?"),
                        "value": data.get("value", 0),
                        "total_days": data.get("total_days", 0),
                    })
                except (json.JSONDecodeError, OSError):
                    pass
            result["recent_deals"] = recent

        return result

    def _collect_agent_performance(self):
        """Read agent performance data."""
        result = {"available": False}

        # Check agent-performance.json (may not exist yet)
        perf = safe_read_json(WORKSPACE / "control-plane" / "agent-performance.json")
        if perf:
            result["available"] = True
            result["data"] = perf

        # Also extract from EXECUTION_STATE.json
        exec_state = safe_read_json(WORKSPACE / "knowledge" / "EXECUTION_STATE.json")
        if exec_state:
            result["available"] = True
            health = exec_state.get("system_health", {})
            result["agents"] = {}
            for agent, info in health.items():
                result["agents"][agent] = {
                    "status": info.get("status", "UNKNOWN"),
                    "age_hours": round(info.get("age_hours", 0), 1),
                }

            counts = exec_state.get("counts", {})
            result["task_counts"] = counts
            result["stale_outputs"] = exec_state.get("stale_outputs", [])
            result["approval_queue"] = exec_state.get("approval_queue", {})

        return result

    def _collect_system_health(self):
        """System health from EXECUTION_STATE and heartbeat."""
        result = {"available": False}

        exec_state = safe_read_json(WORKSPACE / "knowledge" / "EXECUTION_STATE.json")
        if exec_state:
            result["available"] = True
            counts = exec_state.get("counts", {})
            result["healthy_agents"] = counts.get("healthy_agents", 0)
            result["total_agents"] = counts.get("total_agents", 0)
            result["stale_outputs"] = counts.get("stale_outputs", 0)
            result["blocked_tasks"] = counts.get("blocked", 0)
            result["last_autopilot"] = exec_state.get("last_autopilot_run", "")
            result["last_orchestrator"] = exec_state.get("last_orchestrator_run", "")

        # Heartbeat
        heartbeat = safe_read_md(WORKSPACE / "memory" / "HEARTBEAT.md")
        if heartbeat:
            result["available"] = True
            result["heartbeat_snippet"] = heartbeat[:500]

            # Extract health ratio
            m = re.search(r"(\d+)/(\d+)", heartbeat)
            if m:
                result["heartbeat_healthy"] = int(m.group(1))
                result["heartbeat_total"] = int(m.group(2))

        return result

    def _collect_scorecard(self):
        """Scorecard data from score_state.json."""
        result = {"available": False}

        state = safe_read_json(WORKSPACE / "reviews" / "daily-scorecard" / "score_state.json")
        if state:
            result["available"] = True
            result["total_points"] = state.get("total_points", 0)
            result["current_streak"] = state.get("current_streak", 0)
            result["best_streak"] = state.get("best_streak", 0)
            result["title"] = state.get("title", "?")
            result["achievements"] = len(state.get("achievements", []))

            # This week's scores
            scores = state.get("daily_scores", {})
            monday = TODAY - timedelta(days=TODAY.weekday())
            week_scores = {}
            for i in range(7):
                d = (monday + timedelta(days=i)).isoformat()
                if d in scores:
                    week_scores[d] = scores[d]
            result["week_scores"] = week_scores
            result["week_total"] = sum(week_scores.values())

            # Previous week for comparison
            prev_monday = monday - timedelta(days=7)
            prev_scores = {}
            for i in range(7):
                d = (prev_monday + timedelta(days=i)).isoformat()
                if d in scores:
                    prev_scores[d] = scores[d]
            result["prev_week_total"] = sum(prev_scores.values())

        return result

    def _collect_log_stats(self):
        """Aggregate log statistics."""
        result = {"available": False}

        try:
            sys.path.insert(0, str(WORKSPACE / "scripts"))
            from structured_log import LogAggregator
            agg = LogAggregator()
            stats = agg.stats(hours=168)  # Last week
            result["available"] = True
            result.update(stats)
        except Exception as e:
            blog(f"Log stats collection failed: {e}", "WARN")

            # Fallback: count log files manually
            log_dir = WORKSPACE / "logs"
            if log_dir.exists():
                result["available"] = True
                result["log_files"] = len(list(log_dir.glob("*")))
                total_size = sum(f.stat().st_size for f in log_dir.glob("*") if f.is_file())
                result["total_log_size_kb"] = round(total_size / 1024, 1)

        return result

    def _collect_stale_deals(self):
        """Read stale deals info."""
        result = {"available": False}

        stale_md = safe_read_md(WORKSPACE / "pipedrive" / "STALE_DEALS.md")
        if stale_md:
            result["available"] = True
            result["content_snippet"] = stale_md[:1000]

            # Count stale deals
            stale_count = len(re.findall(r"^\|.*\|.*\|.*\|.*\|", stale_md, re.MULTILINE))
            stale_count = max(0, stale_count - 2)  # minus header rows
            result["stale_count"] = stale_count

        return result


# ── BRIEF GENERATOR ───────────────────────────────────

class StrategicBriefGenerator:
    """Generate weekly strategic brief from all collected intelligence."""

    def __init__(self):
        self.collector = DataCollector()
        self.use_ollama = False

    def generate(self, week_label="current"):
        """Generate the strategic brief."""
        blog("Generating strategic brief...")

        # Collect all data
        data = self.collector.collect_all()

        # Generate sections
        sections = []
        sections.append(self._header(week_label))
        sections.append(self._executive_summary(data))
        sections.append(self._pipeline_health(data))
        sections.append(self._wins_and_losses(data))
        sections.append(self._agent_performance(data))
        sections.append(self._system_health(data))
        sections.append(self._recommendations(data))
        sections.append(self._footer())

        brief = "\n\n".join(sections)

        # Optionally enhance with Ollama
        if self.use_ollama:
            enhanced = self._ollama_enhance(brief, data)
            if enhanced:
                brief = enhanced

        # Save
        BRIEF_DIR.mkdir(parents=True, exist_ok=True)
        monday = TODAY - timedelta(days=TODAY.weekday())
        filename = f"week_{monday.isoformat()}.md"
        out_path = BRIEF_DIR / filename
        out_path.write_text(brief)

        blog(f"Brief saved: {out_path}")
        return out_path, brief

    def _header(self, week_label):
        monday = TODAY - timedelta(days=TODAY.weekday())
        sunday = monday + timedelta(days=6)
        return f"""# Strategic Brief — Week of {monday.strftime('%B %-d, %Y')}

> Generated: {NOW.strftime('%Y-%m-%d %H:%M')}
> Period: {monday} to {sunday}
> System: Clawdia Intelligence Engine"""

    def _executive_summary(self, data):
        """3 bullet points: the most important things."""
        bullets = []

        # Pipeline bullet
        pipeline = data.get("pipeline", {})
        if pipeline.get("available"):
            numbers = pipeline.get("numbers", {})
            scoring = pipeline.get("scoring", {})
            sales_count = numbers.get("sales_count", "?")
            sales_value = numbers.get("sales_value", 0) or numbers.get("pipeline_value", 0)
            hot = scoring.get("hot", 0)
            val_str = f"{sales_value:,.0f} CZK" if sales_value else "value TBD"
            bullets.append(f"**Pipeline:** {sales_count} active sales deals ({val_str}), {hot} hot deals ready to close")

        # Win/loss bullet
        wl = data.get("win_loss", {})
        if wl.get("available"):
            win_rate = wl.get("win_rate", 0)
            recent = wl.get("recent_deals", [])
            recent_won = sum(1 for d in recent if d["outcome"] == "WON")
            recent_lost = sum(1 for d in recent if d["outcome"] == "LOST")
            bullets.append(f"**Win rate:** {win_rate}% overall ({recent_won} recent wins, {recent_lost} recent losses)")
        else:
            bullets.append("**Win/Loss:** No analysis data yet -- run `win_loss_analysis.py analyze` to build baseline")

        # System health bullet
        health = data.get("system_health", {})
        if health.get("available"):
            healthy = health.get("healthy_agents", 0)
            total = health.get("total_agents", 0)
            stale = health.get("stale_outputs", 0)
            bullets.append(f"**System:** {healthy}/{total} agents healthy, {stale} stale outputs need attention")

        # Scorecard bullet as fallback
        if len(bullets) < 3:
            sc = data.get("scorecard", {})
            if sc.get("available"):
                bullets.append(f"**Momentum:** {sc.get('week_total', 0)} points this week, {sc.get('current_streak', 0)}-day streak ({sc.get('title', '?')})")

        # Ensure we have 3
        while len(bullets) < 3:
            bullets.append("**Data gap:** Some subsystems have no data yet")

        lines = ["## Executive Summary", ""]
        for bullet in bullets[:3]:
            lines.append(f"- {bullet}")

        return "\n".join(lines)

    def _pipeline_health(self, data):
        """Deals by stage, velocity, value."""
        pipeline = data.get("pipeline", {})
        lines = ["## Pipeline Health"]

        if not pipeline.get("available"):
            lines.append("\n_No pipeline data available. Run `pipedrive_lead_scorer.py` first._")
            return "\n".join(lines)

        # Deal counts and scoring
        scoring = pipeline.get("scoring", {})
        numbers = pipeline.get("numbers", {})

        lines.append("")
        lines.append("### Deal Distribution")
        lines.append("")
        lines.append("| Category | Count |")
        lines.append("|----------|-------|")
        if scoring:
            lines.append(f"| Hot (80+) | {scoring.get('hot', 0)} |")
            lines.append(f"| Warm (60-79) | {scoring.get('warm', 0)} |")
            lines.append(f"| Cool (40-59) | {scoring.get('cool', 0)} |")
            lines.append(f"| Cold (<40) | {scoring.get('cold', 0)} |")
        if numbers.get("sales_count"):
            lines.append(f"| **Total Sales** | **{numbers['sales_count']}** |")
        if numbers.get("onboarding_count"):
            lines.append(f"| Onboarding | {numbers['onboarding_count']} |")

        # Pipeline value
        val = numbers.get("sales_value", 0) or numbers.get("pipeline_value", 0)
        if val:
            lines.append(f"\n**Pipeline Value:** {val:,.0f} CZK")

        # Velocity
        velocity = pipeline.get("velocity", {})
        if velocity:
            lines.append("")
            lines.append("### Velocity")
            lines.append("")
            lines.append(f"- Tracked: {velocity.get('total_tracked', 0)} deals")
            lines.append(f"- Stalling (>1.5x avg): {velocity.get('stalling', 0)}")
            lines.append(f"- Hot (<0.5x avg): {velocity.get('hot', 0)}")
            lines.append(f"- Normal: {velocity.get('normal', 0)}")

            # Stage averages
            stage_stats = velocity.get("stage_stats", {})
            if stage_stats:
                lines.append("")
                lines.append("### Stage Averages (days)")
                lines.append("")
                lines.append("| Stage | Avg | Median | Deals |")
                lines.append("|-------|-----|--------|-------|")
                for sid, stats in sorted(stage_stats.items(), key=lambda x: x[1].get("stage_name", "")):
                    lines.append(f"| {stats['stage_name']} | {stats['avg']} | {stats['median']} | {stats['deal_count']} |")

        # Stale deals
        stale = data.get("stale_deals", {})
        if stale.get("available") and stale.get("stale_count", 0) > 0:
            lines.append(f"\n**Stale deals requiring action:** {stale['stale_count']}")

        return "\n".join(lines)

    def _wins_and_losses(self, data):
        """From win_loss_analysis patterns."""
        wl = data.get("win_loss", {})
        lines = ["## Key Wins & Losses"]

        if not wl.get("available"):
            lines.append("\n_No win/loss analysis data available. Run `win_loss_analysis.py analyze` to generate._")
            return "\n".join(lines)

        lines.append("")
        lines.append(f"**Win Rate:** {wl.get('win_rate', 0)}% ({wl.get('won', 0)} won / {wl.get('lost', 0)} lost)")
        lines.append(f"**Total Analyzed:** {wl.get('total_analyzed', 0)} deals")

        # Recent deals
        recent = wl.get("recent_deals", [])
        if recent:
            lines.append("")
            lines.append("### Recent Closed Deals")
            lines.append("")
            lines.append("| Deal | Outcome | Value | Cycle |")
            lines.append("|------|---------|-------|-------|")
            for d in recent:
                val = f"{d['value']:,.0f} CZK" if d.get("value") else "--"
                cycle = f"{d['total_days']}d" if d.get("total_days") else "--"
                outcome_marker = "WON" if d["outcome"] == "WON" else "LOST"
                lines.append(f"| {d['title'][:30]} | {outcome_marker} | {val} | {cycle} |")

        # Key insights
        insights = wl.get("insights", [])
        if insights:
            lines.append("")
            lines.append("### Key Insights")
            lines.append("")
            for insight in insights:
                lines.append(f"- **{insight.get('type', '?').replace('_', ' ').title()}:** {insight.get('finding', '')}")
                lines.append(f"  - Action: {insight.get('action', '')}")

        return "\n".join(lines)

    def _agent_performance(self, data):
        """Top/bottom performers from agent data."""
        agents_data = data.get("agents", {})
        lines = ["## Agent Performance"]

        if not agents_data.get("available"):
            lines.append("\n_No agent performance data available._")
            return "\n".join(lines)

        agents = agents_data.get("agents", {})
        if agents:
            lines.append("")
            lines.append("| Agent | Status | Last Active |")
            lines.append("|-------|--------|------------|")

            # Sort: healthy first, then stale
            sorted_agents = sorted(agents.items(), key=lambda x: (0 if x[1]["status"] == "OK" else 1, x[0]))
            for agent, info in sorted_agents:
                status = info["status"]
                age = info["age_hours"]
                if age < 1:
                    age_str = f"{age * 60:.0f}m ago"
                elif age < 24:
                    age_str = f"{age:.1f}h ago"
                else:
                    age_str = f"{age / 24:.1f}d ago"

                status_indicator = "OK" if status == "OK" else "STALE"
                lines.append(f"| {agent} | {status_indicator} | {age_str} |")

        # Task counts
        task_counts = agents_data.get("task_counts", {})
        if task_counts:
            lines.append("")
            lines.append("### Task Summary")
            lines.append("")
            lines.append(f"- Open: {task_counts.get('open', 0)}")
            lines.append(f"- Blocked: {task_counts.get('blocked', 0)}")
            lines.append(f"- Stale outputs: {task_counts.get('stale_outputs', 0)}")

        # Stale outputs detail
        stale = agents_data.get("stale_outputs", [])
        if stale:
            lines.append("")
            lines.append("### Stale Outputs")
            lines.append("")
            for item in stale:
                lines.append(f"- **{item.get('agent', '?')}**: {item.get('path', '?')} ({item.get('reason', '?')})")

        return "\n".join(lines)

    def _system_health(self, data):
        """Uptime, errors, recovery."""
        health = data.get("system_health", {})
        logs = data.get("logs", {})
        scorecard = data.get("scorecard", {})

        lines = ["## System Health"]

        if not health.get("available") and not logs.get("available"):
            lines.append("\n_No system health data available._")
            return "\n".join(lines)

        if health.get("available"):
            lines.append("")
            healthy = health.get("healthy_agents", health.get("heartbeat_healthy", 0))
            total = health.get("total_agents", health.get("heartbeat_total", 0))
            lines.append(f"**Agents:** {healthy}/{total} healthy")
            lines.append(f"**Blocked tasks:** {health.get('blocked_tasks', 0)}")
            lines.append(f"**Stale outputs:** {health.get('stale_outputs', 0)}")

            if health.get("last_orchestrator"):
                lines.append(f"**Last orchestrator run:** {health['last_orchestrator'][:19]}")

        # Log stats
        if logs.get("available"):
            lines.append("")
            lines.append("### Log Activity (last 7 days)")
            lines.append("")
            lines.append(f"- Total entries: {logs.get('total_entries', 0)}")
            lines.append(f"- Errors: {logs.get('error_count', 0)}")
            lines.append(f"- Warnings: {logs.get('warn_count', 0)}")

            by_source = logs.get("by_source", {})
            if by_source:
                lines.append("")
                lines.append("| Source | Entries |")
                lines.append("|--------|---------|")
                for src, count in sorted(by_source.items(), key=lambda x: -x[1])[:7]:
                    lines.append(f"| {src} | {count} |")

        # Scorecard
        if scorecard.get("available"):
            lines.append("")
            lines.append("### Scorecard")
            lines.append("")
            lines.append(f"- Total points: {scorecard.get('total_points', 0):,}")
            lines.append(f"- This week: {scorecard.get('week_total', 0)} pts")
            prev = scorecard.get("prev_week_total", 0)
            curr = scorecard.get("week_total", 0)
            if prev > 0:
                trend = ((curr - prev) / prev) * 100
                lines.append(f"- vs last week: {'+' if trend > 0 else ''}{trend:.0f}%")
            lines.append(f"- Streak: {scorecard.get('current_streak', 0)} days")
            lines.append(f"- Level: {scorecard.get('title', '?')}")
            lines.append(f"- Achievements: {scorecard.get('achievements', 0)}")

        return "\n".join(lines)

    def _recommendations(self, data):
        """Top 5 actionable, prioritized recommendations."""
        recs = []

        # From win/loss patterns
        wl = data.get("win_loss", {})
        wl_recs = wl.get("recommendations", [])
        for r in wl_recs[:2]:
            recs.append({
                "source": "win/loss analysis",
                "area": r.get("area", "general"),
                "recommendation": r.get("recommendation", ""),
                "priority": "high",
            })

        # From system health
        health = data.get("system_health", {})
        if health.get("stale_outputs", 0) >= 3:
            recs.append({
                "source": "system health",
                "area": "operations",
                "recommendation": f"Fix {health['stale_outputs']} stale outputs -- agents are falling behind on their deliverables",
                "priority": "high",
            })

        agents_data = data.get("agents", {})
        stale_agents = [a for a, info in agents_data.get("agents", {}).items() if info.get("status") == "STALE"]
        if stale_agents:
            recs.append({
                "source": "agent health",
                "area": "infrastructure",
                "recommendation": f"Restart stale agents: {', '.join(stale_agents)}",
                "priority": "medium",
            })

        # From pipeline
        pipeline = data.get("pipeline", {})
        velocity = pipeline.get("velocity", {})
        if velocity.get("stalling", 0) >= 3:
            recs.append({
                "source": "deal velocity",
                "area": "sales",
                "recommendation": f"{velocity['stalling']} deals stalling -- review and re-engage or disqualify",
                "priority": "high",
            })

        stale = data.get("stale_deals", {})
        if stale.get("stale_count", 0) > 0:
            recs.append({
                "source": "pipeline hygiene",
                "area": "sales",
                "recommendation": f"Clean up {stale['stale_count']} stale deals -- move forward or archive",
                "priority": "medium",
            })

        # Scoring hot deals
        scoring = pipeline.get("scoring", {})
        if scoring.get("hot", 0) > 0:
            recs.append({
                "source": "deal scoring",
                "area": "sales",
                "recommendation": f"Focus this week on {scoring['hot']} HOT deals -- they're ready to close",
                "priority": "high",
            })

        # Scorecard engagement
        sc = data.get("scorecard", {})
        if sc.get("available") and sc.get("week_total", 0) < 100:
            recs.append({
                "source": "scorecard",
                "area": "productivity",
                "recommendation": "Low activity this week -- check automation health and re-engage",
                "priority": "medium",
            })

        # Blocked tasks
        if agents_data.get("task_counts", {}).get("blocked", 0) > 0:
            recs.append({
                "source": "task management",
                "area": "operations",
                "recommendation": f"Unblock {agents_data['task_counts']['blocked']} blocked task(s) -- may need manual approval",
                "priority": "high",
            })

        # Sort by priority and take top 5
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recs.sort(key=lambda x: priority_order.get(x.get("priority", "low"), 2))
        recs = recs[:5]

        lines = ["## Top 5 Recommendations"]
        if not recs:
            lines.append("\n_No actionable recommendations -- all systems look good._")
            return "\n".join(lines)

        lines.append("")
        for i, rec in enumerate(recs, 1):
            prio = rec.get("priority", "medium").upper()
            lines.append(f"**{i}. [{prio}] {rec.get('area', 'general').title()}**")
            lines.append(f"   {rec['recommendation']}")
            lines.append(f"   _Source: {rec['source']}_")
            lines.append("")

        return "\n".join(lines)

    def _footer(self):
        return f"""---

*Generated by Clawdia Strategic Brief Engine | {NOW.strftime('%Y-%m-%d %H:%M')}*
*Data sources: Pipeline, Win/Loss, Agent Performance, System Health, Scorecard, Logs*"""

    def _ollama_enhance(self, brief, data):
        """Use Ollama to add an AI-synthesized executive insight."""
        prompt = f"""You are a strategic business analyst. Based on this weekly strategic brief,
write 2-3 sentences of executive insight — what's the single most important thing
the founder should focus on this week and why. Be specific and actionable.

Brief summary:
- Pipeline: {data.get('pipeline', {}).get('numbers', {})}
- Win rate: {data.get('win_loss', {}).get('win_rate', 'N/A')}%
- Healthy agents: {data.get('system_health', {}).get('healthy_agents', '?')}/{data.get('system_health', {}).get('total_agents', '?')}
- Week score: {data.get('scorecard', {}).get('week_total', 'N/A')} pts

Write ONLY the insight, no headers or formatting."""

        insight = ollama_synthesize(prompt, max_tokens=256)
        if insight and len(insight) > 20:
            # Insert after executive summary
            marker = "## Pipeline Health"
            enhanced = brief.replace(
                marker,
                f"### AI Insight\n\n_{insight}_\n\n{marker}"
            )
            return enhanced
        return None

    def get_latest(self):
        """Get the most recent brief."""
        if not BRIEF_DIR.exists():
            return None, None

        briefs = sorted(BRIEF_DIR.glob("week_*.md"), reverse=True)
        if not briefs:
            return None, None

        latest = briefs[0]
        return latest, latest.read_text()

    def get_history(self):
        """List all generated briefs."""
        if not BRIEF_DIR.exists():
            return []

        briefs = sorted(BRIEF_DIR.glob("week_*.md"), reverse=True)
        history = []
        for b in briefs:
            size = b.stat().st_size
            mtime = datetime.fromtimestamp(b.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            history.append({
                "file": b.name,
                "path": str(b),
                "size_kb": round(size / 1024, 1),
                "generated": mtime,
            })
        return history


# ── CLI ───────────────────────────────────────────────

def main():
    generator = StrategicBriefGenerator()

    if len(sys.argv) < 2:
        print("Usage: strategic_brief.py [generate|latest|history]")
        print("  generate [--week current] [--ollama]  — Generate this week's brief")
        print("  latest                                 — Show most recent brief")
        print("  history                                — List all briefs")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "generate":
        week = "current"
        if "--week" in sys.argv:
            idx = sys.argv.index("--week")
            if idx + 1 < len(sys.argv):
                week = sys.argv[idx + 1]

        if "--ollama" in sys.argv:
            generator.use_ollama = True

        print("Generating strategic brief...")
        path, brief = generator.generate(week)
        print(f"\nBrief saved to: {path}")
        print(f"Size: {len(brief):,} chars")
        print("\n" + "=" * 70)
        print(brief)
        print("=" * 70)

    elif cmd == "latest":
        path, brief = generator.get_latest()
        if not brief:
            print("No briefs generated yet. Run 'generate' first.")
            sys.exit(0)
        print(f"Latest brief: {path}\n")
        print(brief)

    elif cmd == "history":
        history = generator.get_history()
        if not history:
            print("No briefs generated yet.")
            sys.exit(0)

        print(f"\nSTRATEGIC BRIEF HISTORY ({len(history)} briefs)")
        print("-" * 60)
        print(f"  {'Week':<25} {'Size':>8} {'Generated':<20}")
        print("-" * 60)
        for h in history:
            print(f"  {h['file']:<25} {h['size_kb']:>6.1f}KB {h['generated']:<20}")
        print(f"\nBriefs stored in: {BRIEF_DIR}")

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: strategic_brief.py [generate|latest|history]")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        LOG_FILE.parent.mkdir(exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] [FATAL] {e}\n")
            f.write(traceback.format_exc() + "\n")
        print(f"FATAL: {e}", file=sys.stderr)
        raise
