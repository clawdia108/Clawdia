#!/usr/bin/env python3
"""
Competitive Intelligence Tracker — competitor profiling, mention extraction, battle cards
==========================================================================================
Scans Pipedrive deals for competitor mentions, maintains competitor profiles,
generates battle cards, and tracks win/loss records per competitor.

Usage:
  python3 scripts/competitive_intel.py scan                  # Scan deals for competitor mentions
  python3 scripts/competitive_intel.py profile <competitor>   # Show competitor profile
  python3 scripts/competitive_intel.py battlecard <competitor> # Generate battle card
  python3 scripts/competitive_intel.py dashboard              # Competitive overview
  python3 scripts/competitive_intel.py trends                 # Competitive trends
"""

import json
import re
import statistics
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import datetime, date, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
ENV_PATH = WORKSPACE / ".secrets" / "pipedrive.env"
INTEL_DIR = WORKSPACE / "intel"
BATTLECARD_DIR = INTEL_DIR / "battle-cards"
INTEL_DATA_FILE = INTEL_DIR / "competitive-intel.json"
LOG_FILE = WORKSPACE / "logs" / "competitive-intel.log"

TODAY = date.today()
NOW = datetime.now()

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

STAGE_NAMES = {sid: name for sid, (name, _) in SALES_STAGES.items()}


# ── ENV & API ──────────────────────────────────────────

def load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def api_request(base, token, method, path, params=None, data=None, retry=3):
    params = dict(params or {})
    params["api_token"] = token
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"
    headers = {}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
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
        j = api_request(base, token, "GET", path, params=p)
        if not j or not j.get("success"):
            break
        out.extend(j.get("data") or [])
        pag = (j.get("additional_data") or {}).get("pagination") or {}
        if not pag.get("more_items_in_collection"):
            break
        start = pag.get("next_start", start + 500)
    return out


def cilog(msg, level="INFO"):
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


def _slog(message, level="INFO", meta=None):
    try:
        sys.path.insert(0, str(WORKSPACE / "scripts"))
        from structured_log import slog
        slog(message, level=level, source="competitive_intel", meta=meta)
    except Exception:
        cilog(f"{message} {json.dumps(meta) if meta else ''}", level)


def parse_date(date_str):
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def days_between(d1, d2=None):
    if not d1:
        return 999
    d2 = d2 or TODAY
    if isinstance(d1, str):
        d1 = parse_date(d1)
    if isinstance(d2, str):
        d2 = parse_date(d2)
    if not d1 or not d2:
        return 999
    return (d2 - d1).days


def _strip_html(text):
    return re.sub(r'<[^>]+>', ' ', text).strip()


_ollama_available = None  # cached health check

