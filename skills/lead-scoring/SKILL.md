# Lead Scoring Skill

**Owner:** DealOps
**Version:** 1.0.0
**Type:** instruction_only

## Purpose
Multi-factor lead scoring system using Pipedrive behavioral + firmographic signals. Produces a 0–100 composite score per contact/deal.

## Scoring Model

### Signal Weights (total = 100)

| Signal | Weight | Source | Decay |
|--------|--------|--------|-------|
| Email reply speed (<1h) | 15 | Pipedrive activities | 7d half-life |
| Email opens (3+) | 10 | Pipedrive email tracking | 14d half-life |
| Meeting booked | 20 | Pipedrive activities | 30d half-life |
| Deal stage velocity (above avg) | 15 | Pipedrive deal stages | None |
| Multi-stakeholder (2+ contacts) | 10 | Pipedrive persons/org | None |
| Budget confirmed | 15 | Pipedrive custom field | None |
| Company size fit (ICP match) | 10 | Pipedrive org data | None |
| Recent trigger event | 5 | intel/MARKET_SIGNALS.md | 14d half-life |

### Score Tiers

| Tier | Range | Action |
|------|-------|--------|
| 🔥 Hot | 80–100 | Immediate follow-up. Bridge alerts Josef. |
| 🟡 Warm | 50–79 | Active nurture sequence. InboxForge queues touchpoint. |
| 🔵 Cool | 25–49 | Standard cadence. Monitor for signals. |
| ⚪ Cold | 0–24 | Low priority. Re-score in 30 days. |

## Execution

### Input
- Pipedrive deal/contact data (via pipedrive-api skill)
- Activity history (emails, calls, meetings)
- intel/MARKET_SIGNALS.md (trigger events)

### Output
- `pipedrive/SCORING_LOG.md` — Updated scores with change deltas
- Pipedrive custom field `lead_score` updated via API
- Top 10 hottest leads surfaced in `knowledge/EXECUTION_STATE.json`

### Schedule
- Daily recalculation at 07:00 CET (weekdays)
- Real-time bump when: meeting booked, reply received, deal stage advanced

## Rules
1. Score decays over time (half-life per signal)
2. Never score above 90 without human confirmation of budget
3. Negative signals: bounced email (-10), unsubscribe (-50), "not interested" reply (-30)
4. New leads start at 15 (base score for being in pipeline)
5. Score changes >20 points trigger Bridge notification

## Buying Signal Triggers (signal-based selling — 2x conversion vs static lists)
When detected, immediately bump score and trigger cadence:

| Signal | Score Bump | Source | Action |
|--------|-----------|--------|--------|
| HR job posting | +25 | Web scrape / LinkedIn | Immediate personalized outreach |
| Funding announcement | +20 | Crunchbase / news | Congratulations email + Echo Pulse pitch |
| New CEO/CHRO/VP HR | +20 | LinkedIn job changes | "New leaders want data" angle |
| Glassdoor complaints | +15 | Glassdoor monitoring | "We help companies like yours" |
| Competitor evaluation (G2 visit) | +15 | G2 / Capterra signals | Competitive positioning email |
| Growth milestone (50/100/200+) | +10 | LinkedIn headcount | "At your size, informal breaks down" |
| Video message viewed | +10 | Loom/Vidyard analytics | Follow-up within 24h |
| LinkedIn post engagement | +5 | LinkedIn activity | Comment + DM follow-up |
| Website visit (behavera.com) | +10 | Analytics | Auto-trigger warm cadence |

## ADHD-Friendly Score Display
For Josef's dashboard and morning briefing:
- 🔥 HOT (80-100): RED — call TODAY, these are money
- 🟡 WARM (50-79): YELLOW — touch this week
- 🔵 COOL (25-49): BLUE — let cadence engine handle it
- ⚪ COLD (0-24): GREY — ignore until signal detected

Show max 5 hot leads in morning briefing. More = decision paralysis for ADHD brain.

## Integration with Other Skills
- **cadence-engine**: Score determines cadence intensity (hot = daily, warm = 3-day, cool = weekly)
- **sentiment-classifier**: Positive sentiment adds +5 bonus, negative subtracts -10
- **deal-health**: Score feeds into overall deal health calculation
- **spin-sales-prep**: Hot leads auto-trigger SPIN prep generation
- **pitch-builder**: Score determines pitch aggressiveness level

## Knowledge Sources
- `knowledge/COPYWRITER_KNOWLEDGE_BASE.md` — ICP definition, persona details
- `intel/MARKET_SIGNALS.md` — trigger events and industry signals
