#!/usr/bin/env python3
"""
Claude-Powered Email Draft Generator
======================================
Generates follow-up email drafts using Claude Sonnet 4.6 (Anthropic API).
Uses SPIN methodology, personalized per deal context from Pipedrive.
Creates Gmail drafts via API OR saves locally for review.

v2: Upgraded from Ollama llama3.1:8b → Claude Sonnet 4.6 (March 2026)
"""

import json
import subprocess
import sys
import time
from datetime import datetime, date

from lib.paths import WORKSPACE
from lib.secrets import get_api_key
from lib.claude_api import claude_generate
from lib.logger import make_logger
from lib.notifications import notify_telegram

DRAFTS_DIR = WORKSPACE / "drafts"
STALE_DEALS = WORKSPACE / "pipedrive" / "STALE_DEALS.md"
SCORING_FILE = WORKSPACE / "pipedrive" / "DEAL_SCORING.md"
PIPELINE_FILE = WORKSPACE / "pipedrive" / "PIPELINE_STATUS.md"

dlog = make_logger("draft-generator")

# ── MODEL CONFIG ─────────────────────────────────────
# Claude Sonnet 4.6 for high-quality Czech sales copy
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 800

# Fallback to Ollama if Claude API fails
OLLAMA_FALLBACK = True
OLLAMA_MODEL = "llama3.1:8b"
OLLAMA_URL = "http://localhost:11434/api/generate"


# ── SPIN TEMPLATES ───────────────────────────────────
SPIN_TEMPLATES = {
    "cold_followup": {
        "subject_template": "Zpětná vazba na {org_name}",
        "approach": "situation",
        "tone": "friendly_professional",
        "max_words": 150,
        "description": "První kontakt / cold follow-up. Zjisti situaci, buď zvědavý.",
    },
    "warm_reengagement": {
        "subject_template": "Jak to jde s {topic}?",
        "approach": "problem",
        "tone": "helpful",
        "max_words": 120,
        "description": "Warm lead, už byl kontakt. Odhal problém.",
    },
    "hot_closing": {
        "subject_template": "{org_name} — další kroky",
        "approach": "need_payoff",
        "tone": "direct",
        "max_words": 100,
        "description": "Hot deal, push to close. Jasné další kroky.",
    },
    "demo_followup": {
        "subject_template": "Shrnutí z demo — {org_name}",
        "approach": "implication",
        "tone": "professional",
        "max_words": 200,
        "description": "Po demo/callu. Ukaž co ztrácí bez řešení.",
    },
    "stale_revival": {
        "subject_template": "Napadlo mě něco ohledně {org_name}",
        "approach": "problem",
        "tone": "casual",
        "max_words": 80,
        "description": "Mrtvý deal, zkus ho oživit. Krátce, lidsky.",
    },
}

SPIN_APPROACHES = {
    "situation": "Ptej se na aktuální stav. Jaké nástroje používají? Jak měří engagement zaměstnanců? Dělají pravidelné průzkumy? Buď zvědavý, ne dotěrný.",
    "problem": "Jemně odhal problém. Vysoká fluktuace? Těžko získat upřímnou zpětnou vazbu? Chybí jim přehled o náladě v týmu? Nevidí problémy včas?",
    "implication": "Pomoz jim vidět důsledky. Co stojí nízký engagement? Co jim uniká bez pravidelné zpětné vazby? Kolik stojí odchod jednoho zaměstnance?",
    "need_payoff": "Nakresli obraz řešení. Jak by pomohly pravidelné pulse surveys? Co by se dozvěděli? Jak rychle můžou začít? 99-129 Kč/osobu.",
}



