#!/usr/bin/env python3
"""
Meeting Prep Auto-Generator — compile prep docs before calls/demos.

Pulls deal context, contact info, interaction history from Pipedrive,
generates SPIN questions and competitor comparisons, optionally uses
Ollama for talking points.

Usage:
  python3 scripts/meeting_prep.py <deal_id>                    # Prep for a specific deal
  python3 scripts/meeting_prep.py --upcoming                   # Prep for all upcoming meetings
  python3 scripts/meeting_prep.py <deal_id> --template demo    # Specific template (demo/discovery/closing)
"""

import json
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta

from lib.paths import WORKSPACE
from lib.secrets import load_secrets, get_api_key
from lib.claude_api import claude_generate as _claude_generate
from lib.logger import make_logger
from lib.notifications import notify_telegram
from lib.pipedrive import pipedrive_get

PREP_DIR = WORKSPACE / "meeting-prep"
KNOWLEDGE_GRAPH = WORKSPACE / "knowledge" / "graph.json"
LOG_PATH = WORKSPACE / "logs" / "meeting-prep.log"

log = make_logger("meeting-prep")

# Stage mappings (from lead scorer)
SALES_STAGES = {
    7: ("Interested/Qualified", 1),
    8: ("Demo Scheduled", 2),
    28: ("Ongoing Discussion", 3),
    9: ("Proposal made", 4),
    10: ("Negotiation", 5),
    12: ("Pilot", 6),
    29: ("Contract Sent", 7),
    11: ("Invoice sent", 8),
}

ONBOARDING_STAGES = {
    16: ("Sales Action Needed", 1),
    15: ("Waiting for Customer", 2),
    17: ("1. Pulse Planned", 3),
    18: ("Probation Period", 4),
    19: ("Customers", 5),
    20: ("Test Only", 6),
    32: ("Not Converted", 7),
}

# SPIN questions by deal stage
SPIN_QUESTIONS = {
    "discovery": {
        "situation": [
            "How do you currently measure employee engagement?",
            "What tools are you using for HR analytics right now?",
            "How many employees are in your organization?",
            "What does your current feedback process look like?",
            "Who is responsible for employee engagement in your team?",
        ],
        "problem": [
            "What are the biggest challenges with your current approach?",
            "How often do you get meaningful feedback from employees?",
            "Are you able to predict which employees are at risk of leaving?",
            "Do you find it difficult to turn survey results into action?",
            "What frustrates you most about existing engagement tools?",
        ],
        "implication": [
            "What happens when a key employee leaves unexpectedly?",
            "How much does replacing a senior employee cost you?",
            "What impact does low engagement have on team productivity?",
            "If engagement drops further, how would that affect your business goals?",
            "How does turnover affect your ability to deliver on time?",
        ],
        "need_payoff": [
            "If you could predict turnover 3 months in advance, what would that mean for your team?",
            "How valuable would it be to get real-time engagement data instead of annual surveys?",
            "What would reducing turnover by 20% mean for your bottom line?",
            "If managers had actionable insights daily, how would that change things?",
        ],
    },
    "demo": {
        "situation": [
            "What specific features are you most interested in seeing today?",
            "Who else in your organization would need to be involved in the decision?",
            "What's your timeline for implementing a solution like this?",
        ],
        "problem": [
            "What triggered your interest in evaluating engagement tools now?",
            "What's the biggest pain point you're hoping we can solve today?",
            "Have you tried other solutions before? What didn't work?",
        ],
        "implication": [
            "Without better engagement data, where do you see your team in 12 months?",
            "How much time does your HR team spend on manual surveys and analysis?",
            "What opportunities are you missing because you lack predictive insights?",
        ],
        "need_payoff": [
            "If Echo Pulse could automate your entire engagement workflow, how many hours would that free up?",
            "What would it mean for your company to have industry-benchmarked engagement scores?",
            "How would real-time alerts about at-risk employees change your retention strategy?",
        ],
    },
    "closing": {
        "situation": [
            "Have all decision-makers had a chance to review the proposal?",
            "Is there anything in the proposal that needs clarification?",
            "What does your internal approval process look like?",
        ],
        "problem": [
            "Are there any remaining concerns that could prevent us from moving forward?",
            "Is budget or timing a constraint right now?",
            "What would need to change in our offer for this to be a clear yes?",
        ],
        "implication": [
            "Every month without engagement data means more blind spots — what's that costing you?",
            "If you delay this decision, how does that affect your Q2 people goals?",
            "What's the risk of maintaining the status quo for another quarter?",
        ],
        "need_payoff": [
            "With a 2-week pilot, you'd have real data to show leadership — would that help the decision?",
            "If we can start this month, you'd see first results before Q2 review — does that align with your goals?",
            "What ROI would make this an obvious decision for your team?",
        ],
    },
}

