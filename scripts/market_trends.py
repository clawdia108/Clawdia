#!/usr/bin/env python3
"""
Market Trend Detector — sales pipeline trend analysis & competitive intelligence
==================================================================================
Analyzes deal velocity changes, win rate shifts, stage conversion bottlenecks,
deal size trends, seasonal patterns, and competitor signals.

Integrates with:
  - Pipedrive API (deal history, activities, notes)
  - Knowledge Graph (industry/company data)
  - Deal Velocity Tracker (stage timing data)
  - Structured Logger (slog)
  - Optional Ollama (narrative generation)

Usage:
  python3 scripts/market_trends.py analyze     # Full analysis
  python3 scripts/market_trends.py trends      # Show active trends
  python3 scripts/market_trends.py seasonal    # Seasonal patterns
  python3 scripts/market_trends.py report      # Generate weekly report
"""

import json
import re
import statistics
import subprocess
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
TRENDS_FILE = WORKSPACE / "knowledge" / "market-trends.json"
VELOCITY_FILE = WORKSPACE / "pipedrive" / "deal_velocity.json"
GRAPH_FILE = WORKSPACE / "knowledge" / "graph.json"
LOG_FILE = WORKSPACE / "logs" / "market-trends.log"

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

STAGE_ORDER = {sid: order for sid, (_, order) in SALES_STAGES.items()}
STAGE_NAMES = {sid: name for sid, (name, _) in SALES_STAGES.items()}

COMPETITOR_KEYWORDS = [
    "competitor", "alternative", "other vendor", "chose another",
    "went with", "selected", "competing", "rival", "benchmark",
    "comparison", "evaluated", "shortlist", "RFP", "tender",
]

LOSS_REASON_KEYWORDS = {
    "price": ["price", "cost", "expensive", "budget", "cheap", "afford"],
    "timing": ["timing", "not ready", "later", "postpone", "delay", "next year"],
    "fit": ["fit", "needs", "requirements", "scope", "feature", "missing"],
    "competitor": ["competitor", "alternative", "other vendor", "chose another", "went with"],
    "no_response": ["no response", "ghost", "unreachable", "silent", "no reply"],
    "internal": ["internal", "reorganization", "management", "change", "merger"],
}


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


def tlog(msg, level="INFO"):
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


def _slog(message, level="INFO", meta=None):
    """Write to structured log if available."""
    try:
        sys.path.insert(0, str(WORKSPACE / "scripts"))
        from structured_log import slog
        slog(message, level=level, source="market_trends", meta=meta)
    except Exception:
        tlog(f"{message} {json.dumps(meta) if meta else ''}", level)


def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def days_between(d1, d2=None):
    if not d1:
        return 999
    d2 = d2 or TODAY
    if isinstance(d1, str):
        d1 = parse_date(d1)
    if isinstance(d2, str):
        d2 = parse_date(d2)
    if not d1 or not d2:
        return 999
    return (d2 - d1).days


# ── INDUSTRY DETECTION ─────────────────────────────────

def _detect_industry(org_name, notes=""):
    """Heuristic industry classifier based on company name and notes."""
    text = f"{org_name} {notes}".lower()
    industry_signals = {
        "technology": ["tech", "software", "digital", "it ", "saas", "ai ", "data", "cloud", "cyber"],
        "healthcare": ["health", "medical", "pharma", "hospital", "clinic", "nemocnic", "léka"],
        "finance": ["bank", "financ", "invest", "capital", "pojišt", "insurance", "banka"],
        "manufacturing": ["manufactur", "výrob", "industr", "factory", "auto", "motor"],
        "services": ["consult", "service", "advisory", "porad", "agency", "agentur"],
        "retail": ["retail", "store", "shop", "e-commerce", "obchod", "eshop"],
        "education": ["school", "university", "akadem", "vzdělá", "training", "edu"],
        "energy": ["energy", "energi", "solar", "renew", "elektr", "tepláren"],
        "transport": ["transport", "logistic", "doprav", "dpm", "fleet"],
        "food": ["food", "restaurant", "gastro", "potrav", "kofola", "nápoj"],
        "real_estate": ["real estate", "realit", "property", "construct", "staveb"],
        "government": ["government", "municipal", "ministry", "muzeum", "národní"],
    }
    for industry, signals in industry_signals.items():
        for signal in signals:
            if signal in text:
                return industry
    return "other"


# ── TREND DETECTOR ─────────────────────────────────────

