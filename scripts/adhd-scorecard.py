#!/usr/bin/env python3
"""
ADHD Sales Scorecard v2 — Gamification for Josef
=================================================
Tracks daily wins, streaks, achievements, and weekly reports.
Makes sales work feel like a game with real dopamine hits.
"""

import json
import os
from datetime import datetime, date, timedelta
from pathlib import Path

BASE = Path("/Users/josefhofman/Clawdia")
SCORECARD_FILE = BASE / "reviews" / "daily-scorecard" / "SCOREBOARD.md"
STATE_FILE = BASE / "reviews" / "daily-scorecard" / "score_state.json"
WEEKLY_FILE = BASE / "reviews" / "daily-scorecard" / "WEEKLY_REPORT.md"


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {
        "total_points": 0,
        "current_streak": 0,
        "best_streak": 0,
        "level": 1,
        "title": "Sales Padawan",
        "daily_scores": {},
        "achievements": [],
        "weekly_history": [],
    }


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def calculate_daily_score():
    """Calculate today's score based on actual activity"""
    today = date.today().isoformat()
    score = 0
    activities = []

    checks = [
        ("knowledge/USER_DIGEST_AM.md", "Morning briefing generated", 10),
        ("pipedrive/PIPELINE_STATUS.md", "Pipeline reviewed", 15),
        ("pipedrive/STALE_DEALS.md", "Stale deals identified", 10),
        ("pipedrive/DEAL_SCORING.md", "Lead scoring complete", 10),
        ("inbox/INBOX_DIGEST.md", "Inbox triaged", 15),
        ("intel/DAILY-INTEL.md", "Market intel updated", 10),
        ("calendar/TODAY.md", "Daily plan created", 10),
    ]

    for filepath, label, points in checks:
        full_path = BASE / filepath
        if full_path.exists():
            size = full_path.stat().st_size
            mod = datetime.fromtimestamp(full_path.stat().st_mtime).date().isoformat()
            if mod == today and size > 50:
                score += points
                activities.append(f"{label} (+{points})")

    # Approval queue activity
    approved_dir = BASE / "approval-queue" / "approved"
    if approved_dir.exists():
        today_approved = sum(
            1 for f in approved_dir.iterdir()
            if f.is_file() and datetime.fromtimestamp(f.stat().st_mtime).date().isoformat() == today
        )
        if today_approved > 0:
            bonus = today_approved * 5
            score += bonus
            activities.append(f"Approved {today_approved} items (+{bonus})")

    # Drafts created today
    drafts_dir = BASE / "drafts"
    if drafts_dir.exists():
        today_drafts = sum(
            1 for f in drafts_dir.glob("*.md")
            if datetime.fromtimestamp(f.stat().st_mtime).date().isoformat() == today
        )
        if today_drafts > 0:
            bonus = today_drafts * 10
            score += bonus
            activities.append(f"Created {today_drafts} drafts (+{bonus})")

    # Trigger events processed
    trigger_dir = BASE / "triggers" / "processed"
    if trigger_dir.exists():
        today_triggers = sum(
            1 for f in trigger_dir.glob("*.json")
            if datetime.fromtimestamp(f.stat().st_mtime).date().isoformat() == today
        )
        if today_triggers > 0:
            bonus = min(today_triggers * 3, 15)
            score += bonus
            activities.append(f"Agent triggers fired ({today_triggers}) (+{bonus})")

    # System health bonus
    heartbeat = BASE / "memory" / "HEARTBEAT.md"
    if heartbeat.exists():
        content = heartbeat.read_text()
        if "7/7" in content:
            score += 20
            activities.append("All 7 agents healthy! (+20)")
        elif "6/7" in content:
            score += 15
            activities.append("6/7 agents healthy (+15)")
        elif "5/7" in content:
            score += 10
            activities.append("5/7 agents healthy (+10)")

    # Recovery bonus
    recovery_log = BASE / "logs" / "recovery.log"
    if recovery_log.exists():
        today_recoveries = sum(
            1 for line in recovery_log.read_text().splitlines()
            if today in line and "SUCCESS" in line
        )
        if today_recoveries > 0:
            bonus = today_recoveries * 8
            score += bonus
            activities.append(f"Auto-recovered {today_recoveries} agents (+{bonus})")

    return score, activities


LEVELS = [
    (0, "Sales Padawan", "You're just getting started"),
    (100, "Deal Hunter", "You smell opportunities"),
    (300, "Pipeline Warrior", "CRM is your weapon"),
    (600, "Revenue Ninja", "Silent but effective"),
    (1000, "Sales Samurai", "Honor in every deal"),
    (1500, "Pipeline Jedi", "The force is with you"),
    (2500, "Deal Machine", "Unstoppable momentum"),
    (4000, "Revenue Dragon", "Fear the pipeline"),
    (6000, "Sales Legend", "They write songs about you"),
    (10000, "Pipeline God", "Mere mortals bow"),
]


