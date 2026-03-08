#!/usr/bin/env python3
"""
Deal Velocity Tracker & Follow-Up Cadence Engine
==================================================
Tracks how long deals spend in each pipeline stage, identifies stalling/hot deals,
and manages stage-specific follow-up cadences with auto-scheduling.

Integrates with:
  - Pipedrive API (deal data, stage history, activities)
  - Agent Bus (pipeline.deal_stalling, pipeline.deal_hot, cadence.action_due)
  - Agent Learning (outcome tracking when cadence actions complete)

Usage:
  python3 scripts/deal_velocity.py track            # Track all deals
  python3 scripts/deal_velocity.py velocity         # Show velocity dashboard
  python3 scripts/deal_velocity.py stalling         # List stalling deals
  python3 scripts/deal_velocity.py cadence <deal>   # Show cadence for deal
  python3 scripts/deal_velocity.py due              # Today's due actions
  python3 scripts/deal_velocity.py schedule <deal> <stage>  # Schedule cadence
"""

import json
import sys
import time
import statistics
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
ENV_PATH = WORKSPACE / ".secrets" / "pipedrive.env"
VELOCITY_FILE = WORKSPACE / "pipedrive" / "deal_velocity.json"
CADENCE_FILE = WORKSPACE / "pipedrive" / "cadences.json"
LOG_FILE = WORKSPACE / "logs" / "deal-velocity.log"

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

STAGE_ID_BY_NAME = {name.lower(): sid for sid, (name, _) in SALES_STAGES.items()}


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


def vlog(msg, level="INFO"):
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
        return (d2 - d1).days
    except (ValueError, TypeError):
        return 999


# ── FOLLOW-UP CADENCES ────────────────────────────────

CADENCE_TEMPLATES = {
    "interested_qualified": {
        "label": "After Initial Contact",
        "steps": [
            {"day": 1, "action": "thank_you", "desc": "Send thank-you email with brief value summary"},
            {"day": 3, "action": "value_prop", "desc": "Share core value proposition + 1 stat"},
            {"day": 7, "action": "case_study", "desc": "Send relevant case study / social proof"},
            {"day": 14, "action": "check_in", "desc": "Friendly check-in, offer to answer questions"},
        ],
    },
    "demo_scheduled": {
        "label": "After Demo",
        "steps": [
            {"day": 1, "action": "recap", "desc": "Send demo recap + key takeaways"},
            {"day": 3, "action": "roi_calc", "desc": "Share ROI calculation / business case"},
            {"day": 7, "action": "proposal", "desc": "Send proposal or next-step offer"},
            {"day": 14, "action": "decision_nudge", "desc": "Decision nudge — any blockers?"},
        ],
    },
    "proposal_made": {
        "label": "After Proposal",
        "steps": [
            {"day": 2, "action": "qa_offer", "desc": "Offer to walk through proposal / Q&A"},
            {"day": 5, "action": "deadline_reminder", "desc": "Gentle deadline / timeline reminder"},
            {"day": 10, "action": "final_nudge", "desc": "Final nudge — last call before reprioritizing"},
        ],
    },
    "win_recovery": {
        "label": "Win Recovery / Nurture",
        "steps": [
            {"day": 30, "action": "check_in_30", "desc": "30-day check-in — how's onboarding?"},
            {"day": 60, "action": "upsell_60", "desc": "60-day upsell — additional modules?"},
            {"day": 90, "action": "referral_ask", "desc": "90-day referral ask — who else benefits?"},
        ],
    },
}

STAGE_TO_CADENCE = {
    7: "interested_qualified",
    8: "demo_scheduled",
    28: "demo_scheduled",
    9: "proposal_made",
    10: "proposal_made",
    12: "win_recovery",
    29: "win_recovery",
    11: "win_recovery",
}


# ── DEAL VELOCITY TRACKER ────────────────────────────

