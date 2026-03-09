#!/usr/bin/env python3
"""
Stale Deal Cleanup — automatická identifikace a disqualifikace mrtvých dealů.

Pravidla:
- 30+ dnů bez aktivity = STALE (tag "stale", warning)
- 60+ dnů bez aktivity + stage 1-2 = DISQUALIFY kandidát
- 90+ dnů bez aktivity = LOST (automatic pokud --apply)

Bezpečnostní guardy (stejně jako activity_guard.py):
- Dry-run by default (bez --apply se nic nepíše)
- --max-actions cap (default 20)
- Telegram summary vždy
- Log do knowledge/stale_cleanup.json

Usage:
  python3 scripts/stale_deal_cleanup.py                    # dry-run report
  python3 scripts/stale_deal_cleanup.py --apply            # apply changes
  python3 scripts/stale_deal_cleanup.py --apply --max 10   # limit actions
  python3 scripts/stale_deal_cleanup.py --report           # just generate STALE_DEALS.md
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.paths import WORKSPACE, LOGS_DIR
from lib.secrets import load_secrets
from lib.notifications import notify_telegram
from lib.pipedrive import pipedrive_api, pipedrive_get_all

LOG_FILE = LOGS_DIR / "stale-cleanup.log"
STATE_FILE = WORKSPACE / "knowledge" / "stale_cleanup.json"
STALE_DEALS_FILE = WORKSPACE / "pipedrive" / "STALE_DEALS.md"

# Thresholds (days)
STALE_DAYS = 30
DISQUALIFY_DAYS = 60
LOST_DAYS = 90

# Stages where early disqualification makes sense (early pipeline)
EARLY_STAGES = {1, 2}  # Lead In, Contacted

# Deals to never auto-close (by org name substring)
PROTECTED_ORGS = ["vodafone", "škoda", "o2", "lidl"]


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def days_since(date_str):
    """Calculate days since a date string (YYYY-MM-DD)."""
    if not date_str:
        return 999
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d")
        return (datetime.now() - d).days
    except (ValueError, TypeError):
        return 999


def is_protected(deal):
    """Check if deal should never be auto-closed."""
    org = (deal.get("org_name") or deal.get("title") or "").lower()
    return any(p in org for p in PROTECTED_ORGS)


def classify_deal(deal):
    """Classify a deal's staleness level."""
    last_activity = deal.get("last_activity_date")
    next_activity = deal.get("next_activity_date")
    stage = deal.get("stage_order_nr", 0)
    silent_days = days_since(last_activity)
    has_upcoming = next_activity and days_since(next_activity) < 0  # future date

    if has_upcoming:
        return "active", silent_days

    if silent_days >= LOST_DAYS:
        return "lost", silent_days
    elif silent_days >= DISQUALIFY_DAYS and stage in EARLY_STAGES:
        return "disqualify", silent_days
    elif silent_days >= STALE_DAYS:
        return "stale", silent_days

    return "ok", silent_days


def add_deal_label(token, deal_id, label):
    """Add a label/tag to a deal via Pipedrive PUT."""
    return pipedrive_api(token, "PUT", f"/deals/{deal_id}", {
        "label": label,
    })


def mark_deal_lost(token, deal_id, reason):
    """Mark deal as lost with a reason."""
    return pipedrive_api(token, "PUT", f"/deals/{deal_id}", {
        "status": "lost",
        "lost_reason": reason,
    })


def add_deal_note(token, deal_id, content):
    """Add a note to a deal."""
    return pipedrive_api(token, "POST", "/notes", {
        "deal_id": deal_id,
        "content": content,
        "pinned_to_deal_flag": 0,
    })


def generate_report(classified):
    """Generate STALE_DEALS.md report."""
    lines = [f"# Stale Deals Report ({datetime.now().strftime('%Y-%m-%d')})\n"]

    lost = [d for d in classified if d["status"] == "lost"]
    disqualify = [d for d in classified if d["status"] == "disqualify"]
    stale = [d for d in classified if d["status"] == "stale"]

    lines.append(f"**{len(stale)} stale** | **{len(disqualify)} disqualify** | **{len(lost)} lost candidates**\n")

    if lost:
        lines.append("## 🔴 Lost Candidates (90+ days silent)")
        for d in sorted(lost, key=lambda x: x["silent_days"], reverse=True):
            prot = " ⚠️ PROTECTED" if d["protected"] else ""
            lines.append(f"- **{d['title']}** ({d['org']}) — {d['value']:,.0f} CZK — {d['silent_days']}d silent{prot}")
        lines.append("")

    if disqualify:
        lines.append("## 🟡 Disqualify Candidates (60+ days, early stage)")
        for d in sorted(disqualify, key=lambda x: x["silent_days"], reverse=True):
            prot = " ⚠️ PROTECTED" if d["protected"] else ""
            lines.append(f"- **{d['title']}** ({d['org']}) — {d['value']:,.0f} CZK — {d['silent_days']}d silent{prot}")
        lines.append("")

    if stale:
        lines.append("## 🟠 Stale (30+ days silent)")
        for d in sorted(stale, key=lambda x: x["silent_days"], reverse=True):
            lines.append(f"- **{d['title']}** ({d['org']}) — {d['value']:,.0f} CZK — {d['silent_days']}d silent")
        lines.append("")

    total_value = sum(d["value"] for d in classified if d["status"] != "ok")
    lines.append(f"\n**Total at risk: {total_value:,.0f} CZK across {len(stale) + len(disqualify) + len(lost)} deals**")

    return "\n".join(lines)


