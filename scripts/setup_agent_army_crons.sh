#!/usr/bin/env bash
set -euo pipefail

TZ="Europe/Prague"

# ──────────────────────────────────────────────────
# WEEKDAY AGENT OPERATIONS (Mon-Fri only)
# ──────────────────────────────────────────────────

# 06:30 — GrowthLab: morning research sweep
openclaw cron create --name growthlab-morning --agent growthlab --cron "30 6 * * 1-5" --tz "$TZ" \
  --message "Morning research sweep. Update intel/DAILY-INTEL.md and intel/MARKET_SIGNALS.md. Create tasks in tasks/open/ only if a new experiment is actionable."

# 07:00 — Timebox: daily planning
openclaw cron create --name timebox-briefing --agent timebox --cron "0 7 * * 1-5" --tz "$TZ" \
  --message "Build today's execution plan. Write calendar/TODAY.md with four time blocks. Create task handoffs in tasks/open/ for items requiring other agents."

# 07:15 — DealOps: morning pipeline health
openclaw cron create --name dealops-am --agent dealops --cron "15 7 * * 1-5" --tz "$TZ" \
  --message "Morning pipeline health check. Update pipedrive/HYGIENE_REPORT.md with aggregate counts and pipedrive/PIPELINE_STATUS.md with risk categories. No raw CRM data in output."

# 07:30 — InboxForge: morning inbox triage
openclaw cron create --name inboxforge-am --agent inboxforge --cron "30 7 * * 1-5" --tz "$TZ" \
  --message "Morning inbox triage. Update inbox/INBOX_DIGEST.md and inbox/DRAFTS.md. Flag items needing human approval. No sends without explicit command."

# ──────────────────────────────────────────────────
# BRIDGE REPORTS (daily, user-facing)
# ──────────────────────────────────────────────────

# 08:00 — Bridge: morning report for Josef
openclaw cron create --name bridge-am-report --agent main --cron "0 8 * * 1-5" --tz "$TZ" \
  --message "Morning report for Josef. Use templates/user-report.md format. Max 15 lines. Three sections: Co je dnes důležité / Co jsem udělal / Potřebuji od tebe. No task IDs, no agent names, no timestamps."

# 18:30 — Bridge: evening report for Josef
openclaw cron create --name bridge-pm-report --agent main --cron "30 18 * * 1-5" --tz "$TZ" \
  --message "Evening report for Josef. Use templates/user-report.md format. Max 15 lines. Summarize what got done, what's blocked, what needs decision. No task IDs, no agent names."

# ──────────────────────────────────────────────────
# MIDDAY OPS (Mon-Fri)
# ──────────────────────────────────────────────────

# 12:00 — GrowthLab: noon intel refresh
openclaw cron create --name growthlab-noon --agent growthlab --cron "0 12 * * 1-5" --tz "$TZ" \
  --message "Noon intel refresh. Update experiment queue and research log. Only write if there is new information."

# 12:30 — DealOps: midday pipeline check
openclaw cron create --name dealops-noon --agent dealops --cron "30 12 * * 1-5" --tz "$TZ" \
  --message "Midday pipeline check. Update aggregate status and flag any deals that changed risk category since morning."

# 13:00 — InboxForge: noon inbox check
openclaw cron create --name inboxforge-noon --agent inboxforge --cron "0 13 * * 1-5" --tz "$TZ" \
  --message "Noon inbox check. Update task statuses and flag new blockers. Skip if no new mail since morning."

# ──────────────────────────────────────────────────
# AFTERNOON / EVENING OPS (Mon-Fri)
# ──────────────────────────────────────────────────

# 17:00 — DealOps: PM pipeline report
openclaw cron create --name dealops-pm --agent dealops --cron "0 17 * * 1-5" --tz "$TZ" \
  --message "PM pipeline report. Write final aggregate CRM state to pipedrive/PIPELINE_STATUS.md. Include counts and risk categories only."

# 17:15 — InboxForge: PM inbox sweep
openclaw cron create --name inboxforge-pm --agent inboxforge --cron "15 17 * * 1-5" --tz "$TZ" \
  --message "PM inbox sweep. Finalize inbox/FOLLOW_UPS.md with sanitized queue. Flag items pending send approval."

# 17:30 — Reviewer: system health check
openclaw cron create --name reviewer-pm --agent reviewer --cron "30 17 * * 1-5" --tz "$TZ" \
  --message "System health check. Write reviews/PENDING_REVIEWS.md and reviews/SYSTEM_HEALTH.md. Check for stale outputs, blocked tasks, and consistency issues."

# ──────────────────────────────────────────────────
# KNOWLEDGE SYNC (daily, includes weekends)
# ──────────────────────────────────────────────────

# 18:00 — KnowledgeKeeper: daily sync
openclaw cron create --name knowledgekeeper-sync --agent knowledgekeeper --cron "0 18 * * *" --tz "$TZ" \
  --message "Daily knowledge sync. Run scripts/knowledge_sync.py. Update knowledge/AGENT_INSIGHTS.md, knowledge/TODAY_SUMMARY.md, reviews/PENDING_REVIEWS.md. Extract learnings from tasks/done/."

# ──────────────────────────────────────────────────
# NIGHTLY MAINTENANCE (daily, includes weekends)
# ──────────────────────────────────────────────────

# 22:00 — KnowledgeKeeper: night archive
openclaw cron create --name knowledgekeeper-night --agent knowledgekeeper --cron "0 22 * * *" --tz "$TZ" \
  --message "Night archive and dedup. Run scripts/knowledge_sync.py. Archive completed tasks, deduplicate knowledge entries, detect stale outputs."

# 22:30 — Reviewer: night security check
openclaw cron create --name reviewer-night --agent reviewer --cron "30 22 * * *" --tz "$TZ" \
  --message "Night security check. Verify no sensitive data in git-tracked files. Check open task backlog for stale items. Write findings to reviews/SYSTEM_HEALTH.md."

echo "Agent Army cron setup complete (15 jobs: 12 weekday-only, 3 daily)"
