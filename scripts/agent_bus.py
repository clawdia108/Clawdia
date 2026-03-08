#!/usr/bin/env python3
"""
Agent Communication Bus — Message routing between agents
=========================================================
File-based pub/sub system for inter-agent communication.

Message types:
  - EVENT: One-way notification (agent publishes, subscribers receive)
  - REQUEST: Request-reply pattern (agent asks, target responds)
  - HANDOFF: Pass work product from one agent to another
  - REVIEW: Submit output for quality review (multi-round)

Message lifecycle:
  outbox/ → inbox/{target}/ → processed/ (or dead-letter/ on failure)

Routing:
  - Topic-based subscriptions defined in SUBSCRIPTIONS
  - Priority routing (P0 messages processed first)
  - TTL: messages expire after max_age_hours
"""

import json
import time
import hashlib
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

BASE = Path("/Users/josefhofman/Clawdia")
BUS_DIR = BASE / "bus"
OUTBOX = BUS_DIR / "outbox"
INBOX = BUS_DIR / "inbox"
PROCESSED = BUS_DIR / "processed"
DEAD_LETTER = BUS_DIR / "dead-letter"
BUS_LOG = BASE / "logs" / "bus.log"

# Topic subscriptions: topic → list of subscriber agents
SUBSCRIPTIONS = {
    # Sales pipeline events
    "pipeline.scored": ["postak", "udrzbar", "textar"],
    "pipeline.stale_deals": ["postak", "udrzbar"],
    "pipeline.deal_won": ["hlidac", "textar", "archivar"],
    "pipeline.deal_lost": ["hlidac", "strateg"],
    "pipeline.high_value_deal": ["obchodak", "textar"],

    # Content events
    "content.draft_ready": ["kontrolor"],
    "content.review_passed": ["postak"],
    "content.review_failed": ["textar", "postak"],
    "content.approved": ["postak"],

    # System events
    "system.morning_briefing": ["kalendar", "planovac", "udrzbar"],
    "system.agent_recovered": ["kontrolor", "hlidac"],
    "system.health_check": ["kontrolor"],
    "system.knowledge_synced": ["archivar", "strateg"],
    "system.nightly_complete": ["hlidac"],

    # Approval events
    "approval.submitted": ["kontrolor"],
    "approval.approved": ["postak", "textar"],
    "approval.rejected": ["textar"],

    # Research events
    "research.intel_ready": ["textar", "obchodak"],
    "research.competitor_found": ["strateg", "udrzbar"],

    # Calendar events
    "calendar.meeting_soon": ["planovac", "kalendar"],
    "calendar.day_planned": ["planovac"],

    # Cowork bridge events (Claude Desktop scheduled tasks)
    "system.cowork_complete": ["kontrolor", "hlidac"],
}

# Message priorities
PRIORITY_ORDER = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}

DEFAULT_TTL_HOURS = 24


def bus_log(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    BUS_LOG.parent.mkdir(exist_ok=True)
    with open(BUS_LOG, "a") as f:
        f.write(line + "\n")


def generate_message_id():
    return hashlib.md5(f"{time.time()}:{id(object())}".encode()).hexdigest()[:16]


class Message:
    """A message on the agent bus"""

    def __init__(self, source, topic, msg_type="EVENT", payload=None,
                 target=None, priority="P2", ttl_hours=DEFAULT_TTL_HOURS,
                 reply_to=None, correlation_id=None):
        self.id = generate_message_id()
        self.source = source
        self.topic = topic
        self.type = msg_type  # EVENT, REQUEST, HANDOFF, REVIEW
        self.payload = payload or {}
        self.target = target  # Specific agent (for REQUEST/HANDOFF) or None (for pub/sub)
        self.priority = priority
        self.ttl_hours = ttl_hours
        self.reply_to = reply_to  # For request-reply pattern
        self.correlation_id = correlation_id or self.id  # Groups related messages
        self.created_at = datetime.now().isoformat()
        self.status = "pending"
        self.delivery_attempts = 0
        self.max_retries = 3

    def to_dict(self):
        return {
            "id": self.id,
            "source": self.source,
            "topic": self.topic,
            "type": self.type,
            "payload": self.payload,
            "target": self.target,
            "priority": self.priority,
            "ttl_hours": self.ttl_hours,
            "reply_to": self.reply_to,
            "correlation_id": self.correlation_id,
            "created_at": self.created_at,
            "status": self.status,
            "delivery_attempts": self.delivery_attempts,
            "max_retries": self.max_retries,
        }

    @classmethod
    def from_dict(cls, data):
        msg = cls.__new__(cls)
        for k, v in data.items():
            setattr(msg, k, v)
        return msg

    @classmethod
    def from_file(cls, path):
        data = json.loads(path.read_text())
        return cls.from_dict(data)

    def save(self, directory):
        directory.mkdir(parents=True, exist_ok=True)
        filename = f"{self.priority}_{self.id}_{self.topic.replace('.', '_')}.json"
        path = directory / filename
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False))
        return path

    def is_expired(self):
        created = datetime.fromisoformat(self.created_at)
        return datetime.now() > created + timedelta(hours=self.ttl_hours)


