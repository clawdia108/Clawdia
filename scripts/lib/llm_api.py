"""Multi-provider LLM API — tries Anthropic → OpenAI → Ollama."""

import json
import subprocess


def llm_generate(secrets, system_prompt, user_prompt, max_tokens=2500):
    """Generate text using best available LLM provider.

    Priority: Anthropic Claude → OpenAI GPT-4o → Ollama llama3.1
    Returns text or None.
    """
    # Try Anthropic first
    anthropic_key = secrets.get("ANTHROPIC_API_KEY", "")
    if anthropic_key:
        result = _call_anthropic(anthropic_key, system_prompt, user_prompt, max_tokens)
        if result:
            return result

    # Try OpenAI
    openai_key = secrets.get("OPENAI_API_KEY", "")
    if openai_key:
        result = _call_openai(openai_key, system_prompt, user_prompt, max_tokens)
        if result:
            return result

    # Try Ollama local (cap at 2000 tokens for local model)
    result = _call_ollama(system_prompt, user_prompt, min(max_tokens, 2000))
    if result:
        return result

    return None


def _call_anthropic(api_key, system_prompt, user_prompt, max_tokens):
    payload = json.dumps({
        "model": "claude-sonnet-4-6",
        "max_tokens": max_tokens,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_prompt}],
    })
    timeout = max(90, max_tokens // 8)
    try:
        result = subprocess.run(
            ["curl", "-s", "-m", str(timeout),
             "https://api.anthropic.com/v1/messages",
             "-H", f"x-api-key: {api_key}",
             "-H", "anthropic-version: 2023-06-01",
             "-H", "content-type: application/json",
             "-d", payload],
            capture_output=True, text=True, timeout=timeout + 10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if "content" in data and data["content"]:
                return data["content"][0].get("text", "").strip()
            # Check for billing error
            if data.get("error", {}).get("type") == "invalid_request_error":
                return None
    except Exception:
        pass
    return None


def _call_openai(api_key, system_prompt, user_prompt, max_tokens):
    payload = json.dumps({
        "model": "gpt-4o",
        "max_tokens": max_tokens,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    })
    timeout = max(90, max_tokens // 8)
    try:
        result = subprocess.run(
            ["curl", "-s", "-m", str(timeout),
             "https://api.openai.com/v1/chat/completions",
             "-H", f"Authorization: Bearer {api_key}",
             "-H", "Content-Type: application/json",
             "-d", payload],
            capture_output=True, text=True, timeout=timeout + 10,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            choices = data.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "").strip()
    except Exception:
        pass
    return None


def _call_ollama(system_prompt, user_prompt, max_tokens):
    payload = json.dumps({
        "model": "llama3.1:8b",
        "prompt": f"System: {system_prompt}\n\nUser: {user_prompt}",
        "stream": False,
        "options": {"temperature": 0.7, "num_predict": min(max_tokens, 2000)},
    })
    try:
        result = subprocess.run(
            ["curl", "-s", "-m", "120",
             "http://localhost:11434/api/generate",
             "-d", payload],
            capture_output=True, text=True, timeout=130,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("response", "").strip()
    except Exception:
        pass
    return None
