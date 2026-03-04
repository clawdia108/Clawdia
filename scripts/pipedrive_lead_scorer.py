#!/usr/bin/env python3
"""
Pipedrive Lead Scorer — scores all open deals, generates DEAL_SCORING.md and PIPELINE_STATUS.md.
Runs daily via cron at 06:45 CET. Can also be run manually.

Scoring: Fit (0-40) + Engagement (0-35) + Momentum (0-25) = 0-100
"""

import json
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
ENV_PATH = WORKSPACE / ".secrets" / "pipedrive.env"
SCORING_OUTPUT = WORKSPACE / "pipedrive" / "DEAL_SCORING.md"
PIPELINE_OUTPUT = WORKSPACE / "pipedrive" / "PIPELINE_STATUS.md"
SCORING_LOG = WORKSPACE / "pipedrive" / "SCORING_LOG.md"

# Stage mappings
SALES_STAGES = {
    7: ("Interested/Qualified", 1),
    8: ("Demo Scheduled", 2),
    28: ("Ongoing Discussion", 3),
    9: ("Proposal made", 4),
    10: ("Negotiation", 5),
    12: ("Pilot", 6),
    29: ("Contract Sent", 7),
    11: ("Invoice sent", 8),
}

ONBOARDING_STAGES = {
    16: ("Sales Action Needed", 1),
    15: ("Waiting for Customer", 2),
    17: ("1. Pulse Planned", 3),
    18: ("Probation Period", 4),
    19: ("Customers", 5),
    20: ("Test Only", 6),
    32: ("Not Converted", 7),
}

PARTNERSHIP_STAGES = {22: "Talking", 23: "Serious talks", 24: "Preparations", 25: "Active partnership"}
CHURNED_STAGES = {30: "Churned customers", 31: "Onetime deals"}

# Custom field keys
FIELD_LEAD_SOURCE = "545839ef97506e40a691aa34e0d24a82be08d624"
FIELD_LEAD_TAG = "992635de0ece3a9e8a6a88ea5458a8ac2e14ffc1"
FIELD_FIRST_CALL = "b89c5f67c94d5a3bde2f2b1728646673169a007f"
FIELD_ACCOUNT_STATUS = "3f9bbdc78cf6dd9551ed45112800987a7cb2ea51"
FIELD_USE_CASE = "5d832816b0d2d2a47a1d7b76f4382d3665d03020"
FIELD_PRODUCT = "f4f43d7b1284bc4049adb933c3f79ee2d327f637"
FIELD_ICO = "e8f41ce53b4a2eba1050b385216bb4db7e789fca"
FIELD_MRR = "6c4a9ab5743abd972ed7746fb5d2a0035a543acf"

# Enum mappings
LEAD_SOURCE_LABELS = {89: "Cold", 88: "Inbound", 97: "Referral", 94: "Partner", 96: "Event", 98: "Customer"}
FIRST_CALL_LABELS = {152: "Connected", 153: "Not Connected"}

TODAY = date.today()


def load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def api_request(base, token, method, path, params=None, data=None, retry=3):
    params = dict(params or {})
    params["api_token"] = token
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"
    headers = {}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    for i in range(retry):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < retry - 1:
                time.sleep(2 * (i + 1))
                continue
            raise
    return None


def paged_get(base, token, path, params=None):
    out = []
    start = 0
    while True:
        p = dict(params or {})
        p.update({"start": start, "limit": 500})
        j = api_request(base, token, "GET", path, params=p)
        if not j or not j.get("success"):
            break
        out.extend(j.get("data") or [])
        pag = (j.get("additional_data") or {}).get("pagination") or {}
        if not pag.get("more_items_in_collection"):
            break
        start = pag.get("next_start", start + 500)
    return out


def days_ago(date_str):
    if not date_str:
        return 999
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return (TODAY - d).days
    except (ValueError, TypeError):
        return 999


