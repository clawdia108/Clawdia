#!/usr/bin/env python3
"""
Multi-Step Email Sequence Engine
=================================
Automated follow-up sequences per deal. Defines multi-touch cadences,
tracks active sequences, advances based on timing, generates personalized
drafts, and provides A/B testing + analytics.

Integrates with:
  - email_personalizer.py (SPIN templates, personalization)
  - draft_generator.py (Ollama draft generation)
  - deal_velocity.py (deal/stage context)
  - Pipedrive API (deal status, contact info)

Usage:
  python3 scripts/email_sequences.py start <deal_id> <sequence_name>
  python3 scripts/email_sequences.py advance
  python3 scripts/email_sequences.py status
  python3 scripts/email_sequences.py pause <deal_id>
  python3 scripts/email_sequences.py resume <deal_id>
  python3 scripts/email_sequences.py skip <deal_id>
  python3 scripts/email_sequences.py stats
"""

import json
import random
import subprocess
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
SEQUENCES_DIR = WORKSPACE / "sequences" / "active"
STATS_FILE = WORKSPACE / "sequences" / "stats.json"
LOG_FILE = WORKSPACE / "logs" / "email-sequences.log"
ENV_PATH = WORKSPACE / ".secrets" / "pipedrive.env"
DRAFTS_DIR = WORKSPACE / "drafts" / "sequences"

TODAY = date.today()
NOW = datetime.now()


# ── LOGGING ───────────────────────────────────────────

def slog(msg, level="INFO"):
    ts = NOW.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
    try:
        if LOG_FILE.stat().st_size > 200_000:
            lines = LOG_FILE.read_text().splitlines()
            LOG_FILE.write_text("\n".join(lines[-500:]) + "\n")
    except OSError:
        pass


# ── ENV & API ─────────────────────────────────────────

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


def pipedrive_get(path, params=None):
    env = load_env()
    token = env.get("PIPEDRIVE_API_TOKEN", "")
    base = env.get("PIPEDRIVE_BASE_URL", "https://api.pipedrive.com/v1").rstrip("/")
    if not token:
        return None
    url = f"{base}{path}?api_token={token}"
    if params:
        for k, v in params.items():
            url += f"&{k}={v}"
    try:
        r = subprocess.run(
            ["curl", "-s", "-m", "15", url],
            capture_output=True, text=True, timeout=20,
        )
        if r.returncode == 0:
            data = json.loads(r.stdout)
            if data.get("success"):
                return data.get("data")
    except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def get_deal_context(deal_id):
    deal = pipedrive_get(f"/deals/{deal_id}")
    if not deal:
        return None

    person = deal.get("person_id", {})
    org = deal.get("org_id", {})

    ctx = {
        "deal_id": str(deal_id),
        "title": deal.get("title", ""),
        "value": deal.get("value", 0),
        "currency": deal.get("currency", "CZK"),
        "stage_id": deal.get("stage_id"),
        "status": deal.get("status", "open"),
        "company": org.get("name", "") if isinstance(org, dict) else "",
        "contact_name": person.get("name", "") if isinstance(person, dict) else "",
        "contact_email": "",
        "add_time": deal.get("add_time", ""),
        "update_time": deal.get("update_time", ""),
    }

    if isinstance(person, dict) and person.get("value"):
        pid = person["value"] if isinstance(person["value"], int) else person.get("value")
        if pid:
            pdata = pipedrive_get(f"/persons/{pid}")
            if pdata:
                emails = pdata.get("email", [])
                if emails and isinstance(emails, list):
                    ctx["contact_email"] = emails[0].get("value", "")

    return ctx


# ── OLLAMA PERSONALIZATION ────────────────────────────