def main():
    secrets = load_secrets()
    token = secrets.get("PIPEDRIVE_API_TOKEN") or secrets.get("PIPEDRIVE_TOKEN")
    if not token:
        log("No Pipedrive token")
        return 1

    apply_mode = "--apply" in sys.argv
    report_only = "--report" in sys.argv
    max_actions = 20
    for i, arg in enumerate(sys.argv):
        if arg == "--max" and i + 1 < len(sys.argv):
            max_actions = int(sys.argv[i + 1])

    # Fetch all open deals
    log("Fetching open deals...")
    deals = pipedrive_get_all(token, "/deals", {
        "status": "open",
        "user_id": "24403638",
    })
    log(f"Found {len(deals)} open deals")

    # Classify each deal
    classified = []
    for deal in deals:
        status, silent_days = classify_deal(deal)
        classified.append({
            "id": deal["id"],
            "title": deal.get("title", "?"),
            "org": deal.get("org_name") or "?",
            "value": deal.get("value") or 0,
            "stage": deal.get("stage_order_nr", 0),
            "stage_name": deal.get("stage_id", "?"),
            "silent_days": silent_days,
            "status": status,
            "protected": is_protected(deal),
            "last_activity": deal.get("last_activity_date"),
            "next_activity": deal.get("next_activity_date"),
        })

    lost = [d for d in classified if d["status"] == "lost"]
    disqualify = [d for d in classified if d["status"] == "disqualify"]
    stale = [d for d in classified if d["status"] == "stale"]
    ok = [d for d in classified if d["status"] == "ok"]

    log(f"Classification: {len(ok)} active, {len(stale)} stale, {len(disqualify)} disqualify, {len(lost)} lost")

    # Generate report
    report = generate_report(classified)
    STALE_DEALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STALE_DEALS_FILE.write_text(report)
    log(f"Report saved: {STALE_DEALS_FILE}")

    if report_only:
        print(report)
        return 0

    # Apply actions
    actions_taken = 0
    results = {"mode": "apply" if apply_mode else "dry_run", "timestamp": datetime.now().isoformat()}
    results["stale"] = len(stale)
    results["disqualify"] = len(disqualify)
    results["lost"] = len(lost)

    if not apply_mode:
        log("DRY RUN — no changes made. Use --apply to execute.")
        results["would_do"] = {
            "mark_lost": len([d for d in lost if not d["protected"]]),
            "add_note_stale": len(stale),
            "add_note_disqualify": len(disqualify),
        }
    else:
        # Mark lost deals (90+ days, not protected)
        for d in lost:
            if actions_taken >= max_actions:
                log(f"Hit max-actions cap ({max_actions})")
                break
            if d["protected"]:
                log(f"  SKIP (protected): {d['title']}")
                add_deal_note(token, d["id"],
                    f"<b>⚠️ Clawdia Alert</b>: Deal je {d['silent_days']} dnů bez aktivity. "
                    f"Automaticky nemarkovány jako lost (protected org). Prosím zkontroluj.")
                actions_taken += 1
                continue

            mark_deal_lost(token, d["id"],
                f"Auto-closed: {d['silent_days']} dnů bez aktivity (Clawdia stale cleanup)")
            add_deal_note(token, d["id"],
                f"<b>🔴 Auto-closed by Clawdia</b>: {d['silent_days']} dnů bez jakékoli aktivity. "
                f"Pokud je deal stále živý, znovu ho otevři.")
            actions_taken += 1
            log(f"  LOST: {d['title']} ({d['silent_days']}d)")

        # Add notes to disqualify candidates
        for d in disqualify:
            if actions_taken >= max_actions:
                break
            add_deal_note(token, d["id"],
                f"<b>🟡 Stale Alert</b>: Deal je {d['silent_days']} dnů bez aktivity v early stage. "
                f"Zvažte disqualifikaci nebo naplánujte follow-up.")
            actions_taken += 1
            log(f"  DISQUALIFY NOTE: {d['title']} ({d['silent_days']}d)")

        # Add notes to stale deals
        for d in stale:
            if actions_taken >= max_actions:
                break
            add_deal_note(token, d["id"],
                f"<b>🟠 Stale Warning</b>: Deal je {d['silent_days']} dnů bez aktivity. "
                f"Naplánuj follow-up nebo zkontroluj status.")
            actions_taken += 1
            log(f"  STALE NOTE: {d['title']} ({d['silent_days']}d)")

        results["actions_taken"] = actions_taken

    # Save state
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(results, indent=2, ensure_ascii=False))

    # Telegram summary
    total_risk = sum(d["value"] for d in classified if d["status"] != "ok")
    msg_lines = [
        f"Pipeline Cleanup {'✅' if apply_mode else '📋 DRY RUN'}",
        f"",
        f"🔴 {len(lost)} lost ({sum(d['value'] for d in lost):,.0f} CZK)",
        f"🟡 {len(disqualify)} disqualify candidates",
        f"🟠 {len(stale)} stale deals",
        f"💰 {total_risk:,.0f} CZK at risk",
    ]
    if apply_mode:
        msg_lines.append(f"\n✅ {actions_taken} actions taken")
    else:
        msg_lines.append(f"\nRun with --apply to execute")

    notify_telegram("\n".join(msg_lines))

    # Push to Notion
    try:
        from lib.notion import push_analysis
        notion_token = secrets.get("NOTION_TOKEN")
        if notion_token:
            push_analysis(notion_token, f"Stale Cleanup {datetime.now().strftime('%d.%m')}",
                         "Pipeline Health", report[:1990],
                         deals_affected=len(stale) + len(disqualify) + len(lost))
    except Exception:
        pass

    return 0


if __name__ == "__main__":
    exit(main())
