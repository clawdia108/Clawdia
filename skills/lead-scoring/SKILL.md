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

## Integration with Other Skills
- **cadence-engine**: Score determines cadence intensity (hot = daily, warm = 3-day, cool = weekly)
- **sentiment-classifier**: Positive sentiment adds +5 bonus, negative subtracts -10
- **deal-health**: Score feeds into overall deal health calculation
