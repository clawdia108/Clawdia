#!/usr/bin/env python3
"""
Email Personalization Engine — Template + deal data → personalized drafts
==========================================================================
Takes email templates and merges deal-specific data:
- Company name, contact name
- Industry pain points, recent company news
- Deal stage context, SPIN selling angle
- Ollama for personalized opening lines

Usage:
  python3 scripts/email_personalizer.py personalize <deal_id>
  python3 scripts/email_personalizer.py batch [--stage <stage>] [--limit 5]
  python3 scripts/email_personalizer.py templates
  python3 scripts/email_personalizer.py quality <draft_file>
"""

import json
import subprocess
import sys
import re
from datetime import datetime, date
from pathlib import Path

BASE = Path("/Users/josefhofman/Clawdia")
DRAFTS_DIR = BASE / "drafts" / "personalized"
TEMPLATE_DIR = BASE / "templates" / "email"
QUALITY_LOG = BASE / "logs" / "email-quality.jsonl"

# Email templates by deal stage
TEMPLATES = {
    "initial_contact": {
        "subject": "{{company}} + Behavera — {{pain_point}}",
        "body": """{{opening_line}}

Jsem Josef z Behavera. Pomáháme firmám jako {{company}} {{value_prop}}.

{{pain_point_detail}}

Měl byste 15 minut na krátký call příští týden?

S pozdravem,
Josef""",
        "spin_focus": "situation",
    },
    "follow_up": {
        "subject": "Re: {{company}} — {{topic}}",
        "body": """{{opening_line}}

{{followup_context}}

{{case_study}}

Jak to vypadá s volným termínem?

Josef""",
        "spin_focus": "problem",
    },
    "after_demo": {
        "subject": "Shrnutí dema — {{company}} x Behavera",
        "body": """{{opening_line}}

Díky za váš čas na dnešním demu. Tady je shrnutí:

{{demo_summary}}

Další kroky:
{{next_steps}}

Pokud máte dotazy, jsem k dispozici.

Josef""",
        "spin_focus": "implication",
    },
    "proposal": {
        "subject": "Nabídka: Behavera pro {{company}}",
        "body": """{{opening_line}}

Na základě našeho rozhovoru jsem připravil nabídku pro {{company}}.

{{proposal_summary}}

ROI odhad: {{roi_estimate}}

{{urgency_note}}

Josef""",
        "spin_focus": "need-payoff",
    },
    "win_recovery": {
        "subject": "{{contact_name}}, jak se daří s {{topic}}?",
        "body": """{{opening_line}}

Chtěl jsem se zeptat, jak se vám daří od naší poslední konverzace.

{{recovery_context}}

Mám nové poznatky, které by vás mohly zajímat — {{new_insight}}.

Máte čas na krátký catch-up?

Josef""",
        "spin_focus": "situation",
    },
}

# SPIN pain points by industry
INDUSTRY_PAIN_POINTS = {
    "technology": [
        "vysoká fluktuace vývojářů",
        "obtížné měření employee engagement v remote týmech",
        "burn-out u key talentů",
    ],
    "manufacturing": [
        "motivace zaměstnanců ve výrobě",
        "komunikační propast mezi managementem a podlahou",
        "retence kvalifikovaných pracovníků",
    ],
    "services": [
        "spokojenost zaměstnanců ovlivňuje kvalitu služeb",
        "vysoké náklady na nábor a zaškolení",
        "měření výkonu v netechnických rolích",
    ],
    "default": [
        "získání zpětné vazby od zaměstnanců",
        "predikce odchodu klíčových lidí",
        "měření firemní kultury",
    ],
}


def load_env():
    """Load Pipedrive credentials."""
    env_path = BASE / ".secrets" / "pipedrive.env"
    env = {}
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k.startswith("export "):
                k = k[7:]
            env[k] = v.strip().strip('"').strip("'")
    return env


def get_deal_context(deal_id):
    """Pull deal context from Pipedrive API."""
    env = load_env()
    api_key = env.get("PIPEDRIVE_API_TOKEN", "")
    base_url = env.get("PIPEDRIVE_BASE_URL", "https://api.pipedrive.com/v1")

    if not api_key:
        return None

    try:
        # Get deal
        r = subprocess.run(
            ["curl", "-s", "-m", "10",
             f"{base_url}/deals/{deal_id}?api_token={api_key}"],
            capture_output=True, text=True, timeout=15,
        )
        deal_data = json.loads(r.stdout)
        if not deal_data.get("success"):
            return None

        deal = deal_data["data"]

        # Get person
        person = deal.get("person_id", {})
        org = deal.get("org_id", {})

        context = {
            "deal_id": deal_id,
            "title": deal.get("title", ""),
            "value": deal.get("value", 0),
            "currency": deal.get("currency", "CZK"),
            "stage": deal.get("stage_id"),
            "status": deal.get("status", "open"),
            "company": org.get("name", "") if isinstance(org, dict) else "",
            "contact_name": person.get("name", "") if isinstance(person, dict) else "",
            "contact_email": "",
            "add_time": deal.get("add_time", ""),
            "update_time": deal.get("update_time", ""),
        }

        # Try to get person email
        if isinstance(person, dict) and person.get("value"):
            pid = person["value"] if isinstance(person["value"], int) else person.get("value")
            if pid:
                r2 = subprocess.run(
                    ["curl", "-s", "-m", "10",
                     f"{base_url}/persons/{pid}?api_token={api_key}"],
                    capture_output=True, text=True, timeout=15,
                )
                pdata = json.loads(r2.stdout)
                if pdata.get("success") and pdata.get("data"):
                    emails = pdata["data"].get("email", [])
                    if emails and isinstance(emails, list):
                        context["contact_email"] = emails[0].get("value", "")

        return context
    except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError):
        return None


