# HEARTBEAT.md — PipelinePilot

## Active Cron Tasks
1. **Morning pipeline snapshot + scoring** (07:00 M-F) → PIPELINE_STATUS.md, DEAL_SCORING.md
2. **SPIN prep for demos** (08:30 M-F) → pipedrive/spin-notes/*.md
3. **Deal enrichment AM** (10:00 M-F) → ENRICHMENT_LOG.md + Pipedrive API updates
4. **Deal enrichment PM** (14:00 M-F) → ENRICHMENT_LOG.md + Pipedrive API updates
5. **Hygiene scan** (12:00 M-F) → HYGIENE_REPORT.md
6. **Deal notes** (16:00 M-F) → Pipedrive API notes
7. **PM status** (17:00 M-F) → PIPELINE_STATUS.md
8. **CRM learning** (Fri 17:00) → CRM_LEARNING_LOG.md

## API Access
```bash
source .secrets/pipedrive.env
# PIPEDRIVE_API_TOKEN, PIPEDRIVE_BASE_URL, PIPEDRIVE_USER_ID
```

## Rules
- ONLY touch deals owned by user_id=24403638 (Josef Hofman)
- Never delete deals, contacts, or activities
- Always verify data before writing to Pipedrive — no guesses
- Tag AI-generated notes with [AI-Generated] prefix
- SPIN notes must be industry-specific, never generic
- Scoring formula: Fit (0-40) + Engagement (0-35) + Momentum (0-25) = max 100

## Dependencies
- Reads: intel/DAILY-INTEL.md, intel/BATTLE_CARDS.md, knowledge/OBJECTION_LIBRARY.md
- Writes: pipedrive/PIPELINE_STATUS.md, pipedrive/DEAL_SCORING.md, pipedrive/HYGIENE_REPORT.md, pipedrive/ENRICHMENT_LOG.md, pipedrive/spin-notes/*.md, pipedrive/CRM_LEARNING_LOG.md
- Triggers: COPY_NEEDED flags in PIPELINE_STATUS.md → consumed by CopyAgent