class AgentBus:
    """Central message bus for agent communication"""

    def __init__(self):
        for d in [OUTBOX, INBOX, PROCESSED, DEAD_LETTER]:
            d.mkdir(parents=True, exist_ok=True)

    def publish(self, source, topic, payload=None, priority="P2",
                msg_type="EVENT", target=None, ttl_hours=DEFAULT_TTL_HOURS,
                reply_to=None, correlation_id=None):
        """Publish a message to the bus"""
        msg = Message(
            source=source, topic=topic, payload=payload,
            priority=priority, msg_type=msg_type, target=target,
            ttl_hours=ttl_hours, reply_to=reply_to,
            correlation_id=correlation_id,
        )
        path = msg.save(OUTBOX)
        bus_log(f"PUBLISH [{msg.type}] {source} → {topic} (id={msg.id}, priority={priority})")
        return msg

    def request(self, source, target, topic, payload=None, priority="P1"):
        """Send a request to a specific agent (expects reply)"""
        return self.publish(
            source=source, topic=topic, payload=payload,
            priority=priority, msg_type="REQUEST", target=target,
        )

    def reply(self, original_msg, source, payload=None):
        """Reply to a REQUEST message"""
        return self.publish(
            source=source, topic=f"{original_msg.topic}.reply",
            payload=payload, priority=original_msg.priority,
            msg_type="EVENT", target=original_msg.source,
            reply_to=original_msg.id,
            correlation_id=original_msg.correlation_id,
        )

    def handoff(self, source, target, topic, payload=None, priority="P1"):
        """Hand off work product from one agent to another"""
        return self.publish(
            source=source, topic=topic, payload=payload,
            priority=priority, msg_type="HANDOFF", target=target,
        )

    def submit_for_review(self, source, payload, priority="P1"):
        """Submit output for quality review"""
        return self.publish(
            source=source, topic="content.draft_ready",
            payload={
                "author": source,
                "content": payload.get("content", ""),
                "content_type": payload.get("content_type", "text"),
                "context": payload.get("context", {}),
                "review_round": payload.get("review_round", 1),
                "max_rounds": payload.get("max_rounds", 3),
            },
            priority=priority, msg_type="REVIEW",
        )

    def route_messages(self):
        """Process outbox: route messages to subscriber inboxes"""
        routed = 0
        expired = 0
        dead = 0

        # Sort by priority (P0 first)
        messages = sorted(
            OUTBOX.glob("*.json"),
            key=lambda p: p.name,  # Filenames start with priority
        )

        for msg_file in messages:
            try:
                msg = Message.from_file(msg_file)

                # Check TTL
                if msg.is_expired():
                    msg.status = "expired"
                    msg_file.rename(DEAD_LETTER / msg_file.name)
                    expired += 1
                    bus_log(f"EXPIRED {msg.id} ({msg.topic})", "WARN")
                    continue

                # Determine targets
                if msg.target:
                    # Direct message to specific agent
                    targets = [msg.target]
                else:
                    # Pub/sub: find subscribers for this topic
                    targets = SUBSCRIPTIONS.get(msg.topic, [])

                if not targets:
                    bus_log(f"NO SUBSCRIBERS for {msg.topic} (id={msg.id})", "WARN")
                    msg.status = "no_subscribers"
                    msg_file.rename(DEAD_LETTER / msg_file.name)
                    dead += 1
                    continue

                # Deliver to each target's inbox
                for target in targets:
                    target_inbox = INBOX / target
                    target_inbox.mkdir(parents=True, exist_ok=True)
                    delivery = msg.to_dict()
                    delivery["delivered_to"] = target
                    delivery["delivered_at"] = datetime.now().isoformat()
                    delivery["status"] = "delivered"
                    delivery_file = target_inbox / msg_file.name
                    delivery_file.write_text(json.dumps(delivery, indent=2, ensure_ascii=False))

                # Move original to processed
                msg.status = "routed"
                msg_file.rename(PROCESSED / msg_file.name)
                routed += 1

                bus_log(f"ROUTED {msg.id} ({msg.topic}) → {', '.join(targets)}")

            except (json.JSONDecodeError, OSError) as e:
                bus_log(f"ERROR processing {msg_file.name}: {e}", "ERROR")
                msg_file.rename(DEAD_LETTER / msg_file.name)
                dead += 1

        return {"routed": routed, "expired": expired, "dead": dead}

    def get_inbox(self, agent, limit=10):
        """Get pending messages for an agent, sorted by priority"""
        agent_inbox = INBOX / agent
        if not agent_inbox.exists():
            return []

        messages = []
        for f in sorted(agent_inbox.glob("*.json"))[:limit]:
            try:
                messages.append(Message.from_dict(json.loads(f.read_text())))
            except (json.JSONDecodeError, OSError):
                continue

        return messages

    def acknowledge(self, agent, message_id):
        """Mark a message as processed by an agent"""
        agent_inbox = INBOX / agent
        if not agent_inbox.exists():
            return False

        for f in agent_inbox.glob(f"*{message_id}*.json"):
            ack_dir = PROCESSED / agent
            ack_dir.mkdir(parents=True, exist_ok=True)
            f.rename(ack_dir / f.name)
            bus_log(f"ACK {message_id} by {agent}")
            return True
        return False

    def stats(self):
        """Get bus statistics"""
        outbox = list(OUTBOX.glob("*.json"))
        processed = list(PROCESSED.glob("*.json"))
        dead = list(DEAD_LETTER.glob("*.json"))

        inbox_counts = {}
        if INBOX.exists():
            for agent_dir in INBOX.iterdir():
                if agent_dir.is_dir():
                    inbox_counts[agent_dir.name] = len(list(agent_dir.glob("*.json")))

        return {
            "outbox": len(outbox),
            "inbox": inbox_counts,
            "processed": len(processed),
            "dead_letter": len(dead),
            "total_in_flight": len(outbox) + sum(inbox_counts.values()),
        }

    def cleanup(self, max_age_days=7):
        """Remove old processed and dead-letter messages"""
        now = time.time()
        cleaned = 0
        for directory in [PROCESSED, DEAD_LETTER]:
            for f in directory.rglob("*.json"):
                if (now - f.stat().st_mtime) > max_age_days * 86400:
                    f.unlink()
                    cleaned += 1
        if cleaned:
            bus_log(f"CLEANUP: removed {cleaned} old messages")
        return cleaned


