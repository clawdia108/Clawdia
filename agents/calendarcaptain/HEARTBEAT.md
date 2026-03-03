# HEARTBEAT.md — CalendarCaptain

## Active Cron Tasks
1. **Morning planning** (07:00 M-F) → calendar/TODAY.md, calendar/meeting-prep/*.md
2. **EOD wrap + tomorrow prep** (18:00 M-F) → calendar/TOMORROW_PREP.md

## Calendar Access
- Google Calendar MCP tools: gcal_list_events, gcal_get_event, gcal_find_my_free_time

## Rules
- Pull SPIN notes from pipedrive/spin-notes/ for sales meetings
- Pull deal status from pipedrive/PIPELINE_STATUS.md
- Pull relevant intel from intel/DAILY-INTEL.md
- Meeting prep must be specific to the company, not generic
- Flag if a sales meeting has no SPIN note prepared → trigger PipelinePilot
- Suggest optimal time blocks for deep work (min 2h uninterrupted)

## Dependencies
- Reads: pipedrive/spin-notes/*.md, pipedrive/PIPELINE_STATUS.md, pipedrive/DEAL_SCORING.md, intel/DAILY-INTEL.md, inbox/TRIAGE.md
- Writes: calendar/TODAY.md, calendar/TOMORROW_PREP.md, calendar/meeting-prep/*.md
- Google Calendar MCP for schedule data
