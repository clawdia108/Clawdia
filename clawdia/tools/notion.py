"""Notion sync tool — wraps scripts/lib/notion.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from lib.notion import push_analysis, push_digest

__all__ = ["push_analysis", "push_digest"]
