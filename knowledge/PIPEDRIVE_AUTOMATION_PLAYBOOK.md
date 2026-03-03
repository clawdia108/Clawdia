# Pipedrive Automation Playbook

> Written for AI agents that will EXECUTE these automations autonomously.
> All API references target Pipedrive API v2 where available, falling back to v1.
> Authentication: API token (`api_token`) for internal tools, OAuth 2.0 for apps.

---

## API Fundamentals (Read First)

| Concept | Detail |
|---------|--------|
| **Base URL** | `https://api.pipedrive.com/v1/` (v2: `https://api.pipedrive.com/v2/`) |
| **Auth** | Query param `?api_token=TOKEN` or `Authorization: Bearer ACCESS_TOKEN` |
| **Rate Limits** | Token-budget per company/day (resets every 24h). Burst: per-token rolling 2s window. Search: 10 req/2s. |
| **Pagination** | v2 uses cursor-based pagination (`cursor` param). v1 uses `start` + `limit` (max 500). |
| **Error Handling** | Always handle 429 (rate limit), 401 (auth expired), 5xx (retry with backoff). |
| **v2 Priority** | Use v2 endpoints when available -- lower token cost, better performance. |

---

## 1. Pipeline Hygiene Automations

### 1.1 Stale Deal Detection and Alerts

**What it does:** Scans all open deals, flags any that haven't had activity or updates beyond a threshold (per-stage configurable). Sends alerts to deal owners.

**Why it matters:** Stale deals inflate pipeline value, kill forecast accuracy, and represent lost revenue. Pipedrive's built-in "rotting" feature is visual-only -- you can't trigger automations from it directly.

**API endpoints:**
- `GET /v2/deals` -- filter by `status=open`, iterate with cursor pagination
- `GET /v1/deals/{id}/flow` -- get deal timeline/activity history
- `GET /v1/stages` -- get rotting days config per stage
- `PUT /v1/deals/{id}` -- update custom fields (e.g., `stale_flag`, `days_inactive`)
- `POST /v1/activities` -- create follow-up reminder activity
- `POST /v1/notes` -- add automated note about staleness

**Logic:**
```
for each open deal:
  last_activity_date = max(deal.update_time, last_activity.due_date)
  days_inactive = today - last_activity_date
  stage_threshold = stage_rotting_config[deal.stage_id]
  if days_inactive > stage_threshold:
    - flag deal via custom field
    - create urgent follow-up activity for owner
    - send Slack/Telegram notification
    - if days_inactive > 2x threshold: escalate to manager
```

**Cron:** Every 6 hours

**Priority:** MUST-HAVE

---

### 1.2 Missing Fields Enforcement

**What it does:** Checks deals at each stage for required fields. Blocks progression (via alerts) if critical data is missing.

**Why it matters:** Garbage data = garbage forecasts. If a deal reaches "Proposal Sent" without a deal value, your pipeline report is fiction.

**API endpoints:**
- `GET /v2/deals` -- with `custom_fields` param to reduce payload
- `GET /v1/dealFields` -- get field definitions and required status
- `GET /v1/stages` -- map stage IDs to names
- `POST /v1/activities` -- create "fix data" task
- `POST /v1/notes` -- document what's missing

**Logic:**
```
required_fields_by_stage = {
  "Qualified": ["deal_value", "expected_close_date", "contact_person"],
  "Proposal Sent": ["deal_value", "proposal_url", "decision_maker"],
  "Negotiation": ["deal_value", "competitor_info", "budget_confirmed"],
}

for each open deal:
  stage_name = stages[deal.stage_id]
  missing = [f for f in required_fields_by_stage[stage_name] if not deal[f]]
  if missing:
    - create activity: "Complete missing fields: {missing}"
    - tag deal with "incomplete_data" label
```

**Cron:** Every 12 hours

**Priority:** MUST-HAVE

---

### 1.3 Duplicate Detection and Merge

**What it does:** Scans persons and organizations for duplicates using fuzzy matching on name, email, phone, domain. Merges automatically (or flags for review).

**Why it matters:** Duplicates fragment deal history and make contact outreach messy. Pipedrive's built-in dedup only catches exact matches and misses phone format variations.

**API endpoints:**
- `GET /v2/persons` -- cursor-paginated, get all contacts
- `GET /v1/persons/search` -- search by email/phone before creating new
- `PUT /v1/persons/{id}/merge` -- body: `{"merge_with_id": master_id}`
- `GET /v2/organizations` -- cursor-paginated
- `PUT /v1/organizations/{id}/merge` -- same pattern
- `GET /v1/duplicates/person` -- built-in duplicate finder (limited)