def ollama_generate(prompt):
    """Fallback: generate using local Ollama"""
    if not OLLAMA_FALLBACK:
        return None
    try:
        payload = json.dumps({
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": 400, "temperature": 0.7},
        })
        result = subprocess.run(
            ["curl", "-s", "-m", "30", OLLAMA_URL, "-d", payload],
            capture_output=True, text=True, timeout=35,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("response", "").strip()
    except Exception as e:
        dlog(f"Ollama fallback error: {e}", "ERROR")
    return None


def parse_stale_deals():
    """Parse stale deals from STALE_DEALS.md"""
    if not STALE_DEALS.exists():
        return []
    deals = []
    for line in STALE_DEALS.read_text().splitlines():
        if line.startswith("- **"):
            try:
                title = line.split("**")[1]
                org = line.split("(")[1].split(")")[0] if "(" in line else ""
                value = ""
                if "—" in line:
                    value = line.split("—")[1].strip()
                deals.append({
                    "title": title.strip(),
                    "org": org.strip(),
                    "value": value.strip(),
                })
            except (IndexError, ValueError):
                continue
    return deals


def parse_scored_deals():
    """Parse top-scored deals from DEAL_SCORING.md"""
    if not SCORING_FILE.exists():
        return []
    deals = []
    content = SCORING_FILE.read_text()
    for line in content.splitlines():
        # Look for lines with score patterns like "85/100" or "[85]"
        if "**" in line and ("/" in line or "[" in line):
            try:
                title = line.split("**")[1] if "**" in line else ""
                org = line.split("(")[1].split(")")[0] if "(" in line else ""
                deals.append({
                    "title": title.strip(),
                    "org": org.strip(),
                    "value": "",
                    "source": "scoring",
                })
            except (IndexError, ValueError):
                continue
    return deals


def determine_template(deal):
    """Choose the right SPIN template based on deal context"""
    value_str = deal.get("value", "")
    source = deal.get("source", "")

    if source == "scoring":
        return "cold_followup"

    if "CZK" in value_str:
        try:
            amount = int(value_str.replace(",", "").replace(" CZK", "").replace("CZK", "").strip())
            if amount >= 50000:
                return "hot_closing"
            elif amount >= 20000:
                return "warm_reengagement"
        except ValueError:
            pass

    # Stale deals get revival template
    if deal.get("title", "").lower().find("stale") >= 0 or source == "stale":
        return "stale_revival"

    return "cold_followup"


def generate_draft(deal, template_key):
    """Generate a single email draft using Claude (with Ollama fallback)"""
    template = SPIN_TEMPLATES[template_key]
    spin_approach = SPIN_APPROACHES[template["approach"]]

    org = deal.get("org", "firma")
    title = deal.get("title", "")
    value = deal.get("value", "")
    contact = deal.get("contact", "")

    system_prompt = """Jsi Josef Hofman z Behavera. Píšeš obchodní emaily v přirozené češtině.

ZÁSADY JAZYKA:
- Piš jako skutečný český obchodník v roce 2026 v Praze. Ne jako přeložený americký text.
- VŽDY vykej s MALÝM "v" — "vám", "vás", "vaše". NIKDY ne "Vám", "Vás", "Vaše".
- NIKDY netykej (žádné "ty", "tvůj", "ahoj"). Oslovuj profesionálně ale lidsky.
- Žádné americké nadšení: ne "skvělá příležitost!", ne "rád bych se s vámi spojil!", ne "dovolte mi..."
- Žádné korporátní klišé: ne "synergie", "řešení na míru", "přidaná hodnota", "v dnešní době"
- Žádné AI patterny: ne "rád bych vás informoval", ne "dovolte mi se představit", ne "chtěl bych se zeptat"
- Piš krátce. Čech čte email 15 sekund. Respektuj jeho čas.

STRUKTURA:
- Začni rovnou pointou — proč píšeš. Žádné zdvořilostní omáčky.
- Jedna konkrétní otázka na konec.
- Jasný další krok (meeting, call, demo).
- Podpis: "Josef Hofman, Behavera"

PŘÍKLAD DOBRÉHO ČESKÉHO OBCHODNÍHO EMAILU:
"Dobrý den, pane Nováku,
před dvěma týdny jsme spolu řešili engagement vašeho týmu. Chtěl bych se zeptat, jestli jste měl čas se na to podívat, nebo jestli vám můžu s něčím pomoct.
Případně bychom se mohli spojit na 15 minut tento týden — co říkáte?
Josef Hofman, Behavera"

PŘÍKLAD ŠPATNÉHO EMAILU (tak NEPIŠ):
"Ahoj! Doufám, že se máte skvěle! Rád bych Vás informoval o naší úžasné platformě..."

Produkt Echo Pulse:
- Pulse surveys pro měření engagementu zaměstnanců
- 99-129 Kč/osoba/měsíc, start za 2 dny
- Anonymní zpětná vazba, predikce odchodů
- Pro firmy 50-500 zaměstnanců v ČR"""

    user_prompt = f"""Napiš follow-up email pro tento deal:

Firma: {org}
Deal: {title}
Hodnota: {value}
Kontakt: {contact if contact else 'neznámý'}

SPIN přístup: {template['approach']}
Instrukce: {spin_approach}
Tón: {template['tone']}
Max délka: {template['max_words']} slov
Kontext: {template['description']}

DŮLEŽITÉ: Piš přirozenou češtinu. Malé "v" u vykání. Žádné AI patterny. Žádné americké nadšení.
Piš POUZE tělo emailu, nic jiného."""

    # Try Claude first
    api_key = get_api_key()
    response = claude_generate(api_key, system_prompt, user_prompt, max_tokens=MAX_TOKENS, model=MODEL)

    # Fallback to Ollama
    if not response:
        dlog("Claude failed, trying Ollama fallback", "WARN")
        fallback_prompt = f"{system_prompt}\n\n{user_prompt}"
        response = ollama_generate(fallback_prompt)
        if response:
            dlog("Ollama fallback succeeded")

    if not response:
        return None

    # ── 3-AGENT REVIEW PIPELINE ──────────────────────
    response = run_review_pipeline(response, org, template_key)

    subject = template["subject_template"].format(
        org_name=org,
        topic="engagement zaměstnanců",
    )

    return {
        "subject": subject,
        "body": response,
        "to": contact if contact else f"kontakt@{org.lower().replace(' ', '')}.cz",
        "from": "josef.hofman@behavera.com",
        "template": template_key,
        "spin_approach": template["approach"],
        "deal_title": title,
        "deal_org": org,
        "deal_value": value,
        "model_used": MODEL if "Claude" not in (response or "") else OLLAMA_MODEL,
        "generated_at": datetime.now().isoformat(),
        "status": "draft",
    }


def run_review_pipeline(draft_text, org, template_key):
    """3-agent review pipeline: Humanizer → Czech Expert → Sales Strategist.
    Each reviewer gets the draft, critiques it, and rewrites if needed.
    Returns the final polished version."""

    api_key = get_api_key()
    if not api_key:
        dlog("No API key — skipping review pipeline", "WARN")
        return draft_text

    # Load Humanizer training data
    training_data = ""
    training_file = WORKSPACE / "knowledge" / "HUMANIZER_TRAINING.md"
    if training_file.exists():
        training_data = training_file.read_text()[:2500]

    reviewers = [
        {
            "name": "Humanizer",
            "system": f"""Jsi expert na detekci AI textu. Tvůj JEDINÝ úkol: přepsat email tak, aby zněl jako od Josefa Hofmana.

Máš k dispozici analýzu jeho REÁLNÉHO psacího stylu z Gmailu:

{training_data[:2000]}

KONTROLUJ:
- Opakující se struktury (3 body, 3 argumenty = AI pattern)
- Příliš dokonalá stavba vět (lidi píšou nerovnoměrně)
- Generické fráze ("rád bych se s vámi spojil", "dovolte mi")
- Příliš formální nebo příliš nadšený tón
- Žádné seznamy s odrážkami v krátkých emailech
- Přílišná "helpfulness" — Josef je přímý a stručný
- VŽDY malé "v" u vykání: "vám", "vás", "vaše"
- Josefovy typické fráze: "Dejte prosím vědět", "v klidu", "zabere to minutu"

PŘEPIŠ email tak, aby odpovídal Josefovu stylu z tréninku výše.
Vrať POUZE přepsaný email, nic jiného.""",
            "prompt": f"Zkontroluj tento email pro {org} a přepiš ho v Josefově stylu:\n\n{{text}}",
        },
        {
            "name": "Czech Language Expert",
            "system": """Jsi rodilý Čech a korektor obchodní češtiny. Kontroluješ jazyk emailů.

KONTROLUJ:
- Vykání VŽDY s malým "v": "vám", "vás", "vaše", "váš" — NIKDY "Vám", "Vás"
- Žádné tykání (ty, tvůj, ahoj)
- Žádné amerikanismy přeložené do češtiny ("skvělá příležitost", "nebojte se zeptat")
- Přirozený český slovosled (ne otrocký překlad z angličtiny)
- Správné oslovení (pane Nováku, paní Svobodová)
- Čeština roku 2026 — moderní, ale profesionální

Oprav všechny chyby a vrať POUZE opravený email.""",
            "prompt": f"Zkontroluj češtinu v tomto emailu pro {org}:\n\n{{text}}",
        },
        {
            "name": "Sales Strategist",
            "system": f"""Jsi senior sales konzultant se SPIN metodikou. Kontroluješ obchodní efektivitu emailu.

Template: {template_key}
SPIN přístup: {SPIN_TEMPLATES.get(template_key, {}).get('approach', 'situation')}

KONTROLUJ:
- Má email jasný CTA (call-to-action)? Jedna konkrétní otázka nebo návrh dalšího kroku?
- Odpovídá email SPIN fázi dealu? (situation = ptej se, problem = odhal bolest, implication = ukaž důsledky, need_payoff = navrhni řešení)
- Je email dost krátký? CEO čte 15 sekund max.
- Nezní to příliš "prodejně"? Čeští CEO nemají rádi americký hard-sell.
- Je tu value proposition? Proč by měl odpovědět?

Vylepši email z obchodní perspektivy. Vrať POUZE finální email.""",
            "prompt": f"Zkontroluj obchodní kvalitu emailu pro {org}:\n\n{{text}}",
        },
    ]

    current_text = draft_text
    for reviewer in reviewers:
        prompt = reviewer["prompt"].replace("{text}", current_text)
        # First reviewer already has the text in system prompt
        if "{text}" not in reviewer["prompt"]:
            prompt = reviewer["prompt"]

        result = claude_generate(api_key, reviewer["system"], prompt, max_tokens=MAX_TOKENS, model=MODEL)
        if result and len(result) > 20:
            current_text = result
            dlog(f"Review [{reviewer['name']}] OK — {len(result)} chars")
        else:
            dlog(f"Review [{reviewer['name']}] failed, keeping previous version", "WARN")

        time.sleep(0.3)  # Rate limit

    return current_text


def save_draft_locally(draft):
    """Save draft as JSON + markdown to local drafts/ folder"""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    org_safe = draft["deal_org"].replace(" ", "_").replace("/", "-")[:30]
    filename = f"{date.today().isoformat()}_{org_safe}"

    # JSON
    json_path = DRAFTS_DIR / f"{filename}.json"
    json_path.write_text(json.dumps(draft, indent=2, ensure_ascii=False))

    # Markdown
    md_path = DRAFTS_DIR / f"{filename}.md"
    md_path.write_text(f"""# Draft: {draft['subject']}
**To:** {draft['to']}
**From:** {draft['from']}
**Template:** {draft['template']} ({draft['spin_approach']})
**Deal:** {draft['deal_title']} ({draft['deal_value']})
**Model:** {draft.get('model_used', 'unknown')}
**Generated:** {draft['generated_at']}

---

{draft['body']}

---
*Generated by Clawdia Draft Generator v2 (Claude Sonnet 4.6)*
""")

    return json_path, md_path



def generate_all_drafts(max_drafts=5, create_gmail_drafts=False):
    """Generate drafts for top deals"""
    # Collect deals from multiple sources
    stale_deals = parse_stale_deals()
    for d in stale_deals:
        d["source"] = "stale"

    scored_deals = parse_scored_deals()

    all_deals = stale_deals + scored_deals
    if not all_deals:
        dlog("No deals found to generate drafts for")
        print("No deals found — check STALE_DEALS.md and DEAL_SCORING.md")
        return []

    # Deduplicate by org
    seen_orgs = set()
    unique_deals = []
    for deal in all_deals:
        org = deal.get("org", "").lower()
        if org and org not in seen_orgs:
            seen_orgs.add(org)
            unique_deals.append(deal)

    generated = []
    failed = []

    for deal in unique_deals[:max_drafts]:
        template_key = determine_template(deal)
        org = deal.get("org", "?")
        dlog(f"Generating draft for {org} ({template_key})")

        draft = generate_draft(deal, template_key)
        if not draft:
            dlog(f"FAILED to generate draft for {org}", "ERROR")
            failed.append(org)
            continue

        # Always save locally
        json_path, md_path = save_draft_locally(draft)

        generated.append(draft)
        dlog(f"Draft saved: {json_path.name}")

        time.sleep(0.5)

    # Summary
    summary = f"Generated {len(generated)} drafts"
    if failed:
        summary += f", failed {len(failed)}: {', '.join(failed)}"
    dlog(summary)
    print(summary)

    # Notify if there are new drafts to review
    if generated:
        notify_telegram(
            f"📝 {len(generated)} nových email draftů ke kontrole.\n"
            f"Firmy: {', '.join(d['deal_org'] for d in generated[:5])}"
        )

    return generated


if __name__ == "__main__":
    max_drafts = 5
    gmail = False

    for arg in sys.argv[1:]:
        if arg == "--gmail":
            gmail = True
        else:
            try:
                max_drafts = int(arg)
            except ValueError:
                pass

    generate_all_drafts(max_drafts=max_drafts, create_gmail_drafts=gmail)
