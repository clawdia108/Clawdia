#!/bin/bash
# ============================================================
# Overnight Full System Run — Master Orchestration
# ============================================================
# Runs at 06:30 via launchd (com.clawdia.overnight)
# Executes all data gathering, scoring, analysis, and prep
# so everything is fresh when Josef starts his day.
#
# FLOW:
#   1. Health check + tests
#   2. Data gathering (Fathom, signals, enrichment)
#   3. Scoring & analysis (deals, velocity, predictions)
#   4. Intelligence (market, competitive, anomalies)
#   5. Morning prep (call list, SPIN, follow-ups, drafts)
#   6. Reporting & sync (Notion, status, backup)
#   7. Telegram summary
# ============================================================

cd /Users/josefhofman/Clawdia

LOG="logs/overnight.log"
mkdir -p logs reports reports/call-lists reports/health reports/signals reports/weekly \
  proposals meeting-prep intel status knowledge/agent-memory knowledge/signals \
  knowledge/pipeline_snapshots knowledge/call_coaching drafts/followups

echo "============================================" | tee -a "$LOG"
echo "  OVERNIGHT RUN — $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG"
echo "============================================" | tee -a "$LOG"

START=$(date +%s)
ERRORS=0
STEPS_OK=0
TOTAL_STEPS=0

# Timeout wrapper — kill any script that runs > 5 minutes
run_step() {
    local name="$1"
    shift
    TOTAL_STEPS=$((TOTAL_STEPS + 1))
    echo "" | tee -a "$LOG"
    echo "--- [$TOTAL_STEPS] $name ---" | tee -a "$LOG"

    timeout 300 "$@" 2>&1 | tail -5 | tee -a "$LOG"
    local exit_code=${PIPESTATUS[0]}

    if [ "$exit_code" -eq 0 ]; then
        STEPS_OK=$((STEPS_OK + 1))
        echo "  OK" | tee -a "$LOG"
    elif [ "$exit_code" -eq 124 ]; then
        ERRORS=$((ERRORS + 1))
        echo "  TIMEOUT (5min)" | tee -a "$LOG"
    else
        ERRORS=$((ERRORS + 1))
        echo "  ERROR (exit $exit_code)" | tee -a "$LOG"
    fi
}

# ════════════════════════════════════════════════════════════
# PHASE 1: HEALTH CHECK & TESTS
# ════════════════════════════════════════════════════════════
echo "" | tee -a "$LOG"
echo "== PHASE 1: HEALTH CHECK ==" | tee -a "$LOG"

run_step "SMOKE TESTS" python3 tests/test_smoke.py
run_step "INTEGRATION TESTS" python3 tests/test_integration.py
run_step "SCHEMA VALIDATION" python3 scripts/schema_validator.py validate

# ════════════════════════════════════════════════════════════
# PHASE 2: DATA GATHERING
# ════════════════════════════════════════════════════════════
echo "" | tee -a "$LOG"
echo "== PHASE 2: DATA GATHERING ==" | tee -a "$LOG"

run_step "FATHOM SYNC" python3 scripts/fathom_sync.py
run_step "SIGNAL SCANNER" python3 scripts/signal_scanner.py
run_step "LUSHA ENRICHMENT" python3 scripts/lusha_enricher.py --top 5
run_step "HUMANIZER TRAINING" python3 scripts/humanizer_trainer.py

# ════════════════════════════════════════════════════════════
# PHASE 3: SCORING & ANALYSIS
# ════════════════════════════════════════════════════════════
echo "" | tee -a "$LOG"
echo "== PHASE 3: SCORING & ANALYSIS ==" | tee -a "$LOG"

run_step "LEAD SCORING" python3 scripts/pipedrive_lead_scorer.py
run_step "DEAL HEALTH" python3 scripts/deal_health_scorer.py --snapshot
run_step "DEAL VELOCITY" python3 scripts/deal_velocity.py velocity
run_step "SUCCESS PREDICTIONS" python3 scripts/success_predictor.py predict
run_step "ENGAGEMENT SCORING" python3 scripts/engagement_scorer.py score
run_step "PIPELINE AUTOMATION" python3 scripts/pipeline_automation.py check

# ════════════════════════════════════════════════════════════
# PHASE 4: INTELLIGENCE
# ════════════════════════════════════════════════════════════
echo "" | tee -a "$LOG"
echo "== PHASE 4: INTELLIGENCE ==" | tee -a "$LOG"

run_step "KNOWLEDGE GRAPH" python3 scripts/knowledge_graph.py build
run_step "MARKET TRENDS" python3 scripts/market_trends.py report
run_step "COMPETITIVE INTEL" python3 scripts/competitive_intel.py scan
run_step "ANOMALY DETECTION" python3 scripts/anomaly_detector.py scan
run_step "WIN/LOSS ANALYSIS" python3 scripts/win_loss_analysis.py summary

# ════════════════════════════════════════════════════════════
# PHASE 5: MORNING PREP
# ════════════════════════════════════════════════════════════
echo "" | tee -a "$LOG"
echo "== PHASE 5: MORNING PREP ==" | tee -a "$LOG"

