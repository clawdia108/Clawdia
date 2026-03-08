#!/usr/bin/env python3
"""
Strateg Recovery — generates a fresh DAILY-INTEL.md
Uses Ollama locally if available, otherwise creates a structured placeholder.
Runs standalone: python3 scripts/recover_intel.py
"""

import json
import subprocess
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/josefhofman/Clawdia")
OUTPUT = BASE / "intel" / "DAILY-INTEL.md"
RECOVERY_LOG = BASE / "logs" / "recovery.log"


def log_recovery(msg):
    RECOVERY_LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(RECOVERY_LOG, "a") as f:
        f.write(f"[{ts}] [recover_intel] {msg}\n")


def ollama_generate(prompt, timeout=45):
    """Try to get a short market summary from local Ollama"""
    try:
        payload = json.dumps({
            "model": "llama3.1:8b",
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.7, "num_predict": 300},
        })
        result = subprocess.run(
            ["curl", "-s", "-m", str(timeout),
             "http://localhost:11434/api/generate",
             "-d", payload],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("response", "").strip()
    except Exception:
        pass
    return None


def get_pipeline_context():
    """Grab deal names from scoring log for context"""
    scoring = BASE / "pipedrive" / "SCORING_LOG.md"
    if scoring.exists() and scoring.stat().st_size > 100:
        content = scoring.read_text()
        lines = content.splitlines()[:20]
        deals = [l for l in lines if "deal" in l.lower() or "score" in l.lower() or "|" in l]
        return deals[:8]
    return []


def generate_intel():
    now = datetime.now()
    date_str = now.strftime("%-d. %-m. %Y")
    time_str = now.strftime("%H:%M")

    sections = []
    sections.append(f"# Daily Intel — {date_str} (auto-recovery)")
    sections.append(f"\n> Strateg agent was stale. This is an auto-generated recovery digest at {time_str}.\n")

    # Try Ollama for a quick market take
    ollama_summary = ollama_generate(
        "You are a sales intelligence analyst for a Czech B2B SaaS company selling employee engagement surveys (Echo Pulse by Behavera). "
        "Write 3 brief bullet points about current trends in: 1) HR tech / employee engagement market, "
        "2) AI-powered sales automation, 3) Czech tech startup ecosystem. Keep it under 100 words total. "
        "Be specific and actionable."
    )

    if ollama_summary:
        sections.append("## Market Signals (Ollama-generated)")
        sections.append(ollama_summary)
        sections.append("")
    else:
        sections.append("## Market Signals")
        sections.append("- HR tech: Employee engagement platforms consolidating. Focus on ROI proof for mid-market.")
        sections.append("- AI sales: Automated follow-up and lead scoring becoming table stakes.")
        sections.append("- Czech tech: Growing demand for local-language AI solutions in enterprise.")
        sections.append("- *(Ollama unavailable — using static fallback)*\n")

    # Pipeline context
    pipeline = get_pipeline_context()
    if pipeline:
        sections.append("## Pipeline Intel")
        for line in pipeline[:5]:
            sections.append(f"  {line}")
        sections.append("")

    # Standing priorities
    sections.append("## Standing Intel Priorities")
    sections.append("1. Monitor competitor pricing changes (Culture Amp, Engagement Multiplier, Sloneek)")
    sections.append("2. Track Czech labor law changes affecting employee surveys")
    sections.append("3. Identify new vertical opportunities for Echo Pulse")
    sections.append("4. Watch for partnership/integration opportunities\n")

    sections.append("## Action Items")
    sections.append("- [ ] Full Strateg scan needed — this is recovery data only")
    sections.append("- [ ] Verify competitor watch in `intel/COMPETITOR_WATCH.md`")
    sections.append("- [ ] Check market signals in `intel/MARKET_SIGNALS.md`")

    sections.append(f"\n---\n*Recovery timestamp: {now.isoformat()}*")

    return "\n".join(sections)


def main():
    try:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        content = generate_intel()
        OUTPUT.write_text(content)
        log_recovery(f"SUCCESS — wrote {len(content)}B to {OUTPUT}")
        print(f"OK: DAILY-INTEL.md updated ({len(content)}B)")
        return 0
    except Exception as e:
        log_recovery(f"FAILED — {e}")
        print(f"ERROR: {e}", flush=True)
        return 1


if __name__ == "__main__":
    exit(main())
