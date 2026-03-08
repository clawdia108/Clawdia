#!/usr/bin/env python3
"""
Agent Dispatcher — 30min Work Pulses for All Agents
=====================================================
Every 30 minutes, dispatches REAL work to all 12 agents.
Not placeholders — concrete tasks tied to live Pipedrive data,
real emails, actual calendar events, system state.

Each agent gets work matched to its capabilities:
- obchodak: score deals, find stale ones, enrich leads
- textar: write email drafts for top deals
- postak: check inbox for replies, draft follow-ups
- strateg: research competitors, find trends
- kalendar: prep for upcoming meetings
- kontrolor: review agent outputs, check health
- etc.

Work assignments are published to bus/inbox/{agent}/ as messages
and tracked in control-plane/agent-states.json.

Usage:
    python3 scripts/agent_dispatcher.py              # Run one pulse
    python3 scripts/agent_dispatcher.py --status      # Show agent workload
    python3 scripts/agent_dispatcher.py --week-plan   # Generate weekly plan

Runs every 30 minutes via launchd (com.clawdia.dispatcher).
"""

import json
import subprocess
import sys
import time
from datetime import datetime, date, timedelta
from pathlib import Path

from lib.agent_health import collect_agent_health
from lib.paths import WORKSPACE, BUS_INBOX
from lib.secrets import load_secrets
from lib.claude_api import claude_generate
from lib.pipedrive import pipedrive_get
from lib.logger import make_logger
from lib.notifications import notify_telegram as _notify_telegram

LOG_FN = make_logger("dispatcher")
AGENT_STATES = WORKSPACE / "control-plane" / "agent-states.json"
TASK_QUEUE = WORKSPACE / "control-plane" / "task-queue.json"
WEEKLY_PLAN = WORKSPACE / "knowledge" / "WEEKLY_AGENT_PLAN.md"

WORK_HOURS = (7, 20)


def log(msg, level="INFO"):
    LOG_FN(msg, level)


def load_agent_states():
    if AGENT_STATES.exists():
        try:
            return json.loads(AGENT_STATES.read_text())
        except json.JSONDecodeError:
            pass
    return {"agents": {}}


def save_agent_states(states):
    AGENT_STATES.parent.mkdir(parents=True, exist_ok=True)
    AGENT_STATES.write_text(json.dumps(states, indent=2, ensure_ascii=False))


def publish_task(agent_id, task):
    """Publish a work task to agent's bus inbox."""
    inbox = BUS_INBOX / agent_id
    inbox.mkdir(parents=True, exist_ok=True)

    msg = {
        "id": f"dispatch-{agent_id}-{int(time.time())}",
        "source": "dispatcher",
        "topic": f"work.assigned",
        "type": "REQUEST",
        "priority": task.get("priority", "P2"),
        "payload": task,
        "target": agent_id,
        "created_at": datetime.now().isoformat(),
        "ttl_hours": 2,
    }

    msg_file = inbox / f"{msg['id']}.json"
    msg_file.write_text(json.dumps(msg, indent=2, ensure_ascii=False))
    return msg_file


def get_pipeline_context(secrets):
    """Get real pipeline data for work assignment."""
    base = secrets.get("PIPEDRIVE_BASE_URL", "").rstrip("/")
    token = secrets.get("PIPEDRIVE_API_TOKEN", "")
    if not base or not token:
        return {}

    deals = pipedrive_get(base, token, "/api/v1/deals", {"status": "open", "limit": 100})

    today = date.today()
    activities = pipedrive_get(base, token, "/api/v1/activities", {
        "start_date": today.isoformat(),
        "end_date": (today + timedelta(days=2)).isoformat(),
        "done": 0,
    })

    stale = [d for d in deals if d and _days_since(d.get("last_activity_date")) > 14]
    hot = [d for d in deals if d and d.get("stage_id") in (9, 10, 12, 29)]
    new = [d for d in deals if d and _days_since(d.get("add_time")) < 7]

    total_value = sum((d.get("value") or 0) for d in deals if d)

    return {
        "total_deals": len(deals),
        "stale_count": len(stale),
        "hot_count": len(hot),
        "new_count": len(new),
        "today_activities": len(activities),
        "total_value": total_value,
        "top_stale": [_deal_summary(d) for d in stale[:5]],
        "top_hot": [_deal_summary(d) for d in hot[:5]],
        "top_new": [_deal_summary(d) for d in new[:3]],
        "activities": [_activity_summary(a) for a in (activities or [])[:5]],
    }