def ollama_generate(prompt, max_tokens=300, timeout=30):
    try:
        payload = json.dumps({
            "model": "llama3.1:8b",
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0.7},
        })
        result = subprocess.run(
            ["curl", "-s", "-m", str(timeout),
             "http://localhost:11434/api/generate", "-d", payload],
            capture_output=True, text=True, timeout=timeout + 5,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data.get("response", "").strip()
    except (json.JSONDecodeError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def personalize_body(template_body, context, step_name):
    company = context.get("company", "[Company]")
    contact = context.get("contact_name", "")
    first_name = contact.split()[0] if contact else ""

    prompt = f"""Write a personalized opening line in Czech for a business email.
Context: Writing to {contact} at {company}. Step: {step_name}.
One sentence, natural, not salesy. Czech language.

Opening line:"""

    opening = ollama_generate(prompt, max_tokens=80)
    if not opening:
        opening = f"Dobry den {first_name}," if first_name else "Dobry den,"
    else:
        opening = opening.split("\n")[0].strip().strip('"')

    replacements = {
        "{{company}}": company,
        "{{contact_name}}": contact,
        "{{first_name}}": first_name,
        "{{opening_line}}": opening,
        "{{value}}": f"{context.get('value', 0):,.0f} {context.get('currency', 'CZK')}",
    }

    body = template_body
    for key, val in replacements.items():
        body = body.replace(key, str(val))

    return body


# ── SEQUENCE DEFINITIONS ─────────────────────────────

class SequenceDefinition:
    """Define multi-step email sequences with timing and conditions."""

    BUILT_IN = {
        "prospecting_5touch": {
            "name": "prospecting_5touch",
            "label": "5-Touch Prospecting",
            "description": "Cold outreach with 5 escalating touches",
            "steps": [
                {
                    "step": 1,
                    "name": "intro",
                    "delay_days": 0,
                    "subject": "{{company}} + Behavera — employee engagement",
                    "subject_b": "{{first_name}}, quick question about {{company}}",
                    "body": """{{opening_line}}

Jsem Josef z Behavera. Pomahame firmam jako {{company}} merit a zlepsovat employee engagement pomoci AI.

Zajimalo by me, jak aktualne merite spokojenost zamestnancu u vas?

Mel byste 15 minut na kratky call pristi tyden?

S pozdravem,
Josef""",
                    "condition": "deal_open",
                },
                {
                    "step": 2,
                    "name": "value_prop",
                    "delay_days": 3,
                    "subject": "Re: {{company}} — 3 duvody proc Echo Pulse",
                    "subject_b": "Re: {{company}} — data o engagementu",
                    "body": """{{opening_line}}

Navazuji na svuj predchozi email. Tady jsou 3 veci, ktere Echo Pulse resi:

1. Real-time prehled o naladezmestnancu (ne rocni pruzkum)
2. Predikce fluktuace — vite kdo odejde driv nez da vypoved
3. AI doporuceni pro manazery — konkretni kroky, ne obecne rady

Firmy nasi velikosti typicky usetri 15-25% na nakladech spojeny s fluktuaci.

Stoji to za 15 minut?

Josef""",
                    "condition": "no_reply",
                },
                {
                    "step": 3,
                    "name": "case_study",
                    "delay_days": 7,
                    "subject": "{{company}} — jak tech firma snizila fluktuaci o 30%",
                    "subject_b": "Case study: od 25% fluktuace na 12%",
                    "body": """{{opening_line}}

Sdilim kratkou case study — tech firma (200 zamestnancu) pouziva Echo Pulse 6 mesicu:

- Fluktuace klesla z 25% na 12%
- Manager engagement score +40%
- ROI: 3.2x za prvni rok

Muzu vam ukazat, jak by to vypadalo pro {{company}}?

Josef""",
                    "condition": "no_reply",
                },
                {
                    "step": 4,
                    "name": "last_chance",
                    "delay_days": 14,
                    "subject": "{{first_name}} — posledni vec k {{company}}",
                    "subject_b": "Posledni otazka ohledne engagementu v {{company}}",
                    "body": """{{opening_line}}

Nechci obtezovat, ale rad bych vedel — je employee engagement tema, ktere aktualne resite?

Pokud ano, mohu nabidnout:
- 30-minutove demo bez zavazku
- Benchmark vaseho odvetvi zdarma
- Trial na 14 dni

Pokud ne, zadny problem — dam vedet az bude neco noveho.

Josef""",
                    "condition": "no_reply",
                },
                {
                    "step": 5,
                    "name": "breakup",
                    "delay_days": 21,
                    "subject": "Loucim se (prozatim) — {{company}}",
                    "subject_b": "{{first_name}}, tohle je muj posledni email",
                    "body": """{{opening_line}}

Nechci zaplnovat schranku, takze tohle je muj posledni email na toto tema.

Pokud se v budoucnu bude employee engagement resit, jsem tady:
- josef@behavera.com
- behavera.com/demo

Preji hodne uspechu s {{company}}.

Josef

PS: Odpovezte jednim slovem "pozdeji" a ozvu se za 3 mesice.""",
                    "condition": "no_reply",
                },
            ],
        },
        "demo_followup": {
            "name": "demo_followup",
            "label": "Post-Demo Follow-Up",
            "description": "After demo — resources, check-in, escalate",
            "steps": [
                {
                    "step": 1,
                    "name": "thank_you",
                    "delay_days": 0,
                    "subject": "Diky za demo — {{company}} x Behavera",
                    "subject_b": "{{first_name}}, shrnuti z dnesniho dema",
                    "body": """{{opening_line}}

Diky za vas cas na dnesnim demu. Tady je shrnuti klicovych bodu:

- Echo Pulse dashboard: real-time engagement metriky
- AI predikce: identifikace at-risk zamestnancu
- Manager coaching: automaticka doporuceni

Dalsi kroky:
1. Poslu detailni nabidku do ponde
2. Pokud mate otazky, jsem k dispozici
3. Trial muzeme spustit ihned

Josef""",
                    "condition": "deal_open",
                },
                {
                    "step": 2,
                    "name": "resources",
                    "delay_days": 2,
                    "subject": "Re: {{company}} — materialy k Echo Pulse",
                    "subject_b": "Re: {{company}} — ROI kalkulator",
                    "body": """{{opening_line}}

Posilam materialy, ktere jsme zminovali na demu:

- Product overview (PDF)
- ROI kalkulator pro {{company}} (odhad: {{value}} usetrenych rocne)
- Referencni zakaznici v vasem odvetvi

Mate nejake otazky po demu?

Josef""",
                    "condition": "no_reply",
                },
                {
                    "step": 3,
                    "name": "check_in",
                    "delay_days": 5,
                    "subject": "{{first_name}} — jak to vyzerá s Echo Pulse?",
                    "subject_b": "Quick check-in: {{company}} x Behavera",
                    "body": """{{opening_line}}

Chtel jsem se zeptat, jestli jste mel moznost projit materialy, ktere jsem poslal.

Pokud mate nejake otazky nebo obavy, rad je projdu — at uz na callu nebo emailem.

Jaky je vas idealni timing pro rozhodnuti?

Josef""",
                    "condition": "no_reply",
                },
                {
                    "step": 4,
                    "name": "escalate",
                    "delay_days": 10,
                    "subject": "{{company}} — dalsi kroky?",
                    "subject_b": "{{first_name}} — je neco co brani rozhodnuti?",
                    "body": """{{opening_line}}

Vratim se k nasemu demu. Chapu, ze rozhodovani muze chvili trvat.

Je neco, co brani posunu vpred? Treba:
- Potrebujete souhlas dalsiho cloveka? (Rad se pripojim na call)
- Cenove otazky? (Mame flexibilni modely)
- Technicke obavy? (Nabizime POC zdarma)

Dejte vedet, jak muzu pomoct.

Josef""",
                    "condition": "no_reply",
                },
            ],
        },
        "proposal_followup": {
            "name": "proposal_followup",
            "label": "Proposal Follow-Up",
            "description": "After sending proposal — nudge toward decision",
            "steps": [
                {
                    "step": 1,
                    "name": "sent_notice",
                    "delay_days": 0,
                    "subject": "Nabidka: Behavera Echo Pulse pro {{company}}",
                    "subject_b": "{{company}} — vase nabidka je pripravena",
                    "body": """{{opening_line}}

V priloze posilam nabidku pro {{company}} — Echo Pulse implementace.

Klicove body:
- Cena: {{value}} / rok
- Implementace: 2 tydny
- Zahrnuje: onboarding, training, support

Nabidka je platna 30 dni. Pokud mate otazky, jsem k dispozici.

Josef""",
                    "condition": "deal_open",
                },
                {
                    "step": 2,
                    "name": "check_in",
                    "delay_days": 3,
                    "subject": "Re: Nabidka {{company}} — otazky?",
                    "subject_b": "{{first_name}} — prosel jste nabidku?",
                    "body": """{{opening_line}}

Chtel jsem se ujistit, ze jste obdrzel nabidku a ze je vsechno jasne.

Pokud je cokoliv, co bych mel upresnit nebo upravit, dejte vedet.

Mam volno zitra a ve ctvrtek na kratky call.

Josef""",
                    "condition": "no_reply",
                },
                {
                    "step": 3,
                    "name": "value_add",
                    "delay_days": 7,
                    "subject": "{{company}} — novy benchmark z vaseho odvetvi",
                    "subject_b": "Data k rozhodnuti: {{company}} engagement benchmark",
                    "body": """{{opening_line}}

K nasi nabidce prikladam benchmark employee engagementu ve vasem odvetvi:

- Prumerny engagement score: 62%
- Top 10% firem: 78%+
- Firmy s Echo Pulse: 74% prumer po 6 mesicich

Kde byste chteli mit {{company}}?

Josef""",
                    "condition": "no_reply",
                },
                {
                    "step": 4,
                    "name": "decision_push",
                    "delay_days": 14,
                    "subject": "{{company}} — platnost nabidky konci",
                    "subject_b": "{{first_name}} — posledni tyden na soucasne podminky",
                    "body": """{{opening_line}}

Pripominam, ze soucasne cenove podminky pro {{company}} plati do konce mesice.

Potom budu muset nabidku aktualizovat na nove sazby (o ~15% vyssi).

Pokud jste pripraveni, muzeme startovat implementaci uz pristi tyden.

Je neco, co muzu jeste udelat pro vase rozhodnuti?

Josef""",
                    "condition": "no_reply",
                },
            ],
        },
        "re_engagement": {
            "name": "re_engagement",
            "label": "Re-Engagement",
            "description": "Win back cold/lost deals with new value",
            "steps": [
                {
                    "step": 1,
                    "name": "new_feature",
                    "delay_days": 0,
                    "subject": "{{first_name}} — novinka v Behavera, ktera by vas mohla zajimat",
                    "subject_b": "{{company}} — novy AI modul pro predikci fluktuace",
                    "body": """{{opening_line}}

Uz je to nejaky cas, co jsme se bavili. Od te doby jsme pridali par veci:

- AI predikce fluktuace (presnost 87%)
- Anonymni pulse surveys (5 minut, kazdy tyden)
- Manager dashboard s konkretnimi doporucenimi

Myslel jsem na {{company}} — tohle by mohlo resit vase potreby.

Meli byste zajem o kratke demo novinek?

Josef""",
                    "condition": "deal_open",
                },
                {
                    "step": 2,
                    "name": "success_story",
                    "delay_days": 7,
                    "subject": "Jak {{company}}-podobna firma usetri 2M CZK rocne",
                    "subject_b": "Case study: AI engagement = -30% fluktuace",
                    "body": """{{opening_line}}

Chtel jsem sdilet vysledky od jednoho z nasich novych klientu:

Firma podobna {{company}} (cca stejny pocet lidi, stejne odvetvi):
- Nasadili Echo Pulse pred 4 mesici
- Fluktuace klesla o 30%
- Uspora na nakladech: cca 2M CZK/rok
- Manager satisfaction +45%

Stalo by za to se na to podivat znovu?

Josef""",
                    "condition": "no_reply",
                },
                {
                    "step": 3,
                    "name": "offer",
                    "delay_days": 14,
                    "subject": "{{company}} — specialni nabidka na restart",
                    "subject_b": "{{first_name}} — exkluzivni podminky pro {{company}}",
                    "body": """{{opening_line}}

Protoze jsme se uz v minulosti bavili, mohu nabidnout {{company}} specialni podminky:

- 20% sleva na prvni rok
- Implementace zdarma (bezne 25k CZK)
- 30-denni trial bez zavazku

Tato nabidka plati do konce mesice.

Zavolame si na 15 minut?

Josef""",
                    "condition": "no_reply",
                },
            ],
        },
    }

    @classmethod
    def get(cls, name):
        return cls.BUILT_IN.get(name)

    @classmethod
    def list_all(cls):
        return list(cls.BUILT_IN.keys())

    @classmethod
    def summary(cls):
        lines = []
        for name, seq in cls.BUILT_IN.items():
            step_count = len(seq["steps"])
            last_day = seq["steps"][-1]["delay_days"]
            lines.append(f"  {name:<25} {seq['label']:<30} {step_count} steps, {last_day} days")
        return "\n".join(lines)


# ── SEQUENCE ENGINE ───────────────────────────────────

class SequenceEngine:
    """Manage active sequences per deal. Track, advance, pause, stop."""

    def __init__(self):
        SEQUENCES_DIR.mkdir(parents=True, exist_ok=True)
        DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

    def _seq_path(self, deal_id):
        return SEQUENCES_DIR / f"{deal_id}.json"

    def _load_seq(self, deal_id):
        path = self._seq_path(deal_id)
        if path.exists():
            try:
                return json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return None

    def _save_seq(self, deal_id, data):
        self._seq_path(deal_id).write_text(
            json.dumps(data, indent=2, ensure_ascii=False)
        )

    def start(self, deal_id, sequence_name):
        definition = SequenceDefinition.get(sequence_name)
        if not definition:
            print(f"Unknown sequence: {sequence_name}")
            print(f"Available: {', '.join(SequenceDefinition.list_all())}")
            return None

        existing = self._load_seq(deal_id)
        if existing and existing.get("status") == "active":
            print(f"Deal {deal_id} already has active sequence: {existing['sequence_name']}")
            print("Pause or stop it first.")
            return None

        context = get_deal_context(deal_id)
        if not context:
            slog(f"Could not load deal {deal_id} — starting with minimal context", "WARN")
            context = {
                "deal_id": str(deal_id),
                "company": "[Unknown]",
                "contact_name": "",
                "contact_email": "",
                "status": "open",
            }

        if context.get("status") in ("won", "lost"):
            print(f"Deal {deal_id} is {context['status']}. Not starting sequence.")
            return None

        ab_variant = random.choice(["a", "b"])

        steps = []
        anchor = TODAY
        for step_def in definition["steps"]:
            due_date = (anchor + timedelta(days=step_def["delay_days"])).isoformat()
            subject = step_def["subject"]
            if ab_variant == "b" and step_def.get("subject_b"):
                subject = step_def["subject_b"]

            steps.append({
                "step": step_def["step"],
                "name": step_def["name"],
                "delay_days": step_def["delay_days"],
                "due_date": due_date,
                "subject": subject,
                "body_template": step_def["body"],
                "condition": step_def.get("condition", "deal_open"),
                "status": "pending",
                "sent_at": None,
                "draft_file": None,
            })

        seq_data = {
            "deal_id": str(deal_id),
            "sequence_name": sequence_name,
            "sequence_label": definition["label"],
            "status": "active",
            "ab_variant": ab_variant,
            "current_step": 1,
            "started_at": NOW.isoformat(),
            "paused_at": None,
            "stopped_at": None,
            "stopped_reason": None,
            "context": {
                "company": context.get("company", ""),
                "contact_name": context.get("contact_name", ""),
                "contact_email": context.get("contact_email", ""),
            },
            "steps": steps,
        }

        self._save_seq(deal_id, seq_data)
        slog(f"Sequence started: deal {deal_id} -> {sequence_name} (variant {ab_variant})")

        tracker = SequenceTracker()
        tracker.record_start(deal_id, sequence_name, ab_variant)

        return seq_data

    def advance_all(self):
        """Advance all active sequences. Generate drafts for due steps."""
        active_files = list(SEQUENCES_DIR.glob("*.json"))
        advanced = []
        stopped = []

        for path in active_files:
            try:
                seq = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            if seq.get("status") != "active":
                continue

            deal_id = seq["deal_id"]

            deal_status = self._check_deal_status(deal_id)
            if deal_status in ("won", "lost"):
                seq["status"] = "stopped"
                seq["stopped_at"] = NOW.isoformat()
                seq["stopped_reason"] = f"Deal moved to {deal_status}"
                self._save_seq(deal_id, seq)
                stopped.append(deal_id)
                slog(f"Sequence stopped: deal {deal_id} — {deal_status}")
                continue

            for step in seq["steps"]:
                if step["status"] != "pending":
                    continue

                if step["due_date"] > TODAY.isoformat():
                    break

                if step["condition"] == "no_reply":
                    if self._detect_reply(deal_id, seq):
                        seq["status"] = "stopped"
                        seq["stopped_at"] = NOW.isoformat()
                        seq["stopped_reason"] = "Reply detected"
                        self._save_seq(deal_id, seq)
                        stopped.append(deal_id)
                        slog(f"Sequence stopped: deal {deal_id} — reply detected")

                        tracker = SequenceTracker()
                        tracker.record_reply(deal_id, seq["sequence_name"], step["step"])
                        break

                draft = self._generate_step_draft(deal_id, step, seq)
                step["status"] = "drafted"
                step["sent_at"] = NOW.isoformat()
                step["draft_file"] = draft["file"] if draft else None
                seq["current_step"] = step["step"] + 1
                advanced.append({"deal_id": deal_id, "step": step["name"]})
                slog(f"Step advanced: deal {deal_id} / step {step['step']} ({step['name']})")

                tracker = SequenceTracker()
                tracker.record_send(deal_id, seq["sequence_name"], step["step"], seq.get("ab_variant", "a"))

                time.sleep(0.5)

            all_done = all(s["status"] != "pending" for s in seq["steps"])
            if all_done and seq["status"] == "active":
                seq["status"] = "completed"
                seq["stopped_at"] = NOW.isoformat()
                seq["stopped_reason"] = "All steps completed"
                slog(f"Sequence completed: deal {deal_id}")

            self._save_seq(deal_id, seq)

        return {"advanced": advanced, "stopped": stopped}

    def pause(self, deal_id):
        seq = self._load_seq(deal_id)
        if not seq:
            print(f"No sequence found for deal {deal_id}")
            return None
        if seq["status"] != "active":
            print(f"Sequence for deal {deal_id} is {seq['status']}, not active")
            return None

        seq["status"] = "paused"
        seq["paused_at"] = NOW.isoformat()
        self._save_seq(deal_id, seq)
        slog(f"Sequence paused: deal {deal_id}")
        return seq

    def resume(self, deal_id):
        seq = self._load_seq(deal_id)
        if not seq:
            print(f"No sequence found for deal {deal_id}")
            return None
        if seq["status"] != "paused":
            print(f"Sequence for deal {deal_id} is {seq['status']}, not paused")
            return None

        pause_date = seq.get("paused_at", "")
        if pause_date:
            try:
                paused_dt = datetime.fromisoformat(pause_date).date()
                paused_days = (TODAY - paused_dt).days
                for step in seq["steps"]:
                    if step["status"] == "pending":
                        old_due = datetime.strptime(step["due_date"], "%Y-%m-%d").date()
                        new_due = old_due + timedelta(days=paused_days)
                        step["due_date"] = new_due.isoformat()
            except (ValueError, TypeError):
                pass

        seq["status"] = "active"
        seq["paused_at"] = None
        self._save_seq(deal_id, seq)
        slog(f"Sequence resumed: deal {deal_id} (dates shifted)")
        return seq

    def skip_deal(self, deal_id):
        seq = self._load_seq(deal_id)
        if not seq:
            print(f"No sequence found for deal {deal_id}")
            return None

        seq["status"] = "skipped"
        seq["stopped_at"] = NOW.isoformat()
        seq["stopped_reason"] = "Manually skipped"
        self._save_seq(deal_id, seq)
        slog(f"Sequence skipped: deal {deal_id}")
        return seq

    def get_all_active(self):
        active = []
        for path in SEQUENCES_DIR.glob("*.json"):
            try:
                seq = json.loads(path.read_text())
                if seq.get("status") in ("active", "paused"):
                    pending = [s for s in seq["steps"] if s["status"] == "pending"]
                    completed = [s for s in seq["steps"] if s["status"] in ("drafted", "completed")]
                    next_step = pending[0] if pending else None
                    active.append({
                        "deal_id": seq["deal_id"],
                        "sequence": seq["sequence_name"],
                        "label": seq.get("sequence_label", ""),
                        "status": seq["status"],
                        "company": seq.get("context", {}).get("company", ""),
                        "contact": seq.get("context", {}).get("contact_name", ""),
                        "variant": seq.get("ab_variant", "?"),
                        "progress": f"{len(completed)}/{len(seq['steps'])}",
                        "next_step": next_step["name"] if next_step else "done",
                        "next_due": next_step["due_date"] if next_step else "-",
                        "started": seq.get("started_at", "")[:10],
                    })
            except (json.JSONDecodeError, OSError):
                continue
        return active

    def _check_deal_status(self, deal_id):
        deal = pipedrive_get(f"/deals/{deal_id}")
        if deal:
            return deal.get("status", "open")
        return "open"

    def _detect_reply(self, deal_id, seq):
        """Check if there's been activity on the deal since sequence started."""
        deal = pipedrive_get(f"/deals/{deal_id}")
        if not deal:
            return False
        last_activity = deal.get("last_activity_date", "")
        if not last_activity:
            return False
        started = seq.get("started_at", "")[:10]
        return last_activity > started

    def _generate_step_draft(self, deal_id, step, seq):
        """Generate a personalized draft for a sequence step."""
        context = get_deal_context(deal_id)
        if not context:
            context = seq.get("context", {})
            context["deal_id"] = deal_id

        body = personalize_body(step["body_template"], context, step["name"])
        subject = step["subject"]
        for key, val in {
            "{{company}}": context.get("company", "[Company]"),
            "{{contact_name}}": context.get("contact_name", ""),
            "{{first_name}}": context.get("contact_name", "").split()[0] if context.get("contact_name") else "",
            "{{value}}": f"{context.get('value', 0):,.0f} {context.get('currency', 'CZK')}",
        }.items():
            subject = subject.replace(key, str(val))

        draft = {
            "deal_id": deal_id,
            "sequence": seq["sequence_name"],
            "step": step["step"],
            "step_name": step["name"],
            "to": context.get("contact_email", ""),
            "subject": subject,
            "body": body,
            "company": context.get("company", ""),
            "contact": context.get("contact_name", ""),
            "ab_variant": seq.get("ab_variant", "a"),
            "generated_at": NOW.isoformat(),
            "status": "draft",
        }

        filename = f"seq_{deal_id}_{seq['sequence_name']}_step{step['step']}_{TODAY.isoformat()}.json"
        draft_path = DRAFTS_DIR / filename
        draft_path.write_text(json.dumps(draft, indent=2, ensure_ascii=False))

        md_path = DRAFTS_DIR / filename.replace(".json", ".md")
        md_content = f"""# Sequence Draft: {draft['subject']}

**To:** {draft['to'] or '[no email]'}
**Sequence:** {seq['sequence_name']} / step {step['step']} ({step['name']})
**Company:** {draft['company']}
**A/B Variant:** {draft['ab_variant']}

---

{draft['body']}

---
*Generated: {NOW.strftime('%Y-%m-%d %H:%M')} | Deal: {deal_id}*
"""
        md_path.write_text(md_content)

        return {"file": filename, "path": str(draft_path)}


# ── SEQUENCE TRACKER (ANALYTICS) ─────────────────────

class SequenceTracker:
    """Track sequence performance: sends, opens (simulated), replies, A/B tests."""

    def __init__(self):
        self.stats = self._load()

    def _load(self):
        if STATS_FILE.exists():
            try:
                return json.loads(STATS_FILE.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {"sequences": {}, "ab_tests": {}, "last_updated": None}

    def _save(self):
        STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.stats["last_updated"] = NOW.isoformat()
        STATS_FILE.write_text(json.dumps(self.stats, indent=2, ensure_ascii=False))

    def _ensure_seq(self, sequence_name):
        if sequence_name not in self.stats["sequences"]:
            self.stats["sequences"][sequence_name] = {
                "started": 0,
                "completed": 0,
                "replied": 0,
                "total_sends": 0,
                "step_sends": {},
                "step_replies": {},
                "deals": [],
            }
        return self.stats["sequences"][sequence_name]

    def record_start(self, deal_id, sequence_name, ab_variant):
        seq_stats = self._ensure_seq(sequence_name)
        seq_stats["started"] += 1
        seq_stats["deals"].append({
            "deal_id": str(deal_id),
            "variant": ab_variant,
            "started_at": NOW.isoformat(),
            "replied": False,
            "reply_step": None,
        })

        ab_key = f"{sequence_name}_{ab_variant}"
        if ab_key not in self.stats["ab_tests"]:
            self.stats["ab_tests"][ab_key] = {
                "sequence": sequence_name,
                "variant": ab_variant,
                "sends": 0,
                "opens": 0,
                "replies": 0,
            }
        self._save()

    def record_send(self, deal_id, sequence_name, step_num, ab_variant):
        seq_stats = self._ensure_seq(sequence_name)
        seq_stats["total_sends"] += 1
        step_key = str(step_num)
        seq_stats["step_sends"][step_key] = seq_stats["step_sends"].get(step_key, 0) + 1

        simulated_open = random.random() < 0.45
        ab_key = f"{sequence_name}_{ab_variant}"
        if ab_key in self.stats["ab_tests"]:
            self.stats["ab_tests"][ab_key]["sends"] += 1
            if simulated_open:
                self.stats["ab_tests"][ab_key]["opens"] += 1

        self._save()

    def record_reply(self, deal_id, sequence_name, step_num):
        seq_stats = self._ensure_seq(sequence_name)
        seq_stats["replied"] += 1
        step_key = str(step_num)
        seq_stats["step_replies"][step_key] = seq_stats["step_replies"].get(step_key, 0) + 1

        for deal in seq_stats["deals"]:
            if deal["deal_id"] == str(deal_id):
                deal["replied"] = True
                deal["reply_step"] = step_num
                ab_key = f"{sequence_name}_{deal.get('variant', 'a')}"
                if ab_key in self.stats["ab_tests"]:
                    self.stats["ab_tests"][ab_key]["replies"] += 1
                break

        self._save()

    def get_performance(self):
        output = {}
        for name, seq in self.stats.get("sequences", {}).items():
            started = seq.get("started", 0)
            replied = seq.get("replied", 0)
            total_sends = seq.get("total_sends", 0)
            reply_rate = round(replied / started * 100, 1) if started > 0 else 0

            best_step = None
            best_step_rate = 0
            for step_key, replies in seq.get("step_replies", {}).items():
                sends = seq.get("step_sends", {}).get(step_key, 0)
                rate = round(replies / sends * 100, 1) if sends > 0 else 0
                if rate > best_step_rate:
                    best_step_rate = rate
                    best_step = step_key

            output[name] = {
                "started": started,
                "replied": replied,
                "reply_rate": reply_rate,
                "total_sends": total_sends,
                "avg_sends_per_deal": round(total_sends / started, 1) if started > 0 else 0,
                "best_step": best_step,
                "best_step_reply_rate": best_step_rate,
            }

        return output

    def get_ab_results(self):
        results = {}
        for key, ab in self.stats.get("ab_tests", {}).items():
            seq_name = ab["sequence"]
            if seq_name not in results:
                results[seq_name] = {}
            variant = ab["variant"]
            sends = ab.get("sends", 0)
            opens = ab.get("opens", 0)
            replies = ab.get("replies", 0)
            results[seq_name][variant] = {
                "sends": sends,
                "open_rate": round(opens / sends * 100, 1) if sends > 0 else 0,
                "reply_rate": round(replies / sends * 100, 1) if sends > 0 else 0,
            }
        return results


# ── CLI ───────────────────────────────────────────────

def render_status(active_seqs):
    lines = []
    lines.append("=" * 75)
    lines.append("  ACTIVE EMAIL SEQUENCES")
    lines.append(f"  {NOW.strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 75)

    if not active_seqs:
        lines.append("\n  No active sequences.")
        lines.append("  Start one: python3 scripts/email_sequences.py start <deal_id> <sequence>")
        lines.append(f"\n  Available sequences:")
        lines.append(SequenceDefinition.summary())
    else:
        lines.append(f"\n  {'Deal':<10} {'Company':<20} {'Sequence':<22} {'Status':<8} {'Progress':<10} {'Next':<15} {'Due':<12}")
        lines.append("  " + "-" * 73)

        for s in active_seqs:
            lines.append(
                f"  {s['deal_id']:<10} {s['company'][:19]:<20} {s['sequence'][:21]:<22} "
                f"{s['status']:<8} {s['progress']:<10} {s['next_step'][:14]:<15} {s['next_due']:<12}"
            )

    lines.append("=" * 75)
    return "\n".join(lines)


def render_stats(perf, ab_results):
    lines = []
    lines.append("=" * 75)
    lines.append("  SEQUENCE PERFORMANCE")
    lines.append(f"  {NOW.strftime('%Y-%m-%d %H:%M')}")
    lines.append("=" * 75)

    if not perf:
        lines.append("\n  No sequence data yet. Start some sequences first.")
    else:
        lines.append(f"\n  {'Sequence':<25} {'Started':>8} {'Replied':>8} {'Rate':>7} {'Sends':>7} {'Best Step':>10}")
        lines.append("  " + "-" * 73)

        for name, p in perf.items():
            best = f"#{p['best_step']}" if p['best_step'] else "-"
            lines.append(
                f"  {name:<25} {p['started']:>8} {p['replied']:>8} "
                f"{p['reply_rate']:>6.1f}% {p['total_sends']:>7} {best:>10}"
            )

    if ab_results:
        lines.append(f"\n  A/B TEST RESULTS")
        lines.append("  " + "-" * 73)
        lines.append(f"  {'Sequence':<25} {'Variant':<10} {'Sends':>7} {'Open Rate':>10} {'Reply Rate':>11}")
        lines.append("  " + "-" * 73)

        for seq_name, variants in ab_results.items():
            for variant, data in sorted(variants.items()):
                lines.append(
                    f"  {seq_name:<25} {variant:<10} {data['sends']:>7} "
                    f"{data['open_rate']:>9.1f}% {data['reply_rate']:>10.1f}%"
                )
            winner = max(variants.items(), key=lambda x: x[1]["reply_rate"])
            lines.append(f"  {'':>25} -> Winner: variant {winner[0]}")
    else:
        lines.append(f"\n  A/B TEST: No data yet")

    lines.append("=" * 75)
    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: email_sequences.py [start|advance|status|pause|resume|skip|stats]")
        print()
        print("Commands:")
        print("  start <deal_id> <sequence>  — Start a sequence for a deal")
        print("  advance                     — Advance all active sequences")
        print("  status                      — Show all active sequences")
        print("  pause <deal_id>             — Pause a deal's sequence")
        print("  resume <deal_id>            — Resume a paused sequence")
        print("  skip <deal_id>              — Skip/stop a deal's sequence")
        print("  stats                       — Show sequence performance")
        print()
        print("Available sequences:")
        print(SequenceDefinition.summary())
        sys.exit(0)

    cmd = sys.argv[1]
    engine = SequenceEngine()

    if cmd == "start":
        if len(sys.argv) < 4:
            print("Usage: email_sequences.py start <deal_id> <sequence_name>")
            print(f"\nAvailable sequences: {', '.join(SequenceDefinition.list_all())}")
            sys.exit(1)

        deal_id = sys.argv[2]
        seq_name = sys.argv[3]
        result = engine.start(deal_id, seq_name)
        if result:
            print(f"\nSequence started: {result['sequence_label']}")
            print(f"  Deal: {deal_id}")
            print(f"  Company: {result['context']['company']}")
            print(f"  Contact: {result['context']['contact_name']}")
            print(f"  A/B variant: {result['ab_variant']}")
            print(f"  Steps: {len(result['steps'])}")
            print()
            for step in result["steps"]:
                print(f"  Step {step['step']}: {step['name']:<15} due {step['due_date']}")

    elif cmd == "advance":
        print("Advancing active sequences...")
        result = engine.advance_all()
        advanced = result["advanced"]
        stopped = result["stopped"]
        if advanced:
            print(f"\nAdvanced {len(advanced)} steps:")
            for a in advanced:
                print(f"  Deal {a['deal_id']} -> {a['step']}")
        else:
            print("\nNo steps to advance right now.")
        if stopped:
            print(f"\nStopped {len(stopped)} sequences (deal won/lost/replied):")
            for d in stopped:
                print(f"  Deal {d}")

    elif cmd == "status":
        active = engine.get_all_active()
        print(render_status(active))

    elif cmd == "pause":
        if len(sys.argv) < 3:
            print("Usage: email_sequences.py pause <deal_id>")
            sys.exit(1)
        deal_id = sys.argv[2]
        result = engine.pause(deal_id)
        if result:
            print(f"Sequence paused for deal {deal_id}")

    elif cmd == "resume":
        if len(sys.argv) < 3:
            print("Usage: email_sequences.py resume <deal_id>")
            sys.exit(1)
        deal_id = sys.argv[2]
        result = engine.resume(deal_id)
        if result:
            print(f"Sequence resumed for deal {deal_id} (dates shifted)")

    elif cmd == "skip":
        if len(sys.argv) < 3:
            print("Usage: email_sequences.py skip <deal_id>")
            sys.exit(1)
        deal_id = sys.argv[2]
        result = engine.skip_deal(deal_id)
        if result:
            print(f"Sequence skipped for deal {deal_id}")

    elif cmd == "stats":
        tracker = SequenceTracker()
        perf = tracker.get_performance()
        ab = tracker.get_ab_results()
        print(render_stats(perf, ab))

    else:
        print(f"Unknown command: {cmd}")
        print("Usage: email_sequences.py [start|advance|status|pause|resume|skip|stats]")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import traceback
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(f"[{datetime.now().isoformat()}] [FATAL] {e}\n")
            f.write(traceback.format_exc() + "\n")
        print(f"FATAL: {e}", file=sys.stderr)
        raise
