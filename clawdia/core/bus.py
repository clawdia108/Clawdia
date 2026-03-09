"""Typed message bus — file-based queue with validation and TTL."""

import json
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from .config import QUEUE_DIR
from .logging import get_logger

log = get_logger("bus", "bus.log")


@dataclass
class Message:
    """Typed message for inter-agent communication."""
    topic: str           # e.g., "deal.scored", "email.drafted"
    payload: dict        # actual data
    source: str = ""     # which agent/component sent it
    target: str = ""     # which agent should receive ("" = any subscriber)
    priority: int = 2    # 1=urgent, 2=normal, 3=low
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    ttl_hours: int = 24  # auto-expire after this

    def is_expired(self) -> bool:
        try:
            created = datetime.fromisoformat(self.created_at)
            return datetime.now() - created > timedelta(hours=self.ttl_hours)
        except (ValueError, TypeError):
            return False

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "Message":
        known = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known}
        return cls(**filtered)


VALID_TOPICS = {
    "deal.score", "deal.health", "deal.stale", "deal.writeback",
    "email.draft", "email.followup",
    "spin.prep",
    "outreach.morning", "outreach.followup", "outreach.cold",
    "intel.signals", "intel.market", "intel.competitive",
    "calendar.prep", "calendar.sync", "calendar.next_step",
    "health.check", "health.anomaly", "health.schema",
    "sync.notion", "sync.graph", "sync.dedup",
    "system.backup", "system.status",
    "guard.pipeline", "guard.activity",
    "plan.weekly", "plan.strategic",
    "comm.digest", "comm.standup", "comm.scorecard",
    "nudge.send",
    "report.generate",
}


def validate_message(msg: Message) -> list[str]:
    """Validate a message, return list of errors (empty = valid)."""
    errors = []
    if not msg.topic:
        errors.append("missing topic")
    if not msg.payload and not isinstance(msg.payload, dict):
        errors.append("payload must be a dict")
    if msg.priority not in (1, 2, 3):
        errors.append(f"invalid priority: {msg.priority}")
    if msg.ttl_hours < 1 or msg.ttl_hours > 168:
        errors.append(f"ttl_hours must be 1-168, got {msg.ttl_hours}")
    return errors


