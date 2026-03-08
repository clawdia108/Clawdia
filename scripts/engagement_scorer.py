#!/usr/bin/env python3
"""
Contact Engagement Scoring System
====================================
Real-time engagement scoring for Pipedrive contacts. Weighted multi-factor
model that scores contact engagement 0-100, detects trends, maps company
relationships, and flags churn risk.

Integrates with:
  - Pipedrive API (contacts, activities, deals, organizations)
  - knowledge_graph.py (contact enrichment)
  - deal_velocity.py (deal progression data)
  - Agent Bus (engagement.cold_contact, engagement.trend_change)

Usage:
  python3 scripts/engagement_scorer.py score              # Score all contacts
  python3 scripts/engagement_scorer.py score <contact_id> # Single contact
  python3 scripts/engagement_scorer.py cold               # Show cold contacts
  python3 scripts/engagement_scorer.py heatmap <company>  # Company engagement map
  python3 scripts/engagement_scorer.py trends             # Engagement trends
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
SCORES_FILE = WORKSPACE / "knowledge" / "engagement-scores.json"
VELOCITY_FILE = WORKSPACE / "pipedrive" / "deal_velocity.json"
GRAPH_FILE = WORKSPACE / "knowledge" / "graph.json"
LOG_FILE = WORKSPACE / "logs" / "engagement-scorer.log"

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

# Engagement factor weights (sum = 1.0)
WEIGHTS = {
    "activity_frequency": 0.25,
    "response_speed":     0.20,
    "meeting_willingness": 0.20,
    "deal_progression":   0.15,
    "multi_threading":    0.10,
    "recency":            0.10,
}

# Trend detection thresholds
TREND_WARMING_DELTA = 10    # score increase >= this over 2 weeks
TREND_COOLING_DELTA = -10   # score decrease <= this over 2 weeks
GHOST_DAYS = 30             # no activity in this many days = ghost


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


def elog(msg, level="INFO"):
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


def parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


# ── DATA LOADERS ─────────────────────────────────────

def load_velocity_data():
    if VELOCITY_FILE.exists():
        try:
            return json.loads(VELOCITY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"deals": {}, "stage_stats": {}}


def load_graph_data():
    if GRAPH_FILE.exists():
        try:
            return json.loads(GRAPH_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"nodes": {}, "edges": []}


def load_existing_scores():
    if SCORES_FILE.exists():
        try:
            return json.loads(SCORES_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"contacts": {}, "companies": {}, "history": [], "generated_at": None}


# ── ENGAGEMENT SCORER ────────────────────────────────

class EngagementScorer:
    """Weighted multi-factor engagement scoring for contacts (0-100)."""

    def __init__(self, base_url, api_token):
        self.base = base_url
        self.token = api_token
        self.velocity = load_velocity_data()
        self.graph = load_graph_data()
        self.existing = load_existing_scores()
        self._activities_cache = {}
        self._org_contacts_cache = {}
        self._all_activities = None
        self._avg_activities_30d = None

    # ── MAIN SCORING ─────────────────────────────────

    def score_all(self):
        """Score all contacts that have associated deals in the sales pipeline."""
        elog("Fetching contacts with open deals...")
        deals = paged_get(self.base, self.token, "/api/v1/deals", {"status": "open"})
        sales_deals = [d for d in deals if d.get("stage_id") in SALES_STAGES]
        elog(f"Found {len(sales_deals)} open sales deals")

        contact_ids = set()
        contact_deal_map = defaultdict(list)
        for deal in sales_deals:
            person = deal.get("person_id")
            if isinstance(person, dict):
                pid = person.get("value") or person.get("id")
            elif isinstance(person, int):
                pid = person
            else:
                continue
            if pid:
                contact_ids.add(pid)
                contact_deal_map[pid].append(deal)

        elog(f"Unique contacts to score: {len(contact_ids)}")

        self._preload_activities(contact_ids)

        scored = {}
        for cid in contact_ids:
            result = self._score_contact(cid, contact_deal_map.get(cid, []))
            if result:
                scored[str(cid)] = result

        self._save_scores(scored)
        return scored

    def score_single(self, contact_id):
        """Score a single contact by ID."""
        resp = api_request(self.base, self.token, "GET", f"/api/v1/persons/{contact_id}")
        if not resp or not resp.get("success") or not resp.get("data"):
            elog(f"Contact {contact_id} not found", "WARN")
            return None

        person = resp["data"]
        deals_resp = api_request(
            self.base, self.token, "GET",
            f"/api/v1/persons/{contact_id}/deals",
            params={"status": "open"}
        )
        deals = []
        if deals_resp and deals_resp.get("success") and deals_resp.get("data"):
            deals = [d for d in deals_resp["data"] if d.get("stage_id") in SALES_STAGES]

        self._preload_activities({contact_id})
        result = self._score_contact(contact_id, deals, person_data=person)
        if result:
            self._save_scores({str(contact_id): result}, append=True)
        return result

    def _preload_activities(self, contact_ids):
        """Batch-load activities for efficiency."""
        elog("Preloading activities...")
        cutoff = (TODAY - timedelta(days=90)).isoformat()
        all_activities = paged_get(
            self.base, self.token, "/api/v1/activities",
            {"done": "1", "start_date": cutoff}
        )
        elog(f"Loaded {len(all_activities)} activities from last 90 days")

        self._all_activities = all_activities

        for act in all_activities:
            person_id = act.get("person_id")
            if person_id:
                self._activities_cache.setdefault(person_id, []).append(act)

        total_30d = 0
        contacts_with_activity = 0
        cutoff_30 = (TODAY - timedelta(days=30)).isoformat()
        seen = set()
        for act in all_activities:
            pid = act.get("person_id")
            due = act.get("due_date") or act.get("add_time", "")
            if pid and due >= cutoff_30:
                total_30d += 1
                if pid not in seen:
                    contacts_with_activity += 1
                    seen.add(pid)

        if contacts_with_activity > 0:
            self._avg_activities_30d = total_30d / contacts_with_activity
        else:
            self._avg_activities_30d = 3.0

    def _score_contact(self, contact_id, deals, person_data=None):
        """Calculate engagement score for one contact."""
        if person_data is None:
            resp = api_request(self.base, self.token, "GET", f"/api/v1/persons/{contact_id}")
            if not resp or not resp.get("success") or not resp.get("data"):
                return None
            person_data = resp["data"]

        name = person_data.get("name") or "Unknown"
        org = person_data.get("org_id")
        org_name = ""
        org_id = None
        if isinstance(org, dict):
            org_name = org.get("name", "")
            org_id = org.get("value") or org.get("id")
        elif isinstance(org, int):
            org_id = org

        email_entries = person_data.get("email") or []
        phone_entries = person_data.get("phone") or []
        has_email = any(e.get("value") for e in email_entries if isinstance(e, dict))
        has_phone = any(p.get("value") for p in phone_entries if isinstance(p, dict))

        activities = self._activities_cache.get(contact_id, [])

        # Factor scores
        freq_score, freq_detail = self._score_activity_frequency(activities)
        resp_score, resp_detail = self._score_response_speed(activities, contact_id)
        meet_score, meet_detail = self._score_meeting_willingness(activities)
        deal_score, deal_detail = self._score_deal_progression(deals)
        multi_score, multi_detail = self._score_multi_threading(org_id, contact_id)
        recency_score, recency_detail = self._score_recency(activities)

        factors = {
            "activity_frequency": {
                "score": freq_score,
                "weight": WEIGHTS["activity_frequency"],
                "detail": freq_detail,
            },
            "response_speed": {
                "score": resp_score,
                "weight": WEIGHTS["response_speed"],
                "detail": resp_detail,
            },
            "meeting_willingness": {
                "score": meet_score,
                "weight": WEIGHTS["meeting_willingness"],
                "detail": meet_detail,
            },
            "deal_progression": {
                "score": deal_score,
                "weight": WEIGHTS["deal_progression"],
                "detail": deal_detail,
            },
            "multi_threading": {
                "score": multi_score,
                "weight": WEIGHTS["multi_threading"],
                "detail": multi_detail,
            },
            "recency": {
                "score": recency_score,
                "weight": WEIGHTS["recency"],
                "detail": recency_detail,
            },
        }

        engagement_score = round(
            clamp(sum(f["score"] * f["weight"] for f in factors.values())), 1
        )

        last_activity_date = self._last_activity_date(activities)
        days_since = days_between(last_activity_date) if last_activity_date else 999

        return {
            "contact_id": contact_id,
            "name": name,
            "org_name": org_name,
            "org_id": org_id,
            "engagement_score": engagement_score,
            "factors": factors,
            "has_email": has_email,
            "has_phone": has_phone,
            "total_activities_90d": len(activities),
            "days_since_last_activity": days_since,
            "last_activity_date": last_activity_date,
            "deal_count": len(deals),
            "scored_at": NOW.isoformat(),
        }

    # ── FACTOR SCORING ───────────────────────────────

    def _score_activity_frequency(self, activities):
        """25% — number of activities in last 30 days vs average."""
        cutoff_30 = (TODAY - timedelta(days=30)).isoformat()
        recent = [
            a for a in activities
            if (a.get("due_date") or a.get("add_time", "")) >= cutoff_30
        ]
        count_30d = len(recent)
        avg = self._avg_activities_30d or 3.0

        if avg <= 0:
            ratio = count_30d
        else:
            ratio = count_30d / avg

        if ratio >= 3.0:
            score = 100
            detail = f"{count_30d} activities in 30d ({ratio:.1f}x avg) — extremely active"
        elif ratio >= 2.0:
            score = 85
            detail = f"{count_30d} activities in 30d ({ratio:.1f}x avg) — very active"
        elif ratio >= 1.2:
            score = 70
            detail = f"{count_30d} activities in 30d ({ratio:.1f}x avg) — above average"
        elif ratio >= 0.8:
            score = 50
            detail = f"{count_30d} activities in 30d ({ratio:.1f}x avg) — average"
        elif ratio >= 0.4:
            score = 30
            detail = f"{count_30d} activities in 30d ({ratio:.1f}x avg) — below average"
        elif count_30d >= 1:
            score = 15
            detail = f"{count_30d} activities in 30d ({ratio:.1f}x avg) — barely active"
        else:
            score = 0
            detail = "no activities in 30d"

        return score, detail

    def _score_response_speed(self, activities, contact_id):
        """20% — how quickly they respond to outreach (inferred from activity gaps)."""
        if len(activities) < 2:
            return 50, "not enough activities to measure response speed"

        sorted_acts = sorted(
            activities,
            key=lambda a: a.get("due_date") or a.get("add_time", "")
        )

        gaps = []
        for i in range(1, len(sorted_acts)):
            d1 = sorted_acts[i - 1].get("due_date") or sorted_acts[i - 1].get("add_time", "")
            d2 = sorted_acts[i].get("due_date") or sorted_acts[i].get("add_time", "")
            gap = days_between(d1, d2)
            if gap < 999:
                gaps.append(gap)

        if not gaps:
            return 50, "no measurable gaps"

        avg_gap = statistics.mean(gaps)
        median_gap = statistics.median(gaps)

        if median_gap <= 1:
            score = 95
            detail = f"median {median_gap:.0f}d between interactions — lightning fast"
        elif median_gap <= 3:
            score = 80
            detail = f"median {median_gap:.0f}d between interactions — fast responder"
        elif median_gap <= 7:
            score = 60
            detail = f"median {median_gap:.0f}d between interactions — reasonable pace"
        elif median_gap <= 14:
            score = 35
            detail = f"median {median_gap:.0f}d between interactions — slow"
        else:
            score = 10
            detail = f"median {median_gap:.0f}d between interactions — very slow"

        return score, detail

    def _score_meeting_willingness(self, activities):
        """20% — ratio of meetings to emails."""
        meetings = 0
        emails = 0
        calls = 0

        for act in activities:
            act_type = (act.get("type") or "").lower()
            if act_type in ("meeting", "lunch", "demo", "call"):
                if act_type == "call":
                    calls += 1
                else:
                    meetings += 1
            elif act_type in ("email", "email_sent", "email_received"):
                emails += 1

        total = meetings + emails + calls
        if total == 0:
            return 30, "no meetings or emails tracked"

        meeting_ratio = (meetings + calls) / total

        if meetings >= 3:
            score = 95
            detail = f"{meetings} meetings + {calls} calls / {emails} emails — highly engaged"
        elif meeting_ratio >= 0.5:
            score = 85
            detail = f"{meetings} meetings + {calls} calls / {emails} emails — strong meeting ratio"
        elif meeting_ratio >= 0.3:
            score = 65
            detail = f"{meetings} meetings + {calls} calls / {emails} emails — decent ratio"
        elif meeting_ratio >= 0.1:
            score = 40
            detail = f"{meetings} meetings + {calls} calls / {emails} emails — email-heavy"
        elif emails > 0:
            score = 20
            detail = f"only {emails} emails, no meetings — low commitment"
        else:
            score = 10
            detail = f"minimal interaction ({total} total)"

        return score, detail

    def _score_deal_progression(self, deals):
        """15% — is their deal moving forward while they're champion."""
        if not deals:
            return 30, "no active deals"

        best_stage = 0
        progressing = 0
        stalling = 0
        total_value = 0

        vel_deals = self.velocity.get("deals", {})

        for deal in deals:
            stage_id = deal.get("stage_id")
            stage_info = SALES_STAGES.get(stage_id)
            if not stage_info:
                continue

            stage_order = stage_info[1]
            best_stage = max(best_stage, stage_order)
            total_value += deal.get("value") or 0

            deal_id = str(deal.get("id", ""))
            vel = vel_deals.get(deal_id, {})
            status = vel.get("velocity_status", "unknown")
            if status == "hot":
                progressing += 1
            elif status == "stalling":
                stalling += 1

        stage_score = min(best_stage * 12, 100)

        if progressing > 0 and stalling == 0:
            momentum_bonus = 20
            momentum = "deals moving fast"
        elif progressing > stalling:
            momentum_bonus = 10
            momentum = "net positive momentum"
        elif stalling > 0 and progressing == 0:
            momentum_bonus = -15
            momentum = "deals stalling"
        else:
            momentum_bonus = 0
            momentum = "steady"

        score = clamp(stage_score + momentum_bonus)
        stage_name = ""
        for sid, (name, order) in SALES_STAGES.items():
            if order == best_stage:
                stage_name = name
                break

        detail = (
            f"{len(deals)} deals, best stage: {stage_name or 'early'}, "
            f"{momentum}"
        )
        return round(score), detail

    def _score_multi_threading(self, org_id, contact_id):
        """10% — are multiple contacts at their company engaged."""
        if not org_id:
            return 50, "no organization linked"

        if org_id in self._org_contacts_cache:
            org_contacts = self._org_contacts_cache[org_id]
        else:
            resp = api_request(
                self.base, self.token, "GET",
                f"/api/v1/organizations/{org_id}/persons"
            )
            org_contacts = []
            if resp and resp.get("success") and resp.get("data"):
                org_contacts = resp["data"]
            self._org_contacts_cache[org_id] = org_contacts

        total_at_org = len(org_contacts)
        engaged = 0
        for person in org_contacts:
            pid = person.get("id")
            if pid and pid in self._activities_cache:
                acts = self._activities_cache[pid]
                cutoff_60 = (TODAY - timedelta(days=60)).isoformat()
                recent = [
                    a for a in acts
                    if (a.get("due_date") or a.get("add_time", "")) >= cutoff_60
                ]
                if recent:
                    engaged += 1

        if total_at_org <= 1:
            score = 30
            detail = "single-threaded — only 1 contact at company"
        elif engaged >= 3:
            score = 100
            detail = f"{engaged}/{total_at_org} contacts active — deep multi-threading"
        elif engaged >= 2:
            score = 75
            detail = f"{engaged}/{total_at_org} contacts active — multi-threaded"
        elif engaged >= 1:
            score = 45
            detail = f"{engaged}/{total_at_org} contacts active — light threading"
        else:
            score = 15
            detail = f"0/{total_at_org} contacts active — org gone quiet"

        return score, detail

    def _score_recency(self, activities):
        """10% — days since last interaction (exponential decay)."""
        last_date = self._last_activity_date(activities)
        if not last_date:
            return 0, "no activities found"

        days_since = days_between(last_date)

        # Exponential decay: score = 100 * e^(-0.05 * days)
        score = round(clamp(100 * math.exp(-0.05 * days_since)))

        if days_since <= 2:
            detail = f"last activity {days_since}d ago — very fresh"
        elif days_since <= 7:
            detail = f"last activity {days_since}d ago — recent"
        elif days_since <= 14:
            detail = f"last activity {days_since}d ago — starting to fade"
        elif days_since <= 30:
            detail = f"last activity {days_since}d ago — going cold"
        else:
            detail = f"last activity {days_since}d ago — cold"

        return score, detail

    # ── HELPERS ───────────────────────────────────────

    def _last_activity_date(self, activities):
        if not activities:
            return None
        dates = []
        for a in activities:
            d = a.get("due_date") or a.get("add_time", "")
            if d:
                dates.append(d[:10])
        return max(dates) if dates else None

    def _save_scores(self, scored, append=False):
        SCORES_FILE.parent.mkdir(parents=True, exist_ok=True)

        existing_contacts = {}
        existing_companies = {}
        history = []

        if append and self.existing:
            existing_contacts = self.existing.get("contacts", {})
            existing_companies = self.existing.get("companies", {})
            history = self.existing.get("history", [])

        for cid, data in scored.items():
            existing_contacts[cid] = data

        company_map = defaultdict(list)
        for cid, data in existing_contacts.items():
            org = data.get("org_name")
            if org:
                company_map[org].append(data)

        for org_name, contacts in company_map.items():
            scores = [c["engagement_score"] for c in contacts]
            existing_companies[org_name] = {
                "org_name": org_name,
                "contact_count": len(contacts),
                "avg_engagement": round(statistics.mean(scores), 1),
                "max_engagement": max(scores),
                "min_engagement": min(scores),
                "contacts": [
                    {"id": c["contact_id"], "name": c["name"], "score": c["engagement_score"]}
                    for c in sorted(contacts, key=lambda x: x["engagement_score"], reverse=True)
                ],
            }

        week_key = TODAY.strftime("%Y-W%W")
        history_entry = {
            "week": week_key,
            "date": TODAY.isoformat(),
            "total_contacts": len(existing_contacts),
            "avg_score": round(
                statistics.mean([c["engagement_score"] for c in existing_contacts.values()]), 1
            ) if existing_contacts else 0,
            "scores": {
                cid: c["engagement_score"]
                for cid, c in existing_contacts.items()
            },
        }

        existing_weeks = {h["week"] for h in history}
        if week_key in existing_weeks:
            history = [h for h in history if h["week"] != week_key]
        history.append(history_entry)
        history = history[-52:]

        all_scores = sorted(
            existing_contacts.values(),
            key=lambda x: x["engagement_score"],
            reverse=True
        )

        output = {
            "generated_at": NOW.isoformat(),
            "total_contacts": len(existing_contacts),
            "avg_engagement": round(
                statistics.mean([c["engagement_score"] for c in all_scores]), 1
            ) if all_scores else 0,
            "contacts": existing_contacts,
            "companies": existing_companies,
            "history": history,
        }

        SCORES_FILE.write_text(json.dumps(output, indent=2, ensure_ascii=False))
        elog(f"Scores saved: {len(existing_contacts)} contacts -> {SCORES_FILE}")


