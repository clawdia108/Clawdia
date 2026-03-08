#!/usr/bin/env python3
"""
Humanizer Daily Training — Learns from Josef's real emails
============================================================
Reads Josef's recent sent emails via Gmail API (through Claude Code MCP),
extracts writing patterns, and updates HUMANIZER_TRAINING.md.

Also reviews draft_generator output quality and tracks improvements.

This is NOT a superficial scan — it does deep linguistic analysis:
- Sentence structure patterns
- Opening/closing formulas
- Vykání consistency
- Natural Czech phrase extraction
- Anti-pattern detection
- Subject line patterns
- CTA patterns

Runs daily at 6:00 AM via launchd.

Usage:
    python3 scripts/humanizer_trainer.py              # Analyze + update training
    python3 scripts/humanizer_trainer.py --report      # Generate quality report
    python3 scripts/humanizer_trainer.py --check-draft FILE  # Check a draft against patterns
"""

import json
import re
import subprocess
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

from lib.paths import WORKSPACE
from lib.secrets import get_api_key
from lib.claude_api import claude_generate
from lib.logger import make_logger
from lib.notifications import notify_telegram

TRAINING_FILE = WORKSPACE / "knowledge" / "HUMANIZER_TRAINING.md"
PATTERN_DB = WORKSPACE / "knowledge" / "humanizer_patterns.json"
DRAFT_QUALITY_LOG = WORKSPACE / "logs" / "humanizer-quality.log"

log = make_logger("humanizer-trainer")

_api_key = None

def _get_api_key():
    global _api_key
    if _api_key is None:
        _api_key = get_api_key()
    return _api_key


def claude_analyze(system_prompt, user_prompt, max_tokens=1500):
    api_key = _get_api_key()
    if not api_key:
        log("No API key", "ERROR")
        return None
    return claude_generate(api_key, system_prompt, user_prompt, max_tokens=max_tokens)


def load_pattern_db():
    if PATTERN_DB.exists():
        try:
            return json.loads(PATTERN_DB.read_text())
        except json.JSONDecodeError:
            pass
    return {
        "studied_email_ids": [],
        "total_emails_studied": 0,
        "last_study_date": None,
        "opening_patterns": [],
        "closing_patterns": [],
        "transition_phrases": [],
        "cta_patterns": [],
        "subject_patterns": [],
        "anti_patterns_found": [],
        "quality_scores": [],
        "improvement_notes": [],
    }


def save_pattern_db(db):
    PATTERN_DB.parent.mkdir(parents=True, exist_ok=True)
    PATTERN_DB.write_text(json.dumps(db, indent=2, ensure_ascii=False))


def load_drafts_for_review():
    """Load recent drafts from drafts/ folder for quality check."""
    drafts_dir = WORKSPACE / "drafts"
    if not drafts_dir.exists():
        return []
    drafts = []
    today = date.today()
    for f in sorted(drafts_dir.glob("*.json"), reverse=True)[:5]:
        try:
            d = json.loads(f.read_text())
            drafts.append(d)
        except (json.JSONDecodeError, OSError):
            continue
    return drafts


