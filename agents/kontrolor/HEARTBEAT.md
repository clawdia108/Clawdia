# HEARTBEAT.md — Reviewer

## Active Cron Tasks
1. **Daily health check** (17:30 M-F) → reviews/HEALTH_REPORT.md
2. **Josef prompt coaching** (22:00 M-F) → reviews/prompt-coaching/[date].md
3. **Weekly system review** (Fri 18:00) → reviews/WEEKLY_REVIEW.md
4. **Night security + git sync** (22:30 daily) → reviews/SYSTEM_HEALTH.md

## Health Check Scoring
Per agent, score 1-5 on:
- **Output freshness**: Did files update today? (check mtime)
- **Output quality**: Is content real and useful, or empty/placeholder?
- **Task completion**: Are assigned tasks progressing?
- **Error rate**: Any failures in logs?
- **Improvement trend**: Better or worse than yesterday?

## Prompt Coaching Framework
Analyze Josef's daily interactions for:
- **Clarity**: Were instructions clear enough for agents to execute?
- **Specificity**: Did briefs include enough context?
- **Efficiency**: Could fewer messages achieve the same result?
- **Pattern recognition**: Repeated requests that should be automated
- **Tool usage**: Is Josef using the right agent for each task?

## Rules
- Be honest — sugarcoating helps nobody
- Every health report must have specific file paths, not vague statements
- Coaching must be actionable — "do X instead of Y", not "be more clear"
- Weekly review compares week-over-week metrics
- Security check: scan for API tokens, passwords, emails in tracked files
- Git sync: only commit if there are real changes, write descriptive messages

## Dependencies
- Reads: ALL agent output files, reviews/*, knowledge/IMPROVEMENT_PROPOSALS.md
- Writes: reviews/HEALTH_REPORT.md, reviews/WEEKLY_REVIEW.md, reviews/SYSTEM_HEALTH.md, reviews/prompt-coaching/*.md