# Objection handling playbook — top objections with 2-3 rebuttals each
OBJECTION_PLAYBOOK = {
    "price": {
        "objection": "99-129 CZK/osoba je moc / nemáme rozpočet",
        "responses": [
            "Kolik stojí odchod jednoho seniora? Typicky 6-12 měsíčních platů. U 100 lidí je Echo Pulse 10-13k/měsíc. Jeden zachráněný odchod = ROI na rok.",
            "Máme 2-týdenní pilot zdarma. Uvidíte reálná data, pak se rozhodnete na základě faktů.",
            "Srovnejte to s tím, co platíte za roční průzkum od konzultantky — a to dostanete výsledky jednou za rok.",
        ],
    },
    "already_have_tool": {
        "objection": "Už používáme Culture Amp / Peakon / Officevibe",
        "responses": [
            "Jak často dostáváte výsledky? Většina klientů přešla k nám protože roční/čtvrtletní data nestačí — potřebovali pulse v reálném čase.",
            "Máme nativní češtinu a lokální support — to žádný globální nástroj nenabídne.",
            "Setup za 2 dny vs 4-6 týdnů. Můžeme běžet paralelně a porovnat výsledky.",
        ],
    },
    "no_need": {
        "objection": "Nemáme problém s engagementem / lidé jsou spokojení",
        "responses": [
            "Gallup říká, že 77 % zaměstnanců globálně NENÍ angažovaných. Většina firem to nevidí, dokud nezačnou odcházet.",
            "Jak to víte? Máte data, nebo je to pocit? Echo Pulse vám dá čísla za 2 dny.",
            "I spokojení zaměstnanci mohou být 'tichí odcházeči'. Pulse survey zachytí trendy dřív než exit rozhovor.",
        ],
    },
    "need_approval": {
        "objection": "Musím to projednat s vedením / s CEO",
        "responses": [
            "Jasně — co kdybyste mu ukázali data z 2-týdenního pilotu? To je silnější argument než prezentace.",
            "Mám připravený one-pager pro CEO — 3 čísla, ROI kalkulačka. Pošlu vám ho.",
            "Rád bych se s ním/ní setkal přímo — 15 minut, ukážu ROI na vašich číslech.",
        ],
    },
    "bad_timing": {
        "objection": "Teď na to není vhodná doba / po Q2 / po restrukturalizaci",
        "responses": [
            "Právě v době změn je engagement data nejcennější. Vidíte náladu v reálném čase.",
            "Pilot trvá 2 týdny — žádný závazek. A budete mít data, až přijde ten správný čas.",
            "Co se změní za 3 měsíce? Fluktuace mezitím běží dál.",
        ],
    },
    "too_small": {
        "objection": "Jsme moc malí / jen 30-50 lidí",
        "responses": [
            "Pracujeme od 20 zaměstnanců. V malé firmě je každý odchod proporcionálně dražší.",
            "Menší firma = rychlejší setup, rychlejší výsledky, rychlejší akce.",
            "Právě u menších firem má zpětná vazba největší dopad — lidé vidí, že se něco mění.",
        ],
    },
    "data_privacy": {
        "objection": "Jak je to s GDPR / anonymitou?",
        "responses": [
            "100% anonymní odpovědi — ani admin nevidí individuální výsledky pod 5 respondentů.",
            "Data v EU, GDPR compliant, DPA smlouva. Máme to ošetřené.",
            "Zaměstnanci odpovídají anonymně — a právě proto jsou upřímní. To je celý point.",
        ],
    },
}