**Logic:**
```
# Pre-creation check (run on every new contact):
existing = search_persons(email=new_contact.email)
if existing:
  merge or skip creation

# Batch dedup scan:
all_persons = paginate(GET /v2/persons)
groups = cluster_by(normalize(name), normalize(email), normalize(phone))
for group in groups where len > 1:
  master = pick_most_complete(group)
  for duplicate in group:
    merge(duplicate.id, master.id)
```

**Phone normalization:** Strip spaces, dashes, parens. Convert to E.164 format.
**Email normalization:** Lowercase, strip `+alias` from Gmail.

**Cron:** Daily at 2 AM (batch). Real-time check on webhook `create.person`.

**Priority:** MUST-HAVE

---

### 1.4 Stage Validation Rules

**What it does:** When a deal moves to a new stage, validates that prerequisites are met. If not, reverts the move or creates a blocking task.

**Why it matters:** Prevents reps from pushing deals forward prematurely, which destroys conversion rate analytics.

**API endpoints:**
- Webhook: `update.deal` (check `previous` vs `current` stage_id)
- `PUT /v1/deals/{id}` -- revert stage if invalid
- `POST /v1/activities` -- create prerequisite task
- `POST /v1/notes` -- log validation failure

**Logic:**
```
stage_prerequisites = {
  "Demo Scheduled": ["contact_person_id is set", "has_activity_type:call"],
  "Proposal Sent": ["deal_value > 0", "custom_field:proposal_url is set"],
  "Negotiation": ["custom_field:decision_maker is set"],
}

on deal_updated(deal, previous):
  if deal.stage_id != previous.stage_id:
    new_stage = stages[deal.stage_id]
    violations = check_prerequisites(deal, stage_prerequisites[new_stage])
    if violations:
      - create activity listing violations
      - optionally revert: PUT deal.stage_id = previous.stage_id
      - notify owner
```

**Cron:** Real-time (webhook-driven)

**Priority:** NICE-TO-HAVE (implement after 1.1 and 1.2 are stable)

---

### 1.5 Deal Rot Prevention

**What it does:** Proactively creates activities for deals approaching their rot threshold. Escalates to manager if the deal owner doesn't act.

**Why it matters:** Prevention > detection. Catching deals 2 days before they rot gives reps time to act instead of firefighting.

**API endpoints:**
- Same as 1.1 (stale deal detection)
- `GET /v1/pipelines/{id}` -- get pipeline-level rot settings
- `POST /v1/activities` -- preventive follow-up

**Logic:**
```
for each open deal:
  days_to_rot = stage_threshold - days_inactive
  if days_to_rot <= 2 and days_to_rot > 0:
    create_activity(deal, "Deal will rot in {days_to_rot} days - take action")
  if days_to_rot <= 0:
    escalate_to_manager(deal)
```

**Cron:** Every 6 hours (can share the scan with 1.1)

**Priority:** MUST-HAVE

---

## 2. Activity Management

### 2.1 Auto-Create Follow-Up Activities After Stage Changes

**What it does:** When a deal moves to a new stage, automatically creates the appropriate next activity (call, email, meeting, etc.) with a smart due date.

**Why it matters:** Reps forget follow-ups. This guarantees every deal always has a next step.

**API endpoints:**
- Webhook: `update.deal` -- listen for stage changes
- `POST /v1/activities` -- create activity linked to deal
- `GET /v1/activityTypes` -- get available activity types

**Logic:**
```
stage_activities = {
  "Contact Made": {type: "call", due_delta_days: 1, subject: "Discovery call"},
  "Qualified": {type: "email", due_delta_days: 2, subject: "Send qualification summary"},
  "Demo Scheduled": {type: "meeting", due_delta_days: 0, subject: "Product demo"},
  "Proposal Sent": {type: "call", due_delta_days: 3, subject: "Follow up on proposal"},
  "Negotiation": {type: "call", due_delta_days: 2, subject: "Negotiation check-in"},
}

on deal_stage_changed(deal, new_stage):
  config = stage_activities[new_stage]
  create_activity(
    deal_id=deal.id,
    person_id=deal.person_id,
    org_id=deal.org_id,
    type=config.type,
    due_date=today + config.due_delta_days,
    subject=config.subject,
    user_id=deal.user_id  # assign to deal owner
  )
```

**Cron:** Real-time (webhook-driven)

**Priority:** MUST-HAVE

---

### 2.2 Meeting Prep Automation

**What it does:** Before a scheduled meeting activity, pulls all deal context (recent notes, emails, deal history, org info) and compiles a prep brief. Delivers via Slack/email.

**Why it matters:** Reps walking into calls unprepared lose deals. This takes 30 seconds to generate and saves 15 minutes of manual prep.

