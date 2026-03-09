#!/usr/bin/env python3
"""
SPIN Prep Generator — automatická příprava SPIN briefů pro demo cally.

Workflow:
1. Najde deals s aktivitami v příštích 48h (nebo zadaný deal)
2. Pro každý deal: research firmy, kontakt, TLDV transkripty
3. Vygeneruje kompletní SPIN brief přes Claude API
4. Zapíše brief jako Pipedrive note
5. Pošle morning summary přes Telegram

Usage:
  python3 scripts/spin_prep_generator.py              # auto: všechny deals s aktivitou zítra
  python3 scripts/spin_prep_generator.py --deal 360    # konkrétní deal
  python3 scripts/spin_prep_generator.py --dry-run     # jen ukáže co by udělal
  python3 scripts/spin_prep_generator.py --all-open    # všechny open deals bez SPIN note
"""

import json
import sys
import re
import subprocess
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.paths import WORKSPACE, LOGS_DIR
from lib.secrets import load_secrets
from lib.notifications import notify_telegram
from lib.pipedrive import pipedrive_api, fathom_api

# Config
TLDV_EXPORT = Path("/Users/josefhofman/Desktop/tldv_full_export.json")
SPIN_QUESTIONS_DIR = WORKSPACE / "skills" / "spin-questions" / "banks"
SIGNALS_DIR = WORKSPACE / "knowledge" / "signals"
LOG_FILE = LOGS_DIR / "spin-prep.log"
KNOWN_DEALS_FILE = WORKSPACE / "knowledge" / "spin_prepped_deals.json"


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")



def get_upcoming_deals(token, hours=48):
    """Get deals with activities in the next N hours."""
    now = datetime.now()
    cutoff = now + timedelta(hours=hours)

    activities = pipedrive_api(token, "GET", "/activities", {
        "user_id": "24403638",
        "done": "0",
        "start": "0",
        "limit": "100",
        "sort": "due_date ASC",
    })
    if not activities:
        return []

    deal_ids = set()
    deal_activities = {}
    for act in activities:
        deal_id = act.get("deal_id")
        if not deal_id:
            continue

        due = act.get("due_date", "")
        if not due:
            continue

        try:
            due_dt = datetime.strptime(due, "%Y-%m-%d")
        except ValueError:
            continue

        if due_dt <= cutoff:
            deal_ids.add(deal_id)
            if deal_id not in deal_activities:
                deal_activities[deal_id] = []
            deal_activities[deal_id].append({
                "type": act.get("type", ""),
                "subject": act.get("subject", ""),
                "due_date": due,
                "due_time": act.get("due_time", ""),
            })

    deals = []
    for did in deal_ids:
        deal = pipedrive_api(token, "GET", f"/deals/{did}")
        if deal:
            deal["_upcoming_activities"] = deal_activities.get(did, [])
            deals.append(deal)

    return deals


def get_deal_full(token, deal_id):
    """Get single deal with all context."""
    deal = pipedrive_api(token, "GET", f"/deals/{deal_id}")
    if not deal:
        return None

    # Get activities
    activities = pipedrive_api(token, "GET", f"/deals/{deal_id}/activities", {
        "start": "0", "limit": "100",
    })
    deal["_all_activities"] = activities or []

    # Get person
    person_id = deal.get("person_id", {})
    if isinstance(person_id, dict):
        person_id = person_id.get("value")
    if person_id:
        person = pipedrive_api(token, "GET", f"/persons/{person_id}")
        deal["_person"] = person
    else:
        deal["_person"] = None

    # Get org
    org_id = deal.get("org_id", {})
    if isinstance(org_id, dict):
        org_id = org_id.get("value")
    if org_id:
        org = pipedrive_api(token, "GET", f"/organizations/{org_id}")
        deal["_org"] = org
    else:
        deal["_org"] = None

    # Get existing notes
    notes = pipedrive_api(token, "GET", "/notes", {
        "deal_id": str(deal_id), "start": "0", "limit": "20",
    })
    deal["_notes"] = notes or []

    return deal