def score_deal(deal, org_data=None):
    """Score a single deal. Returns (fit, engagement, momentum, total, details).

    ECHO PULSE PRIORITY: Deals with Echo Pulse product and 50-200 employee companies
    get massive score boosts. This is the #1 revenue driver (50% commission).
    """
    stage_id = deal.get("stage_id")
    is_sales = stage_id in SALES_STAGES

    # === FIT SCORE (0-40) ===
    fit = 0
    fit_details = []

    # Has organization (+5)
    org_name = deal.get("org_name") or ""
    if org_name:
        fit += 5
        fit_details.append("org:+5")

    # Has value set (+8)
    value = deal.get("value") or 0
    if value > 0:
        fit += 8
        fit_details.append(f"val({value}):+8")

    # Value size bonus
    if value >= 100000:
        fit += 5
        fit_details.append("bigdeal:+5")
    elif value >= 50000:
        fit += 3
        fit_details.append("meddeal:+3")

    # ECHO PULSE BOOST: Product = Echo Pulse (107) → +10
    product = deal.get(FIELD_PRODUCT)
    if product:
        product_ids = set()
        if isinstance(product, (list, str)):
            # Could be comma-separated string of IDs
            for p in str(product).split(","):
                p = p.strip()
                if p.isdigit():
                    product_ids.add(int(p))
        elif isinstance(product, int):
            product_ids.add(product)
        if 107 in product_ids:  # Echo Pulse
            fit += 10
            fit_details.append("ECHO_PULSE:+10")
        else:
            fit += 2
            fit_details.append("product:+2")

    # ECHO PULSE BOOST: Use case = Engagement (127) → +5
    use_case = deal.get(FIELD_USE_CASE)
    if use_case:
        use_case_str = str(use_case)
        if "127" in use_case_str:  # Engagement
            fit += 5
            fit_details.append("engagement_usecase:+5")
        else:
            fit += 3
            fit_details.append("usecase:+3")

    # Lead source (+5 for inbound/referral, +2 for cold)
    lead_src = deal.get(FIELD_LEAD_SOURCE)
    if lead_src in (88, 97, 98):  # Inbound, Referral, Customer
        fit += 5
        fit_details.append(f"src({LEAD_SOURCE_LABELS.get(lead_src,'?')}):+5")
    elif lead_src == 89:  # Cold
        fit += 2
        fit_details.append("src(Cold):+2")

    # Has MRR (+5)
    mrr = deal.get(FIELD_MRR)
    if mrr and mrr > 0:
        fit += 5
        fit_details.append(f"mrr:+5")

    # In sales pipeline (+5)
    if is_sales:
        fit += 5
        fit_details.append("sales_pipe:+5")

    fit = min(fit, 40)

    # === ENGAGEMENT SCORE (0-35) ===
    eng = 0
    eng_details = []

    # Activity count
    acts = deal.get("activities_count") or 0
    done_acts = deal.get("done_activities_count") or 0
    if done_acts >= 5:
        eng += 10
        eng_details.append(f"acts({done_acts}):+10")
    elif done_acts >= 3:
        eng += 7
        eng_details.append(f"acts({done_acts}):+7")
    elif done_acts >= 1:
        eng += 4
        eng_details.append(f"acts({done_acts}):+4")

    # Email messages
    email_count = deal.get("email_messages_count") or 0
    if email_count >= 3:
        eng += 8
        eng_details.append(f"emails({email_count}):+8")
    elif email_count >= 1:
        eng += 4
        eng_details.append(f"emails({email_count}):+4")

    # Has person with phone
    person = deal.get("person_id")
    if isinstance(person, dict):
        phones = person.get("phone", [])
        has_phone = any(p.get("value") for p in phones if isinstance(p, dict))
        if has_phone:
            eng += 5
            eng_details.append("phone:+5")
        person_email = person.get("email", [])
        has_email = any(e.get("value") for e in person_email if isinstance(e, dict))
        if has_email:
            eng += 3
            eng_details.append("email:+3")

    # First call connected (+5)
    first_call = deal.get(FIELD_FIRST_CALL)
    if first_call == 152:  # Connected
        eng += 5
        eng_details.append("connected:+5")

    # Notes exist (+4)
    if (deal.get("notes_count") or 0) >= 1:
        eng += 4
        eng_details.append("notes:+4")

    eng = min(eng, 35)

    # === MOMENTUM SCORE (0-25) ===
    mom = 0
    mom_details = []

    # Days since last activity (decay)
    last_act_days = days_ago(deal.get("last_activity_date"))
    if last_act_days <= 3:
        mom += 10
        mom_details.append(f"last({last_act_days}d):+10")
    elif last_act_days <= 7:
        mom += 7
        mom_details.append(f"last({last_act_days}d):+7")
    elif last_act_days <= 14:
        mom += 4
        mom_details.append(f"last({last_act_days}d):+4")
    elif last_act_days <= 30:
        mom += 1
        mom_details.append(f"last({last_act_days}d):+1")
    else:
        mom_details.append(f"last({last_act_days}d):0")

    # Has upcoming activity (+8)
    next_act = deal.get("next_activity_date")
    next_act_days = days_ago(next_act) if next_act else 999
    if next_act:
        if next_act_days <= 0:  # Future or today
            mom += 8
            mom_details.append("next_ok:+8")
        elif next_act_days <= 3:  # Overdue by 1-3 days
            mom += 4
            mom_details.append(f"next_overdue({next_act_days}d):+4")
        else:
            mom += 1
            mom_details.append(f"next_stale({next_act_days}d):+1")
    else:
        mom_details.append("no_next:0")

    # Stage progression speed
    stage_age = days_ago(deal.get("stage_change_time", "")[:10] if deal.get("stage_change_time") else "")
    if is_sales:
        stage_order = SALES_STAGES.get(stage_id, ("", 0))[1]
        if stage_order >= 4 and stage_age <= 14:  # Proposal+ and recent
            mom += 7
            mom_details.append(f"fast_adv:+7")
        elif stage_order >= 3 and stage_age <= 21:
            mom += 4
            mom_details.append(f"good_adv:+4")
        elif stage_order >= 2:
            mom += 2
            mom_details.append(f"progressing:+2")

    mom = min(mom, 25)

    total = fit + eng + mom
    details = {
        "fit": fit, "eng": eng, "mom": mom, "total": total,
        "fit_d": " ".join(fit_details),
        "eng_d": " ".join(eng_details),
        "mom_d": " ".join(mom_details),
    }
    return details


