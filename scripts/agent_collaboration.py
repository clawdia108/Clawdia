#!/usr/bin/env python3
"""
Agent Collaboration Engine — Deep multi-round agent interaction
================================================================
Manages structured collaboration sessions where multiple agents work together
through defined rounds of interaction before producing final output.

The key insight: agents don't just hand off work linearly. They DEBATE,
ENRICH, REVIEW, and REFINE through multiple rounds until the output is
genuinely good. No more "one agent does it all" — this is the real deal.

Roles:
  LEAD     — Owns the task, produces initial draft, incorporates feedback
  SUPPORT  — Enriches with data, perspectives, research
  REVIEWER — Evaluates quality, provides structured feedback
  APPROVER — Final sign-off or kicks back for another round

Flow (5 rounds default):
  R1: LEAD drafts    → shared context
  R2: SUPPORT enriches → shared context
  R3: REVIEWER evaluates → feedback to context
  R4: LEAD revises   → updated output
  R5: APPROVER signs off OR requests another cycle

Usage:
  python3 scripts/agent_collaboration.py start <template> [context_json]
  python3 scripts/agent_collaboration.py status [session_id]
  python3 scripts/agent_collaboration.py advance <session_id>
  python3 scripts/agent_collaboration.py history <session_id>
"""

import json
import sys
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict
from enum import Enum

BASE = Path("/Users/josefhofman/Clawdia")
COLLAB_DIR = BASE / "collaboration"
SESSIONS_DIR = COLLAB_DIR / "sessions"
CONTEXT_DIR = COLLAB_DIR / "context"
COLLAB_LOG = BASE / "logs" / "collaboration.log"

# Import sibling modules
sys.path.insert(0, str(BASE / "scripts"))
try:
    from agent_bus import AgentBus, Message, generate_message_id, bus_log
    from agent_lifecycle import AgentStateMachine, PerformanceTracker, AGENTS
    from workflow_engine import WorkflowEngine, WorkflowRun
except ImportError:
    # Graceful fallback if imports fail (for standalone testing)
    def generate_message_id():
        return hashlib.md5(f"{time.time()}:{id(object())}".encode()).hexdigest()[:16]

    def bus_log(msg, level="INFO"):
        pass

    AGENTS = {}


def clog(msg, level="INFO"):
    """Log to collaboration log"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    COLLAB_LOG.parent.mkdir(exist_ok=True)
    with open(COLLAB_LOG, "a") as f:
        f.write(line + "\n")


# ── ROLES & ROUND TYPES ────────────────────────────

class Role(str, Enum):
    LEAD = "LEAD"
    SUPPORT = "SUPPORT"
    REVIEWER = "REVIEWER"
    APPROVER = "APPROVER"


class RoundType(str, Enum):
    DRAFT = "draft"           # LEAD produces initial output
    ENRICH = "enrich"         # SUPPORT adds data/perspectives
    REVIEW = "review"         # REVIEWER evaluates and gives feedback
    REVISE = "revise"         # LEAD incorporates feedback
    APPROVE = "approve"       # APPROVER gives final verdict
    CONFLICT = "conflict"     # ConflictResolver mediates disagreement
    ESCALATE = "escalate"     # Escalate to human


# Standard round sequence for a full collaboration
DEFAULT_ROUND_SEQUENCE = [
    RoundType.DRAFT,
    RoundType.ENRICH,
    RoundType.REVIEW,
    RoundType.REVISE,
    RoundType.APPROVE,
]


# ── SHARED CONTEXT ──────────────────────────────────

class SharedContext:
    """
    Shared workspace for agents in a collaboration session.
    Agents publish findings, summaries, decisions here.
    Other agents query by topic or source agent.
    """

    def __init__(self, session_id):
        self.session_id = session_id
        self.context_dir = CONTEXT_DIR / session_id
        self.context_dir.mkdir(parents=True, exist_ok=True)
        self.entries = self._load()

    def _load(self):
        """Load all context entries from disk"""
        entries = []
        index_file = self.context_dir / "_index.json"
        if index_file.exists():
            try:
                entries = json.loads(index_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return entries

    def _save(self):
        """Persist context index"""
        index_file = self.context_dir / "_index.json"
        index_file.write_text(json.dumps(self.entries, indent=2, ensure_ascii=False))

    def publish(self, agent, topic, content, content_type="text", confidence=0.8, metadata=None):
        """
        Agent publishes a piece of context.

        Args:
            agent: Agent name (e.g., "textar")
            topic: What this is about (e.g., "initial_draft", "market_data", "review_feedback")
            content: The actual content (string or dict)
            content_type: "text", "draft", "data", "feedback", "decision", "artifact"
            confidence: 0.0-1.0 how confident the agent is
            metadata: Extra structured data
        """
        entry_id = generate_message_id()
        entry = {
            "id": entry_id,
            "agent": agent,
            "timestamp": datetime.now().isoformat(),
            "topic": topic,
            "content": content,
            "content_type": content_type,
            "confidence": confidence,
            "metadata": metadata or {},
            "round": len(self.entries) + 1,
            "supersedes": None,  # ID of previous entry this replaces
        }

        self.entries.append(entry)

        # Also save individual entry file for large content
        entry_file = self.context_dir / f"{entry_id}_{topic.replace('.', '_')}.json"
        entry_file.write_text(json.dumps(entry, indent=2, ensure_ascii=False))

        self._save()
        clog(f"[{self.session_id}] Context published: {agent} → {topic} (confidence={confidence})")
        return entry_id

    def publish_revision(self, agent, topic, content, supersedes_id, content_type="text", confidence=0.8):
        """Publish a revision that supersedes a previous entry"""
        entry_id = self.publish(agent, topic, content, content_type, confidence)

        # Mark supersedes
        for e in self.entries:
            if e["id"] == entry_id:
                e["supersedes"] = supersedes_id
                break

        self._save()
        clog(f"[{self.session_id}] Revision: {agent} supersedes {supersedes_id}")
        return entry_id

    def query_by_topic(self, topic, latest_only=True):
        """Get context entries for a specific topic"""
        matches = [e for e in self.entries if e["topic"] == topic]
        if latest_only and matches:
            # Filter out superseded entries
            superseded_ids = {e["supersedes"] for e in self.entries if e.get("supersedes")}
            matches = [e for e in matches if e["id"] not in superseded_ids]
        return matches

    def query_by_agent(self, agent):
        """Get all context entries from a specific agent"""
        return [e for e in self.entries if e["agent"] == agent]

    def query_by_type(self, content_type):
        """Get entries by content type"""
        return [e for e in self.entries if e["content_type"] == content_type]

    def get_latest(self, topic=None):
        """Get the most recent entry, optionally filtered by topic"""
        candidates = self.entries
        if topic:
            candidates = [e for e in candidates if e["topic"] == topic]
        if not candidates:
            return None

        # Filter out superseded
        superseded_ids = {e["supersedes"] for e in self.entries if e.get("supersedes")}
        active = [e for e in candidates if e["id"] not in superseded_ids]
        return active[-1] if active else candidates[-1]

    def get_all_active(self):
        """Get all entries that haven't been superseded"""
        superseded_ids = {e["supersedes"] for e in self.entries if e.get("supersedes")}
        return [e for e in self.entries if e["id"] not in superseded_ids]

    def get_feedback(self):
        """Get all feedback entries (from reviewers)"""
        return self.query_by_type("feedback")

    def get_decisions(self):
        """Get all decision entries"""
        return self.query_by_type("decision")

    def summary(self):
        """Summarize context state"""
        by_agent = defaultdict(int)
        by_type = defaultdict(int)
        by_topic = defaultdict(int)
        for e in self.entries:
            by_agent[e["agent"]] += 1
            by_type[e["content_type"]] += 1
            by_topic[e["topic"]] += 1

        return {
            "total_entries": len(self.entries),
            "active_entries": len(self.get_all_active()),
            "by_agent": dict(by_agent),
            "by_type": dict(by_type),
            "by_topic": dict(by_topic),
            "has_feedback": len(self.get_feedback()) > 0,
            "has_decisions": len(self.get_decisions()) > 0,
        }


