#!/usr/bin/env python3
"""
Sales Coach — post-call coaching agent for Josef.
=====================================================
Analyzes Fathom call recordings and provides actionable coaching feedback.
Runs automatically after fathom_sync detects new calls.

Coaching areas:
1. Talk/Listen ratio — should be <40% talk
2. SPIN question usage — track S/P/I/N distribution
3. Objection handling — did he address or dodge?
4. Next steps quality — concrete vs vague
5. Opening/closing technique
6. Czech sales language quality
7. Deal advancement — did the deal move forward?

Usage:
    python3 scripts/sales_coach.py                  # coach last call
    python3 scripts/sales_coach.py --deal 360       # coach specific deal
    python3 scripts/sales_coach.py --all            # coach all un-coached calls
    python3 scripts/sales_coach.py --weekly         # weekly coaching summary
    python3 scripts/sales_coach.py --trends         # show improvement trends
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.paths import WORKSPACE, LOGS_DIR
from lib.secrets import load_secrets
from lib.notifications import notify_telegram
from lib.pipedrive import pipedrive_api, pipedrive_get_all, fathom_api

COACHING_DIR = WORKSPACE / "knowledge" / "coaching"
COACHING_LOG = COACHING_DIR / "coaching_history.json"
TRENDS_FILE = COACHING_DIR / "coaching_trends.json"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}")


def load_coaching_history():
    if COACHING_LOG.exists():
        try:
            return json.loads(COACHING_LOG.read_text())
        except Exception:
            pass
    return {"sessions": [], "coached_recordings": []}


def save_coaching_history(history):
    COACHING_DIR.mkdir(parents=True, exist_ok=True)
    COACHING_LOG.write_text(json.dumps(history, indent=2, ensure_ascii=False))


def get_recent_calls(fathom_key, days=7):
    """Get recent Fathom recordings."""
    created_after = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    meetings = []
    cursor = None

    while True:
        params = {
            "include_summary": "true",
            "include_action_items": "true",
        }
        if created_after:
            params["created_after"] = created_after
        if cursor:
            params["cursor"] = cursor

        result = fathom_api(fathom_key, "/meetings", params)
        if not result:
            break

        batch = result.get("meetings", [])
        if not batch:
            break
        meetings.extend(batch)

        cursor = result.get("cursor")
        if not cursor:
            break

    return meetings


def get_transcript(fathom_key, recording_id):
    """Get transcript for a specific recording."""
    result = fathom_api(fathom_key, f"/recordings/{recording_id}/transcript")
    if result:
        return result.get("segments", [])
    return []


def analyze_talk_ratio(transcript):
    """Calculate talk/listen ratio from transcript segments."""
    josef_words = 0
    other_words = 0

    for seg in transcript:
        speaker = seg.get("speaker", {})
        name = (speaker.get("display_name") or speaker.get("name") or "").lower()
        text = seg.get("text", "")
        word_count = len(text.split())

        if "josef" in name or "hofman" in name or "behavera" in name:
            josef_words += word_count
        else:
            other_words += word_count

    total = josef_words + other_words
    if total == 0:
        return {"ratio": 0, "josef_pct": 0, "verdict": "no data"}

    josef_pct = round(josef_words / total * 100, 1)

    if josef_pct < 30:
        verdict = "VYNIKAJÍCÍ — hodně nasloucháš"
    elif josef_pct < 40:
        verdict = "DOBRÉ — ideální poměr"
    elif josef_pct < 50:
        verdict = "OK — zkus víc naslouchat"
    elif josef_pct < 60:
        verdict = "POZOR — moc mluvíš, nech klienta"
    else:
        verdict = "ŠPATNÉ — mluvíš víc než klient, otoč to"

    return {
        "ratio": round(josef_pct, 1),
        "josef_words": josef_words,
        "other_words": other_words,
        "verdict": verdict,
    }


def generate_coaching(meeting, transcript, deal, secrets):
    """Generate coaching feedback using Claude."""
    title = meeting.get("title") or meeting.get("meeting_title") or ""
    created = meeting.get("created_at", "")[:10]
    recording_id = meeting.get("recording_id", "")

    # Duration
    start = meeting.get("recording_start_time", "")
    end = meeting.get("recording_end_time", "")
    duration_min = ""
    if start and end:
        try:
            s = datetime.fromisoformat(start.replace("Z", "+00:00"))
            e = datetime.fromisoformat(end.replace("Z", "+00:00"))
            duration_min = f"{(e - s).seconds // 60}"
        except (ValueError, TypeError):
            pass

    deal_title = deal.get("title", "") if deal else ""
    org_name = deal.get("org_name", "") if deal else ""
    person_name = deal.get("person_name", "") if deal else ""

    # Talk ratio analysis
    talk_data = analyze_talk_ratio(transcript)

    # Fathom summary
    fathom_summary = ""
    default_summary = meeting.get("default_summary")
    if default_summary and default_summary.get("markdown_formatted"):
        fathom_summary = default_summary['markdown_formatted'][:1500]

    # Action items
    action_items = ""
    items = meeting.get("action_items", [])
    if items:
        action_items = "\n".join(f"- {a.get('text', '')}" for a in items[:10])

    # Transcript text
    transcript_text = "\n".join(
        f"[{s.get('timestamp', '')}] {s.get('speaker', {}).get('display_name', '?')}: {s.get('text', '')}"
        for s in transcript[:80]
    )

    prompt = f"""Jsi osobní sales coach pro Josefa Hofmana, zakladatele Behavera.