# Competitor comparison data
COMPETITOR_DATA = {
    "headers": ["Feature", "Behavera / Echo Pulse", "Peakon (Workday)", "Culture Amp", "Officevibe"],
    "rows": [
        ["AI-Powered Analysis", "Yes — predictive models", "Basic analytics", "Dashboards only", "Basic reports"],
        ["Pulse Survey Frequency", "Continuous + on-demand", "Weekly/Bi-weekly", "Quarterly typical", "Weekly"],
        ["Predictive Turnover", "Yes — 3-month forecast", "No", "No", "No"],
        ["Setup Time", "1-2 days", "2-4 weeks", "4-6 weeks", "1-2 weeks"],
        ["Czech Language", "Native CZ/SK", "Partial", "English only", "English only"],
        ["Pricing (per person/mo)", "99-129 CZK", "~200-400 CZK", "~300-500 CZK", "~150-250 CZK"],
        ["Min. Company Size", "20 employees", "200+ employees", "100+ employees", "10 employees"],
        ["Local Support", "Prague-based team", "No local presence", "No local presence", "No local presence"],
        ["Custom Integrations", "Yes — API + webhooks", "Limited", "Yes", "Limited"],
        ["Employee Cap", "200 included", "Unlimited (tiered)", "Unlimited (tiered)", "Unlimited (tiered)"],
        ["Commission Model", "50% for partners", "Standard reseller", "Standard reseller", "None"],
    ],
}


def api_get(base, token, path, params=None, retry=3):
    params = dict(params or {})
    params["api_token"] = token
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, method="GET")
    for i in range(retry):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and i < retry - 1:
                time.sleep(2 * (i + 1))
                continue
            raise
    return None


def paged_get(base, token, path, params=None):
    out = []
    start = 0
    while True:
        p = dict(params or {})
        p.update({"start": start, "limit": 500})
        j = api_get(base, token, path, params=p)
        if not j or not j.get("success"):
            break
        out.extend(j.get("data") or [])
        pag = (j.get("additional_data") or {}).get("pagination") or {}
        if not pag.get("more_items_in_collection"):
            break
        start = pag.get("next_start", start + 500)
    return out


def days_since(date_str):
    if not date_str:
        return 999
    try:
        d = datetime.strptime(date_str[:10], "%Y-%m-%d").date()
        return (date.today() - d).days
    except (ValueError, TypeError):
        return 999


def get_stage_name(stage_id):
    if stage_id in SALES_STAGES:
        return SALES_STAGES[stage_id][0]
    if stage_id in ONBOARDING_STAGES:
        return ONBOARDING_STAGES[stage_id][0]
    return f"Stage {stage_id}"


def get_deal(base, token, deal_id):
    """Fetch deal details from Pipedrive."""
    return pipedrive_get(base, token, f"/api/v1/deals/{deal_id}") or None


def get_person(base, token, person_id):
    """Fetch person/contact details from Pipedrive."""
    return pipedrive_get(base, token, f"/api/v1/persons/{person_id}") or None


def get_organization(base, token, org_id):
    """Fetch organization details from Pipedrive."""
    return pipedrive_get(base, token, f"/api/v1/organizations/{org_id}") or None


def get_deal_activities(base, token, deal_id):
    """Fetch activities for a deal."""
    return paged_get(base, token, f"/api/v1/deals/{deal_id}/activities", {"sort": "due_date DESC"})


def get_deal_notes(base, token, deal_id):
    """Fetch notes for a deal."""
    return paged_get(base, token, f"/api/v1/deals/{deal_id}/notes", {"sort": "add_time DESC"})


def get_upcoming_activities(base, token):
    """Fetch upcoming activities (next 7 days) that have deal associations."""
    today = date.today()
    end = today + timedelta(days=7)
    params = {
        "start_date": today.isoformat(),
        "end_date": end.isoformat(),
        "done": 0,
    }
    return paged_get(base, token, "/api/v1/activities", params)