class DealVelocityTracker:
    """Track how long each deal spends in every pipeline stage."""

    def __init__(self, base_url, api_token):
        self.base = base_url
        self.token = api_token
        self.velocity_data = self._load_velocity()

    def _load_velocity(self):
        if VELOCITY_FILE.exists():
            try:
                return json.loads(VELOCITY_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {"deals": {}, "stage_stats": {}, "last_updated": None}

    def _save_velocity(self):
        VELOCITY_FILE.parent.mkdir(exist_ok=True)
        self.velocity_data["last_updated"] = NOW.isoformat()
        VELOCITY_FILE.write_text(json.dumps(self.velocity_data, indent=2, ensure_ascii=False))

    def track_all_deals(self):
        """Pull all open sales deals and compute velocity metrics."""
        vlog("Fetching open deals for velocity tracking...")
        deals = paged_get(self.base, self.token, "/api/v1/deals", {"status": "open"})
        vlog(f"Fetched {len(deals)} open deals")

        sales_deals = [d for d in deals if d.get("stage_id") in SALES_STAGES]
        vlog(f"Sales pipeline deals: {len(sales_deals)}")

        tracked = {}
        for deal in sales_deals:
            deal_id = str(deal["id"])
            stage_id = deal.get("stage_id")
            stage_name = SALES_STAGES.get(stage_id, ("Unknown", 0))[0]
            stage_order = SALES_STAGES.get(stage_id, ("Unknown", 0))[1]

            add_time = deal.get("add_time", "")[:10]
            stage_change = deal.get("stage_change_time", "")
            stage_change_date = stage_change[:10] if stage_change else add_time
            last_activity = deal.get("last_activity_date") or ""
            next_activity = deal.get("next_activity_date") or ""

            days_in_stage = days_between(stage_change_date)
            days_in_pipeline = days_between(add_time)

            owner = deal.get("user_id")
            if isinstance(owner, dict):
                owner_name = owner.get("name", "?")
            else:
                owner_name = "?"

            tracked[deal_id] = {
                "id": deal["id"],
                "title": deal.get("title", ""),
                "org": deal.get("org_name") or "",
                "value": deal.get("value") or 0,
                "currency": deal.get("currency", "CZK"),
                "stage_id": stage_id,
                "stage_name": stage_name,
                "stage_order": stage_order,
                "owner": owner_name,
                "add_time": add_time,
                "stage_change_time": stage_change_date,
                "last_activity": last_activity,
                "next_activity": next_activity,
                "days_in_stage": days_in_stage,
                "days_in_pipeline": days_in_pipeline,
            }

        self.velocity_data["deals"] = tracked

        stage_stats = self._compute_stage_stats(tracked)
        self.velocity_data["stage_stats"] = stage_stats

        for deal_id, deal in tracked.items():
            avg = stage_stats.get(str(deal["stage_id"]), {}).get("avg", 0)
            if avg > 0:
                ratio = deal["days_in_stage"] / avg
                deal["velocity_ratio"] = round(ratio, 2)
                if ratio >= 1.5:
                    deal["velocity_status"] = "stalling"
                elif ratio <= 0.5:
                    deal["velocity_status"] = "hot"
                else:
                    deal["velocity_status"] = "normal"
            else:
                deal["velocity_ratio"] = 0
                deal["velocity_status"] = "unknown"

        self._save_velocity()
        vlog(f"Velocity tracked: {len(tracked)} deals")

        stalling = [d for d in tracked.values() if d["velocity_status"] == "stalling"]
        hot = [d for d in tracked.values() if d["velocity_status"] == "hot"]
        vlog(f"Stalling: {len(stalling)}, Hot: {len(hot)}")

        self._publish_events(stalling, hot)

        return tracked

    def _compute_stage_stats(self, tracked):
        """Calculate avg/median/stddev days per stage."""
        by_stage = {}
        for deal in tracked.values():
            sid = str(deal["stage_id"])
            by_stage.setdefault(sid, []).append(deal["days_in_stage"])

        stats = {}
        for sid, days_list in by_stage.items():
            clean = [d for d in days_list if d < 999]
            if not clean:
                continue
            stage_name = SALES_STAGES.get(int(sid), ("Unknown", 0))[0]
            avg = statistics.mean(clean)
            med = statistics.median(clean)
            std = statistics.stdev(clean) if len(clean) > 1 else 0
            stats[sid] = {
                "stage_name": stage_name,
                "deal_count": len(clean),
                "avg": round(avg, 1),
                "median": round(med, 1),
                "stddev": round(std, 1),
                "min": min(clean),
                "max": max(clean),
            }
        return stats

    def get_deal_velocity(self, deal_id):
        """Get velocity data for a specific deal."""
        return self.velocity_data.get("deals", {}).get(str(deal_id))

    def stage_averages(self):
        """Return stage average times."""
        return self.velocity_data.get("stage_stats", {})

    def stalling_deals(self):
        """Return deals moving slower than 1.5x stage average."""
        return [
            d for d in self.velocity_data.get("deals", {}).values()
            if d.get("velocity_status") == "stalling"
        ]

    def hot_deals(self):
        """Return deals moving faster than 0.5x stage average."""
        return [
            d for d in self.velocity_data.get("deals", {}).values()
            if d.get("velocity_status") == "hot"
        ]

    def _publish_events(self, stalling, hot):
        """Publish events to agent bus."""
        try:
            sys.path.insert(0, str(WORKSPACE / "scripts"))
            from agent_bus import get_bus
            bus = get_bus()

            for deal in stalling:
                bus.publish(
                    source="deal_velocity",
                    topic="pipeline.deal_stalling",
                    payload={
                        "deal_id": deal["id"],
                        "title": deal["title"],
                        "org": deal["org"],
                        "stage": deal["stage_name"],
                        "days_in_stage": deal["days_in_stage"],
                        "velocity_ratio": deal["velocity_ratio"],
                        "recommended": _recommend_action(deal),
                    },
                    priority="P1",
                )

            for deal in hot:
                bus.publish(
                    source="deal_velocity",
                    topic="pipeline.deal_hot",
                    payload={
                        "deal_id": deal["id"],
                        "title": deal["title"],
                        "org": deal["org"],
                        "stage": deal["stage_name"],
                        "days_in_stage": deal["days_in_stage"],
                        "velocity_ratio": deal["velocity_ratio"],
                    },
                    priority="P2",
                )

            if stalling or hot:
                bus.route_messages()

            vlog(f"Published {len(stalling)} stalling + {len(hot)} hot events to bus")
        except Exception as e:
            vlog(f"Bus publish failed (non-fatal): {e}", "WARN")


def _recommend_action(deal):
    """Generate a recommended action for a stalling deal."""
    days = deal["days_in_stage"]
    stage = deal["stage_name"]

    if stage == "Interested/Qualified":
        if days > 14:
            return "Re-engage with a value prop email or cold call"
        return "Schedule initial call / demo"
    elif stage == "Demo Scheduled":
        if days > 21:
            return "Reschedule demo — send alternate times"
        return "Confirm demo details, send prep materials"
    elif stage in ("Ongoing Discussion", "Proposal made"):
        if days > 14:
            return "Send decision nudge + deadline"
        return "Follow up on open questions"
    elif stage == "Negotiation":
        return "Escalate internally — check if pricing/terms need revision"
    elif stage == "Pilot":
        if days > 30:
            return "Review pilot results, push for conversion"
        return "Check in on pilot progress"
    return "Review and take next action"


# ── FOLLOW-UP CADENCE ENGINE ─────────────────────────

class FollowUpCadence:
    """Stage-specific follow-up cadence management."""

    def __init__(self, base_url, api_token):
        self.base = base_url
        self.token = api_token
        self.cadences = self._load()

    def _load(self):
        if CADENCE_FILE.exists():
            try:
                return json.loads(CADENCE_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save(self):
        CADENCE_FILE.parent.mkdir(exist_ok=True)
        CADENCE_FILE.write_text(json.dumps(self.cadences, indent=2, ensure_ascii=False))

    def schedule_cadence(self, deal_id, stage_key, anchor_date=None):
        """Schedule a follow-up cadence for a deal entering a stage.

        stage_key: stage_id (int) or cadence template name (str)
        anchor_date: date string to anchor the cadence from (default: today)
        """
        if isinstance(stage_key, int):
            template_name = STAGE_TO_CADENCE.get(stage_key)
        else:
            template_name = stage_key.lower().replace(" ", "_")

        template = CADENCE_TEMPLATES.get(template_name)
        if not template:
            vlog(f"No cadence template for: {stage_key}", "WARN")
            return None

        anchor = anchor_date or TODAY.isoformat()
        try:
            anchor_dt = datetime.strptime(anchor[:10], "%Y-%m-%d").date()
        except (ValueError, TypeError):
            anchor_dt = TODAY

        deal_key = str(deal_id)
        steps = []
        for step in template["steps"]:
            due_date = (anchor_dt + timedelta(days=step["day"])).isoformat()
            steps.append({
                "day": step["day"],
                "action": step["action"],
                "desc": step["desc"],
                "due_date": due_date,
                "status": "pending",
                "completed_at": None,
                "skipped_reason": None,
            })

        self.cadences[deal_key] = {
            "deal_id": int(deal_id),
            "template": template_name,
            "label": template["label"],
            "anchor_date": anchor,
            "scheduled_at": NOW.isoformat(),
            "steps": steps,
            "status": "active",
            "escalated": False,
        }

        self._save()
        vlog(f"Cadence scheduled: deal {deal_id} → {template_name} ({len(steps)} steps)")
        return self.cadences[deal_key]

    def check_due_actions(self, check_skip=True):
        """Return all cadence actions due today or overdue.

        If check_skip is True, checks Pipedrive for recent activity
        and auto-skips steps where the prospect has responded.
        """
        due = []
        today_str = TODAY.isoformat()

        for deal_key, cadence in self.cadences.items():
            if cadence.get("status") != "active":
                continue

            if check_skip:
                self._auto_skip_if_responded(cadence)

            all_done = True
            for step in cadence["steps"]:
                if step["status"] == "pending":
                    all_done = False
                    if step["due_date"] <= today_str:
                        due.append({
                            "deal_id": cadence["deal_id"],
                            "deal_key": deal_key,
                            "template": cadence["template"],
                            "action": step["action"],
                            "desc": step["desc"],
                            "due_date": step["due_date"],
                            "overdue_days": days_between(step["due_date"]),
                        })

            if all_done and not cadence.get("escalated"):
                pending_count = sum(1 for s in cadence["steps"] if s["status"] == "pending")
                completed_count = sum(1 for s in cadence["steps"] if s["status"] == "completed")
                if completed_count == 0 and pending_count == 0:
                    skipped_all = all(s["status"] == "skipped" for s in cadence["steps"])
                    if not skipped_all:
                        cadence["status"] = "completed"
                elif pending_count == 0:
                    cadence["status"] = "completed"

        due.sort(key=lambda x: (x["due_date"], -x.get("overdue_days", 0)))

        self._save()

        if due:
            self._publish_due_events(due)

        return due

    def _auto_skip_if_responded(self, cadence):
        """Check last activity date on deal — skip pending steps if prospect responded."""
        deal_id = cadence["deal_id"]
        try:
            resp = api_request(self.base, self.token, "GET", f"/api/v1/deals/{deal_id}")
            if resp and resp.get("success") and resp.get("data"):
                deal_data = resp["data"]
                last_activity = deal_data.get("last_activity_date") or ""
                if last_activity:
                    last_dt = datetime.strptime(last_activity[:10], "%Y-%m-%d").date()
                    for step in cadence["steps"]:
                        if step["status"] != "pending":
                            continue
                        step_due = datetime.strptime(step["due_date"], "%Y-%m-%d").date()
                        if last_dt >= step_due:
                            step["status"] = "skipped"
                            step["skipped_reason"] = f"Prospect active on {last_activity}"
        except Exception:
            pass

    def mark_completed(self, deal_id, step_action):
        """Mark a specific cadence step as completed."""
        deal_key = str(deal_id)
        cadence = self.cadences.get(deal_key)
        if not cadence:
            return None

        for step in cadence["steps"]:
            if step["action"] == step_action and step["status"] == "pending":
                step["status"] = "completed"
                step["completed_at"] = NOW.isoformat()
                self._save()
                vlog(f"Cadence step completed: deal {deal_id} / {step_action}")

                self._record_learning(deal_id, step_action, cadence["template"])
                return step

        return None

    def get_cadence_status(self, deal_id):
        """Get full cadence status for a deal."""
        return self.cadences.get(str(deal_id))

    def escalate_stale(self):
        """Escalate deals where full cadence completed with no engagement."""
        escalated = []
        for deal_key, cadence in self.cadences.items():
            if cadence.get("escalated") or cadence.get("status") != "active":
                continue

            steps = cadence["steps"]
            all_done = all(s["status"] in ("completed", "skipped") for s in steps)
            any_skipped_for_response = any(
                s["status"] == "skipped" and s.get("skipped_reason", "").startswith("Prospect active")
                for s in steps
            )

            if all_done and not any_skipped_for_response:
                cadence["escalated"] = True
                cadence["status"] = "escalated"
                escalated.append(cadence)
                vlog(f"Cadence escalated: deal {cadence['deal_id']} — no engagement after full cadence")

        if escalated:
            self._save()
        return escalated

    def _publish_due_events(self, due_actions):
        """Publish cadence.action_due events."""
        try:
            sys.path.insert(0, str(WORKSPACE / "scripts"))
            from agent_bus import get_bus
            bus = get_bus()

            for action in due_actions[:10]:
                bus.publish(
                    source="deal_velocity",
                    topic="cadence.action_due",
                    payload=action,
                    priority="P1" if action.get("overdue_days", 0) > 3 else "P2",
                )
            bus.route_messages()
        except Exception as e:
            vlog(f"Bus publish for cadence failed (non-fatal): {e}", "WARN")

    def _record_learning(self, deal_id, step_action, template):
        """Record cadence completion to agent learning."""
        try:
            sys.path.insert(0, str(WORKSPACE / "scripts"))
            from agent_learning import OutcomeTracker
            tracker = OutcomeTracker()
            tracker.record_outcome(
                "task_completed_fast",
                agents=["deal_velocity"],
                context={"deal_id": deal_id, "step": step_action, "template": template},
            )
        except Exception as e:
            vlog(f"Learning record failed (non-fatal): {e}", "WARN")

    def completion_rates(self):
        """Calculate cadence completion stats."""
        total = len(self.cadences)
        if total == 0:
            return {"total": 0}

        active = sum(1 for c in self.cadences.values() if c["status"] == "active")
        completed = sum(1 for c in self.cadences.values() if c["status"] == "completed")
        escalated = sum(1 for c in self.cadences.values() if c["status"] == "escalated")

        total_steps = 0
        completed_steps = 0
        skipped_steps = 0
        for cadence in self.cadences.values():
            for step in cadence["steps"]:
                total_steps += 1
                if step["status"] == "completed":
                    completed_steps += 1
                elif step["status"] == "skipped":
                    skipped_steps += 1

        return {
            "total_cadences": total,
            "active": active,
            "completed": completed,
            "escalated": escalated,
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "skipped_steps": skipped_steps,
            "step_completion_rate": round(completed_steps / total_steps * 100, 1) if total_steps else 0,
        }


# ── VELOCITY DASHBOARD ───────────────────────────────

class VelocityDashboard:
    """Terminal-printable velocity + cadence summary."""

    def __init__(self, tracker: DealVelocityTracker, cadence: FollowUpCadence):
        self.tracker = tracker
        self.cadence = cadence

    def render(self):
        lines = []
        lines.append("=" * 70)
        lines.append("  DEAL VELOCITY & CADENCE DASHBOARD")
        lines.append(f"  {NOW.strftime('%Y-%m-%d %H:%M')}")
        lines.append("=" * 70)

        self._render_stage_averages(lines)
        self._render_stalling(lines)
        self._render_hot(lines)
        self._render_due_actions(lines)
        self._render_cadence_rates(lines)

        lines.append("=" * 70)
        return "\n".join(lines)

    def _render_stage_averages(self, lines):
        stats = self.tracker.stage_averages()
        if not stats:
            lines.append("\n  No stage velocity data yet. Run 'track' first.")
            return

        lines.append("\n  PIPELINE STAGE AVERAGES (days)")
        lines.append("  " + "-" * 66)
        lines.append(f"  {'Stage':<25} {'Avg':>6} {'Med':>6} {'StdDev':>7} {'Min':>5} {'Max':>5} {'Deals':>6}")
        lines.append("  " + "-" * 66)

        sorted_stages = sorted(stats.items(), key=lambda x: SALES_STAGES.get(int(x[0]), ("", 99))[1])
        for sid, s in sorted_stages:
            lines.append(
                f"  {s['stage_name']:<25} {s['avg']:>6.1f} {s['median']:>6.1f} "
                f"{s['stddev']:>7.1f} {s['min']:>5} {s['max']:>5} {s['deal_count']:>6}"
            )

    def _render_stalling(self, lines):
        stalling = self.tracker.stalling_deals()
        if not stalling:
            lines.append("\n  STALLING DEALS: None (all deals within normal velocity)")
            return

        stalling.sort(key=lambda x: x["velocity_ratio"], reverse=True)
        lines.append(f"\n  STALLING DEALS ({len(stalling)} deals > 1.5x avg stage time)")
        lines.append("  " + "-" * 66)
        lines.append(f"  {'Deal':<25} {'Stage':<18} {'Days':>5} {'Ratio':>6} {'Action'}")
        lines.append("  " + "-" * 66)

        for d in stalling[:15]:
            action = _recommend_action(d)
            lines.append(
                f"  {d['title'][:24]:<25} {d['stage_name'][:17]:<18} "
                f"{d['days_in_stage']:>5} {d['velocity_ratio']:>5.1f}x {action[:35]}"
            )
        if len(stalling) > 15:
            lines.append(f"  ... +{len(stalling) - 15} more")

    def _render_hot(self, lines):
        hot = self.tracker.hot_deals()
        if not hot:
            lines.append("\n  HOT DEALS: None identified")
            return

        hot.sort(key=lambda x: x["velocity_ratio"])
        lines.append(f"\n  HOT DEALS ({len(hot)} deals < 0.5x avg stage time)")
        lines.append("  " + "-" * 66)
        lines.append(f"  {'Deal':<25} {'Stage':<18} {'Days':>5} {'Ratio':>6} {'Value':>12}")
        lines.append("  " + "-" * 66)

        for d in hot[:10]:
            val = f"{d['value']:,.0f} {d['currency']}" if d['value'] else "-"
            lines.append(
                f"  {d['title'][:24]:<25} {d['stage_name'][:17]:<18} "
                f"{d['days_in_stage']:>5} {d['velocity_ratio']:>5.1f}x {val:>12}"
            )

    def _render_due_actions(self, lines):
        due = self.cadence.check_due_actions(check_skip=False)
        if not due:
            lines.append("\n  TODAY'S CADENCE ACTIONS: None due")
            return

        lines.append(f"\n  TODAY'S CADENCE ACTIONS ({len(due)} due)")
        lines.append("  " + "-" * 66)
        lines.append(f"  {'Deal ID':>8} {'Action':<18} {'Due':>12} {'Overdue':>8} {'Task'}")
        lines.append("  " + "-" * 66)

        for a in due[:15]:
            overdue = f"+{a['overdue_days']}d" if a['overdue_days'] > 0 else "today"
            lines.append(
                f"  {a['deal_id']:>8} {a['action'][:17]:<18} {a['due_date']:>12} "
                f"{overdue:>8} {a['desc'][:30]}"
            )
        if len(due) > 15:
            lines.append(f"  ... +{len(due) - 15} more")

    def _render_cadence_rates(self, lines):
        rates = self.cadence.completion_rates()
        if rates.get("total_cadences", 0) == 0:
            lines.append("\n  CADENCE STATS: No cadences scheduled yet")
            return

        lines.append(f"\n  CADENCE COMPLETION RATES")
        lines.append("  " + "-" * 66)
        lines.append(f"  Total cadences: {rates['total_cadences']}")
        lines.append(f"  Active: {rates['active']} | Completed: {rates['completed']} | Escalated: {rates['escalated']}")
        lines.append(f"  Steps: {rates['completed_steps']}/{rates['total_steps']} completed ({rates['step_completion_rate']}%)")
        lines.append(f"  Skipped (prospect responded): {rates['skipped_steps']}")


# ── CLI ───────────────────────────────────────────────

def main():
    env = load_env(ENV_PATH)
    base = env.get("PIPEDRIVE_BASE_URL", "").rstrip("/")
    token = env.get("PIPEDRIVE_API_TOKEN", "")

    if not base or not token:
        print("ERROR: Missing PIPEDRIVE_BASE_URL or PIPEDRIVE_API_TOKEN in .secrets/pipedrive.env")
        sys.exit(1)

    tracker = DealVelocityTracker(base, token)
    cadence = FollowUpCadence(base, token)
    dashboard = VelocityDashboard(tracker, cadence)

    if len(sys.argv) < 2:
        print("Usage: deal_velocity.py [track|velocity|stalling|cadence <deal>|due|schedule <deal> <stage>]")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "track":
        print("Tracking deal velocity...")
        deals = tracker.track_all_deals()
        stalling = tracker.stalling_deals()
        hot = tracker.hot_deals()
        print(f"\nTracked {len(deals)} sales deals")
        print(f"Stalling: {len(stalling)} | Hot: {len(hot)} | Normal: {len(deals) - len(stalling) - len(hot)}")
        print(f"\nVelocity data saved to {VELOCITY_FILE}")

    elif cmd == "velocity":
        output = dashboard.render()
        print(output)

    elif cmd == "stalling":
        stalling = tracker.stalling_deals()
        if not stalling:
            print("No stalling deals found. Run 'track' first if data is empty.")
            return

        print(f"\nSTALLING DEALS ({len(stalling)})")
        print("-" * 80)
        for d in sorted(stalling, key=lambda x: x["velocity_ratio"], reverse=True):
            action = _recommend_action(d)
            print(
                f"  [{d['id']}] {d['title'][:30]} | {d['stage_name']} | "
                f"{d['days_in_stage']}d ({d['velocity_ratio']:.1f}x avg)"
            )
            print(f"         -> {action}")
            print()

    elif cmd == "cadence":
        if len(sys.argv) < 3:
            print("Usage: deal_velocity.py cadence <deal_id>")
            sys.exit(1)
        deal_id = sys.argv[2]
        status = cadence.get_cadence_status(deal_id)
        if not status:
            print(f"No cadence found for deal {deal_id}")
            print("Use 'schedule <deal_id> <stage>' to create one")
            return

        print(f"\nCADENCE: {status['label']} (deal {deal_id})")
        print(f"Template: {status['template']} | Status: {status['status']}")
        print(f"Anchored: {status['anchor_date']} | Scheduled: {status['scheduled_at'][:10]}")
        print("-" * 60)
        for step in status["steps"]:
            icon = {"pending": "[ ]", "completed": "[x]", "skipped": "[-]"}.get(step["status"], "[?]")
            extra = ""
            if step["status"] == "completed" and step["completed_at"]:
                extra = f" (done {step['completed_at'][:10]})"
            elif step["status"] == "skipped" and step["skipped_reason"]:
                extra = f" ({step['skipped_reason']})"
            elif step["status"] == "pending":
                overdue = days_between(step["due_date"])
                if overdue > 0:
                    extra = f" OVERDUE +{overdue}d"
                elif overdue == 0:
                    extra = " DUE TODAY"
            print(f"  {icon} Day {step['day']:>3}: {step['action']:<20} due {step['due_date']}{extra}")
            print(f"         {step['desc']}")

    elif cmd == "due":
        due = cadence.check_due_actions()
        if not due:
            print("No cadence actions due today.")
            return

        print(f"\nDUE CADENCE ACTIONS ({len(due)})")
        print("-" * 70)
        for a in due:
            overdue = f"+{a['overdue_days']}d overdue" if a['overdue_days'] > 0 else "TODAY"
            print(f"  Deal {a['deal_id']} | {a['action']:<18} | {overdue}")
            print(f"    {a['desc']}")
            print()

    elif cmd == "schedule":
        if len(sys.argv) < 4:
            print("Usage: deal_velocity.py schedule <deal_id> <stage>")
            print("\nAvailable stages/templates:")
            for key, tmpl in CADENCE_TEMPLATES.items():
                print(f"  {key:<25} — {tmpl['label']}")
            print("\nOr use stage IDs:", ", ".join(f"{sid} ({n})" for sid, (n, _) in SALES_STAGES.items()))
            sys.exit(1)

        deal_id = sys.argv[2]
        stage = sys.argv[3]

        try:
            stage_key = int(stage)
        except ValueError:
            stage_key = stage

        result = cadence.schedule_cadence(deal_id, stage_key)
        if result:
            print(f"Cadence scheduled: {result['label']}")
            print(f"Steps:")
            for step in result["steps"]:
                print(f"  Day {step['day']:>3}: {step['action']:<20} due {step['due_date']}")
                print(f"         {step['desc']}")
        else:
            print(f"Could not schedule cadence for stage: {stage}")
            print("Available templates:", ", ".join(CADENCE_TEMPLATES.keys()))

    elif cmd == "complete":
        if len(sys.argv) < 4:
            print("Usage: deal_velocity.py complete <deal_id> <step_action>")
            sys.exit(1)
        deal_id = sys.argv[2]
        step_action = sys.argv[3]
        result = cadence.mark_completed(deal_id, step_action)
        if result:
            print(f"Marked '{step_action}' as completed for deal {deal_id}")
        else:
            print(f"Step '{step_action}' not found or already completed for deal {deal_id}")

    elif cmd == "escalate":
        escalated = cadence.escalate_stale()
        if escalated:
            print(f"Escalated {len(escalated)} cadences with no engagement:")
            for c in escalated:
                print(f"  Deal {c['deal_id']} — {c['template']}")
        else:
            print("No cadences to escalate.")

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: deal_velocity.py [track|velocity|stalling|cadence <deal>|due|schedule <deal> <stage>|complete <deal> <step>|escalate]")
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