run_step "COLD CALL LIST" python3 scripts/cold_call_list.py --export
run_step "FOLLOW-UP ENGINE" python3 scripts/followup_engine.py --scan
run_step "EMAIL SEQUENCES" python3 scripts/email_sequences.py advance
run_step "MEETING PREP" python3 scripts/meeting_prep.py --upcoming
run_step "STRATEGIC BRIEF" python3 scripts/strategic_brief.py generate

# ════════════════════════════════════════════════════════════
# PHASE 6: REPORTING & SYNC
# ════════════════════════════════════════════════════════════
echo "" | tee -a "$LOG"
echo "== PHASE 6: REPORTING & SYNC ==" | tee -a "$LOG"

run_step "REPORT GENERATOR" python3 scripts/report_generator.py generate
run_step "NOTION SYNC" python3 scripts/notion_sync.py
run_step "STATUS PAGE" python3 scripts/status_page.py
run_step "DAILY STANDUP" python3 scripts/standup_generator.py
run_step "SCORECARD" python3 scripts/adhd-scorecard.py
run_step "DEDUP + CLEANUP" python3 scripts/knowledge_dedup.py scan
run_step "BACKUP" python3 scripts/backup_system.py snapshot

# ════════════════════════════════════════════════════════════
# COLLECT RESULTS
# ════════════════════════════════════════════════════════════
END=$(date +%s)
ELAPSED=$((END - START))

echo "" | tee -a "$LOG"
echo "============================================" | tee -a "$LOG"
echo "  OVERNIGHT RUN COMPLETE" | tee -a "$LOG"
echo "  Steps: $STEPS_OK/$TOTAL_STEPS OK, $ERRORS errors" | tee -a "$LOG"
echo "  Duration: ${ELAPSED}s ($((ELAPSED / 60))min)" | tee -a "$LOG"
echo "  Finished: $(date '+%Y-%m-%d %H:%M:%S')" | tee -a "$LOG"
echo "============================================" | tee -a "$LOG"

# Save structured results
python3 -c "
import json, time
from pathlib import Path
from datetime import datetime

BASE = Path('/Users/josefhofman/Clawdia')

def safe_json(p):
    try:
        if Path(p).exists():
            return json.loads(Path(p).read_text())
    except: pass
    return None

def file_fresh(p, hours=24):
    try:
        if Path(p).exists() and Path(p).stat().st_size > 50:
            age = (time.time() - Path(p).stat().st_mtime) / 3600
            return age < hours
    except: pass
    return False

results = {
    'timestamp': datetime.now().isoformat(),
    'duration_seconds': ${ELAPSED},
    'steps_ok': ${STEPS_OK},
    'steps_total': ${TOTAL_STEPS},
    'errors': ${ERRORS},
    'agents': {
        'spojka': file_fresh(BASE / 'knowledge/USER_DIGEST_AM.md'),
        'obchodak': file_fresh(BASE / 'pipedrive/PIPELINE_STATUS.md'),
        'postak': file_fresh(BASE / 'inbox/INBOX_DIGEST.md'),
        'strateg': file_fresh(BASE / 'intel/DAILY-INTEL.md', 48),
        'kalendar': file_fresh(BASE / 'calendar/TODAY.md'),
        'kontrolor': file_fresh(BASE / 'reviews/SYSTEM_HEALTH.md', 72),
        'archivar': file_fresh(BASE / 'knowledge/IMPROVEMENTS.md', 72),
    },
    'outputs': {
        'pipeline_scored': file_fresh(BASE / 'pipedrive/DEAL_SCORING.md'),
        'deal_health': file_fresh(BASE / 'reports/health'),
        'signals': file_fresh(BASE / 'reports/signals'),
        'call_list': file_fresh(BASE / 'reports/call-lists'),
        'velocity': file_fresh(BASE / 'pipedrive/deal_velocity.json'),
        'graph': file_fresh(BASE / 'knowledge/graph.json'),
        'predictions': file_fresh(BASE / 'knowledge/deal-predictions.json'),
        'trends': file_fresh(BASE / 'knowledge/market-trends.json'),
        'notion_synced': file_fresh(BASE / 'logs/notion-sync.log'),
    },
    'scorecard': safe_json(BASE / 'reviews/daily-scorecard/score_state.json'),
}

healthy = sum(1 for v in results['agents'].values() if v)
total = len(results['agents'])
results['summary'] = f'{healthy}/{total} agents healthy, {${STEPS_OK}}/{${TOTAL_STEPS}} steps OK'

Path(BASE / 'logs/overnight-results.json').write_text(json.dumps(results, indent=2))
print(f'Results saved: {results[\"summary\"]}')
" 2>&1 | tee -a "$LOG"

# ════════════════════════════════════════════════════════════
# TELEGRAM SUMMARY
# ════════════════════════════════════════════════════════════
python3 -c "
import sys
sys.path.insert(0, 'scripts')
from lib.notifications import notify_telegram

msg = '''Overnight Run Complete

Steps: ${STEPS_OK}/${TOTAL_STEPS} OK, ${ERRORS} errors
Duration: $((ELAPSED / 60))min

Ready for your morning. Check Notion Sales Hub for full overview.'''

notify_telegram(msg)
print('Telegram summary sent')
" 2>&1 | tee -a "$LOG"

# Generate morning digest preview
run_step "MORNING DIGEST" python3 scripts/daily_digest.py preview

echo "" | tee -a "$LOG"
echo "All done. Results in logs/overnight-results.json" | tee -a "$LOG"
