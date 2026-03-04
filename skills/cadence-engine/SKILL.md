# Cadence Engine Skill

**Owner:** Bridge (orchestrator) + InboxForge (execution)
**Version:** 1.0.0
**Type:** instruction_only

## Purpose
Multi-channel outreach sequencing with adaptive timing, A/B testing, and lead-score-driven intensity. Replaces ad-hoc follow-ups with systematic prospect engagement.

## Cadence Types

### 1. Cold Outreach (new prospect, no prior contact)
| Day | Channel | Touch | Content Strategy |
|-----|---------|-------|-----------------|
| 1 | LinkedIn | Profile view + Connect request | Personalized note (<300 chars) |
| 3 | Email | Value-first email #1 | Pain point + insight (no pitch) |
| 5 | LinkedIn | Message (if connected) | Reference shared content/connection |
| 8 | Email | Case study email #2 | Social proof for their industry |
| 12 | Email | Break-up email #3 | "Should I close your file?" |
| 15 | LinkedIn | Engage with their content | Like/comment on recent post |
| 20 | Email | Re-engagement #4 | New angle, different value prop |

### 2. Warm Follow-up (replied or engaged, not yet meeting)
| Day | Channel | Touch | Content Strategy |
|-----|---------|-------|-----------------|
| 0 | Email | Reply within 1 hour | Address their question/interest |
| 2 | Email | Value add | Relevant resource or insight |
| 5 | Calendar | Meeting invite | Propose specific time slot |
| 7 | LinkedIn | Soft touch | Engage with their content |
| 10 | Email | Re-propose meeting | Different time, lower commitment |

### 3. Deal Nurture (in pipeline, between meetings)
| Day | Channel | Touch | Content Strategy |
|-----|---------|-------|-----------------|
| +1 after meeting | Email | Summary + next steps | Meeting recap, confirmed actions |
| +3 | Email | Value drop | Relevant article/insight for their pain |
| +7 | Email | Check-in | "Any questions on the proposal?" |
| +14 | LinkedIn | Soft touch | Content engagement |
| +21 | Email | Re-engage | New case study or trigger event |

### 4. Re-engagement (went dark / "not now")
| Day | Channel | Touch | Content Strategy |
|-----|---------|-------|-----------------|
| 30 | Email | "Thought of you" | Trigger event or industry news |
| 60 | LinkedIn | Reconnect | Engage with their content first |
| 75 | Email | New value prop | Different angle than original |
| 90 | Email | Final check | "Has anything changed?" |

## Adaptive Rules

### Lead Score → Cadence Intensity
| Score | Interval | Max Touches/Week |
|-------|----------|-----------------|
| 🔥 80–100 | Daily | 5 |
| 🟡 50–79 | Every 3 days | 3 |
| 🔵 25–49 | Weekly | 1 |
| ⚪ 0–24 | Monthly | 0.5 |

### Backoff Rules
1. Bounce detected → pause email, switch to LinkedIn only
2. No open after 3 emails → change subject line approach
3. Opened but no reply after 3 → try different channel
4. Explicit "not now" → pause 30 days minimum
5. Unsubscribe → remove from ALL cadences permanently

### A/B Testing Framework
- Every cadence email generates 2 variants (via Claude API)
- Variant A: direct/professional tone
- Variant B: casual/conversational tone
- Split 50/50, track open + reply rates
- After 50 sends per variant → promote winner, generate new challenger
- Results logged in `experiments/cadence-ab-log.md`

## Anti-Spam Quality Gate
Before any message is queued for send:
1. Claude scores message on: value-to-pitch ratio, personalization depth, length appropriateness
2. Messages scoring <60/100 get rewritten
3. Daily send limits enforced: max 50 cold emails, max 20 LinkedIn messages
4. Domain health check before batch sends (SPF/DKIM/bounce rate)

## State Management
- Each prospect has a cadence state in Pipedrive custom fields:
  - `cadence_type`: cold | warm | nurture | reengagement | paused
  - `cadence_step`: current step number
  - `cadence_last_touch`: timestamp
  - `cadence_next_touch`: scheduled timestamp
  - `cadence_channel`: email | linkedin | phone | mixed

## Output
- `inbox/FOLLOW_UPS.md` — Today's queued touches
- Pipedrive activities created for each touch
- Daily cadence summary in `knowledge/EXECUTION_STATE.json`
- A/B test results in `experiments/cadence-ab-log.md`

## Review Gates
- Cold outreach to new prospects → Tier 2 (notify, auto-send unless vetoed in 2h)
- First message to any contact → Tier 3 (require Josef approval)
- Follow-up in existing thread → Tier 1 (auto-execute)
- Re-engagement after 30+ days dark → Tier 2
