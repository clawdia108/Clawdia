#!/usr/bin/env python3
"""
Signal Scanner — monitoring buying signálů pro deals v pipeline.

Zdroje signálů:
1. Google Alerts / Talkwalker (RSS feeds)
2. Atmoskop.cz (české Glassdoor — zaměstnanecké recenze)
3. Jobs.cz (hiring signály — HR/People pozice)
4. Firmy.cz (základní info o firmě)
5. LinkedIn (via web search)
6. Leadfeeder (website visitors — via Pipedrive integration)

Pro každý deal:
1. Vyhledá signály o firmě
2. Uloží nalezené signály do knowledge/signals/
3. Enrichuje SPIN briefy o fresh data
4. Flaguje hot signály (nový HR director, hiring, negativní recenze)

Usage:
  python3 scripts/signal_scanner.py                # scan top 10 priority deals
  python3 scripts/signal_scanner.py --deal 360     # specific deal
  python3 scripts/signal_scanner.py --all           # scan all open deals
  python3 scripts/signal_scanner.py --list          # show cached signals
"""

import json
import sys
import re
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.paths import WORKSPACE, LOGS_DIR
from lib.secrets import load_secrets
from lib.notifications import notify_telegram
from lib.pipedrive import pipedrive_api

LOG_FILE = LOGS_DIR / "signal-scanner.log"
SIGNALS_DIR = WORKSPACE / "knowledge" / "signals"


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")



def web_search(query, num_results=5):
    """Search web via DuckDuckGo HTML (no API key needed)."""
    try:
        encoded = urllib.parse.quote(query)
        url = f"https://html.duckduckgo.com/html/?q={encoded}"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)")
        with urllib.request.urlopen(req, timeout=10) as r:
            html = r.read().decode("utf-8", errors="ignore")

        # Extract results
        results = []
        # Find result links and snippets
        link_pattern = re.compile(r'<a rel="nofollow" class="result__a" href="([^"]+)"[^>]*>(.+?)</a>')
        snippet_pattern = re.compile(r'<a class="result__snippet"[^>]*>(.+?)</a>', re.DOTALL)

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        for i, (href, title) in enumerate(links[:num_results]):
            title = re.sub(r'<[^>]+>', '', title).strip()
            snippet = re.sub(r'<[^>]+>', '', snippets[i]).strip() if i < len(snippets) else ""
            # Extract actual URL from DDG redirect
            if "uddg=" in href:
                actual = urllib.parse.unquote(href.split("uddg=")[1].split("&")[0])
            else:
                actual = href
            results.append({
                "title": title,
                "url": actual,
                "snippet": snippet[:200],
            })
        return results
    except Exception as e:
        log(f"Web search error: {e}")
    return []


def scan_atmoskop(company_name):
    """Search Atmoskop.cz for employee reviews."""
    signals = []
    results = web_search(f"site:atmoskop.cz {company_name}")
    for r in results[:3]:
        if "atmoskop" in r["url"].lower():
            signals.append({
                "source": "atmoskop",
                "type": "employee_review",
                "priority": "high",
                "title": r["title"],
                "url": r["url"],
                "snippet": r["snippet"],
                "relevance": "Zaměstnanecké recenze = pain point pro Echo Pulse",
            })
    return signals


def scan_jobs(company_name):
    """Search jobs.cz for hiring signals."""
    signals = []
    results = web_search(f"site:jobs.cz {company_name}")
    for r in results[:3]:
        title_lower = r["title"].lower()
        # High signal: HR/People/Culture roles
        is_hr = any(w in title_lower for w in [
            "hr ", "human resources", "people", "personalist",
            "culture", "engagement", "employer brand",
        ])
        signals.append({
            "source": "jobs.cz",
            "type": "hiring_hr" if is_hr else "hiring_general",
            "priority": "high" if is_hr else "medium",
            "title": r["title"],
            "url": r["url"],
            "snippet": r["snippet"],
            "relevance": "Hledají HR/People roli = investují do lidí" if is_hr else "Hiring = růst = kulturní výzvy",
        })
    return signals


