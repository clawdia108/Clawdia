# Social Selling Skill

**Owner:** GrowthLab
**Version:** 1.0.0
**Type:** instruction_only

## Purpose
Systematic LinkedIn presence management — content strategy, profile optimization, prospect engagement, SSI tracking, and ABM support. Turn LinkedIn from a resume into a lead generation machine.

## Profile Optimization (Quarterly Audit)

### Checklist (scored 0–100)
| Element | Weight | Criteria |
|---------|--------|----------|
| Headline | 20 | Customer-focused, includes target keyword, <120 chars |
| Photo | 10 | Professional, high-res, approachable |
| Banner | 10 | Branded, communicates value prop |
| Summary | 20 | Problem-solution format, 2000 chars, keywords embedded |
| Experience | 15 | Challenge → Action → Result format, not duties |
| Skills | 10 | Top 3 aligned with what prospects search |
| Recommendations | 10 | 3+ from clients (not colleagues) |
| Custom URL | 5 | Claimed and clean |

### Keyword Strategy
- Extract top 20 keywords from: won deals in Pipedrive (industry terms), target prospect searches
- Embed naturally in headline, summary, experience
- Track search appearances before/after optimization

## Content Calendar

### Weekly Cadence
| Day | Content Type | Goal |
|-----|-------------|------|
| Monday | Industry insight post | Establish expertise |
| Wednesday | Case study / mini-story | Social proof |
| Friday | Engagement bait (question/poll) | Drive comments |

### Content Generation Rules
1. GrowthLab analyzes current deals by industry vertical
2. Claude generates 3 posts/week covering relevant pain points
3. Each post follows: Hook (1 line) → Insight (3-5 lines) → CTA (1 line)
4. Max 1300 characters (LinkedIn sweet spot)
5. No AI-sounding language (run through humanizer skill)
6. Josef reviews all posts before publishing

### Content Performance Tracking
- Track: impressions, likes, comments, shares, profile views generated
- Store in `experiments/social-content-log.md`
- Monthly: identify top 3 performing topics → double down

## Prospect Engagement System

### Daily Actions (15 min/day)
1. **Check profile viewers** → score against ICP → auto-create Pipedrive lead if fit
2. **Engage with prospect content** → like + thoughtful comment on 5 posts
3. **Accept/send connection requests** → max 15-20/day, all personalized

### Connection Request Templates
Personalized using prospect data. Selected by context:

| Context | Template Approach |
|---------|------------------|
| Mutual connection | "Hey [name], noticed we both know [mutual]. [Personalized note about their work]." |
| Content engagement | "Loved your post about [topic]. [Specific insight that adds value]." |
| Industry peer | "[Industry] professionals should stick together. [Relevant observation]." |
| Trigger event | "Congrats on [funding/hire/launch]. [Specific connection to what you do]." |

### Follow-First Strategy (for VP+ prospects)
1. Follow (don't connect yet)
2. Engage with 3 of their posts over 2 weeks
3. Then send connection request referencing their content
4. Message after accepted
- Track each prospect's state: following → engaged → connected → messaged → pipeline

## ABM Support

### Account Intelligence Monitoring
For high-tier target accounts, track:
- New job postings → signals growth areas / budget
- Leadership changes → new decision maker = new opportunity
- Company page posts → strategic priorities
- Employee growth/decline → expansion/contraction signals

### Per-Account Content Targeting
For top 10 ABM accounts:
- GrowthLab generates content themes matching their industry pain points
- Tag/mention relevant company contacts in posts when appropriate
- Track which account employees engage with content → fast-track to outreach

## SSI (Social Selling Index) Optimization

### Four Pillars
| Pillar | Actions to Improve |
|--------|-------------------|
| Establish brand | Complete profile, publish weekly content, get recommendations |
| Find right people | Use Sales Nav searches, connect with ICP matches daily |
| Engage with insights | Comment on industry posts, share articles, start discussions |
| Build relationships | Message connections, engage regularly, multi-touch nurture |

### Targets
- SSI goal: >70 (currently puts you in top 5% of industry)
- Track weekly, identify lowest pillar, prescribe 3 actions

## KPI Dashboard

### Weekly Metrics (tracked in `experiments/social-selling-kpi.md`)
| Metric | Target | Measurement |
|--------|--------|-------------|
| Connection requests sent | 75/week | Manual + automated count |
| Acceptance rate | >40% | Accepted / sent |
| Content posts published | 3/week | Published count |
| Avg engagement rate | >3% | (likes+comments) / impressions |
| Profile views | >200/week | LinkedIn analytics |
| Conversations started | 10/week | Messages that got replies |
| Meetings booked from social | 2/week | Calendar + Pipedrive source |

## Integration
- **cadence-engine**: LinkedIn touches integrated into multi-channel sequences
- **lead-scoring**: LinkedIn engagement adds +5 per meaningful interaction
- **sentiment-classifier**: LinkedIn message replies classified same as email
- **deal-health**: Social engagement counts toward engagement score

## Output Files
- `experiments/social-content-log.md` — Content performance
- `experiments/social-selling-kpi.md` — Weekly KPIs
- `intel/LINKEDIN_PROSPECTS.md` — Hot prospects from profile views
- Content drafts queued for Josef review
