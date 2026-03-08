#!/usr/bin/env python3
"""
A/B Testing Framework — Track and optimize email template performance
======================================================================
Statistically rigorous A/B testing for email subjects, body templates,
and sequences. Automatic winner selection with confidence intervals.

Usage:
  python3 scripts/ab_testing.py experiments           # List experiments
  python3 scripts/ab_testing.py create <name>          # Create experiment
  python3 scripts/ab_testing.py results                # Show all results
  python3 scripts/ab_testing.py results <name>         # Show specific
  python3 scripts/ab_testing.py winner <name>          # Declare winner
"""

import json
import math
import random
import sys
from datetime import datetime
from pathlib import Path
from collections import defaultdict

WORKSPACE = Path(__file__).resolve().parents[1]
EXPERIMENTS_DIR = WORKSPACE / "experiments"
EXPERIMENTS_FILE = EXPERIMENTS_DIR / "experiments.json"
LOG_FILE = WORKSPACE / "logs" / "ab-testing.log"


def ablog(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] [{level}] {msg}\n")


def load_experiments():
    try:
        if EXPERIMENTS_FILE.exists():
            return json.loads(EXPERIMENTS_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        pass
    return {"experiments": []}


def save_experiments(data):
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    EXPERIMENTS_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


class Variant:
    """A single variant in an A/B test."""

    def __init__(self, name, content, variant_type="subject"):
        self.name = name
        self.content = content
        self.variant_type = variant_type
        self.sent = 0
        self.opened = 0
        self.replied = 0
        self.clicked = 0
        self.converted = 0

    def open_rate(self):
        return self.opened / self.sent if self.sent else 0

    def reply_rate(self):
        return self.replied / self.sent if self.sent else 0

    def conversion_rate(self):
        return self.converted / self.sent if self.sent else 0

    def to_dict(self):
        return {
            "name": self.name,
            "content": self.content,
            "type": self.variant_type,
            "sent": self.sent,
            "opened": self.opened,
            "replied": self.replied,
            "clicked": self.clicked,
            "converted": self.converted,
        }

    @classmethod
    def from_dict(cls, d):
        v = cls(d["name"], d["content"], d.get("type", "subject"))
        v.sent = d.get("sent", 0)
        v.opened = d.get("opened", 0)
        v.replied = d.get("replied", 0)
        v.clicked = d.get("clicked", 0)
        v.converted = d.get("converted", 0)
        return v


class Experiment:
    """An A/B test experiment."""

    def __init__(self, name, metric="reply_rate"):
        self.name = name
        self.metric = metric  # reply_rate, open_rate, conversion_rate
        self.variants = []
        self.status = "active"  # active, paused, completed
        self.created_at = datetime.now().isoformat()
        self.winner = None
        self.min_samples = 30  # min sends before declaring winner

    def add_variant(self, name, content, variant_type="subject"):
        self.variants.append(Variant(name, content, variant_type))

    def pick_variant(self):
        """Pick a variant using Thompson Sampling (Bayesian)."""
        if not self.variants:
            return None

        # Thompson Sampling with Beta distribution approximation
        best_score = -1
        best_variant = None
        for v in self.variants:
            metric_fn = getattr(v, self.metric)
            successes = int(metric_fn() * v.sent) if v.sent else 1
            failures = max(1, v.sent - successes)
            # Sample from Beta distribution (approximation using normal)
            mean = successes / (successes + failures)
            std = math.sqrt((mean * (1 - mean)) / max(1, successes + failures))
            score = random.gauss(mean, std)
            if score > best_score:
                best_score = score
                best_variant = v

        return best_variant

    def record_event(self, variant_name, event_type):
        """Record an event for a variant."""
        for v in self.variants:
            if v.name == variant_name:
                if event_type == "sent":
                    v.sent += 1
                elif event_type == "opened":
                    v.opened += 1
                elif event_type == "replied":
                    v.replied += 1
                elif event_type == "clicked":
                    v.clicked += 1
                elif event_type == "converted":
                    v.converted += 1
                return True
        return False

    def statistical_significance(self):
        """Calculate statistical significance between variants."""
        if len(self.variants) < 2:
            return None

        a, b = self.variants[0], self.variants[1]
        if a.sent < self.min_samples or b.sent < self.min_samples:
            return {"significant": False, "reason": "insufficient data", "confidence": 0}

        metric_fn_name = self.metric
        rate_a = getattr(a, metric_fn_name)()
        rate_b = getattr(b, metric_fn_name)()

        # Pooled standard error
        n_a, n_b = a.sent, b.sent
        if rate_a == 0 and rate_b == 0:
            return {"significant": False, "reason": "no events", "confidence": 0}

        # Z-test for proportions
        p_pool = (rate_a * n_a + rate_b * n_b) / (n_a + n_b) if (n_a + n_b) > 0 else 0
        if p_pool == 0 or p_pool == 1:
            return {"significant": False, "reason": "extreme rates", "confidence": 0}

        se = math.sqrt(p_pool * (1 - p_pool) * (1/n_a + 1/n_b))
        if se == 0:
            return {"significant": False, "reason": "zero variance", "confidence": 0}

        z = abs(rate_a - rate_b) / se

        # Z-score to p-value approximation
        # Using complementary error function approximation
        p_value = math.exp(-0.5 * z * z) / math.sqrt(2 * math.pi)
        confidence = (1 - 2 * p_value) * 100

        return {
            "significant": confidence >= 95,
            "confidence": round(confidence, 1),
            "z_score": round(z, 2),
            "variant_a": {"name": a.name, "rate": round(rate_a, 4), "n": a.sent},
            "variant_b": {"name": b.name, "rate": round(rate_b, 4), "n": b.sent},
            "winner": a.name if rate_a > rate_b else b.name,
            "lift": round(abs(rate_a - rate_b) / max(0.001, min(rate_a, rate_b)) * 100, 1),
        }

    def auto_winner(self):
        """Check if we can declare a winner."""
        sig = self.statistical_significance()
        if not sig or not sig["significant"]:
            return None

        self.winner = sig["winner"]
        self.status = "completed"
        ablog(f"Experiment '{self.name}': winner is {self.winner} (confidence: {sig['confidence']}%)")
        return self.winner

    def to_dict(self):
        return {
            "name": self.name,
            "metric": self.metric,
            "variants": [v.to_dict() for v in self.variants],
            "status": self.status,
            "winner": self.winner,
            "created_at": self.created_at,
            "min_samples": self.min_samples,
        }

    @classmethod
    def from_dict(cls, d):
        exp = cls(d["name"], d.get("metric", "reply_rate"))
        exp.variants = [Variant.from_dict(v) for v in d.get("variants", [])]
        exp.status = d.get("status", "active")
        exp.winner = d.get("winner")
        exp.created_at = d.get("created_at", "")
        exp.min_samples = d.get("min_samples", 30)
        return exp


# ── PREDEFINED EXPERIMENTS ──────────────────────────

PREDEFINED = {
    "subject_style": {
        "metric": "reply_rate",
        "variants": [
            ("direct", "Quick question about {{company}}'s employee engagement", "subject"),
            ("curious", "I noticed something about {{company}}...", "subject"),
            ("value", "3 ways {{company}} can boost retention by 40%", "subject"),
        ],
    },
    "opening_style": {
        "metric": "reply_rate",
        "variants": [
            ("personal", "Hi {{name}}, I saw your recent post about...", "body"),
            ("industry", "Hi {{name}}, companies in {{industry}} are seeing...", "body"),
            ("direct", "Hi {{name}}, I'll be brief — we help companies like {{company}}...", "body"),
        ],
    },
    "cta_style": {
        "metric": "reply_rate",
        "variants": [
            ("soft", "Would you be open to a 15-minute chat?", "body"),
            ("specific", "Are you free Tuesday or Wednesday for a quick call?", "body"),
            ("value", "I'd love to show you a 5-minute demo. Worth your time?", "body"),
        ],
    },
    "followup_timing": {
        "metric": "reply_rate",
        "variants": [
            ("day3", "3-day follow-up: Brief check-in", "sequence"),
            ("day5", "5-day follow-up: Brief check-in", "sequence"),
            ("day7", "7-day follow-up: Brief check-in", "sequence"),
        ],
    },
}


def cmd_experiments():
    """List all experiments."""
    data = load_experiments()
    exps = data.get("experiments", [])

    print(f"\n{'='*50}")
    print(f"  A/B Testing Experiments")
    print(f"{'='*50}\n")

    if not exps:
        print("  No experiments yet.")
        print(f"  Predefined: {', '.join(PREDEFINED.keys())}")
        print("  Create: python3 scripts/ab_testing.py create <name>\n")
        return

    for e_data in exps:
        exp = Experiment.from_dict(e_data)
        status_color = {
            "active": "\033[0;32m",
            "paused": "\033[0;33m",
            "completed": "\033[0;36m",
        }.get(exp.status, "")
        print(f"  {status_color}{exp.status:10s}\033[0m  {exp.name}")
        print(f"    Metric: {exp.metric}")
        for v in exp.variants:
            rate = getattr(v, exp.metric)() * 100
            print(f"    {v.name}: {v.sent} sent, {rate:.1f}% {exp.metric}")
        if exp.winner:
            print(f"    Winner: {exp.winner}")
        print()


def cmd_create(name):
    """Create an experiment."""
    data = load_experiments()

    if name in PREDEFINED:
        tpl = PREDEFINED[name]
        exp = Experiment(name, tpl["metric"])
        for vname, content, vtype in tpl["variants"]:
            exp.add_variant(vname, content, vtype)
    else:
        exp = Experiment(name)
        exp.add_variant("variant_a", f"Default A for {name}")
        exp.add_variant("variant_b", f"Default B for {name}")

    data["experiments"].append(exp.to_dict())
    save_experiments(data)

    print(f"\n  Created experiment: {name}")
    print(f"  Variants: {len(exp.variants)}")
    print(f"  Metric: {exp.metric}")
    print(f"  Min samples: {exp.min_samples}\n")


def cmd_results(name=None):
    """Show experiment results."""
    data = load_experiments()

    for e_data in data["experiments"]:
        if name and e_data["name"] != name:
            continue

        exp = Experiment.from_dict(e_data)
        print(f"\n  Experiment: {exp.name} ({exp.status})")
        print(f"  Metric: {exp.metric}")
        print(f"  Created: {exp.created_at[:19]}")
        print(f"  {'-'*40}")

        for v in exp.variants:
            rate = getattr(v, exp.metric)() * 100
            bar = "#" * int(rate * 2)
            print(f"  {v.name:15s} | sent:{v.sent:4d} | {exp.metric}:{rate:5.1f}% | {bar}")

        sig = exp.statistical_significance()
        if sig:
            if sig["significant"]:
                print(f"\n  SIGNIFICANT: {sig['winner']} wins ({sig['confidence']:.1f}% confidence, +{sig['lift']:.1f}% lift)")
            else:
                print(f"\n  Not significant yet: {sig.get('reason', 'need more data')}")
                total = sum(v.sent for v in exp.variants)
                needed = exp.min_samples * len(exp.variants)
                print(f"  Progress: {total}/{needed} sends")

    print()


def cmd_winner(name):
    """Declare a winner."""
    data = load_experiments()

    for i, e_data in enumerate(data["experiments"]):
        if e_data["name"] == name:
            exp = Experiment.from_dict(e_data)
            winner = exp.auto_winner()
            if winner:
                data["experiments"][i] = exp.to_dict()
                save_experiments(data)
                print(f"\n  Winner declared: {winner}")
            else:
                print(f"\n  Cannot declare winner yet — need more data or higher significance")
            return

    print(f"  Experiment not found: {name}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "experiments"

    if cmd == "experiments":
        cmd_experiments()
    elif cmd == "create" and len(sys.argv) > 2:
        cmd_create(sys.argv[2])
    elif cmd == "results":
        name = sys.argv[2] if len(sys.argv) > 2 else None
        cmd_results(name)
    elif cmd == "winner" and len(sys.argv) > 2:
        cmd_winner(sys.argv[2])
    else:
        print("Usage: ab_testing.py [experiments|create <name>|results [name]|winner <name>]")


if __name__ == "__main__":
    main()
