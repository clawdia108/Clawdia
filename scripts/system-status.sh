#!/bin/bash
# Clawdia System Dashboard v2 — comprehensive real-time status
cd /Users/josefhofman/Clawdia

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[0;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; DIM='\033[2m'; NC='\033[0m'

echo ""
echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${BOLD}${CYAN}║            CLAWDIA COMMAND CENTER v2                     ║${NC}"
echo -e "${BOLD}${CYAN}║            $(date '+%Y-%m-%d %H:%M:%S')                          ║${NC}"
echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

echo -e "${BOLD}▸ SYSTEM SERVICES${NC}"
if launchctl list 2>/dev/null | grep -q "com.clawdia.orchestrator"; then
    PID=$(launchctl list 2>/dev/null | grep orchestrator | awk '{print $1}')
    echo -e "  ${GREEN}●${NC} Orchestrator ${DIM}(PID: $PID)${NC}"
else
    echo -e "  ${RED}●${NC} Orchestrator ${RED}NOT RUNNING${NC}"
fi
if launchctl list 2>/dev/null | grep -q "com.clawdia.heartbeat"; then
    echo -e "  ${GREEN}●${NC} Heartbeat ${DIM}(hourly)${NC}"
else
    echo -e "  ${RED}●${NC} Heartbeat ${RED}NOT LOADED${NC}"
fi
if curl -s -m 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
    MODEL=$(curl -s http://localhost:11434/api/tags 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(', '.join(m['name'] for m in d.get('models',[])))" 2>/dev/null)
    echo -e "  ${GREEN}●${NC} Ollama ${DIM}($MODEL)${NC}"
else
    echo -e "  ${RED}●${NC} Ollama ${RED}OFFLINE${NC}"
fi
echo ""

echo -e "${BOLD}▸ AGENT HEALTH${NC}"
python3 << 'PY' 2>/dev/null
from scripts.lib.agent_health import AGENT_OUTPUTS, collect_agent_health

NC = "\033[0m"
RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
BOLD = "\033[1m"
DIM = "\033[2m"

health = collect_agent_health()
for agent in AGENT_OUTPUTS:
    info = health.get(agent, {})
    status = info.get("status", "DEAD")
    color = {"OK": GREEN, "STALE": RED, "EMPTY": YELLOW, "DEAD": RED}.get(status, YELLOW)
    age = info.get("age_hours")
    source = info.get("source", "unknown")
    reason = info.get("reason", "")
    detail = f"{age}h via {source}" if age is not None else reason
    print(f"  {color}●{NC} {BOLD}{agent:<15}{NC} {color}{status}{NC} {DIM}({detail}){NC}")
PY
echo ""

echo -e "${BOLD}▸ TASK QUEUE${NC}"
if [ -f "knowledge/EXECUTION_STATE.json" ]; then
    python3 << 'PY' 2>/dev/null
import json
with open("knowledge/EXECUTION_STATE.json") as f:
    state = json.load(f)
counts = state.get("counts", {})
tasks = state.get("tasks", [])
print(f"  Open: {counts.get('open', '?')} | Blocked: {counts.get('blocked', '?')} | Done: {counts.get('done', '?')}")
for t in tasks[:5]:
    si = {"todo": "○", "in_progress": "◐", "blocked": "⊘", "done": "●"}.get(t.get("status",""), "?")
    p = t.get("priority", "P3")
    pc = {"P0": "\033[0;31m", "P1": "\033[0;33m", "P2": "\033[0;34m"}.get(p, "\033[2m")
    print(f"  {si} {pc}{p}\033[0m {t.get('title','?')[:50]} \033[2m→ {t.get('owner','?')}\033[0m")
PY
else
    echo -e "  ${DIM}No execution state${NC}"
fi
echo ""

echo -e "${BOLD}▸ APPROVAL QUEUE${NC}"
P=$(ls approval-queue/pending/ 2>/dev/null | wc -l | tr -d ' ')
A=$(ls approval-queue/approved/ 2>/dev/null | wc -l | tr -d ' ')
echo -e "  Pending: ${BOLD}$P${NC} | Approved: $A"
echo ""

echo -e "${BOLD}▸ SALES PIPELINE${NC}"
if [ -f "pipedrive/DEAL_SCORING.md" ]; then
    python3 << 'PY' 2>/dev/null
with open("pipedrive/DEAL_SCORING.md") as f:
    content = f.read()
for line in content.split("\n"):
    if any(line.startswith(f"- {p}") for p in ["**Total", "🔥", "🟡", "🔵", "⚪", "**Sales"]):
        print(f"  {line.strip('- ')}")
PY
fi
if [ -f "pipedrive/STALE_DEALS.md" ]; then
    STALE=$(grep -c "^\-" pipedrive/STALE_DEALS.md 2>/dev/null || echo "0")
    [ "$STALE" -gt 0 ] && echo -e "  ${YELLOW}⚠${NC}  ${STALE} deals without next activity"
fi
echo ""

echo -e "${BOLD}▸ SCORECARD${NC}"
if [ -f "reviews/daily-scorecard/score_state.json" ]; then
    python3 << 'PY' 2>/dev/null
import json
from datetime import date
with open("reviews/daily-scorecard/score_state.json") as f:
    s = json.load(f)
today_pts = s.get("daily_scores", {}).get(str(date.today()), 0)
total = s.get("total_points", 0)
streak = s.get("current_streak", 0)
title = s.get("title", "?")
bar = "█" * (min(today_pts, 100) // 5) + "░" * ((100 - min(today_pts, 100)) // 5)
fire = "🔥" * min(streak, 5) if streak > 0 else ""
print(f"  Today: {today_pts} pts [{bar}]")
print(f"  Total: {total:,} | Streak: {streak}d {fire} | {title}")
PY
fi
echo ""

echo -e "${BOLD}▸ COSTS${NC}"
if [ -f "logs/cost-tracker.json" ]; then
    python3 << 'PY' 2>/dev/null
import json
from datetime import date
with open("logs/cost-tracker.json") as f:
    d = json.load(f)
t = d.get("daily", {}).get(date.today().isoformat(), 0)
print(f"  Today: \${t:.4f} | Total: \${d.get('total', 0):.4f}")
PY
else
    echo -e "  ${DIM}No cost data${NC}"
fi
echo ""

echo -e "${BOLD}▸ CIRCUITS${NC}"
if [ -f "logs/circuit-breaker.json" ]; then
    python3 << 'PY' 2>/dev/null
import json
with open("logs/circuit-breaker.json") as f:
    d = json.load(f)
if not d:
    print("  All OK")
else:
    for k, v in d.items():
        s = "\033[0;31m● OPEN\033[0m" if v.get("open") else ("\033[0;33m●\033[0m" if v.get("failures",0) > 0 else "\033[0;32m●\033[0m")
        print(f"  {s} {k}: {v.get('failures',0)} failures")
PY
else
    echo -e "  ${GREEN}All circuits OK${NC}"
fi
echo ""

echo -e "${BOLD}▸ TRIGGERS${NC}"
OUT=$(ls triggers/outbox/ 2>/dev/null | wc -l | tr -d ' ')
PROC=$(ls triggers/processed/ 2>/dev/null | wc -l | tr -d ' ')
echo -e "  Pending: $OUT | Processed: $PROC"
echo ""

echo -e "${BOLD}▸ RECENT EVENTS${NC}"
if [ -f "logs/events.jsonl" ]; then
    tail -5 logs/events.jsonl 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        e = json.loads(line.strip())
        ts = e.get('ts','?')[:16]
        t = e.get('type','?')
        x = {k:v for k,v in e.items() if k not in ('ts','type')}
        xs = json.dumps(x) if x else ''
        if len(xs)>60: xs = xs[:60]+'...'
        print(f'  \033[2m{ts}\033[0m {t} {xs}')
    except: pass
" 2>/dev/null
else
    echo -e "  ${DIM}No events yet${NC}"
fi
echo ""

echo -e "${BOLD}▸ ORCHESTRATOR LOG (last 3)${NC}"
[ -f "logs/orchestrator.log" ] && tail -3 logs/orchestrator.log | while read line; do echo -e "  ${DIM}$line${NC}"; done
echo ""
echo -e "${CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
