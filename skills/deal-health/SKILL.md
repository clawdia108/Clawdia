# Deal Health Skill

**Owner:** DealOps
**Version:** 1.0.0
**Type:** instruction_only

## Purpose
Compute a composite deal health score combining pipeline velocity, engagement patterns, sentiment trends, and risk signals. Predict stalls and trigger interventions.

## Health Dimensions

### 1. Velocity Score (0–25)
| Factor | Points | Measurement |
|--------|--------|-------------|
| Stage progression on pace | 10 | Days in current stage vs historical avg |
| Activity frequency above baseline | 10 | Activities/week vs pipeline avg |
| No activity gaps >5 days | 5 | Gap detection from Pipedrive |

### 2. Engagement Score (0–25)
| Factor | Points | Measurement |
|--------|--------|-------------|
| Reply rate >30% | 10 | Emails sent vs replies received |
| Meeting attendance 100% | 10 | Scheduled vs attended |
| Multi-threaded (2+ contacts) | 5 | Distinct contacts in deal |

### 3. Qualification Score (0–25)
| Factor | Points | Measurement |
|--------|--------|-------------|
| Budget confirmed | 10 | Pipedrive custom field or buying signal |
| Decision maker identified | 5 | Contact role mapping |
| Timeline established | 5 | Close date set and realistic |
| Need articulated (SPIN) | 5 | Need-payoff question answered |

### 4. Momentum Score (0–25)
| Factor | Points | Measurement |
|--------|--------|-------------|
| Sentiment trending positive | 10 | sentiment-classifier trend (last 3 msgs) |
| Lead score increasing | 10 | lead-scoring week-over-week delta |
| Advance (not continuation) | 5 | Last interaction resulted in concrete next step |

## Health Tiers

| Tier | Score | Color | Action |
|------|-------|-------|--------|
| 💚 Healthy | 75–100 | Green | Maintain cadence, prioritize close |
| 🟡 At Risk | 50–74 | Yellow | Increase touchpoints, check sentiment |
| 🟠 Stalling | 25–49 | Orange | Re-engagement sequence, change angle |
| 🔴 Critical | 0–24 | Red | Last-effort outreach or disqualify |

## Advance vs Continuation Tracking (SPIN Selling)

Every deal interaction is classified:
- **Advance**: Concrete next step agreed (meeting booked, proposal requested, trial started)
- **Continuation**: Positive vibes but no commitment ("sounds good", "let's stay in touch")
- **No-sale**: Deal explicitly lost or disqualified

Rules:
- 3 consecutive Continuations → auto-downgrade health by 15 points
- Continuation after Advance → flag as "losing momentum"
- Only Advances count toward stage progression

## Churn Prediction Signals

| Signal | Risk Level | Trigger |
|--------|-----------|---------|
| No reply in 7+ days after 2 follow-ups | High | InboxForge re-engagement |
| Sentiment declining 3 messages in a row | Medium | Change approach angle |
| Deal in same stage >2x average duration | High | Bridge escalation to Josef |
| Single-threaded + decision maker silent | Critical | Multi-thread immediately |
| Competitor mentioned + price objection | High | Value reframe + case study |

## Output

### Files Updated
- `pipedrive/HYGIENE_REPORT.md` — Deal health scores per deal
- `knowledge/EXECUTION_STATE.json` — Health distribution summary
- Pipedrive custom field `deal_health` — 0–100 score
- Pipedrive custom field `deal_risk` — low/medium/high/critical

### Dashboard Integration
- Deal health heatmap on Dashboard page
- At-risk deals highlighted in Hot Tasks
- Health trend sparklines per deal

### Schedule
- Full recalculation: daily 07:30 CET
- Incremental updates: on any Pipedrive activity webhook
