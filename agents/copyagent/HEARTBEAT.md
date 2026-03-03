# HEARTBEAT.md — CopyAgent

## Active Cron Tasks
1. **Morning content production** (09:00 M-F) → drafts/*.md, brief status updates
2. **Slack intel extraction** (10:00, 14:00, 18:00 M-F) → SLACK_INSIGHTS.md, OBJECTION_LIBRARY.md
3. **Template polish** (Wed 10:00) → templates/sales/*.md + Pipedrive upload
4. **Content calendar** (Mon 09:30) → briefs/auto-generated/*.md

## Knowledge Sources
- Product: knowledge/COPYWRITER_KNOWLEDGE_BASE.md
- Voice: knowledge/JOSEF_TONE_OF_VOICE.md
- Phrases: knowledge/CZECH_PHRASE_LIBRARY.md
- Objections: knowledge/OBJECTION_LIBRARY.md
- Slack: knowledge/SLACK_INSIGHTS.md
- Book insights: knowledge/book-insights/*.md (from KnowledgeKeeper)
- Pipeline: pipedrive/PIPELINE_STATUS.md (for COPY_NEEDED flags)

## Rules
- All output in Czech unless specifically requested in English
- Use Josef's real tone — no corporate, no buzzwords, no "letáková šablona"
- Every template must have max 1 showcase link (keep powder dry)
- No signature in templates (Josef has signatures in Pipedrive)
- Quality gate: minimum 80/100 on COPYWRITER_PIPELINE.md 10-dimension scoring
- When uploading to Pipedrive: use merge fields {{person.last_name}}, {{person.first_name}}, {{org.name}}

## Dependencies
- Reads: knowledge/*.md, pipedrive/PIPELINE_STATUS.md, briefs/QUEUE.md, intel/DAILY-INTEL.md
- Writes: drafts/*.md, delivery-queue/*.md, templates/sales/*.md, knowledge/SLACK_INSIGHTS.md
- Triggers from: PipelinePilot COPY_NEEDED flags, briefs/QUEUE.md
