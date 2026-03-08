#!/bin/bash
# Overnight Full System Run — Execute all agents and collect results
# Run: nohup bash scripts/overnight_run.sh &> logs/overnight.log &
set -e
cd /Users/josefhofman/Clawdia

LOG="logs/overnight.log"

# Timeout wrapper — kill any script that runs > 5 minutes
run_step() {
    "$@" &
    local pid=$!
    local i=0
    while kill -0 "$pid" 2>/dev/null; do
        sleep 1
        i=$((i + 1))
        if [ "$i" -ge 300 ]; then
            kill "$pid" 2>/dev/null
            sleep 1
            kill -9 "$pid" 2>/dev/null
            echo "  (timed out after 5min)"
            return 1
        fi
    done
    wait "$pid" 2>/dev/null
}
RESULTS="logs/overnight-results.json"
mkdir -p logs reports proposals meeting-prep intel status knowledge/agent-memory debates experiments sequences

echo "============================================" | tee -a "$LOG"
echo "  OVERNIGHT RUN — $(date)" | tee -a "$LOG"
echo "============================================" | tee -a "$LOG"

# Track timing
START=$(date +%s)

# ── 1. FULL TEST SUITE ─────────────────────────────
echo "" | tee -a "$LOG"
echo "--- [1/12] TEST SUITE ---" | tee -a "$LOG"
echo "Smoke tests:" | tee -a "$LOG"
python3 tests/test_smoke.py 2>&1 | tail -3 | tee -a "$LOG"
echo "Chaos tests:" | tee -a "$LOG"
python3 tests/test_chaos.py 2>&1 | tail -5 | tee -a "$LOG"
echo "Integration tests:" | tee -a "$LOG"
python3 tests/test_integration.py 2>&1 | tail -5 | tee -a "$LOG"
echo "Schema validation:" | tee -a "$LOG"
python3 scripts/schema_validator.py validate 2>&1 | tail -3 | tee -a "$LOG"

# ── 2. PIPELINE SCORING ────────────────────────────
echo "" | tee -a "$LOG"
echo "--- [2/12] PIPELINE SCORING ---" | tee -a "$LOG"
python3 scripts/pipedrive_lead_scorer.py 2>&1 | tail -5 | tee -a "$LOG" || echo "Lead scorer error" | tee -a "$LOG"

# ── 3. DEAL VELOCITY ───────────────────────────────
echo "" | tee -a "$LOG"
echo "--- [3/12] DEAL VELOCITY ---" | tee -a "$LOG"
python3 scripts/deal_velocity.py velocity 2>&1 | tail -10 | tee -a "$LOG" || echo "Velocity error" | tee -a "$LOG"

# ── 4. KNOWLEDGE GRAPH ─────────────────────────────
echo "" | tee -a "$LOG"
echo "--- [4/12] KNOWLEDGE GRAPH ---" | tee -a "$LOG"
python3 scripts/knowledge_graph.py build 2>&1 | tail -5 | tee -a "$LOG" || echo "Graph build error" | tee -a "$LOG"

# ── 5. SUCCESS PREDICTIONS ─────────────────────────
echo "" | tee -a "$LOG"
echo "--- [5/12] SUCCESS PREDICTIONS ---" | tee -a "$LOG"
python3 scripts/success_predictor.py predict 2>&1 | tail -15 | tee -a "$LOG" || echo "Predictor error" | tee -a "$LOG"

# ── 6. MARKET TRENDS ──────────────────────────────
echo "" | tee -a "$LOG"
echo "--- [6/12] MARKET TRENDS ---" | tee -a "$LOG"
python3 scripts/market_trends.py report 2>&1 | tail -10 | tee -a "$LOG" || echo "Trends error" | tee -a "$LOG"

