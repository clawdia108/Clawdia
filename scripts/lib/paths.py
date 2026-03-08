"""Common paths for Clawdia workspace."""

from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
SECRETS_FILE = WORKSPACE / ".secrets" / "ALL_CREDENTIALS.env"
PIPEDRIVE_ENV = WORKSPACE / ".secrets" / "pipedrive.env"
BUS_INBOX = WORKSPACE / "bus" / "inbox"
BUS_OUTBOX = WORKSPACE / "bus" / "outbox"
BUS_PROCESSED = WORKSPACE / "bus" / "processed"
BUS_DEAD_LETTER = WORKSPACE / "bus" / "dead-letter"
BUS_COWORK_STATUS = WORKSPACE / "bus" / "cowork-status"
BUS_CLAUDE_RESULTS = WORKSPACE / "bus" / "claude-results"
LOGS_DIR = WORKSPACE / "logs"