def generate_opening_line(context, template_type, timeout=30):
    """Use Ollama to generate a personalized opening line."""
    company = context.get("company", "")
    contact = context.get("contact_name", "")
    stage = template_type

    prompt = f"""Generate a personalized, friendly opening line for a Czech business email.
Context: Writing to {contact} at {company}. Email type: {stage}.
The line should feel natural, not salesy. Write in Czech. One sentence only.

Opening line:"""

    try:
        result = subprocess.run(
            ["curl", "-s", "-m", str(timeout),
             "http://localhost:11434/api/generate",
             "-d", json.dumps({
                 "model": "llama3.1:8b",
                 "prompt": prompt,
                 "stream": False,
                 "options": {"temperature": 0.7, "num_predict": 100},
             })],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if result.returncode == 0:
            response = json.loads(result.stdout)
            line = response.get("response", "").strip()
            # Clean up
            line = line.split("\n")[0].strip().strip('"')
            if line:
                return line
    except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError):
        pass

    # Fallback opening lines
    fallbacks = {
        "initial_contact": f"Dobrý den {contact.split()[0] if contact else ''},",
        "follow_up": f"Dobrý den {contact.split()[0] if contact else ''}, vracím se k naší konverzaci.",
        "after_demo": f"Dobrý den {contact.split()[0] if contact else ''}, ještě jednou díky za dnešní schůzku.",
        "proposal": f"Dobrý den {contact.split()[0] if contact else ''},",
        "win_recovery": f"Dobrý den {contact.split()[0] if contact else ''}, doufám, že se máte dobře.",
    }
    return fallbacks.get(stage, f"Dobrý den,")


def determine_template(context):
    """Determine which template to use based on deal context."""
    value = context.get("value", 0) or 0
    days_old = 0
    if context.get("add_time"):
        try:
            added = datetime.fromisoformat(context["add_time"].replace("Z", "+00:00").split("+")[0])
            days_old = (datetime.now() - added).days
        except (ValueError, TypeError):
            pass

    if days_old <= 3:
        return "initial_contact"
    elif days_old <= 14:
        return "follow_up"
    elif value and value > 100000:
        return "proposal"
    elif days_old > 30:
        return "win_recovery"
    else:
        return "follow_up"


def get_pain_points(company=""):
    """Get relevant pain points for a company/industry."""
    company_lower = company.lower()
    if any(t in company_lower for t in ["tech", "soft", "dev", "ai", "data", "cloud"]):
        return INDUSTRY_PAIN_POINTS["technology"]
    elif any(t in company_lower for t in ["výrob", "manufact", "product", "industr"]):
        return INDUSTRY_PAIN_POINTS["manufacturing"]
    elif any(t in company_lower for t in ["consult", "služb", "service", "agentur"]):
        return INDUSTRY_PAIN_POINTS["services"]
    return INDUSTRY_PAIN_POINTS["default"]


