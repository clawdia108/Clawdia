#!/usr/bin/env python3
"""
Sales Proposal Generator — automated, data-driven proposals for Echo Pulse / Behavera.

Pulls deal context from knowledge graph, Pipedrive API, and deal velocity data,
then generates a full markdown sales proposal with ROI calculations, timeline,
and industry-specific framing.

Uses Ollama (llama3.1:8b) for narrative sections when available, falls back to templates.

Usage:
  python3 scripts/proposal_generator.py generate <deal_id|company_name>
  python3 scripts/proposal_generator.py list
  python3 scripts/proposal_generator.py show <proposal_file>
  python3 scripts/proposal_generator.py score <proposal_file>
"""

import json
import re
import subprocess
import sys
import hashlib
from datetime import datetime, date
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
PROPOSALS_DIR = WORKSPACE / "proposals"
MANIFEST_FILE = PROPOSALS_DIR / "manifest.json"
GRAPH_FILE = WORKSPACE / "knowledge" / "graph.json"
VELOCITY_FILE = WORKSPACE / "pipedrive" / "deal_velocity.json"
ENV_PATH = WORKSPACE / ".secrets" / "pipedrive.env"
LOG_FILE = WORKSPACE / "logs" / "proposal-generator.log"

TODAY = date.today()
NOW = datetime.now()

# ── Pricing (from echo_pulse_pricing.py) ─────────────

PRICE_TIERS = [
    (50, 129),
    (80, 119),
    (120, 109),
    (160, 99),
]
MAX_EMPLOYEES = 200
PILOT_PRICE = 29900
DEFAULT_SALARY = 70000

# ── Industry templates ───────────────────────────────

INDUSTRY_PROFILES = {
    "saas": {
        "label": "SaaS / Technology",
        "keywords": ["saas", "software", "tech", " ai ", " ai-", "cloud", "data", "dev", "it ", "digital"],
        "pain_points": [
            "Developer burnout and high turnover in competitive talent market",
            "Remote/hybrid team engagement visibility gaps",
            "Scaling culture while growing headcount 2-3x",
            "Key talent retention during funding rounds and pivots",
        ],
        "benchmarks": {
            "avg_turnover_pct": 18,
            "replacement_cost_months": 9,
            "engagement_lift_pct": 25,
            "turnover_reduction_pct": 23,
        },
        "solution_angle": (
            "Echo Pulse provides real-time engagement signals across distributed teams, "
            "predictive attrition alerts for key roles, and AI-driven pulse surveys "
            "that adapt to your team's rhythm."
        ),
        "case_study": (
            "A Czech SaaS company (200 employees) reduced developer turnover by 28% "
            "in 6 months using Echo Pulse engagement insights and early warning alerts."
        ),
    },
    "fintech": {
        "label": "Fintech / Financial Services",
        "keywords": ["fintech", "financ", "bank", "insur", "invest", "capital", "fond"],
        "pain_points": [
            "Regulatory pressure creates stress and disengagement",
            "Compliance teams face high burnout risk",
            "Competition for specialized talent (risk, quant, compliance)",
            "Culture disconnect between front-office and back-office",
        ],
        "benchmarks": {
            "avg_turnover_pct": 15,
            "replacement_cost_months": 12,
            "engagement_lift_pct": 20,
            "turnover_reduction_pct": 18,
        },
        "solution_angle": (
            "Echo Pulse delivers confidential, GDPR-compliant engagement measurement "
            "tailored to regulated environments, with department-level insights "
            "and compliance-team specific stress indicators."
        ),
        "case_study": (
            "A fintech firm (120 employees) identified compliance team burnout "
            "3 months before peak turnover season, saving an estimated 2M CZK in replacement costs."
        ),
    },
    "ecommerce": {
        "label": "E-commerce / Retail",
        "keywords": ["ecommerce", "e-comm", "retail", "shop", "store", "obchod", "prodej"],
        "pain_points": [
            "Seasonal workforce engagement fluctuations",
            "High turnover in warehouse and customer service roles",
            "Disconnect between HQ strategy and frontline morale",
            "Rapid scaling strains existing culture",
        ],
        "benchmarks": {
            "avg_turnover_pct": 25,
            "replacement_cost_months": 6,
            "engagement_lift_pct": 30,
            "turnover_reduction_pct": 20,
        },
        "solution_angle": (
            "Echo Pulse captures engagement signals across retail, warehouse, "
            "and office teams with role-specific pulse surveys and seasonal trend analysis."
        ),
        "case_study": (
            "An e-commerce company (150 employees) reduced seasonal turnover by 35% "
            "by identifying disengagement patterns 6 weeks before peak attrition periods."
        ),
    },
    "healthcare": {
        "label": "Healthcare / Medical",
        "keywords": ["health", "medic", "nemocnic", "klinik", "pharma", "lék", "hospital", "care"],
        "pain_points": [
            "Staff burnout across clinical and support roles",
            "Patient care quality directly tied to employee wellbeing",
            "Shift-based scheduling creates engagement blind spots",
            "Regulatory requirements add to workforce stress",
        ],
        "benchmarks": {
            "avg_turnover_pct": 20,
            "replacement_cost_months": 10,
            "engagement_lift_pct": 22,
            "turnover_reduction_pct": 19,
        },
        "solution_angle": (
            "Echo Pulse measures engagement in clinical environments with shift-aware "
            "pulse timing, burnout prediction models, and anonymous feedback channels "
            "that surface issues before they impact patient care."
        ),
        "case_study": (
            "A hospital network used Echo Pulse to predict nursing staff burnout, "
            "reducing unplanned departures by 24% and improving patient satisfaction scores."
        ),
    },
    "manufacturing": {
        "label": "Manufacturing / Industrial",
        "keywords": ["manufact", "výrob", "industr", "product", "factory", "stroj", "automot"],
        "pain_points": [
            "Communication gap between management and production floor",
            "Retention of skilled operators and technicians",
            "Safety culture tied to employee engagement levels",
            "Shift-based workforce makes traditional surveys ineffective",
        ],
        "benchmarks": {
            "avg_turnover_pct": 22,
            "replacement_cost_months": 8,
            "engagement_lift_pct": 18,
            "turnover_reduction_pct": 15,
        },
        "solution_angle": (
            "Echo Pulse bridges the factory floor gap with mobile-first pulse surveys, "
            "multilingual support, and safety-engagement correlation analysis "
            "that connects wellbeing to operational outcomes."
        ),
        "case_study": (
            "A manufacturing company (180 employees) improved retention of skilled "
            "machine operators by 20% after implementing targeted engagement interventions "
            "based on Echo Pulse insights."
        ),
    },
}

