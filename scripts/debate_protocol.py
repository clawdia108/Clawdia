#!/usr/bin/env python3
"""
Multi-Agent Debate Protocol — Structured argumentation for complex decisions
=============================================================================
When a decision needs multiple perspectives, agents debate in structured rounds:
1. Proposer presents initial position
2. Challengers present counter-arguments
3. Each side responds
4. Judge synthesizes and decides

Uses Ollama for argument generation when available.

Usage:
  python3 scripts/debate_protocol.py start <topic>           # Start a debate
  python3 scripts/debate_protocol.py templates                # List debate templates
  python3 scripts/debate_protocol.py history                  # Past debates
  python3 scripts/debate_protocol.py replay <debate_id>       # Replay a debate
"""

import json
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from collections import defaultdict

WORKSPACE = Path(__file__).resolve().parents[1]
DEBATES_DIR = WORKSPACE / "debates"
LOG_FILE = WORKSPACE / "logs" / "debate.log"


def dblog(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(f"[{ts}] [{level}] {msg}\n")


def ollama_generate(prompt, max_tokens=300):
    """Generate text via Ollama."""
    try:
        payload = json.dumps({
            "model": "llama3.1:8b",
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.7},
        }).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read())
            return data.get("response", "").strip()
    except Exception:
        return None


class DebatePosition:
    """A position in a debate with supporting arguments."""

    def __init__(self, agent, stance, arguments=None):
        self.agent = agent
        self.stance = stance
        self.arguments = arguments or []
        self.confidence = 0.5
        self.evidence = []

    def to_dict(self):
        return {
            "agent": self.agent,
            "stance": self.stance,
            "arguments": self.arguments,
            "confidence": self.confidence,
            "evidence": self.evidence,
        }


class DebateRound:
    """A single round of debate."""

    def __init__(self, round_num, round_type):
        self.round_num = round_num
        self.round_type = round_type  # proposal, challenge, rebuttal, synthesis
        self.contributions = []
        self.timestamp = datetime.now().isoformat()

    def add_contribution(self, agent, content, stance=None):
        self.contributions.append({
            "agent": agent,
            "content": content,
            "stance": stance,
            "timestamp": datetime.now().isoformat(),
        })

    def to_dict(self):
        return {
            "round": self.round_num,
            "type": self.round_type,
            "contributions": self.contributions,
            "timestamp": self.timestamp,
        }


