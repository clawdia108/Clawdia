#!/usr/bin/env python3
"""
Anomaly Detector — Statistical anomaly detection across the Clawdia system
============================================================================
Monitors deal velocity, agent timing, costs, pipeline value, activity patterns,
and bus health. Uses z-scores, moving averages, and trend detection to flag
anomalies and publish them to the agent bus.

Integrates with:
  - Deal Velocity Tracker (pipedrive/deal_velocity.json)
  - Time Tracker (logs/time-tracker.json)
  - Agent Bus (bus/ directory stats, dead-letter monitoring)
  - Structured Logger (slog)
  - Pipedrive API (activity data)

Usage:
  python3 scripts/anomaly_detector.py scan        # Run full anomaly scan
  python3 scripts/anomaly_detector.py status      # Show active anomalies
  python3 scripts/anomaly_detector.py history     # Anomaly history
  python3 scripts/anomaly_detector.py thresholds  # Show/adjust thresholds
"""

import json
import math
import sys
import time
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path

BASE = Path("/Users/josefhofman/Clawdia")
VELOCITY_FILE = BASE / "pipedrive" / "deal_velocity.json"
TRACKER_FILE = BASE / "logs" / "time-tracker.json"
BUS_DIR = BASE / "bus"
DEAD_LETTER = BUS_DIR / "dead-letter"
EVENTS_LOG = BASE / "logs" / "events.jsonl"
BUS_LOG = BASE / "logs" / "bus.log"
ANOMALY_FILE = BASE / "logs" / "anomalies.json"
THRESHOLD_FILE = BASE / "logs" / "anomaly-thresholds.json"
LOG_FILE = BASE / "logs" / "anomaly-detector.log"

TODAY = date.today()
NOW = datetime.now()

# Try importing structured logger and agent bus
sys.path.insert(0, str(BASE / "scripts"))
from lib.notifications import notify_telegram

try:
    from structured_log import slog
    from agent_bus import AgentBus, publish as bus_publish
    HAS_BUS = True
except ImportError:
    HAS_BUS = False

    def slog(message, level="INFO", source="anomaly_detector", meta=None):
        pass

    def bus_publish(source, topic, payload=None, priority="P2"):
        pass


def alog(msg, level="INFO"):
    ts = NOW.strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] [{level}] {msg}\n")


# ── STATISTICAL ENGINE ───────────────────────────────────

class StatisticalEngine:
    """Core statistical computations for anomaly detection."""

    @staticmethod
    def moving_average(values, window=7):
        """Calculate moving average over a window. Returns list of averages."""
        if not values or window < 1:
            return []
        results = []
        for i in range(len(values)):
            start = max(0, i - window + 1)
            chunk = values[start:i + 1]
            results.append(sum(chunk) / len(chunk))
        return results

    @staticmethod
    def z_score(value, mean, stddev):
        """Compute z-score. Returns 0 if stddev is 0."""
        if stddev == 0:
            return 0.0
        return (value - mean) / stddev

    @staticmethod
    def mean(values):
        if not values:
            return 0.0
        return sum(values) / len(values)

    @staticmethod
    def stddev(values):
        """Population standard deviation."""
        if len(values) < 2:
            return 0.0
        avg = sum(values) / len(values)
        variance = sum((x - avg) ** 2 for x in values) / len(values)
        return math.sqrt(variance)

    @staticmethod
    def percentile(values, p):
        """Calculate the p-th percentile (0-100)."""
        if not values:
            return 0.0
        sorted_v = sorted(values)
        k = (p / 100) * (len(sorted_v) - 1)
        f = math.floor(k)
        c = math.ceil(k)
        if f == c:
            return sorted_v[int(k)]
        return sorted_v[f] * (c - k) + sorted_v[c] * (k - f)

    @staticmethod
    def trend_direction(values, min_points=3):
        """Detect trend: 'increasing', 'decreasing', or 'stable'.
        Uses simple linear regression slope."""
        if len(values) < min_points:
            return "stable"
        n = len(values)
        x_mean = (n - 1) / 2
        y_mean = sum(values) / n
        numerator = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
        denominator = sum((i - x_mean) ** 2 for i in range(n))
        if denominator == 0:
            return "stable"
        slope = numerator / denominator
        # Normalize slope relative to mean
        if y_mean == 0:
            return "stable"
        relative_slope = slope / abs(y_mean)
        if relative_slope > 0.05:
            return "increasing"
        elif relative_slope < -0.05:
            return "decreasing"
        return "stable"

    @staticmethod
    def detect_spike(values, threshold_multiplier=3.0):
        """Check if the last value is a spike relative to the rest."""
        if len(values) < 3:
            return False, 0.0
        baseline = values[:-1]
        avg = sum(baseline) / len(baseline)
        if avg == 0:
            return False, 0.0
        ratio = values[-1] / avg
        return ratio > threshold_multiplier, ratio


