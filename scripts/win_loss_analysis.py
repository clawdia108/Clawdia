#!/usr/bin/env python3
"""
Win/Loss Analysis — Post-close deal intelligence
==================================================
After a deal closes (won or lost), auto-generates analysis of the full deal
journey: stages, timing, touchpoints, patterns, and actionable insights.

Usage:
  python3 scripts/win_loss_analysis.py analyze [--days 30]
  python3 scripts/win_loss_analysis.py patterns
  python3 scripts/win_loss_analysis.py deal <deal_id>
  python3 scripts/win_loss_analysis.py summary
"""

import json
import statistics
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

WORKSPACE = Path(__file__).resolve().parents[1]
ENV_PATH = WORKSPACE / ".secrets" / "pipedrive.env"
WIN_LOSS_DIR = WORKSPACE / "reviews" / "win_loss"
PATTERNS_FILE = WIN_LOSS_DIR / "patterns.json"
LOG_FILE = WORKSPACE / "logs" / "win-loss.log"

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

FIELD_LEAD_SOURCE = "545839ef97506e40a691aa34e0d24a82be08d624"
FIELD_PRODUCT = "f4f43d7b1284bc4049adb933c3f79ee2d327f637"
FIELD_USE_CASE = "5d832816b0d2d2a47a1d7b76f4382d3665d03020"
FIELD_MRR = "6c4a9ab5743abd972ed7746fb5d2a0035a543acf"

LEAD_SOURCE_LABELS = {89: "Cold", 88: "Inbound", 97: "Referral", 94: "Partner", 96: "Event", 98: "Customer"}


# ── ENV & API ──────────────────────────────────────────

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


def wlog(msg, level="INFO"):
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


# ── WIN/LOSS ANALYZER ─────────────────────────────────

