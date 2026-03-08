#!/usr/bin/env python3
"""
Daily Sales Tips — Morning inspiration for Josef
==================================================
Every morning at 7:30, sends:
- Sales tip/insight from one of Josef's books
- Current sales trend or technique
- Motivational quote or ADHD productivity hack

Uses Claude to generate fresh, relevant content.
Pulls from Josef's book library (50+ PDFs/EPUBs on sales, HR, AI).

Usage:
    python3 scripts/sales_tips_email.py             # Generate tip
    python3 scripts/sales_tips_email.py --send       # Generate + send via Telegram
"""

import json
import random
import sys
from datetime import datetime, date

from lib.paths import WORKSPACE
from lib.secrets import get_api_key
from lib.claude_api import claude_generate
from lib.logger import make_logger
from lib.notifications import notify_telegram

OUTPUT = WORKSPACE / "knowledge" / "DAILY_SALES_TIP.md"
TIPS_HISTORY = WORKSPACE / "knowledge" / "tips_history.json"

log_msg = make_logger("sales-tips")

# Josef's book library — categorized for targeted tips
BOOKS = {
    "sales": [
        {"title": "The AI Edge", "author": "Jeb Blount", "topic": "AI in sales, prospecting with technology"},
        {"title": "The LinkedIn Edge", "author": "Jeb Blount", "topic": "LinkedIn selling, social selling strategies"},
        {"title": "Sales Automation", "author": "Anne Cordts", "topic": "Automating sales processes, CRM optimization"},
        {"title": "Sales Funnels", "author": "Tiago Lima", "topic": "Funnel optimization, conversion strategies"},
        {"title": "AI Power Funnels", "author": "Ylva Bosemark", "topic": "AI-powered sales funnels, online sales growth"},
        {"title": "Amplify Your Influence", "author": "Rene Rodriguez", "topic": "Persuasion, influence in sales conversations"},
        {"title": "Building a StoryBrand 2.0", "author": "Donald Miller", "topic": "Brand messaging, customer-centric stories"},
        {"title": "CHATGPT AI Business Prompts", "author": "Alex Wright", "topic": "AI prompts for business growth"},
    ],
    "engagement_hr": [
        {"title": "Strategic Employee Surveys", "author": "Jack Wiley", "topic": "Designing effective employee surveys"},
        {"title": "Build it: The Rebel Playbook for Employee Engagement", "author": "Glenn Elliott & Debra Corey", "topic": "Non-traditional engagement strategies"},
        {"title": "42 Rules of Employee Engagement", "author": "Susan Stamm", "topic": "Practical engagement rules"},
        {"title": "Employee Engagement Research Agenda", "author": "John P. Meyer", "topic": "Academic research on engagement"},
        {"title": "The Stepford Employee Fallacy", "author": "Jonathan Villaire", "topic": "Why traditional engagement fails"},
        {"title": "State of the Global Workplace 2025", "author": "Gallup", "topic": "Global engagement benchmarks and trends"},
        {"title": "Data-Driven HR", "author": "Bernard Marr", "topic": "Using analytics in HR decisions"},
        {"title": "AI Revolution in Human Resources", "author": "Sonja Lekahena", "topic": "AI transforming HR practices"},
    ],
    "ai_agents": [
        {"title": "Building AI Agents with LLMs, RAG, and Knowledge Graphs", "author": "Salvatore Raieli", "topic": "Multi-agent AI architectures"},
        {"title": "Build a Multi-Agent System with MCP and A2A", "author": "Val Andrei Fajardo", "topic": "MCP protocol, agent-to-agent communication"},
        {"title": "Context Engineering for Multi-Agent Systems", "author": "Denis Rothman", "topic": "Context management in AI systems"},
        {"title": "Agentic AI in Enterprise", "author": "Sumit Ranjan", "topic": "Enterprise AI agent deployment"},
        {"title": "Beyond Vibe Coding", "author": "Addy Osmani", "topic": "AI-era development practices"},
    ],
    "tech_ops": [
        {"title": "Release It", "author": "Michael Nygard", "topic": "Production-ready software patterns"},
        {"title": "Designing Data-Intensive Applications", "author": "Martin Kleppmann", "topic": "Distributed systems design"},
        {"title": "Building Microservices", "author": "Sam Newman", "topic": "Microservice architecture patterns"},
        {"title": "Accelerate", "author": "Nicole Forsgren", "topic": "DevOps performance and organizational culture"},
    ],
}

# Daily themes — different focus each day
DAILY_THEMES = {
    0: ("sales", "Pondělí — Sales Kickoff"),    # Monday
    1: ("engagement_hr", "Úterý — HR & Engagement"),
    2: ("sales", "Středa — Prospecting"),
    3: ("ai_agents", "Čtvrtek — AI & Tech"),
    4: ("sales", "Pátek — Closing & Review"),
    5: ("tech_ops", "Sobota — Tech Deep Dive"),
    6: ("engagement_hr", "Neděle — Inspiration"),
}