def priority_label(score):
    if score >= 80:
        return "HOT"
    elif score >= 60:
        return "WARM"
    elif score >= 40:
        return "COOL"
    else:
        return "COLD"


def priority_emoji(label):
    return {"HOT": "🔥", "WARM": "🟡", "COOL": "🔵", "COLD": "⚪"}.get(label, "")


def get_pipeline_name(stage_id):
    if stage_id in SALES_STAGES:
        return "Sales"
    if stage_id in ONBOARDING_STAGES:
        return "Onboarding"
    if stage_id in PARTNERSHIP_STAGES:
        return "Partnerships"
    if stage_id in CHURNED_STAGES:
        return "Churned"
    return "Other"


def get_stage_name(stage_id):
    if stage_id in SALES_STAGES:
        return SALES_STAGES[stage_id][0]
    if stage_id in ONBOARDING_STAGES:
        return ONBOARDING_STAGES[stage_id][0]
    return PARTNERSHIP_STAGES.get(stage_id, CHURNED_STAGES.get(stage_id, f"Stage {stage_id}"))


def main():
    import sys
    write_notes = "--write-notes" in sys.argv
    josef_only = "--josef-only" in sys.argv

    env = load_env(ENV_PATH)
    base = env["PIPEDRIVE_BASE_URL"].rstrip("/")
    token = env["PIPEDRIVE_API_TOKEN"]
    my_id = int(env["PIPEDRIVE_USER_ID"])

    print("Fetching open deals...")
    all_deals = paged_get(base, token, "/api/v1/deals", {"status": "open"})
    print(f"  Total open deals: {len(all_deals)}")

    # Score all deals
    scored = []
    for deal in all_deals:
        owner = deal.get("user_id")
        if isinstance(owner, dict):
            owner_id = owner.get("id")
            owner_name = owner.get("name", "?")
        else:
            owner_id = owner
            owner_name = "?"

        if josef_only and owner_id != my_id:
            continue

        scores = score_deal(deal)
        stage_id = deal.get("stage_id")
        pipeline = get_pipeline_name(stage_id)
        stage_name = get_stage_name(stage_id)

        scored.append({
            "id": deal["id"],
            "title": deal.get("title", ""),
            "org": deal.get("org_name") or "—",
            "value": deal.get("value") or 0,
            "currency": deal.get("currency", "CZK"),
            "stage_id": stage_id,
            "stage": stage_name,
            "pipeline": pipeline,
            "owner_id": owner_id,
            "owner": owner_name,
            "next_act": deal.get("next_activity_date") or "—",
            "last_act": deal.get("last_activity_date") or "—",
            "add_time": (deal.get("add_time") or "")[:10],
            **scores,
        })

    # Sort by total score descending
    scored.sort(key=lambda x: x["total"], reverse=True)

    # === GENERATE DEAL_SCORING.md ===
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# Deal Scoring — Echo Pulse Sales Machine",
        f"",
        f"> Generated by lead_scorer.py | {now}",
        f"> Scored {len(scored)} deals | Formula: Fit(0-40) + Engagement(0-35) + Momentum(0-25) = 0-100",
        f"> **MISSION:** Sell Echo Pulse (50% commission, 99-129 CZK/person, cap 200). Echo Pulse deals get score boost.",
        "",
    ]

    # Summary stats
    sales_deals = [s for s in scored if s["pipeline"] == "Sales"]
    josef_deals = [s for s in scored if s["owner_id"] == my_id]
    josef_sales = [s for s in sales_deals if s["owner_id"] == my_id]
    hot = [s for s in scored if s["total"] >= 80]
    warm = [s for s in scored if 60 <= s["total"] < 80]
    cool = [s for s in scored if 40 <= s["total"] < 60]
    cold = [s for s in scored if s["total"] < 40]

    lines.append("## Summary")
    lines.append(f"- **Total scored:** {len(scored)}")
    lines.append(f"- **Sales pipeline:** {len(sales_deals)} deals")
    lines.append(f"- **Josef's deals:** {len(josef_deals)} ({len(josef_sales)} in sales)")
    lines.append(f"- 🔥 HOT (80+): **{len(hot)}**")
    lines.append(f"- 🟡 WARM (60-79): **{len(warm)}**")
    lines.append(f"- 🔵 COOL (40-59): **{len(cool)}**")
    lines.append(f"- ⚪ COLD (<40): **{len(cold)}**")
    total_value = sum(s["value"] for s in sales_deals if s["currency"] == "CZK")
    lines.append(f"- **Sales pipeline value:** {total_value:,.0f} CZK")
    lines.append("")

    # === TODAY'S PRIORITY CALLS (Josef's HOT + WARM sales deals) ===
    lines.append("## 📞 TODAY'S PRIORITY CALLS (Josef)")
    lines.append("")
    today_calls = [s for s in scored if s["owner_id"] == my_id and s["pipeline"] == "Sales" and s["total"] >= 50]
    today_calls.sort(key=lambda x: x["total"], reverse=True)

    if today_calls:
        lines.append("| # | Score | Deal | Org | Stage | Value | Next Act | Action |")
        lines.append("|---|-------|------|-----|-------|-------|----------|--------|")
        for i, s in enumerate(today_calls, 1):
            prio = priority_label(s["total"])
            emoji = priority_emoji(prio)
            val_str = f"{s['value']:,.0f}" if s["value"] else "—"
            # Determine suggested action
            if s["next_act"] == "—":
                action = "⚠️ SCHEDULE NEXT STEP"
            elif days_ago(s["next_act"]) > 0:
                action = f"⚠️ OVERDUE {days_ago(s['next_act'])}d"
            elif days_ago(s["next_act"]) == 0:
                action = "📞 CALL TODAY"
            else:
                action = f"Scheduled {s['next_act']}"
            lines.append(f"| {i} | {emoji} {s['total']} | {s['title'][:30]} | {s['org'][:25]} | {s['stage']} | {val_str} | {s['next_act']} | {action} |")
        lines.append("")
    else:
        lines.append("_No priority deals found._")
        lines.append("")

    # === DEALS NEEDING ATTENTION ===
    no_next = [s for s in scored if s["owner_id"] == my_id and s["pipeline"] == "Sales" and s["next_act"] == "—"]
    overdue = [s for s in scored if s["owner_id"] == my_id and s["pipeline"] == "Sales" and s["next_act"] != "—" and days_ago(s["next_act"]) > 0]

    if no_next:
        lines.append("## ⚠️ NO NEXT ACTIVITY (Josef, Sales)")
        lines.append("")
        lines.append("| Deal | Org | Stage | Score | Last Activity |")
        lines.append("|------|-----|-------|-------|--------------|")
        for s in sorted(no_next, key=lambda x: x["total"], reverse=True):
            lines.append(f"| {s['title'][:30]} | {s['org'][:25]} | {s['stage']} | {s['total']} | {s['last_act']} |")
        lines.append("")

    if overdue:
        lines.append("## ⏰ OVERDUE ACTIVITIES (Josef, Sales)")
        lines.append("")
        lines.append("| Deal | Org | Stage | Score | Overdue Since | Days |")
        lines.append("|------|-----|-------|-------|--------------|------|")
        for s in sorted(overdue, key=lambda x: days_ago(x["next_act"]), reverse=True):
            lines.append(f"| {s['title'][:30]} | {s['org'][:25]} | {s['stage']} | {s['total']} | {s['next_act']} | {days_ago(s['next_act'])} |")
        lines.append("")

    # === FULL SCORED TABLE — Sales Pipeline ===
    lines.append("## 📊 Full Scores — Sales Pipeline")
    lines.append("")
    lines.append("| Rank | Score | Fit | Eng | Mom | Deal | Org | Stage | Value | Owner | Next |")
    lines.append("|------|-------|-----|-----|-----|------|-----|-------|-------|-------|------|")
    rank = 0
    for s in scored:
        if s["pipeline"] != "Sales":
            continue
        rank += 1
        prio = priority_label(s["total"])
        emoji = priority_emoji(prio)
        val_str = f"{s['value']:,.0f}" if s["value"] else "—"
        owner_short = s["owner"].split()[0] if s["owner"] != "?" else "?"
        lines.append(f"| {rank} | {emoji} {s['total']} | {s['fit']} | {s['eng']} | {s['mom']} | {s['title'][:25]} | {s['org'][:20]} | {s['stage'][:15]} | {val_str} | {owner_short} | {s['next_act']} |")
    lines.append("")

    # === OTHER PIPELINES (summary) ===
    for pipe in ["Onboarding", "Partnerships", "Churned"]:
        pipe_deals = [s for s in scored if s["pipeline"] == pipe]
        if pipe_deals:
            lines.append(f"## {pipe} ({len(pipe_deals)} deals)")
            lines.append("")
            lines.append("| Score | Deal | Org | Stage | Owner |")
            lines.append("|-------|------|-----|-------|-------|")
            for s in pipe_deals[:15]:
                owner_short = s["owner"].split()[0] if s["owner"] != "?" else "?"
                lines.append(f"| {s['total']} | {s['title'][:25]} | {s['org'][:20]} | {s['stage'][:15]} | {owner_short} |")
            if len(pipe_deals) > 15:
                lines.append(f"| ... | +{len(pipe_deals)-15} more | | | |")
            lines.append("")

    # === SCORING BREAKDOWN (top 10) ===
    lines.append("## 🔍 Score Breakdown (Top 10)")
    lines.append("")
    for s in scored[:10]:
        lines.append(f"**{s['title']}** ({s['org']}) — Score: {s['total']}")
        lines.append(f"- Fit({s['fit']}): {s['fit_d']}")
        lines.append(f"- Eng({s['eng']}): {s['eng_d']}")
        lines.append(f"- Mom({s['mom']}): {s['mom_d']}")
        lines.append("")

    report = "\n".join(lines)
    SCORING_OUTPUT.write_text(report)
    print(f"\n✅ DEAL_SCORING.md written ({len(scored)} deals scored)")

    # === GENERATE PIPELINE_STATUS.md ===
    pipe_lines = [
        f"# Pipeline Status — {TODAY.strftime('%-d. %-m. %Y')}",
        "",
        f"> Auto-generated by lead_scorer.py | {now}",
        "",
        "## Totals",
    ]

    by_pipeline = {}
    for s in scored:
        p = s["pipeline"]
        by_pipeline.setdefault(p, []).append(s)

    for pipe_name in ["Sales", "Onboarding", "Partnerships", "Churned"]:
        deals = by_pipeline.get(pipe_name, [])
        total_val = sum(d["value"] for d in deals if d["currency"] == "CZK")
        pipe_lines.append(f"- **{pipe_name}:** {len(deals)} deals / {total_val:,.0f} CZK")

    pipe_lines.append("")

    # Josef's today
    josef_today = [s for s in scored if s["owner_id"] == my_id and s["pipeline"] == "Sales" and s["next_act"] != "—" and days_ago(s["next_act"]) <= 0]
    if josef_today:
        pipe_lines.append("## 📅 Josef's Activities Today")
        pipe_lines.append("")
        pipe_lines.append("| Deal | Org | Stage | Score | Activity Date |")
        pipe_lines.append("|------|-----|-------|-------|--------------|")
        for s in sorted(josef_today, key=lambda x: x["total"], reverse=True):
            pipe_lines.append(f"| {s['title'][:30]} | {s['org'][:25]} | {s['stage']} | {s['total']} | {s['next_act']} |")
        pipe_lines.append("")

    # Overdue for Josef
    if overdue:
        pipe_lines.append("## ⏰ Overdue (Josef)")
        pipe_lines.append("")
        for s in sorted(overdue, key=lambda x: days_ago(x["next_act"]), reverse=True):
            pipe_lines.append(f"- **{s['title']}** ({s['org']}) — overdue {days_ago(s['next_act'])}d, score {s['total']}")
        pipe_lines.append("")

    # No next step
    if no_next:
        pipe_lines.append("## ⚠️ No Next Step (Josef, Sales)")
        pipe_lines.append("")
        for s in sorted(no_next, key=lambda x: x["total"], reverse=True):
            pipe_lines.append(f"- **{s['title']}** ({s['org']}) — {s['stage']}, score {s['total']}")
        pipe_lines.append("")

    # Recommended actions
    pipe_lines.append("## 💡 Recommended Actions")
    pipe_lines.append("")
    if no_next:
        pipe_lines.append(f"1. **Schedule next steps** for {len(no_next)} deals missing activities")
    if overdue:
        pipe_lines.append(f"2. **Clear {len(overdue)} overdue activities** — reschedule or complete them")
    stale_warm = [s for s in josef_sales if s["total"] >= 50 and days_ago(s["last_act"]) > 14]
    if stale_warm:
        pipe_lines.append(f"3. **Re-engage {len(stale_warm)} warm deals** that went quiet (14+ days)")
    high_value_early = [s for s in josef_sales if s["value"] >= 50000 and s["stage_id"] in (7, 8)]
    if high_value_early:
        pipe_lines.append(f"4. **Accelerate {len(high_value_early)} high-value early-stage deals** to demo/proposal")
    pipe_lines.append("")

    pipe_report = "\n".join(pipe_lines)
    PIPELINE_OUTPUT.write_text(pipe_report)
    print(f"✅ PIPELINE_STATUS.md written")

    # === WRITE SCORING LOG ===
    log_lines = [
        "# Scoring Log",
        "",
        f"> Last run: {now}",
        f"> Deals scored: {len(scored)}",
        f"> HOT: {len(hot)} | WARM: {len(warm)} | COOL: {len(cool)} | COLD: {len(cold)}",
        "",
    ]
    log_entry = f"| {now} | {len(scored)} | {len(hot)} | {len(warm)} | {len(cool)} | {len(cold)} |"

    # Append to log
    if SCORING_LOG.exists():
        existing = SCORING_LOG.read_text()
        if "| Date |" in existing:
            existing = existing.rstrip() + "\n" + log_entry + "\n"
            SCORING_LOG.write_text(existing)
        else:
            log_lines.append("| Date | Scored | HOT | WARM | COOL | COLD |")
            log_lines.append("|------|--------|-----|------|------|------|")
            log_lines.append(log_entry)
            SCORING_LOG.write_text("\n".join(log_lines))
    else:
        log_lines.append("| Date | Scored | HOT | WARM | COOL | COLD |")
        log_lines.append("|------|--------|-----|------|------|------|")
        log_lines.append(log_entry)
        SCORING_LOG.write_text("\n".join(log_lines))

    print(f"✅ SCORING_LOG.md updated")

    # === OPTIONAL: Write scores to Pipedrive deal notes ===
    if write_notes:
        print("\nWriting scores to Pipedrive deal notes...")
        written = 0
        for s in scored:
            if s["pipeline"] != "Sales":
                continue
            prio = priority_label(s["total"])
            note_text = (
                f"🤖 Lead Score: {s['total']}/100 ({prio})\n"
                f"Fit: {s['fit']}/40 | Engagement: {s['eng']}/35 | Momentum: {s['mom']}/25\n"
                f"Generated: {now}"
            )
            try:
                api_request(base, token, "POST", "/api/v1/notes", data={
                    "deal_id": s["id"],
                    "content": note_text,
                    "pinned_to_deal_flag": 1,
                })
                written += 1
                if written % 10 == 0:
                    print(f"  ...{written} notes written")
                time.sleep(0.3)  # Rate limit protection
            except Exception as e:
                print(f"  Error writing note for deal {s['id']}: {e}")
        print(f"✅ {written} deal notes written to Pipedrive")

    # Print summary to stdout for cron output
    print(f"\n{'='*60}")
    print(f"  LEAD SCORING COMPLETE — {now}")
    print(f"  {len(scored)} deals scored")
    print(f"  🔥 HOT: {len(hot)} | 🟡 WARM: {len(warm)} | 🔵 COOL: {len(cool)} | ⚪ COLD: {len(cold)}")
    if today_calls:
        print(f"  📞 Josef's priority calls today: {len(today_calls)}")
    if no_next:
        print(f"  ⚠️  Deals missing next step: {len(no_next)}")
    if overdue:
        print(f"  ⏰ Overdue activities: {len(overdue)}")
    print(f"{'='*60}")

    return scored


if __name__ == "__main__":
    main()