def _days_since(date_str):
    if not date_str:
        return 999
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d").date()
        return (date.today() - d).days
    except (ValueError, TypeError):
        return 999


def _deal_summary(deal):
    if not deal:
        return {}
    org = deal.get("org_id") or {}
    org_name = org.get("name", "?") if isinstance(org, dict) else "?"
    person = deal.get("person_id") or {}
    contact = person.get("name", "") if isinstance(person, dict) else ""
    return {
        "id": deal.get("id"),
        "title": deal.get("title", ""),
        "org": org_name,
        "contact": contact,
        "value": deal.get("value") or 0,
        "stage_id": deal.get("stage_id"),
        "days_stale": _days_since(deal.get("last_activity_date")),
    }


def _activity_summary(act):
    if not act:
        return {}
    return {
        "type": act.get("type", ""),
        "subject": act.get("subject", ""),
        "due_date": act.get("due_date", ""),
        "deal_id": act.get("deal_id"),
    }


def get_system_health():
    """Check runtime health with output freshness as fallback."""
    raw = collect_agent_health(workspace=WORKSPACE)
    status_map = {"OK": "ok", "STALE": "stale", "EMPTY": "missing", "DEAD": "missing"}
    health = {}
    for agent, info in raw.items():
        health[agent] = {
            "status": status_map.get(info.get("status"), "missing"),
            "age_hours": info.get("age_hours") if info.get("age_hours") is not None else 999,
            "source": info.get("source"),
            "output_status": info.get("output_status"),
        }
    return health


def get_draft_status():
    """Check existing drafts and their quality."""
    drafts_dir = WORKSPACE / "drafts"
    if not drafts_dir.exists():
        return {"count": 0, "recent": []}
    drafts = list(drafts_dir.glob("*.md")) + list(drafts_dir.glob("*.json"))
    recent = sorted(drafts, key=lambda f: f.stat().st_mtime, reverse=True)[:5]
    return {
        "count": len(drafts),
        "recent": [f.name for f in recent],
    }