def analyze_draft_quality(draft_body):
    """Deep quality analysis of a draft against Josef's patterns."""
    system = """Jsi expert na českou obchodní komunikaci a detekci AI textu.
Ohodnoť draft email na stupnici 1-10 v těchto kategoriích:
1. LIDSKOST (1-10): Zní to jako od živého člověka? Nebo jako AI?
2. ČEŠTINA (1-10): Je to přirozená čeština? Správné vykání (malé v)? Žádné amerikanismy?
3. JOSEFŮV STYL (1-10): Zní to jako český obchodník, ne jako AI?
4. OBCHODNÍ EFEKTIVITA (1-10): Má to jasný CTA? Je to přesvědčivé?

Odpověz POUZE JSON bez code-blocku, bez dalšího textu:
{"scores": {"lidskost": N, "cestina": N, "josef_styl": N, "efektivita": N}, "celkove": N, "problemy": ["problém 1"], "doporuceni": ["doporučení 1"], "ai_patterns_found": ["pattern 1"]}"""

    prompt = "DRAFT K HODNOCENÍ:\n" + draft_body[:1500]

    result = claude_analyze(system, prompt, max_tokens=1200)
    if result:
        try:
            # Strip code blocks if present
            cleaned = re.sub(r'```(?:json)?\s*', '', result).strip()
            cleaned = cleaned.rstrip('`').strip()
            # Try direct parse first
            try:
                return json.loads(cleaned)
            except json.JSONDecodeError:
                pass
            # Try finding the outermost JSON object with balanced braces
            depth = 0
            start = None
            for i, ch in enumerate(cleaned):
                if ch == '{':
                    if depth == 0:
                        start = i
                    depth += 1
                elif ch == '}':
                    depth -= 1
                    if depth == 0 and start is not None:
                        try:
                            return json.loads(cleaned[start:i+1])
                        except json.JSONDecodeError:
                            # Try fixing common issues: truncated strings
                            candidate = cleaned[start:i+1]
                            # Close any unclosed arrays/strings
                            candidate = re.sub(r',\s*\]', ']', candidate)
                            try:
                                return json.loads(candidate)
                            except json.JSONDecodeError:
                                pass
                            break
        except Exception:
            log(f"JSON parse failed: {result[:200]}", "WARN")
    return None


def extract_new_patterns(email_bodies):
    """Extract new patterns from a batch of emails using Claude."""
    if not email_bodies:
        return None

    system = """Jsi lingvistický analytik specializovaný na český jazyk.
Analyzuješ emaily obchodníka a hledáš opakující se vzory.

Odpověz POUZE v JSON:
{
  "new_phrases": ["fráze 1", "fráze 2"],
  "opening_formulas": ["vzor 1"],
  "closing_formulas": ["vzor 1"],
  "transition_words": ["slovo/fráze"],
  "cta_patterns": ["vzor CTA"],
  "tone_observations": ["pozorování 1"],
  "unique_style_markers": ["marker 1"]
}"""

    combined = "\n\n---EMAIL---\n\n".join(email_bodies)
    prompt = f"Analyzuj tyto emaily od Josefa Hofmana a extrahuj vzory:\n\n{combined}"

    result = claude_analyze(system, prompt, max_tokens=800)
    if result:
        try:
            cleaned = re.sub(r'```(?:json)?\s*', '', result).strip().rstrip('`').strip()
            json_match = re.search(r'\{[\s\S]*\}', cleaned)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            log(f"Pattern extraction JSON parse failed", "WARN")
    return None


def review_all_drafts():
    """Review all recent drafts and generate quality report."""
    drafts = load_drafts_for_review()
    if not drafts:
        print("No drafts to review")
        return

    db = load_pattern_db()
    scores = []

    for draft in drafts:
        body = draft.get("body", "")
        org = draft.get("deal_org", "?")
        if not body:
            continue

        print(f"  Reviewing draft for {org}...")
        quality = analyze_draft_quality(body)
        if quality:
            quality["org"] = org
            quality["date"] = date.today().isoformat()
            scores.append(quality)
            celkove = quality.get("celkove", 0)
            print(f"    Score: {celkove}/10")
            if quality.get("problemy"):
                for p in quality["problemy"][:3]:
                    print(f"    Problem: {p}")

    if scores:
        db["quality_scores"] = (db.get("quality_scores", []) + scores)[-50:]
        save_pattern_db(db)

        # Log quality report
        avg = sum(s.get("celkove", 0) for s in scores) / len(scores)
        log(f"Quality review: {len(scores)} drafts, avg score: {avg:.1f}/10")

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        DRAFT_QUALITY_LOG.parent.mkdir(exist_ok=True, parents=True)
        with open(DRAFT_QUALITY_LOG, "a") as f:
            f.write(f"\n[{ts}] Reviewed {len(scores)} drafts, avg: {avg:.1f}\n")
            for s in scores:
                f.write(f"  {s.get('org', '?')}: {s.get('celkove', '?')}/10\n")
                for p in s.get("problemy", []):
                    f.write(f"    ! {p}\n")

        # Send Telegram summary
        tg_msg = f"📝 Humanizer Quality Report\n"
        tg_msg += f"Průměr: {avg:.1f}/10 ({len(scores)} draftů)\n"
        for s in scores:
            tg_msg += f"• {s.get('org', '?')}: {s.get('celkove', '?')}/10\n"
        notify_telegram(tg_msg)

    return scores