def personalize_email(deal_id, template_type=None):
    """Generate a personalized email for a deal."""
    context = get_deal_context(deal_id)
    if not context:
        print(f"Could not load deal {deal_id} context")
        return None

    if not template_type:
        template_type = determine_template(context)

    template = TEMPLATES.get(template_type)
    if not template:
        print(f"Unknown template: {template_type}")
        return None

    # Generate personalized content
    opening = generate_opening_line(context, template_type)
    pain_points = get_pain_points(context.get("company", ""))

    # Fill template variables
    vars = {
        "company": context.get("company", "[Company]"),
        "contact_name": context.get("contact_name", "[Contact]"),
        "opening_line": opening,
        "pain_point": pain_points[0] if pain_points else "employee engagement",
        "pain_point_detail": f"Vidíme, že firmy v podobném segmentu řeší {pain_points[0]}. "
                            f"Naši klienti díky Echo Pulse snížili fluktuaci o 23%."
                            if pain_points else "",
        "value_prop": "měřit a zlepšovat employee engagement pomocí AI",
        "topic": "employee engagement",
        "followup_context": f"Navazuji na naši předchozí konverzaci o {context.get('company', '')}.",
        "case_study": "Jeden z našich klientů (tech firma, 200 zaměstnanců) dosáhl 30% zlepšení retence za 6 měsíců.",
        "demo_summary": "- Ukázka Echo Pulse dashboardu\n- Analýza engagement dat\n- Prediktivní modely",
        "next_steps": "1. Zaslání nabídky\n2. Pilotní projekt (2 týdny)\n3. Evaluace výsledků",
        "proposal_summary": f"Echo Pulse pro {context.get('company', '')} — plné nasazení.",
        "roi_estimate": f"Odhadujeme návratnost do 6 měsíců při úspoře na náboru a retenci.",
        "urgency_note": "Aktuální cenové podmínky platí do konce měsíce.",
        "recovery_context": f"Naposledy jsme mluvili o možnostech employee engagement pro {context.get('company', '')}.",
        "new_insight": "nový výzkum o predikci fluktuace pomocí AI",
    }

    subject = template["subject"]
    body = template["body"]
    for key, value in vars.items():
        subject = subject.replace(f"{{{{{key}}}}}", value)
        body = body.replace(f"{{{{{key}}}}}", value)

    draft = {
        "deal_id": deal_id,
        "template": template_type,
        "spin_focus": template.get("spin_focus", ""),
        "subject": subject,
        "body": body,
        "to": context.get("contact_email", ""),
        "company": context.get("company", ""),
        "contact": context.get("contact_name", ""),
        "personalization_method": "ollama+rules",
        "created_at": datetime.now().isoformat(),
    }

    # Save draft
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"draft_{deal_id}_{template_type}_{date.today().isoformat()}.json"
    draft_path = DRAFTS_DIR / filename
    draft_path.write_text(json.dumps(draft, indent=2, ensure_ascii=False))

    # Also save readable version
    md_path = DRAFTS_DIR / filename.replace(".json", ".md")
    md_content = f"""# Email Draft — {context.get('company', '')}

**To:** {draft['to'] or '[no email]'}
**Subject:** {draft['subject']}
**Template:** {template_type} (SPIN: {template.get('spin_focus', '')})

---

{draft['body']}

---
*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Deal: {deal_id}*
"""
    md_path.write_text(md_content)

    return draft


def score_quality(draft):
    """Score email quality on multiple dimensions."""
    body = draft.get("body", "")
    subject = draft.get("subject", "")

    scores = {
        "has_personalization": 1 if draft.get("company") and draft["company"] in body else 0,
        "subject_length": 1 if 20 <= len(subject) <= 80 else 0,
        "body_length": 1 if 100 <= len(body) <= 800 else 0,
        "has_cta": 1 if any(cta in body.lower() for cta in ["call", "schůzk", "termin", "čas", "minut"]) else 0,
        "has_value_prop": 1 if any(v in body.lower() for v in ["engagement", "retenc", "fluktua", "roi"]) else 0,
        "not_too_salesy": 1 if body.count("!") < 3 else 0,
        "has_closing": 1 if any(c in body for c in ["Josef", "S pozdravem", "Díky"]) else 0,
    }

    total = sum(scores.values())
    max_score = len(scores)

    return {
        "score": round(total / max_score * 100),
        "details": scores,
        "rating": "excellent" if total >= 6 else "good" if total >= 4 else "needs_work",
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: email_personalizer.py [personalize <deal_id>|batch|templates|quality <file>]")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "personalize" and len(sys.argv) > 2:
        deal_id = sys.argv[2]
        template_type = sys.argv[3] if len(sys.argv) > 3 else None
        draft = personalize_email(deal_id, template_type)
        if draft:
            quality = score_quality(draft)
            print(f"\nDraft generated for {draft['company']}")
            print(f"  Subject: {draft['subject']}")
            print(f"  Template: {draft['template']} (SPIN: {draft['spin_focus']})")
            print(f"  Quality: {quality['score']}% ({quality['rating']})")
            print(f"  Saved to: drafts/personalized/")

    elif cmd == "batch":
        limit = 5
        for i, arg in enumerate(sys.argv):
            if arg == "--limit" and i + 1 < len(sys.argv):
                limit = int(sys.argv[i + 1])

        # Get deals from scoring
        scoring_file = BASE / "pipedrive" / "DEAL_SCORING.md"
        if scoring_file.exists():
            content = scoring_file.read_text()
            # Extract deal IDs from markdown
            deal_ids = re.findall(r'deal/(\d+)', content)[:limit]
            for did in deal_ids:
                print(f"\n--- Deal {did} ---")
                draft = personalize_email(did)
                if draft:
                    quality = score_quality(draft)
                    print(f"  {draft['company']}: {quality['score']}% quality")
        else:
            print("No scoring data available. Run pipeline scoring first.")

    elif cmd == "templates":
        print("\nAvailable Templates:")
        for name, tmpl in TEMPLATES.items():
            print(f"  {name:<20} SPIN: {tmpl['spin_focus']}")

    elif cmd == "quality" and len(sys.argv) > 2:
        path = Path(sys.argv[2])
        if path.exists() and path.suffix == ".json":
            draft = json.loads(path.read_text())
            quality = score_quality(draft)
            print(f"\nQuality Score: {quality['score']}% ({quality['rating']})")
            for dim, score in quality["details"].items():
                status = "OK" if score else "MISS"
                print(f"  [{status}] {dim}")

    else:
        print("Usage: email_personalizer.py [personalize <deal_id>|batch|templates|quality <file>]")
