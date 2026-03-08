#!/usr/bin/env python3
"""
Agent Memory System — Persistent memory for all agents
========================================================
Each agent gets a dedicated memory store with:
  - decisions: what was decided, why, and what happened
  - patterns: recurring behaviors learned over time
  - contacts: interaction history per contact/company
  - context: current session context and notes

Cross-agent search, temporal queries, auto-pruning.

Usage:
  python3 scripts/agent_memory.py stats                  # Memory statistics
  python3 scripts/agent_memory.py recall <agent>          # Show agent's memories
  python3 scripts/agent_memory.py search <query>          # Search all memories
  python3 scripts/agent_memory.py prune                   # Clean old memories
"""

import json
import re
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

BASE = Path("/Users/josefhofman/Clawdia")
MEMORY_DIR = BASE / "knowledge" / "agent-memory"
MEMORY_LOG = BASE / "logs" / "agent-memory.log"

MEMORY_TYPES = ("decisions", "patterns", "contacts", "context")


def mlog(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    MEMORY_LOG.parent.mkdir(exist_ok=True)
    with open(MEMORY_LOG, "a") as f:
        f.write(f"[{ts}] [{level}] {msg}\n")


# ── AGENT MEMORY ──────────────────────────────────
class AgentMemory:
    """Persistent memory store for a single agent."""

    def __init__(self, agent_name):
        self.agent_name = agent_name
        self.file = MEMORY_DIR / f"{agent_name}.json"
        self.data = self._load()

    def _load(self):
        if self.file.exists():
            try:
                return json.loads(self.file.read_text())
            except (json.JSONDecodeError, OSError):
                mlog(f"Corrupt memory file for {self.agent_name}, resetting", "WARN")
        return self._init_memory()

    def _init_memory(self):
        return {
            "agent": self.agent_name,
            "created_at": datetime.now().isoformat(),
            "decisions": [],
            "patterns": [],
            "contacts": {},
            "context": {
                "current_task": None,
                "recent_events": [],
                "notes": [],
            },
        }

    def _save(self):
        MEMORY_DIR.mkdir(parents=True, exist_ok=True)
        self.file.write_text(json.dumps(self.data, indent=2, ensure_ascii=False))

    # ── Core API ──

    def remember(self, memory_type, data):
        """Store a memory. Returns the stored entry."""
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"Unknown memory type: {memory_type}. Use one of {MEMORY_TYPES}")

        if memory_type == "decisions":
            entry = {
                "id": str(uuid.uuid4())[:8],
                "timestamp": datetime.now().isoformat(),
                "context": data.get("context", ""),
                "decision": data.get("decision", ""),
                "outcome": data.get("outcome"),
                "confidence": data.get("confidence", 0.5),
                "tags": data.get("tags", []),
            }
            self.data["decisions"].append(entry)

        elif memory_type == "patterns":
            pattern_id = data.get("pattern_id") or str(uuid.uuid4())[:8]
            # Check if pattern already exists
            existing = next(
                (p for p in self.data["patterns"] if p["pattern_id"] == pattern_id),
                None,
            )
            if existing:
                existing["last_seen"] = datetime.now().isoformat()
                existing["frequency"] = existing.get("frequency", 1) + 1
                existing["active"] = data.get("active", existing.get("active", True))
                entry = existing
            else:
                entry = {
                    "pattern_id": pattern_id,
                    "description": data.get("description", ""),
                    "first_seen": datetime.now().isoformat(),
                    "last_seen": datetime.now().isoformat(),
                    "frequency": 1,
                    "active": data.get("active", True),
                    "tags": data.get("tags", []),
                }
                self.data["patterns"].append(entry)

        elif memory_type == "contacts":
            contact_id = data.get("contact_id", "unknown")
            contact = self.data["contacts"].setdefault(contact_id, {
                "contact_id": contact_id,
                "interactions": [],
                "preference_notes": [],
                "tags": [],
            })
            interaction = data.get("interaction")
            if interaction:
                contact["interactions"].append({
                    "date": datetime.now().isoformat(),
                    "type": interaction.get("type", "general"),
                    "summary": interaction.get("summary", ""),
                })
            if data.get("preference_note"):
                contact["preference_notes"].append(data["preference_note"])
            if data.get("tags"):
                contact["tags"] = list(set(contact.get("tags", []) + data["tags"]))
            entry = contact

        elif memory_type == "context":
            ctx = self.data["context"]
            if data.get("current_task") is not None:
                ctx["current_task"] = data["current_task"]
            if data.get("event"):
                ctx["recent_events"].append({
                    "timestamp": datetime.now().isoformat(),
                    "event": data["event"],
                })
                # Keep last 50 events
                ctx["recent_events"] = ctx["recent_events"][-50:]
            if data.get("note"):
                ctx["notes"].append({
                    "timestamp": datetime.now().isoformat(),
                    "note": data["note"],
                })
                ctx["notes"] = ctx["notes"][-100:]
            entry = ctx

        self._save()
        mlog(f"remember: {self.agent_name}/{memory_type}")
        return entry

    def recall(self, memory_type, filters=None):
        """Retrieve memories, optionally filtered."""
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"Unknown memory type: {memory_type}")

        filters = filters or {}

        if memory_type == "decisions":
            results = list(self.data.get("decisions", []))
            if filters.get("min_confidence"):
                results = [d for d in results if d.get("confidence", 0) >= filters["min_confidence"]]
            if filters.get("has_outcome"):
                results = [d for d in results if d.get("outcome")]
            if filters.get("tag"):
                results = [d for d in results if filters["tag"] in d.get("tags", [])]
            if filters.get("since"):
                results = [d for d in results if d.get("timestamp", "") >= filters["since"]]
            if filters.get("limit"):
                results = results[-filters["limit"]:]
            return results

        elif memory_type == "patterns":
            results = list(self.data.get("patterns", []))
            if filters.get("active_only", True):
                results = [p for p in results if p.get("active", True)]
            if filters.get("min_frequency"):
                results = [p for p in results if p.get("frequency", 0) >= filters["min_frequency"]]
            if filters.get("tag"):
                results = [p for p in results if filters["tag"] in p.get("tags", [])]
            return results

        elif memory_type == "contacts":
            contacts = self.data.get("contacts", {})
            if filters.get("contact_id"):
                c = contacts.get(filters["contact_id"])
                return [c] if c else []
            if filters.get("tag"):
                return [c for c in contacts.values() if filters["tag"] in c.get("tags", [])]
            return list(contacts.values())

        elif memory_type == "context":
            ctx = self.data.get("context", {})
            if filters.get("events_only"):
                return ctx.get("recent_events", [])
            if filters.get("notes_only"):
                return ctx.get("notes", [])
            return ctx

    def forget(self, memory_type, filter_fn=None):
        """Remove memories matching filter. Returns count removed."""
        if memory_type not in MEMORY_TYPES:
            raise ValueError(f"Unknown memory type: {memory_type}")

        removed = 0

        if memory_type == "decisions":
            before = len(self.data.get("decisions", []))
            if filter_fn:
                self.data["decisions"] = [d for d in self.data["decisions"] if not filter_fn(d)]
            else:
                self.data["decisions"] = []
            removed = before - len(self.data["decisions"])

        elif memory_type == "patterns":
            before = len(self.data.get("patterns", []))
            if filter_fn:
                self.data["patterns"] = [p for p in self.data["patterns"] if not filter_fn(p)]
            else:
                self.data["patterns"] = []
            removed = before - len(self.data["patterns"])

        elif memory_type == "contacts":
            if filter_fn:
                to_remove = [cid for cid, c in self.data.get("contacts", {}).items() if filter_fn(c)]
                for cid in to_remove:
                    del self.data["contacts"][cid]
                removed = len(to_remove)
            else:
                removed = len(self.data.get("contacts", {}))
                self.data["contacts"] = {}

        elif memory_type == "context":
            self.data["context"] = {"current_task": None, "recent_events": [], "notes": []}
            removed = 1

        if removed > 0:
            self._save()
            mlog(f"forget: {self.agent_name}/{memory_type} removed {removed}")

        return removed

    def prune(self, max_age_days=30):
        """Remove memories older than max_age_days. Returns total removed."""
        cutoff = (datetime.now() - timedelta(days=max_age_days)).isoformat()
        total_removed = 0

        # Prune decisions
        before = len(self.data.get("decisions", []))
        self.data["decisions"] = [
            d for d in self.data.get("decisions", [])
            if d.get("timestamp", "") >= cutoff
        ]
        total_removed += before - len(self.data["decisions"])

        # Prune inactive patterns not seen recently
        before = len(self.data.get("patterns", []))
        self.data["patterns"] = [
            p for p in self.data.get("patterns", [])
            if p.get("last_seen", "") >= cutoff or p.get("active", True)
        ]
        total_removed += before - len(self.data["patterns"])

        # Prune contacts with no recent interactions
        contacts_to_remove = []
        for cid, contact in self.data.get("contacts", {}).items():
            interactions = contact.get("interactions", [])
            if not interactions:
                continue
            last_interaction = max(i.get("date", "") for i in interactions)
            if last_interaction < cutoff:
                contacts_to_remove.append(cid)
        for cid in contacts_to_remove:
            del self.data["contacts"][cid]
        total_removed += len(contacts_to_remove)

        # Prune old context events
        before = len(self.data.get("context", {}).get("recent_events", []))
        self.data["context"]["recent_events"] = [
            e for e in self.data.get("context", {}).get("recent_events", [])
            if e.get("timestamp", "") >= cutoff
        ]
        total_removed += before - len(self.data["context"]["recent_events"])

        if total_removed > 0:
            self._save()
            mlog(f"prune: {self.agent_name} removed {total_removed} (cutoff {max_age_days}d)")

        return total_removed

    def stats(self):
        """Memory statistics for this agent."""
        decisions = self.data.get("decisions", [])
        patterns = self.data.get("patterns", [])
        contacts = self.data.get("contacts", {})
        context = self.data.get("context", {})

        oldest = None
        newest = None
        all_timestamps = (
            [d.get("timestamp", "") for d in decisions]
            + [p.get("first_seen", "") for p in patterns]
        )
        for contact in contacts.values():
            for i in contact.get("interactions", []):
                all_timestamps.append(i.get("date", ""))

        all_timestamps = [t for t in all_timestamps if t]
        if all_timestamps:
            oldest = min(all_timestamps)
            newest = max(all_timestamps)

        return {
            "agent": self.agent_name,
            "decisions": len(decisions),
            "patterns": len(patterns),
            "active_patterns": sum(1 for p in patterns if p.get("active", True)),
            "contacts": len(contacts),
            "total_interactions": sum(
                len(c.get("interactions", [])) for c in contacts.values()
            ),
            "context_events": len(context.get("recent_events", [])),
            "context_notes": len(context.get("notes", [])),
            "oldest_memory": oldest,
            "newest_memory": newest,
        }

    def _all_text(self):
        """Get all searchable text from this agent's memory."""
        texts = []
        for d in self.data.get("decisions", []):
            texts.append(f"{d.get('context', '')} {d.get('decision', '')} {d.get('outcome', '')}")
        for p in self.data.get("patterns", []):
            texts.append(p.get("description", ""))
        for contact in self.data.get("contacts", {}).values():
            for i in contact.get("interactions", []):
                texts.append(i.get("summary", ""))
            texts.extend(contact.get("preference_notes", []))
        for e in self.data.get("context", {}).get("recent_events", []):
            texts.append(str(e.get("event", "")))
        for n in self.data.get("context", {}).get("notes", []):
            texts.append(str(n.get("note", "")))
        return texts