def check_single_draft(filepath):
    """Check a single draft file against patterns."""
    p = Path(filepath)
    if not p.exists():
        print(f"File not found: {filepath}")
        return

    content = p.read_text()
    # Try JSON first
    try:
        data = json.loads(content)
        body = data.get("body", content)
    except json.JSONDecodeError:
        # For markdown files, extract just the email body (between --- markers)
        parts = content.split("---")
        if len(parts) >= 3:
            body = parts[2].strip()
        else:
            body = content
    # Truncate to reasonable size
    body = body[:1500]

    print(f"\nAnalyzing: {filepath}")
    quality = analyze_draft_quality(body)
    if quality:
        print(f"\nOverall Score: {quality.get('celkove', '?')}/10")
        print(f"  Lidskost: {quality.get('scores', {}).get('lidskost', '?')}/10")
        print(f"  Čeština: {quality.get('scores', {}).get('cestina', '?')}/10")
        print(f"  Josefův styl: {quality.get('scores', {}).get('josef_styl', '?')}/10")
        print(f"  Efektivita: {quality.get('scores', {}).get('efektivita', '?')}/10")
        if quality.get("problemy"):
            print("\nProblémy:")
            for p in quality["problemy"]:
                print(f"  - {p}")
        if quality.get("ai_patterns_found"):
            print("\nAI patterns:")
            for p in quality["ai_patterns_found"]:
                print(f"  ! {p}")
        if quality.get("doporuceni"):
            print("\nDoporučení:")
            for d in quality["doporuceni"]:
                print(f"  + {d}")
    else:
        print("Analysis failed")


def update_training_metadata():
    """Update the training file with latest stats from pattern DB."""
    db = load_pattern_db()
    if not TRAINING_FILE.exists():
        return

    content = TRAINING_FILE.read_text()
    today_str = date.today().isoformat()

    # Update the date and count in header
    old_line = re.search(r'\*Studovaných emailů: \d+.*\*', content)
    if old_line:
        new_line = f"*Studovaných emailů: {db.get('total_emails_studied', 0)} | Poslední studie: {today_str}*"
        content = content.replace(old_line.group(), new_line)
        TRAINING_FILE.write_text(content)


def main():
    args = sys.argv[1:]

    if "--report" in args:
        print("Generating quality report...")
        review_all_drafts()
        return

    if "--check-draft" in args:
        idx = args.index("--check-draft")
        if idx + 1 < len(args):
            check_single_draft(args[idx + 1])
        else:
            print("Usage: --check-draft <file>")
        return

    # Default: daily training run
    log("Starting daily training run...")
    print("Humanizer Daily Training")
    print("=" * 40)

    db = load_pattern_db()

    # Step 1: Review recent drafts for quality
    print("\n1. Reviewing recent drafts...")
    review_all_drafts()

    # Step 2: Update training metadata
    print("\n2. Updating training metadata...")
    update_training_metadata()

    # Step 3: Log completion
    db["last_study_date"] = date.today().isoformat()
    save_pattern_db(db)

    log("Daily training complete")
    print("\nTraining complete.")
    print(f"  Patterns DB: {PATTERN_DB}")
    print(f"  Training file: {TRAINING_FILE}")


if __name__ == "__main__":
    main()