def scan_funding_news(company_name):
    """Search for funding, acquisition, or growth news."""
    signals = []
    results = web_search(f"{company_name} investice OR funding OR akvizice OR růst 2025 2026")
    for r in results[:3]:
        snippet_lower = r["snippet"].lower()
        is_funding = any(w in snippet_lower for w in [
            "investic", "funding", "akvizic", "milion", "růst",
            "expanz", "série", "round",
        ])
        if is_funding:
            signals.append({
                "source": "news",
                "type": "funding_growth",
                "priority": "high",
                "title": r["title"],
                "url": r["url"],
                "snippet": r["snippet"],
                "relevance": "Investice/růst = budget na nové nástroje",
            })
    return signals


def scan_linkedin_changes(company_name):
    """Search for leadership changes via web."""
    signals = []
    results = web_search(f"{company_name} nový ředitel OR CEO OR HR director OR people lead 2025 2026")
    for r in results[:3]:
        snippet_lower = r["snippet"].lower()
        is_leadership = any(w in snippet_lower for w in [
            "ředitel", "ceo", "cfo", "cto", "hr director",
            "people", "nástup", "jmenován", "nastupuje",
        ])
        if is_leadership:
            signals.append({
                "source": "linkedin/web",
                "type": "leadership_change",
                "priority": "high",
                "title": r["title"],
                "url": r["url"],
                "snippet": r["snippet"],
                "relevance": "Nový leader = nové priority = window of opportunity",
            })
    return signals


def scan_company_web(company_name):
    """Search for general company info and recent news."""
    signals = []
    results = web_search(f"{company_name} zaměstnanci OR tým OR kultura OR spokojenost")
    for r in results[:2]:
        signals.append({
            "source": "web",
            "type": "company_info",
            "priority": "low",
            "title": r["title"],
            "url": r["url"],
            "snippet": r["snippet"],
            "relevance": "Obecné info o firmě",
        })
    return signals


def scan_deal_signals(deal, token):
    """Run all signal scanners for a deal."""
    org = deal.get("org_name", "") or deal.get("title", "")
    if not org or len(org) < 3:
        return []

    # Clean org name for search
    org_clean = org.replace("s.r.o.", "").replace("a.s.", "").replace(",", "").strip()

    log(f"  Scanning signals for: {org_clean}")
    all_signals = []

    # Run all scanners
    all_signals.extend(scan_atmoskop(org_clean))
    all_signals.extend(scan_jobs(org_clean))
    all_signals.extend(scan_funding_news(org_clean))
    all_signals.extend(scan_linkedin_changes(org_clean))
    all_signals.extend(scan_company_web(org_clean))

    # Deduplicate by URL
    seen_urls = set()
    unique = []
    for s in all_signals:
        if s["url"] not in seen_urls:
            seen_urls.add(s["url"])
            unique.append(s)

    return unique


def save_signals(deal_id, org, signals):
    """Save signals to knowledge base."""
    SIGNALS_DIR.mkdir(parents=True, exist_ok=True)
    fpath = SIGNALS_DIR / f"deal_{deal_id}.json"

    data = {
        "deal_id": deal_id,
        "org": org,
        "scanned_at": datetime.now().isoformat(),
        "signals": signals,
        "signal_count": len(signals),
        "high_priority": sum(1 for s in signals if s["priority"] == "high"),
    }

    fpath.write_text(json.dumps(data, ensure_ascii=False, indent=2))
    return fpath