**API endpoints:**
- `GET /v1/activities` -- filter upcoming meetings (next 24h)
- `GET /v1/deals/{id}` -- deal details
- `GET /v1/deals/{id}/flow` -- deal activity timeline
- `GET /v1/persons/{id}` -- contact details
- `GET /v1/organizations/{id}` -- org details
- `GET /v1/notes` -- filter by deal_id, recent
- `GET /v1/deals/{id}/mailMessages` -- recent email threads

**Output template:**
```
MEETING PREP: {deal.title}
Company: {org.name} | Contact: {person.name} ({person.email})
Deal Value: {deal.value} | Stage: {stage.name} | Age: {deal_age} days
---
RECENT ACTIVITY (last 7 days):
- {activity_summary}
LAST 3 NOTES:
- {note_content_preview}
KEY CUSTOM FIELDS:
- Decision Maker: {deal.decision_maker}
- Budget: {deal.budget}
- Competitor: {deal.competitor}
---
SUGGESTED TALKING POINTS:
- [AI-generated based on deal stage and history]
```

**Cron:** Every hour (check for meetings in next 2 hours). Also trigger on activity creation of type `meeting`.

**Priority:** NICE-TO-HAVE (high impact but depends on notification infra)

---

### 2.3 Post-Call Note Templates

**What it does:** When a call activity is marked as done, creates a structured note template attached to the deal prompting the rep (or AI) to fill in outcomes.

**Why it matters:** Unstructured notes are useless for analytics. Templates enforce consistency.

**API endpoints:**
- Webhook: `update.activity` -- listen for `done=true` on call types
- `POST /v1/notes` -- create note linked to deal
- `PUT /v1/deals/{id}` -- update custom fields based on call outcome

**Note template:**
```
## Call Summary - {date}
**Attendees:** {person.name}
**Outcome:** [Positive / Neutral / Negative]
**Key Discussion Points:**
-
**Next Steps:**
-
**Deal Update Needed:** [Yes/No]
**Objections Raised:**
-
```

**Cron:** Real-time (webhook-driven)

**Priority:** NICE-TO-HAVE

---

### 2.4 Activity Completion Reminders

**What it does:** Sends reminders for overdue activities and activities due today. Escalates if overdue by >2 days.

**Why it matters:** Overdue activities = missed follow-ups = lost deals.

**API endpoints:**
- `GET /v2/activities` -- filter `done=0`, `due_date <= today`
- `GET /v1/users` -- get user contact info for notifications
- `POST /v1/activities` -- create escalation activity for manager

**Logic:**
```
overdue = GET activities where done=false AND due_date < today
due_today = GET activities where done=false AND due_date = today

for activity in due_today:
  send_reminder(activity.user_id, "Activity due today: {activity.subject}")

for activity in overdue:
  days_overdue = today - activity.due_date
  if days_overdue >= 1:
    send_reminder(activity.user_id, "OVERDUE ({days_overdue}d): {activity.subject}")
  if days_overdue >= 3:
    escalate_to_manager(activity)
```

**Cron:** 3x daily (9 AM, 1 PM, 5 PM)

**Priority:** MUST-HAVE

---

## 3. Lead Scoring & Prioritization

### 3.1 Scoring Model Design

**What it does:** Calculates a composite score for each deal/person based on weighted signals. Stores the score in a custom field for sorting and filtering.

**Why it matters:** Without scoring, reps work deals randomly instead of focusing on the highest-value opportunities.

**API endpoints:**
- `GET /v2/deals` -- get deal data with custom fields
- `GET /v2/persons` -- get contact engagement data
- `GET /v1/deals/{id}/flow` -- activity frequency
- `GET /v1/deals/{id}/mailMessages` -- email engagement
- `PUT /v1/deals/{id}` -- write score to custom field
- `GET /v1/dealFields` -- ensure score field exists
- `POST /v1/dealFields` -- create score field if needed

**Scoring model:**
```
SCORE COMPONENTS (total: 100 points max)

Deal Fit (40 points):
  - Deal value > median: +15
  - Has expected close date: +5
  - Expected close within 30 days: +10
  - Decision maker identified: +10

Engagement (35 points):
  - Email opened in last 7 days: +10
  - Email replied in last 7 days: +15
  - Had meeting in last 14 days: +10

Activity Freshness (25 points):
  - Activity in last 3 days: +15
  - Activity in last 7 days: +10
  - Activity in last 14 days: +5
  - No activity in 14+ days: 0

TIERS:
  80-100: HOT (immediate action)
  60-79: WARM (prioritize this week)
  40-59: COOL (nurture)
  0-39: COLD (review or close)
```

**Cron:** Every 4 hours

**Priority:** MUST-HAVE

---

### 3.2 Real-Time Score Updates

**What it does:** Updates deal scores immediately when key events happen (email reply, meeting completed, deal value changed) instead of waiting for the batch cron.

**Why it matters:** A deal that just replied to your email should jump to the top of the queue NOW, not in 4 hours.