# ── MEMORY MANAGER ────────────────────────────────
class MemoryManager:
    """Manages all agent memories. Cross-agent queries, stats, auto-prune."""

    def __init__(self, auto_prune=True):
        self._agents = {}
        self._auto_prune = auto_prune
        self._load_all()

    def _load_all(self):
        if not MEMORY_DIR.exists():
            return
        for f in MEMORY_DIR.glob("*.json"):
            agent_name = f.stem
            self._agents[agent_name] = AgentMemory(agent_name)

    def get(self, agent_name):
        """Get or create an agent's memory."""
        if agent_name not in self._agents:
            self._agents[agent_name] = AgentMemory(agent_name)
        mem = self._agents[agent_name]
        if self._auto_prune:
            mem.prune()
        return mem

    def all_agents(self):
        return list(self._agents.keys())

    def cross_query(self, query, memory_types=None):
        """Search across all agents for mentions of a term (company, contact, topic)."""
        query_lower = query.lower()
        memory_types = memory_types or list(MEMORY_TYPES)
        results = []

        for agent_name, mem in self._agents.items():
            for mtype in memory_types:
                if mtype == "decisions":
                    for d in mem.data.get("decisions", []):
                        searchable = f"{d.get('context','')} {d.get('decision','')} {d.get('outcome','')}".lower()
                        if query_lower in searchable:
                            results.append({"agent": agent_name, "type": "decision", "data": d})

                elif mtype == "patterns":
                    for p in mem.data.get("patterns", []):
                        if query_lower in p.get("description", "").lower():
                            results.append({"agent": agent_name, "type": "pattern", "data": p})

                elif mtype == "contacts":
                    for cid, contact in mem.data.get("contacts", {}).items():
                        searchable = cid.lower()
                        for i in contact.get("interactions", []):
                            searchable += f" {i.get('summary', '')}".lower()
                        searchable += " ".join(contact.get("preference_notes", [])).lower()
                        if query_lower in searchable:
                            results.append({"agent": agent_name, "type": "contact", "data": contact})

                elif mtype == "context":
                    ctx = mem.data.get("context", {})
                    for e in ctx.get("recent_events", []):
                        if query_lower in str(e.get("event", "")).lower():
                            results.append({"agent": agent_name, "type": "context_event", "data": e})
                    for n in ctx.get("notes", []):
                        if query_lower in str(n.get("note", "")).lower():
                            results.append({"agent": agent_name, "type": "context_note", "data": n})

        return results

    def stats(self):
        """Aggregate stats across all agents."""
        agent_stats = {}
        totals = {
            "agents": 0,
            "decisions": 0,
            "patterns": 0,
            "contacts": 0,
            "interactions": 0,
        }

        for agent_name, mem in self._agents.items():
            s = mem.stats()
            agent_stats[agent_name] = s
            totals["agents"] += 1
            totals["decisions"] += s["decisions"]
            totals["patterns"] += s["patterns"]
            totals["contacts"] += s["contacts"]
            totals["interactions"] += s["total_interactions"]

        return {"totals": totals, "agents": agent_stats}

    def prune_all(self, max_age_days=30):
        """Prune all agent memories."""
        total = 0
        for agent_name, mem in self._agents.items():
            removed = mem.prune(max_age_days)
            if removed > 0:
                total += removed
        mlog(f"prune_all: removed {total} total memories (cutoff {max_age_days}d)")
        return total