def search_tldv_transcripts(company_name, contact_name=None):
    """Search TLDV export for transcripts matching this company/contact."""
    if not TLDV_EXPORT.exists():
        return []

    try:
        with open(TLDV_EXPORT) as f:
            data = json.load(f)
    except Exception:
        return []

    meetings = data.get("meetings", [])
    matches = []

    search_terms = [company_name.lower()] if company_name else []
    if contact_name:
        # Extract last name for matching
        parts = contact_name.strip().split()
        if parts:
            search_terms.append(parts[-1].lower())

    for m in meetings:
        name = m.get("name", "").lower()
        invitees = m.get("invitees", [])
        inv_names = " ".join(i.get("name", "").lower() for i in invitees)
        inv_emails = " ".join(i.get("email", "").lower() for i in invitees)
        searchable = f"{name} {inv_names} {inv_emails}"

        for term in search_terms:
            if len(term) >= 3 and term in searchable:
                transcript = m.get("transcript", [])
                if transcript:
                    matches.append({
                        "name": m.get("name", ""),
                        "date": m.get("happenedAt", "")[:20],
                        "duration_min": round(m.get("duration", 0) / 60, 1),
                        "segments": len(transcript),
                        "transcript": transcript,
                    })
                break

    # Sort by date, most recent first
    matches.sort(key=lambda x: x.get("date", ""), reverse=True)
    return matches[:3]  # Max 3 most recent


def format_transcript_summary(matches):
    """Format TLDV transcript matches for Claude context."""
    if not matches:
        return "Žádné předchozí hovory v TLDV."

    parts = []
    for m in matches:
        parts.append(f"\n### Hovor: {m['name']} ({m['date']}, {m['duration_min']}min)")
        # Include first 40 segments max
        for seg in m["transcript"][:40]:
            speaker = seg.get("speaker", "?")
            text = seg.get("text", "")[:200]
            parts.append(f"  {speaker}: {text}")
        if len(m["transcript"]) > 40:
            parts.append(f"  ... ({len(m['transcript']) - 40} dalších segmentů)")

    return "\n".join(parts)


def load_deal_signals(deal_id):
    """Load cached signal intelligence for a deal."""
    fpath = SIGNALS_DIR / f"deal_{deal_id}.json"
    if not fpath.exists():
        return ""

    try:
        data = json.loads(fpath.read_text())
    except Exception:
        return ""

    signals = data.get("signals", [])
    if not signals:
        return ""

    parts = [f"Nalezeno {len(signals)} signálů (skenováno: {data.get('scanned_at', '?')[:10]}):"]
    for s in sorted(signals, key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["priority"]]):
        p = s["priority"].upper()
        parts.append(f"  [{p}] {s['type']}: {s['title'][:80]}")
        parts.append(f"    → {s['relevance']}")
        if s.get("snippet"):
            parts.append(f"    > {s['snippet'][:120]}")

    return "\n".join(parts)


def search_fathom_notes(deal, token):
    """Search Pipedrive notes for existing Fathom transcripts/summaries."""
    notes = deal.get("_notes", []) or []
    fathom_content = []

    for n in notes:
        content = n.get("content", "") or ""
        if "fathom" in content.lower() or "post-call summary" in content.lower():
            # Clean HTML
            clean = re.sub(r'<[^>]+>', ' ', content).strip()[:1500]
            if len(clean) > 50:
                fathom_content.append(clean)

    if fathom_content:
        return "\n---\n".join(fathom_content[:2])  # Max 2 transcripts
    return ""


def search_fathom_api(fathom_key, org_name, contact_name=None):
    """Search Fathom API directly for matching meetings."""
    if not fathom_key:
        return ""

    result = fathom_api(fathom_key, "/meetings", {
        "include_summary": "true",
        "include_action_items": "true",
    })
    if not result:
        return ""

    meetings = result.get("items", [])
    search_terms = [org_name.lower()] if org_name else []
    if contact_name:
        parts = contact_name.strip().split()
        if parts:
            search_terms.append(parts[-1].lower())

    matches = []
    for m in meetings:
        title = (m.get("title") or m.get("meeting_title") or "").lower()
        invitees = m.get("calendar_invitees", [])
        inv_text = " ".join(
            f"{i.get('name', '')} {i.get('email', '')}".lower()
            for i in invitees
        )
        searchable = f"{title} {inv_text}"

        for term in search_terms:
            if len(term) >= 3 and term in searchable:
                summary = m.get("default_summary", {})
                summary_text = summary.get("markdown_formatted", "") if summary else ""
                action_items = m.get("action_items", [])
                if summary_text or action_items:
                    created = m.get("created_at", "")[:10]
                    parts = [f"\n### Fathom: {m.get('title', '')} ({created})"]
                    if summary_text:
                        parts.append(summary_text[:800])
                    if action_items:
                        parts.append("Action items:")
                        for a in action_items[:5]:
                            parts.append(f"  - {a.get('text', '')}")
                    matches.append("\n".join(parts))
                break

    return "\n---\n".join(matches[:2]) if matches else ""


