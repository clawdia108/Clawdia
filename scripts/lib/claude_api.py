"""Anthropic Claude API calls — shared implementation."""

import json
import subprocess

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-sonnet-4-6"


def claude_generate(api_key, system_prompt, user_prompt, max_tokens=600, model=None):
    """Call Claude API and return text response.

    Returns None on failure.
    """
    if not api_key:
        return None

    payload = json.dumps({
        "model": model or DEFAULT_MODEL,
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    })

    timeout_sec = max(60, max_tokens // 10)
    try:
        result = subprocess.run(
            ["curl", "-s", "-m", str(timeout_sec), API_URL,
             "-H", f"x-api-key: {api_key}",
             "-H", "anthropic-version: 2023-06-01",
             "-H", "content-type: application/json",
             "-d", payload],
            capture_output=True, text=True, timeout=timeout_sec + 10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if "content" in data and data["content"]:
                return data["content"][0].get("text", "").strip()
    except Exception:
        pass
    return None