# ── REVIEW PROTOCOL ──────────────────────────────────
class ReviewProtocol:
    """Multi-round review protocol for agent outputs"""

    MAX_ROUNDS = 3
    REVIEW_DIR = BASE / "reviews" / "in-progress"

    def __init__(self, bus):
        self.bus = bus
        self.REVIEW_DIR.mkdir(parents=True, exist_ok=True)

    def submit(self, author, content, content_type="email_draft", context=None):
        """Submit content for review. Returns review_id."""
        review = {
            "review_id": generate_message_id(),
            "author": author,
            "content": content,
            "content_type": content_type,
            "context": context or {},
            "status": "pending_review",
            "round": 1,
            "max_rounds": self.MAX_ROUNDS,
            "history": [],
            "created_at": datetime.now().isoformat(),
        }

        review_file = self.REVIEW_DIR / f"{review['review_id']}.json"
        review_file.write_text(json.dumps(review, indent=2, ensure_ascii=False))

        # Publish to reviewer
        self.bus.publish(
            source=author,
            topic="content.draft_ready",
            payload={"review_id": review["review_id"], "round": 1, "content_type": content_type},
            priority="P1",
            msg_type="REVIEW",
        )

        bus_log(f"REVIEW submitted: {review['review_id']} by {author} (type={content_type})")
        return review["review_id"]

    def review(self, review_id, reviewer, verdict, feedback=None, revised_content=None):
        """Submit review verdict: 'approve', 'reject', or 'revise'."""
        review_file = self.REVIEW_DIR / f"{review_id}.json"
        if not review_file.exists():
            return None

        review = json.loads(review_file.read_text())

        # Record this round
        review["history"].append({
            "round": review["round"],
            "kontrolor": reviewer,
            "verdict": verdict,
            "feedback": feedback,
            "timestamp": datetime.now().isoformat(),
        })

        if verdict == "approve":
            review["status"] = "approved"
            review_file.write_text(json.dumps(review, indent=2, ensure_ascii=False))

            # Notify author
            self.bus.publish(
                source=reviewer,
                topic="content.review_passed",
                payload={"review_id": review_id, "author": review["author"]},
                priority="P1",
            )

            # Move to approval queue if high-risk
            if review.get("context", {}).get("risk_level") == "high":
                self.bus.publish(
                    source=reviewer,
                    topic="approval.submitted",
                    payload={
                        "review_id": review_id,
                        "content": review["content"],
                        "author": review["author"],
                    },
                    priority="P0",
                )

            bus_log(f"REVIEW APPROVED: {review_id} after {review['round']} round(s)")

        elif verdict == "revise" and review["round"] < self.MAX_ROUNDS:
            review["round"] += 1
            if revised_content:
                review["content"] = revised_content
            review["status"] = "revision_requested"
            review_file.write_text(json.dumps(review, indent=2, ensure_ascii=False))

            # Send back to author for revision
            self.bus.publish(
                source=reviewer,
                topic="content.review_failed",
                payload={
                    "review_id": review_id,
                    "feedback": feedback,
                    "round": review["round"],
                    "author": review["author"],
                },
                priority="P1",
            )

            bus_log(f"REVIEW REVISE: {review_id} round {review['round']}, feedback: {feedback[:100] if feedback else 'none'}")

        else:
            review["status"] = "rejected"
            review_file.write_text(json.dumps(review, indent=2, ensure_ascii=False))

            self.bus.publish(
                source=reviewer,
                topic="content.review_failed",
                payload={
                    "review_id": review_id,
                    "feedback": feedback,
                    "final": True,
                    "author": review["author"],
                },
                priority="P1",
            )

            bus_log(f"REVIEW REJECTED: {review_id} after {review['round']} round(s)")

        return review

    def get_pending_reviews(self):
        """Get all reviews pending review"""
        pending = []
        for f in self.REVIEW_DIR.glob("*.json"):
            try:
                review = json.loads(f.read_text())
                if review.get("status") in ("pending_review", "revision_requested"):
                    pending.append(review)
            except (json.JSONDecodeError, OSError):
                continue
        return sorted(pending, key=lambda r: r.get("created_at", ""))

    def metrics(self):
        """Review protocol metrics"""
        total = 0
        approved = 0
        rejected = 0
        total_rounds = 0

        for f in self.REVIEW_DIR.glob("*.json"):
            try:
                review = json.loads(f.read_text())
                total += 1
                if review.get("status") == "approved":
                    approved += 1
                    total_rounds += review.get("round", 1)
                elif review.get("status") == "rejected":
                    rejected += 1
            except (json.JSONDecodeError, OSError):
                continue

        return {
            "total_reviews": total,
            "approved": approved,
            "rejected": rejected,
            "pending": total - approved - rejected,
            "avg_rounds": round(total_rounds / approved, 1) if approved else 0,
            "pass_rate": round(approved / total * 100, 1) if total else 0,
        }


