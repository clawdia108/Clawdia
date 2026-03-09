#!/usr/bin/env python3
"""
Weekly Intel (Loop 4) — nedělní sales intelligence report.

Metrics:
1. Pipeline velocity (deals moved, avg age, conversion rates)
2. Activity stats (calls, emails, meetings this week)
3. Deal health overview (advancing, stalling, at risk)
4. Top 5 priority deals for next week
5. Motivational dopamine (achievements, streaks)

Usage:
  python3 scripts/weekly_intel.py                # full report + Telegram
  python3 scripts/weekly_intel.py --stdout        # print to stdout only
  python3 scripts/weekly_intel.py --week 10       # specific ISO week
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.paths import WORKSPACE, LOGS_DIR
from lib.secrets import load_secrets
from lib.notifications import notify_telegram
from lib.notion import push_analysis
from lib.pipedrive import pipedrive_api

LOG_FILE = LOGS_DIR / "weekly-intel.log"
REPORTS_DIR = WORKSPACE / "reports" / "weekly"


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")



def get_week_dates(week_num=None):
    """Get Monday-Sunday dates for given ISO week or current week."""
    now = datetime.now()
    if week_num:
        # Find Monday of given ISO week
        jan1 = datetime(now.year, 1, 1)
        # ISO week 1 contains Jan 4
        jan4 = datetime(now.year, 1, 4)
        monday_w1 = jan4 - timedelta(days=jan4.weekday())
        monday = monday_w1 + timedelta(weeks=week_num - 1)
    else:
        monday = now - timedelta(days=now.weekday())

    sunday = monday + timedelta(days=6)
    return monday.strftime("%Y-%m-%d"), sunday.strftime("%Y-%m-%d")


def get_activities_this_week(token, start_date, end_date):
    """Get all activities done this week."""
    activities = []
    start = 0
    while True:
        batch = pipedrive_api(token, "GET", "/activities", {
            "user_id": "24403638",
            "done": "1",
            "start_date": start_date,
            "end_date": end_date,
            "start": str(start),
            "limit": "100",
        })
        if not batch:
            break
        activities.extend(batch)
        if len(batch) < 100:
            break
        start += 100
    return activities


def get_deals_snapshot(token):
    """Get all deals with key metrics."""
    deals = []
    start = 0
    while True:
        batch = pipedrive_api(token, "GET", "/deals", {
            "status": "open",
            "user_id": "24403638",
            "start": str(start),
            "limit": "100",
        })
        if not batch:
            break
        deals.extend(batch)
        if len(batch) < 100:
            break
        start += 100
    return deals


def get_won_lost_this_week(token, start_date, end_date):
    """Get deals won/lost this week."""
    won = []
    lost = []
    for status in ["won", "lost"]:
        result = pipedrive_api(token, "GET", "/deals", {
            "status": status,
            "user_id": "24403638",
            "sort": "won_time DESC" if status == "won" else "lost_time DESC",
            "start": "0",
            "limit": "50",
        })
        if result:
            for d in result:
                ts = d.get("won_time" if status == "won" else "lost_time", "")
                if ts and ts[:10] >= start_date and ts[:10] <= end_date:
                    if status == "won":
                        won.append(d)
                    else:
                        lost.append(d)
    return won, lost


def calculate_pipeline_velocity(deals):
    """Calculate pipeline velocity metrics."""
    now = datetime.now()
    total_value = sum(d.get("value", 0) for d in deals)
    deal_ages = []

    stages = Counter()
    no_next_step = 0
    stale_14d = 0

    for d in deals:
        # Deal age
        add_time = d.get("add_time", "")
        if add_time:
            try:
                add_dt = datetime.strptime(add_time[:10], "%Y-%m-%d")
                age = (now - add_dt).days
                deal_ages.append(age)
            except ValueError:
                pass

        # Stage distribution
        stage = d.get("stage_order_nr", 0)
        stages[stage] = stages.get(stage, 0) + 1

        # No next step
        if not d.get("next_activity_date"):
            no_next_step += 1

        # Stale
        last = d.get("last_activity_date", "")
        if last:
            try:
                last_dt = datetime.strptime(last, "%Y-%m-%d")
                if (now - last_dt).days >= 14:
                    stale_14d += 1
            except ValueError:
                pass

    avg_age = sum(deal_ages) / len(deal_ages) if deal_ages else 0
    median_age = sorted(deal_ages)[len(deal_ages) // 2] if deal_ages else 0

    return {
        "total_deals": len(deals),
        "total_value": total_value,
        "avg_age_days": round(avg_age),
        "median_age_days": median_age,
        "no_next_step": no_next_step,
        "stale_14d": stale_14d,
        "stages": dict(stages),
    }


def get_top_priority_deals(deals, limit=5):
    """Get top priority deals for next week based on stage + activity."""
    now = datetime.now()
    scored = []

    for d in deals:
        score = 0
        deal_id = d["id"]
        title = d.get("title", "")
        org = d.get("org_name", "") or ""
        value = d.get("value", 0)
        stage = d.get("stage_order_nr", 0)
        next_date = d.get("next_activity_date", "")
        last_date = d.get("last_activity_date", "")

        # Higher stage = higher priority
        score += stage * 10

        # Has value = priority
        if value > 0:
            score += 20

        # Activity in next 7 days = priority
        if next_date:
            try:
                next_dt = datetime.strptime(next_date, "%Y-%m-%d")
                days_until = (next_dt - now).days
                if 0 <= days_until <= 7:
                    score += 30
                elif days_until < 0:  # overdue
                    score += 25
            except ValueError:
                pass

        # Recent activity = momentum
        if last_date:
            try:
                last_dt = datetime.strptime(last_date, "%Y-%m-%d")
                days_since = (now - last_dt).days
                if days_since < 7:
                    score += 15
                elif days_since > 21:
                    score -= 10  # penalize ghosting
            except ValueError:
                pass

        scored.append({
            "deal_id": deal_id,
            "title": title,
            "org": org,
            "value": value,
            "stage": stage,
            "next_date": next_date,
            "score": score,
        })

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def generate_report(activities, deals, won, lost, velocity, priorities, start_date, end_date):
    """Generate the weekly report."""
    # Activity stats
    act_types = Counter(a.get("type", "?") for a in activities)
    total_acts = len(activities)

    # Build report
    week_num = datetime.strptime(start_date, "%Y-%m-%d").isocalendar()[1]
    lines = []

    lines.append(f"# Weekly Sales Intel — Týden {week_num}")
    lines.append(f"_{start_date} → {end_date}_\n")

    # Dopamine section first!
    lines.append("## 🏆 Tvůj týden v číslech\n")
    lines.append(f"📞 **{act_types.get('call', 0)}** callů")
    lines.append(f"📧 **{act_types.get('email', 0)}** emailů")
    lines.append(f"🎯 **{act_types.get('demo_meeting', 0)}** dem")
    lines.append(f"📊 **{total_acts}** aktivit celkem")

    if won:
        won_value = sum(d.get("value", 0) for d in won)
        lines.append(f"\n🎉 **{len(won)} WON** dealů za **{won_value:,.0f} CZK**")
        for w in won:
            lines.append(f"  ✅ {w.get('title','')} ({w.get('value',0):,.0f} CZK)")

    if lost:
        lines.append(f"\n😤 {len(lost)} lost dealů")

    # Motivational
    if total_acts >= 15:
        lines.append("\n🔥 **Na plný plyn!** Víc než 15 aktivit tento týden.")
    elif total_acts >= 10:
        lines.append("\n👍 **Solidní týden.** 10+ aktivit, drž to.")
    elif total_acts >= 5:
        lines.append("\n⚡ **Rozjezd.** Příští týden přidáme.")
    else:
        lines.append("\n💪 **Tichý týden.** Příští týden to rozbalíme.")

    # Pipeline health
    lines.append("\n## 📊 Pipeline Health\n")
    lines.append(f"| Metrika | Hodnota | Target |")
    lines.append(f"|---------|---------|--------|")
    lines.append(f"| Open deals | **{velocity['total_deals']}** | — |")
    lines.append(f"| Pipeline value | **{velocity['total_value']:,.0f} CZK** | — |")
    lines.append(f"| Průměrný věk dealu | **{velocity['avg_age_days']}d** | <74d |")
    lines.append(f"| Bez next step | **{velocity['no_next_step']}** | 0 |")
    lines.append(f"| Stale 14d+ | **{velocity['stale_14d']}** | <5 |")

    # Health assessment
    health_score = 100
    if velocity['no_next_step'] > 0:
        health_score -= velocity['no_next_step'] * 5
    if velocity['stale_14d'] > 5:
        health_score -= (velocity['stale_14d'] - 5) * 3
    if velocity['avg_age_days'] > 100:
        health_score -= 10

    health_emoji = "🟢" if health_score >= 80 else "🟡" if health_score >= 60 else "🔴"
    lines.append(f"\n{health_emoji} **Pipeline health: {health_score}/100**")

    if velocity['no_next_step'] > 0:
        lines.append(f"⚠️ {velocity['no_next_step']} dealů bez next step — naprav hned v pondělí")
    if velocity['stale_14d'] > 5:
        lines.append(f"⚠️ {velocity['stale_14d']} stale dealů (14d+) — spusť follow-up engine")

    # Top priorities
    lines.append("\n## 🎯 Top 5 na příští týden\n")
    lines.append("| # | Deal | Firma | Value | Next Step |")
    lines.append("|---|------|-------|-------|-----------|")
    for i, p in enumerate(priorities, 1):
        val = f"{p['value']:,.0f} CZK" if p['value'] > 0 else "—"
        next_s = p['next_date'] or "⚠️ CHYBÍ"
        lines.append(f"| {i} | {p['title'][:25]} | {p['org'][:20]} | {val} | {next_s} |")

    # Deal health distribution
    from deal_health_scorer import calculate_deal_health
    healthy = sum(1 for d in deals if calculate_deal_health(d, None, detailed=False)["pct"] >= 70)
    at_risk = sum(1 for d in deals if 40 <= calculate_deal_health(d, None, detailed=False)["pct"] < 70)
    critical = sum(1 for d in deals if calculate_deal_health(d, None, detailed=False)["pct"] < 40)

    lines.append("\n## 🏥 Deal Health Distribution\n")
    lines.append(f"🟢 Healthy: **{healthy}** | 🟡 At Risk: **{at_risk}** | 🔴 Critical: **{critical}**")

    # Multi-threading warning
    single_threaded_hv = [d for d in deals if d.get("value", 0) > 50000
                          and not d.get("participants_count", 0) > 1]
    if single_threaded_hv:
        lines.append(f"\n⚠️ **{len(single_threaded_hv)} single-threaded high-value dealů** — přidej druhý kontakt!")

    # Weekly velocity comparison
    lines.append("\n## 📈 Velocity Check\n")
    lines.append(f"- Deals s aktivitou tento týden: **{total_acts}** touchpointů")
    lines.append(f"- Won deals: **{len(won)}**")
    lines.append(f"- Lost deals: **{len(lost)}**")

    if total_acts > 0:
        calls_pct = round(act_types.get('call', 0) / total_acts * 100)
        emails_pct = round(act_types.get('email', 0) / total_acts * 100)
        lines.append(f"- Mix: {calls_pct}% calls, {emails_pct}% emails")
        lines.append(f"- Gong benchmark: nejúspěšnější mix je 40% call, 35% email, 25% other")

    # Multichannel recommendation
    if total_acts > 0 and emails_pct < 20:
        lines.append(f"\n📢 **Chybí emailová cadence!** Multichannel = 287% vyšší engagement. Spusť follow-up engine.")

    lines.append(f"\n---\n_Generováno: {datetime.now().strftime('%d.%m.%Y %H:%M')}_")

    return "\n".join(lines)


def main():
    secrets = load_secrets()
    token = secrets.get("PIPEDRIVE_API_TOKEN") or secrets.get("PIPEDRIVE_TOKEN")
    if not token:
        log("No Pipedrive token found in secrets")
        return 1

    stdout_only = "--stdout" in sys.argv
    week_num = None
    for i, arg in enumerate(sys.argv):
        if arg == "--week" and i + 1 < len(sys.argv):
            week_num = int(sys.argv[i + 1])

    # Get week dates
    start_date, end_date = get_week_dates(week_num)
    log(f"Generating weekly intel for {start_date} → {end_date}")

    # Gather data
    log("Fetching activities...")
    activities = get_activities_this_week(token, start_date, end_date)
    log(f"  {len(activities)} activities this week")

    log("Fetching deals...")
    deals = get_deals_snapshot(token)
    log(f"  {len(deals)} open deals")

    log("Fetching won/lost...")
    won, lost = get_won_lost_this_week(token, start_date, end_date)
    log(f"  {len(won)} won, {len(lost)} lost")

    log("Calculating velocity...")
    velocity = calculate_pipeline_velocity(deals)

    log("Determining priorities...")
    priorities = get_top_priority_deals(deals)

    # Generate report
    report = generate_report(activities, deals, won, lost, velocity, priorities, start_date, end_date)

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    report_file = REPORTS_DIR / f"week_{start_date}.md"
    report_file.write_text(report)
    log(f"Report saved: {report_file}")

    if stdout_only:
        print(report)
        return 0

    # Print report
    print(report)

    # Telegram digest (condensed version)
    tg_lines = []
    act_types = Counter(a.get("type", "?") for a in activities)
    tg_lines.append(f"📊 Weekly Intel — Týden {datetime.strptime(start_date, '%Y-%m-%d').isocalendar()[1]}\n")
    tg_lines.append(f"📞 {act_types.get('call', 0)} callů | 📧 {act_types.get('email', 0)} emailů | 🎯 {act_types.get('demo_meeting', 0)} dem")
    tg_lines.append(f"📈 {velocity['total_deals']} dealů | {velocity['total_value']:,.0f} CZK pipeline")

    if won:
        won_val = sum(d.get("value", 0) for d in won)
        tg_lines.append(f"🎉 {len(won)} WON — {won_val:,.0f} CZK")

    health_emoji = "🟢" if velocity['no_next_step'] == 0 and velocity['stale_14d'] < 5 else "🟡" if velocity['stale_14d'] < 10 else "🔴"
    tg_lines.append(f"\n{health_emoji} Health: {velocity['no_next_step']} bez next step, {velocity['stale_14d']} stale")

    tg_lines.append(f"\n🎯 Top priority:")
    for p in priorities[:3]:
        tg_lines.append(f"  • {p['org'][:20]} ({p['next_date'] or '⚠️ bez next step'})")

    notify_telegram("\n".join(tg_lines))
    log("Telegram digest sent")

    # Push to Notion
    notion_token = secrets.get("NOTION_TOKEN")
    if notion_token:
        push_analysis(notion_token, f"Weekly Intel {datetime.now().strftime('%d.%m')}",
                       "Weekly Intel", report[:1990],
                       deals_affected=len(deals))

    return 0


if __name__ == "__main__":
    exit(main())
