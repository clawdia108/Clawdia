# Revenue Machine Playbook

**Target:** €20,000/month primary · €13,000/month floor
**Owner:** Bridge (orchestration) + all revenue agents
**Version:** 1.0.0
**Created:** 2026-03-04

## Revenue Math

### What €20K/month requires
| Metric | Conservative | Aggressive |
|--------|-------------|------------|
| Avg deal size | €4,000 | €6,000 |
| Deals to close | 5/month | 3-4/month |
| Win rate | 30% | 40% |
| Proposals needed | 17/month | 8-10/month |
| Qualified leads needed | 25/month | 15/month |
| Top-of-funnel leads | 80/month | 40/month |

### What €13K floor requires
| Metric | Value |
|--------|-------|
| Deals to close | 3/month at €4,300 avg |
| Proposals needed | 10/month at 30% win |
| Qualified leads needed | 15/month |

## The 30-Day Activation Plan

### Week 1: Foundation (Days 1-7)

**DealOps tasks:**
- [ ] Run lead-scoring across all active Pipedrive contacts — classify into Hot/Warm/Cool/Cold
- [ ] Run deal-health scoring on all open deals — identify at-risk deals immediately
- [ ] Set up Pipedrive custom fields: `cadence_type`, `cadence_step`, `cadence_last_touch`, `cadence_next_touch`, `lead_score`, `deal_health_score`
- [ ] Generate SPIN pre-call briefs for all calls scheduled this week

