#!/bin/bash
# Morning Command Center v2
# Comprehensive daily dashboard: deals, calendar, inbox, agents, scorecard, focus tip
# Runs at 7-8 AM — the ONE document Josef reads to start his day

set -e
cd /Users/josefhofman/Clawdia

DATE=$(date +%Y-%m-%d)
DAY=$(date +%A)
TIME=$(date +%H:%M)
DIGEST_FILE="knowledge/USER_DIGEST_AM.md"

echo "[$DATE $TIME] Morning command center starting..." >> logs/orchestrator.log

# 1. Calendar
CAL=""
[ -f "calendar/TODAY.md" ] && CAL=$(head -20 calendar/TODAY.md 2>/dev/null)

# 2. Pipeline summary + priority calls
PIPELINE=""
[ -f "pipedrive/PIPELINE_STATUS.md" ] && PIPELINE=$(head -30 pipedrive/PIPELINE_STATUS.md 2>/dev/null)

PRIORITY_CALLS=""
if [ -f "pipedrive/DEAL_SCORING.md" ]; then
    PRIORITY_CALLS=$(python3 << 'PY' 2>/dev/null
with open("pipedrive/DEAL_SCORING.md") as f:
    lines = f.readlines()
in_calls = False
out = []
for line in lines:
    if "TODAY'S PRIORITY CALLS" in line:
        in_calls = True
        continue
    if in_calls:
        if line.startswith("##"):
            break
        if line.strip() and not line.startswith("|---"):
            out.append(line.rstrip())
if out:
    print("\n".join(out[:12]))
else:
    print("_Žádné prioritní hovory_")
PY
)
fi

# 3. Stale deals needing action
STALE_COUNT=0
STALE_TOP=""
if [ -f "pipedrive/STALE_DEALS.md" ]; then
    STALE_COUNT=$(grep -c "^\-" pipedrive/STALE_DEALS.md 2>/dev/null || echo "0")
    STALE_TOP=$(head -10 pipedrive/STALE_DEALS.md 2>/dev/null | grep "^\-" | head -5)
fi

# 4. Approval queue
PENDING_COUNT=$(ls -1 approval-queue/pending/ 2>/dev/null | wc -l | tr -d ' ')
PENDING_LIST=$(ls -1 approval-queue/pending/ 2>/dev/null | head -5 | while read f; do echo "- $f"; done)

# 5. Inbox
INBOX=""
[ -f "inbox/INBOX_DIGEST.md" ] && INBOX=$(head -15 inbox/INBOX_DIGEST.md 2>/dev/null)

# 6. Agent health
AGENT_HEALTH=$(python3 << 'PY' 2>/dev/null
import time
from pathlib import Path
base = Path("/Users/josefhofman/Clawdia")
checks = [
    ("knowledge/USER_DIGEST_AM.md", "spojka", 24),
    ("pipedrive/PIPELINE_STATUS.md", "obchodak", 48),
    ("inbox/INBOX_DIGEST.md", "postak", 24),
    ("intel/DAILY-INTEL.md", "strateg", 48),
    ("calendar/TODAY.md", "kalendar", 24),
    ("reviews/SYSTEM_HEALTH.md", "kontrolor", 72),
    ("knowledge/IMPROVEMENTS.md", "archivar", 72),
]
now = time.time()
ok = 0
total = len(checks)
problems = []
for path, agent, max_h in checks:
    p = base / path
    if not p.exists() or p.stat().st_size < 50:
        problems.append(f"- {agent}: chybí výstup")
        continue
    age = (now - p.stat().st_mtime) / 3600
    if age > max_h:
        problems.append(f"- {agent}: zastaralý ({int(age)}h)")
    else:
        ok += 1
print(f"**{ok}/{total} agentů v pořádku**")
if problems:
    print("\n".join(problems))
PY
)