class WinLossAnalyzer:
    """Analyze closed deals — what worked, what didn't, and why."""

    def __init__(self, base_url, api_token):
        self.base = base_url
        self.token = api_token

    def fetch_closed_deals(self, days=30):
        """Pull all deals closed (won or lost) within the given window."""
        wlog(f"Fetching deals closed in last {days} days...")

        won_deals = paged_get(self.base, self.token, "/api/v1/deals", {"status": "won"})
        lost_deals = paged_get(self.base, self.token, "/api/v1/deals", {"status": "lost"})

        cutoff = (TODAY - timedelta(days=days)).isoformat()
        closed = []

        for deal in won_deals + lost_deals:
            close_time = deal.get("won_time") or deal.get("lost_time") or deal.get("close_time") or ""
            if close_time and close_time[:10] >= cutoff:
                closed.append(deal)

        wlog(f"Found {len(closed)} closed deals (won: {sum(1 for d in closed if d.get('status') == 'won')}, "
             f"lost: {sum(1 for d in closed if d.get('status') == 'lost')})")
        return closed

    def fetch_deal_flow(self, deal_id):
        """Get the stage change history (flow) for a deal."""
        try:
            resp = api_request(self.base, self.token, "GET", f"/api/v1/deals/{deal_id}/flow")
            if resp and resp.get("success"):
                return resp.get("data") or []
        except Exception as e:
            wlog(f"Failed to fetch flow for deal {deal_id}: {e}", "WARN")
        return []

    def fetch_deal_activities(self, deal_id):
        """Get activities associated with a deal."""
        try:
            return paged_get(self.base, self.token, f"/api/v1/deals/{deal_id}/activities", {})
        except Exception as e:
            wlog(f"Failed to fetch activities for deal {deal_id}: {e}", "WARN")
        return []

    def fetch_deal_notes(self, deal_id):
        """Get notes for a deal (may contain competitive intel)."""
        try:
            return paged_get(self.base, self.token, f"/api/v1/deals/{deal_id}/notes", {})
        except Exception as e:
            wlog(f"Failed to fetch notes for deal {deal_id}: {e}", "WARN")
        return []

    def analyze_deal(self, deal):
        """Generate full analysis for a single closed deal."""
        deal_id = deal["id"]
        status = deal.get("status", "unknown")
        title = deal.get("title", "")
        org = deal.get("org_name") or ""
        value = deal.get("value") or 0
        currency = deal.get("currency", "CZK")

        add_time = (deal.get("add_time") or "")[:10]
        close_time = (deal.get("won_time") or deal.get("lost_time") or deal.get("close_time") or "")[:10]
        total_days = days_between(add_time, close_time) if add_time and close_time else 0

        # Owner
        owner = deal.get("user_id")
        if isinstance(owner, dict):
            owner_name = owner.get("name", "?")
        else:
            owner_name = "?"

        # Lead source
        lead_src = deal.get(FIELD_LEAD_SOURCE)
        lead_source = LEAD_SOURCE_LABELS.get(lead_src, f"Unknown ({lead_src})" if lead_src else "Not set")

        # Product
        product = deal.get(FIELD_PRODUCT)
        has_echo_pulse = False
        if product:
            product_str = str(product)
            has_echo_pulse = "107" in product_str

        # MRR
        mrr = deal.get(FIELD_MRR) or 0

        # Activity counts
        done_activities = deal.get("done_activities_count") or 0
        undone_activities = deal.get("undone_activities_count") or 0
        email_count = deal.get("email_messages_count") or 0
        notes_count = deal.get("notes_count") or 0

        # Fetch stage journey
        flow = self.fetch_deal_flow(deal_id)
        stage_journey = self._parse_stage_journey(flow, add_time, close_time)

        # Fetch activities for pattern analysis
        activities = self.fetch_deal_activities(deal_id)
        activity_analysis = self._analyze_activities(activities)

        # Fetch notes for competitive intel
        notes = self.fetch_deal_notes(deal_id)
        competitive_factors = self._extract_competitive_factors(notes)

        # Generate heuristic insights
        what_worked, what_didnt = self._heuristic_analysis(
            status, stage_journey, activity_analysis, done_activities,
            email_count, total_days, value, lead_source
        )

        # Person / stakeholder count
        person = deal.get("person_id")
        stakeholder_info = {}
        if isinstance(person, dict):
            stakeholder_info["primary_contact"] = person.get("name", "?")
            phones = person.get("phone", [])
            stakeholder_info["has_phone"] = any(p.get("value") for p in phones if isinstance(p, dict))
            emails = person.get("email", [])
            stakeholder_info["has_email"] = any(e.get("value") for e in emails if isinstance(e, dict))
        stakeholder_info["participants_count"] = deal.get("participants_count") or 0

        # Lost reason
        lost_reason = deal.get("lost_reason") or "" if status == "lost" else ""

        analysis = {
            "deal_id": deal_id,
            "title": title,
            "org": org,
            "status": status,
            "outcome": "WON" if status == "won" else "LOST",
            "value": value,
            "currency": currency,
            "mrr": mrr,
            "owner": owner_name,
            "lead_source": lead_source,
            "has_echo_pulse": has_echo_pulse,
            "add_time": add_time,
            "close_time": close_time,
            "total_days": total_days,
            "stage_journey": stage_journey,
            "touchpoints": {
                "total_activities": done_activities + undone_activities,
                "done_activities": done_activities,
                "emails": email_count,
                "notes": notes_count,
            },
            "activity_analysis": activity_analysis,
            "stakeholders": stakeholder_info,
            "competitive_factors": competitive_factors,
            "lost_reason": lost_reason,
            "what_worked": what_worked,
            "what_didnt": what_didnt,
            "analyzed_at": NOW.isoformat(),
        }

        # Save individual deal analysis
        WIN_LOSS_DIR.mkdir(parents=True, exist_ok=True)
        out_file = WIN_LOSS_DIR / f"{deal_id}.json"
        out_file.write_text(json.dumps(analysis, indent=2, ensure_ascii=False))
        wlog(f"Analysis saved: {out_file.name} ({status} — {title})")

        return analysis

    def _parse_stage_journey(self, flow, add_time, close_time):
        """Parse deal flow into a stage journey with time spent in each."""
        stages = []
        if not flow:
            return stages

        stage_changes = []
        for item in flow:
            if not isinstance(item, dict):
                continue
            obj = item.get("object", "")
            data = item.get("data") or {}
            ts = item.get("timestamp") or data.get("log_time") or ""

            # Look for stage change entries
            if obj == "dealChange" or "stage" in str(data).lower():
                old_val = data.get("old_value")
                new_val = data.get("new_value")
                field_key = data.get("field_key", "")
                if field_key == "stage_id" and ts:
                    stage_changes.append({
                        "from_stage": old_val,
                        "to_stage": new_val,
                        "timestamp": ts[:10] if ts else "",
                    })

            # Also handle activity-type flow items
            if obj == "activity":
                action = item.get("action", "")
                if action and ts:
                    pass  # activities tracked separately

        # Build journey from stage changes
        if stage_changes:
            stage_changes.sort(key=lambda x: x["timestamp"])
            for i, change in enumerate(stage_changes):
                stage_id = change.get("to_stage")
                entered = change["timestamp"]
                if i + 1 < len(stage_changes):
                    exited = stage_changes[i + 1]["timestamp"]
                else:
                    exited = close_time or TODAY.isoformat()

                stage_name = "Unknown"
                if stage_id:
                    try:
                        sid = int(stage_id)
                        stage_name = SALES_STAGES.get(sid, (f"Stage {sid}", 0))[0]
                    except (ValueError, TypeError):
                        stage_name = str(stage_id)

                days_in = days_between(entered, exited)
                stages.append({
                    "stage": stage_name,
                    "stage_id": stage_id,
                    "entered": entered,
                    "exited": exited,
                    "days": days_in,
                })

        return stages

    def _analyze_activities(self, activities):
        """Analyze activity patterns on the deal."""
        if not activities:
            return {"types": {}, "timeline": [], "avg_gap_days": 0, "first_activity": "", "last_activity": ""}

        by_type = defaultdict(int)
        dates = []
        for act in activities:
            atype = act.get("type", "unknown")
            by_type[atype] += 1
            due = act.get("due_date") or act.get("add_time", "")
            if due:
                dates.append(due[:10])

        dates.sort()

        # Average gap between activities
        gaps = []
        for i in range(1, len(dates)):
            gap = days_between(dates[i - 1], dates[i])
            if gap < 999:
                gaps.append(gap)

        avg_gap = round(statistics.mean(gaps), 1) if gaps else 0

        return {
            "types": dict(by_type),
            "total": len(activities),
            "first_activity": dates[0] if dates else "",
            "last_activity": dates[-1] if dates else "",
            "avg_gap_days": avg_gap,
            "activity_density": round(len(activities) / max(days_between(dates[0], dates[-1]), 1), 2) if len(dates) >= 2 else 0,
        }

    def _extract_competitive_factors(self, notes):
        """Extract competitive mentions from deal notes."""
        factors = []
        competitor_keywords = [
            "competitor", "competition", "alternative", "compared", "vs",
            "pricing", "cheaper", "expensive", "budget",
            "objection", "concern", "hesitation", "blocker",
            "internal", "champion", "sponsor", "decision",
        ]

        for note in notes:
            content = (note.get("content") or "").lower()
            for keyword in competitor_keywords:
                if keyword in content:
                    snippet = (note.get("content") or "")[:200]
                    # Strip HTML tags
                    import re
                    snippet = re.sub(r'<[^>]+>', '', snippet).strip()
                    if snippet:
                        factors.append({
                            "keyword": keyword,
                            "snippet": snippet,
                            "date": (note.get("add_time") or "")[:10],
                        })
                    break  # one match per note

        return factors

    def _heuristic_analysis(self, status, stage_journey, activity_analysis,
                            done_activities, email_count, total_days, value, lead_source):
        """Generate heuristic-based what worked / what didn't."""
        what_worked = []
        what_didnt = []

        is_won = status == "won"
        total_touchpoints = done_activities + email_count
        avg_gap = activity_analysis.get("avg_gap_days", 0)
        density = activity_analysis.get("activity_density", 0)

        # Touchpoint analysis
        if total_touchpoints >= 5 and is_won:
            what_worked.append(f"Strong engagement: {total_touchpoints} touchpoints kept deal moving")
        elif total_touchpoints < 3 and not is_won:
            what_didnt.append(f"Low engagement: only {total_touchpoints} touchpoints — deal may have been under-worked")
        elif total_touchpoints < 3 and is_won:
            what_worked.append(f"Efficient close: won with just {total_touchpoints} touchpoints")

        # Pacing analysis
        if avg_gap <= 5 and is_won:
            what_worked.append(f"Good pacing: avg {avg_gap}d between activities kept momentum")
        elif avg_gap > 14 and not is_won:
            what_didnt.append(f"Lost momentum: avg {avg_gap}d gaps between activities — too long")
        elif avg_gap > 14 and is_won:
            what_worked.append(f"Won despite long gaps ({avg_gap}d avg) — strong product-market fit")

        # Speed analysis
        if total_days <= 30 and is_won:
            what_worked.append(f"Fast close: {total_days} days from open to won")
        elif total_days > 90 and not is_won:
            what_didnt.append(f"Long cycle ({total_days}d) with no conversion — qualify earlier")
        elif total_days > 60 and is_won:
            what_worked.append(f"Persistence paid off: closed after {total_days} days")

        # Stage journey analysis
        if stage_journey:
            slow_stages = [s for s in stage_journey if s["days"] > 21]
            if slow_stages and not is_won:
                names = ", ".join(s["stage"] for s in slow_stages[:3])
                what_didnt.append(f"Stalled in: {names} (21+ days each)")
            elif not slow_stages and is_won:
                what_worked.append("Smooth progression through all stages")

            # Skipped stages
            if len(stage_journey) <= 2 and total_days <= 30 and is_won:
                what_worked.append("Accelerated pipeline — skipped intermediate stages")

        # Email engagement
        if email_count >= 5 and is_won:
            what_worked.append(f"Strong email thread ({email_count} messages) — good dialogue")
        elif email_count == 0 and not is_won:
            what_didnt.append("Zero email engagement — no written dialogue established")

        # Lead source factor
        if lead_source in ("Inbound", "Referral") and is_won:
            what_worked.append(f"{lead_source} lead — warm entry point")
        elif lead_source == "Cold" and not is_won:
            what_didnt.append("Cold outreach without enough nurturing")
        elif lead_source == "Cold" and is_won:
            what_worked.append("Cold-to-won conversion — strong sales execution")

        # Value factor
        if value > 100000 and is_won:
            what_worked.append(f"High-value deal ({value:,.0f}) closed successfully")
        elif value > 100000 and not is_won:
            what_didnt.append(f"High-value deal ({value:,.0f}) lost — review pricing/proposal")

        # Fallbacks
        if not what_worked:
            what_worked.append("No clear positive patterns identified")
        if not what_didnt:
            what_didnt.append("No clear negative patterns identified")

        return what_worked, what_didnt

    def analyze_all(self, days=30):
        """Analyze all recently closed deals."""
        closed = self.fetch_closed_deals(days)
        analyses = []
        for deal in closed:
            try:
                analysis = self.analyze_deal(deal)
                analyses.append(analysis)
                time.sleep(0.3)  # Rate limit protection
            except Exception as e:
                wlog(f"Failed to analyze deal {deal.get('id')}: {e}", "ERROR")

        wlog(f"Analyzed {len(analyses)} closed deals")
        return analyses

    def get_aggregate_stats(self, days=90):
        """Calculate win rate by industry, size, touchpoints from stored analyses."""
        analyses = self._load_all_analyses()
        if not analyses:
            return {}

        cutoff = (TODAY - timedelta(days=days)).isoformat()
        recent = [a for a in analyses if a.get("close_time", "") >= cutoff]

        if not recent:
            return {"total": 0, "message": "No recent analyses found"}

        won = [a for a in recent if a["outcome"] == "WON"]
        lost = [a for a in recent if a["outcome"] == "LOST"]

        # Win rate by lead source
        by_source = defaultdict(lambda: {"won": 0, "lost": 0})
        for a in recent:
            src = a.get("lead_source", "Unknown")
            if a["outcome"] == "WON":
                by_source[src]["won"] += 1
            else:
                by_source[src]["lost"] += 1

        source_rates = {}
        for src, counts in by_source.items():
            total = counts["won"] + counts["lost"]
            source_rates[src] = {
                "won": counts["won"],
                "lost": counts["lost"],
                "total": total,
                "win_rate": round(counts["won"] / total * 100, 1) if total else 0,
            }

        # Win rate by deal size bucket
        def size_bucket(value):
            if value >= 200000:
                return "200k+"
            elif value >= 100000:
                return "100k-200k"
            elif value >= 50000:
                return "50k-100k"
            elif value >= 10000:
                return "10k-50k"
            else:
                return "<10k"

        by_size = defaultdict(lambda: {"won": 0, "lost": 0})
        for a in recent:
            bucket = size_bucket(a.get("value", 0))
            if a["outcome"] == "WON":
                by_size[bucket]["won"] += 1
            else:
                by_size[bucket]["lost"] += 1

        size_rates = {}
        for bucket, counts in by_size.items():
            total = counts["won"] + counts["lost"]
            size_rates[bucket] = {
                "won": counts["won"],
                "lost": counts["lost"],
                "total": total,
                "win_rate": round(counts["won"] / total * 100, 1) if total else 0,
            }

        # Win rate by touchpoint count
        def tp_bucket(touchpoints):
            if touchpoints >= 10:
                return "10+"
            elif touchpoints >= 5:
                return "5-9"
            elif touchpoints >= 3:
                return "3-4"
            else:
                return "1-2"

        by_touchpoints = defaultdict(lambda: {"won": 0, "lost": 0})
        for a in recent:
            tp = a.get("touchpoints", {}).get("done_activities", 0) + a.get("touchpoints", {}).get("emails", 0)
            bucket = tp_bucket(tp)
            if a["outcome"] == "WON":
                by_touchpoints[bucket]["won"] += 1
            else:
                by_touchpoints[bucket]["lost"] += 1

        touchpoint_rates = {}
        for bucket, counts in by_touchpoints.items():
            total = counts["won"] + counts["lost"]
            touchpoint_rates[bucket] = {
                "won": counts["won"],
                "lost": counts["lost"],
                "total": total,
                "win_rate": round(counts["won"] / total * 100, 1) if total else 0,
            }

        # Average deal cycle
        won_cycles = [a["total_days"] for a in won if a.get("total_days", 0) > 0]
        lost_cycles = [a["total_days"] for a in lost if a.get("total_days", 0) > 0]

        return {
            "period_days": days,
            "total_analyzed": len(recent),
            "won": len(won),
            "lost": len(lost),
            "overall_win_rate": round(len(won) / len(recent) * 100, 1) if recent else 0,
            "avg_won_cycle_days": round(statistics.mean(won_cycles), 1) if won_cycles else 0,
            "avg_lost_cycle_days": round(statistics.mean(lost_cycles), 1) if lost_cycles else 0,
            "by_lead_source": source_rates,
            "by_deal_size": size_rates,
            "by_touchpoints": touchpoint_rates,
            "total_won_value": sum(a.get("value", 0) for a in won),
            "total_lost_value": sum(a.get("value", 0) for a in lost),
        }

    def _load_all_analyses(self):
        """Load all stored deal analyses."""
        analyses = []
        if not WIN_LOSS_DIR.exists():
            return analyses

        for f in WIN_LOSS_DIR.glob("*.json"):
            if f.name == "patterns.json":
                continue
            try:
                data = json.loads(f.read_text())
                if "deal_id" in data:
                    analyses.append(data)
            except (json.JSONDecodeError, OSError):
                continue

        return analyses

    def get_single_deal(self, deal_id):
        """Load or fetch analysis for a single deal."""
        out_file = WIN_LOSS_DIR / f"{deal_id}.json"
        if out_file.exists():
            return json.loads(out_file.read_text())

        # Try to fetch and analyze
        try:
            resp = api_request(self.base, self.token, "GET", f"/api/v1/deals/{deal_id}")
            if resp and resp.get("success") and resp.get("data"):
                deal = resp["data"]
                if deal.get("status") in ("won", "lost"):
                    return self.analyze_deal(deal)
                else:
                    return {"error": f"Deal {deal_id} is still open (status: {deal.get('status')})"}
        except Exception as e:
            return {"error": f"Failed to fetch deal {deal_id}: {e}"}

        return {"error": f"Deal {deal_id} not found"}


