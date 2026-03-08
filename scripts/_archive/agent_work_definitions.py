#!/usr/bin/env python3
"""
Agent Work Definitions — What each agent MUST do every cycle
=============================================================
Every agent has continuous work. No idle time. No placeholders.

This module defines:
1. Continuous tasks each agent performs every cycle
2. Learning goals — what each agent improves over time
3. Outputs — what each agent should send to Josef

Used by orchestrator.py to dispatch work and track progress.

Usage:
    python3 scripts/agent_work_definitions.py           # Show all agent tasks
    python3 scripts/agent_work_definitions.py <agent>    # Show specific agent
"""

import json
import sys
from datetime import datetime
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]

AGENT_WORK = {
    "spojka": {
        "display": "🔗 Spojka (Bridge)",
        "role": "Koordinátor mezi agenty, hlavní komunikační uzel",
        "continuous_tasks": [
            "Generuj morning briefing (knowledge/USER_DIGEST_AM.md) — reálná data",
            "Kontroluj bus/ na nerozeslanou poštu a přepošli správným agentům",
            "Zkontroluj approval-queue/ na čekající schválení",
            "Monitoruj konflikty mezi agenty a vyřeš je",
            "Konsoliduj výstupy ze všech agentů do denního přehledu",
        ],
        "learning_goals": [
            "Naučit se predikovat, který agent bude potřebovat pomoc",
            "Optimalizovat routing zpráv — méně latence, méně chyb",
            "Budovat kontext-awareness — co říkali agenti minulý týden",
        ],
        "outputs_for_josef": [
            "Ranní briefing s TOP 3 akcemi",
            "Alert pokud agent nemá data nebo selhal",
            "Týdenní shrnutí aktivity celého systému",
        ],
        "recovery_script": "morning-briefing.sh",
        "schedule": "Každý cyklus (30 min)",
    },

    "obchodak": {
        "display": "📊 Obchodák (Pipeline Pilot)",
        "role": "Pipeline management, deal scoring, lead enrichment",
        "continuous_tasks": [
            "Scoring dealů — spusť pipedrive_lead_scorer.py každých 4h",
            "Detekce stale dealů (>14 dní bez aktivity) → STALE_DEALS.md",
            "Pipeline hygiene — kontrola aktivit (activity guard)",
            "Analyzuj patterns vyhranych vs prohraných dealů",
            "Enrichuj nové leady přes Lusha API",
            "Aktualizuj PIPELINE_STATUS.md s reálnými čísly",
        ],
        "learning_goals": [
            "Zlepšit scoring model — přidej industry-specific váhy",
            "Naučit se predikovat win probability per deal",
            "Trackuj velocity — kolik dní v každém stage v průměru",
            "Analyzuj, které lead sources mají nejlepší konverzi",
        ],
        "outputs_for_josef": [
            "DEAL_SCORING.md — aktuální skóre všech dealů",
            "PIPELINE_STATUS.md — pipeline overview",
            "STALE_DEALS.md — dealy co potřebují pozornost",
            "Telegram alert pokud se deal posune do Negotiation/Won/Lost",
        ],
        "recovery_script": "pipedrive_lead_scorer.py",
        "schedule": "Každé 4 hodiny (9, 13, 17)",
    },

    "postak": {
        "display": "📮 Pošťák (Inbox Forge)",
        "role": "Email drafts, follow-up sequences, inbox monitoring",
        "continuous_tasks": [
            "Generuj email drafty pro top stale dealy (Claude Sonnet)",
            "Personalizuj emaily podle deal kontextu a stage",
            "Kontroluj drafts/ na drafty ke kontrole",
            "Připrav follow-up sequences pro nové dealy",
            "Analyzuj inbox na odpovědi od prospectů",
        ],
        "learning_goals": [
            "Zlepšit email copy — A/B testování subject lines",
            "Naučit se timing — kdy posílat emaily (den, hodina)",
            "Budovat template library — co funguje per industry",
            "Analyzuj response rates per template typ",
        ],
        "outputs_for_josef": [
            "Email drafty v drafts/ ke kontrole",
            "Gmail drafty přes MCP (v budoucnu)",
            "Telegram: 'X nových draftů ke kontrole'",
            "Měsíční report: response rates, best templates",
        ],
        "recovery_script": "recover_inbox.py",
        "schedule": "Ráno v 8:00 + po každém pipeline update",
    },

    "strateg": {
        "display": "🎯 Stratég (Growth Lab)",
        "role": "Market research, competitive intel, growth strategy",
        "continuous_tasks": [
            "Monitoruj konkurenci — competitive_intel.py scan",
            "Analyzuj trendy v HR tech a engagement industry",
            "Připrav battle cards per competitor",
            "Generuj weekly strategic brief",
            "Analyzuj win/loss patterny a doporuč strategy změny",
        ],
        "learning_goals": [
            "Mapovat competitive landscape — kdo co dělá",
            "Identifikovat emerging trends v employee engagement",
            "Predikovat competitor moves",
            "Budovat pricing intelligence — jak se mění trh",
        ],
        "outputs_for_josef": [
            "intel/DAILY-INTEL.md — denní intelligence",
            "Strategic brief (týdně)",
            "Battle cards per competitor",
            "Telegram: alert pokud competitor udělá významný tah",
        ],
        "recovery_script": "recover_intel.py",
        "schedule": "Denně ráno + triggered při competitive mention",
    },

    "kalendar": {
        "display": "📅 Kalendář (Calendar Captain)",
        "role": "Schedule management, meeting prep, time optimization",
        "continuous_tasks": [
            "Generuj TODAY.md z reálného Google Calendar",
            "Kalkuluj volné focus bloky (>45 min) pro deep work",
            "Připrav Pomodoro schedule pro hovory",
            "Kontroluj konflikty v kalendáři",
            "Generuj meeting prep pro upcoming schůzky",
        ],
        "learning_goals": [
            "Optimalizovat schedule — najdi patterns v produktivitě",
            "Predikovat kolik času calls zabere (historická data)",
            "Naučit se buffer time management pro ADHD",
            "Trackovat focus time vs meeting time ratio",
        ],
        "outputs_for_josef": [
            "calendar/TODAY.md — přehled dne",
            "Focus bloky s Pomodoro plánem",
            "Meeting prep pro každou schůzku",
            "Telegram: 'Za 15 min máš call s X — prep ready'",
        ],
        "recovery_script": "recover_calendar.py",
        "schedule": "Každý cyklus + triggered při calendar change",
    },

    "kontrolor": {
        "display": "✅ Kontrolor (Reviewer)",
        "role": "Quality assurance, output review, system health",
        "continuous_tasks": [
            "Review všech agent výstupů — kontrola kvality",
            "Kontroluj system health — SYSTEM_HEALTH.md",
            "Validuj data konzistenci mezi agenty",
            "Kontroluj logy na errory a warningy",
            "Audtuj email drafty před schválením",
        ],
        "learning_goals": [
            "Budovat quality metrics per agent",
            "Naučit se rozpoznat degradaci kvality",
            "Identifikovat data inconsistencies automaticky",
            "Budovat regression test suite pro agenty",
        ],
        "outputs_for_josef": [
            "reviews/SYSTEM_HEALTH.md — zdraví systému",
            "reviews/PENDING_REVIEWS.md — co potřebuje review",
            "Telegram: alert při kritickém health problému",
            "Týdenní quality report",
        ],
        "recovery_script": "recover_reviewer.py",
        "schedule": "Každý cyklus (30 min)",
    },

    "archivar": {
        "display": "📚 Archivář (Knowledge Keeper)",
        "role": "Knowledge management, graph building, deduplication",
        "continuous_tasks": [
            "Buduj knowledge graph z deal dat a interakcí",
            "Deduplikuj knowledge base (knowledge_dedup.py)",
            "Organizuj meeting-prep/ do archivu",
            "Indexuj nové informace z agentů",
            "Exportuj knowledge graph pro ostatní agenty",
        ],
        "learning_goals": [
            "Budovat relationship map — kdo zná koho",
            "Trackovat knowledge gaps — co nám chybí",
            "Optimalizovat search — aby se agenti rychle dostali k info",
            "Analyzovat knowledge utilization — co se používá, co ne",
        ],
        "outputs_for_josef": [
            "knowledge/IMPROVEMENTS.md — co se naučil systém",
            "Knowledge graph export",
            "Deduplication report",
        ],
        "recovery_script": None,
        "schedule": "Noční run + po velkých datech",
    },

    "udrzbar": {
        "display": "🔧 Údržbář (Deal Ops)",
        "role": "System maintenance, CRM sync, data hygiene",
        "continuous_tasks": [
            "Pipedrive write-back — aktualizuj CRM z agent outputů",
            "Cleanup starých logů (>7 dní)",
            "Kontroluj disk space a performance",
            "Validuj credential soubory",
            "Synchronizuj agent states s reality",
        ],
        "learning_goals": [
            "Automatizovat více CRM operací",
            "Budovat self-healing capabilities",
            "Optimalizovat resource usage (API calls, tokens)",
            "Predikovat system failures před tím než nastanou",
        ],
        "outputs_for_josef": [
            "Telegram: alert při system problému",
            "Maintenance report (týdně)",
        ],
        "recovery_script": None,
        "schedule": "Noční run + on-demand",
    },

    "textar": {
        "display": "✍️ Textař (Copy Agent)",
        "role": "Content creation, email copy, social posts",
        "continuous_tasks": [
            "Generuj SPIN email drafty pro deals (Claude Sonnet)",
            "Piš LinkedIn posty pro Josefa",
            "Připrav case study drafty z vyhranych dealů",
            "Personalizuj obsah per industry/persona",
            "Generuj follow-up templaty",
        ],
        "learning_goals": [
            "Zlepšit český copy — natural, ne robotický",
            "Naučit se Josef's voice — jak on píše",
            "A/B testovat email subject lines",
            "Budovat content calendar — co kdy postovat",
        ],
        "outputs_for_josef": [
            "Email drafty v drafts/",
            "LinkedIn post návrhy",
            "Telegram: 'X nových draftů'",
        ],
        "recovery_script": None,
        "schedule": "Ráno v 8:00 + triggered při novém dealu",
    },

    "hlidac": {
        "display": "👁️ Hlídač (Auditor)",
        "role": "Monitoring, anomaly detection, competitor watch",
        "continuous_tasks": [
            "Monitoruj anomálie v pipeline (anomaly_detector.py)",
            "Sleduj competitor zmínky v deal notes",
            "Kontroluj engagement skóre — kdo klesá?",
            "Alert při neobvyklých patterech (velký deal lost, apod.)",
            "Monitoruj market news relevantní pro Behavera",
        ],
        "learning_goals": [
            "Budovat baseline pro 'normální' chování pipeline",
            "Zlepšit anomaly detection — méně false positives",
            "Predikovat deal risk na základě engagement patterns",
            "Trackovat industry trends automaticky",
        ],
        "outputs_for_josef": [
            "Telegram: anomaly alert",
            "Weekly anomaly report",
            "Competitor mention alerts",
        ],
        "recovery_script": None,
        "schedule": "Každé 4 hodiny + event-triggered",
    },

    "planovac": {
        "display": "⏰ Plánovač (Timebox)",
        "role": "Time management, scheduling, ADHD support",
        "continuous_tasks": [
            "Generuj Pomodoro plány per den",
            "Trackuj Josefovu produktivitu — focus vs meeting time",
            "Plánuj follow-up reminders",
            "Optimalizuj scheduling — minimalizuj context switching",
            "Generuj weekly planning overview",
        ],
        "learning_goals": [
            "Naučit se Josefovy productivity patterns",
            "Optimalizovat pro ADHD — správné bloky ve správný čas",
            "Predikovat energy levels per denní dobu",
            "Budovat time audit — kam čas skutečně jde",
        ],
        "outputs_for_josef": [
            "Pomodoro plán v morning prep",
            "Telegram: reminder 5 min před callem",
            "Weekly time report",
            "Focus time recommendations",
        ],
        "recovery_script": None,
        "schedule": "Ráno + event-triggered",
    },

    "vyvojar": {
        "display": "💻 Vývojář (Codex)",
        "role": "Code improvements, bug fixes, new integrations",
        "continuous_tasks": [
            "Monitoring system logů na errory",
            "Identifikuj scripts co selhávají a navrhni fix",
            "Sleduj TODOs v kódu a prioritizuj",
            "Testuj integraci — Pipedrive, Telegram, Gmail",
            "Optimalizuj performance kritických skriptů",
        ],
        "learning_goals": [
            "Budovat automated test suite",
            "Identifikovat tech debt a prioritizovat",
            "Navrhnout nové integrace (Slack, HubSpot, etc.)",
            "Optimalizovat token usage — méně tokenů, stejná kvalita",
        ],
        "outputs_for_josef": [
            "Bug reports + proposed fixes",
            "System performance report",
            "New feature proposals",
        ],
        "recovery_script": None,
        "schedule": "Noční run + on-demand",
    },
}