class MessageBus:
    """File-based message bus with topic routing and TTL."""

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = base_dir or QUEUE_DIR
        self.inbox_dir = self.base_dir / "inbox"
        self.outbox_dir = self.base_dir / "outbox"
        self.dead_letter_dir = self.base_dir / "dead-letter"
        self._subscribers: dict[str, list[Callable]] = {}

        for d in [self.inbox_dir, self.outbox_dir, self.dead_letter_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def publish(self, msg: Message):
        """Publish a message to the bus. Validates before writing."""
        errors = validate_message(msg)
        if errors:
            log.warn(f"Message validation failed: {errors}", topic=msg.topic)
            return

        if msg.target:
            # Direct delivery to agent inbox
            agent_dir = self.inbox_dir / msg.target
            agent_dir.mkdir(parents=True, exist_ok=True)
            fpath = agent_dir / f"{msg.id}.json"
        else:
            # Broadcast to outbox
            fpath = self.outbox_dir / f"{msg.id}.json"

        fpath.write_text(json.dumps(msg.to_dict(), ensure_ascii=False, indent=2))
        log.info(f"Published: {msg.topic} → {msg.target or 'broadcast'}", id=msg.id)

    def consume(self, agent_name: str, limit: int = 10) -> list[Message]:
        """Consume messages from an agent's inbox. Returns and deletes."""
        agent_dir = self.inbox_dir / agent_name
        if not agent_dir.exists():
            return []

        messages = []
        for f in sorted(agent_dir.glob("*.json"))[:limit]:
            try:
                data = json.loads(f.read_text())
                msg = Message.from_dict(data)
                if msg.is_expired():
                    self._dead_letter(f, "expired")
                    continue
                messages.append(msg)
                f.unlink()
            except Exception as e:
                log.error(f"Failed to consume {f.name}: {e}")
                self._dead_letter(f, str(e))

        return sorted(messages, key=lambda m: m.priority)

    def peek(self, agent_name: str) -> int:
        """Count messages in an agent's inbox without consuming."""
        agent_dir = self.inbox_dir / agent_name
        if not agent_dir.exists():
            return 0
        return len(list(agent_dir.glob("*.json")))

    def subscribe(self, topic_pattern: str, handler: Callable):
        """Subscribe to messages matching a topic pattern."""
        self._subscribers.setdefault(topic_pattern, []).append(handler)

    def process_outbox(self):
        """Route outbox messages to subscribed agents."""
        for f in sorted(self.outbox_dir.glob("*.json")):
            try:
                data = json.loads(f.read_text())
                msg = Message.from_dict(data)
                if msg.is_expired():
                    self._dead_letter(f, "expired")
                    continue

                delivered = False
                for pattern, handlers in self._subscribers.items():
                    if self._topic_matches(msg.topic, pattern):
                        for handler in handlers:
                            try:
                                handler(msg)
                                delivered = True
                            except Exception as e:
                                log.error(f"Handler error for {msg.topic}: {e}")

                if delivered:
                    f.unlink()
                # If not delivered, leave in outbox for next cycle
            except Exception as e:
                log.error(f"Failed to process outbox {f.name}: {e}")

    def cleanup(self, max_age_hours: int = 48):
        """Remove expired messages from all queues."""
        cleaned = 0
        for agent_dir in self.inbox_dir.iterdir():
            if not agent_dir.is_dir():
                continue
            for f in agent_dir.glob("*.json"):
                try:
                    data = json.loads(f.read_text())
                    msg = Message.from_dict(data)
                    if msg.is_expired():
                        self._dead_letter(f, "cleanup")
                        cleaned += 1
                except Exception:
                    self._dead_letter(f, "parse_error")
                    cleaned += 1

        # Also clean dead-letter older than max_age_hours
        cutoff = datetime.now() - timedelta(hours=max_age_hours * 3)
        for f in self.dead_letter_dir.glob("*.json"):
            try:
                age = datetime.now().timestamp() - f.stat().st_mtime
                if age > max_age_hours * 3 * 3600:
                    f.unlink()
                    cleaned += 1
            except Exception:
                pass

        if cleaned:
            log.info(f"Cleaned {cleaned} expired messages")
        return cleaned

    def stats(self) -> dict:
        """Get bus statistics."""
        inbox_counts = {}
        for agent_dir in self.inbox_dir.iterdir():
            if agent_dir.is_dir():
                inbox_counts[agent_dir.name] = len(list(agent_dir.glob("*.json")))

        return {
            "inbox": inbox_counts,
            "outbox": len(list(self.outbox_dir.glob("*.json"))),
            "dead_letter": len(list(self.dead_letter_dir.glob("*.json"))),
            "total_inbox": sum(inbox_counts.values()),
        }

    def purge_dead_letters(self) -> int:
        """Delete ALL dead-letter messages. Returns count deleted."""
        count = 0
        for f in self.dead_letter_dir.glob("*.json"):
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
        # Also clean non-json files
        for f in self.dead_letter_dir.glob("*"):
            if f.is_file():
                try:
                    f.unlink()
                    count += 1
                except Exception:
                    pass
        log.info(f"Purged {count} dead-letter messages")
        return count

    def _dead_letter(self, filepath: Path, reason: str):
        """Move a failed message to dead-letter."""
        try:
            dest = self.dead_letter_dir / filepath.name
            filepath.rename(dest)
        except Exception:
            try:
                filepath.unlink()
            except Exception:
                pass

    @staticmethod
    def _topic_matches(topic: str, pattern: str) -> bool:
        """Simple topic pattern matching. '*' matches one segment, '#' matches any."""
        if pattern == "#":
            return True
        if "*" not in pattern and "#" not in pattern:
            return topic == pattern
        t_parts = topic.split(".")
        p_parts = pattern.split(".")
        if len(t_parts) != len(p_parts) and "#" not in pattern:
            return False
        for t, p in zip(t_parts, p_parts):
            if p == "*":
                continue
            if p == "#":
                return True
            if t != p:
                return False
        return len(t_parts) == len(p_parts)