# ── PATTERN DETECTOR ──────────────────────────────────

class PatternDetector:
    """Analyze all win/loss records to surface patterns and recommendations."""

    def __init__(self, analyzer: WinLossAnalyzer):
        self.analyzer = analyzer

    def detect_patterns(self):
        """Run full pattern detection across all stored analyses."""
        analyses = self.analyzer._load_all_analyses()
        if len(analyses) < 2:
            return {
                "status": "insufficient_data",
                "message": f"Only {len(analyses)} analyses found. Need at least 2 to detect patterns.",
                "recommendations": ["Run 'analyze --days 90' to build up the analysis database"],
            }

        won = [a for a in analyses if a["outcome"] == "WON"]
        lost = [a for a in analyses if a["outcome"] == "LOST"]

        patterns = {
            "generated_at": NOW.isoformat(),
            "total_analyzed": len(analyses),
            "won": len(won),
            "lost": len(lost),
            "overall_win_rate": round(len(won) / len(analyses) * 100, 1),
            "correlations": self._compute_correlations(won, lost),
            "winning_traits": self._common_traits(won, "WON"),
            "losing_traits": self._common_traits(lost, "LOST"),
            "insights": [],
            "recommendations": [],
        }

        # Generate insights
        patterns["insights"] = self._generate_insights(patterns, won, lost)
        patterns["recommendations"] = self._generate_recommendations(patterns, won, lost)

        # Save
        PATTERNS_FILE.parent.mkdir(parents=True, exist_ok=True)
        PATTERNS_FILE.write_text(json.dumps(patterns, indent=2, ensure_ascii=False))
        wlog(f"Patterns saved: {len(patterns['insights'])} insights, {len(patterns['recommendations'])} recommendations")

        return patterns

    def _compute_correlations(self, won, lost):
        """Compute key correlations between deal attributes and outcomes."""
        correlations = {}

        # Touchpoints vs outcome
        won_tp = [a["touchpoints"]["done_activities"] + a["touchpoints"]["emails"] for a in won if a.get("touchpoints")]
        lost_tp = [a["touchpoints"]["done_activities"] + a["touchpoints"]["emails"] for a in lost if a.get("touchpoints")]

        correlations["touchpoints"] = {
            "won_avg": round(statistics.mean(won_tp), 1) if won_tp else 0,
            "lost_avg": round(statistics.mean(lost_tp), 1) if lost_tp else 0,
            "won_median": round(statistics.median(won_tp), 1) if won_tp else 0,
            "lost_median": round(statistics.median(lost_tp), 1) if lost_tp else 0,
        }

        # Deal cycle vs outcome
        won_days = [a["total_days"] for a in won if a.get("total_days", 0) > 0]
        lost_days = [a["total_days"] for a in lost if a.get("total_days", 0) > 0]

        correlations["cycle_days"] = {
            "won_avg": round(statistics.mean(won_days), 1) if won_days else 0,
            "lost_avg": round(statistics.mean(lost_days), 1) if lost_days else 0,
            "won_median": round(statistics.median(won_days), 1) if won_days else 0,
            "lost_median": round(statistics.median(lost_days), 1) if lost_days else 0,
        }

        # Deal size vs outcome
        won_values = [a["value"] for a in won if a.get("value", 0) > 0]
        lost_values = [a["value"] for a in lost if a.get("value", 0) > 0]

        correlations["deal_size"] = {
            "won_avg": round(statistics.mean(won_values)) if won_values else 0,
            "lost_avg": round(statistics.mean(lost_values)) if lost_values else 0,
            "won_median": round(statistics.median(won_values)) if won_values else 0,
            "lost_median": round(statistics.median(lost_values)) if lost_values else 0,
        }

        # Email engagement vs outcome
        won_emails = [a["touchpoints"]["emails"] for a in won if a.get("touchpoints")]
        lost_emails = [a["touchpoints"]["emails"] for a in lost if a.get("touchpoints")]

        correlations["email_engagement"] = {
            "won_avg": round(statistics.mean(won_emails), 1) if won_emails else 0,
            "lost_avg": round(statistics.mean(lost_emails), 1) if lost_emails else 0,
        }

        # Activity gap (pacing) vs outcome
        won_gaps = [a.get("activity_analysis", {}).get("avg_gap_days", 0) for a in won]
        lost_gaps = [a.get("activity_analysis", {}).get("avg_gap_days", 0) for a in lost]
        won_gaps = [g for g in won_gaps if g > 0]
        lost_gaps = [g for g in lost_gaps if g > 0]

        correlations["activity_pacing"] = {
            "won_avg_gap_days": round(statistics.mean(won_gaps), 1) if won_gaps else 0,
            "lost_avg_gap_days": round(statistics.mean(lost_gaps), 1) if lost_gaps else 0,
        }

        return correlations

    def _common_traits(self, deals, label):
        """Find what deals in this group have in common."""
        if not deals:
            return {}

        traits = {
            "avg_value": round(statistics.mean([d.get("value", 0) for d in deals])),
            "avg_days": round(statistics.mean([d.get("total_days", 0) for d in deals if d.get("total_days", 0) > 0])) if any(d.get("total_days", 0) > 0 for d in deals) else 0,
            "echo_pulse_pct": round(sum(1 for d in deals if d.get("has_echo_pulse")) / len(deals) * 100, 1),
            "most_common_source": "",
            "avg_touchpoints": 0,
        }

        # Most common lead source
        sources = [d.get("lead_source", "Unknown") for d in deals]
        if sources:
            from collections import Counter
            traits["most_common_source"] = Counter(sources).most_common(1)[0][0]

        # Avg touchpoints
        tps = [d.get("touchpoints", {}).get("done_activities", 0) + d.get("touchpoints", {}).get("emails", 0) for d in deals]
        traits["avg_touchpoints"] = round(statistics.mean(tps), 1) if tps else 0

        # Most common "what worked" / "what didn't"
        all_insights = []
        for d in deals:
            if label == "WON":
                all_insights.extend(d.get("what_worked", []))
            else:
                all_insights.extend(d.get("what_didnt", []))
        if all_insights:
            from collections import Counter
            traits["top_patterns"] = [item for item, _ in Counter(all_insights).most_common(5)]

        return traits

    def _generate_insights(self, patterns, won, lost):
        """Generate top 5 actionable insights."""
        insights = []
        corr = patterns.get("correlations", {})

        # Touchpoint insight
        tp = corr.get("touchpoints", {})
        if tp.get("won_avg", 0) > 0 and tp.get("lost_avg", 0) > 0:
            diff = tp["won_avg"] - tp["lost_avg"]
            if diff > 2:
                insights.append({
                    "type": "touchpoints",
                    "finding": f"Won deals average {tp['won_avg']:.0f} touchpoints vs {tp['lost_avg']:.0f} for lost",
                    "action": f"Aim for at least {tp['won_avg']:.0f} touchpoints per deal before expecting a close",
                    "confidence": "high" if len(won) >= 5 else "medium",
                })

        # Pacing insight
        pacing = corr.get("activity_pacing", {})
        won_gap = pacing.get("won_avg_gap_days", 0)
        lost_gap = pacing.get("lost_avg_gap_days", 0)
        if won_gap > 0 and lost_gap > 0 and lost_gap > won_gap * 1.3:
            insights.append({
                "type": "pacing",
                "finding": f"Won deals have {won_gap:.0f}d avg between activities vs {lost_gap:.0f}d for lost",
                "action": f"Keep activity gaps under {won_gap + 2:.0f} days to maintain momentum",
                "confidence": "high",
            })

        # Cycle time insight
        cycle = corr.get("cycle_days", {})
        if cycle.get("won_avg", 0) > 0 and cycle.get("lost_avg", 0) > 0:
            insights.append({
                "type": "cycle_time",
                "finding": f"Won deals close in {cycle['won_avg']:.0f}d avg vs {cycle['lost_avg']:.0f}d for lost",
                "action": "Deals lingering past " + f"{cycle['won_avg'] * 1.5:.0f}d should be re-qualified or deprioritized",
                "confidence": "medium",
            })

        # Deal size insight
        size = corr.get("deal_size", {})
        if size.get("won_avg", 0) > 0 and size.get("lost_avg", 0) > 0:
            insights.append({
                "type": "deal_size",
                "finding": f"Won deals avg value: {size['won_avg']:,.0f} vs lost: {size['lost_avg']:,.0f}",
                "action": "Focus energy on deals in the winning size range",
                "confidence": "medium",
            })

        # Email engagement insight
        email = corr.get("email_engagement", {})
        if email.get("won_avg", 0) > email.get("lost_avg", 0) * 1.5:
            insights.append({
                "type": "email_engagement",
                "finding": f"Won deals avg {email['won_avg']:.0f} emails vs {email['lost_avg']:.0f} for lost",
                "action": "Push for email dialogue — deals with more email threads close at higher rates",
                "confidence": "high",
            })

        # Echo Pulse insight
        won_ep = sum(1 for d in won if d.get("has_echo_pulse"))
        lost_ep = sum(1 for d in lost if d.get("has_echo_pulse"))
        if won_ep + lost_ep > 0:
            ep_win_rate = round(won_ep / (won_ep + lost_ep) * 100, 1) if (won_ep + lost_ep) else 0
            overall_wr = patterns.get("overall_win_rate", 0)
            if ep_win_rate > overall_wr + 10:
                insights.append({
                    "type": "product",
                    "finding": f"Echo Pulse deals win at {ep_win_rate}% vs {overall_wr}% overall",
                    "action": "Double down on Echo Pulse positioning — it clearly resonates",
                    "confidence": "high",
                })

        # Lost reason patterns
        lost_reasons = [d.get("lost_reason", "") for d in lost if d.get("lost_reason")]
        if lost_reasons:
            from collections import Counter
            top_reason = Counter(lost_reasons).most_common(1)
            if top_reason:
                reason, count = top_reason[0]
                insights.append({
                    "type": "lost_reasons",
                    "finding": f"Top lost reason: '{reason}' ({count} deals)",
                    "action": f"Address '{reason}' proactively in early conversations",
                    "confidence": "high" if count >= 3 else "medium",
                })

        return insights[:5]

    def _generate_recommendations(self, patterns, won, lost):
        """Generate top 5 prioritized recommendations."""
        recs = []
        insights = patterns.get("insights", [])
        corr = patterns.get("correlations", {})

        # Based on insights
        for insight in insights:
            recs.append({
                "priority": len(recs) + 1,
                "area": insight["type"],
                "recommendation": insight["action"],
                "based_on": insight["finding"],
                "confidence": insight["confidence"],
            })

        # Additional recommendations based on aggregate data
        win_rate = patterns.get("overall_win_rate", 0)
        if win_rate < 30:
            recs.append({
                "priority": len(recs) + 1,
                "area": "qualification",
                "recommendation": "Tighten lead qualification — win rate below 30% suggests pipeline quality issues",
                "based_on": f"Overall win rate: {win_rate}%",
                "confidence": "high",
            })

        if len(lost) > len(won) * 2:
            recs.append({
                "priority": len(recs) + 1,
                "area": "pipeline_health",
                "recommendation": "Review lost deal reasons — losing 2x more than winning needs attention",
                "based_on": f"{len(won)} won vs {len(lost)} lost",
                "confidence": "high",
            })

        return recs[:5]