**API endpoints:**
- Webhooks: `update.deal`, `create.activity`, `update.activity`, `create.note`
- `PUT /v1/deals/{id}` -- update score field
- Reuses scoring logic from 3.1

**Trigger events that recalculate:**
- Deal value changed
- Deal stage changed
- Activity created or completed
- Email received/opened (via mail tracking)
- Note added
- Person/org fields updated

**Cron:** Real-time (webhook-driven) + batch fallback every 4 hours

**Priority:** NICE-TO-HAVE (implement after 3.1 batch scoring works)

---

### 3.3 Priority Queue Generation

**What it does:** Generates a ranked list of deals per rep, sorted by score. Delivered as a daily digest via Slack/email/Telegram.

**Why it matters:** Tells each rep exactly what to work on first. No guessing.

**API endpoints:**
- `GET /v2/deals` -- filter `status=open`, include score custom field
- `GET /v1/users` -- get team members

**Output format:**
```
DAILY PRIORITY QUEUE - {rep_name} - {date}

HOT (action today):
1. {deal_title} | {org_name} | ${value} | Score: 92 | Due: {next_activity}
2. ...

WARM (action this week):
3. ...

NEEDS ATTENTION (stale/missing data):
- {deal_title} - missing: expected_close_date
```

**Cron:** Daily at 8 AM (per timezone of deal owner)

**Priority:** MUST-HAVE

---

### 3.4 Hot Lead Alerts

**What it does:** Instant notification when a deal score crosses the HOT threshold (80+), or when a previously cold deal jumps 20+ points.

**Why it matters:** Time-sensitive -- hot leads that sit for 24 hours go cold.

**API endpoints:**
- Triggered by 3.1/3.2 score calculation
- Notification via Slack API, Telegram Bot API, or Pipedrive webhook action

**Logic:**
```
on score_updated(deal, old_score, new_score):
  if new_score >= 80 and old_score < 80:
    alert(deal.user_id, "DEAL WENT HOT: {deal.title} (Score: {new_score})")
  if new_score - old_score >= 20:
    alert(deal.user_id, "SCORE SPIKE: {deal.title} jumped from {old_score} to {new_score}")
```

**Cron:** Real-time (triggered by scoring engine)

**Priority:** MUST-HAVE

---

## 4. Reporting & Analytics

### 4.1 Daily/Weekly Pipeline Reports

**What it does:** Generates pipeline snapshot reports showing total value, deal count, changes since last report, and key movements.

**Why it matters:** Managers need a pulse on pipeline health without logging into Pipedrive.

**API endpoints:**
- `GET /v2/deals` -- all open deals
- `GET /v1/pipelines` -- pipeline definitions
- `GET /v1/stages` -- stage definitions
- `GET /v1/deals/summary` -- aggregate stats (v1 only)
- `GET /v1/recents` -- recent changes across entity types

**Report template:**
```
PIPELINE REPORT - {date}

SNAPSHOT:
  Total Open Deals: {count} ({delta} vs last report)
  Total Pipeline Value: ${total} ({delta_pct}%)
  Weighted Value: ${weighted_total}

BY STAGE:
  | Stage | Deals | Value | Avg Age | Conversion |
  |-------|-------|-------|---------|------------|
  | ...   | ...   | ...   | ...     | ...        |

MOVEMENTS (since last report):
  Deals Won: {count} (${value})
  Deals Lost: {count} (${value}) -- top reasons: {loss_reasons}
  New Deals: {count} (${value})
  Stage Advances: {count}
  Stage Regressions: {count}

AT RISK:
  Stale Deals (>threshold): {count} (${value})
  Overdue Activities: {count}
```

**Cron:** Daily at 7 AM, Weekly summary on Monday 7 AM

**Priority:** MUST-HAVE

---

### 4.2 Win/Loss Analysis

**What it does:** Analyzes won and lost deals over a period, extracts patterns by loss reason, stage where lost, deal size, rep, and source.

**Why it matters:** Tells you where and why you're losing deals so you can fix the process.

**API endpoints:**
- `GET /v2/deals` -- filter `status=won` and `status=lost`, with date range
- `GET /v1/deals/{id}` -- get `lost_reason` field
- `GET /v1/dealFields` -- get loss reason options

**Metrics to compute:**
- Win rate overall and by rep
- Win rate by source/channel
- Average deal size (won vs lost)
- Most common loss reasons (ranked)
- Stage where deals are most often lost
- Time to close (won) vs time to lose (lost)

**Cron:** Weekly on Monday

**Priority:** MUST-HAVE

---

### 4.3 Velocity Metrics (Time in Stage)

**What it does:** Tracks how long deals spend in each stage. Identifies bottlenecks where deals get stuck.

**Why it matters:** If deals spend 15 days in "Proposal Sent" but only 2 days in every other stage, that's your bottleneck.