def get_level_info(total_points):
    current = LEVELS[0]
    next_level = LEVELS[1] if len(LEVELS) > 1 else None

    for i, (threshold, title, desc) in enumerate(LEVELS):
        if total_points >= threshold:
            current = (threshold, title, desc)
            next_level = LEVELS[i + 1] if i + 1 < len(LEVELS) else None

    return current, next_level


# Achievement definitions: (id, name, description, check_function)
ACHIEVEMENTS = {
    "first_50_day": ("First 50-Point Day", "Score 50+ points in a single day"),
    "first_100_day": ("Century Club", "Score 100+ points in a single day"),
    "3_day_streak": ("On Fire", "3-day streak"),
    "5_day_streak": ("Unstoppable", "5-day streak"),
    "7_day_streak": ("Week Warrior", "7-day streak"),
    "14_day_streak": ("Fortnight Force", "14-day streak"),
    "30_day_streak": ("Monthly Monster", "30-day streak"),
    "1000_points": ("Grand", "Reach 1,000 total points"),
    "2500_points": ("Elite", "Reach 2,500 total points"),
    "5000_points": ("Legendary", "Reach 5,000 total points"),
    "10000_points": ("Transcendent", "Reach 10,000 total points"),
    "all_agents_healthy": ("Army Commander", "All 7 agents healthy in one check"),
    "first_recovery": ("Phoenix", "Auto-recover a stale agent"),
    "week_500": ("Weekly Crusher", "500+ points in a single week"),
    "consistent_5": ("Consistency King", "Score 30+ pts for 5 consecutive days"),
}


def check_achievements(state, daily_score, activities):
    new = []

    def unlock(achievement_id):
        if achievement_id not in state.get("achievements", []):
            new.append(achievement_id)
            state.setdefault("achievements", []).append(achievement_id)

    streak = state.get("current_streak", 0)

    # Score-based
    if daily_score >= 50:
        unlock("first_50_day")
    if daily_score >= 100:
        unlock("first_100_day")

    # Streak-based
    if streak >= 3: unlock("3_day_streak")
    if streak >= 5: unlock("5_day_streak")
    if streak >= 7: unlock("7_day_streak")
    if streak >= 14: unlock("14_day_streak")
    if streak >= 30: unlock("30_day_streak")

    # Total points
    total = state.get("total_points", 0)
    if total >= 1000: unlock("1000_points")
    if total >= 2500: unlock("2500_points")
    if total >= 5000: unlock("5000_points")
    if total >= 10000: unlock("10000_points")

    # Activity-based
    if any("7 agents healthy" in a for a in activities):
        unlock("all_agents_healthy")
    if any("Auto-recovered" in a for a in activities):
        unlock("first_recovery")

    # Weekly score
    scores = state.get("daily_scores", {})
    today = date.today()
    week_pts = sum(
        scores.get((today - timedelta(days=i)).isoformat(), 0)
        for i in range(7)
    )
    if week_pts >= 500:
        unlock("week_500")

    # Consistency: 5 consecutive days of 30+
    consecutive_30 = 0
    for i in range(30):
        d = (today - timedelta(days=i)).isoformat()
        if scores.get(d, 0) >= 30:
            consecutive_30 += 1
        else:
            break
    if consecutive_30 >= 5:
        unlock("consistent_5")

    return new