# ── CLI ───────────────────────────────────────────────

def render_summary(stats):
    """Print aggregate stats to terminal."""
    lines = []
    lines.append("=" * 70)
    lines.append("  WIN/LOSS SUMMARY")
    lines.append(f"  Period: last {stats.get('period_days', 90)} days")
    lines.append("=" * 70)

    lines.append(f"\n  Total analyzed: {stats.get('total_analyzed', 0)}")
    lines.append(f"  Won: {stats.get('won', 0)} | Lost: {stats.get('lost', 0)}")
    lines.append(f"  Win Rate: {stats.get('overall_win_rate', 0)}%")
    lines.append(f"  Won Value: {stats.get('total_won_value', 0):,.0f} CZK")
    lines.append(f"  Lost Value: {stats.get('total_lost_value', 0):,.0f} CZK")

    avg_won = stats.get("avg_won_cycle_days", 0)
    avg_lost = stats.get("avg_lost_cycle_days", 0)
    if avg_won or avg_lost:
        lines.append(f"\n  Avg cycle: Won {avg_won}d | Lost {avg_lost}d")

    # By lead source
    by_source = stats.get("by_lead_source", {})
    if by_source:
        lines.append(f"\n  BY LEAD SOURCE")
        lines.append(f"  {'Source':<15} {'Won':>4} {'Lost':>5} {'Rate':>6}")
        lines.append("  " + "-" * 34)
        for src, data in sorted(by_source.items(), key=lambda x: -x[1]["win_rate"]):
            lines.append(f"  {src:<15} {data['won']:>4} {data['lost']:>5} {data['win_rate']:>5.1f}%")

    # By deal size
    by_size = stats.get("by_deal_size", {})
    if by_size:
        lines.append(f"\n  BY DEAL SIZE")
        lines.append(f"  {'Bucket':<15} {'Won':>4} {'Lost':>5} {'Rate':>6}")
        lines.append("  " + "-" * 34)
        for bucket, data in sorted(by_size.items()):
            lines.append(f"  {bucket:<15} {data['won']:>4} {data['lost']:>5} {data['win_rate']:>5.1f}%")

    # By touchpoints
    by_tp = stats.get("by_touchpoints", {})
    if by_tp:
        lines.append(f"\n  BY TOUCHPOINTS")
        lines.append(f"  {'Bucket':<15} {'Won':>4} {'Lost':>5} {'Rate':>6}")
        lines.append("  " + "-" * 34)
        for bucket, data in sorted(by_tp.items()):
            lines.append(f"  {bucket:<15} {data['won']:>4} {data['lost']:>5} {data['win_rate']:>5.1f}%")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def render_deal(analysis):
    """Pretty-print a single deal analysis."""
    lines = []
    lines.append("=" * 70)
    lines.append(f"  DEAL ANALYSIS: {analysis.get('title', '?')}")
    lines.append(f"  {analysis.get('outcome', '?')} | {analysis.get('org', '?')}")
    lines.append("=" * 70)

    lines.append(f"\n  Value: {analysis.get('value', 0):,.0f} {analysis.get('currency', 'CZK')}")
    lines.append(f"  Owner: {analysis.get('owner', '?')}")
    lines.append(f"  Source: {analysis.get('lead_source', '?')}")
    lines.append(f"  Echo Pulse: {'Yes' if analysis.get('has_echo_pulse') else 'No'}")
    lines.append(f"  Cycle: {analysis.get('total_days', 0)} days ({analysis.get('add_time', '?')} -> {analysis.get('close_time', '?')})")

    if analysis.get("lost_reason"):
        lines.append(f"  Lost Reason: {analysis['lost_reason']}")

    # Stage journey
    journey = analysis.get("stage_journey", [])
    if journey:
        lines.append(f"\n  STAGE JOURNEY ({len(journey)} stages)")
        lines.append("  " + "-" * 50)
        for s in journey:
            lines.append(f"  {s['stage']:<25} {s['days']:>3}d  ({s['entered']} -> {s['exited']})")

    # Touchpoints
    tp = analysis.get("touchpoints", {})
    lines.append(f"\n  TOUCHPOINTS")
    lines.append(f"  Activities: {tp.get('done_activities', 0)} done | Emails: {tp.get('emails', 0)} | Notes: {tp.get('notes', 0)}")

    aa = analysis.get("activity_analysis", {})
    if aa.get("avg_gap_days"):
        lines.append(f"  Avg gap: {aa['avg_gap_days']}d | Density: {aa.get('activity_density', 0):.2f} acts/day")

    # What worked / didn't
    lines.append(f"\n  WHAT WORKED")
    for item in analysis.get("what_worked", []):
        lines.append(f"  + {item}")

    lines.append(f"\n  WHAT DIDN'T WORK")
    for item in analysis.get("what_didnt", []):
        lines.append(f"  - {item}")

    # Competitive factors
    cf = analysis.get("competitive_factors", [])
    if cf:
        lines.append(f"\n  COMPETITIVE INTEL ({len(cf)} mentions)")
        for factor in cf[:5]:
            lines.append(f"  [{factor['keyword']}] {factor['snippet'][:80]}")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def render_patterns(patterns):
    """Pretty-print pattern detection results."""
    lines = []
    lines.append("=" * 70)
    lines.append("  WIN/LOSS PATTERN ANALYSIS")
    lines.append(f"  {patterns.get('total_analyzed', 0)} deals analyzed")
    lines.append(f"  Win rate: {patterns.get('overall_win_rate', 0)}%")
    lines.append("=" * 70)

    # Correlations
    corr = patterns.get("correlations", {})
    if corr:
        lines.append(f"\n  KEY CORRELATIONS")
        lines.append("  " + "-" * 60)
        for key, data in corr.items():
            label = key.replace("_", " ").title()
            lines.append(f"\n  {label}:")
            for metric, val in data.items():
                lines.append(f"    {metric}: {val}")

    # Insights
    insights = patterns.get("insights", [])
    if insights:
        lines.append(f"\n  TOP {len(insights)} INSIGHTS")
        lines.append("  " + "-" * 60)
        for i, insight in enumerate(insights, 1):
            lines.append(f"\n  {i}. [{insight['type'].upper()}] ({insight['confidence']} confidence)")
            lines.append(f"     Finding: {insight['finding']}")
            lines.append(f"     Action:  {insight['action']}")

    # Recommendations
    recs = patterns.get("recommendations", [])
    if recs:
        lines.append(f"\n  TOP {len(recs)} RECOMMENDATIONS")
        lines.append("  " + "-" * 60)
        for rec in recs:
            lines.append(f"\n  #{rec['priority']} [{rec['area'].upper()}]")
            lines.append(f"     {rec['recommendation']}")
            lines.append(f"     Based on: {rec['based_on']}")

    lines.append("\n" + "=" * 70)
    return "\n".join(lines)