def format_signal_report(all_results):
    """Format signal scan results."""
    lines = []
    lines.append("# Signal Intelligence Report")
    lines.append(f"_{datetime.now().strftime('%d.%m.%Y %H:%M')}_\n")

    hot_deals = [r for r in all_results if r["high_priority"] > 0]
    lines.append(f"🔥 **{len(hot_deals)} dealů s hot signály** z {len(all_results)} skenovaných\n")

    for r in sorted(all_results, key=lambda x: x["high_priority"], reverse=True):
        if not r["signals"]:
            continue

        emoji = "🔴" if r["high_priority"] >= 2 else "🟡" if r["high_priority"] == 1 else "🟢"
        lines.append(f"\n### {emoji} {r['org']} (deal {r['deal_id']})")
        lines.append(f"_{r['signal_count']} signálů, {r['high_priority']} high priority_\n")

        for s in sorted(r["signals"], key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["priority"]]):
            p_emoji = "🔴" if s["priority"] == "high" else "🟡" if s["priority"] == "medium" else "🟢"
            lines.append(f"- {p_emoji} **{s['type']}**: {s['title'][:60]}")
            lines.append(f"  _{s['relevance']}_")
            if s["snippet"]:
                lines.append(f"  > {s['snippet'][:120]}")

    return "\n".join(lines)


def main():
    secrets = load_secrets()
    token = secrets.get("PIPEDRIVE_API_TOKEN") or secrets.get("PIPEDRIVE_TOKEN")
    if not token:
        token = "8a21711bcee8c0a34e7cfeefbeba2e554444d5d0"

    list_mode = "--list" in sys.argv
    scan_all = "--all" in sys.argv
    specific_deal = None
    for i, arg in enumerate(sys.argv):
        if arg == "--deal" and i + 1 < len(sys.argv):
            specific_deal = int(sys.argv[i + 1])

    # List cached signals
    if list_mode:
        if SIGNALS_DIR.exists():
            for f in sorted(SIGNALS_DIR.glob("deal_*.json")):
                data = json.loads(f.read_text())
                emoji = "🔴" if data["high_priority"] >= 2 else "🟡" if data["high_priority"] >= 1 else "⚪"
                print(f"  {emoji} deal {data['deal_id']:4d} | {data['org'][:25]:25s} | {data['signal_count']} signals ({data['high_priority']} high) | {data['scanned_at'][:10]}")
        else:
            print("  Žádné cached signály. Spusť scan.")
        return 0

    # Fetch deals
    log("Fetching deals...")
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

    if specific_deal:
        deals = [d for d in deals if d["id"] == specific_deal]

    if not scan_all and not specific_deal:
        # Only scan top 10 by stage (highest priority)
        deals.sort(key=lambda d: d.get("stage_order_nr", 0), reverse=True)
        deals = deals[:10]

    log(f"Scanning {len(deals)} deals for signals...")

    all_results = []
    hot_signals = 0

    for deal in deals:
        did = deal["id"]
        org = deal.get("org_name", "") or deal.get("title", "")

        signals = scan_deal_signals(deal, token)
        high = sum(1 for s in signals if s["priority"] == "high")

        result = {
            "deal_id": did,
            "org": org,
            "signals": signals,
            "signal_count": len(signals),
            "high_priority": high,
        }
        all_results.append(result)

        if signals:
            save_signals(did, org, signals)
            log(f"  {org}: {len(signals)} signals ({high} high)")
            hot_signals += high
        else:
            log(f"  {org}: no signals found")

    # Report
    report = format_signal_report(all_results)
    print(report)

    # Save report
    report_dir = WORKSPACE / "reports" / "signals"
    report_dir.mkdir(parents=True, exist_ok=True)
    report_file = report_dir / f"signals_{datetime.now().strftime('%Y-%m-%d')}.md"
    report_file.write_text(report)
    log(f"Report saved: {report_file}")

    # Telegram if hot signals
    if hot_signals > 0:
        notify_telegram(
            f"🔥 Signal Scanner: {hot_signals} hot signálů nalezeno\n"
            f"Skenováno {len(deals)} dealů\n"
            f"📂 Detail: reports/signals/"
        )

    return 0


if __name__ == "__main__":
    exit(main())
