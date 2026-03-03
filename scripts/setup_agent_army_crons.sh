#!/usr/bin/env bash
set -euo pipefail

TZ="Europe/Prague"

openclaw cron create --name growthlab-morning --agent growthlab --cron "30 6 * * *" --tz "$TZ" --message "Proveď ranní research sweep. Aktualizuj intel/DAILY-INTEL.md, intel/MARKET_SIGNALS.md a tasks/open/ pokud vznikne nový experiment."
openclaw cron create --name timebox-briefing --agent timebox --cron "0 7 * * *" --tz "$TZ" --message "Připrav calendar/TODAY.md a případné task handoffy do tasks/open/."
openclaw cron create --name dealops-am --agent dealops --cron "15 7 * * *" --tz "$TZ" --message "Ranní pipeline check + hygiene report. Pokud vznikne follow-up práce, založ task JSON do tasks/open/."
openclaw cron create --name inboxforge-am --agent inboxforge --cron "30 7 * * *" --tz "$TZ" --message "Ranní inbox triage + drafty. Stav zapisuj do inbox/ a tasků v tasks/open/."
openclaw cron create --name bridge-am-report --agent main --cron "0 8 * * *" --tz "$TZ" --message "[Bridge] Ranní report Josefovi"
openclaw cron create --name growthlab-noon --agent growthlab --cron "0 12 * * *" --tz "$TZ" --message "Polední intel update. Udrž experiment queue a research log v sync."
openclaw cron create --name dealops-noon --agent dealops --cron "30 12 * * *" --tz "$TZ" --message "Midday pipeline check. Aktualizuj aggregate status a task handoffs."
openclaw cron create --name inboxforge-noon --agent inboxforge --cron "0 13 * * *" --tz "$TZ" --message "Polední inbox check. Obnov task statusy a blockers."
openclaw cron create --name dealops-pm --agent dealops --cron "0 17 * * *" --tz "$TZ" --message "PM pipeline report. Zapiš aggregate CRM stav do pipedrive/PIPELINE_STATUS.md."
openclaw cron create --name inboxforge-pm --agent inboxforge --cron "15 17 * * *" --tz "$TZ" --message "PM inbox sweep. Udrž anonymized queue v inbox/FOLLOW_UPS.md."
openclaw cron create --name reviewer-pm --agent reviewer --cron "30 17 * * *" --tz "$TZ" --message "System health check. Založ review findings do reviews/PENDING_REVIEWS.md."
openclaw cron create --name knowledgekeeper-sync --agent knowledgekeeper --cron "0 18 * * *" --tz "$TZ" --message "Daily knowledge sync. Spusť scripts/knowledge_sync.py a aktualizuj knowledge/."
openclaw cron create --name bridge-pm-report --agent main --cron "30 18 * * *" --tz "$TZ" --message "[Bridge] Večerní report Josefovi"
openclaw cron create --name knowledgekeeper-night --agent knowledgekeeper --cron "0 22 * * *" --tz "$TZ" --message "Night archive + dedupe. Spusť scripts/knowledge_sync.py před archivací."
openclaw cron create --name reviewer-night --agent reviewer --cron "30 22 * * *" --tz "$TZ" --message "Night security check. Zkontroluj open task backlog a stale outputs."
echo "Agent Army cron setup complete"
