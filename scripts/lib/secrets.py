"""Credential loading — single source of truth."""

import os
from .paths import SECRETS_FILE, PIPEDRIVE_ENV


def load_secrets():
    """Load all secrets from .secrets/ files."""
    env = {}
    for p in [SECRETS_FILE, PIPEDRIVE_ENV]:
        if p.exists():
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                if line.startswith("export "):
                    line = line[7:]
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def get_api_key(env=None):
    """Get Anthropic API key from secrets or environment."""
    if env and env.get("ANTHROPIC_API_KEY"):
        return env["ANTHROPIC_API_KEY"]
    secrets = load_secrets()
    return secrets.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
