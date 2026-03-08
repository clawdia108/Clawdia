#!/usr/bin/env python3
"""
Agent Learning System — Feedback loop from outcomes
=====================================================
Tracks which agent outputs led to good outcomes:
- Deal won → which agents contributed?
- Email replied → which draft template worked?
- Task completed fast → which routing was optimal?

Feeds back into agent prompts and scoring weights.
Agents improve over time based on what actually works.
"""

import json
from datetime import datetime, date, timedelta
from pathlib import Path
from collections import defaultdict

BASE = Path("/Users/josefhofman/Clawdia")
LEARNING_FILE = BASE / "knowledge" / "AGENT_LEARNINGS.json"
OUTCOME_LOG = BASE / "logs" / "outcomes.jsonl"
LEARNING_LOG = BASE / "logs" / "learning.log"


def llog(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LEARNING_LOG.parent.mkdir(exist_ok=True)
    with open(LEARNING_LOG, "a") as f:
        f.write(f"[{ts}] [{level}] {msg}\n")


class OutcomeTracker:
    """Track outcomes of agent actions for learning"""

    OUTCOME_TYPES = {
        "deal_won": {"weight": 10, "agents": ["obchodak", "textar", "postak", "udrzbar"]},
        "deal_lost": {"weight": -3, "agents": ["obchodak", "textar"]},
        "email_replied": {"weight": 5, "agents": ["textar", "postak"]},
        "email_ignored": {"weight": -1, "agents": ["textar"]},
        "meeting_booked": {"weight": 7, "agents": ["postak", "kalendar"]},
        "task_completed_fast": {"weight": 3, "agents": []},  # Dynamic based on task
        "task_failed": {"weight": -2, "agents": []},
        "review_passed_first": {"weight": 2, "agents": []},
        "review_needed_revision": {"weight": -1, "agents": []},
        "recovery_success": {"weight": 4, "agents": []},
    }

    def __init__(self):
        self.data = self._load()

    def _load(self):
        if LEARNING_FILE.exists():
            try:
                return json.loads(LEARNING_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {
            "agent_scores": {},
            "template_performance": {},
            "routing_performance": {},
            "total_outcomes": 0,
            "insights": [],
        }

    def _save(self):
        LEARNING_FILE.parent.mkdir(exist_ok=True)
        LEARNING_FILE.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))

    def record_outcome(self, outcome_type, agents=None, context=None):
        """Record an outcome and attribute it to agents"""
        outcome_config = self.OUTCOME_TYPES.get(outcome_type)
        if not outcome_config:
            llog(f"Unknown outcome type: {outcome_type}", "WARN")
            return

        weight = outcome_config["weight"]
        target_agents = agents or outcome_config["agents"]

        # Update agent scores
        agent_scores = self.data.setdefault("agent_scores", {})
        for agent in target_agents:
            agent_data = agent_scores.setdefault(agent, {
                "positive_outcomes": 0, "negative_outcomes": 0,
                "total_weight": 0, "outcome_types": {},
            })

            if weight > 0:
                agent_data["positive_outcomes"] += 1
            else:
                agent_data["negative_outcomes"] += 1

            agent_data["total_weight"] += weight
            ot = agent_data.setdefault("outcome_types", {})
            ot[outcome_type] = ot.get(outcome_type, 0) + 1

        # Track template performance if applicable
        if context and context.get("template"):
            templates = self.data.setdefault("template_performance", {})
            tmpl = templates.setdefault(context["template"], {"uses": 0, "positive": 0, "negative": 0})
            tmpl["uses"] += 1
            tmpl["positive" if weight > 0 else "negative"] += 1

        # Track routing performance
        if context and context.get("route_rule"):
            routing = self.data.setdefault("routing_performance", {})
            rule = routing.setdefault(context["route_rule"], {"uses": 0, "positive": 0, "negative": 0})
            rule["uses"] += 1
            rule["positive" if weight > 0 else "negative"] += 1

        self.data["total_outcomes"] = self.data.get("total_outcomes", 0) + 1

        # Log outcome
        outcome_event = {
            "ts": datetime.now().isoformat(),
            "type": outcome_type,
            "agents": target_agents,
            "weight": weight,
            "context": context or {},
        }
        OUTCOME_LOG.parent.mkdir(exist_ok=True)
        with open(OUTCOME_LOG, "a") as f:
            f.write(json.dumps(outcome_event, ensure_ascii=False) + "\n")

        self._save()
        llog(f"Outcome recorded: {outcome_type} (weight={weight}) → {', '.join(target_agents)}")

    def get_agent_effectiveness(self, agent_id):
        """Get an agent's learning-adjusted effectiveness score"""
        agent_data = self.data.get("agent_scores", {}).get(agent_id)
        if not agent_data:
            return {"score": 50, "confidence": "low", "outcomes": 0}

        total = agent_data["positive_outcomes"] + agent_data["negative_outcomes"]
        if total == 0:
            return {"score": 50, "confidence": "low", "outcomes": 0}

        success_rate = agent_data["positive_outcomes"] / total
        weight_per_outcome = agent_data["total_weight"] / total

        score = int(success_rate * 60 + min(weight_per_outcome / 10, 1) * 40)
        confidence = "high" if total >= 20 else "medium" if total >= 5 else "low"

        return {
            "score": score,
            "confidence": confidence,
            "outcomes": total,
            "success_rate": round(success_rate * 100, 1),
            "avg_weight": round(weight_per_outcome, 2),
        }

    def generate_insights(self):
        """Analyze outcomes and generate actionable insights"""
        insights = []

        # Best performing agents
        agent_scores = self.data.get("agent_scores", {})
        if agent_scores:
            ranked = sorted(
                agent_scores.items(),
                key=lambda x: x[1].get("total_weight", 0),
                reverse=True,
            )
            if ranked:
                best = ranked[0]
                insights.append({
                    "type": "top_agent",
                    "agent": best[0],
                    "weight": best[1].get("total_weight", 0),
                    "insight": f"{best[0]} is the top performing agent with weight {best[1].get('total_weight', 0)}",
                })

                if len(ranked) > 1 and ranked[-1][1].get("total_weight", 0) < 0:
                    worst = ranked[-1]
                    insights.append({
                        "type": "underperforming_agent",
                        "agent": worst[0],
                        "weight": worst[1].get("total_weight", 0),
                        "insight": f"{worst[0]} is underperforming (weight {worst[1].get('total_weight', 0)}). Consider retraining prompts.",
                    })

        # Best performing templates
        templates = self.data.get("template_performance", {})
        if templates:
            best_template = max(
                templates.items(),
                key=lambda x: x[1].get("positive", 0) - x[1].get("negative", 0),
                default=None,
            )
            if best_template:
                insights.append({
                    "type": "best_template",
                    "template": best_template[0],
                    "insight": f"Template '{best_template[0]}' has best results ({best_template[1].get('positive', 0)} positive outcomes)",
                })

        # Routing effectiveness
        routing = self.data.get("routing_performance", {})
        if routing:
            for rule_id, perf in routing.items():
                total = perf.get("positive", 0) + perf.get("negative", 0)
                if total >= 5:
                    success_rate = perf["positive"] / total
                    if success_rate < 0.5:
                        insights.append({
                            "type": "poor_routing",
                            "route_rule": rule_id,
                            "success_rate": round(success_rate * 100, 1),
                            "insight": f"Route rule '{rule_id}' has low success ({round(success_rate * 100)}%). Consider changing model or approach.",
                        })

        self.data["insights"] = insights
        self._save()
        return insights

    def summary(self):
        """Generate learning summary"""
        agent_scores = self.data.get("agent_scores", {})
        return {
            "total_outcomes": self.data.get("total_outcomes", 0),
            "agents_tracked": len(agent_scores),
            "top_agents": [
                {"agent": aid, "weight": ad.get("total_weight", 0)}
                for aid, ad in sorted(
                    agent_scores.items(),
                    key=lambda x: x[1].get("total_weight", 0),
                    reverse=True,
                )[:5]
            ],
            "insights_count": len(self.data.get("insights", [])),
        }


if __name__ == "__main__":
    import sys

    tracker = OutcomeTracker()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "record" and len(sys.argv) > 2:
            outcome_type = sys.argv[2]
            agents = sys.argv[3].split(",") if len(sys.argv) > 3 else None
            tracker.record_outcome(outcome_type, agents)
            print(f"Recorded: {outcome_type}")

        elif cmd == "insights":
            insights = tracker.generate_insights()
            for i in insights:
                print(f"  [{i['type']}] {i['insight']}")
            if not insights:
                print("  No insights yet (need more outcome data)")

        elif cmd == "effectiveness" and len(sys.argv) > 2:
            agent = sys.argv[2]
            eff = tracker.get_agent_effectiveness(agent)
            print(json.dumps(eff, indent=2))

        elif cmd == "summary":
            print(json.dumps(tracker.summary(), indent=2))

        else:
            print("Usage: agent_learning.py [record <type> [agents]|insights|effectiveness <agent>|summary]")
    else:
        print(json.dumps(tracker.summary(), indent=2))