def web_research(company_name):
    """Quick web research on company using curl."""
    if not company_name or company_name == "None":
        return "Nedostupné — není zadán název firmy."

    # Try to find basic info via web search
    try:
        query = urllib.parse.quote(f"{company_name} firma zaměstnanci česko")
        result = subprocess.run(
            ["curl", "-s", "-m", "10",
             f"https://html.duckduckgo.com/html/?q={query}"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout:
            # Extract text snippets from HTML
            text = result.stdout
            # Simple extraction of result snippets
            snippets = re.findall(r'class="result__snippet">(.*?)</a>', text, re.DOTALL)
            if not snippets:
                snippets = re.findall(r'class="result__snippet">(.*?)</td>', text, re.DOTALL)

            if snippets:
                clean = []
                for s in snippets[:5]:
                    s = re.sub(r'<[^>]+>', '', s).strip()
                    if len(s) > 20:
                        clean.append(s[:300])
                if clean:
                    return "\n".join(clean)
    except Exception:
        pass

    return f"Web research pro '{company_name}' nedostupný. Zkontroluj manuálně."


def load_industry_questions(industry=None):
    """Load SPIN questions for given industry."""
    # Default to general if no match
    files = {
        "it": "saas_tech.json",
        "tech": "saas_tech.json",
        "saas": "saas_tech.json",
        "software": "saas_tech.json",
        "finance": "finance.json",
        "bank": "finance.json",
        "manufacturing": "manufacturing.json",
        "výroba": "manufacturing.json",
        "průmysl": "manufacturing.json",
        "consulting": "professional_services.json",
        "služby": "professional_services.json",
        "ecommerce": "ecommerce.json",
        "retail": "ecommerce.json",
    }

    target_file = "saas_tech.json"  # default
    if industry:
        for key, fname in files.items():
            if key in industry.lower():
                target_file = fname
                break

    fpath = SPIN_QUESTIONS_DIR / target_file
    if fpath.exists():
        try:
            return json.loads(fpath.read_text())
        except Exception:
            pass
    return {}


def has_existing_spin_note(deal):
    """Check if deal already has a recent SPIN note."""
    notes = deal.get("_notes", [])
    today = datetime.now().strftime("%Y-%m-%d")
    for n in notes:
        content = n.get("content", "") or ""
        add_time = (n.get("add_time", "") or "")[:10]
        if "SPIN" in content and "QUICK CARD" in content:
            if add_time >= today:
                return True
    return False


def generate_spin_brief(deal, secrets):
    """Generate SPIN brief using Claude Code CLI (claude -p)."""
    title = deal.get("title", "")
    org_name = deal.get("org_name", "N/A")
    value = deal.get("value", 0)
    currency = deal.get("currency", "CZK")
    person_name = deal.get("person_name", "N/A")

    person = deal.get("_person") or {}
    person_email = ""
    person_phone = ""
    if person:
        emails = person.get("email", [])
        if emails and isinstance(emails, list):
            person_email = emails[0].get("value", "") if emails else ""
        phones = person.get("phone", [])
        if phones and isinstance(phones, list):
            person_phone = phones[0].get("value", "") if phones else ""

    org = deal.get("_org") or {}
    org_people = org.get("people_count", "?")
    org_address = org.get("address", "")

    # Previous activities
    all_acts = deal.get("_all_activities", [])
    done_acts = [a for a in all_acts if a.get("done")]
    done_acts.sort(key=lambda x: x.get("due_date", ""), reverse=True)
    recent_acts = done_acts[:5]
    acts_summary = "\n".join(
        f"  - {a.get('due_date','')} | {a.get('type','')} | {a.get('subject','')[:60]}"
        for a in recent_acts
    ) or "Žádné předchozí aktivity."

    # Existing notes
    existing_notes = ""
    for n in (deal.get("_notes", []) or []):
        content = n.get("content", "") or ""
        clean = re.sub(r'<[^>]+>', ' ', content).strip()[:500]
        if clean:
            existing_notes += f"\n{clean}\n"
    existing_notes = existing_notes[:2000] or "Žádné poznámky."

    # Call transcripts — try Fathom first, then TLDV as fallback
    fathom_key = secrets.get("FATHOM_API_KEY")
    transcript_data = search_fathom_notes(deal, fathom_key)
    if not transcript_data:
        transcript_data = search_fathom_api(fathom_key, org_name, person_name)
    if not transcript_data:
        tldv_matches = search_tldv_transcripts(org_name, person_name)
        transcript_data = format_transcript_summary(tldv_matches)

    # Signal intelligence
    signal_intel = load_deal_signals(deal["id"])

    # Web research
    web_info = web_research(org_name)

    # Upcoming activities
    upcoming = deal.get("_upcoming_activities", [])
    upcoming_str = "\n".join(
        f"  - {a['due_date']} {a.get('due_time','')} | {a['type']} | {a['subject'][:60]}"
        for a in upcoming
    ) or "Žádné naplánované."

    # Industry questions
    industry_qs = load_industry_questions(org.get("name", ""))

    prompt = f"""Jsi expert na SPIN selling (Neil Rackham) a český B2B sales pro Behavera.
Behavera prodává Echo Pulse — platformu pro měření spokojenosti a angažovanosti zaměstnanců.
Cena: 99-129 CZK/osoba/měsíc. Pilot: 29,900 Kč/3 měsíce, 100% garance vrácení peněz.

Připrav kompletní SPIN brief pro tento deal. PRAVIDLA:
1. VŽDY piš česky
2. Situation otázky MAX 2 — na zbytek se neptej
3. Problem otázky 3-4 — reálné bolesti z jejich odvětví
4. Implication otázky 3-5 — KLÍČ, propoj problémy s důsledky
5. Need-payoff otázky 2-3 — nech JE prodat řešení sobě
6. Pokud máš transkripty, CITUJ co řekli
7. Buď konkrétní — žádné generic otázky

## Deal Info
- **Název:** {title}
- **Firma:** {org_name}
- **Kontakt:** {person_name} ({person_email}, {person_phone})
- **Hodnota:** {value} {currency}
- **Zaměstnanci:** {org_people}
- **Adresa:** {org_address}

## Nadcházející aktivity
{upcoming_str}

## Předchozí aktivity
{acts_summary}

## Existující poznámky
{existing_notes}

## Signal Intelligence (buying signály)
{signal_intel or "Žádné signály k dispozici. Spusť: python3 scripts/signal_scanner.py --deal " + str(deal['id'])}

## Web Research
{web_info}

## Transkripty hovorů (Fathom/TLDV)
{transcript_data or "Žádné předchozí hovory."}

## SPIN Question Bank
{json.dumps(industry_qs, ensure_ascii=False)[:2000]}

---

Formát výstupu (HTML pro Pipedrive):

<h2>🎯 SPIN Brief — [typ callu] [datum]</h2>
<p><i>Připraveno Clawdia AI</i></p>

<h3>📋 Intel o firmě</h3>
[Co víme z researche — bullet points]

<h3>🔑 Co víme z předchozích hovorů</h3>
[Klíčové insights a citace]

<h3>🟦 SITUATION</h3>
[1-2 otázky]

<h3>🟧 PROBLEM</h3>
[3-4 otázky specifické pro tuto firmu]

<h3>🟥 IMPLICATION</h3>
[3-5 otázek propojujících problémy s důsledky]

<h3>🟩 NEED-PAYOFF</h3>
[2-3 otázky]

<h3>⚡ Strategie pro tento call</h3>
[Tabulka s fázemi, taktikami, časem]

<h3>🛡️ Objection Playbook</h3>
[Tabulka: objection → response]

<h3>📊 Quick Card (ADHD focus)</h3>
[CÍL, DEAL, KONTAKT, BLOKÁTOR, KILLER ARG, URGENCY]

Piš výstup PŘÍMO jako HTML, žádný markdown."""

    # Write prompt to temp file
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        import os as _os
        env = {k: v for k, v in _os.environ.items() if k != "CLAUDECODE"}
        result = subprocess.run(
            ["claude", "-p", "--model", "claude-sonnet-4-6",
             "--dangerously-skip-permissions"],
            input=prompt,
            capture_output=True, text=True, timeout=120,
            env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            log(f"Claude CLI error: {result.stderr[:200]}")
            return None
    except subprocess.TimeoutExpired:
        log("Claude CLI timeout (120s)")
        return None
    except FileNotFoundError:
        log("Claude CLI not found — install with: npm install -g @anthropic-ai/claude-code")
        return None
    except Exception as e:
        log(f"Claude CLI error: {e}")
        return None
    finally:
        Path(prompt_file).unlink(missing_ok=True)


def write_to_pipedrive(token, deal_id, brief):
    """Write SPIN brief as Pipedrive note."""
    # Wrap in basic HTML for Pipedrive rendering
    html_content = brief.replace("\n", "<br>\n")

    result = pipedrive_api(token, "POST", "/notes", {
        "deal_id": deal_id,
        "content": html_content,
        "pinned_to_deal_flag": 1,
    })

    return result is not None


def load_prepped_deals():
    """Load set of deal IDs already prepped today."""
    if KNOWN_DEALS_FILE.exists():
        try:
            data = json.loads(KNOWN_DEALS_FILE.read_text())
            today = datetime.now().strftime("%Y-%m-%d")
            if data.get("date") == today:
                return set(data.get("deal_ids", []))
        except Exception:
            pass
    return set()


def save_prepped_deals(deal_ids):
    """Save prepped deal IDs for today."""
    KNOWN_DEALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    KNOWN_DEALS_FILE.write_text(json.dumps({
        "date": datetime.now().strftime("%Y-%m-%d"),
        "deal_ids": list(deal_ids),
    }))


def get_all_open_deals_without_spin(token):
    """Get all open deals that don't have a SPIN note yet."""
    deals = []
    start = 0
    while True:
        batch = pipedrive_api(token, "GET", "/deals", {
            "status": "open",
            "user_id": "24403638",
            "start": str(start),
            "limit": "100",
        })
        if not batch:
            break
        deals.extend(batch)
        if len(batch) < 100:
            break
        start += 100

    return deals


def main():
    secrets = load_secrets()
    token = secrets.get("PIPEDRIVE_API_TOKEN") or secrets.get("PIPEDRIVE_TOKEN")
    if not token:
        log("No Pipedrive token found in secrets")
        return 1

    dry_run = "--dry-run" in sys.argv
    specific_deal = None
    all_open = "--all-open" in sys.argv

    for i, arg in enumerate(sys.argv):
        if arg == "--deal" and i + 1 < len(sys.argv):
            specific_deal = int(sys.argv[i + 1])

    # Determine which deals to process
    if specific_deal:
        log(f"Processing specific deal: {specific_deal}")
        deal = get_deal_full(token, specific_deal)
        if not deal:
            log(f"Deal {specific_deal} not found")
            return 1
        deals_to_process = [deal]
    elif all_open:
        log("Processing all open deals without SPIN note...")
        raw_deals = get_all_open_deals_without_spin(token)
        deals_to_process = []
        for d in raw_deals:
            full = get_deal_full(token, d["id"])
            if full and not has_existing_spin_note(full):
                deals_to_process.append(full)
        log(f"Found {len(deals_to_process)} deals without SPIN note")
    else:
        log("Finding deals with upcoming activities (next 48h)...")
        upcoming = get_upcoming_deals(token, hours=48)
        prepped = load_prepped_deals()
        deals_to_process = []
        for d in upcoming:
            full = get_deal_full(token, d["id"])
            if full and d["id"] not in prepped and not has_existing_spin_note(full):
                deals_to_process.append(full)
        log(f"Found {len(deals_to_process)} deals needing SPIN prep")

    if not deals_to_process:
        log("No deals to process")
        return 0

    # Process each deal
    results = []
    prepped = load_prepped_deals()

    for deal in deals_to_process:
        did = deal["id"]
        title = deal.get("title", "")
        org = deal.get("org_name", "N/A")

        log(f"Generating SPIN brief for: {title} ({org}) [deal {did}]")

        if dry_run:
            log(f"  [DRY RUN] Would generate brief for deal {did}")
            results.append({"deal_id": did, "title": title, "status": "dry_run"})
            continue

        brief = generate_spin_brief(deal, secrets)
        if not brief:
            log(f"  ERROR: Failed to generate brief for deal {did}")
            results.append({"deal_id": did, "title": title, "status": "error"})
            continue

        log(f"  Brief generated ({len(brief)} chars)")

        # Write to Pipedrive
        if write_to_pipedrive(token, did, brief):
            log(f"  Written to Pipedrive note on deal {did}")
            prepped.add(did)
            results.append({"deal_id": did, "title": title, "status": "ok", "chars": len(brief)})
        else:
            log(f"  ERROR: Failed to write note to Pipedrive")
            results.append({"deal_id": did, "title": title, "status": "write_error"})

    save_prepped_deals(prepped)

    # Summary
    ok = sum(1 for r in results if r["status"] == "ok")
    errors = sum(1 for r in results if "error" in r["status"])

    summary = f"SPIN Prep: {ok} briefů hotovo"
    if errors:
        summary += f", {errors} chyb"

    log(summary)

    # Telegram notification
    if ok > 0 and not dry_run:
        msg_lines = [f"📋 SPIN Prep hotový — {ok} briefů\n"]
        for r in results:
            if r["status"] == "ok":
                msg_lines.append(f"✅ {r['title']}")
            elif "error" in r["status"]:
                msg_lines.append(f"❌ {r['title']}")
        msg_lines.append("\nOtevři Pipedrive → Notes u každého dealu.")
        notify_telegram("\n".join(msg_lines))

    print(f"\nDone: {ok} OK, {errors} errors")
    return 0 if errors == 0 else 1


if __name__ == "__main__":
    exit(main())