class TrendDetector:
    """Analyzes deal velocity, win rates, conversion rates, deal sizes, and activity patterns."""

    def __init__(self, base_url, api_token):
        self.base = base_url
        self.token = api_token
        self._deals_cache = None
        self._activities_cache = None

    def _fetch_all_deals(self):
        if self._deals_cache is not None:
            return self._deals_cache
        tlog("Fetching all deals for trend analysis...")
        self._deals_cache = paged_get(self.base, self.token, "/api/v1/deals", {"status": "all_not_deleted"})
        tlog(f"Fetched {len(self._deals_cache)} deals")
        return self._deals_cache

    def _fetch_activities(self):
        if self._activities_cache is not None:
            return self._activities_cache
        tlog("Fetching activities for trend analysis...")
        self._activities_cache = paged_get(self.base, self.token, "/api/v1/activities")
        tlog(f"Fetched {len(self._activities_cache)} activities")
        return self._activities_cache

    def _enrich_deal(self, deal):
        """Add computed fields to a deal dict."""
        org_name = deal.get("org_name") or deal.get("title", "")
        return {
            "id": deal.get("id"),
            "title": deal.get("title", ""),
            "org": deal.get("org_name") or "",
            "value": deal.get("value") or 0,
            "currency": deal.get("currency", "CZK"),
            "status": deal.get("status", ""),
            "stage_id": deal.get("stage_id"),
            "stage_name": STAGE_NAMES.get(deal.get("stage_id"), ""),
            "add_time": (deal.get("add_time") or "")[:10],
            "close_time": (deal.get("close_time") or "")[:10],
            "won_time": (deal.get("won_time") or "")[:10],
            "lost_time": (deal.get("lost_time") or "")[:10],
            "stage_change_time": (deal.get("stage_change_time") or "")[:10],
            "last_activity": deal.get("last_activity_date") or "",
            "lost_reason": deal.get("lost_reason") or "",
            "industry": _detect_industry(org_name),
            "activities_count": deal.get("activities_count") or 0,
            "email_messages_count": deal.get("email_messages_count") or 0,
        }

    def _deals_in_window(self, deals, field, days_back):
        """Filter deals to those with `field` within the last N days."""
        cutoff = (TODAY - timedelta(days=days_back)).isoformat()
        return [d for d in deals if d.get(field, "") >= cutoff and d.get(field, "") != ""]

    def velocity_by_industry(self):
        """Deal velocity changes by industry — compares recent vs historical."""
        deals = [self._enrich_deal(d) for d in self._fetch_all_deals()]
        won = [d for d in deals if d["status"] == "won" and d["won_time"]]

        trends = {}
        by_industry = defaultdict(list)
        for d in won:
            add_dt = parse_date(d["add_time"])
            won_dt = parse_date(d["won_time"])
            if add_dt and won_dt:
                cycle_days = (won_dt - add_dt).days
                if 0 < cycle_days < 365:
                    by_industry[d["industry"]].append({
                        "cycle_days": cycle_days,
                        "won_date": d["won_time"],
                        "value": d["value"],
                    })

        for industry, entries in by_industry.items():
            if len(entries) < 2:
                continue

            entries.sort(key=lambda x: x["won_date"])
            midpoint = len(entries) // 2
            old_half = entries[:midpoint]
            new_half = entries[midpoint:]

            old_avg = statistics.mean([e["cycle_days"] for e in old_half])
            new_avg = statistics.mean([e["cycle_days"] for e in new_half])

            if old_avg > 0:
                change_pct = ((new_avg - old_avg) / old_avg) * 100
            else:
                change_pct = 0

            direction = "accelerating" if change_pct < -10 else "decelerating" if change_pct > 10 else "stable"
            confidence = min(100, len(entries) * 10)

            trends[industry] = {
                "industry": industry,
                "direction": direction,
                "old_avg_days": round(old_avg, 1),
                "new_avg_days": round(new_avg, 1),
                "change_pct": round(change_pct, 1),
                "deal_count": len(entries),
                "confidence": confidence,
            }

        return trends

    def win_rate_shifts(self):
        """Win rate changes over 7d, 30d, 90d windows."""
        deals = [self._enrich_deal(d) for d in self._fetch_all_deals()]
        closed = [d for d in deals if d["status"] in ("won", "lost")]

        windows = {}
        for window_days in [7, 30, 90]:
            cutoff = (TODAY - timedelta(days=window_days)).isoformat()
            recent = [d for d in closed
                      if (d["won_time"] >= cutoff and d["won_time"])
                      or (d["lost_time"] >= cutoff and d["lost_time"])]

            won_count = sum(1 for d in recent if d["status"] == "won")
            total = len(recent)
            win_rate = (won_count / total * 100) if total > 0 else 0

            # Compare to previous equivalent window
            prev_start = (TODAY - timedelta(days=window_days * 2)).isoformat()
            prev_end = cutoff
            previous = [d for d in closed
                        if ((d["won_time"] >= prev_start and d["won_time"] < prev_end and d["won_time"])
                            or (d["lost_time"] >= prev_start and d["lost_time"] < prev_end and d["lost_time"]))]

            prev_won = sum(1 for d in previous if d["status"] == "won")
            prev_total = len(previous)
            prev_rate = (prev_won / prev_total * 100) if prev_total > 0 else 0

            shift = win_rate - prev_rate
            direction = "improving" if shift > 5 else "declining" if shift < -5 else "stable"

            windows[f"{window_days}d"] = {
                "window": f"{window_days}d",
                "current_rate": round(win_rate, 1),
                "previous_rate": round(prev_rate, 1),
                "shift": round(shift, 1),
                "direction": direction,
                "current_won": won_count,
                "current_total": total,
                "previous_won": prev_won,
                "previous_total": prev_total,
                "confidence": min(100, total * 5),
            }

        return windows

    def stage_conversion_trends(self):
        """Which stages are bottlenecks — conversion rate per stage."""
        deals = [self._enrich_deal(d) for d in self._fetch_all_deals()]
        sales_deals = [d for d in deals if d["stage_id"] in SALES_STAGES]

        stage_counts = defaultdict(int)
        for d in sales_deals:
            if d["status"] == "open":
                stage_counts[d["stage_id"]] += 1

        # Won deals passed through every stage up to their final stage
        won_deals = [d for d in deals if d["status"] == "won"]
        lost_deals = [d for d in deals if d["status"] == "lost" and d["stage_id"] in SALES_STAGES]

        # Conversion = deals that moved past a stage vs deals that stayed/were lost at that stage
        conversions = {}
        for sid, (stage_name, order) in sorted(SALES_STAGES.items(), key=lambda x: x[1][1]):
            # Deals currently at this stage
            at_stage = stage_counts.get(sid, 0)

            # Deals lost at this stage
            lost_at = sum(1 for d in lost_deals if d["stage_id"] == sid)

            # Won deals that passed through this stage
            passed = sum(1 for d in won_deals
                         if d.get("stage_id") and STAGE_ORDER.get(d["stage_id"], 0) >= order)

            # Deals that entered this stage = current + passed + lost
            entered = at_stage + passed + lost_at
            if entered > 0:
                conversion_rate = ((entered - lost_at) / entered) * 100
            else:
                conversion_rate = 0

            is_bottleneck = conversion_rate < 70 and entered >= 3
            conversions[str(sid)] = {
                "stage_id": sid,
                "stage_name": stage_name,
                "order": order,
                "current_count": at_stage,
                "entered": entered,
                "lost_at": lost_at,
                "passed_through": passed,
                "conversion_rate": round(conversion_rate, 1),
                "is_bottleneck": is_bottleneck,
                "confidence": min(100, entered * 5),
            }

        return conversions

    def deal_size_trends(self):
        """Average deal size trends by industry."""
        deals = [self._enrich_deal(d) for d in self._fetch_all_deals()]
        valued = [d for d in deals if d["value"] > 0 and d["status"] in ("won", "open")]

        by_industry = defaultdict(list)
        for d in valued:
            by_industry[d["industry"]].append({
                "value": d["value"],
                "add_time": d["add_time"],
                "status": d["status"],
            })

        trends = {}
        for industry, entries in by_industry.items():
            if len(entries) < 2:
                continue

            entries.sort(key=lambda x: x["add_time"])
            midpoint = len(entries) // 2
            old_half = entries[:midpoint]
            new_half = entries[midpoint:]

            old_avg = statistics.mean([e["value"] for e in old_half])
            new_avg = statistics.mean([e["value"] for e in new_half])

            if old_avg > 0:
                change_pct = ((new_avg - old_avg) / old_avg) * 100
            else:
                change_pct = 0

            direction = "growing" if change_pct > 15 else "shrinking" if change_pct < -15 else "stable"

            trends[industry] = {
                "industry": industry,
                "direction": direction,
                "old_avg_value": round(old_avg),
                "new_avg_value": round(new_avg),
                "change_pct": round(change_pct, 1),
                "deal_count": len(entries),
                "total_value": sum(e["value"] for e in entries),
                "confidence": min(100, len(entries) * 10),
            }

        return trends

    def activity_pattern_changes(self):
        """Analyze if touchpoints-to-close are changing."""
        deals = [self._enrich_deal(d) for d in self._fetch_all_deals()]
        won = [d for d in deals if d["status"] == "won" and d["activities_count"] > 0]

        if len(won) < 4:
            return {"status": "insufficient_data", "won_count": len(won)}

        won.sort(key=lambda x: x["won_time"])
        midpoint = len(won) // 2
        old_half = won[:midpoint]
        new_half = won[midpoint:]

        old_avg_acts = statistics.mean([d["activities_count"] for d in old_half])
        new_avg_acts = statistics.mean([d["activities_count"] for d in new_half])

        old_avg_emails = statistics.mean([d["email_messages_count"] for d in old_half])
        new_avg_emails = statistics.mean([d["email_messages_count"] for d in new_half])

        if old_avg_acts > 0:
            act_change = ((new_avg_acts - old_avg_acts) / old_avg_acts) * 100
        else:
            act_change = 0

        return {
            "status": "analyzed",
            "old_avg_activities": round(old_avg_acts, 1),
            "new_avg_activities": round(new_avg_acts, 1),
            "activity_change_pct": round(act_change, 1),
            "old_avg_emails": round(old_avg_emails, 1),
            "new_avg_emails": round(new_avg_emails, 1),
            "direction": "more_touches" if act_change > 20 else "fewer_touches" if act_change < -20 else "stable",
            "won_analyzed": len(won),
            "confidence": min(100, len(won) * 5),
        }

    def full_analysis(self):
        """Run all trend analyses and return combined results."""
        tlog("Running full trend analysis...")
        _slog("Starting full market trend analysis")

        results = {
            "velocity_by_industry": self.velocity_by_industry(),
            "win_rate_shifts": self.win_rate_shifts(),
            "stage_conversions": self.stage_conversion_trends(),
            "deal_size_trends": self.deal_size_trends(),
            "activity_patterns": self.activity_pattern_changes(),
            "analyzed_at": NOW.isoformat(),
        }

        tlog(f"Full analysis complete: {len(results['velocity_by_industry'])} industries, "
             f"{len(results['stage_conversions'])} stages analyzed")
        _slog("Full market trend analysis complete", meta={
            "industries": len(results["velocity_by_industry"]),
            "stages": len(results["stage_conversions"]),
        })
        return results