class DebateSession:
    """A full multi-agent debate."""

    def __init__(self, topic, debate_type="general"):
        self.id = f"debate_{int(time.time())}_{topic[:20].replace(' ', '_')}"
        self.topic = topic
        self.debate_type = debate_type
        self.participants = {}  # agent -> role (proposer/challenger/judge)
        self.rounds = []
        self.decision = None
        self.status = "setup"  # setup, active, decided, archived
        self.created_at = datetime.now().isoformat()

    def add_participant(self, agent, role):
        self.participants[agent] = role

    def run_debate(self, context=None):
        """Run the full debate automatically."""
        self.status = "active"
        context = context or {}

        proposer = [a for a, r in self.participants.items() if r == "proposer"]
        challengers = [a for a, r in self.participants.items() if r == "challenger"]
        judge = [a for a, r in self.participants.items() if r == "judge"]

        if not proposer or not challengers or not judge:
            dblog(f"Debate {self.id}: insufficient participants", "ERROR")
            return None

        proposer = proposer[0]
        judge = judge[0]

        # Round 1: Proposal
        r1 = DebateRound(1, "proposal")
        proposal = self._generate_argument(proposer, "propose", context)
        r1.add_contribution(proposer, proposal, "for")
        self.rounds.append(r1)
        dblog(f"Round 1: {proposer} proposes")

        # Round 2: Challenges
        r2 = DebateRound(2, "challenge")
        for challenger in challengers:
            challenge = self._generate_argument(challenger, "challenge", {**context, "proposal": proposal})
            r2.add_contribution(challenger, challenge, "against")
        self.rounds.append(r2)
        dblog(f"Round 2: {len(challengers)} challengers respond")

        # Round 3: Rebuttal
        r3 = DebateRound(3, "rebuttal")
        challenges = " ".join(c["content"] for c in r2.contributions)
        rebuttal = self._generate_argument(proposer, "rebut", {**context, "proposal": proposal, "challenges": challenges})
        r3.add_contribution(proposer, rebuttal, "for")
        self.rounds.append(r3)
        dblog(f"Round 3: {proposer} rebuts")

        # Round 4: Synthesis & Decision
        r4 = DebateRound(4, "synthesis")
        transcript = self._build_transcript()
        decision = self._generate_decision(judge, transcript, context)
        r4.add_contribution(judge, decision, "decision")
        self.rounds.append(r4)

        self.decision = decision
        self.status = "decided"
        self.save()

        dblog(f"Debate {self.id}: decided by {judge}")
        return decision

    def _generate_argument(self, agent, arg_type, context):
        """Generate an argument using Ollama or templates."""
        topic = self.topic

        prompts = {
            "propose": f"You are {agent}, a sales agent. Propose a strategy for: {topic}. "
                      f"Context: {json.dumps(context)[:200]}. Be specific and actionable. 3 bullet points max.",
            "challenge": f"You are {agent}, playing devil's advocate. Challenge this proposal about {topic}: "
                        f"{context.get('proposal', '')[:200]}. Identify risks, costs, alternatives. 3 points.",
            "rebut": f"You are {agent}. Defend your proposal about {topic} against these challenges: "
                    f"{context.get('challenges', '')[:200]}. Address each concern. 3 points.",
        }

        prompt = prompts.get(arg_type, f"Comment on {topic} as {agent}.")
        result = ollama_generate(prompt)

        if result:
            return result

        # Template fallback
        templates = {
            "propose": f"[{agent}] PROPOSAL for '{topic}': Based on current data, I recommend proceeding with "
                      f"a focused approach targeting high-probability deals first. Key arguments: "
                      f"1) Data supports this direction. 2) Resource allocation is optimal. 3) Risk is manageable.",
            "challenge": f"[{agent}] CHALLENGE: While the proposal has merit, consider: "
                        f"1) Opportunity cost of not pursuing alternatives. "
                        f"2) Market conditions may shift. "
                        f"3) Resource constraints could limit execution.",
            "rebut": f"[{agent}] REBUTTAL: Addressing the challenges: "
                    f"1) Our data analysis accounts for alternatives. "
                    f"2) Built-in flexibility handles market shifts. "
                    f"3) Phased rollout manages resource constraints.",
        }
        return templates.get(arg_type, f"[{agent}] Position on {topic}")

    def _generate_decision(self, judge, transcript, context):
        """Generate the judge's decision."""
        prompt = (f"You are {judge}, the deciding judge in a strategy debate about: {self.topic}. "
                 f"Here's the transcript:\n{transcript[:500]}\n\n"
                 f"Synthesize the arguments and make a decision. Include: "
                 f"1) Decision (which approach to take), "
                 f"2) Key reasoning, "
                 f"3) Risk mitigations from the challenger's concerns, "
                 f"4) Concrete next steps.")

        result = ollama_generate(prompt, max_tokens=400)
        if result:
            return result

        return (f"[{judge}] DECISION on '{self.topic}': After weighing all arguments, "
                f"I recommend proceeding with the proposal with modifications to address "
                f"the challenger's concerns. Key action items: "
                f"1) Implement the core strategy as proposed. "
                f"2) Add risk monitoring for identified concerns. "
                f"3) Review in 2 weeks and adjust based on results.")

    def _build_transcript(self):
        """Build a readable debate transcript."""
        lines = [f"DEBATE: {self.topic}\n"]
        for r in self.rounds:
            lines.append(f"\n--- Round {r.round_num} ({r.round_type}) ---")
            for c in r.contributions:
                lines.append(f"[{c['agent']}] {c['content'][:200]}")
        return "\n".join(lines)

    def save(self):
        """Save debate to disk."""
        DEBATES_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "id": self.id,
            "topic": self.topic,
            "type": self.debate_type,
            "participants": self.participants,
            "rounds": [r.to_dict() for r in self.rounds],
            "decision": self.decision,
            "status": self.status,
            "created_at": self.created_at,
            "decided_at": datetime.now().isoformat() if self.decision else None,
        }
        (DEBATES_DIR / f"{self.id}.json").write_text(json.dumps(data, indent=2, ensure_ascii=False))

    def to_dict(self):
        return {
            "id": self.id,
            "topic": self.topic,
            "participants": self.participants,
            "rounds": len(self.rounds),
            "status": self.status,
            "decision": self.decision[:100] if self.decision else None,
        }


# ── DEBATE TEMPLATES ────────────────────────────────

DEBATE_TEMPLATES = {
    "deal_priority": {
        "description": "Which deals to prioritize this week",
        "participants": {
            "obchodak": "proposer",
            "spojka": "challenger",
            "kontrolor": "judge",
        },
        "context_sources": ["pipedrive/DEAL_SCORING.md", "pipedrive/PIPELINE_STATUS.md"],
    },
    "resource_allocation": {
        "description": "How to allocate agent time across tasks",
        "participants": {
            "archivar": "proposer",
            "obchodak": "challenger",
            "spojka": "judge",
        },
        "context_sources": ["control-plane/agent-states.json", "control-plane/task-queue.json"],
    },
    "pricing_strategy": {
        "description": "Pricing approach for target segment",
        "participants": {
            "strateg": "proposer",
            "obchodak": "challenger",
            "spojka": "judge",
        },
        "context_sources": ["pipedrive/DEAL_SCORING.md"],
    },
    "risk_assessment": {
        "description": "Risk assessment for key pipeline deals",
        "participants": {
            "kontrolor": "proposer",
            "obchodak": "challenger",
            "spojka": "judge",
        },
        "context_sources": ["pipedrive/STALE_DEALS.md", "pipedrive/deal_velocity.json"],
    },
    "outreach_strategy": {
        "description": "Best outreach approach for new leads",
        "participants": {
            "postak": "proposer",
            "strateg": "challenger",
            "spojka": "judge",
        },
        "context_sources": ["pipedrive/DEAL_SCORING.md"],
    },
}