# ── ENGAGEMENT TREND ─────────────────────────────────

class EngagementTrend:
    """Track engagement over time, detect warming/cooling/ghost patterns."""

    def __init__(self, scorer: EngagementScorer):
        self.scorer = scorer
        self.existing = load_existing_scores()

    def detect_trends(self):
        """Analyze engagement history and classify each contact's trend."""
        history = self.existing.get("history", [])
        contacts = self.existing.get("contacts", {})

        if len(history) < 2:
            elog("Not enough history for trend detection (need 2+ weeks)")
            return self._default_trends(contacts)

        history_sorted = sorted(history, key=lambda h: h["date"])
        latest = history_sorted[-1]
        previous = history_sorted[-2]

        trends = {}
        for cid, contact in contacts.items():
            current_score = contact["engagement_score"]
            prev_score = previous.get("scores", {}).get(cid)
            days_since = contact.get("days_since_last_activity", 999)

            if prev_score is None:
                trend = "new"
                delta = 0
            else:
                delta = current_score - prev_score

                if days_since >= GHOST_DAYS and current_score < 20:
                    trend = "ghost"
                elif delta >= TREND_WARMING_DELTA:
                    trend = "warming_up"
                elif delta <= TREND_COOLING_DELTA:
                    trend = "cooling_down"
                else:
                    trend = "stable"

            alert = None
            if trend in ("cooling_down", "ghost") and current_score < 30:
                best_deal_value = 0
                for did, deal_data in self.scorer.velocity.get("deals", {}).items():
                    if deal_data.get("org") == contact.get("org_name"):
                        best_deal_value = max(best_deal_value, deal_data.get("value", 0))
                if best_deal_value > 0:
                    alert = {
                        "type": "high_value_going_cold",
                        "message": (
                            f"{contact['name']} at {contact.get('org_name', '?')} "
                            f"going cold (score: {current_score}, delta: {delta:+.0f}), "
                            f"deal value: {best_deal_value:,.0f}"
                        ),
                        "priority": "P1",
                    }

            trends[cid] = {
                "contact_id": int(cid) if cid.isdigit() else cid,
                "name": contact.get("name", "?"),
                "org": contact.get("org_name", ""),
                "current_score": current_score,
                "previous_score": prev_score,
                "delta": round(delta, 1),
                "trend": trend,
                "days_since_last_activity": days_since,
                "alert": alert,
            }

        self._publish_trend_alerts(trends)
        return trends

    def _default_trends(self, contacts):
        trends = {}
        for cid, contact in contacts.items():
            days_since = contact.get("days_since_last_activity", 999)
            score = contact["engagement_score"]
            if days_since >= GHOST_DAYS and score < 20:
                trend = "ghost"
            elif score >= 60:
                trend = "stable"
            elif score >= 30:
                trend = "stable"
            else:
                trend = "cooling_down"

            trends[cid] = {
                "contact_id": int(cid) if cid.isdigit() else cid,
                "name": contact.get("name", "?"),
                "org": contact.get("org_name", ""),
                "current_score": score,
                "previous_score": None,
                "delta": 0,
                "trend": trend,
                "days_since_last_activity": days_since,
                "alert": None,
            }
        return trends

    def _publish_trend_alerts(self, trends):
        alerts = [t for t in trends.values() if t.get("alert")]
        if not alerts:
            return
        try:
            sys.path.insert(0, str(WORKSPACE / "scripts"))
            from agent_bus import get_bus
            bus = get_bus()
            for t in alerts:
                bus.publish(
                    source="engagement_scorer",
                    topic="engagement.trend_change",
                    payload=t,
                    priority=t["alert"]["priority"],
                )
            bus.route_messages()
            elog(f"Published {len(alerts)} trend alerts to bus")
        except Exception as e:
            elog(f"Bus publish failed (non-fatal): {e}", "WARN")