# ── ANOMALY EVENT ─────────────────────────────────────────

class AnomalyEvent:
    """A detected anomaly with metadata."""

    TYPES = ("deal_velocity", "agent_timing", "cost_spike",
             "pipeline_shift", "activity_gap", "bus_error")
    SEVERITIES = ("info", "warning", "critical")

    def __init__(self, anomaly_type, severity, confidence, description,
                 recommended_action, details=None):
        self.id = f"anomaly_{int(time.time())}_{id(self) % 10000:04d}"
        self.type = anomaly_type
        self.severity = severity
        self.confidence = max(0, min(100, confidence))
        self.description = description
        self.recommended_action = recommended_action
        self.details = details or {}
        self.detected_at = NOW.isoformat()
        self.acknowledged = False
        self.false_positive = False

    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "severity": self.severity,
            "confidence": self.confidence,
            "description": self.description,
            "recommended_action": self.recommended_action,
            "details": self.details,
            "detected_at": self.detected_at,
            "acknowledged": self.acknowledged,
            "false_positive": self.false_positive,
        }

    def publish_to_bus(self):
        """Publish this anomaly to the agent bus."""
        priority = {"critical": "P0", "warning": "P1", "info": "P2"}.get(
            self.severity, "P2"
        )
        try:
            bus_publish(
                source="anomaly_detector",
                topic="anomaly.detected",
                payload=self.to_dict(),
                priority=priority,
            )
            alog(f"Published anomaly to bus: {self.type} ({self.severity})")
        except Exception as e:
            alog(f"Failed to publish anomaly to bus: {e}", "ERROR")


# ── ANOMALY HISTORY ───────────────────────────────────────

class AnomalyHistory:
    """Persist and query anomaly history. Tracks false positive rates."""

    def __init__(self):
        self.file = ANOMALY_FILE
        self.data = self._load()

    def _load(self):
        try:
            if self.file.exists():
                return json.loads(self.file.read_text())
        except (json.JSONDecodeError, OSError):
            pass
        return {
            "anomalies": [],
            "stats": {
                "total_detected": 0,
                "false_positives": 0,
                "by_type": {},
                "by_severity": {},
            },
        }

    def save(self):
        self.file.parent.mkdir(exist_ok=True)
        # Keep last 500 anomalies
        if len(self.data["anomalies"]) > 500:
            self.data["anomalies"] = self.data["anomalies"][-500:]
        self.file.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))

    def add(self, event):
        entry = event.to_dict()
        self.data["anomalies"].append(entry)
        stats = self.data["stats"]
        stats["total_detected"] += 1
        stats["by_type"][event.type] = stats["by_type"].get(event.type, 0) + 1
        stats["by_severity"][event.severity] = stats["by_severity"].get(event.severity, 0) + 1
        self.save()

    def mark_false_positive(self, anomaly_id):
        for a in self.data["anomalies"]:
            if a["id"] == anomaly_id:
                a["false_positive"] = True
                self.data["stats"]["false_positives"] += 1
                self.save()
                return True
        return False

    def mark_acknowledged(self, anomaly_id):
        for a in self.data["anomalies"]:
            if a["id"] == anomaly_id:
                a["acknowledged"] = True
                self.save()
                return True
        return False

    def get_active(self):
        """Get unacknowledged anomalies from the last 48 hours."""
        cutoff = (NOW - timedelta(hours=48)).isoformat()
        return [
            a for a in self.data["anomalies"]
            if not a.get("acknowledged") and not a.get("false_positive")
            and a.get("detected_at", "") >= cutoff
        ]

    def get_recent(self, days=7):
        cutoff = (NOW - timedelta(days=days)).isoformat()
        return [
            a for a in self.data["anomalies"]
            if a.get("detected_at", "") >= cutoff
        ]

    def false_positive_rate(self):
        stats = self.data["stats"]
        total = stats.get("total_detected", 0)
        if total == 0:
            return 0.0
        return round(stats.get("false_positives", 0) / total * 100, 1)