Josef prodává Echo Pulse — platformu pro měření spokojenosti zaměstnanců (99-129 CZK/osoba/měsíc).
Cílí na české firmy 50-500 zaměstnanců, mluví s CEO a HR řediteli.

ÚKOL: Analyzuj tento hovor a poskytni KONKRÉTNÍ, AKČNÍ coaching feedback.
Buď přímý, upřímný ale povzbudivý. Josef má ADHD — krátké body, jasné akce.

HOVOR:
- Meeting: {title}
- Datum: {created} | Délka: {duration_min} min
- Deal: {deal_title} | Firma: {org_name} | Kontakt: {person_name}
- Talk ratio: Josef {talk_data['ratio']}% | Klient {100 - talk_data['ratio']}%

FATHOM SUMMARY:
{fathom_summary}

ACTION ITEMS:
{action_items}

TRANSCRIPT:
{transcript_text[:6000]}

---

Vygeneruj coaching report v PŘESNĚ tomto formátu:

## 🏋️ Sales Coaching — {person_name or org_name or title}

### 📊 Skóre hovoru
| Oblast | Skóre (1-10) | Komentář |
|--------|-------------|----------|
| Talk/Listen ratio | X/10 | {talk_data['verdict']} |
| SPIN otázky | X/10 | [kolik S/P/I/N otázek zaznělo] |
| Objection handling | X/10 | [jak reagoval na námitky] |
| Next steps | X/10 | [konkrétní vs vágní dohodnutí] |
| Opening | X/10 | [jak zahájil hovor] |
| Closing | X/10 | [jak ukončil, CTA] |
| Celkový dojem | X/10 | [overall] |

**Celkové skóre: XX/70**

### ✅ Co fungovalo skvěle (1-3 body)
[Konkrétní momenty z hovoru kde Josef exceloval — s citacemi]

### ⚠️ Co zlepšit (1-3 body)
[Konkrétní, akční rady — ne obecné fráze. Cituj momenty kde to šlo líp]

### 🎯 Klíčový tip na příště
[JEDEN nejdůležitější tip pro příští hovor s tímto klientem]

### 📝 Doporučený follow-up
[Konkrétní návrh follow-up emailu/akce na základě hovoru]

### 🔮 Deal prognóza
[ADVANCE/CONTINUATION/STALL — s pravděpodobností uzavření a proč]