# ── RELATIONSHIP MAP ─────────────────────────────────

class RelationshipMap:
    """Company-level engagement heat map with champion/coach/blocker identification."""

    def __init__(self, scorer: EngagementScorer):
        self.scorer = scorer
        self.existing = load_existing_scores()

    def company_heatmap(self, company_name):
        """Build engagement heat map for a company."""
        companies = self.existing.get("companies", {})
        contacts = self.existing.get("contacts", {})

        match = None
        company_lower = company_name.lower()
        for name, data in companies.items():
            if company_lower in name.lower():
                match = data
                break

        if not match:
            return None

        contact_details = []
        for c_info in match.get("contacts", []):
            cid = str(c_info["id"])
            full = contacts.get(cid, {})
            score = full.get("engagement_score", c_info.get("score", 0))

            if score >= 70:
                role = "champion"
            elif score >= 40:
                role = "coach"
            elif score >= 15:
                role = "passive"
            else:
                role = "blocker"

            contact_details.append({
                "contact_id": c_info["id"],
                "name": c_info.get("name", full.get("name", "?")),
                "score": score,
                "role": role,
                "days_since_activity": full.get("days_since_last_activity", 999),
                "deal_count": full.get("deal_count", 0),
                "factors": full.get("factors", {}),
            })

        contact_details.sort(key=lambda x: x["score"], reverse=True)

        champion_count = sum(1 for c in contact_details if c["role"] == "champion")
        coach_count = sum(1 for c in contact_details if c["role"] == "coach")
        passive_count = sum(1 for c in contact_details if c["role"] == "passive")
        blocker_count = sum(1 for c in contact_details if c["role"] == "blocker")

        total = len(contact_details)
        if total <= 1:
            threading_depth = 0
        elif champion_count >= 2 and coach_count >= 1:
            threading_depth = 100
        elif champion_count >= 1 and coach_count >= 1:
            threading_depth = 70
        elif champion_count >= 1:
            threading_depth = 40
        elif coach_count >= 1:
            threading_depth = 20
        else:
            threading_depth = 0

        return {
            "company": match["org_name"],
            "contact_count": total,
            "avg_engagement": match.get("avg_engagement", 0),
            "max_engagement": match.get("max_engagement", 0),
            "threading_depth": threading_depth,
            "role_summary": {
                "champions": champion_count,
                "coaches": coach_count,
                "passive": passive_count,
                "blockers": blocker_count,
            },
            "contacts": contact_details,
        }