# ── MEMORY INDEX ──────────────────────────────────
class MemoryIndex:
    """Full-text search, tag-based retrieval, temporal queries."""

    def __init__(self, manager=None):
        self.manager = manager or MemoryManager(auto_prune=False)

    def search(self, query, max_results=50):
        """Full-text search across all agent memories."""
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        results = []

        for agent_name in self.manager.all_agents():
            mem = self.manager.get(agent_name)

            for d in mem.data.get("decisions", []):
                searchable = f"{d.get('context','')} {d.get('decision','')} {d.get('outcome','')}"
                if pattern.search(searchable):
                    results.append({
                        "agent": agent_name,
                        "type": "decision",
                        "timestamp": d.get("timestamp", ""),
                        "match": d.get("decision", ""),
                        "data": d,
                    })

            for p in mem.data.get("patterns", []):
                if pattern.search(p.get("description", "")):
                    results.append({
                        "agent": agent_name,
                        "type": "pattern",
                        "timestamp": p.get("last_seen", ""),
                        "match": p.get("description", ""),
                        "data": p,
                    })

            for cid, contact in mem.data.get("contacts", {}).items():
                searchable = cid
                for i in contact.get("interactions", []):
                    searchable += f" {i.get('summary', '')}"
                searchable += " ".join(contact.get("preference_notes", []))
                if pattern.search(searchable):
                    results.append({
                        "agent": agent_name,
                        "type": "contact",
                        "timestamp": "",
                        "match": cid,
                        "data": contact,
                    })

            ctx = mem.data.get("context", {})
            for e in ctx.get("recent_events", []):
                if pattern.search(str(e.get("event", ""))):
                    results.append({
                        "agent": agent_name,
                        "type": "context_event",
                        "timestamp": e.get("timestamp", ""),
                        "match": str(e.get("event", "")),
                        "data": e,
                    })
            for n in ctx.get("notes", []):
                if pattern.search(str(n.get("note", ""))):
                    results.append({
                        "agent": agent_name,
                        "type": "context_note",
                        "timestamp": n.get("timestamp", ""),
                        "match": str(n.get("note", "")),
                        "data": n,
                    })

        # Sort by timestamp descending
        results.sort(key=lambda r: r.get("timestamp", ""), reverse=True)
        return results[:max_results]

    def by_tag(self, tag):
        """Retrieve all memories with a specific tag."""
        results = []
        for agent_name in self.manager.all_agents():
            mem = self.manager.get(agent_name)

            for d in mem.data.get("decisions", []):
                if tag in d.get("tags", []):
                    results.append({"agent": agent_name, "type": "decision", "data": d})

            for p in mem.data.get("patterns", []):
                if tag in p.get("tags", []):
                    results.append({"agent": agent_name, "type": "pattern", "data": p})

            for cid, contact in mem.data.get("contacts", {}).items():
                if tag in contact.get("tags", []):
                    results.append({"agent": agent_name, "type": "contact", "data": contact})

        return results

    def since(self, days=7):
        """Get all memories from the last N days."""
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        results = []

        for agent_name in self.manager.all_agents():
            mem = self.manager.get(agent_name)

            for d in mem.data.get("decisions", []):
                if d.get("timestamp", "") >= cutoff:
                    results.append({"agent": agent_name, "type": "decision", "data": d})

            for p in mem.data.get("patterns", []):
                if p.get("last_seen", "") >= cutoff:
                    results.append({"agent": agent_name, "type": "pattern", "data": p})

            for cid, contact in mem.data.get("contacts", {}).items():
                recent = [i for i in contact.get("interactions", []) if i.get("date", "") >= cutoff]
                if recent:
                    results.append({
                        "agent": agent_name,
                        "type": "contact",
                        "data": {**contact, "interactions": recent},
                    })

            ctx = mem.data.get("context", {})
            for e in ctx.get("recent_events", []):
                if e.get("timestamp", "") >= cutoff:
                    results.append({"agent": agent_name, "type": "context_event", "data": e})

        # Sort by most recent first
        def sort_key(r):
            d = r["data"]
            return d.get("timestamp", d.get("last_seen", d.get("date", "")))
        results.sort(key=sort_key, reverse=True)

        return results