DEFAULT_INDUSTRY = {
    "label": "General Business",
    "keywords": [],
    "pain_points": [
        "Difficulty measuring employee engagement beyond annual surveys",
        "Key talent departures with no early warning",
        "Growing pains as team scales past initial culture",
        "Lack of actionable data on team morale and dynamics",
    ],
    "benchmarks": {
        "avg_turnover_pct": 18,
        "replacement_cost_months": 8,
        "engagement_lift_pct": 22,
        "turnover_reduction_pct": 18,
    },
    "solution_angle": (
        "Echo Pulse provides continuous, AI-powered employee engagement measurement "
        "with predictive attrition alerts, anonymous feedback channels, "
        "and actionable management dashboards."
    ),
    "case_study": (
        "Companies using Echo Pulse see an average 22% improvement in engagement scores "
        "and 18% reduction in unwanted turnover within the first 6 months."
    ),
}

# ── SPIN selling framework ───────────────────────────

SPIN_FRAMEWORK = {
    "situation": "Understanding your current people operations and engagement practices",
    "problem": "Identifying the gaps and pain points in how you measure and improve engagement",
    "implication": "Quantifying the cost of disengagement: turnover, productivity loss, hiring costs",
    "need_payoff": "Showing the concrete ROI of real-time engagement intelligence",
}


# ── Helpers ──────────────────────────────────────────

def plog(msg, level="INFO"):
    ts = NOW.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    LOG_FILE.parent.mkdir(exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    try:
        if LOG_FILE.stat().st_size > 200_000:
            lines = LOG_FILE.read_text().splitlines()
            LOG_FILE.write_text("\n".join(lines[-500:]) + "\n")
    except OSError:
        pass


def load_env():
    env = {}
    if not ENV_PATH.exists():
        return env
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def detect_industry(company_name, org_data=None):
    """Detect industry from company name and org data."""
    search_text = (company_name or "").lower()
    if org_data and isinstance(org_data, dict):
        search_text += " " + (org_data.get("label", "") or "").lower()
        search_text += " " + (org_data.get("address", "") or "").lower()

    for key, profile in INDUSTRY_PROFILES.items():
        for kw in profile["keywords"]:
            if kw in search_text:
                return key, profile

    return "general", DEFAULT_INDUSTRY


def pick_price_tier(employees):
    """Pick the best price tier for employee count."""
    price = 129  # default/premium
    for lower_bound, tier_price in PRICE_TIERS:
        if employees >= lower_bound:
            price = tier_price
    return price


def estimate_employees(ctx):
    """Estimate employee count from available data, never return less than 50."""
    emp = ctx.get("employees", 0)
    if emp and emp >= 10:
        return emp

    # Try to estimate from deal value
    value = ctx.get("value", 0) or 0
    if value > 0:
        # Rough estimate: deal value = ~price_per_person * employees * months
        estimated = int(value / (109 * 3))  # assume mid-tier, quarterly
        if estimated >= 20:
            return min(estimated, MAX_EMPLOYEES)

    # Default assumption for Czech mid-market
    return 100


def calculate_roi(employees, industry_benchmarks, salary=DEFAULT_SALARY):
    """Calculate ROI metrics for the proposal."""
    turnover_pct = industry_benchmarks["avg_turnover_pct"] / 100
    reduction_pct = industry_benchmarks["turnover_reduction_pct"] / 100
    replacement_months = industry_benchmarks["replacement_cost_months"]

    current_turnover = int(employees * turnover_pct)
    prevented_departures = max(1, int(current_turnover * reduction_pct))
    cost_per_departure = salary * replacement_months
    annual_savings = prevented_departures * cost_per_departure

    price_per_person = pick_price_tier(employees)
    annual_cost = price_per_person * employees * 12

    roi_ratio = annual_savings / annual_cost if annual_cost > 0 else 0

    return {
        "employees": employees,
        "current_turnover_count": current_turnover,
        "prevented_departures": prevented_departures,
        "cost_per_departure_czk": cost_per_departure,
        "annual_savings_czk": annual_savings,
        "annual_cost_czk": annual_cost,
        "monthly_cost_czk": price_per_person * employees,
        "price_per_person_czk": price_per_person,
        "roi_ratio": round(roi_ratio, 1),
        "payback_months": round(12 / roi_ratio, 1) if roi_ratio > 0 else 99,
    }


def ollama_generate(prompt, max_tokens=512, temperature=0.7, timeout=45):
    """Call local Ollama for narrative generation. Returns None on failure."""
    try:
        result = subprocess.run(
            ["curl", "-s", "-m", str(timeout),
             "http://localhost:11434/api/generate",
             "-d", json.dumps({
                 "model": "llama3.1:8b",
                 "prompt": prompt,
                 "stream": False,
                 "options": {"num_predict": max_tokens, "temperature": temperature},
             })],
            capture_output=True, text=True, timeout=timeout + 10,
        )
        if result.returncode == 0:
            response = json.loads(result.stdout)
            text = response.get("response", "").strip()
            if text and len(text) > 20:
                return text
    except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError):
        pass
    return None