# ── CONVENIENCE FUNCTIONS ────────────────────────────
def get_bus():
    """Get singleton bus instance"""
    return AgentBus()


def publish(source, topic, payload=None, priority="P2"):
    """Quick publish helper"""
    return get_bus().publish(source, topic, payload, priority)


def route_all():
    """Route all pending messages"""
    return get_bus().route_messages()


if __name__ == "__main__":
    import sys

    bus = AgentBus()

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "route":
            result = bus.route_messages()
            print(json.dumps(result, indent=2))

        elif cmd == "stats":
            result = bus.stats()
            print(json.dumps(result, indent=2))

        elif cmd == "inbox" and len(sys.argv) > 2:
            agent = sys.argv[2]
            messages = bus.get_inbox(agent)
            for msg in messages:
                print(f"  [{msg.priority}] {msg.topic} from {msg.source} ({msg.type})")

        elif cmd == "cleanup":
            cleaned = bus.cleanup()
            print(f"Cleaned {cleaned} old messages")

        elif cmd == "reviews":
            protocol = ReviewProtocol(bus)
            metrics = protocol.metrics()
            print(json.dumps(metrics, indent=2))
            pending = protocol.get_pending_reviews()
            if pending:
                print(f"\n{len(pending)} pending reviews:")
                for r in pending:
                    print(f"  [{r['review_id']}] {r['author']} round {r['round']}/{r['max_rounds']}")

        else:
            print("Usage: agent_bus.py [route|stats|inbox <agent>|cleanup|reviews]")
    else:
        print("Agent Bus Status:")
        print(json.dumps(bus.stats(), indent=2))