**API endpoints:**
- `GET /v1/deals/{id}/flow` -- deal timeline with stage changes and timestamps
- `GET /v2/deals` -- all deals (won + open) for analysis
- `GET /v1/stages` -- stage definitions

**Logic:**
```
for each deal:
  flow = GET deal_flow(deal.id)
  stage_durations = {}
  for each stage_change in flow:
    stage_durations[stage] = time_in_stage

aggregate:
  avg_time_per_stage = mean(all_deals.stage_durations)
  median_time_per_stage = median(all_deals.stage_durations)
  p90_time_per_stage = percentile(90, all_deals.stage_durations)
```

**Cron:** Weekly

**Priority:** NICE-TO-HAVE

---

### 4.4 Conversion Rates by Stage

**What it does:** Calculates stage-to-stage conversion rates to show pipeline funnel efficiency.

**Why it matters:** If 80% of deals pass "Qualified" but only 30% pass "Proposal Sent," you know where to coach your team.

**API endpoints:**
- Same as 4.3 (deal flow analysis)
- `GET /v1/deals/summary` -- can give basic stats

**Output:**
```
CONVERSION FUNNEL - {period}

Lead In -> Qualified: 65% (130/200)
Qualified -> Demo: 55% (71/130)
Demo -> Proposal: 70% (50/71)
Proposal -> Negotiation: 40% (20/50)  <-- BOTTLENECK
Negotiation -> Won: 75% (15/20)

Overall: 7.5% (15/200)
```

**Cron:** Weekly

**Priority:** MUST-HAVE

---

### 4.5 Revenue Forecasting

**What it does:** Projects revenue based on current pipeline, stage probabilities, and historical conversion rates.

**Why it matters:** "How much will we close this month?" -- every founder/manager asks this.

**API endpoints:**
- `GET /v2/deals` -- open deals with `expected_close_date` and `value`
- Historical conversion rates from 4.4

**Logic:**
```
stage_probability = {  # derived from historical data or manual input
  "Qualified": 0.20,
  "Demo Scheduled": 0.35,
  "Proposal Sent": 0.50,
  "Negotiation": 0.75,
  "Verbal Commit": 0.90,
}

forecast = 0
for deal in open_deals:
  if deal.expected_close_date within forecast_period:
    forecast += deal.value * stage_probability[deal.stage]

weighted_forecast = forecast
best_case = sum(deal.value for closing_this_period)
worst_case = sum(deal.value * prob for prob < 0.5 deals excluded)
```

**Cron:** Daily

**Priority:** MUST-HAVE

---

## 5. Integration Patterns

### 5.1 Webhook Setup for Real-Time Events

**What it does:** Registers webhooks for all critical events to enable real-time automations across this playbook.

**Why it matters:** Polling is wasteful and slow. Webhooks give you instant reactions.

**API endpoints:**
- `POST /v1/webhooks` -- register webhook
- `GET /v1/webhooks` -- list existing webhooks
- `DELETE /v1/webhooks/{id}` -- cleanup

**Webhooks to register:**
```
Required webhooks (max 40 per user):

| Event Object  | Event Action | Use Case |
|---------------|-------------|----------|
| deal          | create      | New deal scoring, dedup check |
| deal          | update      | Stage change, value change, score recalc |
| deal          | delete      | Cleanup related data |
| person        | create      | Dedup check, enrichment trigger |
| person        | update      | Score recalc |
| activity      | create      | Meeting prep trigger |
| activity      | update      | Post-call notes, follow-up creation |
| note          | create      | Score recalc |
| organization  | create      | Dedup, enrichment |
```

**Webhook endpoint requirements:**
- Must respond with 2xx within 10 seconds
- Retry policy: 3 retries at 3s, 30s, 150s intervals
- Auto-deleted after 3 consecutive days of failures
- Use HMAC signature validation for security

**Cron:** N/A (one-time setup, health-check daily)

**Priority:** MUST-HAVE (prerequisite for all real-time automations)

---

### 5.2 Email Integration

**What it does:** Syncs email conversations to Pipedrive, tracks opens/clicks, triggers automations on email events.

**Why it matters:** Email is the primary sales communication channel. Without sync, half your deal history is invisible.

**API endpoints:**
- `GET /v1/mailbox/mailThreads` -- get email threads
- `GET /v1/mailbox/mailMessages/{id}` -- get specific message
- `GET /v1/deals/{id}/mailMessages` -- emails linked to deal
- `POST /v1/mailbox/mailMessages` -- send email via Pipedrive (limited)

**Integration approach:**
- Use Pipedrive's native email sync (IMAP/Gmail/Outlook) for inbound/outbound tracking
- For automated email sending, use external provider (Resend, SendGrid) + log to Pipedrive via API
- Track opens/clicks via email provider, update deal score via webhook