def dispatch_work(pipeline, health, draft_status, secrets, now):
    """Dispatch concrete work tasks to each agent based on real data."""
    api_key = secrets.get("ANTHROPIC_API_KEY", "")
    hour = now.hour
    weekday = now.weekday()  # 0=Mon, 6=Sun
    is_weekend = weekday >= 5
    dispatched = []

    # ── OBCHODÁK: Pipeline scoring + stale detection ──
    if pipeline.get("total_deals", 0) > 0:
        task = {
            "action": "score_and_analyze",
            "description": f"Skóruj {pipeline['total_deals']} dealů. "
                          f"{pipeline['stale_count']} stale, {pipeline['hot_count']} hot, {pipeline['new_count']} nových. "
                          f"Pipeline value: {pipeline['total_value']:,.0f} CZK.",
            "specific_work": [
                f"Aktualizuj DEAL_SCORING.md — znovu skóruj všechny open dealy",
                f"Zkontroluj {pipeline['stale_count']} stale dealů a navrhni akci pro každý",
                f"Enrichuj nové dealy přes Lusha pokud nemají kontakt",
            ],
            "data": {"stale": pipeline.get("top_stale", []), "hot": pipeline.get("top_hot", [])},
            "priority": "P1",
            "script": "pipedrive_lead_scorer.py",
        }
        publish_task("obchodak", task)
        dispatched.append("obchodak: scoring + stale detection")

    # ── TEXTAR: Email drafts ──
    if pipeline.get("top_stale") and not is_weekend:
        stale_orgs = [d.get("org", "?") for d in pipeline["top_stale"][:3]]
        task = {
            "action": "generate_email_drafts",
            "description": f"Napiš follow-up emaily pro stale dealy: {', '.join(stale_orgs)}",
            "specific_work": [
                f"Vygeneruj SPIN email pro každý z {min(3, len(stale_orgs))} stale dealů",
                "Každý email MUSÍ projít 3-agent review pipeline (Humanizer → Czech Expert → Sales)",
                "Ulož do drafts/ jako .md + .json",
                "Zkontroluj HUMANIZER_TRAINING.md pro Josefův styl",
            ],
            "data": {"deals": pipeline.get("top_stale", [])[:3]},
            "priority": "P1",
            "script": "draft_generator.py 3",
        }
        publish_task("textar", task)
        dispatched.append(f"textar: drafty pro {', '.join(stale_orgs[:2])}")

    # ── POSTAK: Follow-up sequences ──
    if not is_weekend:
        task = {
            "action": "check_inbox_and_followups",
            "description": "Zkontroluj inbox na odpovědi a připrav follow-up sekvence",
            "specific_work": [
                "Zkontroluj drafts/ — jsou tam neodeslané drafty?",
                "Připrav follow-up pro dealy bez odpovědi >5 dní",
                "Analyzuj response rate — které templaty fungují nejlíp",
            ],
            "priority": "P2",
        }
        publish_task("postak", task)
        dispatched.append("postak: inbox check + follow-ups")

    # ── STRATEG: Research + intel ──
    research_topics = []
    if weekday == 0:  # Monday
        research_topics = ["Analyzuj competitive landscape — kdo je nový na trhu employee engagement v ČR",
                          "Zkontroluj novinky od Sloneek, Arnold, LMC"]
    elif weekday == 1:  # Tuesday
        research_topics = ["Najdi 5 českých firem 50-200 zaměstnanců co hledají engagement řešení",
                          "Zkontroluj HR konference v ČR na další měsíc"]
    elif weekday == 2:  # Wednesday
        research_topics = ["Připrav battle card: Behavera vs Sloneek",
                          "Analyzuj trendy v employee engagement 2026"]
    elif weekday == 3:  # Thursday
        research_topics = ["Win/loss analýza posledních 10 dealů — proč jsme prohráli/vyhráli",
                          "Identifikuj top 3 industries s nejlepší konverzí"]
    elif weekday == 4:  # Friday
        research_topics = ["Připrav weekly strategic brief pro Josefa",
                          "Shrň co se děje u konkurence tento týden"]
    else:
        research_topics = ["Studuj články o SPIN selling v češtině",
                          "Najdi case studies employee engagement pro manufacturing"]

    task = {
        "action": "research_and_intel",
        "description": f"Denní research: {research_topics[0][:60]}...",
        "specific_work": research_topics,
        "priority": "P2",
    }
    publish_task("strateg", task)
    dispatched.append(f"strateg: {research_topics[0][:40]}")

    # ── KALENDÁŘ: Meeting prep + schedule ──
    if pipeline.get("activities") and not is_weekend:
        act_count = pipeline.get("today_activities", 0)
        task = {
            "action": "prep_meetings_and_schedule",
            "description": f"Připrav SPIN prep pro {act_count} aktivit dnes/zítra",
            "specific_work": [
                "Aktualizuj calendar/TODAY.md z Google Calendar",
                f"Připrav meeting prep pro {act_count} schůzek",
                "Naplánuj Pomodoro bloky pro calling time",
                "Zkontroluj konflikty v kalendáři na zítra",
            ],
            "data": {"activities": pipeline.get("activities", [])},
            "priority": "P1",
            "script": "meeting_prep.py --upcoming",
        }
        publish_task("kalendar", task)
        dispatched.append(f"kalendar: prep pro {act_count} schůzek")

    # ── KONTROLOR: Health check + quality review ──
    stale_agents = [a for a, h in health.items() if h["status"] != "ok"]
    task = {
        "action": "health_check_and_review",
        "description": f"System health: {len(stale_agents)} problémů. Review agent outputů.",
        "specific_work": [
            f"Zkontroluj stale agenty: {', '.join(stale_agents) if stale_agents else 'žádní'}",
            "Review posledních email draftů v drafts/ — kvalita OK?",
            "Zkontroluj logy na chyby za posledních 6h",
            "Aktualizuj reviews/SYSTEM_HEALTH.md",
        ],
        "data": {"health": health, "stale_agents": stale_agents},
        "priority": "P1",
    }
    publish_task("kontrolor", task)
    dispatched.append(f"kontrolor: health + review ({len(stale_agents)} stale)")

    # ── ARCHIVÁŘ: Knowledge management ──
    task = {
        "action": "knowledge_sync",
        "description": "Synchro knowledge base — deduplikace, indexace, export",
        "specific_work": [
            "Deduplikuj knowledge/ soubory",
            "Indexuj nové informace z dneška",
            "Exportuj aktuální knowledge graph",
            "Zkontroluj zda se knowledge base používá — co je zastaralé?",
        ],
        "priority": "P3",
    }
    publish_task("archivar", task)
    dispatched.append("archivar: knowledge sync")

    # ── ÚDRŽBÁŘ: System maintenance ──
    task = {
        "action": "system_maintenance",
        "description": "Údržba systému — cleanup, sync, monitoring",
        "specific_work": [
            "Cleanup logů starších 7 dní",
            "Zkontroluj disk space",
            "Validuj API klíče — fungují všechny?",
            "Synchronizuj agent-states.json s realitou",
        ],
        "priority": "P3",
    }
    publish_task("udrzbar", task)
    dispatched.append("udrzbar: maintenance")

    # ── HLÍDAČ: Anomaly detection ──
    task = {
        "action": "monitor_and_detect",
        "description": "Monitoruj pipeline anomálie a competitor zmínky",
        "specific_work": [
            "Spusť anomaly_detector.py",
            "Zkontroluj deal notes na competitor zmínky",
            f"Pipeline value: {pipeline.get('total_value', 0):,.0f} CZK — je to normální?",
            "Zkontroluj zda se neztratil velký deal",
        ],
        "priority": "P2",
    }
    publish_task("hlidac", task)
    dispatched.append("hlidac: anomaly detection")

    # ── PLÁNOVAČ: Productivity + ADHD support ──
    if not is_weekend:
        task = {
            "action": "plan_and_optimize",
            "description": "Denní Pomodoro plán a productivity tracking",
            "specific_work": [
                "Generuj Pomodoro plán pro zbytek dne",
                "Trackuj kolik času šlo na calls vs admin vs focus work",
                "Navrhni optimální scheduling pro zítra",
                "Zkontroluj zda má Josef dost focus bloků (>45 min)",
            ],
            "priority": "P2",
        }
        publish_task("planovac", task)
        dispatched.append("planovac: Pomodoro + productivity")

    # ── SPOJKA: Coordination ──
    task = {
        "action": "coordinate_agents",
        "description": f"Koordinuj {len(dispatched)} agentů, konsoliduj výstupy",
        "specific_work": [
            f"Zkontroluj bus/ — {len(dispatched)} agentů má novou práci",
            "Konsoliduj výstupy do morning briefingu",
            "Zkontroluj approval-queue/ na čekající schválení",
            "Připrav Josef's dashboard summary",
        ],
        "data": {"dispatched": dispatched},
        "priority": "P2",
    }
    publish_task("spojka", task)
    dispatched.append("spojka: coordination")

    # ── VÝVOJÁŘ: Code improvements (less frequent) ──
    if hour in (7, 11, 15, 19):
        task = {
            "action": "code_review_and_improve",
            "description": "Kontrola systému a návrhy vylepšení",
            "specific_work": [
                "Zkontroluj logs/ na opakující se errory",
                "Najdi scripts co selhávají a navrhni fix",
                "Identifikuj duplicitní kód mezi skripty",
                "Navrhni jedno konkrétní vylepšení systému",
            ],
            "priority": "P3",
        }
        publish_task("vyvojar", task)
        dispatched.append("vyvojar: code review")

    return dispatched