def load_context(sources):
    """Load context from multiple files."""
    ctx = {}
    for src in sources:
        p = WORKSPACE / src
        if p.exists():
            try:
                if src.endswith(".json"):
                    ctx[src] = json.loads(p.read_text())
                else:
                    ctx[src] = p.read_text()[:500]
            except Exception:
                pass
    return ctx


def cmd_start(topic):
    """Start a debate."""
    # Check if topic matches a template
    template = DEBATE_TEMPLATES.get(topic)

    if template:
        session = DebateSession(template["description"], topic)
        for agent, role in template["participants"].items():
            session.add_participant(agent, role)
        context = load_context(template.get("context_sources", []))
    else:
        # Custom topic
        session = DebateSession(topic, "custom")
        session.add_participant("obchodak", "proposer")
        session.add_participant("strateg", "challenger")
        session.add_participant("spojka", "judge")
        context = {}

    print(f"\n  Starting Debate: {session.topic}")
    print(f"  Participants: {', '.join(f'{a}({r})' for a, r in session.participants.items())}")
    print(f"  {'='*50}\n")

    decision = session.run_debate(context)

    print(f"  Debate ID: {session.id}")
    print(f"\n  Transcript:")
    for r in session.rounds:
        print(f"\n  --- Round {r.round_num} ({r.round_type}) ---")
        for c in r.contributions:
            content = c["content"][:200]
            print(f"  [{c['agent']}]: {content}")

    print(f"\n  DECISION:")
    print(f"  {decision[:500]}")
    print()


def cmd_templates():
    """List debate templates."""
    print(f"\n  Available Debate Templates ({len(DEBATE_TEMPLATES)}):\n")
    for name, tpl in DEBATE_TEMPLATES.items():
        parts = ", ".join(f"{a}({r})" for a, r in tpl["participants"].items())
        print(f"  {name}")
        print(f"    {tpl['description']}")
        print(f"    Agents: {parts}")
        print()


def cmd_history():
    """Show debate history."""
    if not DEBATES_DIR.exists():
        print("  No debates yet.")
        return

    debates = sorted(DEBATES_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)
    print(f"\n  Debate History ({len(debates)} debates):\n")
    for f in debates[:20]:
        try:
            d = json.loads(f.read_text())
            status = d.get("status", "?")
            topic = d.get("topic", "?")[:50]
            created = d.get("created_at", "?")[:19]
            color = "\033[0;32m" if status == "decided" else "\033[0;33m"
            print(f"  {color}{status:10s}\033[0m  {created}  {topic}")
        except Exception:
            pass
    print()


def cmd_replay(debate_id):
    """Replay a debate."""
    path = DEBATES_DIR / f"{debate_id}.json"
    if not path.exists():
        # Try partial match
        matches = list(DEBATES_DIR.glob(f"*{debate_id}*.json"))
        if matches:
            path = matches[0]
        else:
            print(f"  Debate not found: {debate_id}")
            return

    d = json.loads(path.read_text())
    print(f"\n  Debate: {d['topic']}")
    print(f"  Created: {d.get('created_at', '?')}")
    print(f"  Status: {d.get('status', '?')}")
    print(f"  Participants: {d.get('participants', {})}")
    print(f"  {'='*50}")

    for r in d.get("rounds", []):
        print(f"\n  --- Round {r['round']} ({r['type']}) ---")
        for c in r.get("contributions", []):
            print(f"  [{c['agent']}]: {c['content'][:300]}")

    if d.get("decision"):
        print(f"\n  DECISION:")
        print(f"  {d['decision'][:500]}")
    print()


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "templates"

    if cmd == "start" and len(sys.argv) > 2:
        cmd_start(" ".join(sys.argv[2:]))
    elif cmd == "templates":
        cmd_templates()
    elif cmd == "history":
        cmd_history()
    elif cmd == "replay" and len(sys.argv) > 2:
        cmd_replay(sys.argv[2])
    else:
        print("Usage: debate_protocol.py [start <topic>|templates|history|replay <id>]")


if __name__ == "__main__":
    main()