**Cron:** Continuous (via email sync) + batch reconciliation daily

**Priority:** MUST-HAVE

---

### 5.3 Calendar Sync

**What it does:** Keeps Pipedrive activities in sync with Google Calendar / Outlook. Creates Pipedrive activities from calendar events and vice versa.

**Why it matters:** Reps live in their calendar, not in Pipedrive. Sync ensures activities are tracked without double-entry.

**API endpoints:**
- `GET /v2/activities` -- get activities with date range
- `POST /v1/activities` -- create from calendar events
- `PUT /v1/activities/{id}` -- update when calendar event changes

**Integration approach:**
- Use Pipedrive's native calendar sync feature first
- For custom sync: Google Calendar API + Pipedrive Activities API
- Match on: event title containing deal name, attendee email matching contact

**Cron:** Every 15 minutes (bidirectional sync check)

**Priority:** NICE-TO-HAVE (Pipedrive native sync covers most cases)

---

### 5.4 Slack/Telegram Notifications

**What it does:** Sends real-time notifications to Slack channels or Telegram chats for key CRM events.

**Why it matters:** Reps check Slack/Telegram 100x/day. Pipedrive notifications get buried.

**Notification events:**
```
DEAL EVENTS:
  - New deal created: #sales-pipeline
  - Deal won: #wins (with confetti)
  - Deal lost: #losses (with reason)
  - Deal stage advanced: owner DM
  - Deal went hot (score 80+): owner DM + #hot-leads

ACTIVITY EVENTS:
  - Activity overdue: owner DM
  - Meeting in 2 hours: owner DM with prep brief (see 2.2)

DATA QUALITY:
  - Duplicate detected: #data-quality
  - Missing required fields: owner DM
```

**Integration:**
- Slack: Use Slack Incoming Webhooks or Slack API `chat.postMessage`
- Telegram: Use Bot API `sendMessage` to chat_id
- Pipedrive native: Supports Slack as automation action

**Cron:** Real-time (triggered by webhooks and other automations)

**Priority:** MUST-HAVE

---

## 6. CRM Data Quality

### 6.1 Contact Enrichment

**What it does:** When a new person or organization is created, enriches the record with additional data (company size, industry, social profiles, etc.) using external APIs.

**Why it matters:** Reps waste time researching contacts manually. Enriched data also improves lead scoring accuracy.

**API endpoints:**
- Webhook: `create.person`, `create.organization`
- `PUT /v1/persons/{id}` -- update with enriched data
- `PUT /v1/organizations/{id}` -- update with enriched data
- External: Clearbit, Apollo, or similar enrichment API

**Fields to enrich:**
```
Person:
  - Job title
  - LinkedIn URL
  - Phone (if missing)

Organization:
  - Industry
  - Employee count
  - Annual revenue
  - Website
  - LinkedIn company page
  - Country/City
```

**Cron:** Real-time (webhook on create) + weekly batch for existing records missing data

**Priority:** NICE-TO-HAVE

---

### 6.2 Organization Matching

**What it does:** When a person is created with an email, automatically matches them to an existing organization by email domain. Creates the org if it doesn't exist.

**Why it matters:** Orphaned contacts (no org linked) break pipeline analysis by company.

**API endpoints:**
- Webhook: `create.person`
- `GET /v1/organizations/search` -- search by domain
- `PUT /v1/persons/{id}` -- link org_id
- `POST /v1/organizations` -- create org if needed

**Logic:**
```
on person_created(person):
  domain = extract_domain(person.email)
  if domain in free_email_providers:  # gmail, yahoo, etc.
    skip
  org = search_organizations(term=domain)
  if org:
    update_person(person.id, org_id=org.id)
  else:
    new_org = create_organization(name=domain_to_company_name(domain))
    update_person(person.id, org_id=new_org.id)
```

**Cron:** Real-time (webhook-driven)

**Priority:** MUST-HAVE

---

### 6.3 Email Verification

**What it does:** Validates email addresses on new and existing contacts. Flags invalid/risky emails.

**Why it matters:** Bounced emails hurt deliverability and waste time on dead leads.

**API endpoints:**
- `GET /v2/persons` -- batch scan
- `PUT /v1/persons/{id}` -- update email status custom field
- External: ZeroBounce, NeverBounce, or similar verification API

**Logic:**
```
on person_created(person):
  for email in person.emails:
    result = verify_email(email)
    if result.status == "invalid":
      flag_person(person.id, "invalid_email")
      create_activity("Fix invalid email for {person.name}")
    elif result.status == "risky":
      flag_person(person.id, "risky_email")
```

**Cron:** Real-time on creation + weekly batch for unverified contacts

**Priority:** NICE-TO-HAVE

---