# ── INTEGRATION HOOKS ─────────────────────────────

def remember_decision(agent, context, decision, outcome=None, confidence=0.5, tags=None):
    """Quick hook: store a decision."""
    mem = AgentMemory(agent)
    return mem.remember("decisions", {
        "context": context,
        "decision": decision,
        "outcome": outcome,
        "confidence": confidence,
        "tags": tags or [],
    })


def recall_context(agent):
    """Quick hook: get recent relevant memories for an agent."""
    mem = AgentMemory(agent)
    ctx = mem.recall("context")
    recent_decisions = mem.recall("decisions", {"limit": 5})
    active_patterns = mem.recall("patterns", {"active_only": True})
    return {
        "context": ctx,
        "recent_decisions": recent_decisions,
        "active_patterns": active_patterns,
    }


def learn_pattern(agent, pattern_description, pattern_id=None, tags=None):
    """Quick hook: record or reinforce a pattern."""
    mem = AgentMemory(agent)
    return mem.remember("patterns", {
        "pattern_id": pattern_id,
        "description": pattern_description,
        "tags": tags or [],
    })


def remember_contact(agent, contact_id, interaction_type, summary, tags=None):
    """Quick hook: record a contact interaction."""
    mem = AgentMemory(agent)
    return mem.remember("contacts", {
        "contact_id": contact_id,
        "interaction": {"type": interaction_type, "summary": summary},
        "tags": tags or [],
    })