# 7. Scorecard summary
SCORE=""
if [ -f "reviews/daily-scorecard/score_state.json" ]; then
    SCORE=$(python3 << 'PY' 2>/dev/null
import json
from datetime import date, timedelta
with open("reviews/daily-scorecard/score_state.json") as f:
    s = json.load(f)
yesterday = (date.today() - timedelta(days=1)).isoformat()
y_pts = s.get("daily_scores", {}).get(yesterday, 0)
total = s.get("total_points", 0)
streak = s.get("current_streak", 0)
title = s.get("title", "?")
fire = "🔥" * min(streak, 5) if streak > 0 else ""
print(f"**{title}** | {total:,} bodů | Streak: {streak}d {fire}")
if y_pts > 0:
    print(f"Včera: {y_pts} bodů")
PY
)
fi

# 8. Active tasks
TASKS=$(python3 << 'PY' 2>/dev/null
import json
try:
    with open("knowledge/EXECUTION_STATE.json") as f:
        state = json.load(f)
    tasks = state.get("tasks", [])
    active = [t for t in tasks if t.get("status") in ("todo", "in_progress")]
    for t in active[:5]:
        p = t.get("priority", "?")
        s = {"todo": "○", "in_progress": "◐"}.get(t.get("status"), "?")
        summary = t.get("user_summary", t.get("title", "?"))
        print(f"  {s} [{p}] {summary}")
    if not active:
        print("  Žádné aktivní tasky")
except:
    print("  Stav nedostupný")
PY
)

# 9. Workflows in progress
WORKFLOWS=$(python3 << 'PY' 2>/dev/null
import json
from pathlib import Path
runs_dir = Path("/Users/josefhofman/Clawdia/workflows/runs")
if runs_dir.exists():
    runs = list(runs_dir.glob("*.json"))
    if runs:
        for f in runs[:3]:
            r = json.loads(f.read_text())
            total = len(r.get("step_states", {}))
            done = sum(1 for s in r.get("step_states", {}).values() if s.get("status") in ("completed", "skipped"))
            print(f"  [{r.get('workflow_name','?')}] {done}/{total} kroků")
    else:
        print("  Žádné aktivní workflow")
else:
    print("  Workflow engine připraven")
PY
)

# 10. Bus messages
BUS_STATUS=$(python3 << 'PY' 2>/dev/null
from pathlib import Path
base = Path("/Users/josefhofman/Clawdia/bus")
outbox = len(list((base / "outbox").glob("*.json"))) if (base / "outbox").exists() else 0
inbox_total = 0
if (base / "inbox").exists():
    for agent_dir in (base / "inbox").iterdir():
        if agent_dir.is_dir():
            inbox_total += len(list(agent_dir.glob("*.json")))
if outbox or inbox_total:
    print(f"  {outbox} ve frontě, {inbox_total} v inboxech agentů")
else:
    print("  Vše doručeno")
PY
)

# 11. ADHD focus tip from Ollama
FOCUS=$(./scripts/ollama-router.sh adhd-focus "It's $DAY morning. Priority calls: $(echo "$PRIORITY_CALLS" | head -3). Stale deals: $STALE_COUNT. Pending approvals: $PENDING_COUNT. Keep it to 2 sentences in Czech. What should Josef focus on RIGHT NOW?" 2>/dev/null || echo "Zaměř se na svůj top deal. Jeden hovor = jeden krok vpřed.")

# Generate the command center
cat > "$DIGEST_FILE" << DIGEST
# Velitelské centrum — $DAY, $DATE

## 🎯 FOCUS
$FOCUS

## 📞 Prioritní hovory
$PRIORITY_CALLS

## 📊 Pipeline
$PIPELINE

## ⚠️ Stále dealy ($STALE_COUNT bez další aktivity)
$STALE_TOP

## ✅ Ke schválení ($PENDING_COUNT)
$PENDING_LIST

## 📬 Inbox
${INBOX:-_Inbox digest není k dispozici_}

## 📅 Kalendář
${CAL:-_Žádné události_}

## 🤖 Agenti
$AGENT_HEALTH

## 📋 Aktivní tasky
$TASKS

## 🔄 Workflow
$WORKFLOWS

## 📨 Agent Bus
$BUS_STATUS

## 🏆 Scorecard
$SCORE

---
*Vygenerováno: $TIME | Command Center v2*
DIGEST

echo "[$DATE $TIME] Morning command center ready: $DIGEST_FILE" >> logs/orchestrator.log
echo "Command center ready: $DIGEST_FILE"