Piš ČESKY. Buď konkrétní — cituj z přepisu. Žádné obecné rady."""

    try:
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        result = subprocess.run(
            ["claude", "-p", "--model", "claude-sonnet-4-6",
             "--dangerously-skip-permissions"],
            input=prompt,
            capture_output=True, text=True, timeout=120,
            env=env,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip(), talk_data
        else:
            log(f"Claude CLI error: rc={result.returncode}")
    except Exception as e:
        log(f"Claude CLI error: {e}")

    return None, talk_data


def extract_score(coaching_text):
    """Try to extract the total score from coaching text."""
    import re
    match = re.search(r'Celkové skóre:\s*(\d+)/70', coaching_text)
    if match:
        return int(match.group(1))
    # Fallback: count X/10 scores
    scores = re.findall(r'\|\s*(\d+)/10', coaching_text)
    if scores:
        return sum(int(s) for s in scores)
    return 0


def save_coaching_session(history, recording_id, deal_id, org_name,
                          score, talk_ratio, coaching_text, date):
    """Save a coaching session to history."""
    session = {
        "recording_id": recording_id,
        "deal_id": deal_id,
        "org_name": org_name,
        "score": score,
        "talk_ratio": talk_ratio,
        "date": date,
        "timestamp": datetime.now().isoformat(),
    }
    history["sessions"].append(session)
    history["coached_recordings"].append(recording_id)

    # Save coaching text to file
    safe_name = org_name.replace("/", "-").replace(" ", "_")[:30] if org_name else recording_id
    coaching_file = COACHING_DIR / f"{date}_{safe_name}.md"
    coaching_file.write_text(coaching_text)
    log(f"Coaching saved: {coaching_file.name}")

    save_coaching_history(history)
    return session


def update_trends(history):
    """Calculate coaching improvement trends."""
    sessions = history.get("sessions", [])
    if len(sessions) < 2:
        return None

    # Last 10 vs previous 10
    recent = sessions[-10:]
    older = sessions[-20:-10] if len(sessions) >= 20 else sessions[:max(1, len(sessions)-10)]

    recent_avg = sum(s.get("score", 0) for s in recent) / len(recent) if recent else 0
    older_avg = sum(s.get("score", 0) for s in older) / len(older) if older else 0
    trend = round(recent_avg - older_avg, 1)

    recent_talk = sum(s.get("talk_ratio", 50) for s in recent) / len(recent) if recent else 50
    older_talk = sum(s.get("talk_ratio", 50) for s in older) / len(older) if older else 50
    talk_trend = round(recent_talk - older_talk, 1)

    trends = {
        "total_sessions": len(sessions),
        "recent_avg_score": round(recent_avg, 1),
        "older_avg_score": round(older_avg, 1),
        "score_trend": trend,
        "score_direction": "📈" if trend > 0 else "📉" if trend < 0 else "➡️",
        "recent_talk_ratio": round(recent_talk, 1),
        "talk_trend": round(talk_trend, 1),
        "talk_direction": "📈" if talk_trend < 0 else "📉" if talk_trend > 0 else "➡️",
        "best_score": max((s.get("score", 0) for s in sessions), default=0),
        "updated_at": datetime.now().isoformat(),
    }

    COACHING_DIR.mkdir(parents=True, exist_ok=True)
    TRENDS_FILE.write_text(json.dumps(trends, indent=2, ensure_ascii=False))
    return trends


def send_coaching_telegram(coaching_text, org_name, score, talk_ratio):
    """Send condensed coaching via Telegram."""
    lines = [
        f"🏋️ *Sales Coaching* — {org_name}",
        f"📊 Skóre: {score}/70 | Talk ratio: {talk_ratio}%",
        "",
    ]

    # Extract key sections
    for section in ["Co fungovalo", "Co zlepšit", "Klíčový tip", "Deal prognóza"]:
        start = coaching_text.find(section)
        if start > 0:
            # Get next 2-3 lines after header
            chunk = coaching_text[start:start+300]
            section_lines = chunk.split("\n")[1:4]
            clean = "\n".join(l.strip() for l in section_lines if l.strip())
            if clean:
                lines.append(f"*{section}:*")
                lines.append(clean[:200])
                lines.append("")

    notify_telegram("\n".join(lines))


def coach_call(meeting, fathom_key, pd_token, secrets, history):
    """Coach a single call."""
    recording_id = meeting.get("recording_id", "")
    title = meeting.get("title") or meeting.get("meeting_title") or ""
    created = meeting.get("created_at", "")[:10]

    log(f"Coaching: {title} ({recording_id})")

    # Get transcript
    transcript = get_transcript(fathom_key, recording_id)
    if not transcript:
        log(f"  No transcript for {recording_id}")
        return None

    # Try to match deal
    deal = None
    invitees = meeting.get("calendar_invitees", [])
    for inv in invitees:
        email = inv.get("email", "")
        if email and "behavera" not in email and "hofman" not in email:
            # Search Pipedrive for this contact
            search_result = pipedrive_api(pd_token, "GET", "/persons/search",
                                          {"term": email, "limit": 1})
            if search_result and search_result.get("items"):
                person_id = search_result["items"][0].get("item", {}).get("id")
                if person_id:
                    deals_result = pipedrive_api(pd_token, "GET",
                                                 f"/persons/{person_id}/deals",
                                                 {"status": "open", "limit": 1})
                    if deals_result:
                        deal_list = deals_result if isinstance(deals_result, list) else deals_result.get("data", [])
                        if deal_list:
                            deal = deal_list[0]
                            break

    # Generate coaching
    coaching_text, talk_data = generate_coaching(meeting, transcript, deal, secrets)
    if not coaching_text:
        log(f"  Coaching generation failed")
        return None

    # Extract score
    score = extract_score(coaching_text)
    org_name = deal.get("org_name", title) if deal else title
    deal_id = deal.get("id") if deal else None

    # Save
    session = save_coaching_session(
        history, recording_id, deal_id, org_name,
        score, talk_data["ratio"], coaching_text, created
    )

    # Send Telegram
    send_coaching_telegram(coaching_text, org_name, score, talk_data["ratio"])

    # Write coaching note to Pipedrive
    if deal and pd_token:
        note_content = (
            f"<h2>🏋️ Sales Coaching — {org_name}</h2>"
            f"<p><b>Skóre:</b> {score}/70 | <b>Talk ratio:</b> {talk_data['ratio']}%</p>"
            f"<hr>"
            f"{coaching_text[:3000].replace(chr(10), '<br>')}"
        )
        pipedrive_api(pd_token, "POST", "/notes", {
            "deal_id": deal["id"],
            "content": note_content,
        })
        log(f"  Coaching note written to deal {deal['id']}")

    # Push to Notion
    try:
        from notion_sync import push_coaching_report
        notion_token = secrets.get("NOTION_TOKEN")
        if notion_token:
            push_coaching_report(
                notion_token, title, org_name, score,
                talk_data["ratio"], 0, coaching_text[:1900],
            )
            log(f"  Coaching pushed to Notion")
    except Exception as e:
        log(f"  Notion push failed: {e}")

    log(f"  Score: {score}/70 | Talk: {talk_data['ratio']}%")
    return session


def show_trends():
    """Show coaching improvement trends."""
    history = load_coaching_history()
    trends = update_trends(history)

    if not trends:
        print("Málo dat pro trendy — potřebuji alespoň 2 coaching sessions.")
        return

    print(f"\n{'='*50}")
    print(f"  SALES COACHING TRENDY")
    print(f"{'='*50}")
    print(f"\n  Celkem sessions: {trends['total_sessions']}")
    print(f"  Průměrné skóre (posledních 10): {trends['recent_avg_score']}/70")
    print(f"  Trend skóre: {trends['score_direction']} {trends['score_trend']:+.1f}")
    print(f"  Talk ratio (posledních 10): {trends['recent_talk_ratio']}%")
    print(f"  Trend talk ratio: {trends['talk_direction']} {trends['talk_trend']:+.1f}%")
    print(f"  Nejlepší skóre: {trends['best_score']}/70")

    sessions = history.get("sessions", [])
    if sessions:
        print(f"\n  Posledních 5 sessions:")
        for s in sessions[-5:]:
            emoji = "🟢" if s.get("score", 0) >= 50 else "🟡" if s.get("score", 0) >= 35 else "🔴"
            print(f"  {emoji} {s.get('date','?'):10s} | {s.get('org_name','?')[:25]:25s} | "
                  f"Skóre: {s.get('score',0)}/70 | Talk: {s.get('talk_ratio',0)}%")

    print()


def weekly_summary():
    """Generate weekly coaching summary."""
    history = load_coaching_history()
    sessions = history.get("sessions", [])

    # Last 7 days
    cutoff = (datetime.now() - timedelta(days=7)).isoformat()
    recent = [s for s in sessions if s.get("timestamp", "") >= cutoff]

    if not recent:
        print("Žádné coaching sessions za poslední týden.")
        return

    avg_score = sum(s.get("score", 0) for s in recent) / len(recent)
    avg_talk = sum(s.get("talk_ratio", 50) for s in recent) / len(recent)
    best = max(recent, key=lambda s: s.get("score", 0))
    worst = min(recent, key=lambda s: s.get("score", 0))

    summary = f"""🏋️ *Týdenní Coaching Summary*