# ── CLI ───────────────────────────────────────────

COLORS = {
    "BOLD": "\033[1m",
    "DIM": "\033[2m",
    "GREEN": "\033[0;32m",
    "YELLOW": "\033[0;33m",
    "CYAN": "\033[0;36m",
    "RESET": "\033[0m",
}


def cli_stats():
    mgr = MemoryManager(auto_prune=False)
    s = mgr.stats()
    t = s["totals"]

    print(f"\n{'='*50}")
    print(f"  AGENT MEMORY STATISTICS")
    print(f"{'='*50}\n")
    print(f"  Agents with memory:  {t['agents']}")
    print(f"  Total decisions:     {t['decisions']}")
    print(f"  Total patterns:      {t['patterns']}")
    print(f"  Total contacts:      {t['contacts']}")
    print(f"  Total interactions:  {t['interactions']}")

    if s["agents"]:
        print(f"\n  {'Agent':<20s} {'Dec':>4s} {'Pat':>4s} {'Con':>4s} {'Int':>4s}  Freshest")
        print(f"  {'-'*20} {'-'*4} {'-'*4} {'-'*4} {'-'*4}  {'-'*19}")
        for name, a in sorted(s["agents"].items()):
            newest = (a.get("newest_memory") or "never")[:19]
            print(
                f"  {name:<20s} {a['decisions']:>4d} {a['patterns']:>4d} "
                f"{a['contacts']:>4d} {a['total_interactions']:>4d}  {newest}"
            )
    print()