# ── 7. COMPETITIVE INTEL ──────────────────────────
echo "" | tee -a "$LOG"
echo "--- [7/12] COMPETITIVE INTEL ---" | tee -a "$LOG"
run_step python3 scripts/competitive_intel.py scan | tail -10 | tee -a "$LOG" || echo "Comp intel error" | tee -a "$LOG"

# ── 8. ANOMALY DETECTION ─────────────────────────
echo "" | tee -a "$LOG"
echo "--- [8/12] ANOMALY DETECTION ---" | tee -a "$LOG"
python3 scripts/anomaly_detector.py scan 2>&1 | tail -10 | tee -a "$LOG" || echo "Anomaly error" | tee -a "$LOG"

# ── 9. MEETING PREP ──────────────────────────────
echo "" | tee -a "$LOG"
echo "--- [9/12] MEETING PREP ---" | tee -a "$LOG"
run_step python3 scripts/meeting_prep.py --upcoming | tail -10 | tee -a "$LOG" || echo "Meeting prep error" | tee -a "$LOG"

# ── 10. PIPELINE AUTOMATION ──────────────────────
echo "" | tee -a "$LOG"
echo "--- [10/12] PIPELINE AUTOMATION ---" | tee -a "$LOG"
python3 scripts/pipeline_automation.py check 2>&1 | tail -5 | tee -a "$LOG" || echo "Automation error" | tee -a "$LOG"

# ── 11. WEEKLY REPORT ────────────────────────────
echo "" | tee -a "$LOG"
echo "--- [11/12] WEEKLY REPORT ---" | tee -a "$LOG"
python3 scripts/report_generator.py generate 2>&1 | tail -5 | tee -a "$LOG" || echo "Report error" | tee -a "$LOG"

# ── 12. DEDUP + CLEANUP ─────────────────────────
echo "" | tee -a "$LOG"
echo "--- [12/12] DEDUP + CLEANUP ---" | tee -a "$LOG"
python3 scripts/knowledge_dedup.py scan 2>&1 | tail -5 | tee -a "$LOG" || echo "Dedup error" | tee -a "$LOG"

# ── ADVANCE EMAIL SEQUENCES ─────────────────────
echo "" | tee -a "$LOG"
echo "--- BONUS: EMAIL SEQUENCES ---" | tee -a "$LOG"
python3 scripts/email_sequences.py advance 2>&1 | tail -5 | tee -a "$LOG" || echo "Sequence error" | tee -a "$LOG"

# ── STRATEGIC BRIEF ─────────────────────────────
echo "" | tee -a "$LOG"
echo "--- BONUS: STRATEGIC BRIEF ---" | tee -a "$LOG"
python3 scripts/strategic_brief.py generate 2>&1 | tail -5 | tee -a "$LOG" || echo "Brief error" | tee -a "$LOG"

# ── STANDUP ─────────────────────────────────────
echo "" | tee -a "$LOG"
echo "--- BONUS: DAILY STANDUP ---" | tee -a "$LOG"
python3 scripts/standup_generator.py 2>&1 | tail -10 | tee -a "$LOG" || echo "Standup error" | tee -a "$LOG"

# ── STATUS PAGE ─────────────────────────────────
echo "" | tee -a "$LOG"
echo "--- BONUS: STATUS PAGE ---" | tee -a "$LOG"
python3 scripts/status_page.py 2>&1 | tail -3 | tee -a "$LOG" || echo "Status page error" | tee -a "$LOG"

# ── WIN/LOSS ────────────────────────────────────
echo "" | tee -a "$LOG"
echo "--- BONUS: WIN/LOSS ANALYSIS ---" | tee -a "$LOG"
python3 scripts/win_loss_analysis.py summary 2>&1 | tail -10 | tee -a "$LOG" || echo "Win/loss error" | tee -a "$LOG"

# ── REFERRAL NETWORK ────────────────────────────
echo "" | tee -a "$LOG"
echo "--- BONUS: REFERRAL NETWORK ---" | tee -a "$LOG"
python3 scripts/referral_network.py network 2>&1 | tail -10 | tee -a "$LOG" || echo "Referral error" | tee -a "$LOG"