def load_knowledge_graph():
    """Load company data from knowledge graph if it exists."""
    if not KNOWLEDGE_GRAPH.exists():
        return {}
    try:
        data = json.loads(KNOWLEDGE_GRAPH.read_text())
        # Index by company name for quick lookup
        graph = {}
        if isinstance(data, dict):
            companies = data.get("companies", data.get("nodes", []))
            if isinstance(companies, list):
                for c in companies:
                    name = c.get("name", c.get("label", ""))
                    if name:
                        graph[name.lower()] = c
            elif isinstance(companies, dict):
                for k, v in companies.items():
                    graph[k.lower()] = v
        return graph
    except (json.JSONDecodeError, OSError):
        return {}


def lookup_company_knowledge(company_name, graph):
    """Look up company info from knowledge graph."""
    if not company_name or not graph:
        return None
    key = company_name.lower()
    if key in graph:
        return graph[key]
    # Partial match
    for k, v in graph.items():
        if key in k or k in key:
            return v
    return None


def claude_generate(system_prompt, user_prompt, max_tokens=512):
    """Generate text using Claude via shared lib."""
    api_key = get_api_key()
    if not api_key:
        log("No Anthropic API key found", "WARN")
        return None
    return _claude_generate(api_key, system_prompt, user_prompt, max_tokens=max_tokens)


