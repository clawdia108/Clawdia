"""Pipedrive CRM tool — wraps scripts/lib/pipedrive.py with structured interface."""

import sys
from pathlib import Path

# Reuse existing shared lib
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from lib.pipedrive import (
    pipedrive_api,
    pipedrive_get_all,
    pipedrive_search,
    fathom_api,
    PIPEDRIVE_BASE,
)

__all__ = [
    "pipedrive_api",
    "pipedrive_get_all",
    "pipedrive_search",
    "fathom_api",
    "PIPEDRIVE_BASE",
    "get_open_deals",
    "get_deal",
    "update_deal",
    "add_note",
    "create_activity",
]


def get_open_deals(token: str, user_id: str = "24403638") -> list[dict]:
    """Get all open deals for a user."""
    return pipedrive_get_all(token, "/deals", {
        "status": "open",
        "user_id": user_id,
    })


def get_deal(token: str, deal_id: int) -> dict | None:
    """Get a single deal by ID."""
    return pipedrive_api(token, "GET", f"/deals/{deal_id}")


def update_deal(token: str, deal_id: int, data: dict) -> dict | None:
    """Update a deal."""
    return pipedrive_api(token, "PUT", f"/deals/{deal_id}", data)


def add_note(token: str, deal_id: int, content: str, pinned: bool = False) -> dict | None:
    """Add a note to a deal."""
    return pipedrive_api(token, "POST", "/notes", {
        "deal_id": deal_id,
        "content": content,
        "pinned_to_deal_flag": 1 if pinned else 0,
    })


def create_activity(token: str, deal_id: int, subject: str,
                     activity_type: str = "call", due_date: str = "",
                     user_id: int = 24403638) -> dict | None:
    """Create a Pipedrive activity."""
    return pipedrive_api(token, "POST", "/activities", {
        "deal_id": deal_id,
        "subject": subject,
        "type": activity_type,
        "due_date": due_date,
        "user_id": user_id,
    })