def run_executable_tasks(dispatched, secrets):
    """Actually execute tasks that have runnable scripts."""
    executed = []

    scripts_to_run = {
        "pipedrive_lead_scorer.py": ("obchodak", 120),
        "draft_generator.py 3": ("textar", 180),
    }

    for script_cmd, (agent, timeout) in scripts_to_run.items():
        if any(agent in d for d in dispatched):
            script_parts = script_cmd.split()
            script_path = WORKSPACE / "scripts" / script_parts[0]
            if script_path.exists():
                try:
                    cmd = ["python3", str(script_path)] + script_parts[1:]
                    log(f"Executing: {script_cmd} for {agent}")
                    subprocess.run(cmd, capture_output=True, timeout=timeout, cwd=str(WORKSPACE))
                    executed.append(f"{agent}: {script_cmd}")
                except subprocess.TimeoutExpired:
                    log(f"Timeout: {script_cmd}", "WARN")
                except Exception as e:
                    log(f"Execution error {script_cmd}: {e}", "ERROR")

    return executed


def notify_telegram(message):
    _notify_telegram(message)


def generate_week_plan(secrets):
    """Generate a concrete weekly plan for all agents."""
    api_key = secrets.get("ANTHROPIC_API_KEY", "")
    pipeline = get_pipeline_context(secrets)

    system = """Jsi manažer 12 AI agentů pro Czech sales tým (Behavera — Echo Pulse engagement surveys).
Vytvoř konkrétní týdenní plán práce pro každého agenta. ŽÁDNÉ placeholdery.
Každý agent musí mít 5-8 KONKRÉTNÍCH úkolů s měřitelnými výstupy.
Pipeline context ti pomůže vygenerovat reálné úkoly.
Piš česky. Formátuj jako markdown."""

    prompt = f"""Pipeline data:
- {pipeline.get('total_deals', 0)} open dealů, value {pipeline.get('total_value', 0):,.0f} CZK
- {pipeline.get('stale_count', 0)} stale, {pipeline.get('hot_count', 0)} hot, {pipeline.get('new_count', 0)} nových
- Top stale: {json.dumps(pipeline.get('top_stale', [])[:3], ensure_ascii=False)}
- Today activities: {pipeline.get('today_activities', 0)}

Vytvoř plán pro týden {date.today().isocalendar()[1]} ({date.today().isoformat()} - {(date.today() + timedelta(days=6)).isoformat()}).

Agenti: obchodak, textar, postak, strateg, kalendar, kontrolor, archivar, udrzbar, hlidac, planovac, spojka, vyvojar.

Pro každého agenta: 5-8 konkrétních úkolů s deadlinem (den v týdnu) a měřitelným výstupem."""

    plan = claude_generate(api_key, system, prompt, max_tokens=4096)
    if plan:
        header = f"# Weekly Agent Plan — Týden {date.today().isocalendar()[1]}\n"
        header += f"*Generováno: {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n"
        header += f"*Pipeline: {pipeline.get('total_deals', 0)} dealů, {pipeline.get('total_value', 0):,.0f} CZK*\n\n"
        full_plan = header + plan
        WEEKLY_PLAN.parent.mkdir(parents=True, exist_ok=True)
        WEEKLY_PLAN.write_text(full_plan)
        log(f"Weekly plan generated: {len(full_plan)} chars")
        print(f"Weekly plan saved to {WEEKLY_PLAN}")
        return full_plan
    else:
        log("Failed to generate weekly plan", "ERROR")
        print("Failed to generate weekly plan")
        return None