# ── SEASONAL ANALYZER ──────────────────────────────────

class SeasonalAnalyzer:
    """Day-of-week, monthly, and quarter-end pattern detection."""

    def __init__(self, base_url, api_token):
        self.base = base_url
        self.token = api_token

    def _fetch_won_deals(self):
        deals = paged_get(self.base, self.token, "/api/v1/deals", {"status": "won"})
        return deals

    def _fetch_all_deals(self):
        return paged_get(self.base, self.token, "/api/v1/deals", {"status": "all_not_deleted"})

    def day_of_week_patterns(self):
        """When do deals move fastest? Analyze stage changes by day of week."""
        deals = self._fetch_all_deals()
        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

        # Won deals by day of week
        won_by_day = defaultdict(int)
        stage_changes_by_day = defaultdict(int)

        for deal in deals:
            won_time = deal.get("won_time")
            if won_time and deal.get("status") == "won":
                dt = parse_date(won_time)
                if dt:
                    won_by_day[dt.weekday()] += 1

            stage_change = deal.get("stage_change_time")
            if stage_change:
                dt = parse_date(stage_change)
                if dt:
                    stage_changes_by_day[dt.weekday()] += 1

        results = {}
        total_won = sum(won_by_day.values())
        total_changes = sum(stage_changes_by_day.values())

        for day_idx in range(7):
            won = won_by_day.get(day_idx, 0)
            changes = stage_changes_by_day.get(day_idx, 0)
            results[day_names[day_idx]] = {
                "day": day_names[day_idx],
                "day_index": day_idx,
                "won_deals": won,
                "won_pct": round(won / total_won * 100, 1) if total_won > 0 else 0,
                "stage_changes": changes,
                "change_pct": round(changes / total_changes * 100, 1) if total_changes > 0 else 0,
            }

        # Find best day
        if total_won > 0:
            best_day = max(results.values(), key=lambda x: x["won_deals"])
            results["_best_day_for_closing"] = best_day["day"]
        if total_changes > 0:
            most_active = max(results.values(), key=lambda x: x.get("stage_changes", 0)
                             if isinstance(x, dict) and "stage_changes" in x else 0)
            if isinstance(most_active, dict) and "day" in most_active:
                results["_most_active_day"] = most_active["day"]

        return results

    def monthly_patterns(self):
        """Monthly deal flow patterns."""
        deals = self._fetch_all_deals()
        month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                       "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

        won_by_month = defaultdict(int)
        lost_by_month = defaultdict(int)
        added_by_month = defaultdict(int)
        value_by_month = defaultdict(float)

        for deal in deals:
            add_time = deal.get("add_time")
            if add_time:
                dt = parse_date(add_time)
                if dt:
                    added_by_month[dt.month] += 1

            if deal.get("status") == "won":
                won_time = deal.get("won_time")
                if won_time:
                    dt = parse_date(won_time)
                    if dt:
                        won_by_month[dt.month] += 1
                        value_by_month[dt.month] += deal.get("value") or 0

            if deal.get("status") == "lost":
                lost_time = deal.get("lost_time")
                if lost_time:
                    dt = parse_date(lost_time)
                    if dt:
                        lost_by_month[dt.month] += 1

        results = {}
        for m in range(1, 13):
            won = won_by_month.get(m, 0)
            lost = lost_by_month.get(m, 0)
            total_closed = won + lost
            results[month_names[m - 1]] = {
                "month": month_names[m - 1],
                "month_num": m,
                "deals_added": added_by_month.get(m, 0),
                "won": won,
                "lost": lost,
                "win_rate": round(won / total_closed * 100, 1) if total_closed > 0 else 0,
                "revenue": round(value_by_month.get(m, 0)),
            }

        # Best month for revenue
        month_dicts = [v for v in results.values() if isinstance(v, dict)]
        if any(v.get("revenue", 0) > 0 for v in month_dicts):
            best_revenue = max(month_dicts, key=lambda x: x.get("revenue", 0))
            results["_best_revenue_month"] = best_revenue["month"]
            best_win = max(month_dicts, key=lambda x: x.get("win_rate", 0)
                          if x.get("won", 0) + x.get("lost", 0) >= 3 else 0)
            results["_best_win_rate_month"] = best_win["month"]

        return results

    def quarter_end_acceleration(self):
        """Detect if deals accelerate at quarter ends (months 3, 6, 9, 12)."""
        deals = self._fetch_all_deals()

        qe_months = {3, 6, 9, 12}
        qe_won = []
        non_qe_won = []

        for deal in deals:
            if deal.get("status") != "won":
                continue
            won_time = deal.get("won_time")
            add_time = deal.get("add_time")
            if not won_time or not add_time:
                continue

            won_dt = parse_date(won_time)
            add_dt = parse_date(add_time)
            if not won_dt or not add_dt:
                continue

            cycle = (won_dt - add_dt).days
            if cycle <= 0 or cycle > 365:
                continue

            if won_dt.month in qe_months:
                qe_won.append({"cycle": cycle, "value": deal.get("value") or 0})
            else:
                non_qe_won.append({"cycle": cycle, "value": deal.get("value") or 0})

        if not qe_won or not non_qe_won:
            return {"status": "insufficient_data"}

        qe_avg_cycle = statistics.mean([d["cycle"] for d in qe_won])
        non_qe_avg_cycle = statistics.mean([d["cycle"] for d in non_qe_won])
        qe_avg_value = statistics.mean([d["value"] for d in qe_won]) if any(d["value"] for d in qe_won) else 0
        non_qe_avg_value = statistics.mean([d["value"] for d in non_qe_won]) if any(d["value"] for d in non_qe_won) else 0

        acceleration = ((non_qe_avg_cycle - qe_avg_cycle) / non_qe_avg_cycle * 100) if non_qe_avg_cycle > 0 else 0

        return {
            "status": "analyzed",
            "quarter_end_avg_cycle": round(qe_avg_cycle, 1),
            "non_quarter_end_avg_cycle": round(non_qe_avg_cycle, 1),
            "acceleration_pct": round(acceleration, 1),
            "detected": acceleration > 15,
            "quarter_end_deals": len(qe_won),
            "non_quarter_end_deals": len(non_qe_won),
            "quarter_end_avg_value": round(qe_avg_value),
            "non_quarter_end_avg_value": round(non_qe_avg_value),
            "confidence": min(100, (len(qe_won) + len(non_qe_won)) * 3),
        }

    def full_seasonal(self):
        """Run all seasonal analyses."""
        tlog("Running seasonal analysis...")
        return {
            "day_of_week": self.day_of_week_patterns(),
            "monthly": self.monthly_patterns(),
            "quarter_end": self.quarter_end_acceleration(),
            "analyzed_at": NOW.isoformat(),
        }