📊 *{len(recent)} hovorů tento týden*
- Průměrné skóre: {avg_score:.0f}/70
- Průměrný talk ratio: {avg_talk:.0f}%
- Nejlepší: {best.get('org_name','?')} ({best.get('score',0)}/70)
- K zlepšení: {worst.get('org_name','?')} ({worst.get('score',0)}/70)

"""

    # Score breakdown
    great = sum(1 for s in recent if s.get("score", 0) >= 50)
    ok = sum(1 for s in recent if 35 <= s.get("score", 0) < 50)
    weak = sum(1 for s in recent if s.get("score", 0) < 35)

    summary += f"🟢 Skvělé: {great} | 🟡 OK: {ok} | 🔴 Slabé: {weak}\n"

    if avg_talk > 50:
        summary += "\n⚠️ *Talk ratio moc vysoký!* Zkus víc naslouchat a klást otázky.\n"
    elif avg_talk < 30:
        summary += "\n✅ *Výborný talk ratio!* Necháváš klienta mluvit — pokračuj.\n"

    notify_telegram(summary)
    print(summary)

    # Save to file
    week_file = COACHING_DIR / f"weekly_{datetime.now().strftime('%Y-W%W')}.md"
    week_file.write_text(summary)
    log(f"Weekly summary saved: {week_file.name}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Sales Coach — post-call coaching")
    parser.add_argument("--deal", type=int, help="Coach specific deal")
    parser.add_argument("--all", action="store_true", help="Coach all un-coached calls")
    parser.add_argument("--weekly", action="store_true", help="Weekly coaching summary")
    parser.add_argument("--trends", action="store_true", help="Show improvement trends")
    parser.add_argument("--days", type=int, default=7, help="Look back N days")
    args = parser.parse_args()

    if args.trends:
        show_trends()
        return 0

    if args.weekly:
        weekly_summary()
        return 0

    secrets = load_secrets()
    pd_token = secrets.get("PIPEDRIVE_API_TOKEN") or secrets.get("PIPEDRIVE_TOKEN")
    fathom_key = secrets.get("FATHOM_API_KEY")

    if not pd_token:
        log("No Pipedrive token")
        return 1
    if not fathom_key:
        log("No Fathom API key")
        return 1

    history = load_coaching_history()
    meetings = get_recent_calls(fathom_key, days=args.days)
    log(f"Found {len(meetings)} meetings in last {args.days} days")

    # Filter to un-coached
    coached_ids = set(history.get("coached_recordings", []))
    uncoached = [m for m in meetings if m.get("recording_id") not in coached_ids]

    if args.deal:
        # Coach specific deal — find meeting for it
        log(f"Looking for meetings matching deal {args.deal}")
        # Get deal details
        deal = pipedrive_api(pd_token, "GET", f"/deals/{args.deal}")
        if deal:
            org_name = deal.get("org_name", "").lower()
            person_name = deal.get("person_name", "").lower()
            # Match by org or person in meeting title/invitees
            for m in meetings:
                title = (m.get("title") or "").lower()
                invitee_names = " ".join(
                    (i.get("name") or "").lower() for i in m.get("calendar_invitees", [])
                )
                if org_name in title or org_name in invitee_names or \
                   person_name in title or person_name in invitee_names:
                    coach_call(m, fathom_key, pd_token, secrets, history)
                    break
            else:
                log(f"No matching meeting found for deal {args.deal}")
        return 0

    if not args.all:
        # Just coach the last uncoached call
        uncoached = uncoached[-1:] if uncoached else []

    if not uncoached:
        log("No un-coached calls found")
        return 0

    coached_count = 0
    for meeting in uncoached:
        session = coach_call(meeting, fathom_key, pd_token, secrets, history)
        if session:
            coached_count += 1

    log(f"Coached {coached_count}/{len(uncoached)} calls")

    # Update trends after coaching
    update_trends(history)

    return 0


if __name__ == "__main__":
    exit(main())
