# HEARTBEAT.md — Auditor

## Active Cron Tasks
1. **Morning accountability** (07:15 M-F) → reviews/daily-scorecard/[date].md
2. **Midday check-in** (12:30 M-F) → quick Slack/notification
3. **EOD scorecard** (17:30 M-F) → reviews/daily-scorecard/[date].md (full)
4. **Weekly roast** (Fri 18:00) → reviews/daily-scorecard/WEEKLY_ROAST.md

## KPIs Tracked
| Metric | Source | How to Measure |
|--------|--------|----------------|
| Demos booked | Pipedrive activities created (type: call/meeting) | GET /v1/activities?user_id=24403638&type=call |
| Demos done | Pipedrive activities marked done | GET /v1/activities?user_id=24403638&done=1 |
| Follow-ups | inbox/FOLLOW_UPS.md + Pipedrive | Count emails sent |
| Proposals | Pipedrive deals in "Proposal Made" | Stage changes |
| Revenue | Pipedrive deals won | GET /v1/deals?status=won |
| Pipeline growth | PIPELINE_STATUS.md | Compare day-over-day |

## Gamification
- XP tracking: reviews/daily-scorecard/SCOREBOARD.md
- Streak tracking: consecutive days at target
- Level system: Rookie → Closer → Dealmaker → Sales Machine

## Dependencies
- Reads: pipedrive/PIPELINE_STATUS.md, pipedrive/DEAL_SCORING.md, calendar/TODAY.md, inbox/FOLLOW_UPS.md
- Writes: reviews/daily-scorecard/*.md, reviews/daily-scorecard/SCOREBOARD.md, reviews/daily-scorecard/WEEKLY_ROAST.md
- Pipedrive API: source .secrets/pipedrive.env (for activity/deal data)
