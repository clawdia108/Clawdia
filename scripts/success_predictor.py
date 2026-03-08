#!/usr/bin/env python3
"""
Deal Success Probability Predictor
====================================
Weighted scoring model that predicts deal win probability, detects at-risk
deals, forecasts pipeline revenue, and coaches reps on next-best actions.

Integrates with:
  - deal_velocity.py (stage timing / velocity data)
  - knowledge_graph.py (company/contact enrichment)
  - win_loss_analysis.py (historical win/loss patterns)
  - Pipedrive API (live deal data, activities, contacts)

Usage:
  python3 scripts/success_predictor.py predict              # All active deals
  python3 scripts/success_predictor.py predict <deal_id>    # Single deal
  python3 scripts/success_predictor.py risks                # At-risk deals
  python3 scripts/success_predictor.py forecast             # Revenue forecast
  python3 scripts/success_predictor.py coach <deal_id>      # Deal coaching
"""

import json
import math
import statistics
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
ENV_PATH = WORKSPACE / ".secrets" / "pipedrive.env"
PREDICTIONS_FILE = WORKSPACE / "knowledge" / "deal-predictions.json"
VELOCITY_FILE = WORKSPACE / "pipedrive" / "deal_velocity.json"
PATTERNS_FILE = WORKSPACE / "reviews" / "win_loss" / "patterns.json"
GRAPH_FILE = WORKSPACE / "knowledge" / "graph.json"
LOG_FILE = WORKSPACE / "logs" / "success-predictor.log"

TODAY = date.today()
NOW = datetime.now()

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

STAGE_BASE_PROBABILITY = {
    1: 10,   # Interested/Qualified
    2: 20,   # Demo Scheduled
    3: 30,   # Ongoing Discussion
    4: 45,   # Proposal made
    5: 60,   # Negotiation
    6: 70,   # Pilot
    7: 85,   # Contract Sent
    8: 95,   # Invoice sent
}

FIELD_LEAD_SOURCE = "545839ef97506e40a691aa34e0d24a82be08d624"
FIELD_PRODUCT = "f4f43d7b1284bc4049adb933c3f79ee2d327f637"
FIELD_USE_CASE = "5d832816b0d2d2a47a1d7b76f4382d3665d03020"
FIELD_MRR = "6c4a9ab5743abd972ed7746fb5d2a0035a543acf"

LEAD_SOURCE_LABELS = {89: "Cold", 88: "Inbound", 97: "Referral", 94: "Partner", 96: "Event", 98: "Customer"}

# Factor weights (must sum to 1.0)
WEIGHTS = {
    "stage_velocity":      0.20,
    "engagement":          0.20,
    "deal_size_fit":       0.10,
    "champion":            0.15,
    "activity_recency":    0.15,
    "industry_win_rate":   0.10,
    "stage_progression":   0.10,
}


# ── ENV & API ──────────────────────────────────────────

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


def slog(msg, level="INFO"):
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


def days_between(d1_str, d2_str=None):
    if not d1_str:
        return 999
    try:
        d1 = datetime.strptime(d1_str[:10], "%Y-%m-%d").date()
        d2 = datetime.strptime(d2_str[:10], "%Y-%m-%d").date() if d2_str else TODAY
        return abs((d2 - d1).days)
    except (ValueError, TypeError):
        return 999


def clamp(value, lo=0.0, hi=100.0):
    return max(lo, min(hi, value))


# ── DATA LOADERS ─────────────────────────────────────

def load_velocity_data():
    if VELOCITY_FILE.exists():
        try:
            return json.loads(VELOCITY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"deals": {}, "stage_stats": {}}