def cli_recall(agent_name):
    mem = AgentMemory(agent_name)
    s = mem.stats()

    C = COLORS
    print(f"\n{C['BOLD']}Memory: {agent_name}{C['RESET']}")
    print(f"{'='*50}\n")

    # Decisions
    decisions = mem.recall("decisions", {"limit": 10})
    print(f"  {C['CYAN']}Decisions ({s['decisions']} total, showing last 10):{C['RESET']}")
    if decisions:
        for d in decisions:
            ts = d.get("timestamp", "")[:16]
            conf = d.get("confidence", 0)
            outcome = d.get("outcome", "-")
            print(f"    {C['DIM']}{ts}{C['RESET']}  [{conf:.0%}] {d.get('decision', '?')}")
            if outcome and outcome != "-":
                print(f"      outcome: {outcome}")
    else:
        print("    (none)")

    # Patterns
    patterns = mem.recall("patterns")
    print(f"\n  {C['CYAN']}Active Patterns ({s['active_patterns']}):{C['RESET']}")
    if patterns:
        for p in patterns:
            freq = p.get("frequency", 1)
            print(f"    [{freq}x] {p.get('description', '?')}")
    else:
        print("    (none)")

    # Contacts
    contacts = mem.recall("contacts")
    print(f"\n  {C['CYAN']}Contacts ({s['contacts']}):{C['RESET']}")
    if contacts:
        for c in contacts:
            cid = c.get("contact_id", "?")
            n_int = len(c.get("interactions", []))
            print(f"    {cid} ({n_int} interactions)")
            for i in c.get("interactions", [])[-3:]:
                print(f"      {C['DIM']}{i.get('date', '')[:16]}{C['RESET']} [{i.get('type', '')}] {i.get('summary', '')}")
    else:
        print("    (none)")

    # Context
    ctx = mem.recall("context")
    if isinstance(ctx, dict):
        task = ctx.get("current_task")
        n_events = len(ctx.get("recent_events", []))
        n_notes = len(ctx.get("notes", []))
        print(f"\n  {C['CYAN']}Context:{C['RESET']}")
        print(f"    Current task: {task or '(none)'}")
        print(f"    Recent events: {n_events}")
        print(f"    Notes: {n_notes}")

    print()


def cli_search(query):
    idx = MemoryIndex()
    results = idx.search(query)

    C = COLORS
    print(f"\n  Search: \"{query}\"")
    print(f"  {len(results)} result(s)\n")

    if not results:
        print("  No matches found.\n")
        return

    for r in results:
        ts = r.get("timestamp", "")[:16]
        agent = r.get("agent", "?")
        mtype = r.get("type", "?")
        match = r.get("match", "")
        # Truncate long matches
        if len(match) > 120:
            match = match[:117] + "..."
        print(f"  {C['DIM']}{ts}{C['RESET']}  {C['GREEN']}{agent}{C['RESET']}  [{mtype}]")
        print(f"    {match}")
        print()


def cli_prune():
    mgr = MemoryManager(auto_prune=False)
    total = mgr.prune_all(max_age_days=30)
    print(f"\n  Pruned {total} old memories (>30 days).\n")


def main():
    if len(sys.argv) < 2:
        print("Usage: agent_memory.py [stats|recall <agent>|search <query>|prune]")
        return

    cmd = sys.argv[1]

    if cmd == "stats":
        cli_stats()
    elif cmd == "recall":
        if len(sys.argv) < 3:
            print("Usage: agent_memory.py recall <agent_name>")
            return
        cli_recall(sys.argv[2])
    elif cmd == "search":
        if len(sys.argv) < 3:
            print("Usage: agent_memory.py search <query>")
            return
        cli_search(" ".join(sys.argv[2:]))
    elif cmd == "prune":
        cli_prune()
    else:
        print("Usage: agent_memory.py [stats|recall <agent>|search <query>|prune]")


if __name__ == "__main__":
    main()