**InboxForge tasks:**
- [ ] Classify all unread replies using sentiment-classifier
- [ ] Identify any replies sitting in inbox with buying signals → fast-track to Bridge
- [ ] Set up cadence state for all active prospects (who's in what sequence?)

**GrowthLab tasks:**
- [ ] Run LinkedIn profile audit using social-selling checklist
- [ ] Generate first week of LinkedIn content (3 posts)
- [ ] Identify top 10 ABM target accounts → begin intelligence monitoring

**Bridge:**
- [ ] Review all hot deals — are cadences running? Are next steps scheduled?
- [ ] Review at-risk deals — what intervention is needed?
- [ ] Set up daily 15-min social selling routine

### Week 2: Cadence Launch (Days 8-14)

**InboxForge + Bridge:**
- [ ] Launch cold outreach cadences for Cool/Cold leads that match ICP
- [ ] Launch warm follow-up cadences for anyone who engaged but hasn't booked
- [ ] Launch deal nurture cadences for all in-pipeline deals
- [ ] Set up A/B testing on first cold email (professional vs. casual tone)

**DealOps:**
- [ ] Generate pre-call briefs for all scheduled calls
- [ ] Track advance vs. continuation for every call this week
- [ ] Re-score all leads after week 1 activity data

**GrowthLab:**
- [ ] Execute follow-first strategy on 10 VP+ targets
- [ ] Engage with 5 prospect posts daily (like + comment)
- [ ] Send 15-20 connection requests/day (personalized templates)

### Week 3: Pitch & Close (Days 15-21)

**GrowthLab + Bridge:**
- [ ] Generate pitch deck for top 3 hottest deals using pitch-builder
- [ ] Build proposal using Klaff 20-minute structure
- [ ] Prepare pricing with anchoring-first strategy (premium → standard → starter)
- [ ] Pre-load intrigue stories matching each prospect's industry

**DealOps:**
- [ ] Frame detection on all prospect communications this week
- [ ] Auto-counter any power/time/analyst frames detected
- [ ] Track objections → map to intrigue story bank
- [ ] Use concession bank strategically (max 2 per deal, never with discount)

**InboxForge:**
- [ ] Build rapport sequences for new high-value prospects (3-touch before pitch)
- [ ] Monitor reply sentiment — flag any stress/negative signals
- [ ] Ensure cognitive load rules: max 3 decision points per email, 1 CTA

### Week 4: Optimize & Scale (Days 22-30)

**KnowledgeKeeper:**
- [ ] Compile month's learnings: what worked, what didn't
- [ ] Update SPIN question banks with new questions from actual calls
- [ ] Add new stories to intrigue bank from won deals
- [ ] Update concession effectiveness data

**Bridge:**
- [ ] Review A/B test results → promote winners
- [ ] Review cadence performance → adjust timing/content for underperformers
- [ ] Review SSI score → identify lowest pillar → prescribe 3 actions
- [ ] Run full pipeline review: deal health across all stages

**GrowthLab:**
- [ ] Publish content performance report → double down on top 3 topics
- [ ] Review LinkedIn analytics: profile views, connection acceptance rate
- [ ] Identify any prospect content engagement → fast-track to outreach

## Daily Operating Rhythm

### Morning (automated, 07:00)
1. **KnowledgeKeeper** generates `USER_DIGEST_AM.md`:
   - Pipeline snapshot (total, weighted, changes from yesterday)
   - Hot deals requiring attention today
   - At-risk deals with recommended actions
   - Today's scheduled cadence touches
   - LinkedIn engagement queue (5 posts to engage with)

2. **DealOps** generates pre-call briefs for any calls/meetings today

3. **InboxForge** classifies overnight replies → routes to appropriate cadence step

### Midday (Josef action, 15 min)
1. Execute LinkedIn engagement (5 posts — like + comment)
2. Review and approve any pending first-touch messages
3. Review any proposals queued for send

### Evening (automated, 18:00)
1. **KnowledgeKeeper** generates `USER_DIGEST_PM.md`:
   - What happened today (deals advanced, emails sent, meetings held)
   - Lead score changes
   - Tomorrow's calendar + prep needed
   - Cadence touches completed vs. planned

## Kill Metrics (stop and reassess if)

| Metric | Danger Zone | Action |
|--------|------------|--------|
| Reply rate | <5% after 100 sends | Stop cadence, rewrite all templates, check deliverability |
| Meeting book rate | <10% of warm leads | Review follow-up quality, check timing |
| Win rate | <15% | Review qualification criteria, tighten ICP |
| Deal health avg | <40 across pipeline | Deep-dive on stuck deals, consider pricing/positioning change |
| LinkedIn acceptance | <20% | Review connection request templates, check profile |
| Cadence completion | <50% get to step 3+ | Check content quality, reduce friction |

## Agent Coordination Map

```
                    ┌─────────────┐
                    │   Bridge    │
                    │ orchestrate │
                    └──────┬──────┘
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌──────────┐   ┌──────────────┐  ┌──────────┐
    │ DealOps  │   │  InboxForge  │  │ GrowthLab│
    │ score +  │   │  classify +  │  │ content + │
    │ qualify  │   │  sequence    │  │ research  │
    └────┬─────┘   └──────┬───────┘  └─────┬────┘
         │                │                 │
         ▼                ▼                 ▼
   ┌──────────┐   ┌──────────────┐   ┌──────────┐
   │ Pipedrive│   │    Gmail     │   │ LinkedIn │
   │  CRM     │   │  + cadence   │   │ + social │
   └──────────┘   └──────────────┘   └──────────┘
         │                │                 │
         └────────────────┼─────────────────┘
                          ▼
                   ┌──────────────┐
                   │   Timebox    │
                   │  scheduling  │
                   └──────┬───────┘
                          ▼
                   ┌──────────────┐
                   │  Reviewer    │
                   │  QA + learn  │
                   └──────┬───────┘
                          ▼
                   ┌──────────────┐
                   │ Knowledge    │
                   │ Keeper       │
                   │ consolidate  │
                   └──────────────┘
```

## Skill Dependencies

| Skill | Feeds Into | Gets Data From |
|-------|-----------|----------------|
| lead-scoring | cadence-engine (intensity), deal-health (momentum) | sentiment-classifier, pipedrive-api |
| sentiment-classifier | lead-scoring (+signals), cadence-engine (routing) | gog (email replies) |
| deal-health | Bridge alerts, revenue dashboard | lead-scoring, pipedrive-api, sentiment-classifier |
| cadence-engine | InboxForge (email queue), GrowthLab (LinkedIn queue) | lead-scoring (intensity), sentiment (backoff) |
| spin-questions | DealOps (pre-call briefs) | pipedrive-api, knowledge-sync |
| pitch-builder | proposals, pricing recs | deal-health, spin-questions, sentiment-classifier |
| social-selling | LinkedIn content + engagement | cadence-engine, lead-scoring, pipedrive-api |

## Revenue Pipeline Targets

| Stage | Target Count | Avg Value | Total Value |
|-------|-------------|-----------|-------------|
| Lead In | 25+ | €2,000 | €50,000 |
| Qualified | 12+ | €4,000 | €48,000 |
| Proposal | 6+ | €5,000 | €30,000 |
| Negotiation | 3+ | €6,000 | €18,000 |
| **Won (monthly)** | **5** | **€4,000** | **€20,000** |

Pipeline coverage ratio target: **3x** (€60K weighted pipeline for €20K target)

## Output Files

- `pipedrive/PIPELINE_STATUS.md` — Daily pipeline snapshot
- `pipedrive/DEAL_HEALTH.md` — Deal health scores
- `pipedrive/SCORING_LOG.md` — Lead score changes
- `inbox/FOLLOW_UPS.md` — Today's cadence touches
- `intel/DAILY-INTEL.md` — Market signals and triggers
- `intel/LINKEDIN_PROSPECTS.md` — Hot LinkedIn prospects
- `experiments/cadence-ab-log.md` — A/B test results
- `experiments/social-content-log.md` — Content performance
- `experiments/social-selling-kpi.md` — Social selling metrics
- `knowledge/USER_DIGEST_AM.md` — Morning briefing
- `knowledge/USER_DIGEST_PM.md` — Evening summary