def load_win_loss_patterns():
    if PATTERNS_FILE.exists():
        try:
            return json.loads(PATTERNS_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def load_win_loss_analyses():
    win_loss_dir = WORKSPACE / "reviews" / "win_loss"
    analyses = []
    if not win_loss_dir.exists():
        return analyses
    for f in win_loss_dir.glob("*.json"):
        if f.name == "patterns.json":
            continue
        try:
            data = json.loads(f.read_text())
            if "deal_id" in data:
                analyses.append(data)
        except (json.JSONDecodeError, OSError):
            continue
    return analyses


def load_graph_data():
    if GRAPH_FILE.exists():
        try:
            return json.loads(GRAPH_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"nodes": {}, "edges": []}


# ── SUCCESS PREDICTOR ────────────────────────────────

class SuccessPredictor:
    """Weighted scoring model that predicts deal win probability (0-100)."""

    def __init__(self, base_url, api_token):
        self.base = base_url
        self.token = api_token
        self.velocity = load_velocity_data()
        self.patterns = load_win_loss_patterns()
        self.analyses = load_win_loss_analyses()
        self.graph = load_graph_data()
        self._won_deals_cache = None
        self._industry_win_rates_cache = None

    def predict_deal(self, deal):
        """Calculate success probability for a single deal. Returns prediction dict."""
        deal_id = str(deal["id"])
        stage_id = deal.get("stage_id")
        stage_info = SALES_STAGES.get(stage_id)
        if not stage_info:
            return None

        stage_name, stage_order = stage_info
        base_prob = STAGE_BASE_PROBABILITY.get(stage_order, 10)

        add_time = (deal.get("add_time") or "")[:10]
        last_activity = deal.get("last_activity_date") or ""
        next_activity = deal.get("next_activity_date") or ""
        stage_change = deal.get("stage_change_time") or ""
        stage_change_date = stage_change[:10] if stage_change else add_time
        value = deal.get("value") or 0
        org_name = deal.get("org_name") or ""

        days_in_pipeline = days_between(add_time)
        days_in_stage = days_between(stage_change_date)
        days_since_activity = days_between(last_activity) if last_activity else 999

        done_activities = deal.get("done_activities_count") or 0
        email_count = deal.get("email_messages_count") or 0
        participants = deal.get("participants_count") or 0

        # Owner
        owner = deal.get("user_id")
        owner_name = owner.get("name", "?") if isinstance(owner, dict) else "?"

        # Lead source
        lead_src = deal.get(FIELD_LEAD_SOURCE)
        lead_source = LEAD_SOURCE_LABELS.get(lead_src, "Unknown")

        # Velocity data for this deal
        vel_deal = self.velocity.get("deals", {}).get(deal_id, {})
        stage_stats = self.velocity.get("stage_stats", {})

        # --- FACTOR SCORES (each 0-100) ---

        velocity_score, velocity_detail = self._score_velocity(
            stage_id, days_in_stage, stage_stats
        )
        engagement_score, engagement_detail = self._score_engagement(
            done_activities, email_count, days_in_pipeline
        )
        size_fit_score, size_fit_detail = self._score_deal_size_fit(
            value, org_name
        )
        champion_score, champion_detail = self._score_champion(
            deal, participants, email_count
        )
        recency_score, recency_detail = self._score_activity_recency(
            days_since_activity, next_activity
        )
        industry_score, industry_detail = self._score_industry_win_rate(
            org_name, lead_source
        )
        progression_score, progression_detail = self._score_stage_progression(
            stage_order, days_in_pipeline, days_in_stage
        )

        factors = {
            "stage_velocity":   {"score": velocity_score,    "weight": WEIGHTS["stage_velocity"],    "detail": velocity_detail},
            "engagement":       {"score": engagement_score,  "weight": WEIGHTS["engagement"],        "detail": engagement_detail},
            "deal_size_fit":    {"score": size_fit_score,    "weight": WEIGHTS["deal_size_fit"],     "detail": size_fit_detail},
            "champion":         {"score": champion_score,    "weight": WEIGHTS["champion"],          "detail": champion_detail},
            "activity_recency": {"score": recency_score,     "weight": WEIGHTS["activity_recency"],  "detail": recency_detail},
            "industry_win_rate":{"score": industry_score,    "weight": WEIGHTS["industry_win_rate"], "detail": industry_detail},
            "stage_progression":{"score": progression_score, "weight": WEIGHTS["stage_progression"], "detail": progression_detail},
        }

        # Weighted combination
        weighted_sum = sum(f["score"] * f["weight"] for f in factors.values())

        # Blend with stage base probability (60% model, 40% stage base)
        probability = round(clamp(weighted_sum * 0.6 + base_prob * 0.4), 1)

        # Lead source bonus
        source_bonus = 0
        if lead_source == "Referral":
            source_bonus = 5
        elif lead_source == "Inbound":
            source_bonus = 3
        elif lead_source == "Cold":
            source_bonus = -3
        probability = round(clamp(probability + source_bonus), 1)

        prediction = {
            "deal_id": deal["id"],
            "title": deal.get("title", ""),
            "org": org_name,
            "owner": owner_name,
            "stage": stage_name,
            "stage_order": stage_order,
            "value": value,
            "currency": deal.get("currency", "CZK"),
            "probability": probability,
            "base_probability": base_prob,
            "lead_source": lead_source,
            "source_bonus": source_bonus,
            "days_in_pipeline": days_in_pipeline,
            "days_in_stage": days_in_stage,
            "days_since_activity": days_since_activity,
            "done_activities": done_activities,
            "email_count": email_count,
            "participants": participants,
            "factors": factors,
            "predicted_at": NOW.isoformat(),
        }

        return prediction

    def predict_all(self):
        """Predict success probability for all open sales deals."""
        slog("Fetching open deals for prediction...")
        deals = paged_get(self.base, self.token, "/api/v1/deals", {"status": "open"})
        sales_deals = [d for d in deals if d.get("stage_id") in SALES_STAGES]
        slog(f"Predicting {len(sales_deals)} sales deals")

        predictions = []
        for deal in sales_deals:
            pred = self.predict_deal(deal)
            if pred:
                predictions.append(pred)

        predictions.sort(key=lambda x: x["probability"], reverse=True)
        self._save_predictions(predictions)
        return predictions

    def predict_single(self, deal_id):
        """Predict success for a single deal by ID."""
        resp = api_request(self.base, self.token, "GET", f"/api/v1/deals/{deal_id}")
        if not resp or not resp.get("success") or not resp.get("data"):
            slog(f"Deal {deal_id} not found", "WARN")
            return None
        deal = resp["data"]
        pred = self.predict_deal(deal)
        if pred:
            self._save_predictions([pred], append=True)
        return pred

    def _save_predictions(self, predictions, append=False):
        PREDICTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = {}
        if append and PREDICTIONS_FILE.exists():
            try:
                data = json.loads(PREDICTIONS_FILE.read_text())
                existing = {str(p["deal_id"]): p for p in data.get("predictions", [])}
            except (json.JSONDecodeError, OSError):
                pass

        for pred in predictions:
            existing[str(pred["deal_id"])] = pred

        all_preds = sorted(existing.values(), key=lambda x: x["probability"], reverse=True)

        output = {
            "generated_at": NOW.isoformat(),
            "total_predicted": len(all_preds),
            "avg_probability": round(statistics.mean([p["probability"] for p in all_preds]), 1) if all_preds else 0,
            "predictions": all_preds,
        }
        PREDICTIONS_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))
        slog(f"Predictions saved: {len(all_preds)} deals -> {PREDICTIONS_FILE}")

    # ── SCORING FACTORS ──────────────────────────────

    def _score_velocity(self, stage_id, days_in_stage, stage_stats):
        """Faster than average = higher score."""
        sid = str(stage_id)
        stats = stage_stats.get(sid, {})
        avg = stats.get("avg", 0)

        if avg <= 0 or days_in_stage >= 999:
            return 50, "no baseline data"

        ratio = days_in_stage / avg
        if ratio <= 0.3:
            score = 95
            detail = f"{days_in_stage}d vs {avg:.0f}d avg — blazing fast"
        elif ratio <= 0.5:
            score = 85
            detail = f"{days_in_stage}d vs {avg:.0f}d avg — well ahead"
        elif ratio <= 0.8:
            score = 70
            detail = f"{days_in_stage}d vs {avg:.0f}d avg — on track"
        elif ratio <= 1.2:
            score = 50
            detail = f"{days_in_stage}d vs {avg:.0f}d avg — average"
        elif ratio <= 1.5:
            score = 30
            detail = f"{days_in_stage}d vs {avg:.0f}d avg — slowing"
        elif ratio <= 2.0:
            score = 15
            detail = f"{days_in_stage}d vs {avg:.0f}d avg — stalling"
        else:
            score = 5
            detail = f"{days_in_stage}d vs {avg:.0f}d avg — stuck"

        return score, detail

    def _score_engagement(self, done_activities, email_count, days_in_pipeline):
        """Touchpoint density relative to deal age."""
        total_touchpoints = done_activities + email_count
        age = max(days_in_pipeline, 1)
        density = total_touchpoints / age * 7  # touchpoints per week

        if density >= 3.0:
            score = 95
            detail = f"{total_touchpoints} touchpoints in {age}d ({density:.1f}/wk) — highly engaged"
        elif density >= 1.5:
            score = 80
            detail = f"{total_touchpoints} touchpoints in {age}d ({density:.1f}/wk) — strong"
        elif density >= 0.7:
            score = 60
            detail = f"{total_touchpoints} touchpoints in {age}d ({density:.1f}/wk) — moderate"
        elif density >= 0.3:
            score = 40
            detail = f"{total_touchpoints} touchpoints in {age}d ({density:.1f}/wk) — light"
        elif total_touchpoints >= 1:
            score = 20
            detail = f"{total_touchpoints} touchpoints in {age}d ({density:.1f}/wk) — sparse"
        else:
            score = 5
            detail = f"no touchpoints in {age}d"

        return score, detail

    def _score_deal_size_fit(self, value, org_name):
        """Score based on deal value fitting typical won deal ranges."""
        won_analyses = [a for a in self.analyses if a.get("outcome") == "WON"]
        won_values = [a.get("value", 0) for a in won_analyses if a.get("value", 0) > 0]

        if not won_values or value <= 0:
            return 50, "no value or no historical data"

        avg_won = statistics.mean(won_values)
        median_won = statistics.median(won_values)

        # How close is this deal to the typical won deal size?
        reference = median_won if median_won > 0 else avg_won
        if reference <= 0:
            return 50, "no reference value"

        ratio = value / reference
        if 0.5 <= ratio <= 2.0:
            score = 80
            detail = f"{value:,.0f} CZK — fits won deal sweet spot ({median_won:,.0f} median)"
        elif 0.3 <= ratio <= 3.0:
            score = 60
            detail = f"{value:,.0f} CZK — reasonable range (median won: {median_won:,.0f})"
        elif ratio > 3.0:
            score = 35
            detail = f"{value:,.0f} CZK — significantly above typical ({median_won:,.0f}) — may need longer cycle"
        else:
            score = 40
            detail = f"{value:,.0f} CZK — below typical won value ({median_won:,.0f})"

        return score, detail

    def _score_champion(self, deal, participants, email_count):
        """Evaluate champion / key contact engagement."""
        person = deal.get("person_id")
        has_contact = isinstance(person, dict)
        has_phone = False
        has_email = False
        contact_name = ""

        if has_contact:
            contact_name = person.get("name", "")
            phones = person.get("phone", [])
            has_phone = any(p.get("value") for p in phones if isinstance(p, dict))
            emails = person.get("email", [])
            has_email = any(e.get("value") for e in emails if isinstance(e, dict))

        score = 20  # baseline
        detail_parts = []

        if has_contact:
            score += 15
            detail_parts.append(f"contact: {contact_name}")
        else:
            detail_parts.append("no contact assigned")

        if has_phone:
            score += 10
            detail_parts.append("phone available")
        if has_email:
            score += 10
            detail_parts.append("email available")

        if participants >= 3:
            score += 25
            detail_parts.append(f"{participants} stakeholders — multi-threaded")
        elif participants >= 2:
            score += 15
            detail_parts.append(f"{participants} stakeholders")
        elif participants >= 1:
            score += 5
            detail_parts.append("single stakeholder")

        if email_count >= 5:
            score += 15
            detail_parts.append(f"{email_count} emails — strong dialogue")
        elif email_count >= 2:
            score += 5
            detail_parts.append(f"{email_count} emails")

        return clamp(score, 0, 100), "; ".join(detail_parts)

    def _score_activity_recency(self, days_since, next_activity_date):
        """More recent activity = higher score. Scheduled next activity = bonus."""
        if days_since >= 999:
            score = 5
            detail = "no activity recorded"
        elif days_since <= 1:
            score = 95
            detail = "active today/yesterday"
        elif days_since <= 3:
            score = 85
            detail = f"last activity {days_since}d ago — very recent"
        elif days_since <= 7:
            score = 70
            detail = f"last activity {days_since}d ago — recent"
        elif days_since <= 14:
            score = 45
            detail = f"last activity {days_since}d ago — getting cold"
        elif days_since <= 21:
            score = 25
            detail = f"last activity {days_since}d ago — going dark"
        elif days_since <= 30:
            score = 10
            detail = f"last activity {days_since}d ago — nearly dead"
        else:
            score = 5
            detail = f"last activity {days_since}d ago — zombie deal"

        # Bonus for scheduled next activity
        if next_activity_date:
            next_days = days_between(TODAY.isoformat(), next_activity_date)
            if next_days < 999:
                # Next activity is in the future
                if next_activity_date >= TODAY.isoformat():
                    score = min(score + 10, 100)
                    detail += f"; next scheduled in {next_days}d"
                else:
                    # Overdue
                    overdue = days_between(next_activity_date)
                    if overdue > 7:
                        score = max(score - 10, 0)
                        detail += f"; next activity OVERDUE {overdue}d"
                    else:
                        detail += f"; next activity overdue {overdue}d"

        return score, detail

    def _score_industry_win_rate(self, org_name, lead_source):
        """Historical win rate for similar deals (by lead source as proxy)."""
        # Use win/loss patterns if available
        patterns = self.patterns
        if not patterns:
            return 50, "no pattern data"

        correlations = patterns.get("correlations", {})

        # Use lead source as industry/segment proxy
        by_source = {}
        for a in self.analyses:
            src = a.get("lead_source", "Unknown")
            by_source.setdefault(src, {"won": 0, "lost": 0})
            if a.get("outcome") == "WON":
                by_source[src]["won"] += 1
            else:
                by_source[src]["lost"] += 1

        src_data = by_source.get(lead_source, {})
        total = src_data.get("won", 0) + src_data.get("lost", 0)

        if total >= 3:
            win_rate = src_data["won"] / total * 100
            score = clamp(win_rate, 5, 95)
            detail = f"{lead_source} source: {win_rate:.0f}% win rate ({total} deals)"
        elif total > 0:
            win_rate = src_data.get("won", 0) / total * 100
            score = clamp(win_rate * 0.7 + 15, 5, 95)  # discount small sample
            detail = f"{lead_source} source: {win_rate:.0f}% ({total} deals, small sample)"
        else:
            overall = patterns.get("overall_win_rate", 50)
            score = clamp(overall, 5, 95)
            detail = f"no {lead_source} data, using overall {overall:.0f}% rate"

        return round(score), detail

    def _score_stage_progression(self, stage_order, days_in_pipeline, days_in_stage):
        """How smoothly has the deal progressed through stages?"""
        if days_in_pipeline <= 0:
            return 50, "new deal"

        # Expected: deal should advance roughly 1 stage per 10-14 days
        expected_stages = max(days_in_pipeline / 12, 1)
        progression_ratio = stage_order / expected_stages

        if progression_ratio >= 1.5:
            score = 90
            detail = f"stage {stage_order} in {days_in_pipeline}d — fast progression"
        elif progression_ratio >= 1.0:
            score = 70
            detail = f"stage {stage_order} in {days_in_pipeline}d — on pace"
        elif progression_ratio >= 0.7:
            score = 50
            detail = f"stage {stage_order} in {days_in_pipeline}d — slightly slow"
        elif progression_ratio >= 0.4:
            score = 30
            detail = f"stage {stage_order} in {days_in_pipeline}d — behind schedule"
        else:
            score = 10
            detail = f"stage {stage_order} in {days_in_pipeline}d — severely delayed"

        # Penalty for sitting in current stage too long relative to pipeline age
        if days_in_pipeline > 0:
            stage_pct = days_in_stage / days_in_pipeline
            if stage_pct > 0.7 and days_in_stage > 14:
                score = max(score - 15, 5)
                detail += f"; {stage_pct:.0%} of time in current stage"

        return score, detail


