#!/usr/bin/env python3
"""
Mission Control Dashboard Generator — single-page view of the entire agent army.

Reads from workspace files and generates MISSION_CONTROL.md with:
- Agent status overview with mission statements
- Pipeline scores & priority calls
- Alerts & overdue items
- Recent activity log
- Cron schedule summary
- System health

Runs daily via cron or on-demand.
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
OUTPUT = WORKSPACE / "MISSION_CONTROL.md"

AGENTS = {
    "pipelinepilot": {
        "name": "PipelinePilot",
        "role": "CRM & Sales Intelligence",
        "mission": "Make Behavera's pipeline the most data-driven, zero-blind-spot sales machine in Czech HR tech.",
        "outputs": ["pipedrive/DEAL_SCORING.md", "pipedrive/PIPELINE_STATUS.md", "pipedrive/ENRICHMENT_LOG.md"],
    },
    "auditor": {
        "name": "Auditor",
        "role": "Sales Performance Coach",
        "mission": "Drive Josef to 8 demos/day, 40/week, and 500K+ CZK monthly closed revenue.",
        "outputs": ["reviews/daily-scorecard/SCOREBOARD.md"],
    },
    "copyagent": {
        "name": "CopyAgent",
        "role": "Sales Content Production",
        "mission": "Produce sales content that books demos and closes deals.",
        "outputs": ["drafts/", "templates/sales/"],
    },
    "growthlab": {
        "name": "GrowthLab",
        "role": "Market Intelligence",
        "mission": "Give Josef an unfair intelligence advantage over every competitor in Czech HR tech.",
        "outputs": ["intel/DAILY-INTEL.md", "intel/COMPETITOR_WATCH.md"],
    },
    "inboxforge": {
        "name": "InboxForge",
        "role": "Email Operations",
        "mission": "Inbox zero, zero missed opportunities.",
        "outputs": ["inbox/TRIAGE.md", "inbox/FOLLOW_UPS.md"],
    },
    "knowledgekeeper": {
        "name": "KnowledgeKeeper",
        "role": "Knowledge Operations",
        "mission": "Make the entire team smarter every day.",
        "outputs": ["knowledge/READING_TRACKER.md", "knowledge/AGENT_INSIGHTS.md"],
    },
    "calendarcaptain": {
        "name": "CalendarCaptain",
        "role": "Time & Meeting Prep",
        "mission": "Maximize Josef's selling time and ensure zero unprepared meetings.",
        "outputs": ["calendar/TODAY.md", "calendar/TOMORROW_PREP.md"],
    },
    "codex": {
        "name": "Codex",
        "role": "System Builder",
        "mission": "Build the most reliable, self-improving AI agent infrastructure.",
        "outputs": ["scripts/BUILD_LOG.md"],
    },
    "reviewer": {
        "name": "Reviewer",
        "role": "Quality Control",
        "mission": "Ensure every agent output is accurate, high-quality, and improving.",
        "outputs": ["reviews/HEALTH_REPORT.md", "reviews/SYSTEM_HEALTH.md"],
    },
}


def file_age_str(path: Path) -> str:
    if not path.exists():
        return "never"
    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    delta = datetime.now() - mtime
    if delta.days > 0:
        return f"{delta.days}d ago"
    hours = delta.seconds // 3600
    if hours > 0:
        return f"{hours}h ago"
    minutes = delta.seconds // 60
    return f"{minutes}m ago"


def read_first_lines(path: Path, n: int = 5) -> str:
    if not path.exists():
        return ""
    lines = path.read_text().splitlines()[:n]
    return "\n".join(lines)


def extract_section(path: Path, header: str, max_lines: int = 20) -> list:
    if not path.exists():
        return []
    lines = path.read_text().splitlines()
    collecting = False
    result = []
    for line in lines:
        if header.lower() in line.lower():
            collecting = True
            continue
        if collecting:
            if line.startswith("## ") and len(result) > 0:
                break
            result.append(line)
            if len(result) >= max_lines:
                break
    return result


def get_cron_count() -> int:
    try:
        result = subprocess.run(
            ["openclaw", "cron", "list", "--json"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if isinstance(data, list):
                return len(data)
    except Exception:
        pass
    return -1


def main():
    now = datetime.now()
    lines = [
        "# 🎛️ MISSION CONTROL",
        f"**Generated:** {now.strftime('%Y-%m-%d %H:%M')} | **System:** OpenClaw Kombucha Mode",
        "",
        "---",
        "",
    ]

    # === GLOBAL MISSION ===
    lines.append("## 🌟 Global Mission")
    lines.append("**Make Behavera the #1 employee assessment platform in Czech Republic through relentless, data-driven sales execution powered by an autonomous AI agent army.**")
    lines.append("")

    # === AGENT ARMY STATUS ===
    lines.append("## 🤖 Agent Army (9 Active)")
    lines.append("")
    lines.append("| Agent | Role | Mission | Last Output |")
    lines.append("|-------|------|---------|-------------|")

    for agent_id, info in AGENTS.items():
        # Check freshness of outputs
        freshest = "—"
        for out_path in info["outputs"]:
            p = WORKSPACE / out_path
            if p.is_dir():
                # Check any file in dir
                files = sorted(p.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True) if p.exists() else []
                if files:
                    age = file_age_str(files[0])
                    if freshest == "—" or "m ago" in age or "h ago" in age:
                        freshest = age
            elif p.exists():
                age = file_age_str(p)
                if freshest == "—" or "m ago" in age or "h ago" in age:
                    freshest = age

        lines.append(f"| **{info['name']}** | {info['role']} | {info['mission'][:60]}... | {freshest} |")

    lines.append("")

    # === PIPELINE SNAPSHOT ===
    scoring_path = WORKSPACE / "pipedrive" / "DEAL_SCORING.md"
    if scoring_path.exists():
        lines.append("## 📊 Pipeline Snapshot")
        lines.append("")

        # Extract summary
        summary_lines = extract_section(scoring_path, "## Summary", max_lines=10)
        for sl in summary_lines:
            if sl.strip():
                lines.append(sl)
        lines.append("")

        # Extract priority calls
        call_lines = extract_section(scoring_path, "TODAY'S PRIORITY CALLS", max_lines=15)
        if call_lines:
            lines.append("### 📞 Priority Calls")
            lines.append("")
            for cl in call_lines:
                if cl.strip():
                    lines.append(cl)
            lines.append("")

    # === ALERTS ===
    lines.append("## ⚡ Alerts")
    lines.append("")
    alerts = []

    # Check for overdue deals
    pipeline_path = WORKSPACE / "pipedrive" / "PIPELINE_STATUS.md"
    if pipeline_path.exists():
        overdue_lines = extract_section(pipeline_path, "Overdue", max_lines=10)
        for ol in overdue_lines:
            if ol.strip().startswith("- "):
                alerts.append(f"⏰ {ol.strip()[2:]}")

    # Check for missing next steps
    if pipeline_path.exists():
        no_next_lines = extract_section(pipeline_path, "No Next Step", max_lines=10)
        for nl in no_next_lines:
            if nl.strip().startswith("- "):
                alerts.append(f"⚠️ {nl.strip()[2:]}")

    # Check stale agent outputs
    for agent_id, info in AGENTS.items():
        for out_path in info["outputs"]:
            p = WORKSPACE / out_path
            if p.exists() and not p.is_dir():
                delta = datetime.now() - datetime.fromtimestamp(p.stat().st_mtime)
                if delta.days >= 3:
                    alerts.append(f"🔇 {info['name']}: `{out_path}` last updated {delta.days}d ago")

    if alerts:
        for a in alerts:
            lines.append(f"- {a}")
    else:
        lines.append("- All clear.")
    lines.append("")

    # === SCOREBOARD ===
    scoreboard_path = WORKSPACE / "reviews" / "daily-scorecard" / "SCOREBOARD.md"
    if scoreboard_path.exists():
        lines.append("## 🏆 Scoreboard")
        lines.append("")
        sb_lines = scoreboard_path.read_text().splitlines()[:20]
        for sl in sb_lines:
            if sl.strip():
                lines.append(sl)
        lines.append("")

    # === RECOMMENDED ACTIONS ===
    if pipeline_path.exists():
        rec_lines = extract_section(pipeline_path, "Recommended Actions", max_lines=10)
        if rec_lines:
            lines.append("## 💡 Recommended Actions")
            lines.append("")
            for rl in rec_lines:
                if rl.strip():
                    lines.append(rl)
            lines.append("")

    # === CRON STATUS ===
    cron_count = get_cron_count()
    lines.append("## ⏱️ System")
    lines.append("")
    if cron_count >= 0:
        lines.append(f"- **Active crons:** {cron_count}")
    lines.append(f"- **Agents:** {len(AGENTS)} active")
    lines.append(f"- **Mode:** Kombucha (autonomous)")
    lines.append(f"- **Last refresh:** {now.strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # === REVERSE PROMPT SECTION ===
    lines.append("## 🔄 Reverse Prompt (for idle agents)")
    lines.append("")
    lines.append("When any agent is idle, it should ask itself:")
    lines.append("> **\"What is 1 high-impact task I can do RIGHT NOW to advance my mission statement?\"**")
    lines.append("")
    lines.append("Then execute it immediately. This is the core of proactive behavior.")
    lines.append("")

    lines.append("---")
    lines.append(f"*Mission Control v1 — inspired by Alex Finn's Mission Control concept*")

    report = "\n".join(lines)
    OUTPUT.write_text(report)
    print(f"✅ MISSION_CONTROL.md generated ({len(lines)} lines)")
    return report


if __name__ == "__main__":
    main()