# ── THRESHOLD MANAGER ─────────────────────────────────────

class ThresholdManager:
    """Manage and auto-adjust detection thresholds."""

    DEFAULTS = {
        "deal_velocity_z": 2.0,
        "agent_timing_multiplier": 3.0,
        "cost_spike_multiplier": 3.0,
        "pipeline_shift_z": 2.5,
        "activity_gap_days": 3,
        "bus_dead_letter_threshold": 5,
        "bus_routing_failure_rate": 0.2,
        "min_data_points": 5,
    }

    def __init__(self):
        self.file = THRESHOLD_FILE
        self.thresholds = self._load()

    def _load(self):
        try:
            if self.file.exists():
                saved = json.loads(self.file.read_text())
                merged = dict(self.DEFAULTS)
                merged.update(saved.get("thresholds", {}))
                return merged
        except (json.JSONDecodeError, OSError):
            pass
        return dict(self.DEFAULTS)

    def save(self):
        self.file.parent.mkdir(exist_ok=True)
        data = {
            "thresholds": self.thresholds,
            "updated_at": NOW.isoformat(),
        }
        self.file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def get(self, key):
        return self.thresholds.get(key, self.DEFAULTS.get(key))

    def set(self, key, value):
        self.thresholds[key] = value
        self.save()

    def auto_adjust(self, history):
        """Tighten or loosen thresholds based on false positive rate."""
        fp_rate = history.false_positive_rate()
        if fp_rate > 30:
            # Too many false positives — loosen thresholds
            for key in ("deal_velocity_z", "pipeline_shift_z"):
                self.thresholds[key] = min(self.thresholds[key] * 1.1, 4.0)
            for key in ("agent_timing_multiplier", "cost_spike_multiplier"):
                self.thresholds[key] = min(self.thresholds[key] * 1.1, 5.0)
            self.thresholds["activity_gap_days"] = min(
                self.thresholds["activity_gap_days"] + 1, 7
            )
            alog(f"Auto-loosened thresholds — FP rate was {fp_rate}%")
        elif fp_rate < 5 and history.data["stats"]["total_detected"] > 20:
            # Very few false positives — can tighten
            for key in ("deal_velocity_z", "pipeline_shift_z"):
                self.thresholds[key] = max(self.thresholds[key] * 0.95, 1.5)
            for key in ("agent_timing_multiplier", "cost_spike_multiplier"):
                self.thresholds[key] = max(self.thresholds[key] * 0.95, 2.0)
            alog(f"Auto-tightened thresholds — FP rate was {fp_rate}%")
        self.save()


# ── ANOMALY DETECTOR ──────────────────────────────────────