def print_agent(agent_id):
    agent = AGENT_WORK.get(agent_id)
    if not agent:
        print(f"Unknown agent: {agent_id}")
        return

    print(f"\n{'='*60}")
    print(f"  {agent['display']}")
    print(f"  {agent['role']}")
    print(f"{'='*60}")

    print(f"\n📋 CONTINUOUS TASKS:")
    for t in agent["continuous_tasks"]:
        print(f"  • {t}")

    print(f"\n📈 LEARNING GOALS:")
    for g in agent["learning_goals"]:
        print(f"  • {g}")

    print(f"\n📤 OUTPUTS FOR JOSEF:")
    for o in agent["outputs_for_josef"]:
        print(f"  • {o}")

    print(f"\n⏰ Schedule: {agent['schedule']}")
    if agent.get("recovery_script"):
        print(f"🔧 Recovery: {agent['recovery_script']}")


def export_summary():
    """Export agent work definitions to markdown."""
    lines = [f"# Agent Work Definitions — {datetime.now().strftime('%Y-%m-%d')}\n"]
    for agent_id, agent in AGENT_WORK.items():
        lines.append(f"## {agent['display']}")
        lines.append(f"*{agent['role']}*\n")

        lines.append("**Continuous Tasks:**")
        for t in agent["continuous_tasks"]:
            lines.append(f"- {t}")

        lines.append("\n**Learning Goals:**")
        for g in agent["learning_goals"]:
            lines.append(f"- {g}")

        lines.append(f"\n**Schedule:** {agent['schedule']}")
        lines.append("")

    output = WORKSPACE / "knowledge" / "AGENT_WORK_DEFINITIONS.md"
    output.write_text("\n".join(lines))
    print(f"Exported to {output}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        agent_id = sys.argv[1]
        if agent_id == "--export":
            export_summary()
        else:
            print_agent(agent_id)
    else:
        for agent_id in AGENT_WORK:
            print_agent(agent_id)
        print(f"\nUse --export to save to markdown")
