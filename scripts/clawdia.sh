#!/bin/bash
# Clawdia CLI — Quick-action shortcuts for common operations
# Usage: ./scripts/clawdia.sh <command>

set -e
cd /Users/josefhofman/Clawdia

case "${1:-help}" in
    status|s)
        bash scripts/system-status.sh
        ;;

    score|sc)
        python3 scripts/adhd-scorecard.py
        ;;

    morning|m)
        bash scripts/morning-briefing.sh
        cat knowledge/USER_DIGEST_AM.md
        ;;

    pipeline|p)
        python3 scripts/pipedrive_lead_scorer.py
        ;;

    stale|st)
        cat pipedrive/STALE_DEALS.md 2>/dev/null || echo "No stale deals data"
        ;;

    deals|d)
        head -50 pipedrive/DEAL_SCORING.md 2>/dev/null || echo "No scoring data"
        ;;

    bus|b)
        python3 scripts/agent_bus.py stats
        ;;

    bus-route|br)
        python3 scripts/agent_bus.py route
        ;;

    workflow|w)
        python3 scripts/workflow_engine.py status
        ;;

    workflow-start|ws)
        if [ -z "$2" ]; then
            python3 scripts/workflow_engine.py list
        else
            python3 scripts/workflow_engine.py start "$2"
        fi
        ;;

    agents|a)
        python3 scripts/agent_lifecycle.py states
        ;;

    stuck)
        python3 scripts/agent_lifecycle.py stuck
        ;;

    perf)
        python3 scripts/agent_lifecycle.py perf
        ;;

    reviews|r)
        python3 scripts/agent_bus.py reviews
        ;;

    drafts|dr)
        python3 scripts/draft_generator.py "${2:-3}"
        ;;

    writeback|wb)
        python3 scripts/pipedrive_writeback.py "${@:2}"
        ;;

    heartbeat|hb)
        bash scripts/heartbeat-check.sh
        ;;

    ollama|o)
        if [ -z "$2" ]; then
            curl -s http://localhost:11434/api/tags | python3 -c "import json,sys; d=json.load(sys.stdin); print('\n'.join(m['name'] for m in d.get('models',[])))"
        else
            ./scripts/ollama-router.sh "$2" "${@:3}"
        fi
        ;;

    logs|l)
        tail -20 logs/orchestrator.log 2>/dev/null
        ;;

    events|e)
        tail -20 logs/events.jsonl 2>/dev/null | python3 -c "
import sys, json
for line in sys.stdin:
    try:
        e = json.loads(line.strip())
        ts = e.get('ts','?')[:19]
        t = e.get('type','?')
        print(f'{ts} {t}')
    except: pass
"
        ;;

    costs|c)
        if [ -f "logs/cost-tracker.json" ]; then
            python3 -c "
import json
from datetime import date
with open('logs/cost-tracker.json') as f:
    d = json.load(f)
today = date.today().isoformat()
print(f'Today: \${d.get(\"daily\",{}).get(today,0):.4f}')
print(f'Total: \${d.get(\"total\",0):.4f}')
top = sorted(d.get('by_model',{}).items(), key=lambda x:x[1], reverse=True)[:5]
for m, c in top:
    print(f'  {m}: \${c:.4f}')
