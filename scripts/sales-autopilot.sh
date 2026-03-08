#!/bin/bash
# Sales Autopilot — runs every 4 hours during workday
# Checks pipeline, generates follow-ups, updates CRM state
# Uses Ollama for classification, Claude scheduled tasks for heavy lifting

set -e
cd /Users/josefhofman/Clawdia

DATE=$(date +%Y-%m-%d)
HOUR=$(date +%H)
LOG="logs/sales-autopilot.log"

echo "[$DATE $HOUR:00] Sales autopilot cycle starting..." >> "$LOG"

# 1. Run pipeline hygiene check
if [ -f "scripts/pipedrive_open_deal_activity_guard.py" ]; then
    python3 scripts/pipedrive_open_deal_activity_guard.py >> "$LOG" 2>&1 || true
fi

# 2. Run lead scoring
if [ -f "scripts/pipedrive_lead_scorer.py" ]; then
    python3 scripts/pipedrive_lead_scorer.py >> "$LOG" 2>&1 || true
fi

# 3. Check for stale deals needing follow-up
python3 << 'PYTHON' 2>/dev/null || true
import json, os
from datetime import datetime, timedelta

deals_file = "pipedrive/pipedrive_deals_compact.json"
if not os.path.exists(deals_file):
    print("No deals file found")
    exit(0)

# Parse multi-object JSON file (objects separated by whitespace)
import re
deals = []
try:
    with open(deals_file) as f:
        content = f.read().strip()
    if not content:
        print("Deals file is empty")
        exit(0)
    # Normalize: always wrap in array
    # Handle multi-object JSON: {}{} or {} {} or {}\n{}
    normalized = re.sub(r'}\s*{', '},{', content)
    if not normalized.startswith('['):
        normalized = '[' + normalized + ']'
    deals = json.loads(normalized)
    if not isinstance(deals, list):
        deals = [deals]
except json.JSONDecodeError as e:
    # Fallback: try line-by-line parsing (NDJSON)
    try:
        with open(deals_file) as f:
            deals = [json.loads(line) for line in f if line.strip()]
    except Exception:
        print(f"Parse error (all methods failed): {e}")
        exit(0)
except Exception as e:
    print(f"Parse error: {e}")
    exit(0)

print(f"Loaded {len(deals)} deals")

# Find deals without next activity (stale)
stale = []
for deal in deals:
    if deal.get("status") != "open":
        continue
    next_act = deal.get("next_activity_date")
    if not next_act:
        stale.append({
            "title": deal.get("title", "Unknown"),
            "org": deal.get("org_name", "?"),
            "value": deal.get("value", 0),
            "reason": "no next activity scheduled"
        })

if stale:
    stale.sort(key=lambda x: x["value"] or 0, reverse=True)
    output = f"# Deals Without Next Activity ({datetime.now().strftime('%Y-%m-%d')})\n\n"
    output += f"**{len(stale)} deals** need attention:\n\n"
    for d in stale[:15]:
        val = f"{d['value']:,} CZK" if d['value'] else "no value"
        output += f"- **{d['title']}** ({d['org']}) — {val}\n"

    with open("pipedrive/STALE_DEALS.md", "w") as f:
        f.write(output)
    print(f"Found {len(stale)} deals without next activity")
else:
    print("All deals have next activities scheduled")
PYTHON

# 4. Generate follow-up suggestions using Ollama
if [ -f "pipedrive/STALE_DEALS.md" ]; then
    STALE=$(cat pipedrive/STALE_DEALS.md | head -20)
    if [ -n "$STALE" ]; then
        SUGGESTIONS=$(./scripts/ollama-router.sh adhd-focus "You have stale deals: $STALE. What's the most important follow-up to send right now?" 2>/dev/null)
        echo -e "\n## Doporučení\n$SUGGESTIONS" >> pipedrive/STALE_DEALS.md
    fi
fi

# 5. Update execution state timestamp
python3 << 'PYTHON' 2>/dev/null || true
import json, os
from datetime import datetime

state_file = "knowledge/EXECUTION_STATE.json"
if os.path.exists(state_file):
    with open(state_file) as f:
        state = json.load(f)
    state["last_autopilot_run"] = datetime.now().isoformat()
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
PYTHON

echo "[$DATE $HOUR:00] Sales autopilot cycle complete" >> "$LOG"
echo "Sales autopilot complete. Check pipedrive/STALE_DEALS.md"
