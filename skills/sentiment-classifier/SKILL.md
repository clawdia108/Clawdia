# Sentiment Classifier Skill

**Owner:** InboxForge
**Version:** 1.0.0
**Type:** instruction_only

## Purpose
Classify incoming prospect communications by sentiment, emotional tone, frame dynamics, and urgency. Drives automated routing, deal health scoring, and response strategy.

## Classification Dimensions

### 1. Reply Sentiment (primary)

| Label | Signal Patterns | Auto-Action |
|-------|----------------|-------------|
| **positive_interested** | Questions about pricing, timeline, next steps, "let's schedule" | → DealOps: bump lead score +15, advance stage |
| **objection** | "Too expensive", "not the right time", "using competitor X" | → Queue objection-handling response template |
| **not_now** | "Circle back in Q3", "maybe later", "not a priority" | → Timebox: schedule re-engagement 30/60/90 days |
| **unsubscribe** | "Remove me", "stop emailing", "not interested" | → Remove from all sequences, log in CRM |
| **auto_reply** | OOO, vacation, auto-response patterns | → Ignore, retry after return date if detected |
| **neutral** | Informational, forwarding to colleague, requesting materials | → Continue current cadence |

### 2. Frame Detection (from Pitch Anything / Klaff)

| Frame | Detection Patterns | Counter-Strategy |
|-------|-------------------|-----------------|
| **power_frame** | Demanding tone, "we need X by Y", one-word responses | → Prize Frame response: position as selective |
| **time_frame** | Artificial urgency, deadline pressure | → Disrupt: slow down, reframe value |
| **analyst_frame** | Requesting ROI spreadsheets, detailed comparisons prematurely | → Intrigue: share brief success story instead |
| **prize_frame** (ours) | Prospect asking "how do I work with you?" | → Maintain: qualify them back |
| **moral_authority** | Appealing to fairness, standards, industry norms | → Acknowledge + redirect to unique value |

### 3. Stress/Urgency Detection (from Negotiation Neuroscience)

| Level | Signals | Response Adjustment |
|-------|---------|-------------------|
| **high_stress** | Short/terse, ALL CAPS, exclamation marks, contradictions | → De-escalate: empathy first, simplify ask |
| **medium_stress** | Delayed response after fast cadence, vague answers | → Reduce cognitive load: one question max |
| **low_stress** | Normal patterns, engaged, thoughtful responses | → Continue normally |

### 4. Buying Signal Detection

| Signal | Pattern | Action |
|--------|---------|--------|
| **budget_signal** | Mentions budget, allocation, "what does it cost" | → DealOps: flag budget confirmed |
| **authority_signal** | "I'll need to check with...", mentions boss/team | → Map stakeholders, suggest multi-thread |
| **need_signal** | Describes specific pain point or use case | → Log need, match to SPIN implication |
| **timeline_signal** | "We're looking to start by...", deadline mention | → Timebox: calendar the close date |

## Execution

### Input
- Incoming email text (via gog/InboxForge)
- Historical conversation context (last 5 messages)
- Deal stage from Pipedrive

### Output
- Classification JSON appended to deal activity notes
- Sentiment trend stored in `pipedrive/SCORING_LOG.md`
- Frame alerts routed to Bridge for high-value deals
- Buying signals pushed to DealOps for scoring

### Prompt Template
```
Classify this prospect reply across 4 dimensions:
1. Sentiment: positive_interested | objection | not_now | unsubscribe | auto_reply | neutral
2. Frame: power_frame | time_frame | analyst_frame | prize_frame | moral_authority | none
3. Stress: high_stress | medium_stress | low_stress
4. Buying signals: budget_signal | authority_signal | need_signal | timeline_signal | none

Context: [deal stage], [last 3 messages summary]
Reply text: [incoming message]

Output JSON only.
```

## Rules
1. Never auto-respond to objections without review (review gate: external_message)
2. Unsubscribe classification triggers immediate removal — no override
3. Frame detection only runs on deals >2k EUR (don't over-optimize small deals)
4. Stress detection triggers de-escalation template, not silence
5. All classifications logged for feedback loop (Reviewer tracks accuracy monthly)