# ── ENGAGEMENT SCORES ───────────────────────────
echo "" | tee -a "$LOG"
echo "--- BONUS: ENGAGEMENT SCORING ---" | tee -a "$LOG"
python3 scripts/engagement_scorer.py score 2>&1 | tail -10 | tee -a "$LOG" || echo "Engagement error" | tee -a "$LOG"

# ── AGENT DEBATE ────────────────────────────────
echo "" | tee -a "$LOG"
echo "--- BONUS: AGENT DEBATE ---" | tee -a "$LOG"
run_step python3 scripts/debate_protocol.py start deal_priority | tail -15 | tee -a "$LOG" || echo "Debate error" | tee -a "$LOG"

# ── SCORECARD UPDATE ────────────────────────────
echo "" | tee -a "$LOG"
echo "--- BONUS: SCORECARD ---" | tee -a "$LOG"
python3 scripts/adhd-scorecard.py 2>&1 | tail -5 | tee -a "$LOG" || echo "Scorecard error" | tee -a "$LOG"

# ── BACKUP ──────────────────────────────────────
echo "" | tee -a "$LOG"
echo "--- FINAL: BACKUP ---" | tee -a "$LOG"
python3 scripts/backup_system.py snapshot 2>&1 | tail -3 | tee -a "$LOG" || echo "Backup error" | tee -a "$LOG"

# ── COLLECT RESULTS ─────────────────────────────
END=$(date +%s)
ELAPSED=$((END - START))

echo "" | tee -a "$LOG"
echo "============================================" | tee -a "$LOG"
echo "  OVERNIGHT RUN COMPLETE" | tee -a "$LOG"
echo "  Duration: ${ELAPSED}s ($((ELAPSED / 60))min)" | tee -a "$LOG"
echo "  Finished: $(date)" | tee -a "$LOG"
echo "============================================" | tee -a "$LOG"

# Save structured results
python3 -c "
import json, time, os
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
    'tests': {
        'smoke': safe_json(BASE / 'logs/smoke-test-results.json'),
        'chaos': safe_json(BASE / 'logs/chaos-test-results.json'),
        'integration': safe_json(BASE / 'logs/integration-test-results.json'),
    },
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
        'velocity_tracked': file_fresh(BASE / 'pipedrive/deal_velocity.json'),
        'graph_built': file_fresh(BASE / 'knowledge/graph.json'),
        'predictions_made': file_fresh(BASE / 'knowledge/deal-predictions.json'),
        'trends_analyzed': file_fresh(BASE / 'knowledge/market-trends.json'),
        'report_generated': (BASE / 'reports').exists() and len(list((BASE / 'reports').glob('*.html'))) > 0,
        'meeting_preps': (BASE / 'meeting-prep').exists() and len(list((BASE / 'meeting-prep').glob('*.md'))) > 0,
        'status_page': file_fresh(BASE / 'status/index.html'),
    },
    'scorecard': safe_json(BASE / 'reviews/daily-scorecard/score_state.json'),
}

healthy = sum(1 for v in results['agents'].values() if v)
total = len(results['agents'])
results['summary'] = f'{healthy}/{total} agents healthy'

Path(BASE / 'logs/overnight-results.json').write_text(json.dumps(results, indent=2))
print(f'Results saved. Agents: {healthy}/{total} healthy')
" 2>&1 | tee -a "$LOG"

# Generate morning digest preview
echo "" | tee -a "$LOG"
echo "--- MORNING DIGEST ---" | tee -a "$LOG"
python3 scripts/daily_digest.py preview 2>&1 | tee -a "$LOG" || echo "Digest error" | tee -a "$LOG"

echo "" | tee -a "$LOG"
echo "Good night! Results in logs/overnight-results.json" | tee -a "$LOG"
echo "Morning digest in status/digest_preview.html" | tee -a "$LOG"