def main():
    env = load_env(ENV_PATH)
    base = env.get("PIPEDRIVE_BASE_URL", "").rstrip("/")
    token = env.get("PIPEDRIVE_API_TOKEN", "")

    if not base or not token:
        print("ERROR: Missing PIPEDRIVE_BASE_URL or PIPEDRIVE_API_TOKEN in .secrets/pipedrive.env")
        sys.exit(1)

    analyzer = WinLossAnalyzer(base, token)
    detector = PatternDetector(analyzer)

    if len(sys.argv) < 2:
        print("Usage: win_loss_analysis.py [analyze|patterns|deal <id>|summary]")
        print("  analyze [--days 30]  — Analyze all recently closed deals")
        print("  patterns             — Detect patterns across all analyses")
        print("  deal <deal_id>       — Show analysis for a specific deal")
        print("  summary              — Show aggregate win/loss stats")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "analyze":
        days = 30
        if "--days" in sys.argv:
            idx = sys.argv.index("--days")
            if idx + 1 < len(sys.argv):
                days = int(sys.argv[idx + 1])

        print(f"Analyzing deals closed in last {days} days...")
        analyses = analyzer.analyze_all(days)
        won = sum(1 for a in analyses if a["outcome"] == "WON")
        lost = sum(1 for a in analyses if a["outcome"] == "LOST")
        print(f"\nAnalyzed {len(analyses)} deals: {won} won, {lost} lost")
        print(f"Results saved to {WIN_LOSS_DIR}/")

        if analyses:
            print(f"\nAuto-detecting patterns...")
            patterns = detector.detect_patterns()
            if patterns.get("recommendations"):
                print(f"\nTop recommendation: {patterns['recommendations'][0]['recommendation']}")

    elif cmd == "patterns":
        patterns = detector.detect_patterns()
        print(render_patterns(patterns))

    elif cmd == "deal":
        if len(sys.argv) < 3:
            print("Usage: win_loss_analysis.py deal <deal_id>")
            sys.exit(1)
        deal_id = int(sys.argv[2])
        analysis = analyzer.get_single_deal(deal_id)
        if "error" in analysis:
            print(f"Error: {analysis['error']}")
        else:
            print(render_deal(analysis))

    elif cmd == "summary":
        days = 90
        if "--days" in sys.argv:
            idx = sys.argv.index("--days")
            if idx + 1 < len(sys.argv):
                days = int(sys.argv[idx + 1])

        stats = analyzer.get_aggregate_stats(days)
        print(render_summary(stats))

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: win_loss_analysis.py [analyze|patterns|deal <id>|summary]")
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