def add_pipedrive_note(base, token, deal_id, content):
    """Write SPIN prep as a note to the Pipedrive deal."""
    payload = json.dumps({
        "deal_id": deal_id,
        "content": content,
        "pinned_to_deal_flag": 1,
    }).encode()
    url = f"{base}/api/v1/notes?api_token={token}"
    req = urllib.request.Request(url, data=payload, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            if data.get("success"):
                log(f"Note added to deal {deal_id}")
                return True
    except Exception as e:
        log(f"Failed to add note to deal {deal_id}: {e}", "ERROR")
    return False


def generate_talking_points(deal_context, template_type):
    """Use Claude Sonnet to generate recommended talking points."""
    company = deal_context.get("company", "the company")
    stage = deal_context.get("stage_name", "unknown")
    value = deal_context.get("value", 0)
    industry = deal_context.get("industry", "unknown")
    days_in_pipeline = deal_context.get("days_in_pipeline", 0)

    system = """Jsi B2B sales advisor pro Behavera, prodáváš Echo Pulse (AI nástroj na engagement zaměstnanců) českým firmám.
Piš talking pointy v češtině. Buď konkrétní, ne generický. Zaměř se na hodnotu, ne features."""

    prompt = f"""Vygeneruj 5 konkrétních talking pointů pro {template_type} meeting s {company}.
Kontext:
- Stage: {stage}
- Hodnota: {value} CZK
- Odvětví: {industry}
- Dní v pipeline: {days_in_pipeline}

Pravidla:
- Buď specifický pro tuto firmu/stage
- Mix otázek a tvrzení
- Každý bod 1-2 věty
- Napiš POUZE číslovaný seznam"""

    result = claude_generate(system, prompt, max_tokens=400)
    if result:
        lines = [l.strip() for l in result.strip().split("\n") if l.strip()]
        return lines[:5]

    # Static fallback based on template
    fallbacks = {
        "discovery": [
            "1. Ask about their current employee engagement measurement approach",
            "2. Explore the cost of recent employee turnover",
            "3. Discuss how AI-driven insights differ from annual surveys",
            "4. Share a relevant Czech customer success story",
            "5. Identify the decision-making process and timeline",
        ],
        "demo": [
            "1. Start with their biggest pain point — tailor the demo flow",
            "2. Show the predictive turnover dashboard with sample data",
            "3. Highlight Czech language support and local data residency",
            "4. Compare setup time (2 days) vs competitors (4-6 weeks)",
            "5. End with ROI calculator using their employee count",
        ],
        "closing": [
            "1. Recap the value they've seen in previous conversations",
            "2. Address any outstanding objections directly",
            "3. Present the pilot option (2 weeks, low commitment)",
            "4. Create urgency with current pricing terms",
            "5. Agree on next steps with specific dates",
        ],
    }
    return fallbacks.get(template_type, fallbacks["discovery"])


def determine_template(deal):
    """Auto-detect the right template based on deal stage."""
    stage_id = deal.get("stage_id")
    if stage_id in (7,):  # Interested/Qualified
        return "discovery"
    elif stage_id in (8, 28):  # Demo Scheduled, Ongoing Discussion
        return "demo"
    elif stage_id in (9, 10, 29):  # Proposal, Negotiation, Contract
        return "closing"
    elif stage_id in (12,):  # Pilot
        return "closing"
    else:
        return "discovery"


class MeetingPrepGenerator:
    """Generates meeting prep documents from Pipedrive deal data."""

    def __init__(self):
        env = load_secrets()

        self.base = env.get("PIPEDRIVE_BASE_URL", "").rstrip("/")
        self.token = env.get("PIPEDRIVE_API_TOKEN", "")
        self.user_id = env.get("PIPEDRIVE_USER_ID", "")

        if not self.base or not self.token:
            log("Missing PIPEDRIVE_BASE_URL or PIPEDRIVE_API_TOKEN", "ERROR")
            sys.exit(1)

        self.knowledge_graph = load_knowledge_graph()
        PREP_DIR.mkdir(parents=True, exist_ok=True)

    def build_deal_context(self, deal_id):
        """Pull all data for a deal and assemble context dict."""
        log(f"Fetching deal {deal_id}...")
        deal = get_deal(self.base, self.token, deal_id)
        if not deal:
            log(f"Deal {deal_id} not found", "ERROR")
            return None

        # Extract org info
        org_raw = deal.get("org_id")
        org_id = None
        org_name = ""
        org_data = {}
        if isinstance(org_raw, dict):
            org_id = org_raw.get("value")
            org_name = org_raw.get("name", "")
        elif org_raw:
            org_id = org_raw

        if org_id:
            log(f"Fetching organization {org_id}...")
            org_data = get_organization(self.base, self.token, org_id) or {}

        # Extract person info
        person_raw = deal.get("person_id")
        person_id = None
        contact_name = ""
        person_data = {}
        if isinstance(person_raw, dict):
            person_id = person_raw.get("value")
            contact_name = person_raw.get("name", "")
        elif person_raw:
            person_id = person_raw

        if person_id:
            log(f"Fetching contact {person_id}...")
            person_data = get_person(self.base, self.token, person_id) or {}

        # Extract contact details
        contact_email = ""
        contact_phone = ""
        if person_data:
            emails = person_data.get("email", [])
            if isinstance(emails, list):
                for e in emails:
                    if isinstance(e, dict) and e.get("value"):
                        contact_email = e["value"]
                        break
            phones = person_data.get("phone", [])
            if isinstance(phones, list):
                for p in phones:
                    if isinstance(p, dict) and p.get("value"):
                        contact_phone = p["value"]
                        break
            if not contact_name:
                contact_name = person_data.get("name", "")

        # Activities
        log(f"Fetching activities for deal {deal_id}...")
        activities = get_deal_activities(self.base, self.token, deal_id) or []

        # Notes
        log(f"Fetching notes for deal {deal_id}...")
        notes = get_deal_notes(self.base, self.token, deal_id) or []

        # Knowledge graph lookup
        kg_info = lookup_company_knowledge(org_name, self.knowledge_graph)

        # Calculate pipeline days
        add_time = deal.get("add_time", "")
        pipeline_days = days_since(add_time) if add_time else 0

        # Stage info
        stage_id = deal.get("stage_id")
        stage_name = get_stage_name(stage_id)

        context = {
            "deal_id": deal_id,
            "title": deal.get("title", ""),
            "company": org_name or deal.get("org_name", "Unknown"),
            "contact_name": contact_name,
            "contact_email": contact_email,
            "contact_phone": contact_phone,
            "contact_job_title": person_data.get("job_title", ""),
            "stage_id": stage_id,
            "stage_name": stage_name,
            "value": deal.get("value") or 0,
            "currency": deal.get("currency", "CZK"),
            "status": deal.get("status", "open"),
            "add_time": add_time,
            "update_time": deal.get("update_time", ""),
            "last_activity_date": deal.get("last_activity_date", ""),
            "next_activity_date": deal.get("next_activity_date", ""),
            "days_in_pipeline": pipeline_days,
            "org_data": org_data,
            "person_data": person_data,
            "activities": activities,
            "notes": notes,
            "knowledge_graph": kg_info,
            "industry": (org_data.get("industry") or
                         (kg_info.get("industry") if kg_info else None) or
                         "Unknown"),
            "employee_count": (org_data.get("people_count") or
                               (kg_info.get("employees") if kg_info else None) or
                               "Unknown"),
        }
        return context

    def format_company_overview(self, ctx):
        """Build the Company Overview section."""
        lines = ["## Company Overview"]
        lines.append(f"- **Company:** {ctx['company']}")
        lines.append(f"- **Industry:** {ctx['industry']}")
        lines.append(f"- **Size:** {ctx['employee_count']} employees")

        # Org address
        org = ctx.get("org_data", {})
        address = org.get("address", "")
        if address:
            lines.append(f"- **Location:** {address}")

        # Knowledge graph extras
        kg = ctx.get("knowledge_graph")
        if kg:
            if kg.get("description"):
                lines.append(f"- **About:** {kg['description']}")
            if kg.get("founded"):
                lines.append(f"- **Founded:** {kg['founded']}")
            if kg.get("website"):
                lines.append(f"- **Website:** {kg['website']}")
            if kg.get("tags"):
                tags = kg["tags"] if isinstance(kg["tags"], list) else [kg["tags"]]
                lines.append(f"- **Tags:** {', '.join(str(t) for t in tags)}")

        # Recent activity summary
        last_act = ctx.get("last_activity_date", "")
        if last_act and last_act != "—":
            lines.append(f"- **Last activity:** {last_act} ({days_since(last_act)} days ago)")
        else:
            lines.append("- **Last activity:** None recorded")

        return "\n".join(lines)

    def format_deal_context(self, ctx):
        """Build the Deal Context section."""
        lines = ["## Deal Context"]
        value = ctx.get("value", 0)
        currency = ctx.get("currency", "CZK")
        lines.append(f"- **Deal:** {ctx.get('title', 'N/A')}")
        lines.append(f"- **Value:** {value:,.0f} {currency}" if value else "- **Value:** Not set")
        lines.append(f"- **Stage:** {ctx.get('stage_name', 'Unknown')}")
        lines.append(f"- **Status:** {ctx.get('status', 'open')}")
        lines.append(f"- **Days in pipeline:** {ctx.get('days_in_pipeline', 'N/A')}")
        lines.append(f"- **Added:** {ctx.get('add_time', 'N/A')[:10]}")
        lines.append(f"- **Last updated:** {ctx.get('update_time', 'N/A')[:10]}")

        last_act = ctx.get("last_activity_date", "")
        next_act = ctx.get("next_activity_date", "")
        lines.append(f"- **Last activity:** {last_act or 'None'}")
        lines.append(f"- **Next activity:** {next_act or 'None scheduled'}")

        return "\n".join(lines)

    def format_contact_info(self, ctx):
        """Build the Contact section."""
        lines = ["## Contact"]
        lines.append(f"- **Name:** {ctx.get('contact_name', 'Unknown')}")
        if ctx.get("contact_job_title"):
            lines.append(f"- **Title:** {ctx['contact_job_title']}")
        if ctx.get("contact_email"):
            lines.append(f"- **Email:** {ctx['contact_email']}")
        if ctx.get("contact_phone"):
            lines.append(f"- **Phone:** {ctx['contact_phone']}")
        return "\n".join(lines)

    def format_interaction_history(self, ctx):
        """Build the Interaction History section from activities and notes."""
        lines = ["## Interaction History"]

        activities = ctx.get("activities", [])
        if activities:
            lines.append("")
            lines.append("### Recent Activities")
            for act in activities[:10]:
                done = "Done" if act.get("done") else "Planned"
                act_type = act.get("type", "activity")
                subject = act.get("subject", "No subject")
                due = act.get("due_date", "")
                note = (act.get("note") or "")[:100]
                note_text = f" — {note}" if note else ""
                lines.append(f"- [{done}] **{act_type}** ({due}): {subject}{note_text}")
        else:
            lines.append("- No activities recorded")

        notes = ctx.get("notes", [])
        if notes:
            lines.append("")
            lines.append("### Notes")
            for n in notes[:5]:
                content = (n.get("content") or "").replace("\n", " ")[:200]
                added = (n.get("add_time") or "")[:10]
                lines.append(f"- [{added}] {content}")

        return "\n".join(lines)

    def format_spin_questions(self, template_type):
        """Build the SPIN Questions section."""
        questions = SPIN_QUESTIONS.get(template_type, SPIN_QUESTIONS["discovery"])
        lines = ["## SPIN Questions"]

        lines.append("")
        lines.append("### Situation")
        for i, q in enumerate(questions["situation"], 1):
            lines.append(f"{i}. {q}")

        lines.append("")
        lines.append("### Problem")
        for i, q in enumerate(questions["problem"], 1):
            lines.append(f"{i}. {q}")

        lines.append("")
        lines.append("### Implication")
        for i, q in enumerate(questions["implication"], 1):
            lines.append(f"{i}. {q}")

        lines.append("")
        lines.append("### Need-Payoff")
        for i, q in enumerate(questions["need_payoff"], 1):
            lines.append(f"{i}. {q}")

        return "\n".join(lines)

    def format_competitor_comparison(self):
        """Build the Competitor Comparison table."""
        lines = ["## Competitor Comparison"]
        lines.append("")

        headers = COMPETITOR_DATA["headers"]
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "|".join(["------" for _ in headers]) + "|")

        for row in COMPETITOR_DATA["rows"]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    def format_talking_points(self, ctx, template_type):
        """Build the Recommended Talking Points section."""
        lines = ["## Recommended Talking Points"]
        lines.append("")

        points = generate_talking_points(ctx, template_type)
        for p in points:
            # Strip leading number/bullet if already formatted
            text = p.strip()
            if not text:
                continue
            if text[0].isdigit() and ". " in text[:4]:
                lines.append(text)
            else:
                lines.append(f"- {text}")

        return "\n".join(lines)

    def format_objection_handling(self, template_type):
        """Build the Objection Handling section — top objections with rebuttals."""
        lines = ["## Objection Handling"]
        lines.append("")

        # Select most relevant objections based on template
        if template_type == "closing":
            priority_keys = ["price", "need_approval", "bad_timing", "already_have_tool"]
        elif template_type == "demo":
            priority_keys = ["already_have_tool", "no_need", "data_privacy", "too_small"]
        else:
            priority_keys = ["no_need", "already_have_tool", "price", "bad_timing"]

        for key in priority_keys:
            obj = OBJECTION_PLAYBOOK.get(key)
            if not obj:
                continue
            lines.append(f"### ❓ \"{obj['objection']}\"")
            for i, resp in enumerate(obj["responses"], 1):
                lines.append(f"{i}. {resp}")
            lines.append("")

        return "\n".join(lines)

    def format_post_meeting(self):
        """Build the Post-Meeting Actions section."""
        return """## Post-Meeting Actions
- [ ] Send follow-up email within 24h
- [ ] Update deal stage in Pipedrive
- [ ] Log meeting notes
- [ ] Schedule next meeting
- [ ] Update scoring (run `python3 scripts/pipedrive_lead_scorer.py`)
- [ ] Create personalized follow-up (`python3 scripts/email_personalizer.py personalize <deal_id>`)"""

    def generate_prep(self, deal_id, template_type=None):
        """Generate a full meeting prep document for a deal."""
        ctx = self.build_deal_context(deal_id)
        if not ctx:
            return None

        # Auto-detect template if not specified
        if not template_type:
            template_type = determine_template(ctx)

        log(f"Generating {template_type} prep for deal {deal_id} ({ctx['company']})")

        today_str = date.today().isoformat()
        contact_display = ctx.get("contact_name", "Unknown")
        if ctx.get("contact_job_title"):
            contact_display += f" ({ctx['contact_job_title']})"

        # Build the document
        sections = []

        # Header
        sections.append(f"# Meeting Prep — {ctx['company']}")
        sections.append(f"**Date:** {today_str} | **Contact:** {contact_display} | **Stage:** {ctx.get('stage_name', 'Unknown')}")
        sections.append(f"**Template:** {template_type} | **Deal ID:** {deal_id}")
        sections.append("")

        # Sections
        sections.append(self.format_company_overview(ctx))
        sections.append("")
        sections.append(self.format_contact_info(ctx))
        sections.append("")
        sections.append(self.format_deal_context(ctx))
        sections.append("")
        sections.append(self.format_interaction_history(ctx))
        sections.append("")
        sections.append(self.format_spin_questions(template_type))
        sections.append("")
        sections.append(self.format_competitor_comparison())
        sections.append("")
        sections.append(self.format_talking_points(ctx, template_type))
        sections.append("")
        sections.append(self.format_objection_handling(template_type))
        sections.append("")
        sections.append(self.format_post_meeting())
        sections.append("")
        sections.append(f"---\n*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} by meeting_prep.py*")

        document = "\n".join(sections)

        # Save to file
        filename = f"{deal_id}_{today_str}.md"
        output_path = PREP_DIR / filename
        output_path.write_text(document)

        log(f"Prep saved: {output_path}")

        # Write SPIN prep as Pipedrive note (skip if already written today)
        existing_notes = get_deal_notes(self.base, self.token, deal_id) or []
        already_prepped = any(
            f"SPIN Prep — {today_str}" in (n.get("content") or "")
            for n in existing_notes
        )
        if not already_prepped:
            spin_note = f"<h3>SPIN Prep — {today_str} ({template_type})</h3>\n"
            spin_note += self.format_spin_questions(template_type).replace("\n", "<br>")
            spin_note += f"<br><br><i>Auto-generated by Clawdia meeting_prep.py</i>"
            add_pipedrive_note(self.base, self.token, deal_id, spin_note)

        # Telegram notification
        notify_telegram(f"📋 Meeting prep pro deal #{deal_id} ({ctx['company']}) uložen + SPIN prep v Pipedrive notes")

        return output_path, document

    def generate_upcoming(self):
        """Generate preps for all upcoming activities with deal associations."""
        log("Fetching upcoming activities...")
        activities = get_upcoming_activities(self.base, self.token)
        if not activities:
            log("No upcoming activities found")
            print("No upcoming activities in the next 7 days.")
            return []

        # Filter to activities with deals, deduplicate by deal_id
        seen_deals = set()
        deal_activities = []
        for act in activities:
            deal_id = act.get("deal_id")
            if deal_id and deal_id not in seen_deals:
                # Only include meeting-type activities
                act_type = (act.get("type") or "").lower()
                if act_type in ("call", "meeting", "demo", "lunch", "deadline", "task", "email"):
                    seen_deals.add(deal_id)
                    deal_activities.append(act)

        if not deal_activities:
            log("No deal-associated activities found in upcoming schedule")
            print("No upcoming activities with deal associations.")
            return []

        results = []
        for act in deal_activities:
            deal_id = act["deal_id"]
            act_type = (act.get("type") or "").lower()
            subject = act.get("subject", "")
            due = act.get("due_date", "")

            print(f"\n--- Deal {deal_id}: {subject} ({act_type}, {due}) ---")

            # Infer template from activity type
            template = None
            if "demo" in subject.lower() or act_type == "demo":
                template = "demo"
            elif any(w in subject.lower() for w in ["closing", "contract", "proposal", "nabid"]):
                template = "closing"

            result = self.generate_prep(deal_id, template_type=template)
            if result:
                path, _ = result
                results.append(path)
                print(f"  Saved: {path}")

        return results


def main():
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    gen = MeetingPrepGenerator()

    if args[0] == "--upcoming":
        results = gen.generate_upcoming()
        print(f"\nGenerated {len(results)} prep documents in {PREP_DIR}/")

    elif args[0].isdigit():
        deal_id = args[0]
        template = None
        if "--template" in args:
            idx = args.index("--template")
            if idx + 1 < len(args):
                template = args[idx + 1]

        result = gen.generate_prep(deal_id, template_type=template)
        if result:
            path, document = result
            print(f"\nPrep generated: {path}")
            print(f"\n{'='*60}")
            print(document)
            print(f"{'='*60}")
        else:
            print(f"Failed to generate prep for deal {deal_id}")
            sys.exit(1)

    else:
        print(f"Unknown argument: {args[0]}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
    except Exception as e:
        import traceback
        LOG_PATH.parent.mkdir(exist_ok=True)
        with open(LOG_PATH, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] [FATAL] {e}\n")
            f.write(traceback.format_exc() + "\n")
        print(f"FATAL: {e}", file=sys.stderr)
        raise