class AnomalyDetector:
    """Main detector — runs all anomaly checks and publishes results."""

    def __init__(self):
        self.engine = StatisticalEngine()
        self.history = AnomalyHistory()
        self.thresholds = ThresholdManager()
        self.anomalies = []

    def _emit(self, anomaly_type, severity, confidence, description,
              recommended_action, details=None):
        event = AnomalyEvent(
            anomaly_type=anomaly_type,
            severity=severity,
            confidence=confidence,
            description=description,
            recommended_action=recommended_action,
            details=details,
        )
        self.anomalies.append(event)
        self.history.add(event)
        event.publish_to_bus()
        slog(f"Anomaly: {description}", level="WARN", source="anomaly_detector",
             meta={"type": anomaly_type, "severity": severity, "confidence": confidence})
        alog(f"[{severity.upper()}] {anomaly_type}: {description}")
        return event

    # ── Deal velocity anomalies ───────────────────────────

    def check_deal_velocity(self):
        """Detect sudden speedups/slowdowns in deal progression."""
        if not VELOCITY_FILE.exists():
            alog("No deal velocity data — skipping deal_velocity check")
            return

        try:
            data = json.loads(VELOCITY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return

        deals = data.get("deals", {})
        if not deals:
            return

        # Collect days_in_stage values across all deals
        stage_times = []
        velocity_ratios = []
        for deal_id, deal in deals.items():
            dis = deal.get("days_in_stage", 0)
            vr = deal.get("velocity_ratio", 1.0)
            stage_times.append(dis)
            velocity_ratios.append(vr)

        if len(velocity_ratios) < self.thresholds.get("min_data_points"):
            return

        avg_ratio = self.engine.mean(velocity_ratios)
        std_ratio = self.engine.stddev(velocity_ratios)
        z_threshold = self.thresholds.get("deal_velocity_z")

        for deal_id, deal in deals.items():
            vr = deal.get("velocity_ratio", 1.0)
            z = self.engine.z_score(vr, avg_ratio, std_ratio)
            title = deal.get("title", f"Deal #{deal_id}")

            # Stalling anomaly (high z-score = much slower than average)
            if z > z_threshold and vr > 1.5:
                confidence = min(95, int(50 + abs(z) * 15))
                self._emit(
                    "deal_velocity", "warning", confidence,
                    f"{title} is stalling — velocity ratio {vr:.2f} "
                    f"({deal.get('days_in_stage', '?')} days in {deal.get('stage_name', '?')})",
                    f"Review {title} — consider follow-up or stage reassignment",
                    details={"deal_id": deal_id, "deal_title": title,
                             "velocity_ratio": vr, "z_score": round(z, 2),
                             "days_in_stage": deal.get("days_in_stage")},
                )

            # Unusually fast (negative z-score, deal racing through)
            elif z < -z_threshold and vr < 0.3:
                confidence = min(90, int(40 + abs(z) * 15))
                self._emit(
                    "deal_velocity", "info", confidence,
                    f"{title} is moving unusually fast — velocity ratio {vr:.2f}",
                    f"Verify {title} data — fast deals sometimes have missing stages",
                    details={"deal_id": deal_id, "deal_title": title,
                             "velocity_ratio": vr, "z_score": round(z, 2)},
                )

    # ── Agent timing anomalies ────────────────────────────

    def check_agent_timing(self):
        """Detect agents taking abnormally long to complete tasks."""
        if not TRACKER_FILE.exists():
            alog("No time tracker data — skipping agent_timing check")
            return

        try:
            tracker = json.loads(TRACKER_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return

        multiplier = self.thresholds.get("agent_timing_multiplier")

        # Check agent timings
        for name, stats in tracker.get("agent_timings", {}).items():
            avg_ms = stats.get("avg_ms", 0)
            last_ms = stats.get("last_ms", 0)

            if avg_ms > 0 and last_ms > avg_ms * multiplier:
                ratio = last_ms / avg_ms
                severity = "critical" if ratio > 5 else "warning"
                confidence = min(95, int(60 + ratio * 5))
                self._emit(
                    "agent_timing", severity, confidence,
                    f"Agent '{name}' last run took {last_ms}ms "
                    f"({ratio:.1f}x the average {avg_ms}ms)",
                    f"Check agent '{name}' for errors or external API slowdowns",
                    details={"agent": name, "last_ms": last_ms,
                             "avg_ms": avg_ms, "ratio": round(ratio, 2)},
                )

        # Check cycle time spikes
        cycles = tracker.get("cycles", [])
        if len(cycles) >= 3:
            cycle_times = [c.get("total_ms", 0) for c in cycles]
            is_spike, ratio = self.engine.detect_spike(cycle_times, multiplier)
            if is_spike:
                last_cycle = cycles[-1]
                severity = "critical" if ratio > 5 else "warning"
                confidence = min(95, int(55 + ratio * 8))
                self._emit(
                    "agent_timing", severity, confidence,
                    f"Cycle time spike: {last_cycle.get('total_ms', 0)}ms "
                    f"({ratio:.1f}x average)",
                    "Investigate last orchestrator cycle — check step timings",
                    details={"cycle_id": last_cycle.get("id"),
                             "total_ms": last_cycle.get("total_ms"),
                             "ratio": round(ratio, 2)},
                )

        # Check daily stats trend
        daily = tracker.get("daily_stats", {})
        days = sorted(daily.keys())[-7:]
        if len(days) >= 3:
            avgs = [daily[d].get("avg_ms", 0) for d in days]
            trend = self.engine.trend_direction(avgs)
            if trend == "increasing" and len(avgs) >= 3:
                increase_pct = ((avgs[-1] - avgs[0]) / max(avgs[0], 1)) * 100
                if increase_pct > 50:
                    self._emit(
                        "agent_timing", "warning", 65,
                        f"Cycle times increasing over {len(days)} days: "
                        f"{avgs[0]}ms -> {avgs[-1]}ms (+{increase_pct:.0f}%)",
                        "Performance degrading — review recent changes and resource usage",
                        details={"trend": trend, "days": days,
                                 "averages": avgs, "increase_pct": round(increase_pct, 1)},
                    )

    # ── Cost anomalies ────────────────────────────────────

    def check_cost_anomalies(self):
        """Detect daily cost exceeding 3x moving average.
        Reads cost data from events log or a dedicated cost file."""
        # Try to extract cost signals from events log
        if not EVENTS_LOG.exists():
            return

        daily_costs = defaultdict(float)
        try:
            for line in EVENTS_LOG.read_text().splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    cost = entry.get("cost") or entry.get("meta", {}).get("cost")
                    if cost is not None:
                        ts = entry.get("ts", "")[:10]
                        if ts:
                            daily_costs[ts] += float(cost)
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue
        except OSError:
            return

        if len(daily_costs) < 3:
            return

        sorted_days = sorted(daily_costs.keys())
        cost_values = [daily_costs[d] for d in sorted_days]
        multiplier = self.thresholds.get("cost_spike_multiplier")

        # 7-day moving average
        ma_7 = self.engine.moving_average(cost_values, window=7)

        if ma_7 and len(cost_values) >= 3:
            latest_cost = cost_values[-1]
            latest_ma = ma_7[-2] if len(ma_7) >= 2 else ma_7[-1]

            if latest_ma > 0 and latest_cost > latest_ma * multiplier:
                ratio = latest_cost / latest_ma
                severity = "critical" if ratio > 5 else "warning"
                confidence = min(95, int(60 + ratio * 8))
                self._emit(
                    "cost_spike", severity, confidence,
                    f"Daily cost ${latest_cost:.2f} is {ratio:.1f}x "
                    f"the 7-day average ${latest_ma:.2f}",
                    "Check for runaway API calls or misconfigured agents",
                    details={"date": sorted_days[-1], "cost": latest_cost,
                             "moving_avg": round(latest_ma, 2), "ratio": round(ratio, 2)},
                )

    # ── Pipeline value anomalies ──────────────────────────

    def check_pipeline_value(self):
        """Detect sudden large deal additions or losses."""
        if not VELOCITY_FILE.exists():
            return

        try:
            data = json.loads(VELOCITY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return

        deals = data.get("deals", {})
        if not deals:
            return

        values = []
        recent_adds = []
        for deal_id, deal in deals.items():
            val = deal.get("value", 0)
            values.append(val)
            # Check for recently added deals (last 3 days)
            add_time = deal.get("add_time", "")
            if add_time:
                try:
                    add_date = datetime.strptime(add_time[:10], "%Y-%m-%d").date()
                    if (TODAY - add_date).days <= 3:
                        recent_adds.append(deal)
                except ValueError:
                    pass

        if not values:
            return

        avg_val = self.engine.mean(values)
        std_val = self.engine.stddev(values)
        z_threshold = self.thresholds.get("pipeline_shift_z")

        # Check recent additions for outlier values
        for deal in recent_adds:
            val = deal.get("value", 0)
            if std_val > 0:
                z = self.engine.z_score(val, avg_val, std_val)
                if abs(z) > z_threshold and val > 0:
                    title = deal.get("title", "Unknown deal")
                    confidence = min(95, int(55 + abs(z) * 12))
                    self._emit(
                        "pipeline_shift", "info" if z > 0 else "warning",
                        confidence,
                        f"Large deal added: {title} — {val:,.0f} {deal.get('currency', 'CZK')} "
                        f"(z-score {z:.1f}, avg deal is {avg_val:,.0f})",
                        f"Verify deal value for {title} — it's {abs(z):.1f} std devs from average",
                        details={"deal_id": deal.get("id"), "deal_title": title,
                                 "value": val, "z_score": round(z, 2),
                                 "avg_value": round(avg_val, 2)},
                    )

        # Overall pipeline value trend
        total_pipeline = sum(values)
        p90 = self.engine.percentile(values, 90)
        if total_pipeline > 0:
            slog("Pipeline value scan", source="anomaly_detector",
                 meta={"total": total_pipeline, "deal_count": len(values),
                        "avg": round(avg_val, 2), "p90": round(p90, 2)})

    # ── Activity gap anomalies ────────────────────────────

    def check_activity_gaps(self):
        """Detect deals with no activity when they should be active."""
        if not VELOCITY_FILE.exists():
            return

        try:
            data = json.loads(VELOCITY_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return

        deals = data.get("deals", {})
        gap_days = self.thresholds.get("activity_gap_days")

        for deal_id, deal in deals.items():
            last_activity = deal.get("last_activity", "")
            if not last_activity:
                continue

            try:
                last_date = datetime.strptime(last_activity[:10], "%Y-%m-%d").date()
            except ValueError:
                continue

            days_since = (TODAY - last_date).days
            stage = deal.get("stage_name", "Unknown")
            title = deal.get("title", f"Deal #{deal_id}")

            # Only flag if deal is in an active stage (not Invoice sent)
            if stage in ("Invoice sent",):
                continue

            if days_since >= gap_days:
                severity = "critical" if days_since > gap_days * 2 else "warning"
                confidence = min(95, int(50 + days_since * 3))

                # Check if there's a next activity scheduled
                next_act = deal.get("next_activity", "")
                has_next = bool(next_act)
                if has_next:
                    try:
                        next_date = datetime.strptime(next_act[:10], "%Y-%m-%d").date()
                        if next_date >= TODAY:
                            # Has a future activity — lower severity
                            severity = "info"
                            confidence = max(30, confidence - 20)
                    except ValueError:
                        pass

                self._emit(
                    "activity_gap", severity, confidence,
                    f"No activity for {days_since} days on {title} "
                    f"(stage: {stage}, owner: {deal.get('owner', '?')})",
                    f"Schedule a follow-up for {title} — "
                    f"{'next activity: ' + next_act if has_next else 'no next activity planned'}",
                    details={"deal_id": deal_id, "deal_title": title,
                             "days_since_activity": days_since,
                             "stage": stage, "owner": deal.get("owner"),
                             "next_activity": next_act},
                )

    # ── Bus message anomalies ─────────────────────────────

    def check_bus_health(self):
        """Detect dead-letter spikes and routing failures."""
        dl_threshold = self.thresholds.get("bus_dead_letter_threshold")

        # Count dead letter messages
        dl_count = 0
        recent_dl = []
        if DEAD_LETTER.exists():
            for f in DEAD_LETTER.glob("*.json"):
                dl_count += 1
                try:
                    msg = json.loads(f.read_text())
                    created = msg.get("created_at", "")
                    if created:
                        try:
                            created_dt = datetime.fromisoformat(created)
                            if (NOW - created_dt).total_seconds() < 86400:
                                recent_dl.append(msg)
                        except ValueError:
                            pass
                except (json.JSONDecodeError, OSError):
                    pass

        if len(recent_dl) >= dl_threshold:
            severity = "critical" if len(recent_dl) > dl_threshold * 2 else "warning"
            confidence = min(95, int(60 + len(recent_dl) * 3))

            # Analyze dead letter reasons
            reasons = defaultdict(int)
            for msg in recent_dl:
                status = msg.get("status", "unknown")
                reasons[status] += 1

            self._emit(
                "bus_error", severity, confidence,
                f"{len(recent_dl)} dead-letter messages in last 24h "
                f"(threshold: {dl_threshold})",
                "Check bus routing and subscriber health — messages failing to deliver",
                details={"dead_letter_count": len(recent_dl),
                         "total_dead_letters": dl_count,
                         "reasons": dict(reasons)},
            )

        # Check bus log for routing failures
        if BUS_LOG.exists():
            try:
                lines = BUS_LOG.read_text().splitlines()
                recent_errors = 0
                recent_total = 0
                cutoff = (NOW - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")

                for line in lines:
                    if len(line) > 21 and line[1:20] >= cutoff[:19]:
                        recent_total += 1
                        if "[ERROR]" in line or "NO SUBSCRIBERS" in line:
                            recent_errors += 1

                failure_threshold = self.thresholds.get("bus_routing_failure_rate")
                if recent_total > 10 and recent_errors / recent_total > failure_threshold:
                    rate = recent_errors / recent_total
                    self._emit(
                        "bus_error", "warning", int(60 + rate * 30),
                        f"Bus routing failure rate {rate:.0%} "
                        f"({recent_errors}/{recent_total} messages in 24h)",
                        "Review topic subscriptions — some messages have no subscribers",
                        details={"error_count": recent_errors,
                                 "total_count": recent_total,
                                 "failure_rate": round(rate, 3)},
                    )
            except OSError:
                pass

    # ── Full scan ─────────────────────────────────────────

    def scan(self):
        """Run all anomaly detectors. Returns list of AnomalyEvents."""
        alog("Starting full anomaly scan")
        self.anomalies = []

        self.check_deal_velocity()
        self.check_agent_timing()
        self.check_cost_anomalies()
        self.check_pipeline_value()
        self.check_activity_gaps()
        self.check_bus_health()

        # Auto-adjust thresholds based on history
        self.thresholds.auto_adjust(self.history)

        alog(f"Scan complete — {len(self.anomalies)} anomalies detected")
        slog(f"Anomaly scan: {len(self.anomalies)} detected",
             source="anomaly_detector",
             meta={"count": len(self.anomalies),
                    "by_severity": self._count_by("severity"),
                    "by_type": self._count_by("type")})
        return self.anomalies

    def _count_by(self, field):
        counts = defaultdict(int)
        for a in self.anomalies:
            counts[getattr(a, field, "unknown")] += 1
        return dict(counts)


# ── CLI ───────────────────────────────────────────────────

COLORS = {
    "critical": "\033[0;31m",
    "warning": "\033[0;33m",
    "info": "\033[0;36m",
    "reset": "\033[0m",
    "bold": "\033[1m",
    "dim": "\033[2m",
}


def print_anomaly(a, idx=None):
    """Pretty-print a single anomaly (dict or AnomalyEvent)."""
    d = a if isinstance(a, dict) else a.to_dict()
    sev = d.get("severity", "info")
    color = COLORS.get(sev, "")
    reset = COLORS["reset"]
    dim = COLORS["dim"]
    bold = COLORS["bold"]

    prefix = f"  {idx}." if idx is not None else "  *"
    sev_label = f"{color}{sev.upper():8s}{reset}"

    print(f"{prefix} {sev_label} [{d.get('type', '?')}] "
          f"confidence: {d.get('confidence', 0)}%")
    print(f"     {bold}{d.get('description', '')}{reset}")
    print(f"     {dim}Action: {d.get('recommended_action', '')}{reset}")
    if d.get("false_positive"):
        print(f"     {dim}(marked as false positive){reset}")
    ts = d.get("detected_at", "")[:19]
    if ts:
        print(f"     {dim}Detected: {ts}{reset}")
    print()


def cmd_scan():
    detector = AnomalyDetector()
    anomalies = detector.scan()

    print(f"\n{'='*60}")
    print(f"  ANOMALY SCAN RESULTS — {TODAY.isoformat()}")
    print(f"{'='*60}\n")

    if not anomalies:
        print("  All clear. No anomalies detected.\n")
        return

    # Group by severity
    by_sev = defaultdict(list)
    for a in anomalies:
        by_sev[a.severity].append(a)

    for sev in ("critical", "warning", "info"):
        items = by_sev.get(sev, [])
        if items:
            color = COLORS.get(sev, "")
            reset = COLORS["reset"]
            print(f"  {color}{sev.upper()} ({len(items)}){reset}")
            print(f"  {'─'*56}")
            for i, a in enumerate(items, 1):
                print_anomaly(a, i)

    critical = sum(1 for a in anomalies if a.severity == 'critical')
    warnings = sum(1 for a in anomalies if a.severity == 'warning')
    print(f"  Total: {len(anomalies)} anomalies "
          f"({critical} critical, "
          f"{warnings} warning, "
          f"{sum(1 for a in anomalies if a.severity == 'info')} info)\n")

    if critical > 5:
        notify_telegram(f"Anomaly Alert: {critical} critical, {warnings} warnings detected")


def cmd_status():
    history = AnomalyHistory()
    active = history.get_active()

    print(f"\n{'='*60}")
    print(f"  ACTIVE ANOMALIES")
    print(f"{'='*60}\n")

    if not active:
        print("  No active anomalies (last 48h).\n")
        return

    for i, a in enumerate(active, 1):
        print_anomaly(a, i)

    print(f"  {len(active)} active anomalies\n")

    fp_rate = history.false_positive_rate()
    stats = history.data["stats"]
    dim = COLORS["dim"]
    reset = COLORS["reset"]
    print(f"  {dim}Lifetime: {stats.get('total_detected', 0)} detected, "
          f"{stats.get('false_positives', 0)} false positives ({fp_rate}% FP rate){reset}\n")


def cmd_history():
    history = AnomalyHistory()
    recent = history.get_recent(days=7)

    print(f"\n{'='*60}")
    print(f"  ANOMALY HISTORY (last 7 days)")
    print(f"{'='*60}\n")

    if not recent:
        print("  No anomalies in the last 7 days.\n")
        return

    for i, a in enumerate(recent, 1):
        print_anomaly(a, i)

    # Stats breakdown
    stats = history.data["stats"]
    print(f"  {'─'*56}")
    print(f"  Lifetime stats:")
    print(f"    Total detected: {stats.get('total_detected', 0)}")
    print(f"    False positives: {stats.get('false_positives', 0)} "
          f"({history.false_positive_rate()}%)")

    by_type = stats.get("by_type", {})
    if by_type:
        print(f"    By type:")
        for t, c in sorted(by_type.items(), key=lambda x: -x[1]):
            print(f"      {t}: {c}")

    by_sev = stats.get("by_severity", {})
    if by_sev:
        print(f"    By severity:")
        for s, c in sorted(by_sev.items()):
            print(f"      {s}: {c}")
    print()


def cmd_thresholds():
    tm = ThresholdManager()

    print(f"\n{'='*60}")
    print(f"  ANOMALY DETECTION THRESHOLDS")
    print(f"{'='*60}\n")

    descriptions = {
        "deal_velocity_z": "Deal velocity z-score threshold",
        "agent_timing_multiplier": "Agent timing spike multiplier",
        "cost_spike_multiplier": "Cost spike multiplier (vs moving avg)",
        "pipeline_shift_z": "Pipeline value shift z-score threshold",
        "activity_gap_days": "Days without activity to flag",
        "bus_dead_letter_threshold": "Dead-letter count to trigger alert",
        "bus_routing_failure_rate": "Bus routing failure rate threshold",
        "min_data_points": "Minimum data points for analysis",
    }

    for key, value in sorted(tm.thresholds.items()):
        desc = descriptions.get(key, key)
        default = ThresholdManager.DEFAULTS.get(key)
        modified = " (modified)" if value != default else ""
        print(f"  {desc:45s} {value:>8}{modified}")

    print()
    history = AnomalyHistory()
    fp_rate = history.false_positive_rate()
    total = history.data["stats"].get("total_detected", 0)
    dim = COLORS["dim"]
    reset = COLORS["reset"]
    print(f"  {dim}FP rate: {fp_rate}% ({total} total detections)")
    print(f"  Thresholds auto-adjust based on false positive rate.{reset}\n")

    # Show how to adjust
    print(f"  {dim}To adjust: edit {THRESHOLD_FILE}")
    print(f"  To mark false positive: add 'false_positive: true' in {ANOMALY_FILE}{reset}\n")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "scan"

    if cmd == "scan":
        cmd_scan()
    elif cmd == "status":
        cmd_status()
    elif cmd == "history":
        cmd_history()
    elif cmd == "thresholds":
        cmd_thresholds()
    else:
        print("Usage: anomaly_detector.py [scan|status|history|thresholds]")
        print("  scan        Run full anomaly scan across all sources")
        print("  status      Show active (unacknowledged) anomalies")
        print("  history     View anomaly history (last 7 days)")
        print("  thresholds  Show and manage detection thresholds")


if __name__ == "__main__":
    main()