"
        else
            echo "No cost data yet"
        fi
        ;;

    collab|co)
        if [ -z "$2" ]; then
            python3 scripts/agent_collaboration.py stats
        else
            python3 scripts/agent_collaboration.py "$2" "${@:3}"
        fi
        ;;

    collab-start|cs)
        python3 scripts/agent_collaboration.py start "${2:-email_campaign}" "${@:3}"
        ;;

    claude-bridge|cb)
        python3 scripts/claude_bridge.py "${2:-status}" "${@:3}"
        ;;

    claude-send|cbs)
        python3 scripts/claude_bridge.py send "${@:2}"
        ;;

    control-plane-check|cpc)
        python3 scripts/check_control_plane.py
        ;;

    tasks|t)
        python3 scripts/task_queue.py list
        ;;

    task-add|ta)
        python3 scripts/task_queue.py add "${@:2}"
        ;;

    dispatch|di)
        python3 scripts/task_queue.py auto
        ;;

    velocity|v)
        python3 scripts/deal_velocity.py velocity
        ;;

    stalling)
        python3 scripts/deal_velocity.py stalling
        ;;

    cadence|ca)
        python3 scripts/deal_velocity.py due
        ;;

    timeline|tl)
        python3 scripts/structured_log.py tail -n "${2:-30}"
        ;;

    log-stats|ls)
        python3 scripts/structured_log.py stats
        ;;

    log-search)
        python3 scripts/structured_log.py search "${2:-error}"
        ;;

    status-web|sw)
        python3 scripts/status_page.py
        open status/index.html 2>/dev/null || echo "Open status/index.html in browser"
        ;;

    recover)
        if [ -z "$2" ]; then
            echo "Usage: recover <agent>"
            echo "Agents: inbox, intel, calendar, reviewer"
        else
            case "$2" in
                inbox) python3 scripts/recover_inbox.py ;;
                intel) python3 scripts/recover_intel.py ;;
                calendar) python3 scripts/recover_calendar.py ;;
                reviewer) python3 scripts/recover_reviewer.py ;;
                all)
                    python3 scripts/recover_inbox.py
                    python3 scripts/recover_intel.py
                    python3 scripts/recover_calendar.py
                    python3 scripts/recover_reviewer.py
                    ;;
                *) echo "Unknown agent: $2" ;;
            esac
        fi
        ;;

    learning|le)
        python3 scripts/agent_learning.py "${2:-summary}"
        ;;

    standup|su)
        python3 scripts/standup_generator.py "${@:2}"
        ;;

    graph|g)
        python3 scripts/knowledge_graph.py "${2:-stats}"
        ;;

    graph-build|gb)
        python3 scripts/knowledge_graph.py build
        ;;

    brief|bf)
        python3 scripts/strategic_brief.py "${2:-latest}"
        ;;

    brief-gen|bg)
        python3 scripts/strategic_brief.py generate "${@:2}"
        ;;

    winloss|wl)
        python3 scripts/win_loss_analysis.py "${2:-summary}"
        ;;

    personalize|pe)
        python3 scripts/email_personalizer.py personalize "${@:2}"
        ;;

    backup|bk)
        python3 scripts/backup_system.py "${2:-snapshot}"
        ;;

    preflight|pf)
        python3 scripts/preflight.py "${@:2}"
        ;;

    nlp|n)
        python3 scripts/nlp_task.py "${@:2}"
        ;;

    health-server|hs)
        python3 scripts/health_server.py "${@:2}"
        ;;

    report|rp)
        python3 scripts/report_generator.py "${2:-generate}"
        ;;

    report-open|ro)
        python3 scripts/report_generator.py latest
        ;;

    predict|pr)
        python3 scripts/success_predictor.py "${2:-predict}"
        ;;

    risks)
        python3 scripts/success_predictor.py risks
        ;;

    forecast|fc)
        python3 scripts/success_predictor.py forecast
        ;;

    coach)
        python3 scripts/success_predictor.py coach "${2}"
        ;;

    trends|tr)
        python3 scripts/market_trends.py "${2:-analyze}"
        ;;

    referral|ref)
        python3 scripts/referral_network.py "${2:-network}" "${@:3}"
        ;;

    propose|pp)
        python3 scripts/proposal_generator.py generate "${@:2}"
        ;;

    meeting|mt)
        if [ -z "$2" ]; then
            python3 scripts/meeting_prep.py --upcoming
        else
            python3 scripts/meeting_prep.py "$2" "${@:3}"
        fi
        ;;

    timing|ti)
        python3 scripts/time_tracker.py "${2:-stats}"
        ;;

    warmup|wu)
        python3 scripts/agent_warmup.py "${2:-status}"
        ;;

    testdata|td)
        python3 scripts/test_data_generator.py "${2:-generate}"
        ;;

    schema|sv)
        python3 scripts/schema_validator.py "${2:-validate}"
        ;;

    chaos)
        python3 tests/test_chaos.py
        ;;

    integration)
        python3 tests/test_integration.py
        ;;

    sequence|sq)
        python3 scripts/email_sequences.py "${2:-status}" "${@:3}"
        ;;

    compete|ci)
        python3 scripts/competitive_intel.py "${2:-dashboard}"
        ;;

    battlecard|bc)
        python3 scripts/competitive_intel.py battlecard "${2}"
        ;;

    timeline-deal|tld)
        python3 scripts/deal_timeline.py deal "${2}"
        ;;

    timeline-all|tla)
        python3 scripts/deal_timeline.py all
        ;;

    dedup|dd)
        python3 scripts/knowledge_dedup.py "${2:-scan}"
        ;;

    dashboard|db)
        python3 scripts/dashboard_aggregator.py "${2:-summary}"
        ;;

    debate|de)
        python3 scripts/debate_protocol.py "${2:-templates}" "${@:3}"
        ;;

    debate-start|ds)
        python3 scripts/debate_protocol.py start "${@:2}"
        ;;

    abtest|ab)
        python3 scripts/ab_testing.py "${2:-experiments}"
        ;;

    memory|mem)
        python3 scripts/agent_memory.py "${2:-stats}"
        ;;

    anomaly|an)
        python3 scripts/anomaly_detector.py "${2:-scan}"
        ;;

    engage|eg)
        python3 scripts/engagement_scorer.py "${2:-score}" "${@:3}"
        ;;

    automate|auto)
        python3 scripts/pipeline_automation.py "${2:-check}"
        ;;

    auto-rules)
        python3 scripts/pipeline_automation.py rules
        ;;

    digest)
        python3 scripts/daily_digest.py "${2:-preview}"
        ;;

    digest-send)
        python3 scripts/daily_digest.py send
        ;;

    sync)
        python3 scripts/knowledge_sync.py 2>/dev/null || echo "Knowledge sync not available (missing agent-registry.json)"
        ;;

    smoke)
        python3 tests/test_smoke.py
        ;;

    test)
        echo "Running system tests..."
        echo -n "Agent Bus: " && python3 -c "from scripts.agent_bus import AgentBus; print('OK')" 2>/dev/null || echo "FAIL"
        echo -n "Workflow Engine: " && python3 -c "from scripts.workflow_engine import WorkflowEngine; print('OK')" 2>/dev/null || echo "FAIL"
        echo -n "Agent Lifecycle: " && python3 -c "from scripts.agent_lifecycle import AgentStateMachine; print('OK')" 2>/dev/null || echo "FAIL"
        echo -n "Task Queue: " && python3 -c "from scripts.task_queue import TaskPriorityQueue; print('OK')" 2>/dev/null || echo "FAIL"
        echo -n "Collaboration: " && python3 -c "from scripts.agent_collaboration import CollaborationEngine; print('OK')" 2>/dev/null || echo "FAIL"
        echo -n "Deal Velocity: " && python3 -c "from scripts.deal_velocity import DealVelocityTracker; print('OK')" 2>/dev/null || echo "FAIL"
        echo -n "Structured Log: " && python3 -c "from scripts.structured_log import LogAggregator; print('OK')" 2>/dev/null || echo "FAIL"
        echo -n "Scorecard: " && python3 scripts/adhd-scorecard.py 2>/dev/null | head -1 || echo "FAIL"
        echo -n "Ollama: " && curl -s -m 3 http://localhost:11434/api/tags >/dev/null 2>&1 && echo "OK" || echo "OFFLINE"
        echo -n "Heartbeat: " && bash scripts/heartbeat-check.sh 2>/dev/null | head -1 || echo "FAIL"
        echo -n "Smoke Tests: " && python3 tests/test_smoke.py 2>/dev/null | tail -3 | head -1 || echo "FAIL"
        echo "Tests complete."
        ;;

    help|h|*)
        echo "╔══════════════════════════════════════════╗"
        echo "║     CLAWDIA CLI v2 — Quick Actions       ║"
        echo "╚══════════════════════════════════════════╝"
        echo ""
        echo "  DASHBOARD:"
        echo "    status (s)        Full system dashboard"
        echo "    morning (m)       Morning briefing"
        echo "    timeline (tl) N   Unified log timeline"
        echo "    log-stats (ls)    Log statistics"
        echo "    log-search <pat>  Search all logs"
        echo "    events (e)        Recent system events"
        echo "    logs (l)          Raw orchestrator logs"
        echo ""
        echo "  SALES:"
        echo "    pipeline (p)      Run lead scoring"
        echo "    deals (d)         Top scored deals"
        echo "    stale (st)        Stale deals"
        echo "    velocity (v)      Deal velocity dashboard"
        echo "    stalling          Stalling deals"
        echo "    cadence (ca)      Due follow-up actions"
        echo "    drafts (dr) N     Generate N email drafts"
        echo "    writeback (wb)    CRM write-back"
        echo ""
        echo "  AGENTS:"
        echo "    agents (a)        Agent states"
        echo "    stuck             Check stuck agents"
        echo "    perf              Performance analytics"
        echo "    score (sc)        ADHD scorecard"
        echo "    heartbeat (hb)    Health check"
        echo "    recover <agent>   Manual agent recovery"
        echo "    learning (le)     Agent learning insights"
        echo ""
        echo "  COLLABORATION:"
        echo "    collab (co)       Collaboration stats"
        echo "    collab-start (cs) Start collaboration session"
        echo "    tasks (t)         Task priority queue"
        echo "    task-add (ta)     Add task to queue"
        echo "    dispatch (di)     Auto-dispatch tasks"
        echo "    nlp (n) \"text\"    NLP task creation"
        echo ""
        echo "  INTELLIGENCE:"
        echo "    graph (g)         Knowledge graph stats"
        echo "    graph-build (gb)  Build graph from Pipedrive"
        echo "    brief (bf)        Latest strategic brief"
        echo "    brief-gen (bg)    Generate new brief"
        echo "    winloss (wl)      Win/loss analysis"
        echo "    personalize (pe)  Personalize email for deal"
        echo "    standup (su)      Generate daily standup"
        echo ""
        echo "  PREDICTIONS:"
        echo "    predict (pr)      Deal success prediction"
        echo "    risks             At-risk deals"
        echo "    forecast (fc)     Revenue forecast"
        echo "    coach <deal>      Deal coaching advice"
        echo "    trends (tr)       Market trend analysis"
        echo "    referral (ref)    Referral network paths"
        echo "    propose (pp)      Generate sales proposal"
        echo "    meeting (mt)      Meeting prep docs"
        echo "    engage (eg)       Contact engagement scores"
        echo "    anomaly (an)      Anomaly detection"
        echo ""
        echo "  AUTOMATION:"
        echo "    sequence (sq)     Email sequence engine"
        echo "    automate (auto)   Pipeline automation check"
        echo "    auto-rules        Show automation rules"
        echo "    compete (ci)      Competitive intelligence"
        echo "    battlecard (bc)   Competitor battle card"
        echo "    abtest (ab)       A/B test experiments"
        echo "    dedup (dd)        Knowledge deduplication"
        echo ""
        echo "  REPORTS:"
        echo "    report (rp)       Generate weekly report"
        echo "    report-open (ro)  Open latest report"
        echo "    digest            Daily digest preview"
        echo "    digest-send       Send daily digest email"
        echo ""
        echo "  AI / MEMORY:"
        echo "    debate (de)       Debate templates"
        echo "    debate-start (ds) Start multi-agent debate"
        echo "    memory (mem)      Agent memory stats"
        echo "    dashboard (db)    Unified dashboard"
        echo ""
        echo "  SYSTEM:"
        echo "    bus (b)           Message bus stats"
        echo "    bus-route (br)    Route pending messages"
        echo "    workflow (w)      Workflow engine status"
        echo "    workflow-start    Start a workflow"
        echo "    reviews (r)       Pending reviews"
        echo "    costs (c)         API cost tracking"
        echo "    ollama (o)        Ollama status/query"
        echo "    sync              Knowledge sync"
        echo "    backup (bk)       Backup state files"
        echo "    preflight (pf)    Pre-flight checks"
        echo "    status-web (sw)   Mobile status page"
        echo "    health-server     HTTP health endpoint"
        echo "    timing (ti)       Execution time analytics"
        echo "    warmup (wu)       Agent warm-up status"
        echo "    schema (sv)       JSON schema validation"
        echo ""
        echo "  TESTING:"
        echo "    smoke             Full smoke test suite"
        echo "    test              Quick system tests"
        echo "    chaos             Chaos testing framework"
        echo "    integration       Integration tests"
        echo "    testdata (td)     Generate test data"
        echo ""
        ;;
esac