# ── Data Loading ─────────────────────────────────────

def load_graph():
    """Load knowledge graph data."""
    if not GRAPH_FILE.exists():
        return None
    try:
        return json.loads(GRAPH_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def load_velocity():
    """Load deal velocity data."""
    if not VELOCITY_FILE.exists():
        return None
    try:
        return json.loads(VELOCITY_FILE.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def find_deal_in_graph(graph_data, identifier):
    """Find a deal node by ID or company name in the knowledge graph."""
    if not graph_data:
        return None, None

    nodes = graph_data.get("nodes", {})
    edges = graph_data.get("edges", [])

    # Try direct deal ID match
    deal_key = f"deal_{identifier}"
    if deal_key in nodes:
        deal_node = nodes[deal_key]
        company_node = _find_linked_company(deal_key, nodes, edges)
        return deal_node, company_node

    # Search by company name
    identifier_lower = str(identifier).lower()
    for node_id, node in nodes.items():
        props = node.get("properties", {})
        if node["type"] == "COMPANY":
            name = (props.get("name", "") or "").lower()
            if identifier_lower in name or name in identifier_lower:
                deals = _find_company_deals(node_id, nodes, edges)
                if deals:
                    return deals[0], node
                return None, node

    # Search deal titles
    for node_id, node in nodes.items():
        if node["type"] == "DEAL":
            props = node.get("properties", {})
            title = (props.get("title", "") or "").lower()
            org = (props.get("org_name", "") or "").lower()
            if identifier_lower in title or identifier_lower in org:
                company_node = _find_linked_company(node_id, nodes, edges)
                return node, company_node

    return None, None


def _find_linked_company(deal_id, nodes, edges):
    """Find company linked to a deal via edges."""
    for edge in edges:
        if edge["from_id"] == deal_id or edge["to_id"] == deal_id:
            other = edge["to_id"] if edge["from_id"] == deal_id else edge["from_id"]
            node = nodes.get(other)
            if node and node["type"] == "COMPANY":
                return node
    return None


def _find_company_deals(company_id, nodes, edges):
    """Find all deals linked to a company."""
    deals = []
    for edge in edges:
        if edge["from_id"] == company_id or edge["to_id"] == company_id:
            other = edge["to_id"] if edge["from_id"] == company_id else edge["from_id"]
            node = nodes.get(other)
            if node and node["type"] == "DEAL":
                deals.append(node)
    return deals


def fetch_deal_from_api(deal_id):
    """Fetch deal from Pipedrive API as fallback."""
    env = load_env()
    api_key = env.get("PIPEDRIVE_API_TOKEN", "")
    base_url = env.get("PIPEDRIVE_BASE_URL", "https://api.pipedrive.com/v1")

    if not api_key:
        return None

    try:
        r = subprocess.run(
            ["curl", "-s", "-m", "10",
             f"{base_url}/deals/{deal_id}?api_token={api_key}"],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(r.stdout)
        if data.get("success") and data.get("data"):
            deal = data["data"]
            org = deal.get("org_id", {})
            person = deal.get("person_id", {})
            return {
                "deal_id": deal.get("id"),
                "title": deal.get("title", ""),
                "value": deal.get("value", 0),
                "currency": deal.get("currency", "CZK"),
                "stage_id": deal.get("stage_id"),
                "status": deal.get("status", "open"),
                "company": org.get("name", "") if isinstance(org, dict) else "",
                "org_id": org.get("value") if isinstance(org, dict) else org,
                "contact_name": person.get("name", "") if isinstance(person, dict) else "",
                "add_time": deal.get("add_time", ""),
                "update_time": deal.get("update_time", ""),
                "people_count": org.get("people_count", 0) if isinstance(org, dict) else 0,
            }
    except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def get_deal_velocity_data(deal_id):
    """Get velocity data for a specific deal."""
    velocity = load_velocity()
    if not velocity:
        return None
    return velocity.get("deals", {}).get(str(deal_id))


# ── Manifest ─────────────────────────────────────────

def load_manifest():
    if MANIFEST_FILE.exists():
        try:
            return json.loads(MANIFEST_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {"proposals": [], "last_updated": None}


def save_manifest(manifest):
    PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
    manifest["last_updated"] = NOW.isoformat()
    MANIFEST_FILE.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))


# ── Proposal Generator ──────────────────────────────

class ProposalGenerator:
    """Generates data-driven sales proposals for Echo Pulse / Behavera."""

    def __init__(self):
        self.graph_data = load_graph()
        self.velocity_data = load_velocity()
        self.manifest = load_manifest()
        self.ollama_available = self._check_ollama()

    def _check_ollama(self):
        try:
            r = subprocess.run(
                ["curl", "-s", "-m", "3", "http://localhost:11434/api/tags"],
                capture_output=True, text=True, timeout=5,
            )
            return r.returncode == 0 and "llama" in r.stdout.lower()
        except (subprocess.TimeoutExpired, OSError):
            return False

    def generate(self, identifier):
        """Generate a proposal for a deal_id or company name."""
        plog(f"Generating proposal for: {identifier}")

        context = self._build_context(identifier)
        if not context:
            print(f"Could not find deal or company: {identifier}")
            plog(f"No context found for: {identifier}", "WARN")
            return None

        industry_key, industry = detect_industry(
            context.get("company", ""),
            context.get("org_data"),
        )
        context["industry_key"] = industry_key
        context["industry"] = industry

        employees = context.get("employees", 100)
        roi = calculate_roi(employees, industry["benchmarks"])
        context["roi"] = roi

        proposal_md = self._render_proposal(context)

        quality = self.score_proposal(proposal_md, context)
        context["quality"] = quality

        filepath = self._save_proposal(proposal_md, context)
        self._update_manifest(context, filepath, quality)

        plog(f"Proposal generated: {filepath.name} (quality: {quality['score']}%)")
        return {
            "file": str(filepath),
            "company": context.get("company", ""),
            "industry": industry["label"],
            "quality": quality,
            "roi": roi,
        }

    def _build_context(self, identifier):
        """Gather all available data about the deal/company."""
        context = {}

        # Try knowledge graph first
        deal_node, company_node = find_deal_in_graph(self.graph_data, identifier)

        if deal_node:
            props = deal_node.get("properties", {})
            context["deal_id"] = props.get("pipedrive_id", identifier)
            context["deal_title"] = props.get("title", "")
            context["value"] = props.get("value", 0)
            context["currency"] = props.get("currency", "CZK")
            context["stage"] = props.get("stage_name", "")
            context["status"] = props.get("status", "open")
            context["company"] = props.get("org_name", "")
            context["owner"] = props.get("owner", "")

        if company_node:
            cprops = company_node.get("properties", {})
            context["company"] = context.get("company") or cprops.get("name", "")
            context["org_data"] = cprops
            context["employees"] = cprops.get("people_count", 0) or 100
            context["org_id"] = cprops.get("pipedrive_id")

        # Try API if we have a numeric deal ID and missing data
        if str(identifier).isdigit() and not context.get("company"):
            api_data = fetch_deal_from_api(identifier)
            if api_data:
                context["deal_id"] = api_data["deal_id"]
                context["deal_title"] = api_data.get("title", "")
                context["value"] = api_data.get("value", 0)
                context["currency"] = api_data.get("currency", "CZK")
                context["company"] = api_data.get("company", "")
                context["contact_name"] = api_data.get("contact_name", "")
                context["org_id"] = api_data.get("org_id")
                context["employees"] = api_data.get("people_count", 0) or 100

        # Get velocity data
        deal_id = context.get("deal_id")
        if deal_id:
            vel = get_deal_velocity_data(deal_id)
            if vel:
                context["velocity"] = vel
                context["days_in_stage"] = vel.get("days_in_stage", 0)
                context["days_in_pipeline"] = vel.get("days_in_pipeline", 0)
                context["velocity_status"] = vel.get("velocity_status", "unknown")
                context["stage"] = context.get("stage") or vel.get("stage_name", "")
                context["company"] = context.get("company") or vel.get("org", "")
            elif self.velocity_data:
                # Search velocity by org name
                for vid, vdeal in self.velocity_data.get("deals", {}).items():
                    if (context.get("company", "").lower() in vdeal.get("org", "").lower()
                            or vdeal.get("org", "").lower() in context.get("company", "").lower()):
                        context["velocity"] = vdeal
                        context["days_in_stage"] = vdeal.get("days_in_stage", 0)
                        context["days_in_pipeline"] = vdeal.get("days_in_pipeline", 0)
                        context["velocity_status"] = vdeal.get("velocity_status", "unknown")
                        if not context.get("deal_id"):
                            context["deal_id"] = vdeal.get("id")
                        break

        # Ensure we have something to work with
        if not context.get("company") and not str(identifier).isdigit():
            context["company"] = str(identifier)

        if not context.get("company"):
            return None

        # Estimate employee count properly
        context["employees"] = estimate_employees(context)
        context.setdefault("currency", "CZK")
        context.setdefault("deal_id", "N/A")

        return context

    def _render_proposal(self, ctx):
        """Render the full proposal markdown."""
        company = ctx.get("company", "Company")
        industry = ctx["industry"]
        roi = ctx["roi"]
        employees = ctx.get("employees", 100)

        sections = [
            self._section_header(ctx),
            self._section_executive_summary(ctx),
            self._section_current_challenge(ctx),
            self._section_proposed_solution(ctx),
            self._section_expected_roi(ctx),
            self._section_implementation_timeline(ctx),
            self._section_investment(ctx),
            self._section_why_now(ctx),
            self._section_next_steps(ctx),
            self._section_footer(ctx),
        ]

        return "\n\n".join(sections)

    def _section_header(self, ctx):
        company = ctx.get("company", "Company")
        industry = ctx["industry"]
        return f"""---
company: {company}
industry: {industry['label']}
deal_id: {ctx.get('deal_id', 'N/A')}
generated: {NOW.strftime('%Y-%m-%d %H:%M')}
employees: {ctx.get('employees', 'N/A')}
---

# Sales Proposal: Echo Pulse for {company}

**Prepared by:** Josef Hofman, Behavera
**Date:** {TODAY.strftime('%d. %m. %Y')}
**Industry:** {industry['label']}
**Confidential** — prepared exclusively for {company}"""

    def _section_executive_summary(self, ctx):
        company = ctx.get("company", "Company")
        industry = ctx["industry"]
        employees = ctx.get("employees", 100)
        roi = ctx["roi"]

        if self.ollama_available:
            prompt = (
                f"Write a 3-4 sentence executive summary for a sales proposal. "
                f"Company: {company}. Industry: {industry['label']}. "
                f"Employees: ~{employees}. "
                f"Product: Echo Pulse - AI-powered employee engagement platform. "
                f"Key benefit: {roi['roi_ratio']}x ROI through reduced turnover. "
                f"Write in professional English, be specific and compelling. "
                f"Do NOT use marketing fluff. Start directly with the content."
            )
            generated = ollama_generate(prompt, max_tokens=300, temperature=0.6)
            if generated:
                return f"## Executive Summary\n\n{generated}"

        return f"""## Executive Summary

{company} operates in the {industry['label']} sector with approximately {employees} employees.
In today's competitive talent market, employee engagement is not just an HR metric — it directly
impacts retention, productivity, and bottom-line results.

Echo Pulse by Behavera provides {company} with continuous, AI-powered engagement intelligence
that transforms how you understand and retain your people. Based on our analysis,
implementing Echo Pulse can deliver a **{roi['roi_ratio']}x return on investment**
by preventing an estimated {roi['prevented_departures']} unnecessary departures annually,
saving approximately **{roi['annual_savings_czk']:,.0f} CZK** per year."""

    def _section_current_challenge(self, ctx):
        industry = ctx["industry"]
        company = ctx.get("company", "Company")
        pain_points = industry["pain_points"]

        spin_section = ""
        stage = ctx.get("stage", "")
        if "Proposal" in stage or "Negotiation" in stage:
            spin_focus = "need_payoff"
        elif "Demo" in stage or "Discussion" in stage:
            spin_focus = "implication"
        elif "Interested" in stage or "Qualified" in stage:
            spin_focus = "problem"
        else:
            spin_focus = "situation"

        spin_text = SPIN_FRAMEWORK.get(spin_focus, "")
        if spin_text:
            spin_section = f"\n\n*Focus area: {spin_text}*"

        bullets = "\n".join(f"- **{p}**" for p in pain_points)

        if self.ollama_available:
            prompt = (
                f"Write 2-3 sentences expanding on the current challenges facing {company} "
                f"in the {industry['label']} industry regarding employee engagement. "
                f"Key challenges: {'; '.join(pain_points[:2])}. "
                f"Be specific to the industry, not generic. Professional tone."
            )
            expanded = ollama_generate(prompt, max_tokens=200, temperature=0.6)
            if expanded:
                return f"""## Current Challenge

Companies in the {industry['label']} space face specific workforce challenges:

{bullets}

{expanded}{spin_section}"""

        return f"""## Current Challenge

Companies in the {industry['label']} space face specific workforce challenges:

{bullets}

These challenges compound over time. Without real-time visibility into team engagement,
issues surface only after they've already impacted performance — or when key people
hand in their notice.{spin_section}"""

    def _section_proposed_solution(self, ctx):
        industry = ctx["industry"]
        company = ctx.get("company", "Company")

        return f"""## Proposed Solution: Echo Pulse by Behavera

{industry['solution_angle']}

### Core Capabilities

| Feature | What It Does | Impact for {company} |
|---------|-------------|---------------------|
| **AI Pulse Surveys** | Adaptive micro-surveys (2-3 min) | High response rates without survey fatigue |
| **Predictive Attrition** | ML models flag flight risk | Intervene before talent walks out the door |
| **Team Dynamics** | Map collaboration and engagement patterns | Identify team health issues early |
| **Manager Dashboard** | Real-time engagement scores by team | Actionable insights, not data dumps |
| **Anonymous Feedback** | Secure, confidential channel | Honest input from all levels |
| **Benchmarking** | Industry and internal benchmarks | Context for your numbers |

### Success Story

> {industry['case_study']}"""

    def _section_expected_roi(self, ctx):
        roi = ctx["roi"]
        industry = ctx["industry"]
        benchmarks = industry["benchmarks"]

        return f"""## Expected ROI

### The Cost of Disengagement

| Metric | Your Estimate |
|--------|--------------|
| Current workforce | ~{roi['employees']} employees |
| Industry avg. turnover | {benchmarks['avg_turnover_pct']}% |
| Expected annual departures | ~{roi['current_turnover_count']} people |
| Average replacement cost | {roi['cost_per_departure_czk']:,.0f} CZK ({benchmarks['replacement_cost_months']} months salary) |
| **Annual cost of turnover** | **{roi['current_turnover_count'] * roi['cost_per_departure_czk']:,.0f} CZK** |

### With Echo Pulse

| Metric | Projected Impact |
|--------|-----------------|
| Engagement improvement | +{benchmarks['engagement_lift_pct']}% |
| Turnover reduction | -{benchmarks['turnover_reduction_pct']}% |
| Prevented departures | ~{roi['prevented_departures']}/year |
| **Annual savings** | **{roi['annual_savings_czk']:,.0f} CZK** |
| Echo Pulse cost | {roi['annual_cost_czk']:,.0f} CZK/year |
| **Net benefit** | **{roi['annual_savings_czk'] - roi['annual_cost_czk']:,.0f} CZK/year** |
| **ROI** | **{roi['roi_ratio']}x** |
| **Payback period** | **{roi['payback_months']:.0f} months** |

> One prevented departure saves more than an entire year of Echo Pulse."""

    def _section_implementation_timeline(self, ctx):
        company = ctx.get("company", "Company")

        return f"""## Implementation Timeline

### Phase 1: Setup & Launch (Weeks 1-2)
- Technical integration and platform configuration
- Survey template customization for {company}
- Manager onboarding and training session
- Initial baseline pulse survey deployment

### Phase 2: Insights & Action (Weeks 3-8)
- First engagement report and team dynamics analysis
- Predictive model calibration with {company}'s data
- Manager coaching on interpreting and acting on insights
- Anonymous feedback channel activation

### Phase 3: Optimization & Scale (Weeks 9-12)
- ROI review against baseline metrics
- Survey cadence optimization based on response patterns
- Advanced analytics: attrition prediction, team health trends
- Quarterly business review and success metrics report

> Total time to first actionable insights: **2 weeks**
> Full deployment and optimization: **12 weeks**"""

    def _section_investment(self, ctx):
        employees = ctx.get("employees", 100)
        roi = ctx["roi"]

        # Build pricing tiers relevant to company size
        scenarios = []
        for lower_bound, price in PRICE_TIERS:
            if employees >= lower_bound - 20:
                monthly = price * employees
                quarterly = monthly * 3
                annual = monthly * 12
                scenarios.append((lower_bound, price, monthly, quarterly, annual))

        # Always show at least the premium tier
        if not scenarios:
            price = 129
            monthly = price * employees
            scenarios.append((50, price, monthly, monthly * 3, monthly * 12))

        selected_price = roi["price_per_person_czk"]

        rows = []
        for lb, price, monthly, quarterly, annual in scenarios:
            marker = " **recommended**" if price == selected_price else ""
            rows.append(
                f"| {price} CZK/person | {monthly:,.0f} CZK | {quarterly:,.0f} CZK | "
                f"{annual:,.0f} CZK |{marker}"
            )

        pricing_table = "\n".join(rows)

        return f"""## Investment

### Echo Pulse Pricing ({employees} employees)

| Per Person/Month | Monthly Total | Quarterly | Annual |
|-----------------|---------------|-----------|--------|
{pricing_table}

### Pilot Option

| | Details |
|---|---|
| **3-Month Pilot** | {PILOT_PRICE:,.0f} CZK flat fee (up to {MAX_EMPLOYEES} people) |
| **What's included** | Full platform access, setup, training, 3 pulse cycles, ROI report |
| **Risk** | Zero — if results don't meet expectations, no further commitment |

> **Our recommendation:** Start with a 3-month pilot to validate ROI with real data from your team."""

    def _section_why_now(self, ctx):
        company = ctx.get("company", "Company")
        urgency_points = []

        # Velocity-based urgency
        velocity = ctx.get("velocity")
        if velocity:
            days_in_pipeline = ctx.get("days_in_pipeline", 0)
            if days_in_pipeline > 30:
                urgency_points.append(
                    f"This conversation has been in motion for {days_in_pipeline} days — "
                    f"every week of delay means another week without engagement visibility."
                )
            vel_status = ctx.get("velocity_status", "")
            if vel_status == "hot":
                urgency_points.append(
                    "Your team is moving fast on this decision — let's maintain that momentum "
                    "and lock in the current terms."
                )

        # Market urgency
        urgency_points.extend([
            "The Czech labor market remains tight — talent competition means "
            "retention intelligence is no longer optional.",
            "Companies that implement engagement tools now build a data advantage: "
            "6 months of baseline data creates predictive models no amount of money can buy later.",
            "Current pilot pricing is available this quarter — we review pricing quarterly "
            "based on demand.",
        ])

        bullets = "\n".join(f"- {p}" for p in urgency_points[:4])

        if self.ollama_available:
            prompt = (
                f"Write 1-2 compelling sentences about why {company} should act now "
                f"on implementing an employee engagement platform. "
                f"Context: Czech market, {ctx.get('employees', 100)} employees, "
                f"{ctx['industry']['label']} industry. "
                f"Be specific, not generic urgency. Professional tone."
            )
            why_now_extra = ollama_generate(prompt, max_tokens=150, temperature=0.6)
            if why_now_extra:
                bullets += f"\n\n{why_now_extra}"

        return f"""## Why Now

{bullets}

> The best time to measure engagement was 6 months ago. The second best time is today."""

    def _section_next_steps(self, ctx):
        company = ctx.get("company", "Company")
        contact = ctx.get("contact_name", "your team")

        return f"""## Next Steps

1. **Schedule a walkthrough** (30 min) — I'll walk {contact} through the pilot scope
   and answer any remaining questions.
2. **Pilot agreement** — Simple 3-month commitment, full platform access from day 1.
3. **Kick-off call** — Technical setup + survey customization (within 1 week of signing).
4. **First pulse results** — Actionable insights within 2 weeks of launch.

I'll follow up within the next 2 business days. If you'd like to move faster,
reach out directly:

**Josef Hofman**
Behavera | Echo Pulse
josef@behavera.com"""

    def _section_footer(self, ctx):
        proposal_id = hashlib.md5(
            f"{ctx.get('company', '')}{NOW.isoformat()}".encode()
        ).hexdigest()[:8]

        return f"""---

*Proposal ID: {proposal_id} | Generated: {NOW.strftime('%Y-%m-%d %H:%M')}*
*This proposal is confidential and intended solely for {ctx.get('company', 'the recipient')}.*
*Valid for 30 days from the date of issue.*"""

    def _save_proposal(self, proposal_md, ctx):
        """Save proposal to proposals/ directory."""
        PROPOSALS_DIR.mkdir(parents=True, exist_ok=True)
        company_slug = re.sub(r'[^a-z0-9]+', '-', ctx.get("company", "unknown").lower()).strip("-")
        filename = f"proposal_{company_slug}_{TODAY.isoformat()}.md"
        filepath = PROPOSALS_DIR / filename
        filepath.write_text(proposal_md, encoding="utf-8")
        return filepath

    def _update_manifest(self, ctx, filepath, quality):
        """Update the proposal manifest."""
        entry = {
            "file": filepath.name,
            "company": ctx.get("company", ""),
            "deal_id": ctx.get("deal_id", "N/A"),
            "industry": ctx["industry"]["label"],
            "employees": ctx.get("employees", 0),
            "quality_score": quality["score"],
            "quality_rating": quality["rating"],
            "roi_ratio": ctx["roi"]["roi_ratio"],
            "generated_at": NOW.isoformat(),
            "ollama_used": self.ollama_available,
        }

        self.manifest["proposals"].append(entry)
        save_manifest(self.manifest)

    def score_proposal(self, proposal_md=None, ctx=None, filepath=None):
        """Score a proposal on multiple quality dimensions."""
        if filepath and not proposal_md:
            path = Path(filepath)
            if not path.is_absolute():
                path = PROPOSALS_DIR / path
            if path.exists():
                proposal_md = path.read_text()
            else:
                return {"score": 0, "rating": "error", "details": {}, "feedback": "File not found"}

        if not proposal_md:
            return {"score": 0, "rating": "error", "details": {}, "feedback": "No content"}

        company = ""
        if ctx:
            company = ctx.get("company", "")
        else:
            m = re.search(r'^company:\s*(.+)$', proposal_md, re.MULTILINE)
            if m:
                company = m.group(1).strip()

        checks = {
            "has_exec_summary": bool(re.search(r'## Executive Summary', proposal_md)),
            "has_challenge": bool(re.search(r'## Current Challenge', proposal_md)),
            "has_solution": bool(re.search(r'## Proposed Solution', proposal_md)),
            "has_roi": bool(re.search(r'## Expected ROI', proposal_md)),
            "has_timeline": bool(re.search(r'## Implementation Timeline', proposal_md)),
            "has_investment": bool(re.search(r'## Investment', proposal_md)),
            "has_why_now": bool(re.search(r'## Why Now', proposal_md)),
            "has_next_steps": bool(re.search(r'## Next Steps', proposal_md)),
            "company_mentioned": proposal_md.count(company) >= 5 if company else False,
            "has_roi_numbers": bool(re.search(r'\d+[.,]\d+.*CZK', proposal_md)),
            "has_pricing_table": bool(re.search(r'CZK/person', proposal_md)),
            "has_case_study": bool(re.search(r'(?:case study|success story|reduced|improved)', proposal_md, re.I)),
            "reasonable_length": 2000 <= len(proposal_md) <= 15000,
            "has_contact_info": bool(re.search(r'josef@behavera|Josef Hofman', proposal_md)),
            "has_urgency": bool(re.search(r'(?:now|today|this quarter|current)', proposal_md, re.I)),
        }

        total = sum(checks.values())
        max_score = len(checks)
        pct = round(total / max_score * 100)

        if pct >= 90:
            rating = "excellent"
        elif pct >= 75:
            rating = "good"
        elif pct >= 55:
            rating = "acceptable"
        else:
            rating = "needs_work"

        missing = [k.replace("has_", "").replace("_", " ") for k, v in checks.items() if not v]
        feedback = f"Missing: {', '.join(missing)}" if missing else "All quality checks passed"

        return {
            "score": pct,
            "rating": rating,
            "details": checks,
            "feedback": feedback,
        }

    def list_proposals(self):
        """List all generated proposals from manifest."""
        proposals = self.manifest.get("proposals", [])
        if not proposals:
            print("No proposals generated yet.")
            print(f"Generate one: python3 scripts/proposal_generator.py generate <deal_id|company>")
            return

        print(f"\nGenerated Proposals ({len(proposals)})")
        print("=" * 80)
        print(f"{'Company':<25} {'Industry':<18} {'Quality':>8} {'ROI':>6} {'Date':<12} {'File'}")
        print("-" * 80)

        for p in sorted(proposals, key=lambda x: x.get("generated_at", ""), reverse=True):
            print(
                f"{p.get('company', '?')[:24]:<25} "
                f"{p.get('industry', '?')[:17]:<18} "
                f"{p.get('quality_score', 0):>6}% "
                f"{p.get('roi_ratio', 0):>5.1f}x "
                f"{p.get('generated_at', '')[:10]:<12} "
                f"{p.get('file', '')}"
            )

        print(f"\nProposals directory: {PROPOSALS_DIR}")


# ── CLI ──────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  proposal_generator.py generate <deal_id|company_name>")
        print("  proposal_generator.py list")
        print("  proposal_generator.py show <proposal_file>")
        print("  proposal_generator.py score <proposal_file>")
        sys.exit(0)

    cmd = sys.argv[1]
    gen = ProposalGenerator()

    if cmd == "generate":
        if len(sys.argv) < 3:
            print("Usage: proposal_generator.py generate <deal_id|company_name>")
            sys.exit(1)

        identifier = " ".join(sys.argv[2:])
        result = gen.generate(identifier)
        if result:
            print(f"\nProposal generated for {result['company']}")
            print(f"  Industry: {result['industry']}")
            print(f"  Quality:  {result['quality']['score']}% ({result['quality']['rating']})")
            print(f"  ROI:      {result['roi']['roi_ratio']}x")
            print(f"  File:     {result['file']}")
            if result['quality']['score'] < 75:
                print(f"  Note:     {result['quality']['feedback']}")
        else:
            sys.exit(1)

    elif cmd == "list":
        gen.list_proposals()

    elif cmd == "show":
        if len(sys.argv) < 3:
            print("Usage: proposal_generator.py show <proposal_file>")
            sys.exit(1)
        filepath = Path(sys.argv[2])
        if not filepath.is_absolute():
            filepath = PROPOSALS_DIR / filepath
        if filepath.exists():
            print(filepath.read_text())
        else:
            print(f"File not found: {filepath}")
            sys.exit(1)

    elif cmd == "score":
        if len(sys.argv) < 3:
            print("Usage: proposal_generator.py score <proposal_file>")
            sys.exit(1)
        filepath = sys.argv[2]
        quality = gen.score_proposal(filepath=filepath)
        print(f"\nQuality Score: {quality['score']}% ({quality['rating']})")
        print(f"Feedback: {quality['feedback']}")
        print()
        for check, passed in quality["details"].items():
            status = "OK" if passed else "MISS"
            print(f"  [{status:>4}] {check.replace('_', ' ')}")

    else:
        print(f"Unknown command: {cmd}")
        print("Commands: generate, list, show, score")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        LOG_FILE.parent.mkdir(exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] [FATAL] {e}\n")
            f.write(traceback.format_exc() + "\n")
        print(f"FATAL: {e}", file=sys.stderr)
        raise
