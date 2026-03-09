"""Central configuration — paths, secrets, settings."""

import json
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
SECRETS_FILE = WORKSPACE / ".secrets" / "ALL_CREDENTIALS.env"
CONFIG_DIR = WORKSPACE / "config"
DATA_DIR = WORKSPACE / "data"
LOGS_DIR = WORKSPACE / "logs"
QUEUE_DIR = WORKSPACE / "bus"
KNOWLEDGE_DIR = WORKSPACE / "knowledge"


def load_secrets() -> dict:
    """Load all secrets from ALL_CREDENTIALS.env."""
    secrets = {}
    if not SECRETS_FILE.exists():
        return secrets
    for line in SECRETS_FILE.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and value:
            secrets[key] = value
    return secrets


def load_yaml(name: str) -> dict:
    """Load a YAML config file. Falls back to JSON if PyYAML not available."""
    yaml_path = CONFIG_DIR / f"{name}.yaml"
    json_path = CONFIG_DIR / f"{name}.json"

    # Try YAML first
    if yaml_path.exists():
        try:
            import yaml
            return yaml.safe_load(yaml_path.read_text()) or {}
        except ImportError:
            pass

    # Fallback to JSON
    if json_path.exists():
        return json.loads(json_path.read_text())

    # Try reading YAML as simple key-value (subset parser)
    if yaml_path.exists():
        return _parse_simple_yaml(yaml_path)

    return {}


def load_agent_config() -> dict:
    """Load agent configuration from config/agents.json."""
    return load_yaml("agents").get("agents", {})


def load_schedule_config() -> dict:
    """Load schedule configuration from config/schedules.json."""
    return load_yaml("schedules")


def _parse_simple_yaml(path: Path) -> dict:
    """Minimal YAML-like parser for simple configs (no arrays, no nesting)."""
    result = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ": " in line:
            key, _, value = line.partition(": ")
            result[key.strip()] = value.strip()
    return result