ADHD_TIPS = [
    "Body doubling: Pracuj na callech, když je vedle tebe někdo jiný (i virtuálně).",
    "2-minutové pravidlo: Pokud to trvá < 2 minuty, udělej to HNED.",
    "Pomodoro: 25 min focus + 5 min pauza. Po 4 kolech 15 min pauza.",
    "Eat the frog: Nejhorší úkol udělej PRVNÍ. Pak je zbytek dne lehčí.",
    "Ulož telefon do jiné místnosti. Seriously.",
    "Stav queue: Před každým callem si napiš 1 větu — proč volám.",
    "Dopaminový hack: Za každý dokončený call si dej malou odměnu.",
    "Záchranný alarm: Nastav si timer na 5 min — pokud nevíš co dělat, za 5 min začni s čímkoliv.",
    "Nesnaž se být perfektní. First draft = done > perfect.",
    "Power hour: 60 minut, žádný email, žádný Slack. Jen hovory.",
    "Vizualizace: Představ si, jak deal uzavřeš. Mozek to bere jako odměnu.",
    "Micro-commitments: Slíbil sis 10 callů? Udělej JEDEN. Pak se rozhodni znovu.",
]


def load_tip_history():
    """Load previously used tips to avoid repetition."""
    if TIPS_HISTORY.exists():
        try:
            return json.loads(TIPS_HISTORY.read_text())
        except json.JSONDecodeError:
            pass
    return {"used_books": [], "used_topics": [], "last_date": ""}


def save_tip_history(history):
    TIPS_HISTORY.parent.mkdir(parents=True, exist_ok=True)
    TIPS_HISTORY.write_text(json.dumps(history, indent=2, ensure_ascii=False))


def pick_book(category, history):
    """Pick a book that hasn't been used recently."""
    books = BOOKS.get(category, BOOKS["sales"])
    used = set(history.get("used_books", [])[-14:])  # Rotate every 2 weeks

    available = [b for b in books if b["title"] not in used]
    if not available:
        # Reset — all books used
        available = books

    return random.choice(available)


def generate_tip(api_key, book, theme_name, adhd_tip):
    """Generate a sales tip using Claude."""
    system = """Jsi Josef Hofman's osobní sales coach. Píšeš mu každé ráno krátký,
inspirativní tip v češtině. Styl: přímý, bez bullshitu, akční.

Pravidla:
- Max 200 slov celkem
- Začni rovnou pointou, žádné "Dobré ráno"
- Zakonči jednou konkrétní akcí, kterou může udělat DNES
- Piš jako kamarád co rozumí sales, ne jako učitel
- Používej české příklady a kontext (firmy 50-500 zaměstnanců)
- Občas zmíň Echo Pulse / Behavera jako kontext"""

    prompt = f"""Dnešní téma: {theme_name}

Inspiruj se touto knihou: "{book['title']}" od {book['author']}
Téma knihy: {book['topic']}

Napiš denní sales tip. Struktura:
1. Hlavní insight z knihy (2-3 věty)
2. Jak to aplikovat na B2B sales engagementu zaměstnanců v ČR (2-3 věty)
3. Jedna konkrétní akce na dnes (1 věta)

ADHD tip dne: {adhd_tip}"""

    return claude_generate(api_key, system, prompt, max_tokens=600)


def main(send_telegram=False):
    api_key = get_api_key()

    today = date.today()
    now = datetime.now()

    # Get today's theme
    category, theme_name = DAILY_THEMES.get(today.weekday(), ("sales", "Sales"))

    # Load history
    history = load_tip_history()

    # Pick book
    book = pick_book(category, history)

    # Pick ADHD tip
    adhd_tip = random.choice(ADHD_TIPS)

    log_msg(f"Generating tip from '{book['title']}' ({category})")

    # Generate tip
    tip_content = generate_tip(api_key, book, theme_name, adhd_tip)

    if not tip_content:
        # Fallback
        tip_content = f"""**{theme_name}**

📚 Z knihy *{book['title']}* ({book['author']}):
{book['topic']}

🎯 **Akce na dnes:** Zavolej jednomu dealu, co jsi dlouho neřešil. Jen 5 minut.

🧠 **ADHD tip:** {adhd_tip}"""

    # Build full document
    sections = []
    sections.append(f"# 📚 Sales Tip — {today.isoformat()}")
    sections.append(f"*{theme_name} | Z knihy: {book['title']}*\n")
    sections.append(tip_content)
    sections.append(f"\n---\n🧠 **ADHD Tip:** {adhd_tip}")
    sections.append(f"\n---\n*Sales Tips v1 | {now.strftime('%H:%M')} | Zdroj: {book['title']} ({book['author']})*")

    content = "\n".join(sections)

    # Save
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content)
    log_msg(f"Tip saved: {len(content)}B from '{book['title']}'")
    print(f"Sales tip saved to {OUTPUT}")

    # Update history
    history["used_books"].append(book["title"])
    history["used_books"] = history["used_books"][-30:]  # Keep last 30
    history["last_date"] = today.isoformat()
    save_tip_history(history)

    # Telegram
    if send_telegram:
        tg = f"📚 *{theme_name}*\n\n"
        tg += tip_content[:800]  # Telegram has limits
        tg += f"\n\n🧠 *ADHD:* {adhd_tip}"
        notify_telegram(tg)
        log_msg("Telegram notification sent")

    return 0


if __name__ == "__main__":
    send = "--send" in sys.argv
    exit(main(send_telegram=send))