# ── COMPETITOR SIGNAL DETECTOR ─────────────────────────

class CompetitorSignalDetector:
    """Detect competitive pressure from lost deals, notes, and stall patterns."""

    def __init__(self, base_url, api_token):
        self.base = base_url
        self.token = api_token

    def lost_deal_analysis(self):
        """Categorize loss reasons and detect competitor mentions."""
        deals = paged_get(self.base, self.token, "/api/v1/deals", {"status": "lost"})
        tlog(f"Analyzing {len(deals)} lost deals for competitor signals")

        loss_categories = defaultdict(list)
        competitor_mentions = []
        timeline = defaultdict(int)

        for deal in deals:
            lost_reason = (deal.get("lost_reason") or "").lower()
            title = deal.get("title") or ""
            org = deal.get("org_name") or ""
            lost_time = (deal.get("lost_time") or "")[:7]  # YYYY-MM

            if lost_time:
                timeline[lost_time] += 1

            # Categorize loss reason
            categorized = False
            for category, keywords in LOSS_REASON_KEYWORDS.items():
                for kw in keywords:
                    if kw in lost_reason:
                        loss_categories[category].append({
                            "deal": title,
                            "org": org,
                            "reason": deal.get("lost_reason", ""),
                            "lost_time": lost_time,
                            "value": deal.get("value") or 0,
                        })
                        categorized = True
                        break
                if categorized:
                    break

            if not categorized and lost_reason:
                loss_categories["other"].append({
                    "deal": title,
                    "org": org,
                    "reason": deal.get("lost_reason", ""),
                    "lost_time": lost_time,
                    "value": deal.get("value") or 0,
                })

            # Check for competitor mentions
            for kw in COMPETITOR_KEYWORDS:
                if kw in lost_reason:
                    competitor_mentions.append({
                        "deal": title,
                        "org": org,
                        "reason": deal.get("lost_reason", ""),
                        "keyword": kw,
                        "lost_time": lost_time,
                    })
                    break

        # Also scan notes for competitor mentions
        note_signals = self._scan_notes_for_competitors()

        category_summary = {}
        for cat, entries in loss_categories.items():
            total_value = sum(e["value"] for e in entries)
            category_summary[cat] = {
                "count": len(entries),
                "total_value_lost": total_value,
                "recent": [e for e in entries if e["lost_time"] >= (TODAY - timedelta(days=90)).strftime("%Y-%m")],
            }

        return {
            "total_lost_deals": len(deals),
            "loss_categories": category_summary,
            "competitor_mentions": competitor_mentions,
            "note_signals": note_signals,
            "loss_timeline": dict(sorted(timeline.items())),
        }

    def _scan_notes_for_competitors(self):
        """Scan deal notes for competitor keywords."""
        signals = []
        try:
            notes = paged_get(self.base, self.token, "/api/v1/notes")
            for note in notes:
                content = (note.get("content") or "").lower()
                # Strip HTML tags
                content_clean = re.sub(r'<[^>]+>', ' ', content)
                for kw in COMPETITOR_KEYWORDS:
                    if kw in content_clean:
                        signals.append({
                            "deal_id": note.get("deal_id"),
                            "org_id": note.get("org_id"),
                            "keyword": kw,
                            "snippet": content_clean[:200].strip(),
                            "add_time": (note.get("add_time") or "")[:10],
                        })
                        break
        except Exception as e:
            tlog(f"Note scan failed: {e}", "WARN")

        return signals

    def deal_stall_patterns(self):
        """Detect deals that stall, which may indicate competitive evaluation."""
        velocity_data = {}
        if VELOCITY_FILE.exists():
            try:
                velocity_data = json.loads(VELOCITY_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass

        stall_signals = []
        for deal_id, deal in velocity_data.get("deals", {}).items():
            if deal.get("velocity_status") == "stalling":
                days = deal.get("days_in_stage", 0)
                ratio = deal.get("velocity_ratio", 0)
                if ratio >= 2.0:
                    stall_signals.append({
                        "deal_id": deal.get("id"),
                        "title": deal.get("title", ""),
                        "org": deal.get("org", ""),
                        "stage": deal.get("stage_name", ""),
                        "days_in_stage": days,
                        "velocity_ratio": ratio,
                        "risk_level": "high" if ratio >= 3.0 else "medium",
                        "possible_cause": "competitive_evaluation" if days > 21 else "internal_delay",
                    })

        stall_signals.sort(key=lambda x: x["velocity_ratio"], reverse=True)
        return {
            "stall_signals": stall_signals,
            "high_risk_count": sum(1 for s in stall_signals if s["risk_level"] == "high"),
            "medium_risk_count": sum(1 for s in stall_signals if s["risk_level"] == "medium"),
        }

    def full_competitor_analysis(self):
        """Full competitive signal analysis."""
        tlog("Running competitor signal detection...")
        return {
            "lost_deals": self.lost_deal_analysis(),
            "stall_patterns": self.deal_stall_patterns(),
            "analyzed_at": NOW.isoformat(),
        }


# ── TREND REPORT ───────────────────────────────────────

class TrendReport:
    """Generate weekly trend reports with confidence scores and recommendations."""

    def __init__(self, base_url, api_token):
        self.base = base_url
        self.token = api_token
        self.detector = TrendDetector(base_url, api_token)
        self.seasonal = SeasonalAnalyzer(base_url, api_token)
        self.competitor = CompetitorSignalDetector(base_url, api_token)

    def generate(self):
        """Generate full weekly trend report."""
        tlog("Generating weekly trend report...")
        _slog("Generating weekly trend report")

        analysis = self.detector.full_analysis()
        seasonal = self.seasonal.full_seasonal()
        competitor = self.competitor.full_competitor_analysis()

        # Build active trends list
        active_trends = self._extract_active_trends(analysis, seasonal, competitor)

        # Generate recommendations
        recommendations = self._generate_recommendations(active_trends, analysis, seasonal, competitor)

        # Try Ollama narrative
        narrative = self._generate_narrative(active_trends, recommendations)

        report = {
            "report_date": TODAY.isoformat(),
            "report_week": TODAY.isocalendar()[1],
            "analysis": analysis,
            "seasonal": seasonal,
            "competitor": competitor,
            "active_trends": active_trends,
            "recommendations": recommendations,
            "narrative": narrative,
            "generated_at": NOW.isoformat(),
        }

        # Save
        TRENDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        TRENDS_FILE.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        tlog(f"Report saved to {TRENDS_FILE}")
        _slog("Weekly trend report generated", meta={
            "trends": len(active_trends),
            "recommendations": len(recommendations),
            "file": str(TRENDS_FILE),
        })

        return report

    def _extract_active_trends(self, analysis, seasonal, competitor):
        """Extract all active/notable trends with confidence scores."""
        trends = []

        # Velocity trends
        for industry, data in analysis.get("velocity_by_industry", {}).items():
            if data["direction"] != "stable":
                trends.append({
                    "type": "velocity",
                    "industry": industry,
                    "direction": data["direction"],
                    "detail": f"{industry}: {data['direction']} ({data['change_pct']:+.1f}%) — "
                              f"{data['old_avg_days']}d -> {data['new_avg_days']}d avg cycle",
                    "confidence": data["confidence"],
                    "impact": "high" if abs(data["change_pct"]) > 30 else "medium",
                })

        # Win rate shifts
        for window, data in analysis.get("win_rate_shifts", {}).items():
            if data["direction"] != "stable":
                trends.append({
                    "type": "win_rate",
                    "window": window,
                    "direction": data["direction"],
                    "detail": f"Win rate {data['direction']} over {window}: "
                              f"{data['previous_rate']:.1f}% -> {data['current_rate']:.1f}% ({data['shift']:+.1f}pp)",
                    "confidence": data["confidence"],
                    "impact": "high" if abs(data["shift"]) > 15 else "medium",
                })

        # Stage bottlenecks
        for sid, data in analysis.get("stage_conversions", {}).items():
            if data.get("is_bottleneck"):
                trends.append({
                    "type": "bottleneck",
                    "stage": data["stage_name"],
                    "detail": f"Bottleneck at {data['stage_name']}: {data['conversion_rate']:.1f}% conversion "
                              f"({data['lost_at']} lost of {data['entered']} entered)",
                    "confidence": data["confidence"],
                    "impact": "high",
                })

        # Deal size changes
        for industry, data in analysis.get("deal_size_trends", {}).items():
            if data["direction"] != "stable":
                trends.append({
                    "type": "deal_size",
                    "industry": industry,
                    "direction": data["direction"],
                    "detail": f"{industry} deal sizes {data['direction']}: "
                              f"{data['old_avg_value']:,.0f} -> {data['new_avg_value']:,.0f} CZK "
                              f"({data['change_pct']:+.1f}%)",
                    "confidence": data["confidence"],
                    "impact": "medium",
                })

        # Activity pattern changes
        act = analysis.get("activity_patterns", {})
        if act.get("status") == "analyzed" and act.get("direction") != "stable":
            trends.append({
                "type": "activity_pattern",
                "direction": act["direction"],
                "detail": f"Touchpoints to close: {act['direction']} "
                          f"({act['old_avg_activities']:.0f} -> {act['new_avg_activities']:.0f} activities, "
                          f"{act['activity_change_pct']:+.1f}%)",
                "confidence": act["confidence"],
                "impact": "medium",
            })

        # Quarter-end acceleration
        qe = seasonal.get("quarter_end", {})
        if qe.get("detected"):
            trends.append({
                "type": "seasonal",
                "detail": f"Quarter-end acceleration detected: deals close "
                          f"{qe['acceleration_pct']:.0f}% faster in Q-end months "
                          f"({qe['quarter_end_avg_cycle']:.0f}d vs {qe['non_quarter_end_avg_cycle']:.0f}d)",
                "confidence": qe["confidence"],
                "impact": "medium",
            })

        # Competitor pressure
        comp = competitor.get("lost_deals", {})
        competitor_count = len(comp.get("competitor_mentions", []))
        if competitor_count > 0:
            trends.append({
                "type": "competitor",
                "detail": f"Competitor pressure: {competitor_count} deals mention competitors in loss reason",
                "confidence": min(100, competitor_count * 15),
                "impact": "high" if competitor_count >= 3 else "medium",
            })

        stalls = competitor.get("stall_patterns", {})
        high_risk = stalls.get("high_risk_count", 0)
        if high_risk > 0:
            trends.append({
                "type": "competitive_stall",
                "detail": f"{high_risk} deals severely stalling (3x+ avg stage time) — possible competitive evaluation",
                "confidence": min(100, high_risk * 20),
                "impact": "high",
            })

        # Sort by confidence then impact
        impact_order = {"high": 0, "medium": 1, "low": 2}
        trends.sort(key=lambda t: (impact_order.get(t.get("impact", "medium"), 1), -t.get("confidence", 0)))

        return trends

    def _generate_recommendations(self, trends, analysis, seasonal, competitor):
        """Generate actionable recommendations for each trend."""
        recs = []

        for trend in trends:
            rec = {"trend": trend["detail"], "confidence": trend["confidence"]}

            if trend["type"] == "velocity" and trend.get("direction") == "decelerating":
                rec["action"] = (f"Review {trend.get('industry', '')} deals for blockers. "
                                 "Consider faster follow-up cadence and executive engagement earlier.")
                rec["priority"] = "P1"

            elif trend["type"] == "velocity" and trend.get("direction") == "accelerating":
                rec["action"] = (f"Double down on {trend.get('industry', '')} — deals are closing faster. "
                                 "Increase prospecting in this segment.")
                rec["priority"] = "P2"

            elif trend["type"] == "win_rate" and trend.get("direction") == "declining":
                rec["action"] = ("Audit recent losses. Check if messaging/pricing needs updating. "
                                 "Review objection handling playbook.")
                rec["priority"] = "P1"

            elif trend["type"] == "win_rate" and trend.get("direction") == "improving":
                rec["action"] = "Winning formula working — document what changed and standardize."
                rec["priority"] = "P3"

            elif trend["type"] == "bottleneck":
                rec["action"] = (f"Stage '{trend.get('stage', '')}' is leaking deals. "
                                 "Review lost deals at this stage. Consider adding a qualification step or "
                                 "changing the pitch for this stage.")
                rec["priority"] = "P1"

            elif trend["type"] == "deal_size" and trend.get("direction") == "shrinking":
                rec["action"] = (f"Deal sizes shrinking in {trend.get('industry', '')}. "
                                 "Review pricing, consider bundling, or shift to higher-value segments.")
                rec["priority"] = "P2"

            elif trend["type"] == "deal_size" and trend.get("direction") == "growing":
                rec["action"] = (f"Deal sizes growing in {trend.get('industry', '')} — "
                                 "good signal. Allocate more sales capacity here.")
                rec["priority"] = "P3"

            elif trend["type"] == "activity_pattern" and trend.get("direction") == "more_touches":
                rec["action"] = ("Deals need more touchpoints to close. Review content/collateral. "
                                 "Buyers may need more education or trust-building.")
                rec["priority"] = "P2"

            elif trend["type"] == "competitor":
                rec["action"] = ("Build competitive battle cards. Train team on differentiation. "
                                 "Identify which competitors appear most often.")
                rec["priority"] = "P1"

            elif trend["type"] == "competitive_stall":
                rec["action"] = ("Proactively address stalling deals — call to confirm status. "
                                 "Offer exclusive terms or pilot extension to regain momentum.")
                rec["priority"] = "P1"

            elif trend["type"] == "seasonal":
                rec["action"] = ("Plan pipeline push before quarter-end months. "
                                 "Front-load proposals to ride the acceleration wave.")
                rec["priority"] = "P2"

            else:
                rec["action"] = "Monitor this trend — act if it continues next week."
                rec["priority"] = "P3"

            recs.append(rec)

        return recs

    def _generate_narrative(self, trends, recommendations):
        """Use Ollama to generate a human-readable narrative summary."""
        if not trends:
            return "No significant trends detected this week."

        # Build prompt
        trend_lines = "\n".join(f"- {t['detail']} (confidence: {t['confidence']}%)" for t in trends[:8])
        rec_lines = "\n".join(f"- [{r['priority']}] {r['action']}" for r in recommendations[:5])

        prompt = (
            f"You are a sales operations analyst. Write a concise 3-5 sentence summary of these market trends "
            f"for a sales team weekly briefing. Be direct and actionable.\n\n"
            f"Trends:\n{trend_lines}\n\n"
            f"Top Recommendations:\n{rec_lines}\n\n"
            f"Write the summary:"
        )

        try:
            data = json.dumps({
                "model": "llama3.1:8b",
                "prompt": prompt,
                "stream": False,
                "options": {"num_predict": 300, "temperature": 0.3},
            }).encode()
            req = urllib.request.Request(
                "http://localhost:11434/api/generate",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            resp = urllib.request.urlopen(req, timeout=60)
            result = json.loads(resp.read())
            narrative = result.get("response", "").strip()
            if narrative:
                tlog("Ollama narrative generated")
                return narrative
        except Exception as e:
            tlog(f"Ollama narrative failed (non-fatal): {e}", "WARN")

        # Fallback: simple summary
        high_impact = [t for t in trends if t.get("impact") == "high"]
        if high_impact:
            return (f"This week: {len(trends)} active trends detected, "
                    f"{len(high_impact)} high-impact. "
                    f"Top concern: {high_impact[0]['detail']}. "
                    f"See recommendations for action items.")
        return f"This week: {len(trends)} trends detected, all medium impact. Pipeline stable overall."

    def load_existing(self):
        """Load the most recent report from file."""
        if TRENDS_FILE.exists():
            try:
                return json.loads(TRENDS_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return None


# ── CLI DISPLAY ────────────────────────────────────────

def _display_trends(report):
    """Pretty-print active trends."""
    trends = report.get("active_trends", [])
    if not trends:
        print("\n  No active trends detected. Run 'analyze' to refresh data.")
        return

    print("=" * 72)
    print("  ACTIVE MARKET TRENDS")
    print(f"  Report date: {report.get('report_date', '?')}")
    print("=" * 72)

    for i, t in enumerate(trends, 1):
        impact = t.get("impact", "?").upper()
        conf = t.get("confidence", 0)
        bar = "#" * (conf // 10) + "-" * (10 - conf // 10)
        ttype = t.get("type", "?")
        print(f"\n  [{i}] ({impact}) {t['detail']}")
        print(f"      Type: {ttype} | Confidence: [{bar}] {conf}%")

    print(f"\n  Total: {len(trends)} active trends")
    print("=" * 72)


def _display_seasonal(report):
    """Pretty-print seasonal patterns."""
    seasonal = report.get("seasonal", {})
    if not seasonal:
        print("\n  No seasonal data. Run 'analyze' first.")
        return

    print("=" * 72)
    print("  SEASONAL PATTERNS")
    print("=" * 72)

    # Day of week
    dow = seasonal.get("day_of_week", {})
    best_day = dow.pop("_best_day_for_closing", None)
    active_day = dow.pop("_most_active_day", None)

    print("\n  DAY-OF-WEEK PATTERNS")
    print("  " + "-" * 68)
    print(f"  {'Day':<12} {'Won':>6} {'Win%':>7} {'Stage Changes':>14} {'Change%':>9}")
    print("  " + "-" * 68)
    for day_name in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]:
        d = dow.get(day_name)
        if not d:
            continue
        marker = " <--" if day_name == best_day else ""
        print(f"  {d['day']:<12} {d['won_deals']:>6} {d['won_pct']:>6.1f}% {d['stage_changes']:>14} "
              f"{d['change_pct']:>8.1f}%{marker}")

    if best_day:
        print(f"\n  Best day for closing: {best_day}")
    if active_day:
        print(f"  Most active day: {active_day}")

    # Monthly
    monthly = seasonal.get("monthly", {})
    best_rev = monthly.pop("_best_revenue_month", None)
    best_wr = monthly.pop("_best_win_rate_month", None)

    print("\n  MONTHLY PATTERNS")
    print("  " + "-" * 68)
    print(f"  {'Month':<6} {'Added':>7} {'Won':>5} {'Lost':>6} {'WinRate':>9} {'Revenue':>12}")
    print("  " + "-" * 68)
    for m_name in ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]:
        m = monthly.get(m_name)
        if not m:
            continue
        rev_str = f"{m['revenue']:,.0f}" if m["revenue"] > 0 else "-"
        print(f"  {m['month']:<6} {m['deals_added']:>7} {m['won']:>5} {m['lost']:>6} "
              f"{m['win_rate']:>8.1f}% {rev_str:>12}")

    if best_rev:
        print(f"\n  Best revenue month: {best_rev}")
    if best_wr:
        print(f"  Best win rate month: {best_wr}")

    # Quarter-end
    qe = seasonal.get("quarter_end", {})
    if qe.get("status") == "analyzed":
        print("\n  QUARTER-END ACCELERATION")
        print("  " + "-" * 68)
        print(f"  Q-end avg cycle:     {qe['quarter_end_avg_cycle']:.1f} days ({qe['quarter_end_deals']} deals)")
        print(f"  Non-Q-end avg cycle: {qe['non_quarter_end_avg_cycle']:.1f} days ({qe['non_quarter_end_deals']} deals)")
        print(f"  Acceleration:        {qe['acceleration_pct']:+.1f}%")
        print(f"  Detected:            {'YES' if qe['detected'] else 'No'}")

    print("=" * 72)


def _display_report(report):
    """Pretty-print the full weekly report."""
    print("=" * 72)
    print("  WEEKLY MARKET TREND REPORT")
    print(f"  Week {report.get('report_week', '?')} | {report.get('report_date', '?')}")
    print("=" * 72)

    # Narrative
    narrative = report.get("narrative", "")
    if narrative:
        print(f"\n  EXECUTIVE SUMMARY")
        print("  " + "-" * 68)
        # Word-wrap narrative at 68 chars
        words = narrative.split()
        line = "  "
        for word in words:
            if len(line) + len(word) + 1 > 70:
                print(line)
                line = "  " + word
            else:
                line += " " + word if line.strip() else "  " + word
        if line.strip():
            print(line)

    # Active trends
    trends = report.get("active_trends", [])
    if trends:
        print(f"\n  ACTIVE TRENDS ({len(trends)})")
        print("  " + "-" * 68)
        for i, t in enumerate(trends, 1):
            impact = t.get("impact", "?").upper()
            conf = t.get("confidence", 0)
            print(f"  {i}. [{impact}] {t['detail']}")
            print(f"     Confidence: {conf}%")

    # Recommendations
    recs = report.get("recommendations", [])
    if recs:
        print(f"\n  RECOMMENDATIONS ({len(recs)})")
        print("  " + "-" * 68)
        for i, r in enumerate(recs, 1):
            print(f"  {i}. [{r.get('priority', '?')}] {r['action']}")

    # Competitor signals
    comp = report.get("competitor", {})
    lost = comp.get("lost_deals", {})
    cats = lost.get("loss_categories", {})
    if cats:
        print(f"\n  LOSS REASON BREAKDOWN")
        print("  " + "-" * 68)
        for cat, data in sorted(cats.items(), key=lambda x: -x[1].get("count", 0)):
            recent = len(data.get("recent", []))
            print(f"  {cat:<20} {data['count']:>4} total | {recent:>3} recent (90d) | "
                  f"Lost value: {data['total_value_lost']:>10,.0f} CZK")

    mentions = lost.get("competitor_mentions", [])
    if mentions:
        print(f"\n  COMPETITOR MENTIONS ({len(mentions)})")
        print("  " + "-" * 68)
        for m in mentions[:10]:
            print(f"  {m['deal'][:30]:<32} \"{m['keyword']}\" in: {m['reason'][:40]}")

    stalls = comp.get("stall_patterns", {})
    stall_list = stalls.get("stall_signals", [])
    if stall_list:
        print(f"\n  COMPETITIVE STALL RISK ({len(stall_list)} deals)")
        print("  " + "-" * 68)
        print(f"  {'Deal':<25} {'Stage':<18} {'Days':>5} {'Ratio':>6} {'Risk'}")
        print("  " + "-" * 68)
        for s in stall_list[:10]:
            print(f"  {s['title'][:24]:<25} {s['stage'][:17]:<18} "
                  f"{s['days_in_stage']:>5} {s['velocity_ratio']:>5.1f}x {s['risk_level']}")

    print(f"\n  Generated: {report.get('generated_at', '?')}")
    print(f"  Saved to: {TRENDS_FILE}")
    print("=" * 72)


# ── CLI ────────────────────────────────────────────────

def main():
    env = load_env(ENV_PATH)
    base = env.get("PIPEDRIVE_BASE_URL", "").rstrip("/")
    token = env.get("PIPEDRIVE_API_TOKEN", "")

    if not base or not token:
        print("ERROR: Missing PIPEDRIVE_BASE_URL or PIPEDRIVE_API_TOKEN in .secrets/pipedrive.env")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: market_trends.py [analyze|trends|seasonal|report]")
        print("  analyze   — full market analysis (velocity, win rates, conversions, sizes)")
        print("  trends    — show active trends from last analysis")
        print("  seasonal  — seasonal patterns (day-of-week, monthly, quarter-end)")
        print("  report    — generate full weekly trend report")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "analyze":
        print("Running full market trend analysis...\n")
        detector = TrendDetector(base, token)
        results = detector.full_analysis()

        print(f"Velocity trends: {len(results['velocity_by_industry'])} industries")
        for industry, data in results["velocity_by_industry"].items():
            if data["direction"] != "stable":
                print(f"  {industry}: {data['direction']} ({data['change_pct']:+.1f}%)")

        print(f"\nWin rate shifts:")
        for window, data in results["win_rate_shifts"].items():
            arrow = "^" if data["direction"] == "improving" else "v" if data["direction"] == "declining" else "="
            print(f"  {window}: {data['current_rate']:.1f}% ({arrow} {data['shift']:+.1f}pp)")

        print(f"\nStage conversions:")
        for sid, data in sorted(results["stage_conversions"].items(),
                                key=lambda x: x[1].get("order", 0)):
            marker = " ** BOTTLENECK" if data.get("is_bottleneck") else ""
            print(f"  {data['stage_name']:<22} {data['conversion_rate']:>5.1f}% "
                  f"({data['entered']} entered, {data['lost_at']} lost){marker}")

        print(f"\nDeal size trends:")
        for industry, data in results["deal_size_trends"].items():
            if data["direction"] != "stable":
                print(f"  {industry}: {data['direction']} ({data['change_pct']:+.1f}%)")

        act = results["activity_patterns"]
        if act.get("status") == "analyzed":
            print(f"\nActivity patterns: {act['direction']} "
                  f"({act['old_avg_activities']:.0f} -> {act['new_avg_activities']:.0f} avg touches)")

        print(f"\nAnalysis complete. Run 'report' for full report with recommendations.")

    elif cmd == "trends":
        report = TrendReport(base, token).load_existing()
        if not report:
            print("No existing report found. Run 'report' first to generate one.")
            sys.exit(1)
        _display_trends(report)

    elif cmd == "seasonal":
        # Check for existing report first
        report = TrendReport(base, token).load_existing()
        if report and report.get("seasonal"):
            _display_seasonal(report)
        else:
            print("Running seasonal analysis (this fetches from Pipedrive)...\n")
            analyzer = SeasonalAnalyzer(base, token)
            seasonal = analyzer.full_seasonal()
            _display_seasonal({"seasonal": seasonal})

    elif cmd == "report":
        print("Generating weekly market trend report...\n")
        print("This will fetch deals, activities, and notes from Pipedrive.")
        print("Please wait...\n")

        reporter = TrendReport(base, token)
        report = reporter.generate()
        _display_report(report)

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: market_trends.py [analyze|trends|seasonal|report]")
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