# ── CHURN RISK ───────────────────────────────────────

class ChurnRisk:
    """Identify contacts at risk of disengagement."""

    def __init__(self, scorer: EngagementScorer):
        self.scorer = scorer
        self.existing = load_existing_scores()

    def find_cold_contacts(self):
        """Find contacts who were engaged but have gone silent, or are below company avg."""
        contacts = self.existing.get("contacts", {})
        companies = self.existing.get("companies", {})
        history = self.existing.get("history", [])

        cold = []
        for cid, contact in contacts.items():
            score = contact["engagement_score"]
            days_since = contact.get("days_since_last_activity", 999)
            org_name = contact.get("org_name", "")

            risk_reasons = []
            risk_score = 0

            # Ghost: had activities but now silent
            if days_since >= GHOST_DAYS:
                total_acts = contact.get("total_activities_90d", 0)
                if total_acts > 0:
                    risk_reasons.append(f"gone silent ({days_since}d, had {total_acts} activities)")
                    risk_score += 40
                else:
                    risk_reasons.append(f"never active ({days_since}d)")
                    risk_score += 20

            # Was engaged, now cold
            if len(history) >= 2:
                prev = history[-2].get("scores", {}).get(cid)
                if prev is not None and prev >= 50 and score < 30:
                    risk_reasons.append(f"score dropped from {prev:.0f} to {score:.0f}")
                    risk_score += 30

            # Below company average
            company_data = companies.get(org_name, {})
            company_avg = company_data.get("avg_engagement", 0)
            if company_avg > 0 and score < company_avg * 0.6:
                risk_reasons.append(
                    f"below company avg ({score:.0f} vs {company_avg:.0f})"
                )
                risk_score += 20

            # Low score with active deals
            if score < 25 and contact.get("deal_count", 0) > 0:
                risk_reasons.append("low engagement but has active deals")
                risk_score += 25

            if risk_reasons:
                cold.append({
                    "contact_id": contact["contact_id"],
                    "name": contact.get("name", "?"),
                    "org": org_name,
                    "engagement_score": score,
                    "risk_score": min(risk_score, 100),
                    "days_since_activity": days_since,
                    "deal_count": contact.get("deal_count", 0),
                    "risk_reasons": risk_reasons,
                    "suggested_action": self._suggest_action(contact, risk_reasons),
                })

        cold.sort(key=lambda x: x["risk_score"], reverse=True)

        self._publish_cold_alerts(cold)
        return cold

    def _suggest_action(self, contact, reasons):
        days_since = contact.get("days_since_last_activity", 999)
        score = contact["engagement_score"]

        if days_since >= 60:
            return "Send re-engagement email with fresh value prop or industry insight"
        elif days_since >= 30:
            return "Personal check-in call — ask about priorities, offer to help"
        elif score < 15:
            return "Try different channel (LinkedIn, phone) — email may not be landing"
        elif any("below company" in r for r in reasons):
            return "Loop them into next meeting with their engaged colleague"
        elif any("dropped" in r for r in reasons):
            return "Direct outreach — something changed, find out what"
        else:
            return "Schedule a brief catch-up call or send relevant content"

    def _publish_cold_alerts(self, cold):
        high_risk = [c for c in cold if c["risk_score"] >= 50 and c["deal_count"] > 0]
        if not high_risk:
            return
        try:
            sys.path.insert(0, str(WORKSPACE / "scripts"))
            from agent_bus import get_bus
            bus = get_bus()
            for c in high_risk[:10]:
                bus.publish(
                    source="engagement_scorer",
                    topic="engagement.cold_contact",
                    payload=c,
                    priority="P1" if c["risk_score"] >= 70 else "P2",
                )
            bus.route_messages()
            elog(f"Published {len(high_risk)} cold contact alerts to bus")
        except Exception as e:
            elog(f"Bus publish failed (non-fatal): {e}", "WARN")