# ── RISK DETECTOR ────────────────────────────────────

class RiskDetector:
    """Identify deals at risk and generate early warning signals."""

    RISK_RULES = [
        {
            "id": "velocity_drop",
            "name": "Velocity Drop",
            "check": "_check_velocity_drop",
            "action": "Re-engage immediately — send a value-add email or call to restart momentum",
        },
        {
            "id": "activity_gap",
            "name": "Activity Gap",
            "check": "_check_activity_gap",
            "action": "Schedule a touchpoint ASAP — the deal is going cold",
        },
        {
            "id": "no_next_activity",
            "name": "No Next Activity",
            "check": "_check_no_next_activity",
            "action": "Book a follow-up call or send a check-in email today",
        },
        {
            "id": "single_threaded",
            "name": "Single-Threaded",
            "check": "_check_single_threaded",
            "action": "Identify and engage a second stakeholder to reduce champion risk",
        },
        {
            "id": "stale_stage",
            "name": "Stale Stage",
            "check": "_check_stale_stage",
            "action": "Push for stage advancement — ask about blockers or offer a concession",
        },
        {
            "id": "overdue_activities",
            "name": "Overdue Activities",
            "check": "_check_overdue_activities",
            "action": "Complete overdue activities immediately — they signal lack of attention",
        },
        {
            "id": "low_engagement",
            "name": "Low Engagement",
            "check": "_check_low_engagement",
            "action": "Increase touchpoint frequency — aim for 2+ per week until deal warms up",
        },
        {
            "id": "zombie_deal",
            "name": "Zombie Deal",
            "check": "_check_zombie_deal",
            "action": "Qualify or kill — send a breakup email to force a response",
        },
    ]

    def __init__(self, predictions):
        self.predictions = {str(p["deal_id"]): p for p in predictions}

    def detect_risks(self):
        """Scan all predictions and return risk assessments."""
        risks = []
        for deal_id, pred in self.predictions.items():
            deal_risks = self._assess_deal(pred)
            if deal_risks:
                severity = self._overall_severity(deal_risks)
                risks.append({
                    "deal_id": pred["deal_id"],
                    "title": pred["title"],
                    "org": pred["org"],
                    "owner": pred["owner"],
                    "stage": pred["stage"],
                    "probability": pred["probability"],
                    "value": pred["value"],
                    "severity": severity,
                    "risk_count": len(deal_risks),
                    "risks": deal_risks,
                })

        risks.sort(key=lambda x: (
            {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(x["severity"], 4),
            -x.get("value", 0),
        ))
        return risks

    def _assess_deal(self, pred):
        """Run all risk rules against a deal prediction."""
        deal_risks = []
        for rule in self.RISK_RULES:
            check_method = getattr(self, rule["check"])
            result = check_method(pred)
            if result:
                deal_risks.append({
                    "risk_id": rule["id"],
                    "name": rule["name"],
                    "severity": result["severity"],
                    "signal": result["signal"],
                    "action": rule["action"],
                })
        return deal_risks

    def _overall_severity(self, risks):
        severity_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        worst = min(severity_order.get(r["severity"], 4) for r in risks)
        return {0: "critical", 1: "high", 2: "medium", 3: "low"}.get(worst, "low")

    def _check_velocity_drop(self, pred):
        vel = pred["factors"].get("stage_velocity", {})
        if vel.get("score", 50) <= 15:
            return {"severity": "high", "signal": f"Deal stuck in stage — {vel.get('detail', '')}"}
        if vel.get("score", 50) <= 30:
            return {"severity": "medium", "signal": f"Velocity slowing — {vel.get('detail', '')}"}
        return None

    def _check_activity_gap(self, pred):
        days = pred.get("days_since_activity", 0)
        if days >= 30:
            return {"severity": "critical", "signal": f"No activity for {days} days"}
        if days >= 14:
            return {"severity": "high", "signal": f"No activity for {days} days"}
        if days >= 7:
            return {"severity": "medium", "signal": f"No activity for {days} days"}
        return None

    def _check_no_next_activity(self, pred):
        recency = pred["factors"].get("activity_recency", {})
        detail = recency.get("detail", "")
        if "no activity recorded" in detail:
            return {"severity": "high", "signal": "No activities recorded at all"}
        if "next scheduled" not in detail and "OVERDUE" not in detail and "overdue" not in detail:
            if pred.get("days_since_activity", 0) >= 3:
                return {"severity": "medium", "signal": "No next activity scheduled"}
        return None

    def _check_single_threaded(self, pred):
        champ = pred["factors"].get("champion", {})
        participants = pred.get("participants", 0)
        if participants <= 1 and pred.get("stage_order", 0) >= 3:
            return {"severity": "medium", "signal": f"Only {participants} stakeholder(s) at {pred['stage']} stage"}
        return None

    def _check_stale_stage(self, pred):
        days = pred.get("days_in_stage", 0)
        if days >= 45:
            return {"severity": "critical", "signal": f"{days} days in {pred['stage']} — deal is dying"}
        if days >= 30:
            return {"severity": "high", "signal": f"{days} days in {pred['stage']} — needs urgent push"}
        if days >= 21:
            return {"severity": "medium", "signal": f"{days} days in {pred['stage']} — getting stale"}
        return None

    def _check_overdue_activities(self, pred):
        detail = pred["factors"].get("activity_recency", {}).get("detail", "")
        if "OVERDUE" in detail:
            return {"severity": "high", "signal": detail.split(";")[-1].strip() if ";" in detail else "Activity overdue"}
        if "overdue" in detail:
            return {"severity": "medium", "signal": detail.split(";")[-1].strip() if ";" in detail else "Activity overdue"}
        return None

    def _check_low_engagement(self, pred):
        eng = pred["factors"].get("engagement", {})
        if eng.get("score", 50) <= 20 and pred.get("days_in_pipeline", 0) >= 14:
            return {"severity": "high", "signal": f"Low engagement — {eng.get('detail', '')}"}
        if eng.get("score", 50) <= 40 and pred.get("days_in_pipeline", 0) >= 21:
            return {"severity": "medium", "signal": f"Below-average engagement — {eng.get('detail', '')}"}
        return None

    def _check_zombie_deal(self, pred):
        if pred.get("days_since_activity", 0) >= 30 and pred.get("days_in_stage", 0) >= 30:
            return {
                "severity": "critical",
                "signal": f"No activity for {pred['days_since_activity']}d, stuck in {pred['stage']} for {pred['days_in_stage']}d",
            }
        return None


# ── PIPELINE FORECAST ────────────────────────────────

class PipelineForecast:
    """Weighted pipeline value and revenue forecasting."""

    def __init__(self, predictions, velocity_data):
        self.predictions = predictions
        self.velocity = velocity_data
        self.stage_stats = velocity_data.get("stage_stats", {})

    def forecast(self):
        """Generate full pipeline forecast."""
        deals = [p for p in self.predictions if p.get("value", 0) > 0]
        all_deals = self.predictions

        # Weighted pipeline value
        weighted_total = sum(p["value"] * p["probability"] / 100 for p in deals)
        raw_total = sum(p["value"] for p in deals)

        # Expected close dates
        deal_forecasts = []
        for pred in all_deals:
            expected_close = self._estimate_close_date(pred)
            deal_forecasts.append({
                "deal_id": pred["deal_id"],
                "title": pred["title"],
                "org": pred["org"],
                "value": pred["value"],
                "probability": pred["probability"],
                "weighted_value": round(pred["value"] * pred["probability"] / 100) if pred["value"] else 0,
                "expected_close": expected_close,
                "stage": pred["stage"],
            })

        deal_forecasts.sort(key=lambda x: x.get("expected_close") or "9999-12-31")

        # Monthly forecast
        monthly = self._monthly_forecast(deal_forecasts)

        # Quarterly forecast
        quarterly = self._quarterly_forecast(deal_forecasts)

        # Scenarios
        scenarios = self._scenario_forecast(deal_forecasts)

        return {
            "generated_at": NOW.isoformat(),
            "pipeline_summary": {
                "total_deals": len(all_deals),
                "deals_with_value": len(deals),
                "raw_pipeline_value": raw_total,
                "weighted_pipeline_value": round(weighted_total),
                "avg_probability": round(statistics.mean([p["probability"] for p in all_deals]), 1) if all_deals else 0,
                "currency": "CZK",
            },
            "deal_forecasts": deal_forecasts,
            "monthly": monthly,
            "quarterly": quarterly,
            "scenarios": scenarios,
        }

    def _estimate_close_date(self, pred):
        """Estimate when a deal will close based on remaining stages and velocity."""
        stage_order = pred.get("stage_order", 1)
        remaining_stages = 8 - stage_order  # 8 = Invoice sent

        if remaining_stages <= 0:
            return TODAY.isoformat()

        # Average days per remaining stage from velocity data
        total_remaining_days = 0
        for sid, (_, order) in SALES_STAGES.items():
            if order > stage_order:
                stats = self.stage_stats.get(str(sid), {})
                avg_days = stats.get("avg", 14)  # default 14 days per stage
                total_remaining_days += avg_days

        # Add remaining time in current stage (estimate: half the average)
        current_stats = self.stage_stats.get(str(self._stage_id_from_order(stage_order)), {})
        current_avg = current_stats.get("avg", 14)
        days_in = pred.get("days_in_stage", 0)
        remaining_current = max(current_avg - days_in, 0)

        total_remaining_days += remaining_current
        close_date = TODAY + timedelta(days=int(total_remaining_days))
        return close_date.isoformat()

    def _stage_id_from_order(self, order):
        for sid, (_, o) in SALES_STAGES.items():
            if o == order:
                return sid
        return 7

    def _monthly_forecast(self, forecasts):
        """Group expected revenue by month."""
        by_month = defaultdict(lambda: {"expected": 0, "weighted": 0, "deal_count": 0})
        for f in forecasts:
            close = f.get("expected_close") or ""
            if not close:
                continue
            month_key = close[:7]  # YYYY-MM
            by_month[month_key]["expected"] += f.get("value", 0)
            by_month[month_key]["weighted"] += f.get("weighted_value", 0)
            by_month[month_key]["deal_count"] += 1

        return {k: v for k, v in sorted(by_month.items())[:6]}  # Next 6 months

    def _quarterly_forecast(self, forecasts):
        """Group expected revenue by quarter."""
        by_quarter = defaultdict(lambda: {"expected": 0, "weighted": 0, "deal_count": 0})
        for f in forecasts:
            close = f.get("expected_close") or ""
            if not close:
                continue
            try:
                dt = datetime.strptime(close[:10], "%Y-%m-%d")
                q = (dt.month - 1) // 3 + 1
                quarter_key = f"{dt.year}-Q{q}"
                by_quarter[quarter_key]["expected"] += f.get("value", 0)
                by_quarter[quarter_key]["weighted"] += f.get("weighted_value", 0)
                by_quarter[quarter_key]["deal_count"] += 1
            except (ValueError, TypeError):
                continue

        return {k: v for k, v in sorted(by_quarter.items())[:4]}  # Next 4 quarters

    def _scenario_forecast(self, forecasts):
        """Best-case / expected / worst-case scenarios."""
        if not forecasts:
            return {"best": 0, "expected": 0, "worst": 0}

        best = 0
        expected = 0
        worst = 0

        for f in forecasts:
            val = f.get("value", 0)
            prob = f.get("probability", 0) / 100

            # Best case: all deals above 30% probability close
            if prob >= 0.3:
                best += val

            # Expected: weighted value
            expected += val * prob

            # Worst case: only deals above 70% probability close
            if prob >= 0.7:
                worst += val

        return {
            "best_case": round(best),
            "expected": round(expected),
            "worst_case": round(worst),
            "currency": "CZK",
            "explanation": {
                "best": "All deals with >30% probability close",
                "expected": "Sum of (deal_value x probability)",
                "worst": "Only deals with >70% probability close",
            },
        }


# ── DEAL COACH ───────────────────────────────────────

class DealCoach:
    """Per-deal recommendations to improve probability."""

    def __init__(self, predictor: SuccessPredictor):
        self.predictor = predictor
        self.analyses = predictor.analyses

    def coach(self, prediction):
        """Generate coaching advice for a deal."""
        if not prediction:
            return None

        recommendations = []
        similar_won = self._find_similar_won_deals(prediction)
        next_actions = []

        # Analyze each factor and generate recs
        for factor_name, factor_data in prediction.get("factors", {}).items():
            score = factor_data.get("score", 50)
            detail = factor_data.get("detail", "")

            if score < 40:
                rec = self._recommendation_for_factor(factor_name, score, detail, prediction)
                if rec:
                    recommendations.append(rec)

        # Stage-specific advice
        stage_recs = self._stage_advice(prediction)
        recommendations.extend(stage_recs)

        # Next actions with timing
        next_actions = self._suggest_next_actions(prediction, recommendations)

        # What won deals did differently
        won_diff = self._what_won_deals_did(prediction, similar_won)

        coaching = {
            "deal_id": prediction["deal_id"],
            "title": prediction["title"],
            "org": prediction["org"],
            "current_probability": prediction["probability"],
            "stage": prediction["stage"],
            "recommendations": recommendations,
            "what_won_deals_did": won_diff,
            "next_actions": next_actions,
            "similar_won_deals": [
                {"title": d.get("title", ""), "org": d.get("org", ""), "value": d.get("value", 0), "total_days": d.get("total_days", 0)}
                for d in similar_won[:5]
            ],
            "coached_at": NOW.isoformat(),
        }

        return coaching

    def _recommendation_for_factor(self, factor, score, detail, pred):
        recs = {
            "stage_velocity": {
                "area": "Speed",
                "issue": f"Deal is moving slower than average ({detail})",
                "fix": "Identify the specific blocker — is it decision authority, budget approval, or internal politics? Address directly.",
                "impact": "high",
            },
            "engagement": {
                "area": "Engagement",
                "issue": f"Touchpoint density is low ({detail})",
                "fix": "Increase contact frequency: schedule a call, send a case study, or share relevant industry news.",
                "impact": "high",
            },
            "deal_size_fit": {
                "area": "Deal Size",
                "issue": f"Deal value doesn't fit typical won deal profile ({detail})",
                "fix": "Review pricing — if too high, consider phased approach. If too low, explore upsell opportunities.",
                "impact": "medium",
            },
            "champion": {
                "area": "Champion / Contacts",
                "issue": f"Weak champion presence ({detail})",
                "fix": "Identify an internal champion. Multi-thread by finding 2-3 stakeholders. Get phone and email for key contact.",
                "impact": "high",
            },
            "activity_recency": {
                "area": "Recency",
                "issue": f"Deal going cold ({detail})",
                "fix": "Take action today — call or email the primary contact. No next activity = no pipeline.",
                "impact": "critical",
            },
            "industry_win_rate": {
                "area": "Segment Fit",
                "issue": f"Lower historical win rate in this segment ({detail})",
                "fix": "Study what worked in won deals from this segment. Adjust pitch to address segment-specific objections.",
                "impact": "medium",
            },
            "stage_progression": {
                "area": "Progression",
                "issue": f"Stage advancement is behind schedule ({detail})",
                "fix": "Create urgency — use a deadline, a limited offer, or competitive pressure to push for next stage.",
                "impact": "high",
            },
        }
        return recs.get(factor)

    def _stage_advice(self, pred):
        """Stage-specific tactical advice."""
        advice = []
        stage = pred.get("stage", "")

        if stage == "Interested/Qualified":
            if pred.get("days_in_stage", 0) > 7:
                advice.append({
                    "area": "Stage: Qualification",
                    "issue": "Still in qualification after 7+ days",
                    "fix": "Book a discovery call. Use SPIN questions to uncover pain. If no pain, disqualify early.",
                    "impact": "high",
                })
        elif stage == "Demo Scheduled":
            advice.append({
                "area": "Stage: Demo Prep",
                "issue": "Demo preparation",
                "fix": "Customize demo to their industry/pain. Confirm attendees. Send prep questions 24h before.",
                "impact": "medium",
            })
        elif stage == "Proposal made":
            if pred.get("days_in_stage", 0) > 10:
                advice.append({
                    "area": "Stage: Proposal Follow-up",
                    "issue": f"Proposal outstanding for {pred.get('days_in_stage', 0)} days",
                    "fix": "Offer to walk through proposal on a call. Address objections proactively. Set a decision deadline.",
                    "impact": "high",
                })
        elif stage == "Negotiation":
            advice.append({
                "area": "Stage: Negotiation",
                "issue": "In negotiation phase",
                "fix": "Focus on value, not price. Use package/bundle options. Set clear next steps with dates.",
                "impact": "medium",
            })
        elif stage == "Pilot":
            advice.append({
                "area": "Stage: Pilot Success",
                "issue": "Active pilot",
                "fix": "Define success criteria upfront. Schedule weekly check-ins. Collect data for ROI story.",
                "impact": "medium",
            })

        return advice

    def _find_similar_won_deals(self, pred):
        """Find won deals with similar characteristics."""
        won = [a for a in self.analyses if a.get("outcome") == "WON"]
        if not won:
            return []

        pred_value = pred.get("value", 0)
        pred_source = pred.get("lead_source", "")

        scored = []
        for deal in won:
            sim = 0
            # Same lead source = +3
            if deal.get("lead_source", "") == pred_source:
                sim += 3
            # Similar value range = +2
            deal_val = deal.get("value", 0)
            if pred_value > 0 and deal_val > 0:
                ratio = min(pred_value, deal_val) / max(pred_value, deal_val)
                if ratio >= 0.5:
                    sim += 2
            # Similar touchpoints = +1
            pred_tp = pred.get("done_activities", 0) + pred.get("email_count", 0)
            deal_tp = deal.get("touchpoints", {}).get("done_activities", 0) + deal.get("touchpoints", {}).get("emails", 0)
            if pred_tp > 0 and deal_tp > 0:
                tp_ratio = min(pred_tp, deal_tp) / max(pred_tp, deal_tp)
                if tp_ratio >= 0.5:
                    sim += 1
            scored.append((sim, deal))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [deal for _, deal in scored[:5]]

    def _what_won_deals_did(self, pred, similar_won):
        """Compare current deal to what similar won deals did differently."""
        if not similar_won:
            return ["No similar won deals found for comparison"]

        insights = []
        pred_tp = pred.get("done_activities", 0) + pred.get("email_count", 0)
        pred_days = pred.get("days_in_pipeline", 0)

        won_tps = [d.get("touchpoints", {}).get("done_activities", 0) + d.get("touchpoints", {}).get("emails", 0) for d in similar_won]
        won_days = [d.get("total_days", 0) for d in similar_won if d.get("total_days", 0) > 0]

        if won_tps:
            avg_won_tp = statistics.mean(won_tps)
            if pred_tp < avg_won_tp * 0.7:
                insights.append(f"Won deals averaged {avg_won_tp:.0f} touchpoints — you have {pred_tp}. Increase engagement.")
            elif pred_tp > avg_won_tp * 1.3:
                insights.append(f"You have more touchpoints ({pred_tp}) than won deals ({avg_won_tp:.0f}). Focus on quality over quantity.")

        if won_days:
            avg_won_days = statistics.mean(won_days)
            if pred_days > avg_won_days * 1.5:
                insights.append(f"Won deals closed in ~{avg_won_days:.0f} days. This deal is at {pred_days}d — push for faster resolution.")

        # Check what worked in won deals
        for deal in similar_won[:3]:
            worked = deal.get("what_worked", [])
            for item in worked[:2]:
                if item not in insights:
                    insights.append(f"Won deal '{deal.get('title', '')[:30]}': {item}")

        if not insights:
            insights.append("Current deal metrics align with won deals — stay the course")

        return insights

    def _suggest_next_actions(self, pred, recommendations):
        """Generate prioritized next actions with timing."""
        actions = []

        # Critical: activity recency
        if pred.get("days_since_activity", 0) >= 7:
            actions.append({
                "action": "Call or email primary contact",
                "timing": "TODAY",
                "priority": "critical",
                "reason": f"No activity for {pred.get('days_since_activity', 0)} days",
            })

        # High: engagement
        eng_score = pred["factors"].get("engagement", {}).get("score", 50)
        if eng_score < 40:
            actions.append({
                "action": "Send value-add content (case study, ROI calculator, or industry report)",
                "timing": "Within 2 days",
                "priority": "high",
                "reason": "Low engagement score",
            })

        # High: champion
        champ_score = pred["factors"].get("champion", {}).get("score", 50)
        if champ_score < 40:
            actions.append({
                "action": "Identify and connect with a second stakeholder / decision maker",
                "timing": "Within 1 week",
                "priority": "high",
                "reason": "Weak champion / single-threaded deal",
            })

        # Medium: stage velocity
        vel_score = pred["factors"].get("stage_velocity", {}).get("score", 50)
        if vel_score < 30:
            actions.append({
                "action": "Ask directly about blockers / timeline for decision",
                "timing": "Next call",
                "priority": "high",
                "reason": "Deal velocity is dropping",
            })

        # Stage-specific
        stage = pred.get("stage", "")
        stage_order = pred.get("stage_order", 0)

        if stage == "Demo Scheduled" and pred.get("days_in_stage", 0) > 14:
            actions.append({
                "action": "Confirm or reschedule the demo — send 2 alternate time slots",
                "timing": "TODAY",
                "priority": "high",
                "reason": "Demo has been pending 14+ days",
            })

        if stage_order >= 4 and pred.get("participants", 0) <= 1:
            actions.append({
                "action": "Ask champion to loop in the budget holder / decision maker for next meeting",
                "timing": "Within 3 days",
                "priority": "medium",
                "reason": "Need multi-threading at proposal+ stages",
            })

        if not actions:
            actions.append({
                "action": "Maintain current cadence — deal is tracking well",
                "timing": "Per schedule",
                "priority": "low",
                "reason": "All metrics within healthy ranges",
            })

        return actions


# ── CLI OUTPUT ───────────────────────────────────────

def print_predictions(predictions):
    print("=" * 90)
    print("  DEAL SUCCESS PREDICTIONS")
    print(f"  {NOW.strftime('%Y-%m-%d %H:%M')} | {len(predictions)} deals")
    print("=" * 90)

    if not predictions:
        print("\n  No deals to predict.")
        return

    # Summary stats
    probs = [p["probability"] for p in predictions]
    high = sum(1 for p in probs if p >= 70)
    medium = sum(1 for p in probs if 40 <= p < 70)
    low = sum(1 for p in probs if p < 40)

    print(f"\n  HIGH (70%+): {high} | MEDIUM (40-69%): {medium} | LOW (<40%): {low}")
    print(f"  Avg probability: {statistics.mean(probs):.1f}%")

    # Table
    print(f"\n  {'P%':>4} {'Deal':<28} {'Org':<22} {'Stage':<18} {'Value':>10} {'Owner':<8}")
    print("  " + "-" * 96)

    for p in predictions[:40]:
        prob = p["probability"]
        if prob >= 70:
            icon = "##"
        elif prob >= 40:
            icon = "--"
        else:
            icon = ".."

        val = f"{p['value']:,.0f}" if p["value"] else "-"
        print(
            f"  {prob:>3.0f}% {p['title'][:27]:<28} {p['org'][:21]:<22} "
            f"{p['stage'][:17]:<18} {val:>10} {p['owner'][:7]:<8}"
        )

    if len(predictions) > 40:
        print(f"  ... +{len(predictions) - 40} more deals")


def print_single_prediction(pred):
    print("=" * 70)
    print(f"  PREDICTION: {pred['title']}")
    print(f"  Org: {pred['org']} | Owner: {pred['owner']}")
    print("=" * 70)

    print(f"\n  PROBABILITY: {pred['probability']:.0f}%")
    print(f"  Base (stage): {pred['base_probability']}% | Source bonus: {pred['source_bonus']:+d}%")
    print(f"  Stage: {pred['stage']} | Days in stage: {pred['days_in_stage']}")
    print(f"  Pipeline age: {pred['days_in_pipeline']}d | Last activity: {pred['days_since_activity']}d ago")
    print(f"  Lead source: {pred['lead_source']}")

    if pred["value"]:
        print(f"  Value: {pred['value']:,.0f} {pred['currency']}")
        weighted = round(pred['value'] * pred['probability'] / 100)
        print(f"  Weighted value: {weighted:,.0f} {pred['currency']}")

    print(f"\n  FACTOR BREAKDOWN")
    print("  " + "-" * 66)
    print(f"  {'Factor':<22} {'Score':>6} {'Weight':>7} {'Contribution':>13}  Detail")
    print("  " + "-" * 66)

    for name, f in pred["factors"].items():
        contrib = f["score"] * f["weight"]
        print(f"  {name:<22} {f['score']:>5.0f} {f['weight']:>6.0%} {contrib:>12.1f}  {f['detail'][:40]}")


def print_risks(risks):
    print("=" * 90)
    print("  AT-RISK DEALS")
    print(f"  {NOW.strftime('%Y-%m-%d %H:%M')} | {len(risks)} deals flagged")
    print("=" * 90)

    if not risks:
        print("\n  No at-risk deals detected.")
        return

    sev_count = defaultdict(int)
    for r in risks:
        sev_count[r["severity"]] += 1
    print(f"\n  CRITICAL: {sev_count['critical']} | HIGH: {sev_count['high']} | MEDIUM: {sev_count['medium']} | LOW: {sev_count['low']}")

    for r in risks:
        sev_tag = r["severity"].upper()
        val = f"{r['value']:,.0f} CZK" if r["value"] else "-"
        print(f"\n  [{sev_tag}] {r['title']} ({r['org']}) — {r['probability']:.0f}% | {val}")
        print(f"         Stage: {r['stage']} | Owner: {r['owner']}")
        for risk in r["risks"]:
            print(f"         - [{risk['severity'].upper()}] {risk['name']}: {risk['signal']}")
            print(f"           Action: {risk['action']}")


def print_forecast(forecast):
    print("=" * 90)
    print("  PIPELINE REVENUE FORECAST")
    print(f"  {NOW.strftime('%Y-%m-%d %H:%M')}")
    print("=" * 90)

    summary = forecast["pipeline_summary"]
    print(f"\n  PIPELINE SUMMARY")
    print(f"  Total deals: {summary['total_deals']} ({summary['deals_with_value']} with value)")
    print(f"  Raw pipeline: {summary['raw_pipeline_value']:,.0f} {summary['currency']}")
    print(f"  Weighted pipeline: {summary['weighted_pipeline_value']:,.0f} {summary['currency']}")
    print(f"  Avg probability: {summary['avg_probability']:.1f}%")

    # Scenarios
    scenarios = forecast["scenarios"]
    print(f"\n  REVENUE SCENARIOS ({scenarios.get('currency', 'CZK')})")
    print("  " + "-" * 50)
    print(f"  Best case (>30% prob):    {scenarios['best_case']:>12,.0f}")
    print(f"  Expected (weighted):      {scenarios['expected']:>12,.0f}")
    print(f"  Worst case (>70% prob):   {scenarios['worst_case']:>12,.0f}")

    # Monthly
    monthly = forecast.get("monthly", {})
    if monthly:
        print(f"\n  MONTHLY FORECAST")
        print("  " + "-" * 50)
        print(f"  {'Month':<12} {'Expected':>12} {'Weighted':>12} {'Deals':>6}")
        print("  " + "-" * 50)
        for month, data in monthly.items():
            print(f"  {month:<12} {data['expected']:>12,.0f} {data['weighted']:>12,.0f} {data['deal_count']:>6}")

    # Quarterly
    quarterly = forecast.get("quarterly", {})
    if quarterly:
        print(f"\n  QUARTERLY FORECAST")
        print("  " + "-" * 50)
        print(f"  {'Quarter':<12} {'Expected':>12} {'Weighted':>12} {'Deals':>6}")
        print("  " + "-" * 50)
        for q, data in quarterly.items():
            print(f"  {q:<12} {data['expected']:>12,.0f} {data['weighted']:>12,.0f} {data['deal_count']:>6}")


def print_coaching(coaching):
    print("=" * 70)
    print(f"  DEAL COACHING: {coaching['title']}")
    print(f"  Org: {coaching['org']} | Probability: {coaching['current_probability']:.0f}%")
    print("=" * 70)

    # Recommendations
    recs = coaching.get("recommendations", [])
    if recs:
        print(f"\n  RECOMMENDATIONS ({len(recs)})")
        print("  " + "-" * 66)
        for r in recs:
            impact = r.get("impact", "medium").upper()
            print(f"\n  [{impact}] {r.get('area', '')}")
            print(f"  Issue: {r.get('issue', '')}")
            print(f"  Fix: {r.get('fix', '')}")

    # What won deals did differently
    won_diff = coaching.get("what_won_deals_did", [])
    if won_diff:
        print(f"\n  WHAT SIMILAR WON DEALS DID DIFFERENTLY")
        print("  " + "-" * 66)
        for insight in won_diff:
            print(f"  - {insight}")

    # Next actions
    actions = coaching.get("next_actions", [])
    if actions:
        print(f"\n  NEXT ACTIONS")
        print("  " + "-" * 66)
        for a in actions:
            prio = a.get("priority", "medium").upper()
            print(f"  [{prio}] {a['action']}")
            print(f"         When: {a['timing']} | Why: {a['reason']}")

    # Similar won deals
    similar = coaching.get("similar_won_deals", [])
    if similar:
        print(f"\n  SIMILAR WON DEALS")
        print("  " + "-" * 66)
        for d in similar:
            val = f"{d['value']:,.0f} CZK" if d.get("value") else "-"
            print(f"  - {d['title'][:40]} ({d.get('org', '')[:20]}) | {val} | {d.get('total_days', '?')}d cycle")


# ── CLI ──────────────────────────────────────────────

def main():
    env = load_env(ENV_PATH)
    base = env.get("PIPEDRIVE_BASE_URL", "").rstrip("/")
    token = env.get("PIPEDRIVE_API_TOKEN", "")

    if not base or not token:
        print("ERROR: Missing PIPEDRIVE_BASE_URL or PIPEDRIVE_API_TOKEN in .secrets/pipedrive.env")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: success_predictor.py [predict|predict <deal_id>|risks|forecast|coach <deal_id>]")
        sys.exit(0)

    cmd = sys.argv[1]

    predictor = SuccessPredictor(base, token)

    if cmd == "predict":
        if len(sys.argv) >= 3:
            deal_id = sys.argv[2]
            print(f"Predicting deal {deal_id}...")
            pred = predictor.predict_single(deal_id)
            if pred:
                print_single_prediction(pred)
            else:
                print(f"Could not predict deal {deal_id}")
        else:
            print("Predicting all active deals...")
            predictions = predictor.predict_all()
            print_predictions(predictions)
            print(f"\nPredictions saved to {PREDICTIONS_FILE}")

    elif cmd == "risks":
        print("Analyzing pipeline risks...")
        predictions = predictor.predict_all()
        detector = RiskDetector(predictions)
        risks = detector.detect_risks()
        print_risks(risks)

    elif cmd == "forecast":
        print("Generating revenue forecast...")
        predictions = predictor.predict_all()
        velocity = load_velocity_data()
        forecaster = PipelineForecast(predictions, velocity)
        forecast = forecaster.forecast()
        print_forecast(forecast)

    elif cmd == "coach":
        if len(sys.argv) < 3:
            print("Usage: success_predictor.py coach <deal_id>")
            sys.exit(1)
        deal_id = sys.argv[2]
        print(f"Coaching deal {deal_id}...")
        pred = predictor.predict_single(deal_id)
        if not pred:
            print(f"Could not load deal {deal_id}")
            sys.exit(1)
        coach = DealCoach(predictor)
        coaching = coach.coach(pred)
        print_coaching(coaching)

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: success_predictor.py [predict|predict <deal_id>|risks|forecast|coach <deal_id>]")
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
