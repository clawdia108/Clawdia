# HEARTBEAT.md — InboxForge

## Active Cron Tasks
1. **Gmail scan** (every 2h, 08-18 M-F) → inbox/TRIAGE.md
2. **Draft replies** (09:00 M-F) → inbox/DRAFTS.md + Gmail drafts
3. **Follow-up queue** (17:00 M-F) → inbox/FOLLOW_UPS.md

## Gmail Access
- Account: josef.hofman@behavera.com (via Gmail MCP tools)
- Tools: gmail_search_messages, gmail_read_message, gmail_create_draft

## Rules
- NEVER send emails — only create drafts or suggest replies
- All drafts in Josef's tone (JOSEF_TONE_OF_VOICE.md + CZECH_PHRASE_LIBRARY.md)
- Cross-reference senders with Pipedrive deals
- Flag urgent emails (from active prospects, customers with issues)
- Follow-up suggestions must include which template to use

## Dependencies
- Reads: pipedrive/PIPELINE_STATUS.md, pipedrive/HYGIENE_REPORT.md, knowledge/JOSEF_TONE_OF_VOICE.md, knowledge/CZECH_PHRASE_LIBRARY.md, templates/sales/*.md
- Writes: inbox/TRIAGE.md, inbox/DRAFTS.md, inbox/FOLLOW_UPS.md
- Gmail MCP: gmail_create_draft for automated drafts