# ── CLI DASHBOARD ────────────────────────────────────

def render_scores(scored):
    lines = []
    lines.append("=" * 75)
    lines.append("  CONTACT ENGAGEMENT SCORES")
    lines.append(f"  {NOW.strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 75)

    if not scored:
        lines.append("\n  No contacts scored. Check Pipedrive connection.")
        return "\n".join(lines)

    all_scores = sorted(scored.values(), key=lambda x: x["engagement_score"], reverse=True)
    avg = statistics.mean([c["engagement_score"] for c in all_scores])

    lines.append(f"\n  Total: {len(all_scores)} contacts | Avg engagement: {avg:.1f}/100")
    lines.append("")

    # Tier breakdown
    hot = [c for c in all_scores if c["engagement_score"] >= 70]
    warm = [c for c in all_scores if 40 <= c["engagement_score"] < 70]
    cool = [c for c in all_scores if 15 <= c["engagement_score"] < 40]
    cold = [c for c in all_scores if c["engagement_score"] < 15]

    lines.append(f"  HOT (>=70): {len(hot)} | WARM (40-69): {len(warm)} | "
                 f"COOL (15-39): {len(cool)} | COLD (<15): {len(cold)}")
    lines.append("")

    # Top engaged
    lines.append("  TOP ENGAGED CONTACTS")
    lines.append("  " + "-" * 71)
    lines.append(
        f"  {'Name':<25} {'Company':<20} {'Score':>6} {'Last':>6} {'Acts':>5} {'Deals':>5}"
    )
    lines.append("  " + "-" * 71)

    for c in all_scores[:20]:
        days = c.get("days_since_last_activity", 999)
        days_str = f"{days}d" if days < 999 else "n/a"
        lines.append(
            f"  {c['name'][:24]:<25} {c.get('org_name', '')[:19]:<20} "
            f"{c['engagement_score']:>5.0f} {days_str:>6} "
            f"{c.get('total_activities_90d', 0):>5} {c.get('deal_count', 0):>5}"
        )

    if len(all_scores) > 20:
        lines.append(f"  ... +{len(all_scores) - 20} more")

    lines.append("")
    lines.append("=" * 75)
    return "\n".join(lines)


def render_single(result):
    lines = []
    lines.append("=" * 65)
    lines.append(f"  ENGAGEMENT: {result['name']}")
    lines.append(f"  {result.get('org_name', 'No org')} | Score: {result['engagement_score']:.0f}/100")
    lines.append("=" * 65)

    lines.append(f"\n  Last activity: {result.get('last_activity_date', 'never')} "
                 f"({result.get('days_since_last_activity', '?')}d ago)")
    lines.append(f"  Activities (90d): {result.get('total_activities_90d', 0)}")
    lines.append(f"  Active deals: {result.get('deal_count', 0)}")

    lines.append(f"\n  FACTOR BREAKDOWN")
    lines.append("  " + "-" * 61)
    lines.append(f"  {'Factor':<22} {'Score':>6} {'Weight':>7} {'Weighted':>8}  Detail")
    lines.append("  " + "-" * 61)

    for name, f in result["factors"].items():
        weighted = f["score"] * f["weight"]
        label = name.replace("_", " ").title()
        lines.append(
            f"  {label:<22} {f['score']:>5.0f} {f['weight']:>6.0%} {weighted:>7.1f}  "
            f"{f['detail'][:40]}"
        )

    lines.append("  " + "-" * 61)
    lines.append(f"  {'TOTAL':<22} {result['engagement_score']:>5.0f}")

    lines.append("")
    lines.append("=" * 65)
    return "\n".join(lines)


def render_cold(cold_contacts):
    lines = []
    lines.append("=" * 75)
    lines.append("  COLD / AT-RISK CONTACTS")
    lines.append(f"  {NOW.strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 75)

    if not cold_contacts:
        lines.append("\n  No cold contacts found. Pipeline is healthy.")
        return "\n".join(lines)

    lines.append(f"\n  {len(cold_contacts)} contacts flagged")
    lines.append("")
    lines.append(
        f"  {'Name':<22} {'Company':<18} {'Eng':>4} {'Risk':>5} {'Days':>5} {'Deals':>5}  Action"
    )
    lines.append("  " + "-" * 71)

    for c in cold_contacts[:25]:
        lines.append(
            f"  {c['name'][:21]:<22} {c.get('org', '')[:17]:<18} "
            f"{c['engagement_score']:>3.0f} {c['risk_score']:>4} "
            f"{c['days_since_activity']:>5} {c['deal_count']:>5}  "
            f"{c.get('suggested_action', '')[:30]}"
        )
        for reason in c.get("risk_reasons", []):
            lines.append(f"    -> {reason}")

    if len(cold_contacts) > 25:
        lines.append(f"\n  ... +{len(cold_contacts) - 25} more")

    lines.append("")
    lines.append("=" * 75)
    return "\n".join(lines)


def render_heatmap(heatmap):
    lines = []
    lines.append("=" * 70)
    lines.append(f"  ENGAGEMENT HEAT MAP: {heatmap['company']}")
    lines.append(f"  {NOW.strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 70)

    lines.append(f"\n  Contacts: {heatmap['contact_count']} | "
                 f"Avg engagement: {heatmap['avg_engagement']:.0f} | "
                 f"Threading depth: {heatmap['threading_depth']}/100")

    rs = heatmap["role_summary"]
    lines.append(
        f"  Champions: {rs['champions']} | Coaches: {rs['coaches']} | "
        f"Passive: {rs['passive']} | Blockers: {rs['blockers']}"
    )

    lines.append("")
    lines.append(f"  {'Name':<25} {'Score':>6} {'Role':<12} {'Last':>6} {'Deals':>5}")
    lines.append("  " + "-" * 60)

    for c in heatmap["contacts"]:
        bar_len = int(c["score"] / 5)
        bar = "#" * bar_len + "." * (20 - bar_len)
        days = c.get("days_since_activity", 999)
        days_str = f"{days}d" if days < 999 else "n/a"
        lines.append(
            f"  {c['name'][:24]:<25} {c['score']:>5.0f} {c['role']:<12} "
            f"{days_str:>6} {c.get('deal_count', 0):>5}"
        )
        lines.append(f"    [{bar}]")

    lines.append("")
    lines.append("=" * 70)
    return "\n".join(lines)


def render_trends(trends):
    lines = []
    lines.append("=" * 75)
    lines.append("  ENGAGEMENT TRENDS")
    lines.append(f"  {NOW.strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 75)

    if not trends:
        lines.append("\n  No trend data available. Run 'score' first.")
        return "\n".join(lines)

    by_trend = defaultdict(list)
    for cid, t in trends.items():
        by_trend[t["trend"]].append(t)

    for trend_name, icon in [
        ("warming_up", "[++]"),
        ("cooling_down", "[--]"),
        ("ghost", "[!!]"),
        ("stable", "[ = ]"),
        ("new", "[**]"),
    ]:
        group = by_trend.get(trend_name, [])
        if not group:
            continue

        group.sort(key=lambda x: abs(x.get("delta", 0)), reverse=True)

        lines.append(f"\n  {icon} {trend_name.upper().replace('_', ' ')} ({len(group)})")
        lines.append("  " + "-" * 71)
        lines.append(
            f"  {'Name':<25} {'Company':<18} {'Score':>6} {'Delta':>7} {'Days':>5}"
        )
        lines.append("  " + "-" * 71)

        for t in group[:10]:
            delta_str = f"{t['delta']:+.0f}" if t["delta"] != 0 else "  0"
            days = t.get("days_since_last_activity", 999)
            days_str = f"{days}d" if days < 999 else "n/a"
            lines.append(
                f"  {t['name'][:24]:<25} {t.get('org', '')[:17]:<18} "
                f"{t['current_score']:>5.0f} {delta_str:>7} {days_str:>5}"
            )
            if t.get("alert"):
                lines.append(f"    ALERT: {t['alert']['message'][:65]}")

        if len(group) > 10:
            lines.append(f"  ... +{len(group) - 10} more")

    # Summary
    total = len(trends)
    alerts = sum(1 for t in trends.values() if t.get("alert"))
    lines.append(f"\n  Summary: {total} contacts tracked, {alerts} alerts")
    lines.append("=" * 75)
    return "\n".join(lines)


# ── CLI ──────────────────────────────────────────────

def main():
    env = load_env(ENV_PATH)
    base = env.get("PIPEDRIVE_BASE_URL", "").rstrip("/")
    token = env.get("PIPEDRIVE_API_TOKEN", "")

    if not base or not token:
        print("ERROR: Missing PIPEDRIVE_BASE_URL or PIPEDRIVE_API_TOKEN in .secrets/pipedrive.env")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: engagement_scorer.py [score|score <id>|cold|heatmap <company>|trends]")
        sys.exit(0)

    cmd = sys.argv[1]

    scorer = EngagementScorer(base, token)

    if cmd == "score":
        if len(sys.argv) >= 3:
            contact_id = int(sys.argv[2])
            print(f"Scoring contact {contact_id}...")
            result = scorer.score_single(contact_id)
            if result:
                print(render_single(result))
            else:
                print(f"Contact {contact_id} not found or has no data.")
        else:
            print("Scoring all contacts...")
            scored = scorer.score_all()
            print(render_scores(scored))
            print(f"\nScores saved to {SCORES_FILE}")

    elif cmd == "cold":
        existing = load_existing_scores()
        if not existing.get("contacts"):
            print("No scores yet. Run 'score' first.")
            sys.exit(1)

        churn = ChurnRisk(scorer)
        cold = churn.find_cold_contacts()
        print(render_cold(cold))

    elif cmd == "heatmap":
        if len(sys.argv) < 3:
            print("Usage: engagement_scorer.py heatmap <company_name>")
            print("\nAvailable companies:")
            existing = load_existing_scores()
            for name in sorted(existing.get("companies", {}).keys()):
                data = existing["companies"][name]
                print(f"  {name} ({data['contact_count']} contacts, avg: {data['avg_engagement']:.0f})")
            sys.exit(1)

        company = " ".join(sys.argv[2:])
        rmap = RelationshipMap(scorer)
        heatmap = rmap.company_heatmap(company)
        if heatmap:
            print(render_heatmap(heatmap))
        else:
            print(f"Company '{company}' not found in scored data.")
            print("Run 'score' first, then try again.")

    elif cmd == "trends":
        trend = EngagementTrend(scorer)
        trends = trend.detect_trends()
        print(render_trends(trends))

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: engagement_scorer.py [score|score <id>|cold|heatmap <company>|trends]")
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