### 6.4 Phone Number Formatting

**What it does:** Normalizes all phone numbers to E.164 international format. Flags invalid numbers.

**Why it matters:** Pipedrive's dedup misses duplicates when phone formats differ ("08 52 78 94 56" vs "0852789456"). Normalized numbers also enable click-to-call integrations.

**API endpoints:**
- `GET /v2/persons` -- batch scan
- `PUT /v1/persons/{id}` -- update normalized phone

**Logic:**
```
Use libphonenumber (or equivalent) to:
1. Parse the raw phone number with country context
2. Validate it
3. Format to E.164 (+420123456789)
4. Update the person record
5. Flag invalid numbers
```

**Cron:** Real-time on create/update + weekly batch cleanup

**Priority:** NICE-TO-HAVE

---

## 7. Sales Sequence Automation

### 7.1 Automatic Email Sequences Based on Deal Stage

**What it does:** Triggers pre-built email sequences when deals enter specific stages. Stops the sequence when the deal advances or the contact replies.

**Why it matters:** Manual follow-up emails are the #1 thing reps forget. Sequences ensure consistent outreach.

**API endpoints:**
- Webhook: `update.deal` (stage change)
- External email provider (Resend, SendGrid) for sending
- `POST /v1/notes` -- log sent emails
- `POST /v1/activities` -- create email activity record
- `GET /v1/deals/{id}/mailMessages` -- check for replies

**Sequence design:**
```
STAGE: "Proposal Sent"
  Day 0: "Here's your proposal" (auto-sent on stage entry)
  Day 3: "Quick follow-up on the proposal" (if no reply)
  Day 7: "Checking in -- any questions?" (if no reply)
  Day 14: "Last call on this proposal" (if no reply)

  STOP CONDITIONS:
  - Contact replied to any email
  - Deal moved to next stage
  - Deal marked lost
  - Manual override by rep

STAGE: "Contact Made"
  Day 0: Intro email
  Day 2: Value prop email
  Day 5: Case study email
  Day 10: Break-up email
```

**Cron:** Check sequence state and send pending emails every 30 minutes. Webhook-driven for stop conditions.

**Priority:** MUST-HAVE

---

### 7.2 Follow-Up Cadence Rules

**What it does:** Enforces a minimum and maximum follow-up cadence per deal stage. Alerts when reps are following up too aggressively or not enough.

**Why it matters:** Too many emails = annoying. Too few = deal goes cold. Cadence rules find the sweet spot.

**API endpoints:**
- `GET /v2/activities` -- get activity history per deal
- `GET /v1/deals/{id}/mailMessages` -- email history
- `POST /v1/activities` -- create follow-up if under-cadence
- Notification API for over-cadence warnings

**Cadence rules:**
```
stage_cadence = {
  "Qualified": {min_days: 2, max_days: 5},
  "Demo Scheduled": {min_days: 1, max_days: 3},
  "Proposal Sent": {min_days: 3, max_days: 7},
  "Negotiation": {min_days: 1, max_days: 4},
}

for each open deal:
  last_outreach = get_last_outreach_date(deal)
  days_since = today - last_outreach
  cadence = stage_cadence[deal.stage]

  if days_since > cadence.max_days:
    create_activity("Follow up overdue by {days_since - cadence.max_days} days")
  if days_since < cadence.min_days and has_pending_outreach:
    warn_rep("Too soon for follow-up. Wait {cadence.min_days - days_since} more days.")
```

**Cron:** Every 6 hours

**Priority:** NICE-TO-HAVE

---

### 7.3 Deal-Specific Copy Generation Triggers

**What it does:** When a deal reaches a stage that requires written communication (proposal, follow-up, break-up), triggers AI copy generation using deal context as input.

**Why it matters:** Personalized emails convert 2-3x better than templates. AI generation gives personalization at scale.

**API endpoints:**
- Webhook: `update.deal` (stage change triggers)
- `GET /v1/deals/{id}` -- deal context
- `GET /v1/persons/{id}` -- contact info
- `GET /v1/organizations/{id}` -- company context
- `GET /v1/notes` -- recent notes for context
- `POST /v1/notes` -- save generated copy as draft note
- External: Claude API for copy generation

**Trigger points:**
```
COPY GENERATION TRIGGERS:

"Proposal Sent" -> Generate:
  - Proposal email (personalized to deal specifics)
  - Pricing summary

"Negotiation" -> Generate:
  - Objection handling responses (based on noted objections)
  - Comparison document (vs competitors mentioned in notes)

"Lost" -> Generate:
  - Win-back email (scheduled for 30 days later)
  - Feedback request email

General -> Generate on demand:
  - Follow-up email based on last conversation notes
  - Meeting summary email
```

**Context to feed AI:**
- Deal title, value, stage
- Contact name, title, company
- Recent notes and conversation history
- Competitors mentioned
- Objections raised
- Products/services in the deal