def show_status():
    """Show current agent workload and inbox status."""
    print(f"\n{'='*60}")
    print(f"  Agent Dispatcher Status — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}\n")

    health = get_system_health()
    for agent, h in sorted(health.items()):
        status_icon = "✅" if h["status"] == "ok" else "⚠️" if h["status"] == "stale" else "❌"
        inbox_dir = BUS_INBOX / agent
        inbox_count = len(list(inbox_dir.glob("*.json"))) if inbox_dir.exists() else 0
        print(f"  {status_icon} {agent:12s} | output: {h['age_hours']:5.1f}h | inbox: {inbox_count} msgs")

    # Task queue
    if TASK_QUEUE.exists():
        try:
            tq = json.loads(TASK_QUEUE.read_text())
            tasks = tq.get("tasks", [])
            pending = sum(1 for t in tasks if isinstance(t, dict) and t.get("status") != "done")
            print(f"\n  Task queue: {pending} pending / {len(tasks)} total")
        except json.JSONDecodeError:
            pass

    print()


def main():
    args = sys.argv[1:]

    if "--status" in args:
        show_status()
        return

    secrets = load_secrets()

    if "--week-plan" in args:
        generate_week_plan(secrets)
        return

    # Check work hours
    now = datetime.now()
    if now.hour < WORK_HOURS[0] or now.hour >= WORK_HOURS[1]:
        log("Outside work hours — skipping dispatch")
        return

    if now.weekday() >= 5:
        # Weekend — lighter workload
        log("Weekend — reduced dispatch")

    log("Starting dispatch pulse...")
    print(f"Dispatch pulse — {now.strftime('%Y-%m-%d %H:%M')}")

    # Gather context
    pipeline = get_pipeline_context(secrets)
    health = get_system_health()
    draft_status = get_draft_status()

    # Dispatch work
    dispatched = dispatch_work(pipeline, health, draft_status, secrets, now)

    # Execute runnable tasks
    executed = run_executable_tasks(dispatched, secrets)

    # Summary
    log(f"Dispatched {len(dispatched)} tasks, executed {len(executed)} scripts")
    print(f"  Dispatched: {len(dispatched)} agents")
    for d in dispatched:
        print(f"    • {d}")
    if executed:
        print(f"  Executed: {len(executed)} scripts")
        for e in executed:
            print(f"    ✓ {e}")

    # Telegram summary (every 4 hours, not every 30 min)
    if now.hour in (7, 11, 15, 19) and now.minute < 35:
        tg = f"🤖 Agent Pulse — {now.strftime('%H:%M')}\n"
        tg += f"Dispatched: {len(dispatched)} agentů\n"
        stale = [a for a, h in health.items() if h["status"] != "ok"]
        if stale:
            tg += f"⚠️ Stale: {', '.join(stale)}\n"
        tg += f"Pipeline: {pipeline.get('total_deals', 0)} dealů, "
        tg += f"{pipeline.get('stale_count', 0)} stale, "
        tg += f"{pipeline.get('hot_count', 0)} hot"
        notify_telegram(tg)


if __name__ == "__main__":
    main()