def _ollama_generate(prompt, max_tokens=512, temperature=0.3):
    global _ollama_available
    if _ollama_available is False:
        return None
    try:
        if _ollama_available is None:
            urllib.request.urlopen("http://localhost:11434/api/tags", timeout=3)
            _ollama_available = True
    except Exception:
        _ollama_available = False
        return None
    try:
        data = json.dumps({
            "model": "llama3.1:8b",
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": temperature},
        }).encode()
        req = urllib.request.Request(
            "http://localhost:11434/api/generate",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        resp = urllib.request.urlopen(req, timeout=15)
        result = json.loads(resp.read())
        return result.get("response", "").strip()
    except Exception as e:
        cilog(f"Ollama call failed (non-fatal): {e}", "WARN")
        return None


# ── COMPETITOR PROFILES ────────────────────────────────

class CompetitorProfile:
    """Pre-loaded competitor intelligence for the employee engagement / HR tech space."""

    COMPETITORS = {
        "peakon": {
            "name": "Peakon (Workday)",
            "category": "Enterprise Employee Engagement",
            "parent_company": "Workday",
            "pricing_model": "Per employee/month, enterprise contracts (typically $5-8/employee/mo)",
            "target_market": "Enterprise 1000+ employees, global organizations",
            "key_features": [
                "Continuous listening platform",
                "AI-driven insights and recommendations",
                "Benchmarking against 200M+ data points",
                "Multi-language support (60+ languages)",
                "Integration with Workday HCM",
                "Manager dashboards and action plans",
            ],
            "strengths": [
                "Massive benchmark dataset",
                "Workday ecosystem integration",
                "Strong AI/NLP for open-text analysis",
                "Global enterprise proven",
                "Continuous (not annual) surveys",
            ],
            "weaknesses": [
                "Expensive — enterprise pricing out of reach for SMBs",
                "Overkill for companies under 500 employees",
                "Complex implementation (3-6 months)",
                "Locked into Workday ecosystem",
                "Less flexible survey design",
            ],
            "typical_objections": [
                "Peakon has more benchmark data",
                "Workday integration is seamless for us",
                "They have AI-driven recommendations",
                "Peakon is the industry standard",
            ],
            "counter_messaging": [
                "Benchmark data means nothing if the questions don't fit your culture",
                "You don't need Workday lock-in — Echo Pulse integrates with any HRIS",
                "Our AI focuses on actionable Czech/CEE market insights, not generic global averages",
                "Industry standard means one-size-fits-all — we customize for your reality",
            ],
        },
        "culture_amp": {
            "name": "Culture Amp",
            "category": "People & Culture Platform",
            "parent_company": "Independent (VC-backed)",
            "pricing_model": "Per employee/month, tiered plans ($4-11/employee/mo)",
            "target_market": "Mid-market 200-5000 employees, culture-forward companies",
            "key_features": [
                "Employee engagement surveys",
                "Performance management",
                "360-degree feedback",
                "DEI analytics",
                "People science-backed templates",
                "Manager effectiveness tools",
            ],
            "strengths": [
                "Strong people-science team and methodology",
                "All-in-one (engagement + performance + development)",
                "Good UI/UX — modern feel",
                "Strong brand in culture-focused companies",
                "Decent mid-market pricing",
            ],
            "weaknesses": [
                "Jack of all trades — engagement module not as deep",
                "Limited CEE/Czech market presence",
                "No local language support for smaller markets",
                "Performance module competes with their own engagement focus",
                "US-centric benchmarks",
            ],
            "typical_objections": [
                "Culture Amp does engagement AND performance in one tool",
                "Their people-science team is world-class",
                "We already use Culture Amp for performance reviews",
            ],
            "counter_messaging": [
                "All-in-one sounds great until you need depth — our engagement module goes deeper",
                "People science is universal but implementation needs local expertise — we know Czech companies",
                "Keep Culture Amp for performance, add Echo Pulse for real engagement insights — they complement",
            ],
        },
        "officevibe": {
            "name": "Officevibe (Workleap)",
            "category": "Employee Experience Platform",
            "parent_company": "Workleap (formerly GSoft)",
            "pricing_model": "Per person/month, free tier available ($3.50-5/person/mo)",
            "target_market": "SMBs 50-500 employees, teams wanting quick wins",
            "key_features": [
                "Pulse surveys (weekly automated)",
                "Anonymous feedback channel",
                "1-on-1 meeting tools",
                "Recognition features",
                "eNPS tracking",
                "Good-vibes tool for team mood",
            ],
            "strengths": [
                "Free tier available — low barrier to entry",
                "Very simple to set up (minutes, not weeks)",
                "Good for small teams and startups",
                "Anonymous feedback encourages honesty",
                "Lightweight, not overwhelming",
            ],
            "weaknesses": [
                "Too basic for serious analytics",
                "Limited customization of surveys",
                "No deep industry benchmarks",
                "Reporting is surface-level",
                "Doesn't scale well past 500 employees",
                "No Czech/local language",
            ],
            "typical_objections": [
                "Officevibe is free / much cheaper",
                "It's simple and our team already uses it",
                "We just need basic pulse surveys",
            ],
            "counter_messaging": [
                "Free gets you data, not insights — Echo Pulse tells you what to DO with the data",
                "Simple = limited. When your CEO asks 'why is turnover up?', Officevibe can't answer",
                "Basic pulse surveys are table stakes — the value is in analysis, trends, and action plans",
            ],
        },
        "lattice": {
            "name": "Lattice",
            "category": "People Management Platform",
            "parent_company": "Independent (VC-backed)",
            "pricing_model": "Per person/month, modular ($4-11/person/mo per module)",
            "target_market": "Mid-market 200-2000 employees, HR-mature organizations",
            "key_features": [
                "Performance reviews and cycles",
                "OKR/goal tracking",
                "Engagement surveys",
                "Compensation management",
                "Career development tracks",
                "Analytics and reporting",
            ],
            "strengths": [
                "Best-in-class performance management",
                "Strong OKR integration",
                "Modular pricing — buy what you need",
                "Good enterprise features (compensation, career)",
                "Growing fast, strong product team",
            ],
            "weaknesses": [
                "Engagement is an add-on, not the core product",
                "Expensive when you stack modules",
                "Complex setup for full suite",
                "US-focused — limited European presence",
                "Engagement surveys feel bolted on",
            ],
            "typical_objections": [
                "Lattice does performance + engagement together",
                "We already use Lattice for OKRs",
                "They have compensation management too",
            ],
            "counter_messaging": [
                "Lattice is a performance tool that added engagement — we're engagement-first",
                "Keep Lattice for OKRs, use Echo Pulse for what it can't do — deep engagement analytics",
                "Compensation management is separate from understanding WHY people leave — that's our focus",
            ],
        },
        "15five": {
            "name": "15Five",
            "category": "Performance Management & Engagement",
            "parent_company": "Independent (VC-backed)",
            "pricing_model": "Per user/month, tiered ($4-14/user/mo)",
            "target_market": "SMBs and mid-market, manager-focused organizations",
            "key_features": [
                "Weekly check-ins (15 min to write, 5 min to read)",
                "OKR tracking",
                "1-on-1 meeting agendas",
                "Engagement surveys",
                "High-five recognition",
                "Manager training (Transform product)",
            ],
            "strengths": [
                "Great manager enablement philosophy",
                "Weekly cadence keeps pulse on team",
                "Simple, opinionated workflow",
                "Strong focus on manager-report relationship",
                "Good content and thought leadership",
            ],
            "weaknesses": [
                "Engagement surveys are secondary to check-ins",
                "Less analytical depth for HR/people teams",
                "Small benchmark dataset",
                "No European localization",
                "Opinionated workflow doesn't fit every culture",
            ],
            "typical_objections": [
                "15Five has weekly check-ins built in",
                "Their manager training program is great",
                "We want the check-in workflow, not just surveys",
            ],
            "counter_messaging": [
                "Weekly check-ins tell you what people SAY — engagement analytics reveal what they FEEL",
                "Manager training is great, but without data on where to focus, training is generic",
                "Check-ins complement surveys — use 15Five for dialogue, Echo Pulse for measurement",
            ],
        },
        "glint": {
            "name": "Glint (LinkedIn/Microsoft)",
            "category": "Employee Engagement Platform",
            "parent_company": "Microsoft (via LinkedIn)",
            "pricing_model": "Enterprise contracts, bundled with Viva ($2-6/user/mo estimated)",
            "target_market": "Enterprise 2000+ employees, Microsoft-heavy organizations",
            "key_features": [
                "Engagement surveys with AI insights",
                "Microsoft Viva integration",
                "LinkedIn Learning tie-in",
                "Manager effectiveness dashboards",
                "Organizational network analysis",
                "Narrative intelligence (NLP)",
            ],
            "strengths": [
                "Microsoft ecosystem integration (Teams, Viva, Outlook)",
                "LinkedIn data enrichment",
                "Enterprise-grade security and compliance",
                "Bundled pricing with Microsoft 365",
                "Strong NLP and AI capabilities",
            ],
            "weaknesses": [
                "Only makes sense in Microsoft-heavy shops",
                "Being absorbed into Viva — product direction unclear",
                "Enterprise-only — not for SMBs",
                "Complex licensing and procurement",
                "Less standalone identity — becoming a Viva feature",
            ],
            "typical_objections": [
                "We already have Microsoft 365, Glint comes included",
                "Viva integration is seamless",
                "Microsoft handles our security/compliance",
            ],
            "counter_messaging": [
                "Included doesn't mean good — Excel is included too but you still buy analytics tools",
                "Viva integration means you get a feature, not a product — Echo Pulse is purpose-built",
                "Security and compliance are table stakes — the question is: does it actually reduce turnover?",
            ],
        },
    }

    COMPETITOR_ALIASES = {
        "workday": "peakon",
        "peakon": "peakon",
        "culture amp": "culture_amp",
        "cultureamp": "culture_amp",
        "officevibe": "officevibe",
        "workleap": "officevibe",
        "gsofft": "officevibe",
        "lattice": "lattice",
        "15five": "15five",
        "fifteen five": "15five",
        "glint": "glint",
        "viva": "glint",
        "microsoft viva": "glint",
        "linkedin": "glint",
    }

    @classmethod
    def get(cls, name):
        key = cls.COMPETITOR_ALIASES.get(name.lower().strip(), name.lower().strip().replace(" ", "_"))
        return cls.COMPETITORS.get(key)

    @classmethod
    def find_by_mention(cls, text):
        text_lower = text.lower()
        found = []
        for alias, key in cls.COMPETITOR_ALIASES.items():
            if alias in text_lower and key not in found:
                found.append(key)
        return found

    @classmethod
    def all_keys(cls):
        return list(cls.COMPETITORS.keys())

    @classmethod
    def all_names(cls):
        return [c["name"] for c in cls.COMPETITORS.values()]


# ── COMPETITOR MENTION EXTRACTOR ───────────────────────

MENTION_CONTEXT_KEYWORDS = {
    "comparison": ["compared", "comparison", "vs", "versus", "benchmark", "evaluate", "shortlist",
                    "RFP", "tender", "side by side", "head to head"],
    "objection": ["objection", "concern", "hesitation", "pushback", "but they", "they have",
                   "worried about", "they offer", "they said"],
    "price": ["price", "cost", "expensive", "cheaper", "budget", "afford", "pricing",
              "discount", "free tier", "included"],
    "feature_gap": ["feature", "missing", "don't have", "can't do", "doesn't support",
                     "no integration", "lacks", "limited", "gap", "wish list"],
}


class CompetitorMentionExtractor:
    """Scan Pipedrive deals for competitor mentions with context classification."""

    def __init__(self, base_url, api_token):
        self.base = base_url
        self.token = api_token
        self._deals_cache = None
        self._notes_cache = None

    def _fetch_all_deals(self):
        if self._deals_cache is not None:
            return self._deals_cache
        cilog("Fetching all deals for competitor scan...")
        self._deals_cache = paged_get(self.base, self.token, "/api/v1/deals", {"status": "all_not_deleted"})
        cilog(f"Fetched {len(self._deals_cache)} deals")
        return self._deals_cache

    def _fetch_all_notes(self):
        if self._notes_cache is not None:
            return self._notes_cache
        cilog("Fetching all notes for competitor scan...")
        self._notes_cache = paged_get(self.base, self.token, "/api/v1/notes")
        cilog(f"Fetched {len(self._notes_cache)} notes")
        return self._notes_cache

    def _fetch_deal_notes(self, deal_id):
        try:
            return paged_get(self.base, self.token, f"/api/v1/deals/{deal_id}/notes", {})
        except Exception as e:
            cilog(f"Failed to fetch notes for deal {deal_id}: {e}", "WARN")
        return []

    def _classify_context_rule_based(self, text):
        text_lower = text.lower()
        contexts = []
        for context_type, keywords in MENTION_CONTEXT_KEYWORDS.items():
            for kw in keywords:
                if kw in text_lower:
                    contexts.append(context_type)
                    break
        return contexts if contexts else ["general"]

    def _classify_context_ollama(self, text, competitor_name):
        prompt = (
            f"Classify this deal note mentioning competitor '{competitor_name}' into ONE or more categories. "
            f"Categories: comparison, objection, price, feature_gap. "
            f"Reply with ONLY the category names separated by commas, nothing else.\n\n"
            f"Text: {text[:500]}"
        )
        result = _ollama_generate(prompt, max_tokens=64, temperature=0.1)
        if result:
            valid = {"comparison", "objection", "price", "feature_gap"}
            categories = [c.strip().lower().replace(" ", "_") for c in result.split(",")]
            categories = [c for c in categories if c in valid]
            if categories:
                return categories
        return None

    def classify_context(self, text, competitor_name):
        ollama_result = self._classify_context_ollama(text, competitor_name)
        if ollama_result:
            return ollama_result
        return self._classify_context_rule_based(text)

    def scan_deal_notes(self):
        """Scan all deal notes for competitor mentions."""
        cilog("Scanning deal notes for competitor mentions...")
        notes = self._fetch_all_notes()
        mentions = []

        for note in notes:
            content = _strip_html(note.get("content") or "")
            if not content:
                continue

            found_competitors = CompetitorProfile.find_by_mention(content)
            for comp_key in found_competitors:
                comp = CompetitorProfile.COMPETITORS[comp_key]
                contexts = self.classify_context(content, comp["name"])
                mentions.append({
                    "competitor": comp_key,
                    "competitor_name": comp["name"],
                    "deal_id": note.get("deal_id"),
                    "org_id": note.get("org_id"),
                    "context": contexts,
                    "snippet": content[:300],
                    "date": (note.get("add_time") or "")[:10],
                    "source": "note",
                })

        cilog(f"Found {len(mentions)} competitor mentions in notes")
        return mentions

    def scan_loss_reasons(self):
        """Extract competitor mentions from deal loss reasons."""
        cilog("Scanning loss reasons for competitor mentions...")
        deals = self._fetch_all_deals()
        lost = [d for d in deals if d.get("status") == "lost"]
        mentions = []

        for deal in lost:
            reason = (deal.get("lost_reason") or "").strip()
            if not reason:
                continue

            found_competitors = CompetitorProfile.find_by_mention(reason)

            # Also check generic competitor keywords
            generic_keywords = ["competitor", "alternative", "other vendor", "chose another", "went with"]
            has_generic = any(kw in reason.lower() for kw in generic_keywords)

            for comp_key in found_competitors:
                comp = CompetitorProfile.COMPETITORS[comp_key]
                contexts = self.classify_context(reason, comp["name"])
                mentions.append({
                    "competitor": comp_key,
                    "competitor_name": comp["name"],
                    "deal_id": deal.get("id"),
                    "deal_title": deal.get("title", ""),
                    "org": deal.get("org_name") or "",
                    "value": deal.get("value") or 0,
                    "context": contexts,
                    "reason": reason,
                    "lost_time": (deal.get("lost_time") or "")[:10],
                    "source": "loss_reason",
                })

            if has_generic and not found_competitors:
                mentions.append({
                    "competitor": "unknown",
                    "competitor_name": "Unknown Competitor",
                    "deal_id": deal.get("id"),
                    "deal_title": deal.get("title", ""),
                    "org": deal.get("org_name") or "",
                    "value": deal.get("value") or 0,
                    "context": self._classify_context_rule_based(reason),
                    "reason": reason,
                    "lost_time": (deal.get("lost_time") or "")[:10],
                    "source": "loss_reason",
                })

        cilog(f"Found {len(mentions)} competitor mentions in loss reasons")
        return mentions

    def full_scan(self):
        """Run complete competitor mention scan across notes and loss reasons."""
        _slog("Starting full competitor mention scan")

        note_mentions = self.scan_deal_notes()
        loss_mentions = self.scan_loss_reasons()

        all_mentions = note_mentions + loss_mentions
        all_mentions.sort(key=lambda m: m.get("date") or m.get("lost_time", ""), reverse=True)

        # Build per-competitor summary
        by_competitor = defaultdict(list)
        for m in all_mentions:
            by_competitor[m["competitor"]].append(m)

        summary = {}
        for comp_key, comp_mentions in by_competitor.items():
            note_count = sum(1 for m in comp_mentions if m["source"] == "note")
            loss_count = sum(1 for m in comp_mentions if m["source"] == "loss_reason")
            context_counts = defaultdict(int)
            for m in comp_mentions:
                for ctx in m.get("context", []):
                    context_counts[ctx] += 1

            total_lost_value = sum(m.get("value", 0) for m in comp_mentions if m["source"] == "loss_reason")

            recent_90d = [m for m in comp_mentions
                          if (m.get("date") or m.get("lost_time", "")) >= (TODAY - timedelta(days=90)).isoformat()[:10]]

            summary[comp_key] = {
                "competitor": comp_key,
                "name": comp_mentions[0].get("competitor_name", comp_key),
                "total_mentions": len(comp_mentions),
                "note_mentions": note_count,
                "loss_mentions": loss_count,
                "context_breakdown": dict(context_counts),
                "total_lost_value": total_lost_value,
                "recent_90d_mentions": len(recent_90d),
                "first_seen": min((m.get("date") or m.get("lost_time", "9999")) for m in comp_mentions),
                "last_seen": max((m.get("date") or m.get("lost_time", "0000")) for m in comp_mentions),
            }

        result = {
            "mentions": all_mentions,
            "by_competitor": summary,
            "total_mentions": len(all_mentions),
            "scan_date": TODAY.isoformat(),
            "scanned_at": NOW.isoformat(),
        }

        # Persist
        INTEL_DIR.mkdir(parents=True, exist_ok=True)
        INTEL_DATA_FILE.write_text(json.dumps(result, indent=2, ensure_ascii=False))
        cilog(f"Scan complete: {len(all_mentions)} mentions, {len(summary)} competitors. Saved to {INTEL_DATA_FILE}")
        _slog("Competitor scan complete", meta={"mentions": len(all_mentions), "competitors": len(summary)})

        return result


# ── BATTLE CARD GENERATOR ──────────────────────────────

class BattleCardGenerator:
    """Generate per-competitor battle cards with win/loss data."""

    def __init__(self, base_url, api_token):
        self.base = base_url
        self.token = api_token
        self._intel_data = None

    def _load_intel(self):
        if self._intel_data is not None:
            return self._intel_data
        if INTEL_DATA_FILE.exists():
            try:
                self._intel_data = json.loads(INTEL_DATA_FILE.read_text())
                return self._intel_data
            except (json.JSONDecodeError, OSError):
                pass
        self._intel_data = {}
        return self._intel_data

    def _get_win_loss_record(self, comp_key):
        """Calculate win/loss record against a specific competitor."""
        intel = self._load_intel()
        mentions = intel.get("mentions", [])
        comp_mentions = [m for m in mentions if m["competitor"] == comp_key]

        deal_ids = set()
        for m in comp_mentions:
            if m.get("deal_id"):
                deal_ids.add(m["deal_id"])

        if not deal_ids:
            return {"wins": 0, "losses": 0, "open": 0, "win_rate": 0, "deals": []}

        wins = 0
        losses = 0
        open_deals = 0
        deal_details = []

        for deal_id in deal_ids:
            try:
                resp = api_request(self.base, self.token, "GET", f"/api/v1/deals/{deal_id}")
                if resp and resp.get("success") and resp.get("data"):
                    deal = resp["data"]
                    status = deal.get("status", "")
                    if status == "won":
                        wins += 1
                    elif status == "lost":
                        losses += 1
                    elif status == "open":
                        open_deals += 1

                    deal_details.append({
                        "id": deal_id,
                        "title": deal.get("title", ""),
                        "org": deal.get("org_name") or "",
                        "status": status,
                        "value": deal.get("value") or 0,
                    })
            except Exception:
                pass

        total_closed = wins + losses
        win_rate = round((wins / total_closed * 100), 1) if total_closed > 0 else 0

        return {
            "wins": wins,
            "losses": losses,
            "open": open_deals,
            "win_rate": win_rate,
            "total_closed": total_closed,
            "deals": deal_details,
        }

    def _generate_ollama_messaging(self, profile, win_loss):
        prompt = (
            f"You are a sales strategist. Write 3 punchy counter-positioning statements against "
            f"{profile['name']} for our product Echo Pulse (employee engagement surveys for Czech market). "
            f"Our win rate against them: {win_loss['win_rate']:.0f}% "
            f"({win_loss['wins']}W/{win_loss['losses']}L). "
            f"Their weaknesses: {', '.join(profile.get('weaknesses', [])[:3])}. "
            f"Keep each statement under 20 words. Be direct and competitive.\n\n"
            f"Write 3 statements, one per line:"
        )
        result = _ollama_generate(prompt, max_tokens=200, temperature=0.4)
        if result:
            lines = [line.strip().lstrip("0123456789.-) ") for line in result.split("\n") if line.strip()]
            return lines[:3]
        return None

    def generate(self, comp_key):
        """Generate a complete battle card for a competitor."""
        profile = CompetitorProfile.COMPETITORS.get(comp_key)
        if not profile:
            cilog(f"Unknown competitor: {comp_key}", "WARN")
            return None

        cilog(f"Generating battle card for {profile['name']}...")

        win_loss = self._get_win_loss_record(comp_key)

        intel = self._load_intel()
        comp_summary = intel.get("by_competitor", {}).get(comp_key, {})

        # Get Ollama-generated counter-messaging or use pre-loaded
        ai_messaging = self._generate_ollama_messaging(profile, win_loss)
        counter_messages = ai_messaging or profile.get("counter_messaging", [])

        # Build battle card markdown
        card = []
        card.append(f"# Battle Card: {profile['name']}")
        card.append(f"*Generated: {TODAY.isoformat()}*\n")

        # Overview
        card.append("## Overview & Positioning")
        card.append(f"- **Category:** {profile['category']}")
        card.append(f"- **Parent:** {profile.get('parent_company', 'Independent')}")
        card.append(f"- **Target Market:** {profile['target_market']}")
        card.append(f"- **Pricing:** {profile['pricing_model']}")
        card.append("")

        # Win/Loss Record
        card.append("## Win/Loss Record")
        if win_loss["total_closed"] > 0:
            card.append(f"- **Win Rate:** {win_loss['win_rate']:.1f}%")
            card.append(f"- **Wins:** {win_loss['wins']} | **Losses:** {win_loss['losses']} | **Open:** {win_loss['open']}")
            if win_loss["deals"]:
                card.append("")
                card.append("| Deal | Org | Status | Value |")
                card.append("|------|-----|--------|-------|")
                for d in win_loss["deals"]:
                    status_marker = "WON" if d["status"] == "won" else "LOST" if d["status"] == "lost" else "OPEN"
                    card.append(f"| {d['title'][:30]} | {d['org'][:20]} | {status_marker} | {d['value']:,.0f} |")
        else:
            card.append("- No head-to-head deals recorded yet")
        card.append("")

        # Key Differentiators
        card.append("## Key Differentiators (Echo Pulse vs Them)")
        card.append("")
        card.append("| Area | Echo Pulse | " + profile['name'] + " |")
        card.append("|------|------------|" + "-" * (len(profile['name']) + 2) + "|")
        card.append(f"| Market Focus | Czech/CEE specialists | {profile['target_market']} |")
        card.append(f"| Pricing | Flexible, SMB-friendly | {profile['pricing_model'][:40]} |")
        card.append(f"| Setup Time | Days, not months | {'Complex' if 'enterprise' in profile['target_market'].lower() else 'Moderate'} |")
        card.append(f"| Language | Czech-native | {'Multi-language' if 'language' in str(profile.get('key_features', [])).lower() else 'English-primary'} |")
        card.append(f"| Support | Local, hands-on | {'Global enterprise' if 'enterprise' in profile['category'].lower() else 'Standard'} |")
        card.append("")

        # Their Strengths (know your enemy)
        card.append("## Their Strengths (Know Your Enemy)")
        for s in profile.get("strengths", []):
            card.append(f"- {s}")
        card.append("")

        # Their Weaknesses (exploit these)
        card.append("## Their Weaknesses (Exploit These)")
        for w in profile.get("weaknesses", []):
            card.append(f"- {w}")
        card.append("")

        # Common Objections & Responses
        card.append("## Common Objections & Responses")
        card.append("")
        objections = profile.get("typical_objections", [])
        responses = profile.get("counter_messaging", [])
        for i, obj in enumerate(objections):
            card.append(f"**Objection:** \"{obj}\"")
            if i < len(responses):
                card.append(f"**Response:** {responses[i]}")
            card.append("")

        # AI-Generated Counter-Messaging
        if ai_messaging:
            card.append("## AI-Generated Counter-Positioning")
            for msg in ai_messaging:
                card.append(f"- {msg}")
            card.append("")

        # Pricing Comparison
        card.append("## Pricing Comparison")
        card.append(f"- **Them:** {profile['pricing_model']}")
        card.append("- **Echo Pulse:** Custom pricing, typically 30-50% less for Czech market")
        card.append("- **Key Lever:** Local implementation + no enterprise overhead = lower TCO")
        card.append("")

        # Mention History
        if comp_summary:
            card.append("## Pipeline Intelligence")
            card.append(f"- **Total mentions:** {comp_summary.get('total_mentions', 0)}")
            card.append(f"- **In deal notes:** {comp_summary.get('note_mentions', 0)}")
            card.append(f"- **In loss reasons:** {comp_summary.get('loss_mentions', 0)}")
            card.append(f"- **Recent (90d):** {comp_summary.get('recent_90d_mentions', 0)}")
            card.append(f"- **Total lost value to them:** {comp_summary.get('total_lost_value', 0):,.0f} CZK")
            ctx = comp_summary.get("context_breakdown", {})
            if ctx:
                card.append(f"- **Context:** {', '.join(f'{k}: {v}' for k, v in ctx.items())}")
        card.append("")

        card.append("---")
        card.append(f"*Auto-generated by Clawdia Competitive Intel | {NOW.isoformat()}*")

        # Save
        BATTLECARD_DIR.mkdir(parents=True, exist_ok=True)
        out_file = BATTLECARD_DIR / f"{comp_key}.md"
        out_file.write_text("\n".join(card))
        cilog(f"Battle card saved: {out_file}")
        _slog(f"Battle card generated for {profile['name']}", meta={"file": str(out_file)})

        return {
            "competitor": comp_key,
            "name": profile["name"],
            "file": str(out_file),
            "win_loss": win_loss,
            "card_content": "\n".join(card),
        }


# ── COMPETITIVE INTEL DASHBOARD ────────────────────────

class CompetitiveIntelDashboard:
    """Aggregate competitive intelligence into actionable overview."""

    def __init__(self, base_url, api_token):
        self.base = base_url
        self.token = api_token
        self._intel_data = None

    def _load_intel(self):
        if self._intel_data is not None:
            return self._intel_data
        if INTEL_DATA_FILE.exists():
            try:
                self._intel_data = json.loads(INTEL_DATA_FILE.read_text())
                return self._intel_data
            except (json.JSONDecodeError, OSError):
                pass
        self._intel_data = {}
        return self._intel_data

    def win_rate_by_competitor(self):
        """Win rate when competing against each competitor."""
        intel = self._load_intel()
        mentions = intel.get("mentions", [])

        deal_competitors = defaultdict(set)
        for m in mentions:
            if m.get("deal_id"):
                deal_competitors[m["deal_id"]].add(m["competitor"])

        if not deal_competitors:
            return {}

        comp_records = defaultdict(lambda: {"wins": 0, "losses": 0, "open": 0})
        deal_ids = list(deal_competitors.keys())

        for deal_id in deal_ids:
            try:
                resp = api_request(self.base, self.token, "GET", f"/api/v1/deals/{deal_id}")
                if resp and resp.get("success") and resp.get("data"):
                    status = resp["data"].get("status", "")
                    for comp in deal_competitors[deal_id]:
                        if status == "won":
                            comp_records[comp]["wins"] += 1
                        elif status == "lost":
                            comp_records[comp]["losses"] += 1
                        elif status == "open":
                            comp_records[comp]["open"] += 1
            except Exception:
                pass

        results = {}
        for comp, record in comp_records.items():
            total = record["wins"] + record["losses"]
            results[comp] = {
                "competitor": comp,
                "name": CompetitorProfile.COMPETITORS.get(comp, {}).get("name", comp),
                "wins": record["wins"],
                "losses": record["losses"],
                "open": record["open"],
                "win_rate": round(record["wins"] / total * 100, 1) if total > 0 else 0,
                "total_closed": total,
            }

        return results

    def most_mentioned_competitors(self):
        """Rank competitors by total mentions."""
        intel = self._load_intel()
        by_comp = intel.get("by_competitor", {})

        ranked = sorted(by_comp.values(), key=lambda c: c.get("total_mentions", 0), reverse=True)
        return ranked

    def competitive_trends(self):
        """Trend analysis: gaining/losing against each competitor over time."""
        intel = self._load_intel()
        mentions = intel.get("mentions", [])

        if not mentions:
            return {"status": "no_data"}

        comp_timeline = defaultdict(lambda: defaultdict(int))
        for m in mentions:
            d = m.get("date") or m.get("lost_time", "")
            if d:
                month = d[:7]
                comp_timeline[m["competitor"]][month] += 1

        trends = {}
        for comp, monthly in comp_timeline.items():
            months = sorted(monthly.keys())
            if len(months) < 2:
                trends[comp] = {
                    "competitor": comp,
                    "name": CompetitorProfile.COMPETITORS.get(comp, {}).get("name", comp),
                    "direction": "insufficient_data",
                    "months_tracked": len(months),
                }
                continue

            midpoint = len(months) // 2
            old_months = months[:midpoint]
            new_months = months[midpoint:]

            old_avg = statistics.mean([monthly[m] for m in old_months]) if old_months else 0
            new_avg = statistics.mean([monthly[m] for m in new_months]) if new_months else 0

            if old_avg > 0:
                change_pct = ((new_avg - old_avg) / old_avg) * 100
            else:
                change_pct = 100 if new_avg > 0 else 0

            # More mentions = more competitive pressure = we're "losing ground"
            if change_pct > 25:
                direction = "increasing_threat"
            elif change_pct < -25:
                direction = "decreasing_threat"
            else:
                direction = "stable"

            trends[comp] = {
                "competitor": comp,
                "name": CompetitorProfile.COMPETITORS.get(comp, {}).get("name", comp),
                "direction": direction,
                "old_avg_monthly": round(old_avg, 1),
                "new_avg_monthly": round(new_avg, 1),
                "change_pct": round(change_pct, 1),
                "months_tracked": len(months),
                "total_mentions": sum(monthly.values()),
            }

        return trends

    def feature_gap_analysis(self):
        """Identify feature gaps mentioned in competitor contexts."""
        intel = self._load_intel()
        mentions = intel.get("mentions", [])

        feature_mentions = [m for m in mentions if "feature_gap" in m.get("context", [])]

        gaps_by_competitor = defaultdict(list)
        for m in feature_mentions:
            snippet = m.get("snippet") or m.get("reason", "")
            gaps_by_competitor[m["competitor"]].append({
                "snippet": snippet[:200],
                "deal_id": m.get("deal_id"),
                "date": m.get("date") or m.get("lost_time", ""),
            })

        # Try Ollama to extract specific feature gaps
        all_gap_text = " | ".join(
            m.get("snippet") or m.get("reason", "")
            for m in feature_mentions
        )[:2000]

        extracted_gaps = []
        if all_gap_text:
            prompt = (
                "Extract specific product feature gaps mentioned in these deal notes. "
                "Return as a numbered list of specific missing features or capabilities. "
                "Be concise — one line per gap.\n\n"
                f"Notes: {all_gap_text}"
            )
            result = _ollama_generate(prompt, max_tokens=300)
            if result:
                extracted_gaps = [line.strip().lstrip("0123456789.-) ")
                                  for line in result.split("\n")
                                  if line.strip() and not line.strip().startswith("Note")]

        return {
            "feature_gap_mentions": len(feature_mentions),
            "by_competitor": {k: len(v) for k, v in gaps_by_competitor.items()},
            "gap_details": dict(gaps_by_competitor),
            "extracted_gaps": extracted_gaps,
        }

    def full_dashboard(self):
        """Generate complete competitive dashboard."""
        _slog("Generating competitive intel dashboard")

        win_rates = self.win_rate_by_competitor()
        most_mentioned = self.most_mentioned_competitors()
        trends = self.competitive_trends()
        gaps = self.feature_gap_analysis()

        dashboard = {
            "win_rate_by_competitor": win_rates,
            "most_mentioned": most_mentioned,
            "trends": trends,
            "feature_gaps": gaps,
            "generated_at": NOW.isoformat(),
        }

        return dashboard


# ── CLI DISPLAY ────────────────────────────────────────

def _display_scan(result):
    print("=" * 72)
    print("  COMPETITOR MENTION SCAN RESULTS")
    print(f"  Scan date: {result.get('scan_date', '?')}")
    print("=" * 72)

    print(f"\n  Total mentions found: {result.get('total_mentions', 0)}")

    by_comp = result.get("by_competitor", {})
    if by_comp:
        print(f"\n  BY COMPETITOR")
        print("  " + "-" * 68)
        print(f"  {'Competitor':<25} {'Total':>6} {'Notes':>6} {'Losses':>7} {'Recent':>7} {'Lost Value':>12}")
        print("  " + "-" * 68)

        sorted_comps = sorted(by_comp.values(), key=lambda c: c.get("total_mentions", 0), reverse=True)
        for c in sorted_comps:
            print(f"  {c['name'][:24]:<25} {c['total_mentions']:>6} {c['note_mentions']:>6} "
                  f"{c['loss_mentions']:>7} {c['recent_90d_mentions']:>7} {c['total_lost_value']:>11,.0f}")

    mentions = result.get("mentions", [])
    if mentions:
        print(f"\n  RECENT MENTIONS (last 10)")
        print("  " + "-" * 68)
        for m in mentions[:10]:
            source = "NOTE" if m["source"] == "note" else "LOSS"
            date_str = m.get("date") or m.get("lost_time", "?")
            ctx = ",".join(m.get("context", []))
            snippet = (m.get("snippet") or m.get("reason", ""))[:50]
            print(f"  [{source}] {date_str} | {m['competitor_name'][:18]:<18} | {ctx[:20]:<20} | {snippet}")

    print(f"\n  Data saved to: {INTEL_DATA_FILE}")
    print("=" * 72)


def _display_profile(comp_key):
    profile = CompetitorProfile.COMPETITORS.get(comp_key)
    if not profile:
        print(f"  Unknown competitor: {comp_key}")
        print(f"  Available: {', '.join(CompetitorProfile.all_keys())}")
        return

    print("=" * 72)
    print(f"  COMPETITOR PROFILE: {profile['name']}")
    print("=" * 72)

    print(f"\n  Category:     {profile['category']}")
    print(f"  Parent:       {profile.get('parent_company', 'Independent')}")
    print(f"  Target:       {profile['target_market']}")
    print(f"  Pricing:      {profile['pricing_model']}")

    print(f"\n  KEY FEATURES")
    print("  " + "-" * 68)
    for f in profile.get("key_features", []):
        print(f"  - {f}")

    print(f"\n  STRENGTHS")
    print("  " + "-" * 68)
    for s in profile.get("strengths", []):
        print(f"  + {s}")

    print(f"\n  WEAKNESSES")
    print("  " + "-" * 68)
    for w in profile.get("weaknesses", []):
        print(f"  - {w}")

    print(f"\n  TYPICAL OBJECTIONS")
    print("  " + "-" * 68)
    for i, obj in enumerate(profile.get("typical_objections", []), 1):
        print(f"  {i}. \"{obj}\"")
        counters = profile.get("counter_messaging", [])
        if i - 1 < len(counters):
            print(f"     -> {counters[i - 1]}")

    print("=" * 72)


def _display_battlecard(result):
    if not result:
        return
    print(result["card_content"])
    print(f"\n  Saved to: {result['file']}")


def _display_dashboard(dashboard):
    print("=" * 72)
    print("  COMPETITIVE INTELLIGENCE DASHBOARD")
    print(f"  Generated: {dashboard.get('generated_at', '?')[:10]}")
    print("=" * 72)

    # Win rate by competitor
    win_rates = dashboard.get("win_rate_by_competitor", {})
    if win_rates:
        print(f"\n  WIN RATE BY COMPETITOR")
        print("  " + "-" * 68)
        print(f"  {'Competitor':<25} {'Win Rate':>9} {'W':>4} {'L':>4} {'Open':>5}")
        print("  " + "-" * 68)
        for comp in sorted(win_rates.values(), key=lambda c: -c.get("win_rate", 0)):
            bar_len = int(comp["win_rate"] / 10)
            bar = "#" * bar_len + "-" * (10 - bar_len)
            print(f"  {comp['name'][:24]:<25} [{bar}] {comp['win_rate']:>5.1f}% "
                  f"{comp['wins']:>4} {comp['losses']:>4} {comp['open']:>5}")
    else:
        print("\n  No win/loss data against competitors yet. Run 'scan' first.")

    # Most mentioned
    most_mentioned = dashboard.get("most_mentioned", [])
    if most_mentioned:
        print(f"\n  MOST MENTIONED COMPETITORS")
        print("  " + "-" * 68)
        for i, c in enumerate(most_mentioned[:8], 1):
            bar = "#" * min(c.get("total_mentions", 0), 30)
            print(f"  {i}. {c['name'][:22]:<22} {bar} ({c['total_mentions']})")

    # Feature gaps
    gaps = dashboard.get("feature_gaps", {})
    extracted = gaps.get("extracted_gaps", [])
    if extracted:
        print(f"\n  FEATURE GAPS IDENTIFIED")
        print("  " + "-" * 68)
        for gap in extracted[:8]:
            print(f"  - {gap}")

    gap_by_comp = gaps.get("by_competitor", {})
    if gap_by_comp:
        print(f"\n  Feature gap mentions by competitor:")
        for comp, count in sorted(gap_by_comp.items(), key=lambda x: -x[1]):
            name = CompetitorProfile.COMPETITORS.get(comp, {}).get("name", comp)
            print(f"    {name}: {count}")

    print("=" * 72)


def _display_trends(trends):
    print("=" * 72)
    print("  COMPETITIVE TRENDS")
    print("=" * 72)

    if isinstance(trends, dict) and trends.get("status") == "no_data":
        print("\n  No competitive data available. Run 'scan' first.")
        print("=" * 72)
        return

    if not trends:
        print("\n  No trend data available.")
        print("=" * 72)
        return

    increasing = []
    decreasing = []
    stable = []
    insufficient = []

    for comp, data in trends.items():
        direction = data.get("direction", "")
        if direction == "increasing_threat":
            increasing.append(data)
        elif direction == "decreasing_threat":
            decreasing.append(data)
        elif direction == "stable":
            stable.append(data)
        else:
            insufficient.append(data)

    if increasing:
        print(f"\n  INCREASING THREATS (more mentions recently)")
        print("  " + "-" * 68)
        for t in sorted(increasing, key=lambda x: -x.get("change_pct", 0)):
            print(f"  ! {t['name'][:24]:<25} {t['old_avg_monthly']:.1f} -> {t['new_avg_monthly']:.1f}/mo "
                  f"({t['change_pct']:+.1f}%) | {t['total_mentions']} total mentions")

    if decreasing:
        print(f"\n  DECREASING THREATS (fewer mentions recently)")
        print("  " + "-" * 68)
        for t in sorted(decreasing, key=lambda x: x.get("change_pct", 0)):
            print(f"  v {t['name'][:24]:<25} {t['old_avg_monthly']:.1f} -> {t['new_avg_monthly']:.1f}/mo "
                  f"({t['change_pct']:+.1f}%) | {t['total_mentions']} total mentions")

    if stable:
        print(f"\n  STABLE")
        print("  " + "-" * 68)
        for t in stable:
            print(f"  = {t['name'][:24]:<25} ~{t['new_avg_monthly']:.1f}/mo | {t['total_mentions']} total mentions")

    if insufficient:
        print(f"\n  INSUFFICIENT DATA")
        print("  " + "-" * 68)
        for t in insufficient:
            print(f"  ? {t['name'][:24]:<25} {t.get('months_tracked', 0)} months tracked")

    print("=" * 72)


# ── CLI ────────────────────────────────────────────────

def main():
    env = load_env(ENV_PATH)
    base = env.get("PIPEDRIVE_BASE_URL", "").rstrip("/")
    token = env.get("PIPEDRIVE_API_TOKEN", "")

    if not base or not token:
        print("ERROR: Missing PIPEDRIVE_BASE_URL or PIPEDRIVE_API_TOKEN in .secrets/pipedrive.env")
        sys.exit(1)

    if len(sys.argv) < 2:
        print("Usage: competitive_intel.py [scan|profile|battlecard|dashboard|trends]")
        print("  scan                  — scan all deals for competitor mentions")
        print("  profile <competitor>  — show competitor profile")
        print("  battlecard <competitor> — generate battle card")
        print("  dashboard             — competitive overview")
        print("  trends                — competitive trends over time")
        print(f"\n  Available competitors: {', '.join(CompetitorProfile.all_keys())}")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "scan":
        print("Scanning Pipedrive deals for competitor mentions...\n")
        extractor = CompetitorMentionExtractor(base, token)
        result = extractor.full_scan()
        _display_scan(result)

    elif cmd == "profile":
        if len(sys.argv) < 3:
            print("Usage: competitive_intel.py profile <competitor>")
            print(f"Available: {', '.join(CompetitorProfile.all_keys())}")
            sys.exit(1)
        comp_input = " ".join(sys.argv[2:]).lower().strip()
        comp_key = CompetitorProfile.COMPETITOR_ALIASES.get(comp_input, comp_input.replace(" ", "_"))
        _display_profile(comp_key)

    elif cmd == "battlecard":
        if len(sys.argv) < 3:
            print("Usage: competitive_intel.py battlecard <competitor>")
            print(f"Available: {', '.join(CompetitorProfile.all_keys())}")
            sys.exit(1)
        comp_input = " ".join(sys.argv[2:]).lower().strip()
        comp_key = CompetitorProfile.COMPETITOR_ALIASES.get(comp_input, comp_input.replace(" ", "_"))
        if comp_key not in CompetitorProfile.COMPETITORS:
            print(f"Unknown competitor: {comp_input}")
            print(f"Available: {', '.join(CompetitorProfile.all_keys())}")
            sys.exit(1)
        print(f"Generating battle card for {CompetitorProfile.COMPETITORS[comp_key]['name']}...\n")
        generator = BattleCardGenerator(base, token)
        result = generator.generate(comp_key)
        if result:
            _display_battlecard(result)
        else:
            print("Failed to generate battle card.")

    elif cmd == "dashboard":
        print("Building competitive intelligence dashboard...\n")
        dash = CompetitiveIntelDashboard(base, token)
        dashboard = dash.full_dashboard()
        _display_dashboard(dashboard)

    elif cmd == "trends":
        print("Analyzing competitive trends...\n")
        dash = CompetitiveIntelDashboard(base, token)
        trends = dash.competitive_trends()
        _display_trends(trends)

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: competitive_intel.py [scan|profile|battlecard|dashboard|trends]")
        sys.exit(1)


if __name__ == "__main__":
    main()
