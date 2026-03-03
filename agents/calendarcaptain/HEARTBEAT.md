# HEARTBEAT.md — CalendarCaptain

## Active Cron Tasks
1. **Morning planning + Pomodoro schedule** (07:00 M-F) → calendar/TODAY.md, calendar/pomodoro/[date].md, calendar/meeting-prep/*.md
2. **Midday rebalance** (12:45 M-F) → update TODAY.md if morning went off-plan, adjust afternoon Pomodoros
3. **EOD wrap + tomorrow prep** (18:00 M-F) → calendar/TOMORROW_PREP.md, calendar/pomodoro/[date].md (log completion)

## Calendar Access
- Google Calendar MCP tools: gcal_list_events, gcal_get_event, gcal_find_my_free_time, gcal_create_event

## ADHD-Aware Planning Protocol
- Use Pomodoro technique: 25min work / 5min break / 15min break after 4
- Front-load prospecting calls (08:00-10:45) — non-negotiable
- Alternate task types — never schedule 2+ hours of same activity
- Include XP/streak status from reviews/daily-scorecard/SCOREBOARD.md in morning briefing
- Frame tasks as XP opportunities for gamification
- Buffer all meetings (+10min)
- Protect 15:30-16:30 creative/building block (high dopamine)

## Daily Targets to Schedule Around
- 8 demo bookings (prospecting outreach)
- 5 demo calls (30min each, mostly 11:00-15:30)
- 10+ follow-ups (afternoon sprint 16:45)
- 2 proposals (admin block 13:20)

## Rules
- Pull SPIN notes from pipedrive/spin-notes/ for sales meetings
- Pull deal status from pipedrive/PIPELINE_STATUS.md
- Pull relevant intel from intel/DAILY-INTEL.md
- Meeting prep must be specific to the company, not generic
- Flag if a sales meeting has no SPIN note prepared → trigger PipelinePilot
- Read Auditor's scorecard for yesterday's performance → adjust today's plan
- If streak at risk, mark it prominently in TODAY.md

## Dependencies
- Reads: pipedrive/spin-notes/*.md, pipedrive/PIPELINE_STATUS.md, pipedrive/DEAL_SCORING.md, intel/DAILY-INTEL.md, inbox/TRIAGE.md, reviews/daily-scorecard/SCOREBOARD.md, reviews/daily-scorecard/*.md
- Writes: calendar/TODAY.md, calendar/TOMORROW_PREP.md, calendar/meeting-prep/*.md, calendar/pomodoro/*.md
- Google Calendar MCP for schedule data