def generate_weekly_report(state):
    """Generate weekly summary report"""
    today = date.today()
    scores = state.get("daily_scores", {})

    # This week (Mon-Sun)
    monday = today - timedelta(days=today.weekday())
    week_days = [(monday + timedelta(days=i)).isoformat() for i in range(7)]
    week_scores = [scores.get(d, 0) for d in week_days]
    week_total = sum(week_scores)

    # Last week
    last_monday = monday - timedelta(days=7)
    last_week_days = [(last_monday + timedelta(days=i)).isoformat() for i in range(7)]
    last_week_total = sum(scores.get(d, 0) for d in last_week_days)

    # Trend
    if last_week_total > 0:
        trend_pct = ((week_total - last_week_total) / last_week_total) * 100
        trend = f"+{trend_pct:.0f}%" if trend_pct > 0 else f"{trend_pct:.0f}%"
    else:
        trend = "N/A"

    # Best day this week
    best_day_idx = week_scores.index(max(week_scores)) if any(week_scores) else 0
    best_day_name = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][best_day_idx]

    # Active days
    active_days = sum(1 for s in week_scores if s > 0)

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    report = f"""# Weekly Report — Week of {monday}

## Overview
| Metric | Value |
|--------|-------|
| Total Points | {week_total} |
| vs Last Week | {trend} |
| Active Days | {active_days}/7 |
| Best Day | {best_day_name} ({max(week_scores)} pts) |
| Current Streak | {state.get('current_streak', 0)} days |

## Daily Breakdown
"""

    for i, (name, score) in enumerate(zip(day_names, week_scores)):
        bar = "█" * (score // 5) if score > 0 else "░"
        marker = " ← today" if week_days[i] == today.isoformat() else ""
        report += f"  {name}: {score:3d} pts {bar}{marker}\n"

    report += f"""
## All-Time Stats
| Metric | Value |
|--------|-------|
| Total Points | {state.get('total_points', 0):,} |
| Best Streak | {state.get('best_streak', 0)} days |
| Level | {state.get('title', '?')} |
| Achievements | {len(state.get('achievements', []))} / {len(ACHIEVEMENTS)} |

"""

    # Achievements earned
    earned = state.get("achievements", [])
    if earned:
        report += "## Achievements Earned\n"
        for a in earned:
            name, desc = ACHIEVEMENTS.get(a, (a, ""))
            report += f"  {name} — {desc}\n"
    else:
        report += "## Achievements\n  None yet — keep going!\n"

    report += f"\n---\n*Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"

    WEEKLY_FILE.parent.mkdir(parents=True, exist_ok=True)
    WEEKLY_FILE.write_text(report)

    return week_total


def generate_scorecard():
    state = load_state()
    today = date.today().isoformat()

    daily_score, activities = calculate_daily_score()

    yesterday = (date.today() - timedelta(days=1)).isoformat()
    already_scored_today = today in state.get("daily_scores", {})

    if not already_scored_today:
        if yesterday in state.get("daily_scores", {}):
            state["current_streak"] += 1
        else:
            state["current_streak"] = 1
        state["total_points"] = state.get("total_points", 0) + daily_score
    else:
        old_score = state["daily_scores"].get(today, 0)
        if daily_score > old_score:
            state["total_points"] = state.get("total_points", 0) + (daily_score - old_score)

    state["daily_scores"][today] = daily_score

    if state["current_streak"] > state.get("best_streak", 0):
        state["best_streak"] = state["current_streak"]

    (_, title, _), next_level = get_level_info(state["total_points"])
    state["title"] = title

    new_achievements = check_achievements(state, daily_score, activities)

    # Progress bar
    bar_filled = min(daily_score, 100)
    progress_bar = "█" * (bar_filled // 5) + "░" * ((100 - bar_filled) // 5)

    # Streak fire
    streak = state["current_streak"]
    streak_fire = "🔥" * min(streak, 7) if streak > 0 else ""

    # Level progress
    (current_threshold, _, _), next_lvl = get_level_info(state["total_points"])
    if next_lvl:
        next_threshold, next_title, _ = next_lvl
        level_progress = (state["total_points"] - current_threshold) / (next_threshold - current_threshold) * 100
        level_bar = "█" * (int(level_progress) // 5) + "░" * ((100 - int(level_progress)) // 5)
        level_info = f"Next: {next_title} ({next_threshold - state['total_points']} pts to go) [{level_bar}]"
    else:
        level_info = "MAX LEVEL REACHED"

    scorecard = f"""# Sales Scorecard — {today}

## Today: {daily_score} pts  [{progress_bar}]

### Activities
{chr(10).join(f'  {a}' for a in activities) if activities else '  No activities yet — get started!'}

## Stats
| Metric | Value |
|--------|-------|
| Total Points | {state['total_points']:,} |
| Current Streak | {streak} days {streak_fire} |
| Best Streak | {state.get('best_streak', 0)} days |
| Level | {state['title']} |
| {level_info} | |

"""

    if new_achievements:
        scorecard += "## NEW ACHIEVEMENTS UNLOCKED!\n"
        for a in new_achievements:
            name, desc = ACHIEVEMENTS.get(a, (a, ""))
            scorecard += f"  **{name}** — {desc}\n"
        scorecard += "\n"

    # Achievement progress
    earned = len(state.get("achievements", []))
    total_ach = len(ACHIEVEMENTS)
    ach_bar = "█" * (earned * 20 // total_ach) + "░" * (20 - earned * 20 // total_ach)
    scorecard += f"## Achievements: {earned}/{total_ach} [{ach_bar}]\n"
    for aid, (name, desc) in ACHIEVEMENTS.items():
        icon = "✅" if aid in state.get("achievements", []) else "⬜"
        scorecard += f"  {icon} {name}\n"
    scorecard += "\n"

    # Recent history
    scores = state.get("daily_scores", {})
    recent = sorted(scores.items(), reverse=True)[:7]
    if recent:
        scorecard += "## Last 7 Days\n"
        for d, s in recent:
            bar = "█" * (s // 5)
            scorecard += f"  {d}: {s:3d} pts {bar}\n"

    scorecard += f"\n---\n*{state['title']} | {streak_fire} Keep the streak alive!*\n"

    SCORECARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    SCORECARD_FILE.write_text(scorecard)

    # Generate weekly report
    generate_weekly_report(state)

    save_state(state)
    print(f"Scorecard: {daily_score} pts today, {state['total_points']} total, streak: {state['current_streak']}, achievements: {earned}/{total_ach}")
    return daily_score


if __name__ == "__main__":
    generate_scorecard()
