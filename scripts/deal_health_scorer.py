#!/usr/bin/env python3
"""
Deal Health Scorer — komplexní health score pro každý deal v pipeline.

Skóre se skládá z 7 faktorů (max 100 bodů):
1. Next step coverage (0-20) — má naplánovanou další aktivitu?
2. Activity recency (0-20) — jak čerstvý je poslední kontakt?
3. Multi-threading (0-15) — kolik kontaktů je na dealu?
4. Stage velocity (0-15) — jak rychle se deal pohybuje?
5. CRM field coverage (0-10) — je vyplněná hodnota, org, kontakt?
6. Commitment stage (0-10) — kde je v yes-ladder?
7. Activity volume (0-10) — celkový počet touchpointů

Navíc:
- Call coaching z Fathom transcriptů (talk ratio, SPIN analysis)
- Multi-threading report (single-threaded deals = risk)
- Week-over-week velocity trending
- Saved snapshots pro historické porovnání

Usage:
  python3 scripts/deal_health_scorer.py                # full health report
  python3 scripts/deal_health_scorer.py --deal 360     # specific deal
  python3 scripts/deal_health_scorer.py --coaching      # call coaching report
  python3 scripts/deal_health_scorer.py --snapshot      # save weekly snapshot
  python3 scripts/deal_health_scorer.py --trend         # show velocity trends
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
from lib.pipedrive import pipedrive_api, fathom_api

LOG_FILE = LOGS_DIR / "deal-health.log"
SNAPSHOTS_DIR = WORKSPACE / "knowledge" / "pipeline_snapshots"
COACHING_DIR = WORKSPACE / "knowledge" / "call_coaching"


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")



# ─── DEAL HEALTH SCORING ────────────────────────────────────

def score_next_step(deal):
    """Score: Does the deal have a next step? (0-20)"""
    next_date = deal.get("next_activity_date", "")
    if not next_date:
        return 0, "❌ Žádný next step"

    try:
        next_dt = datetime.strptime(next_date, "%Y-%m-%d")
        now = datetime.now()
        days = (next_dt - now).days

        if days < 0:
            return 5, f"⏰ Overdue {abs(days)}d"
        elif days <= 7:
            return 20, f"✅ Za {days}d"
        elif days <= 14:
            return 15, f"📅 Za {days}d"
        else:
            return 10, f"📅 Za {days}d (daleko)"
    except ValueError:
        return 5, "⚠️ Neplatné datum"


def score_activity_recency(deal):
    """Score: How fresh is the last activity? (0-20)"""
    last = deal.get("last_activity_date", "")
    if not last:
        return 0, "❌ Žádná aktivita"

    try:
        last_dt = datetime.strptime(last, "%Y-%m-%d")
        days = (datetime.now() - last_dt).days

        if days <= 3:
            return 20, f"🔥 {days}d"
        elif days <= 7:
            return 15, f"✅ {days}d"
        elif days <= 14:
            return 10, f"🟡 {days}d"
        elif days <= 21:
            return 5, f"🟠 {days}d"
        else:
            return 0, f"🔴 {days}d ghosting"
    except ValueError:
        return 0, "⚠️ Neplatné datum"


def score_multi_threading(deal, token):
    """Score: How many contacts are on this deal? (0-15)"""
    deal_id = deal["id"]
    participants = pipedrive_api(token, "GET", f"/deals/{deal_id}/participants", {
        "limit": "20",
    })
    count = len(participants) if participants else 0

    # Also check person directly
    if count == 0 and deal.get("person_id"):
        count = 1

    if count >= 3:
        return 15, f"✅ {count} kontaktů"
    elif count == 2:
        return 10, f"👥 {count} kontakty"
    elif count == 1:
        return 5, f"⚠️ Single-threaded"
    else:
        return 0, "❌ Žádný kontakt"


def score_stage_velocity(deal):
    """Score: How fast is the deal moving through stages? (0-15)"""
    stage = deal.get("stage_order_nr", 0)
    add_time = deal.get("add_time", "")

    if not add_time:
        return 5, "⚠️ Neznámý věk"

    try:
        add_dt = datetime.strptime(add_time[:10], "%Y-%m-%d")
        age = (datetime.now() - add_dt).days

        if age == 0:
            age = 1

        # Days per stage
        if stage > 0:
            days_per_stage = age / stage
        else:
            days_per_stage = age

        if days_per_stage <= 14:
            return 15, f"🚀 {days_per_stage:.0f}d/stage"
        elif days_per_stage <= 30:
            return 10, f"✅ {days_per_stage:.0f}d/stage"
        elif days_per_stage <= 60:
            return 5, f"🟡 {days_per_stage:.0f}d/stage"
        else:
            return 0, f"🐌 {days_per_stage:.0f}d/stage"
    except ValueError:
        return 5, "⚠️ Parse error"


def score_crm_coverage(deal):
    """Score: How well-filled is the CRM data? (0-10)"""
    fields_present = 0
    fields_total = 5

    if deal.get("value", 0) > 0:
        fields_present += 1
    if deal.get("org_id"):
        fields_present += 1
    if deal.get("person_id"):
        fields_present += 1
    if deal.get("expected_close_date"):
        fields_present += 1
    if deal.get("stage_order_nr", 0) > 0:
        fields_present += 1

    pct = fields_present / fields_total
    score = round(pct * 10)

    if pct >= 0.8:
        return score, f"✅ {fields_present}/{fields_total} polí"
    elif pct >= 0.6:
        return score, f"🟡 {fields_present}/{fields_total} polí"
    else:
        missing = []
        if not deal.get("value", 0):
            missing.append("value")
        if not deal.get("expected_close_date"):
            missing.append("close date")
        return score, f"🔴 {fields_present}/{fields_total} — chybí: {', '.join(missing)}"


def score_commitment_stage(deal):
    """Score: Where is this deal in the commitment ladder? (0-10)
    Inferred from stage + activities + notes."""
    stage = deal.get("stage_order_nr", 0)
    has_next = bool(deal.get("next_activity_date"))
    has_value = deal.get("value", 0) > 0

    # Map stage to commitment
    if stage >= 5:
        return 10, "🎯 Closing"
    elif stage >= 4:
        return 8, "📋 Proposal/Pilot"
    elif stage >= 3:
        return 6, "🤝 Multi-thread/Demo"
    elif stage >= 2:
        return 4, "📞 Meeting done"
    elif stage >= 1:
        return 2, "📧 First contact"
    else:
        return 0, "❓ New"


def score_activity_volume(deal, token):
    """Score: Total touchpoints on this deal. (0-10)"""
    deal_id = deal["id"]
    activities = pipedrive_api(token, "GET", f"/deals/{deal_id}/activities", {
        "limit": "50", "done": "1",
    })
    count = len(activities) if activities else 0

    if count >= 8:
        return 10, f"✅ {count} touchpointů"
    elif count >= 5:
        return 7, f"👍 {count} touchpointů"
    elif count >= 3:
        return 5, f"🟡 {count} touchpointů"
    elif count >= 1:
        return 3, f"⚠️ {count} touchpoint"
    else:
        return 0, "❌ 0 touchpointů"


def calculate_deal_health(deal, token, detailed=False):
    """Calculate comprehensive health score for a deal."""
    scores = {}

    s1, d1 = score_next_step(deal)
    scores["next_step"] = {"score": s1, "max": 20, "detail": d1}

    s2, d2 = score_activity_recency(deal)
    scores["recency"] = {"score": s2, "max": 20, "detail": d2}

    s5, d5 = score_crm_coverage(deal)
    scores["crm_coverage"] = {"score": s5, "max": 10, "detail": d5}

    s6, d6 = score_commitment_stage(deal)
    scores["commitment"] = {"score": s6, "max": 10, "detail": d6}

    s4, d4 = score_stage_velocity(deal)
    scores["velocity"] = {"score": s4, "max": 15, "detail": d4}

    # These require extra API calls — only for detailed mode or specific deal
    if detailed:
        s3, d3 = score_multi_threading(deal, token)
        scores["multi_thread"] = {"score": s3, "max": 15, "detail": d3}

        s7, d7 = score_activity_volume(deal, token)
        scores["activity_vol"] = {"score": s7, "max": 10, "detail": d7}
    else:
        # Estimate from available data
        pid = deal.get("person_id")
        s3 = 5 if pid else 0
        scores["multi_thread"] = {"score": s3, "max": 15, "detail": "⚠️ Single-threaded (est.)" if pid else "❌ Žádný kontakt"}
        scores["activity_vol"] = {"score": 5, "max": 10, "detail": "— (estimated)"}

    total = sum(s["score"] for s in scores.values())
    max_total = sum(s["max"] for s in scores.values())

    return {
        "deal_id": deal["id"],
        "title": deal.get("title", ""),
        "org": deal.get("org_name", "") or "",
        "value": deal.get("value", 0),
        "stage": deal.get("stage_order_nr", 0),
        "total_score": total,
        "max_score": max_total,
        "pct": round(total / max_total * 100) if max_total > 0 else 0,
        "scores": scores,
        "risk_flags": get_risk_flags(deal, scores),
    }


def get_risk_flags(deal, scores):
    """Identify specific risk flags for a deal."""
    flags = []
    if scores["next_step"]["score"] == 0:
        flags.append("NO_NEXT_STEP")
    if scores["recency"]["score"] <= 5:
        flags.append("STALE")
    if scores["multi_thread"]["score"] <= 5 and deal.get("value", 0) > 50000:
        flags.append("SINGLE_THREADED_HIGH_VALUE")
    if scores["crm_coverage"]["score"] < 6:
        flags.append("MISSING_CRM_DATA")
    if scores["velocity"]["score"] == 0:
        flags.append("SLOW_VELOCITY")
    if scores["recency"]["score"] == 0:
        flags.append("GHOSTING")
    return flags


# ─── CALL COACHING ───────────────────────────────────────────

def analyze_call_coaching(fathom_key):
    """Analyze Fathom recordings for coaching insights."""
    log("Fetching Fathom meetings for coaching analysis...")
    result = fathom_api(fathom_key, "/meetings", {
        "include_transcript": "true",
        "include_summary": "true",
    })
    if not result:
        log("No Fathom data available")
        return None

    meetings = result.get("items", [])
    if not meetings:
        log("No meetings found in Fathom")
        return None

    coaching_results = []
    for m in meetings:
        transcript = m.get("transcript", [])
        if not transcript or len(transcript) < 10:
            continue

        title = m.get("title") or m.get("meeting_title") or ""
        created = m.get("created_at", "")[:10]
        rid = m.get("recording_id", "")

        # Analyze talk ratio
        my_words = 0
        their_words = 0
        my_segments = 0
        their_segments = 0

        # Question analysis
        situation_q = 0
        problem_q = 0
        implication_q = 0
        need_payoff_q = 0
        total_questions = 0

        # Identify "my" speaker (Josef / Behavera)
        my_names = {"josef", "hofman", "behavera"}

        for seg in transcript:
            speaker = (seg.get("speaker", {}).get("display_name", "") or "").lower()
            text = seg.get("text", "")
            words = len(text.split())

            is_me = any(n in speaker for n in my_names)

            if is_me:
                my_words += words
                my_segments += 1

                # Count questions
                if "?" in text:
                    total_questions += 1
                    text_lower = text.lower()
                    # Simple SPIN classification
                    if any(w in text_lower for w in ["kolik", "jak velk", "kolika", "kdo ", "kde ", "jaký systém", "co používáte"]):
                        situation_q += 1
                    elif any(w in text_lower for w in ["problém", "trápí", "potíž", "výzv", "obtíž", "necítí", "frustr", "nespokojen"]):
                        problem_q += 1
                    elif any(w in text_lower for w in ["dopad", "následek", "stojí", "ztráta", "odchod", "fluktu", "náklad", "co to znamená", "co se stane"]):
                        implication_q += 1
                    elif any(w in text_lower for w in ["kdyby", "představte", "pomohl", "přínos", "zlepš", "ušetř", "co by to", "jak by"]):
                        need_payoff_q += 1
                    else:
                        situation_q += 1  # default to situation
            else:
                their_words += words
                their_segments += 1

        total_words = my_words + their_words
        if total_words == 0:
            continue

        talk_ratio = round(my_words / total_words * 100)
        listen_ratio = 100 - talk_ratio

        # Coaching assessment
        coaching = {
            "recording_id": rid,
            "title": title,
            "date": created,
            "segments": len(transcript),
            "my_words": my_words,
            "their_words": their_words,
            "talk_ratio": talk_ratio,
            "listen_ratio": listen_ratio,
            "total_questions": total_questions,
            "spin_distribution": {
                "situation": situation_q,
                "problem": problem_q,
                "implication": implication_q,
                "need_payoff": need_payoff_q,
            },
            "tips": [],
        }

        # Generate coaching tips
        if talk_ratio > 60:
            coaching["tips"].append(f"🗣️ Talk ratio {talk_ratio}% — příliš mluvíš. Target: 46% (Gong benchmark)")
        elif talk_ratio < 35:
            coaching["tips"].append(f"🤫 Talk ratio {talk_ratio}% — mluvíš málo. Neztrácej kontrolu nad konverzací.")
        else:
            coaching["tips"].append(f"✅ Talk ratio {talk_ratio}% — v zóně (Gong target: 46%)")

        spin_total = situation_q + problem_q + implication_q + need_payoff_q
        if spin_total > 0:
            sit_pct = round(situation_q / spin_total * 100)
            imp_pct = round((implication_q + need_payoff_q) / spin_total * 100)
            if sit_pct > 35:
                coaching["tips"].append(f"⚠️ {sit_pct}% Situation otázek — příliš. Target: <15%")
            if imp_pct < 30:
                coaching["tips"].append(f"⚠️ {imp_pct}% Implication+Need-payoff — málo. Target: >50%")
            else:
                coaching["tips"].append(f"✅ {imp_pct}% Implication+Need-payoff — dobré")

        if total_questions < 8:
            coaching["tips"].append(f"⚠️ Jen {total_questions} otázek — málo. Target: 11-14 (Gong)")
        elif total_questions > 16:
            coaching["tips"].append(f"⚠️ {total_questions} otázek — moc. Target: 11-14 (diminishing returns)")
        else:
            coaching["tips"].append(f"✅ {total_questions} otázek — v zóně")

        coaching_results.append(coaching)

    return coaching_results


# ─── VELOCITY TRENDING ───────────────────────────────────────

def save_snapshot(deals, velocity_data):
    """Save weekly pipeline snapshot for trending."""
    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")

    snapshot = {
        "date": today,
        "total_deals": len(deals),
        "total_value": sum(d.get("value", 0) for d in deals),
        "avg_age": velocity_data.get("avg_age", 0),
        "no_next_step": velocity_data.get("no_next_step", 0),
        "stale_14d": velocity_data.get("stale_14d", 0),
        "stage_distribution": {},
        "health_distribution": velocity_data.get("health_distribution", {}),
    }

    # Stage distribution
    for d in deals:
        stage = str(d.get("stage_order_nr", 0))
        snapshot["stage_distribution"][stage] = snapshot["stage_distribution"].get(stage, 0) + 1

    fpath = SNAPSHOTS_DIR / f"snapshot_{today}.json"
    fpath.write_text(json.dumps(snapshot, indent=2))
    log(f"Snapshot saved: {fpath}")
    return fpath


def load_snapshots(limit=8):
    """Load recent snapshots for trending."""
    if not SNAPSHOTS_DIR.exists():
        return []

    files = sorted(SNAPSHOTS_DIR.glob("snapshot_*.json"), reverse=True)[:limit]
    snapshots = []
    for f in files:
        try:
            snapshots.append(json.loads(f.read_text()))
        except Exception:
            pass
    return list(reversed(snapshots))  # oldest first


def format_trend(current, previous, unit="", lower_better=False):
    """Format trend indicator."""
    if previous is None or previous == 0:
        return "—"
    diff = current - previous
    if diff == 0:
        return "→"
    if lower_better:
        arrow = "▼" if diff < 0 else "▲"
        color = "🟢" if diff < 0 else "🔴"
    else:
        arrow = "▲" if diff > 0 else "▼"
        color = "🟢" if diff > 0 else "🔴"
    return f"{color}{arrow}{abs(diff)}{unit}"


# ─── MAIN REPORTS ────────────────────────────────────────────

def generate_health_report(health_scores, velocity_extras):
    """Generate the full health report."""
    lines = []
    lines.append("# Deal Health Report")
    lines.append(f"_{datetime.now().strftime('%d.%m.%Y %H:%M')}_\n")

    # Distribution
    healthy = sum(1 for h in health_scores if h["pct"] >= 70)
    at_risk = sum(1 for h in health_scores if 40 <= h["pct"] < 70)
    critical = sum(1 for h in health_scores if h["pct"] < 40)

    lines.append("## Pipeline Health Distribution\n")
    lines.append(f"🟢 Healthy (70+): **{healthy}** dealů")
    lines.append(f"🟡 At Risk (40-69): **{at_risk}** dealů")
    lines.append(f"🔴 Critical (<40): **{critical}** dealů")

    avg_health = sum(h["pct"] for h in health_scores) / len(health_scores) if health_scores else 0
    lines.append(f"\n📊 Průměrný health score: **{avg_health:.0f}/100**")

    # Multi-threading summary
    single_threaded = [h for h in health_scores if "SINGLE_THREADED_HIGH_VALUE" in h.get("risk_flags", [])]
    if single_threaded:
        lines.append(f"\n⚠️ **{len(single_threaded)} single-threaded high-value dealů:**")
        for h in single_threaded:
            lines.append(f"  • {h['org']} ({h['value']:,.0f} CZK) — přidej druhý kontakt!")

    # Velocity extras
    if velocity_extras:
        lines.append(f"\n## Velocity Trending\n")
        snapshots = velocity_extras.get("snapshots", [])
        if len(snapshots) >= 2:
            prev = snapshots[-2]
            curr = snapshots[-1]
            lines.append(f"| Metrika | Minulý týden | Tento týden | Trend |")
            lines.append(f"|---------|-------------|-------------|-------|")
            lines.append(f"| Deals | {prev['total_deals']} | {curr['total_deals']} | {format_trend(curr['total_deals'], prev['total_deals'])} |")
            lines.append(f"| Value | {prev['total_value']:,.0f} | {curr['total_value']:,.0f} | {format_trend(curr['total_value'], prev['total_value'])} |")
            lines.append(f"| Avg age | {prev.get('avg_age',0)}d | {curr.get('avg_age',0)}d | {format_trend(curr.get('avg_age',0), prev.get('avg_age',0), 'd', lower_better=True)} |")
            lines.append(f"| No next step | {prev['no_next_step']} | {curr['no_next_step']} | {format_trend(curr['no_next_step'], prev['no_next_step'], '', lower_better=True)} |")
            lines.append(f"| Stale 14d+ | {prev['stale_14d']} | {curr['stale_14d']} | {format_trend(curr['stale_14d'], prev['stale_14d'], '', lower_better=True)} |")
        else:
            lines.append("_Zatím jen 1 snapshot. Trending se zobrazí od příštího týdne._")

    # Top risk deals
    risk_deals = sorted(health_scores, key=lambda x: x["pct"])[:10]
    lines.append("\n## 🔴 Top 10 nejslabších dealů\n")
    lines.append("| # | Deal | Firma | Score | Flags |")
    lines.append("|---|------|-------|-------|-------|")
    for i, h in enumerate(risk_deals, 1):
        flags = ", ".join(h.get("risk_flags", [])[:3]) or "—"
        lines.append(f"| {i} | {h['title'][:22]} | {h['org'][:18]} | **{h['pct']}**/100 | {flags} |")

    # Top healthy deals
    top_deals = sorted(health_scores, key=lambda x: x["pct"], reverse=True)[:5]
    lines.append("\n## 🟢 Top 5 nejzdravějších dealů\n")
    lines.append("| # | Deal | Firma | Score | Stage |")
    lines.append("|---|------|-------|-------|-------|")
    for i, h in enumerate(top_deals, 1):
        lines.append(f"| {i} | {h['title'][:22]} | {h['org'][:18]} | **{h['pct']}**/100 | {h['stage']} |")

    # Actionable recommendations
    lines.append("\n## 🎯 Co udělat TEĎ\n")
    no_next = [h for h in health_scores if "NO_NEXT_STEP" in h.get("risk_flags", [])]
    if no_next:
        lines.append(f"1. **Naplánuj next step** pro {len(no_next)} dealů bez aktivity")
    ghosting = [h for h in health_scores if "GHOSTING" in h.get("risk_flags", [])]
    if ghosting:
        lines.append(f"2. **Rozhoduj: follow-up nebo disqualify** u {len(ghosting)} ghosting dealů")
    missing_crm = [h for h in health_scores if "MISSING_CRM_DATA" in h.get("risk_flags", [])]
    if missing_crm:
        lines.append(f"3. **Doplň CRM data** u {len(missing_crm)} dealů (value, close date)")
    if single_threaded:
        lines.append(f"4. **Multi-thread** {len(single_threaded)} dealů — přidej druhý kontakt (HR/CEO)")

    lines.append(f"\n---\n_Generováno: {datetime.now().strftime('%d.%m.%Y %H:%M')}_")
    return "\n".join(lines)


def format_coaching_report(coaching_results):
    """Format call coaching analysis."""
    if not coaching_results:
        return "# Call Coaching\n\n_Žádné Fathom nahrávky k analýze._"

    lines = []
    lines.append("# Call Coaching Report")
    lines.append(f"_{datetime.now().strftime('%d.%m.%Y %H:%M')}_\n")

    # Aggregate stats
    total_calls = len(coaching_results)
    avg_talk = sum(c["talk_ratio"] for c in coaching_results) / total_calls
    avg_questions = sum(c["total_questions"] for c in coaching_results) / total_calls

    lines.append(f"## Přehled ({total_calls} hovorů)\n")
    lines.append(f"- Průměrný talk ratio: **{avg_talk:.0f}%** (target: 46%)")
    lines.append(f"- Průměrný počet otázek: **{avg_questions:.0f}** (target: 11-14)")

    # SPIN distribution aggregate
    total_s = sum(c["spin_distribution"]["situation"] for c in coaching_results)
    total_p = sum(c["spin_distribution"]["problem"] for c in coaching_results)
    total_i = sum(c["spin_distribution"]["implication"] for c in coaching_results)
    total_n = sum(c["spin_distribution"]["need_payoff"] for c in coaching_results)
    spin_total = total_s + total_p + total_i + total_n

    if spin_total > 0:
        lines.append(f"\n## SPIN Distribution\n")
        lines.append(f"| Type | Count | % | Target % |")
        lines.append(f"|------|-------|---|----------|")
        lines.append(f"| Situation | {total_s} | {total_s/spin_total*100:.0f}% | <15% |")
        lines.append(f"| Problem | {total_p} | {total_p/spin_total*100:.0f}% | 25-30% |")
        lines.append(f"| Implication | {total_i} | {total_i/spin_total*100:.0f}% | 30-35% |")
        lines.append(f"| Need-Payoff | {total_n} | {total_n/spin_total*100:.0f}% | 20-25% |")

    # Per-call breakdown
    lines.append(f"\n## Detail per hovor\n")
    for c in coaching_results:
        lines.append(f"### {c['date']} — {c['title']}")
        lines.append(f"- Talk ratio: **{c['talk_ratio']}%** / Listen: **{c['listen_ratio']}%**")
        lines.append(f"- Otázky: **{c['total_questions']}** (S:{c['spin_distribution']['situation']} P:{c['spin_distribution']['problem']} I:{c['spin_distribution']['implication']} N:{c['spin_distribution']['need_payoff']})")
        for tip in c["tips"]:
            lines.append(f"  {tip}")
        lines.append("")

    return "\n".join(lines)


def main():
    secrets = load_secrets()
    token = secrets.get("PIPEDRIVE_API_TOKEN") or secrets.get("PIPEDRIVE_TOKEN")
    if not token:
        log("No Pipedrive token found in secrets")
        return 1

    fathom_key = secrets.get("FATHOM_API_KEY")
    if not fathom_key:
        log("No Fathom API key found in secrets")
        return 1

    coaching_mode = "--coaching" in sys.argv
    snapshot_mode = "--snapshot" in sys.argv
    trend_mode = "--trend" in sys.argv
    specific_deal = None
    for i, arg in enumerate(sys.argv):
        if arg == "--deal" and i + 1 < len(sys.argv):
            specific_deal = int(sys.argv[i + 1])

    # Call coaching report
    if coaching_mode:
        coaching = analyze_call_coaching(fathom_key)
        report = format_coaching_report(coaching)
        COACHING_DIR.mkdir(parents=True, exist_ok=True)
        fpath = COACHING_DIR / f"coaching_{datetime.now().strftime('%Y-%m-%d')}.md"
        fpath.write_text(report)
        print(report)
        log(f"Coaching report saved: {fpath}")
        return 0

    # Fetch deals
    log("Fetching deals...")
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
    log(f"  {len(deals)} open deals")

    # Score each deal
    log("Scoring deals...")
    health_scores = []
    detailed = bool(specific_deal)  # detailed mode for specific deal

    for d in deals:
        if specific_deal and d["id"] != specific_deal:
            continue
        h = calculate_deal_health(d, token, detailed=detailed)
        health_scores.append(h)

    # Specific deal — print detailed breakdown
    if specific_deal and health_scores:
        h = health_scores[0]
        print(f"\n{'='*50}")
        print(f"  DEAL HEALTH: {h['org']} (deal {h['deal_id']})")
        print(f"{'='*50}")
        print(f"\n  Total: {h['pct']}/100\n")
        for name, s in h["scores"].items():
            bar = "█" * s["score"] + "░" * (s["max"] - s["score"])
            print(f"  {name:15s} [{bar}] {s['score']:2d}/{s['max']:2d}  {s['detail']}")
        if h["risk_flags"]:
            print(f"\n  Risk flags: {', '.join(h['risk_flags'])}")
        return 0

    # Calculate velocity extras
    now = datetime.now()
    no_next = sum(1 for d in deals if not d.get("next_activity_date"))
    stale_14d = 0
    ages = []
    for d in deals:
        add_time = d.get("add_time", "")
        if add_time:
            try:
                age = (now - datetime.strptime(add_time[:10], "%Y-%m-%d")).days
                ages.append(age)
            except ValueError:
                pass
        last = d.get("last_activity_date", "")
        if last:
            try:
                if (now - datetime.strptime(last, "%Y-%m-%d")).days >= 14:
                    stale_14d += 1
            except ValueError:
                pass

    avg_age = sum(ages) / len(ages) if ages else 0
    velocity_data = {
        "avg_age": round(avg_age),
        "no_next_step": no_next,
        "stale_14d": stale_14d,
        "health_distribution": {
            "healthy": sum(1 for h in health_scores if h["pct"] >= 70),
            "at_risk": sum(1 for h in health_scores if 40 <= h["pct"] < 70),
            "critical": sum(1 for h in health_scores if h["pct"] < 40),
        },
    }

    # Save snapshot
    if snapshot_mode:
        save_snapshot(deals, velocity_data)

    # Load snapshots for trending
    snapshots = load_snapshots()
    velocity_extras = {"snapshots": snapshots} if snapshots else None

    if trend_mode and snapshots:
        print("\n## Velocity Trend\n")
        print(f"{'Date':12s} | {'Deals':>5s} | {'Value':>12s} | {'Avg Age':>7s} | {'No Next':>7s} | {'Stale':>5s}")
        print("-" * 65)
        for s in snapshots:
            print(f"{s['date']:12s} | {s['total_deals']:5d} | {s['total_value']:>12,.0f} | {s.get('avg_age',0):5d}d | {s['no_next_step']:7d} | {s['stale_14d']:5d}")
        return 0

    # Generate report
    report = generate_health_report(health_scores, velocity_extras)

    # Save report
    report_dir = WORKSPACE / "reports" / "health"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / f"health_{datetime.now().strftime('%Y-%m-%d')}.md"
    report_file.write_text(report)
    log(f"Report saved: {report_file}")

    print(report)

    # Telegram summary
    avg_h = sum(h["pct"] for h in health_scores) / len(health_scores) if health_scores else 0
    healthy_n = sum(1 for h in health_scores if h["pct"] >= 70)
    critical_n = sum(1 for h in health_scores if h["pct"] < 40)

    emoji = "🟢" if avg_h >= 70 else "🟡" if avg_h >= 50 else "🔴"
    tg = (
        f"{emoji} Deal Health Score: {avg_h:.0f}/100\n\n"
        f"🟢 {healthy_n} healthy | 🔴 {critical_n} critical\n"
        f"❌ {no_next} bez next step | 📉 {stale_14d} stale 14d+\n"
    )
    single_t = [h for h in health_scores if "SINGLE_THREADED_HIGH_VALUE" in h.get("risk_flags", [])]
    if single_t:
        tg += f"⚠️ {len(single_t)} single-threaded high-value dealů\n"

    notify_telegram(tg)
    log("Telegram sent")

    # Push to Notion
    notion_token = secrets.get("NOTION_TOKEN")
    if notion_token:
        push_analysis(notion_token, f"Deal Health {datetime.now().strftime('%d.%m')}",
                       "Deal Health", report[:1990],
                       deals_affected=len(health_scores))

    return 0


if __name__ == "__main__":
    exit(main())