# ── HANDOFF PROTOCOL ───────────────────────────────

class HandoffProtocol:
    """
    Formal handoff between agents in a collaboration.
    Tracks the chain of work as it moves from agent to agent,
    ensuring nothing is lost and every handoff is traceable.
    """

    def __init__(self, session_id):
        self.session_id = session_id
        self.handoff_dir = COLLAB_DIR / "handoffs" / session_id
        self.handoff_dir.mkdir(parents=True, exist_ok=True)
        self.chain = self._load_chain()

    def _load_chain(self):
        chain_file = self.handoff_dir / "_chain.json"
        if chain_file.exists():
            try:
                return json.loads(chain_file.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return []

    def _save_chain(self):
        chain_file = self.handoff_dir / "_chain.json"
        chain_file.write_text(json.dumps(self.chain, indent=2, ensure_ascii=False))

    def create_handoff(self, from_agent, to_agent, task_context, work_done,
                       artifacts=None, expected_next_steps=None, quality_notes=None):
        """
        Create a formal handoff from one agent to another.

        Args:
            from_agent: Agent handing off
            to_agent: Agent receiving
            task_context: What the task is about
            work_done: Summary of what's been done so far
            artifacts: List of artifacts produced (file paths, content IDs, etc.)
            expected_next_steps: What the receiving agent should do
            quality_notes: Any quality concerns or flags
        """
        handoff_id = generate_message_id()
        handoff = {
            "id": handoff_id,
            "session_id": self.session_id,
            "from_agent": from_agent,
            "to_agent": to_agent,
            "timestamp": datetime.now().isoformat(),
            "task_context": task_context,
            "work_done": work_done,
            "artifacts": artifacts or [],
            "expected_next_steps": expected_next_steps or [],
            "quality_notes": quality_notes,
            "status": "pending",  # pending, accepted, rejected
            "acceptance_notes": None,
            "chain_position": len(self.chain),
        }

        # Save handoff file
        handoff_file = self.handoff_dir / f"{handoff_id}.json"
        handoff_file.write_text(json.dumps(handoff, indent=2, ensure_ascii=False))

        # Add to chain
        self.chain.append({
            "handoff_id": handoff_id,
            "from": from_agent,
            "to": to_agent,
            "timestamp": handoff["timestamp"],
            "status": "pending",
        })
        self._save_chain()

        # Publish to bus for traceability
        try:
            bus = AgentBus()
            bus.handoff(
                source=from_agent,
                target=to_agent,
                topic="collaboration.handoff",
                payload={
                    "session_id": self.session_id,
                    "handoff_id": handoff_id,
                    "task_context": task_context[:200] if isinstance(task_context, str) else str(task_context)[:200],
                    "artifacts_count": len(artifacts or []),
                },
                priority="P1",
            )
        except Exception:
            pass  # Bus not available, that's ok

        clog(f"[{self.session_id}] Handoff: {from_agent} → {to_agent} (id={handoff_id})")
        return handoff_id

    def accept_handoff(self, handoff_id, agent, notes=None):
        """Agent accepts a handoff"""
        handoff_file = self.handoff_dir / f"{handoff_id}.json"
        if not handoff_file.exists():
            return None

        handoff = json.loads(handoff_file.read_text())
        if handoff["to_agent"] != agent:
            clog(f"[{self.session_id}] Handoff {handoff_id} rejected: wrong agent ({agent} != {handoff['to_agent']})", "WARN")
            return None

        handoff["status"] = "accepted"
        handoff["acceptance_notes"] = notes
        handoff["accepted_at"] = datetime.now().isoformat()
        handoff_file.write_text(json.dumps(handoff, indent=2, ensure_ascii=False))

        # Update chain
        for link in self.chain:
            if link["handoff_id"] == handoff_id:
                link["status"] = "accepted"
        self._save_chain()

        clog(f"[{self.session_id}] Handoff accepted: {handoff_id} by {agent}")
        return handoff

    def reject_handoff(self, handoff_id, agent, reason):
        """Agent rejects a handoff (needs more info, wrong scope, etc.)"""
        handoff_file = self.handoff_dir / f"{handoff_id}.json"
        if not handoff_file.exists():
            return None

        handoff = json.loads(handoff_file.read_text())
        handoff["status"] = "rejected"
        handoff["rejection_reason"] = reason
        handoff["rejected_at"] = datetime.now().isoformat()
        handoff_file.write_text(json.dumps(handoff, indent=2, ensure_ascii=False))

        for link in self.chain:
            if link["handoff_id"] == handoff_id:
                link["status"] = "rejected"
        self._save_chain()

        clog(f"[{self.session_id}] Handoff rejected: {handoff_id} by {agent}, reason: {reason}", "WARN")
        return handoff

    def get_chain(self):
        """Get the full handoff chain for this session"""
        return self.chain

    def get_chain_display(self):
        """Human-readable chain: agentA → agentB → agentC"""
        if not self.chain:
            return "No handoffs yet"
        agents = [self.chain[0]["from"]]
        for link in self.chain:
            agents.append(link["to"])
        statuses = [link["status"] for link in self.chain]
        parts = []
        for i, agent in enumerate(agents):
            parts.append(agent)
            if i < len(statuses):
                status_icon = {"pending": "?", "accepted": ">", "rejected": "X"}[statuses[i]]
                parts.append(f" -{status_icon}-> ")
        return "".join(parts)


# ── CONFLICT RESOLVER ──────────────────────────────

class ConflictResolver:
    """
    Resolves disagreements between agents.
    Three strategies: confidence scoring, majority vote, human escalation.
    """

    def __init__(self, session_id, shared_context):
        self.session_id = session_id
        self.context = shared_context
        self.conflicts = []
        self.resolutions = []

    def detect_conflicts(self, topic=None):
        """
        Find entries on the same topic from different agents that disagree.
        A conflict exists when:
          - Multiple agents publish on the same topic
          - Their content differs meaningfully
          - No superseding revision exists
        """
        entries = self.context.get_all_active()
        if topic:
            entries = [e for e in entries if e["topic"] == topic]

        # Group by topic
        by_topic = defaultdict(list)
        for e in entries:
            by_topic[e["topic"]].append(e)

        conflicts = []
        for t, topic_entries in by_topic.items():
            if len(topic_entries) < 2:
                continue

            # Check if entries are from different agents
            agents = set(e["agent"] for e in topic_entries)
            if len(agents) < 2:
                continue

            # Multiple agents, same topic — potential conflict
            conflicts.append({
                "topic": t,
                "entries": topic_entries,
                "agents": list(agents),
                "detected_at": datetime.now().isoformat(),
            })

        self.conflicts = conflicts
        return conflicts

    def resolve_by_confidence(self, conflict):
        """Highest confidence wins"""
        entries = conflict["entries"]
        winner = max(entries, key=lambda e: e.get("confidence", 0.5))
        resolution = {
            "strategy": "confidence",
            "topic": conflict["topic"],
            "winner": winner["agent"],
            "winning_confidence": winner["confidence"],
            "all_positions": [
                {"agent": e["agent"], "confidence": e.get("confidence", 0.5)}
                for e in entries
            ],
            "resolved_at": datetime.now().isoformat(),
        }
        self.resolutions.append(resolution)

        # Publish resolution to context
        self.context.publish(
            agent="conflict_resolver",
            topic=f"resolution.{conflict['topic']}",
            content={
                "strategy": "confidence",
                "winner": winner["agent"],
                "winning_content": winner["content"],
                "reason": f"{winner['agent']} had highest confidence ({winner['confidence']})",
            },
            content_type="decision",
            confidence=winner["confidence"],
        )

        clog(f"[{self.session_id}] Conflict resolved (confidence): {conflict['topic']} → {winner['agent']} wins")
        return resolution

    def resolve_by_vote(self, conflict):
        """Majority vote — each agent's entry counts as a vote for their position"""
        entries = conflict["entries"]

        if len(entries) < 3:
            # Not enough for majority, fall back to confidence
            return self.resolve_by_confidence(conflict)

        # Group entries by content similarity (simple: by agent)
        # In a real system you'd do semantic similarity
        positions = defaultdict(list)
        for e in entries:
            # Use content hash as position identifier
            content_str = json.dumps(e["content"]) if isinstance(e["content"], dict) else str(e["content"])
            content_hash = hashlib.md5(content_str.encode()).hexdigest()[:8]
            positions[content_hash].append(e)

        # Find majority position
        majority = max(positions.values(), key=len)
        winner = max(majority, key=lambda e: e.get("confidence", 0.5))

        resolution = {
            "strategy": "majority_vote",
            "topic": conflict["topic"],
            "winner": winner["agent"],
            "vote_count": len(majority),
            "total_voters": len(entries),
            "resolved_at": datetime.now().isoformat(),
        }
        self.resolutions.append(resolution)

        self.context.publish(
            agent="conflict_resolver",
            topic=f"resolution.{conflict['topic']}",
            content={
                "strategy": "majority_vote",
                "winner": winner["agent"],
                "winning_content": winner["content"],
                "votes": len(majority),
                "total": len(entries),
            },
            content_type="decision",
            confidence=len(majority) / len(entries),
        )

        clog(f"[{self.session_id}] Conflict resolved (vote): {conflict['topic']} → {winner['agent']} wins ({len(majority)}/{len(entries)})")
        return resolution

    def escalate_to_human(self, conflict):
        """When agents can't agree, escalate to human"""
        resolution = {
            "strategy": "human_escalation",
            "topic": conflict["topic"],
            "agents": conflict["agents"],
            "reason": "No consensus after max rounds",
            "escalated_at": datetime.now().isoformat(),
            "status": "awaiting_human",
        }
        self.resolutions.append(resolution)

        self.context.publish(
            agent="conflict_resolver",
            topic=f"escalation.{conflict['topic']}",
            content={
                "strategy": "human_escalation",
                "positions": [
                    {"agent": e["agent"], "confidence": e.get("confidence", 0.5), "content_preview": str(e["content"])[:200]}
                    for e in conflict["entries"]
                ],
            },
            content_type="decision",
            confidence=0.0,
        )

        # Publish to bus as P0
        try:
            bus = AgentBus()
            bus.publish(
                source="conflict_resolver",
                topic="collaboration.escalation",
                payload={
                    "session_id": self.session_id,
                    "conflict_topic": conflict["topic"],
                    "agents": conflict["agents"],
                },
                priority="P0",
            )
        except Exception:
            pass

        clog(f"[{self.session_id}] ESCALATION: {conflict['topic']} — agents {conflict['agents']} can't agree", "WARN")
        return resolution

    def resolve(self, conflict, strategy="auto"):
        """
        Resolve a conflict using specified strategy.
        'auto' picks the best strategy based on number of agents.
        """
        if strategy == "auto":
            if len(conflict["entries"]) >= 3:
                return self.resolve_by_vote(conflict)
            else:
                return self.resolve_by_confidence(conflict)
        elif strategy == "confidence":
            return self.resolve_by_confidence(conflict)
        elif strategy == "vote":
            return self.resolve_by_vote(conflict)
        elif strategy == "escalate":
            return self.escalate_to_human(conflict)
        else:
            return self.resolve_by_confidence(conflict)


# ── COLLABORATION SESSION ──────────────────────────

class CollaborationSession:
    """
    Manages a multi-agent collaboration task through defined rounds.

    Each session has:
    - Participants with assigned roles (LEAD, SUPPORT, REVIEWER, APPROVER)
    - A shared context where agents publish outputs
    - A handoff protocol for traceability
    - Rounds that follow a defined sequence
    - A conflict resolver for disagreements
    """

    def __init__(self, session_id=None, task=None, template=None):
        self.session_id = session_id or f"collab_{int(time.time())}_{generate_message_id()[:6]}"
        self.task = task or ""
        self.template = template
        self.participants = {}  # agent_name → Role
        self.status = "created"  # created, active, paused, completed, failed, escalated
        self.created_at = datetime.now().isoformat()
        self.completed_at = None
        self.current_round = 0
        self.max_rounds = 7  # Allow up to 7 rounds (5 standard + 2 extra revision cycles)
        self.round_sequence = list(DEFAULT_ROUND_SEQUENCE)
        self.rounds = []  # History of completed rounds
        self.workspace = SESSIONS_DIR / self.session_id
        self.workspace.mkdir(parents=True, exist_ok=True)

        # Initialize subsystems
        self.context = SharedContext(self.session_id)
        self.handoffs = HandoffProtocol(self.session_id)
        self.resolver = ConflictResolver(self.session_id, self.context)

        # Workflow tracking (if workflow engine available)
        self._workflow_run_id = None

    def add_participant(self, agent, role):
        """Add an agent with a specific role"""
        if isinstance(role, str):
            role = Role(role)
        self.participants[agent] = role.value
        clog(f"[{self.session_id}] Added participant: {agent} as {role.value}")

    def get_agents_by_role(self, role):
        """Get all agents with a specific role"""
        if isinstance(role, str):
            role = Role(role)
        return [a for a, r in self.participants.items() if r == role.value]

    def start(self):
        """Start the collaboration session"""
        if not self.participants:
            raise ValueError("No participants added to session")

        leads = self.get_agents_by_role(Role.LEAD)
        if not leads:
            raise ValueError("No LEAD agent assigned")

        self.status = "active"
        self.current_round = 0

        # Publish session start to bus
        try:
            bus = AgentBus()
            bus.publish(
                source="collaboration_engine",
                topic="collaboration.session_started",
                payload={
                    "session_id": self.session_id,
                    "task": self.task[:200],
                    "participants": self.participants,
                    "template": self.template,
                },
                priority="P1",
            )
        except Exception:
            pass

        # Create workflow run for tracking
        self._create_workflow_tracking()

        self.save()
        clog(f"[{self.session_id}] Session STARTED: {self.task[:100]}")
        return self

    def _create_workflow_tracking(self):
        """Create a workflow run to track collaboration progress"""
        try:
            engine = WorkflowEngine()
            # We don't use the engine's workflows directly, but we log events
            # for the orchestrator to pick up
        except Exception:
            pass

    def advance(self):
        """
        Advance to the next round of collaboration.
        Returns info about what needs to happen in this round.
        """
        if self.status != "active":
            return {"error": f"Session is {self.status}, not active"}

        if self.current_round >= len(self.round_sequence):
            # Check if we need extra rounds (approver requested revision)
            last_round = self.rounds[-1] if self.rounds else None
            if last_round and last_round.get("verdict") == "revise":
                # Add another revision cycle
                self.round_sequence.extend([RoundType.REVISE, RoundType.APPROVE])
                clog(f"[{self.session_id}] Extended: adding revision cycle (round {self.current_round + 1})")
            else:
                self.status = "completed"
                self.completed_at = datetime.now().isoformat()
                self.save()
                return {"status": "completed", "message": "All rounds complete"}

        if self.current_round >= self.max_rounds:
            # Hit max rounds — resolve any conflicts and wrap up
            conflicts = self.resolver.detect_conflicts()
            for conflict in conflicts:
                self.resolver.escalate_to_human(conflict)
            self.status = "escalated" if conflicts else "completed"
            self.completed_at = datetime.now().isoformat()
            self.save()
            return {"status": self.status, "message": f"Max rounds ({self.max_rounds}) reached"}

        round_type = self.round_sequence[self.current_round]
        self.current_round += 1

        # Determine which agents are active this round
        round_info = self._dispatch_round(round_type)
        round_info["round_number"] = self.current_round
        round_info["round_type"] = round_type.value if isinstance(round_type, RoundType) else round_type

        self.rounds.append(round_info)
        self.save()

        clog(f"[{self.session_id}] Round {self.current_round}: {round_type.value if isinstance(round_type, RoundType) else round_type}")
        return round_info

    def _dispatch_round(self, round_type):
        """Dispatch work for a specific round type"""
        if isinstance(round_type, str):
            round_type = RoundType(round_type)

        if round_type == RoundType.DRAFT:
            return self._round_draft()
        elif round_type == RoundType.ENRICH:
            return self._round_enrich()
        elif round_type == RoundType.REVIEW:
            return self._round_review()
        elif round_type == RoundType.REVISE:
            return self._round_revise()
        elif round_type == RoundType.APPROVE:
            return self._round_approve()
        elif round_type == RoundType.CONFLICT:
            return self._round_conflict()
        else:
            return {"error": f"Unknown round type: {round_type}"}

    def _round_draft(self):
        """Round: LEAD produces initial draft/analysis"""
        leads = self.get_agents_by_role(Role.LEAD)
        if not leads:
            return {"error": "No LEAD assigned"}

        lead = leads[0]
        instructions = {
            "action": "produce_initial_draft",
            "task": self.task,
            "context": self.context.get_all_active(),
            "participants": self.participants,
        }

        # Create handoff to lead
        self.handoffs.create_handoff(
            from_agent="collaboration_engine",
            to_agent=lead,
            task_context=self.task,
            work_done="Session initialized. You are the LEAD.",
            expected_next_steps=[
                "Analyze the task requirements",
                "Produce initial draft/analysis",
                "Publish to shared context with topic 'initial_draft'",
            ],
        )

        # Transition agent state
        try:
            sm = AgentStateMachine()
            sm.transition(lead, "assigned", task_id=self.session_id)
        except Exception:
            pass

        return {
            "active_agents": leads,
            "role": "LEAD",
            "instructions": instructions,
            "expected_output": "initial_draft published to shared context",
            "started_at": datetime.now().isoformat(),
            "status": "dispatched",
        }

    def _round_enrich(self):
        """Round: SUPPORT agents enrich with additional data/perspectives"""
        supports = self.get_agents_by_role(Role.SUPPORT)
        if not supports:
            return {"status": "skipped", "reason": "No SUPPORT agents assigned"}

        # Get the initial draft for context
        draft = self.context.get_latest(topic="initial_draft")
        draft_content = draft["content"] if draft else "No initial draft found"

        dispatched = []
        for agent in supports:
            instructions = {
                "action": "enrich_with_data",
                "task": self.task,
                "initial_draft": draft_content,
                "existing_context": self.context.get_all_active(),
                "your_role": "Add data, perspectives, and enrichment to the initial draft",
            }

            self.handoffs.create_handoff(
                from_agent=self.get_agents_by_role(Role.LEAD)[0],
                to_agent=agent,
                task_context=self.task,
                work_done=f"Initial draft produced. Your job: enrich with your expertise.",
                artifacts=[draft["id"]] if draft else [],
                expected_next_steps=[
                    "Review the initial draft",
                    "Add relevant data, research, or perspectives",
                    "Publish enrichment to shared context with topic 'enrichment'",
                ],
            )

            try:
                sm = AgentStateMachine()
                sm.transition(agent, "assigned", task_id=self.session_id)
            except Exception:
                pass

            dispatched.append(agent)

        return {
            "active_agents": dispatched,
            "role": "SUPPORT",
            "draft_available": draft is not None,
            "expected_output": "enrichment data published to shared context",
            "started_at": datetime.now().isoformat(),
            "status": "dispatched",
        }

    def _round_review(self):
        """Round: REVIEWER evaluates quality, provides feedback"""
        reviewers = self.get_agents_by_role(Role.REVIEWER)
        if not reviewers:
            return {"status": "skipped", "reason": "No REVIEWER agents assigned"}

        reviewer = reviewers[0]

        # Gather everything for review
        all_context = self.context.get_all_active()
        draft = self.context.get_latest(topic="initial_draft")
        enrichments = self.context.query_by_type("data")

        instructions = {
            "action": "review_and_provide_feedback",
            "task": self.task,
            "all_context": all_context,
            "review_criteria": [
                "Accuracy: Is the content factually correct?",
                "Completeness: Does it cover all aspects of the task?",
                "Quality: Is it well-structured and clear?",
                "Actionability: Can Josef act on this immediately?",
                "Tone: Does it match Josef's direct, no-fluff style?",
            ],
        }

        self.handoffs.create_handoff(
            from_agent=self.get_agents_by_role(Role.SUPPORT)[0] if self.get_agents_by_role(Role.SUPPORT) else self.get_agents_by_role(Role.LEAD)[0],
            to_agent=reviewer,
            task_context=self.task,
            work_done="Draft produced and enriched. Your job: review quality.",
            artifacts=[e["id"] for e in all_context],
            expected_next_steps=[
                "Evaluate draft against review criteria",
                "Provide specific, actionable feedback",
                "Publish feedback to shared context with topic 'review_feedback' and content_type 'feedback'",
                "Set confidence based on overall quality assessment",
            ],
        )

        try:
            sm = AgentStateMachine()
            sm.transition(reviewer, "assigned", task_id=self.session_id)
        except Exception:
            pass

        return {
            "active_agents": [reviewer],
            "role": "REVIEWER",
            "context_entries_to_review": len(all_context),
            "expected_output": "review_feedback published to shared context",
            "started_at": datetime.now().isoformat(),
            "status": "dispatched",
        }

    def _round_revise(self):
        """Round: LEAD revises based on feedback"""
        leads = self.get_agents_by_role(Role.LEAD)
        lead = leads[0]

        # Get feedback
        feedback = self.context.get_feedback()
        original_draft = self.context.get_latest(topic="initial_draft")

        if not feedback:
            return {"status": "skipped", "reason": "No feedback to incorporate"}

        instructions = {
            "action": "revise_based_on_feedback",
            "task": self.task,
            "original_draft": original_draft["content"] if original_draft else None,
            "feedback": [f["content"] for f in feedback],
            "enrichments": [e["content"] for e in self.context.query_by_type("data")],
        }

        self.handoffs.create_handoff(
            from_agent=self.get_agents_by_role(Role.REVIEWER)[0],
            to_agent=lead,
            task_context=self.task,
            work_done="Review complete with feedback. Your job: revise the draft.",
            artifacts=[f["id"] for f in feedback],
            expected_next_steps=[
                "Review all feedback carefully",
                "Incorporate valid points into revised output",
                "Publish revised version with topic 'revised_draft' using publish_revision()",
                "Note what feedback was incorporated vs. rejected and why",
            ],
        )

        try:
            sm = AgentStateMachine()
            sm.transition(lead, "assigned", task_id=self.session_id)
        except Exception:
            pass

        return {
            "active_agents": [lead],
            "role": "LEAD",
            "feedback_count": len(feedback),
            "expected_output": "revised_draft published to shared context",
            "started_at": datetime.now().isoformat(),
            "status": "dispatched",
        }

    def _round_approve(self):
        """Round: APPROVER gives final sign-off or requests another round"""
        approvers = self.get_agents_by_role(Role.APPROVER)
        if not approvers:
            # No approver — auto-approve if reviewer was happy
            feedback = self.context.get_feedback()
            last_feedback = feedback[-1] if feedback else None
            if last_feedback and last_feedback.get("confidence", 0) >= 0.7:
                self.context.publish(
                    agent="auto_approver",
                    topic="approval_decision",
                    content={"verdict": "approved", "reason": "Auto-approved (no APPROVER assigned, reviewer confidence >= 0.7)"},
                    content_type="decision",
                    confidence=0.8,
                )
                return {"status": "auto_approved", "reason": "No approver, reviewer satisfied"}
            else:
                return {"status": "skipped", "reason": "No APPROVER and reviewer not confident enough — consider adding an APPROVER"}

        approver = approvers[0]

        # Gather final state
        revised = self.context.get_latest(topic="revised_draft")
        if not revised:
            revised = self.context.get_latest(topic="initial_draft")

        all_feedback = self.context.get_feedback()
        decisions = self.context.get_decisions()

        instructions = {
            "action": "final_approval",
            "task": self.task,
            "final_output": revised["content"] if revised else None,
            "feedback_history": [f["content"] for f in all_feedback],
            "decisions_made": [d["content"] for d in decisions],
            "handoff_chain": self.handoffs.get_chain_display(),
            "round_count": self.current_round,
            "approval_options": [
                "approve — Output is good, ship it",
                "revise — Needs another revision round (provide specific feedback)",
                "escalate — Can't decide, need human input",
            ],
        }

        self.handoffs.create_handoff(
            from_agent=self.get_agents_by_role(Role.LEAD)[0],
            to_agent=approver,
            task_context=self.task,
            work_done=f"Draft revised after {len(all_feedback)} rounds of feedback. Ready for approval.",
            artifacts=[revised["id"]] if revised else [],
            expected_next_steps=[
                "Review final output",
                "Decide: approve, revise, or escalate",
                "Publish decision to shared context with topic 'approval_decision' and content_type 'decision'",
            ],
        )

        try:
            sm = AgentStateMachine()
            sm.transition(approver, "assigned", task_id=self.session_id)
        except Exception:
            pass

        return {
            "active_agents": [approver],
            "role": "APPROVER",
            "expected_output": "approval_decision published to shared context",
            "started_at": datetime.now().isoformat(),
            "status": "dispatched",
        }

    def _round_conflict(self):
        """Round: Detect and resolve conflicts"""
        conflicts = self.resolver.detect_conflicts()
        if not conflicts:
            return {"status": "skipped", "reason": "No conflicts detected"}

        resolutions = []
        for conflict in conflicts:
            resolution = self.resolver.resolve(conflict, strategy="auto")
            resolutions.append(resolution)

        return {
            "active_agents": ["conflict_resolver"],
            "conflicts_found": len(conflicts),
            "resolutions": resolutions,
            "status": "resolved",
        }

    def submit_round_output(self, agent, topic, content, content_type="text",
                            confidence=0.8, verdict=None):
        """
        Agent submits their output for the current round.
        This is the main API agents call after doing their work.
        """
        # Publish to shared context
        entry_id = self.context.publish(
            agent=agent,
            topic=topic,
            content=content,
            content_type=content_type,
            confidence=confidence,
        )

        # Update round info
        if self.rounds:
            current = self.rounds[-1]
            current["output_id"] = entry_id
            current["output_agent"] = agent
            current["output_confidence"] = confidence
            if verdict:
                current["verdict"] = verdict

        # Transition agent back
        try:
            sm = AgentStateMachine()
            sm.transition(agent, "working")
            sm.transition(agent, "done")
            sm.transition(agent, "idle")
        except Exception:
            pass

        # Record performance
        try:
            pt = PerformanceTracker()
            round_info = self.rounds[-1] if self.rounds else {}
            started = round_info.get("started_at")
            if started:
                elapsed = (datetime.now() - datetime.fromisoformat(started)).total_seconds() / 60
                pt.record_completion(agent, f"collab_{topic}", elapsed, success=True)
        except Exception:
            pass

        self.save()
        clog(f"[{self.session_id}] Output submitted: {agent} → {topic} (confidence={confidence})")
        return entry_id

    def get_status(self):
        """Get current session status"""
        return {
            "session_id": self.session_id,
            "task": self.task,
            "template": self.template,
            "status": self.status,
            "participants": self.participants,
            "current_round": self.current_round,
            "max_rounds": self.max_rounds,
            "round_sequence": [r.value if isinstance(r, RoundType) else r for r in self.round_sequence],
            "rounds_completed": len([r for r in self.rounds if r.get("status") in ("dispatched", "skipped", "resolved", "auto_approved")]),
            "context_summary": self.context.summary(),
            "handoff_chain": self.handoffs.get_chain_display(),
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    def get_history(self):
        """Get full session history"""
        return {
            "session_id": self.session_id,
            "task": self.task,
            "participants": self.participants,
            "status": self.status,
            "rounds": self.rounds,
            "context_entries": self.context.entries,
            "handoff_chain": self.handoffs.get_chain(),
            "conflicts": self.resolver.conflicts,
            "resolutions": self.resolver.resolutions,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    def save(self):
        """Persist session state"""
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        session_file = SESSIONS_DIR / f"{self.session_id}.json"
        data = {
            "session_id": self.session_id,
            "task": self.task,
            "template": self.template,
            "participants": self.participants,
            "status": self.status,
            "current_round": self.current_round,
            "max_rounds": self.max_rounds,
            "round_sequence": [r.value if isinstance(r, RoundType) else r for r in self.round_sequence],
            "rounds": self.rounds,
            "workflow_run_id": self._workflow_run_id,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }
        session_file.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    @classmethod
    def load(cls, session_id):
        """Load a session from disk"""
        session_file = SESSIONS_DIR / f"{session_id}.json"
        if not session_file.exists():
            raise FileNotFoundError(f"Session not found: {session_id}")

        data = json.loads(session_file.read_text())
        session = cls.__new__(cls)
        session.session_id = data["session_id"]
        session.task = data["task"]
        session.template = data.get("template")
        session.participants = data["participants"]
        session.status = data["status"]
        session.current_round = data["current_round"]
        session.max_rounds = data["max_rounds"]
        session.round_sequence = [RoundType(r) if r in [e.value for e in RoundType] else r for r in data.get("round_sequence", [])]
        session.rounds = data.get("rounds", [])
        session.created_at = data["created_at"]
        session.completed_at = data.get("completed_at")
        session._workflow_run_id = data.get("workflow_run_id")
        session.workspace = SESSIONS_DIR / session.session_id

        # Reinitialize subsystems
        session.context = SharedContext(session.session_id)
        session.handoffs = HandoffProtocol(session.session_id)
        session.resolver = ConflictResolver(session.session_id, session.context)

        return session

    @classmethod
    def list_sessions(cls, status_filter=None):
        """List all collaboration sessions"""
        sessions = []
        SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
        for f in sorted(SESSIONS_DIR.glob("*.json")):
            if f.name.startswith("_"):
                continue
            try:
                data = json.loads(f.read_text())
                if status_filter and data.get("status") != status_filter:
                    continue
                sessions.append({
                    "session_id": data["session_id"],
                    "task": data["task"][:80],
                    "template": data.get("template"),
                    "status": data["status"],
                    "participants": len(data.get("participants", {})),
                    "round": f"{data.get('current_round', 0)}/{data.get('max_rounds', 7)}",
                    "created_at": data["created_at"],
                })
            except (json.JSONDecodeError, OSError, KeyError):
                continue
        return sessions


# ── COLLABORATION TEMPLATES ─────────────────────────

TEMPLATES = {
    "email_campaign": {
        "name": "Email Campaign Collaboration",
        "description": "Textar drafts, Strateg enriches with research, Kontrolor checks quality, Spojka approves",
        "task_prefix": "Create email campaign: ",
        "participants": {
            "textar": Role.LEAD.value,
            "strateg": Role.SUPPORT.value,
            "kontrolor": Role.REVIEWER.value,
            "spojka": Role.APPROVER.value,
        },
        "round_sequence": ["draft", "enrich", "review", "revise", "approve"],
        "max_rounds": 7,
    },
    "deal_analysis": {
        "name": "Deal Analysis Collaboration",
        "description": "Obchodak leads analysis, Strateg adds market context, Udrzbar reviews, Spojka approves",
        "task_prefix": "Analyze deal: ",
        "participants": {
            "obchodak": Role.LEAD.value,
            "strateg": Role.SUPPORT.value,
            "udrzbar": Role.REVIEWER.value,
            "spojka": Role.APPROVER.value,
        },
        "round_sequence": ["draft", "enrich", "review", "revise", "approve"],
        "max_rounds": 7,
    },
    "morning_synthesis": {
        "name": "Morning Synthesis Collaboration",
        "description": "Spojka synthesizes, Obchodak + Kalendar + Postak provide data, Planovac reviews",
        "task_prefix": "Morning synthesis: ",
        "participants": {
            "spojka": Role.LEAD.value,
            "obchodak": Role.SUPPORT.value,
            "kalendar": Role.SUPPORT.value,
            "postak": Role.SUPPORT.value,
            "planovac": Role.REVIEWER.value,
        },
        "round_sequence": ["draft", "enrich", "review", "revise", "approve"],
        "max_rounds": 5,
    },
    "content_review": {
        "name": "Content Review Collaboration",
        "description": "Textar creates content, Archivar validates facts, Kontrolor quality checks",
        "task_prefix": "Review content: ",
        "participants": {
            "textar": Role.LEAD.value,
            "archivar": Role.SUPPORT.value,
            "kontrolor": Role.REVIEWER.value,
        },
        "round_sequence": ["draft", "enrich", "review", "revise", "approve"],
        "max_rounds": 5,
    },
    "competitive_intel": {
        "name": "Competitive Intelligence Collaboration",
        "description": "Strateg researches, Obchodak adds pipeline context, Udrzbar reviews strategic fit",
        "task_prefix": "Competitive analysis: ",
        "participants": {
            "strateg": Role.LEAD.value,
            "obchodak": Role.SUPPORT.value,
            "udrzbar": Role.REVIEWER.value,
            "spojka": Role.APPROVER.value,
        },
        "round_sequence": ["draft", "enrich", "review", "revise", "approve"],
        "max_rounds": 7,
    },
}


def create_from_template(template_name, task_context=None):
    """Create a collaboration session from a predefined template"""
    if template_name not in TEMPLATES:
        available = ", ".join(TEMPLATES.keys())
        raise ValueError(f"Unknown template: {template_name}. Available: {available}")

    template = TEMPLATES[template_name]
    task = template["task_prefix"]
    if task_context:
        if isinstance(task_context, dict):
            task += json.dumps(task_context)
        else:
            task += str(task_context)

    session = CollaborationSession(task=task, template=template_name)
    session.max_rounds = template.get("max_rounds", 7)
    session.round_sequence = [RoundType(r) for r in template["round_sequence"]]

    for agent, role in template["participants"].items():
        session.add_participant(agent, role)

    session.save()
    clog(f"Created session from template '{template_name}': {session.session_id}")
    return session


# ── COLLABORATION ENGINE (TOP-LEVEL) ───────────────

class CollaborationEngine:
    """
    Top-level engine that manages all collaboration sessions.
    Integrates with the bus, lifecycle, and workflow systems.
    """

    def __init__(self):
        self.bus = None
        try:
            self.bus = AgentBus()
        except Exception:
            pass

    def start_session(self, template_name, task_context=None):
        """Start a new collaboration from a template"""
        session = create_from_template(template_name, task_context)
        session.start()
        return session

    def advance_session(self, session_id):
        """Advance a session to its next round"""
        session = CollaborationSession.load(session_id)
        result = session.advance()
        return result

    def get_session_status(self, session_id):
        """Get status of a specific session"""
        session = CollaborationSession.load(session_id)
        return session.get_status()

    def get_session_history(self, session_id):
        """Get full history of a session"""
        session = CollaborationSession.load(session_id)
        return session.get_history()

    def list_active(self):
        """List all active collaboration sessions"""
        return CollaborationSession.list_sessions(status_filter="active")

    def list_all(self):
        """List all collaboration sessions"""
        return CollaborationSession.list_sessions()

    def run_full_cycle(self, template_name, task_context=None):
        """
        Run a complete collaboration cycle (all rounds).
        Returns the session with all rounds completed.
        Useful for automated pipelines.
        """
        session = self.start_session(template_name, task_context)

        while session.status == "active":
            result = session.advance()
            if result.get("status") in ("completed", "escalated"):
                break
            if result.get("error"):
                clog(f"[{session.session_id}] Error in round: {result['error']}", "ERROR")
                break

        return session

    def stats(self):
        """Get collaboration engine statistics"""
        all_sessions = CollaborationSession.list_sessions()
        active = [s for s in all_sessions if s["status"] == "active"]
        completed = [s for s in all_sessions if s["status"] == "completed"]
        failed = [s for s in all_sessions if s["status"] in ("failed", "escalated")]

        return {
            "total_sessions": len(all_sessions),
            "active": len(active),
            "completed": len(completed),
            "failed_or_escalated": len(failed),
            "templates_used": dict(defaultdict(int, {s.get("template", "custom"): 1 for s in all_sessions})),
        }


# ── CLI ─────────────────────────────────────────────

def print_json(data):
    print(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def cli():
    if len(sys.argv) < 2:
        print("Agent Collaboration Engine")
        print("=" * 40)
        print()
        print("Commands:")
        print("  start <template> [context]  — Start a collaboration session")
        print("  status [session_id]         — Show session status (or list all)")
        print("  advance <session_id>        — Advance session to next round")
        print("  history <session_id>        — Show full session history")
        print("  templates                   — List available templates")
        print("  stats                       — Engine statistics")
        print()
        print("Templates:")
        for name, tmpl in TEMPLATES.items():
            agents = ", ".join(f"{a}({r})" for a, r in tmpl["participants"].items())
            print(f"  {name}: {agents}")
        return

    cmd = sys.argv[1]
    engine = CollaborationEngine()

    if cmd == "start":
        if len(sys.argv) < 3:
            print("Usage: agent_collaboration.py start <template> [context_json]")
            print(f"Available templates: {', '.join(TEMPLATES.keys())}")
            return

        template = sys.argv[2]
        context = None
        if len(sys.argv) > 3:
            try:
                context = json.loads(sys.argv[3])
            except json.JSONDecodeError:
                context = sys.argv[3]

        try:
            session = engine.start_session(template, context)
            print(f"Session started: {session.session_id}")
            print(f"Task: {session.task}")
            print(f"Participants:")
            for agent, role in session.participants.items():
                print(f"  {agent} — {role}")
            print(f"\nRun: python3 scripts/agent_collaboration.py advance {session.session_id}")
        except ValueError as e:
            print(f"Error: {e}")

    elif cmd == "status":
        if len(sys.argv) > 2:
            session_id = sys.argv[2]
            try:
                status = engine.get_session_status(session_id)
                print_json(status)
            except FileNotFoundError:
                print(f"Session not found: {session_id}")
        else:
            sessions = engine.list_all()
            if not sessions:
                print("No collaboration sessions found.")
            else:
                print(f"{'ID':<45} {'Template':<20} {'Status':<12} {'Round':<8} {'Created'}")
                print("-" * 110)
                for s in sessions:
                    created = s["created_at"][:16] if s.get("created_at") else "?"
                    print(f"{s['session_id']:<45} {s.get('template', '-'):<20} {s['status']:<12} {s['round']:<8} {created}")

    elif cmd == "advance":
        if len(sys.argv) < 3:
            print("Usage: agent_collaboration.py advance <session_id>")
            return

        session_id = sys.argv[2]
        try:
            result = engine.advance_session(session_id)
            print(f"Round {result.get('round_number', '?')}: {result.get('round_type', '?')}")
            if result.get("active_agents"):
                print(f"Active agents: {', '.join(result['active_agents'])}")
            if result.get("status") == "completed":
                print("Session COMPLETED.")
            elif result.get("status") == "skipped":
                print(f"Skipped: {result.get('reason', '')}")
            elif result.get("error"):
                print(f"Error: {result['error']}")
            else:
                print_json(result)
        except FileNotFoundError:
            print(f"Session not found: {session_id}")

    elif cmd == "history":
        if len(sys.argv) < 3:
            print("Usage: agent_collaboration.py history <session_id>")
            return

        session_id = sys.argv[2]
        try:
            history = engine.get_session_history(session_id)
            print(f"Session: {history['session_id']}")
            print(f"Task: {history['task']}")
            print(f"Status: {history['status']}")
            print(f"Participants: {json.dumps(history['participants'])}")
            print()

            print("Rounds:")
            for i, r in enumerate(history.get("rounds", []), 1):
                status = r.get("status", "?")
                role = r.get("role", "?")
                agents = ", ".join(r.get("active_agents", []))
                verdict = f" — verdict: {r['verdict']}" if r.get("verdict") else ""
                print(f"  R{i} [{r.get('round_type', '?')}] {role}: {agents} ({status}{verdict})")

            print()
            print(f"Handoff chain: {history.get('handoff_chain', [])}")

            if history.get("context_entries"):
                print(f"\nContext entries: {len(history['context_entries'])}")
                for e in history["context_entries"]:
                    preview = str(e["content"])[:80].replace("\n", " ")
                    print(f"  [{e['agent']}] {e['topic']} ({e['content_type']}, conf={e.get('confidence', '?')}): {preview}")

            if history.get("resolutions"):
                print(f"\nConflict resolutions: {len(history['resolutions'])}")
                for r in history["resolutions"]:
                    print(f"  {r['topic']}: {r['strategy']} → {r.get('winner', 'escalated')}")

        except FileNotFoundError:
            print(f"Session not found: {session_id}")

    elif cmd == "templates":
        print("Available Collaboration Templates:")
        print("=" * 60)
        for name, tmpl in TEMPLATES.items():
            print(f"\n{name}:")
            print(f"  {tmpl['description']}")
            print(f"  Rounds: {' → '.join(tmpl['round_sequence'])}")
            print(f"  Max rounds: {tmpl.get('max_rounds', 7)}")
            print(f"  Agents:")
            for agent, role in tmpl["participants"].items():
                display = AGENTS.get(agent, {}).get("display", agent)
                print(f"    {display} — {role}")

    elif cmd == "stats":
        print_json(engine.stats())

    else:
        print(f"Unknown command: {cmd}")
        print("Run without arguments for usage info.")


if __name__ == "__main__":
    cli()
