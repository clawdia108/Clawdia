#!/usr/bin/env python3
"""
Pipedrive Writeback — synchronizuje analýzy zpět do Pipedrive CRM.

Co zapisuje:
1. Health Score label na dealech (🟢 Healthy / 🟡 At Risk / 🔴 Critical)
2. Signal tags (hot signal notes na dealy s čerstvými signály)
3. Missing next-step activities (follow-up task pro deals bez aktivity)

Bezpečnostní guardy:
- Dry-run by default
- --apply flag pro skutečné zápisy
- --max cap na počet zápisů (default 30)
- Telegram summary

Usage:
  python3 scripts/pipedrive_writeback.py                    # dry-run
  python3 scripts/pipedrive_writeback.py --apply            # apply all
  python3 scripts/pipedrive_writeback.py --apply --health   # only health labels
  python3 scripts/pipedrive_writeback.py --apply --signals  # only signal tags
  python3 scripts/pipedrive_writeback.py --apply --nextstep # only missing activities
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

LOG_FILE = LOGS_DIR / "pipedrive-writeback.log"
STATE_FILE = WORKSPACE / "knowledge" / "writeback_state.json"
SIGNALS_DIR = WORKSPACE / "knowledge" / "signals"


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")


def days_since(date_str):
    if not date_str:
        return 999
    try:
        return (datetime.now() - datetime.strptime(date_str[:10], "%Y-%m-%d")).days
    except (ValueError, TypeError):
        return 999


def next_business_day():
    d = datetime.now().date() + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d.isoformat()


# ─── HEALTH SCORE WRITEBACK ───────────────────────────────

def calculate_quick_health(deal):
    """Quick health score (no extra API calls)."""
    score = 0

    # Next step (0-20)
    next_date = deal.get("next_activity_date")
    if next_date:
        nd = days_since(next_date)
        if nd < 0:  # future
            score += 20
        elif nd == 0:
            score += 15
        else:
            score += 5

    # Activity recency (0-20)
    last = deal.get("last_activity_date")
    ld = days_since(last)
    if ld <= 3:
        score += 20
    elif ld <= 7:
        score += 15
    elif ld <= 14:
        score += 10
    elif ld <= 21:
        score += 5

    # Stage velocity (0-15)
    stage = deal.get("stage_order_nr", 0)
    add_time = deal.get("add_time", "")
    age = days_since(add_time) if add_time else 999
    if stage > 0 and age > 0:
        dps = age / stage
        if dps <= 14:
            score += 15
        elif dps <= 30:
            score += 10
        elif dps <= 60:
            score += 5

    # CRM coverage (0-10)
    fields = 0
    if deal.get("value", 0) > 0:
        fields += 1
    if deal.get("org_id"):
        fields += 1
    if deal.get("person_id"):
        fields += 1
    if deal.get("expected_close_date"):
        fields += 1
    if stage > 0:
        fields += 1
    score += fields * 2  # max 10

    # Commitment (0-10)
    if stage >= 5:
        score += 10
    elif stage >= 3:
        score += 6
    elif stage >= 2:
        score += 4
    elif stage >= 1:
        score += 2

    # Estimates for multi-thread + volume (0-25 combined)
    if deal.get("person_id"):
        score += 5
    score += 5  # volume estimate

    return score


def writeback_health_labels(token, deals, apply=False, max_actions=30):
    """Write health score labels back to Pipedrive deals."""
    actions = 0
    results = {"healthy": 0, "at_risk": 0, "critical": 0, "updated": 0}

    for deal in deals:
        if actions >= max_actions:
            break

        score = calculate_quick_health(deal)
        deal_id = deal["id"]
        org = deal.get("org_name") or deal.get("title", "?")

        if score >= 70:
            label = "🟢"
            results["healthy"] += 1
        elif score >= 40:
            label = "🟡"
            results["at_risk"] += 1
        else:
            label = "🔴"
            results["critical"] += 1

        if apply:
            pipedrive_api(token, "PUT", f"/deals/{deal_id}", {
                "label": label,
            })
            actions += 1
            results["updated"] += 1
            log(f"  {label} {org[:25]} (score {score})")

    results["actions"] = actions
    return results


# ─── SIGNAL TAGS WRITEBACK ─────────────────────────────────

def writeback_signal_tags(token, deals, apply=False, max_actions=30):
    """Add signal-based notes to deals with hot signals."""
    if not SIGNALS_DIR.exists():
        log("No signals directory found")
        return {"actions": 0, "hot_deals": 0}

    actions = 0
    hot_count = 0
    deal_ids = {d["id"] for d in deals}

    for f in SIGNALS_DIR.glob("deal_*.json"):
        if actions >= max_actions:
            break

        try:
            data = json.loads(f.read_text())
        except Exception:
            continue

        deal_id = data.get("deal_id")
        if deal_id not in deal_ids:
            continue

        high = data.get("high_priority", 0)
        if high == 0:
            continue

        # Skip if scan is older than 7 days
        scanned = data.get("scanned_at", "")
        if scanned and days_since(scanned[:10]) > 7:
            continue

        hot_count += 1
        signals = data.get("signals", [])
        hot_signals = [s for s in signals if s.get("priority") == "high"]

        if apply:
            lines = ["<h3>🔥 Signal Intelligence</h3>"]
            lines.append(f"<p><b>{len(hot_signals)} hot signálů</b> nalezeno {scanned[:10]}</p>")
            for s in hot_signals[:5]:
                lines.append(f"<p>• <b>{s['type']}</b>: {s['title'][:60]}<br>")
                lines.append(f"  <i>{s['relevance']}</i></p>")

            pipedrive_api(token, "POST", "/notes", {
                "deal_id": deal_id,
                "content": "\n".join(lines),
            })
            actions += 1
            log(f"  Signal note: deal {deal_id} ({high} hot)")

    return {"actions": actions, "hot_deals": hot_count}


# ─── NEXT STEP CREATION ───────────────────────────────────

def writeback_next_steps(token, deals, apply=False, max_actions=30):
    """Create follow-up activities for deals without next steps."""
    actions = 0
    missing = 0
    due = next_business_day()

    for deal in deals:
        if actions >= max_actions:
            break

        if deal.get("next_activity_date"):
            continue

        # Skip very old deals (stale_deal_cleanup handles those)
        last = deal.get("last_activity_date")
        if days_since(last) > 60:
            continue

        missing += 1
        deal_id = deal["id"]
        org = deal.get("org_name") or deal.get("title", "?")
        stage = deal.get("stage_order_nr", 0)

        if stage >= 4:
            subject = f"Follow-up: {org[:30]} — check proposal status"
            activity_type = "call"
        elif stage >= 2:
            subject = f"Follow-up: {org[:30]} — schedule next meeting"
            activity_type = "call"
        else:
            subject = f"Follow-up: {org[:30]} — initial outreach"
            activity_type = "email"

        if apply:
            result = pipedrive_api(token, "POST", "/activities", {
                "deal_id": deal_id,
                "subject": subject,
                "type": activity_type,
                "due_date": due,
                "user_id": 24403638,
            })
            if result:
                actions += 1
                log(f"  Activity: {org[:25]} ({activity_type})")

    return {"actions": actions, "missing": missing}


# ─── MAIN ─────────────────────────────────────────────────

def main():
    secrets = load_secrets()
    token = secrets.get("PIPEDRIVE_API_TOKEN") or secrets.get("PIPEDRIVE_TOKEN")
    if not token:
        log("No Pipedrive token")
        return 1

    apply_mode = "--apply" in sys.argv
    max_actions = 30
    for i, arg in enumerate(sys.argv):
        if arg == "--max" and i + 1 < len(sys.argv):
            max_actions = int(sys.argv[i + 1])

    specific_flags = any(a in sys.argv for a in ["--health", "--signals", "--nextstep"])
    do_health = "--health" in sys.argv or not specific_flags
    do_signals = "--signals" in sys.argv or not specific_flags
    do_nextstep = "--nextstep" in sys.argv or not specific_flags

    # Fetch all open deals
    log("Fetching open deals...")
    deals = pipedrive_get_all(token, "/deals", {
        "status": "open",
        "user_id": "24403638",
    })
    log(f"Found {len(deals)} open deals")

    results = {"timestamp": datetime.now().isoformat(), "mode": "apply" if apply_mode else "dry_run"}

    if do_health:
        log("\n=== HEALTH LABEL WRITEBACK ===")
        health_result = writeback_health_labels(token, deals, apply_mode, max_actions)
        results["health"] = health_result
        log(f"Health: {health_result}")

    if do_signals:
        log("\n=== SIGNAL TAG WRITEBACK ===")
        signal_result = writeback_signal_tags(token, deals, apply_mode, max_actions)
        results["signals"] = signal_result
        log(f"Signals: {signal_result}")

    if do_nextstep:
        log("\n=== NEXT STEP CREATION ===")
        nextstep_result = writeback_next_steps(token, deals, apply_mode, max_actions)
        results["nextstep"] = nextstep_result
        log(f"Next steps: {nextstep_result}")

    # Save state
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(results, indent=2))

    if not apply_mode:
        log(f"\nDRY RUN — use --apply to execute.")

    # Telegram
    lines = [f"Pipedrive Writeback {'✅' if apply_mode else '📋 DRY RUN'}"]
    if "health" in results and isinstance(results["health"], dict):
        h = results["health"]
        lines.append(f"🏥 Health: {h.get('healthy',0)} 🟢 {h.get('at_risk',0)} 🟡 {h.get('critical',0)} 🔴")
    if "signals" in results and isinstance(results["signals"], dict):
        s = results["signals"]
        lines.append(f"🔥 Signals: {s.get('hot_deals',0)} deals with hot signals")
    if "nextstep" in results and isinstance(results["nextstep"], dict):
        n = results["nextstep"]
        lines.append(f"📋 Next steps: {n.get('missing',0)} missing, {n.get('actions',0)} created")

    notify_telegram("\n".join(lines))

    return 0


if __name__ == "__main__":
    exit(main())
