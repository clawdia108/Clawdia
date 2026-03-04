# SPIN Questions Skill

**Owner:** DealOps
**Version:** 1.0.0
**Type:** instruction_only

## Purpose
Auto-generate SPIN-sequenced discovery questions (Situation → Problem → Implication → Need-payoff) based on deal context. Produce pre-call briefings that make every discovery call 3x more effective.

## SPIN Framework (Rackham)

### S — Situation Questions (LIMIT TO 2 MAX)
- Purpose: Understand current state
- Rule: Research first, ask second. KnowledgeKeeper pre-enriches contacts so we don't waste call time on questions we can answer ourselves.
- Template: "How do you currently handle [specific process]?"
- Anti-pattern: Never ask generic "tell me about your company" — we already know.

### P — Problem Questions (3-4 per call)
- Purpose: Surface dissatisfaction with current state
- Template: "What challenges do you face with [process from Situation]?"
- Template: "Where does [current approach] fall short?"
- Template: "What's frustrating about [specific area]?"
- Rule: Listen for emotional language — that's where the pain is.

### I — Implication Questions (THE MONEY MAKER — 3-5 per call)
- Purpose: Connect small problems to big consequences
- Template: "If [problem] continues, what impact does that have on [revenue/team/timeline]?"
- Template: "How does [problem] affect your ability to [strategic goal]?"
- Template: "What happens to [downstream process] when [problem] occurs?"
- Rule: This is where large deals are won. Implication Questions have the strongest correlation with sales success above $500.

### N — Need-payoff Questions (2-3 per call)
- Purpose: Get the buyer to articulate the value of solving the problem
- Template: "If you could [solve problem], what would that mean for [metric]?"
- Template: "How would [desired outcome] impact your [department/revenue/efficiency]?"
- Template: "What would it be worth to eliminate [problem]?"
- Rule: Let THEM sell the solution to themselves. The buyer's own words are 10x more persuasive than yours.

## Pre-Call Brief Generation

### Input
- Deal data from Pipedrive (stage, value, notes, activities)
- Contact data (role, company, industry)
- Previous call notes (if any)
- intel/MARKET_SIGNALS.md (company triggers)
- KnowledgeKeeper enrichment data

### Output Format
```
## Pre-Call Brief: [Company] / [Contact Name]
**Deal:** [value] | **Stage:** [current] | **Health:** [score]

### What We Already Know (DON'T ask these)
- [Company details, recent news, tech stack, team size]

### SPIN Questions for This Call

**Situation (max 2):**
1. [Context-specific question we can't research]
2. [Follow-up to previous call topic]

**Problem (3-4):**
1. [Based on industry pain points]
2. [Based on previous conversation hints]
3. [Based on trigger event if applicable]

**Implication (3-5):**
1. "If [specific problem from their notes] continues, what impact..."
2. "How does that affect your ability to [their stated goal]..."
3. [Industry-specific consequence question]

**Need-Payoff (2-3):**
1. "If you could [solve their specific problem], what would that mean for..."
2. "How would [outcome] change [their metric]..."

### Objection Prep
- Likely objection: [based on stage + sentiment]
- Counter: [Intrigue story from pitch-builder]

### Meeting Goal
- Advance to: [specific next step to propose]
- Minimum acceptable: [fallback next step]
```

## Industry Question Banks

Maintained in `skills/spin-questions/banks/` as JSON:
- `saas_tech.json` — SaaS/Technology companies
- `professional_services.json` — Consulting, agencies
- `manufacturing.json` — Industrial, production
- `finance.json` — Banking, insurance, fintech
- `ecommerce.json` — Retail, D2C, marketplace

Each bank contains 10 Situation, 15 Problem, 20 Implication, 10 Need-payoff templates per industry.

## Advance Tracking Integration
After every call, DealOps classifies the outcome:
- **Advance**: What specific next step was agreed?
- **Continuation**: Why? What was the buyer's stated reason?
- **No-sale**: What was the final objection?

This feeds back into deal-health scoring and cadence-engine next-step scheduling.

## Schedule
- Pre-call brief auto-generated 30 minutes before any scheduled Pipedrive activity of type "call" or "meeting"
- Timebox triggers the generation via cron