**Cron:** Real-time (webhook-driven for stage changes) + on-demand via Slack command

**Priority:** NICE-TO-HAVE (high impact but requires Claude API integration)

---

## Implementation Priority Order

Execute in this order for maximum impact with minimum effort:

### Phase 1: Foundation (Week 1)
1. **5.1** Webhook setup (prerequisite for everything real-time)
2. **1.1** Stale deal detection
3. **1.2** Missing fields enforcement
4. **2.1** Auto follow-up activities on stage change
5. **2.4** Activity completion reminders

### Phase 2: Scoring & Reporting (Week 2)
6. **3.1** Lead scoring (batch)
7. **3.3** Priority queue generation
8. **3.4** Hot lead alerts
9. **4.1** Daily pipeline reports
10. **4.4** Conversion rates

### Phase 3: Data Quality (Week 3)
11. **1.3** Duplicate detection and merge
12. **6.2** Organization matching
13. **6.4** Phone number formatting
14. **1.5** Deal rot prevention
15. **4.5** Revenue forecasting

### Phase 4: Advanced (Week 4+)
16. **5.4** Slack/Telegram notifications
17. **7.1** Email sequences
18. **4.2** Win/loss analysis
19. **2.2** Meeting prep automation
20. **7.3** AI copy generation
21. **3.2** Real-time score updates
22. **6.1** Contact enrichment
23. **6.3** Email verification

---

## Architecture Notes for Agent Execution

### Agent Design Pattern
```
PipedriveAgent
  ├── WebhookListener (Express/Fastify server)
  │   ├── handles all registered webhooks
  │   ├── routes events to appropriate handlers
  │   └── validates HMAC signatures
  ├── CronScheduler (node-cron or similar)
  │   ├── schedules all batch jobs
  │   ├── prevents overlapping runs
  │   └── logs execution times
  ├── PipedriveClient (API wrapper)
  │   ├── handles auth (token rotation for OAuth)
  │   ├── rate limit awareness (read X-RateLimit headers)
  │   ├── automatic retry with exponential backoff
  │   ├── cursor pagination helper
  │   └── request queuing to stay under burst limits
  ├── NotificationService
  │   ├── Slack integration
  │   ├── Telegram integration
  │   └── Email (via Resend)
  ├── ScoringEngine
  │   ├── score calculation
  │   ├── threshold alerts
  │   └── score history tracking
  └── ReportGenerator
      ├── template rendering
      ├── metric calculations
      └── delivery scheduling
```

### Rate Limit Strategy
- Read `X-RateLimit-Remaining` and `X-RateLimit-Reset` headers on every response
- Queue requests with 100ms minimum interval between calls
- Use v2 endpoints (lower token cost) wherever possible
- Batch operations: process in chunks of 50 with 1s pauses
- Search endpoints: max 10 req/2s -- queue accordingly
- If 429 received: pause all requests, wait for reset, resume

### Data Storage
- Cache deal/person/org data locally (SQLite or Supabase) to reduce API calls
- Store score history for trend analysis
- Log all automation actions for audit trail
- Keep webhook event log for debugging

---

## Sources

- [Pipedrive API v1/v2 Reference](https://developers.pipedrive.com/docs/api/v1)
- [Pipedrive API v2 Migration Guide](https://pipedrive.readme.io/docs/pipedrive-api-v2-migration-guide)
- [Pipedrive Webhook Guide](https://pipedrive.readme.io/docs/guide-for-webhooks)
- [Pipedrive Webhook Guide v2](https://pipedrive.readme.io/docs/guide-for-webhooks-v2)
- [Pipedrive Rate Limiting](https://pipedrive.readme.io/docs/core-api-concepts-rate-limiting)
- [Pipedrive Rotting Feature](https://support.pipedrive.com/en/article/the-rotting-feature)
- [Pipedrive Scores Feature](https://support.pipedrive.com/en/article/scores)
- [Pipedrive Workflow Automation Conditions](https://support.pipedrive.com/en/article/workflow-automation-conditions)
- [Pipedrive Merge Duplicates](https://support.pipedrive.com/en/article/merge-duplicates)
- [Pipedrive Automations: 40 High-ROI Examples](https://insights.datomni.com/blog/pipedrive-automations/)
- [Pipedrive Workflow Automation Guide 2025](https://mazaal.ai/blog/pipedrive-workflow-automation-guide-2025)
- [Pipedrive Email Sync](https://support.pipedrive.com/en/article/email-sync)
- [Pipedrive Pipeline Management](https://www.pipedrive.com/en/blog/sales-pipeline-management)
- [Pipedrive Lead Scoring Guide](https://zeeg.me/en/blog/post/pipedrive-lead-scoring)
