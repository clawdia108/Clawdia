# Pitch Builder Skill

**Owner:** GrowthLab
**Version:** 1.0.0
**Type:** instruction_only

## Purpose
Generate structured pitch decks, proposals, and presentation outlines using Klaff's neurofinance principles. Control frames, manage cognitive load, and build pitches that close.

## Pitch Structure (Klaff's 20-Minute Method)

### Phase 1: Intro + Big Idea (5 min)
- **Hook**: Pattern interrupt — something unexpected they haven't heard before
- **Big Idea**: "For [target audience] who [problem], our [solution] provides [unique value] unlike [alternatives]."
- **Why Now**: Trigger event, market shift, or urgency driver
- Rule: No slides. Eye contact. Energy.

### Phase 2: Budget + Secret Sauce (10 min)
- **Budget Frame**: Present full price FIRST (anchoring from Negotiation Neuroscience)
- **Secret Sauce**: What makes this unfair advantage — not features, but the insight/approach others don't have
- **Social Proof**: 1 specific case study, not 10 logos
- Rule: Show premium option first, then standard. Never lead with cheapest.

### Phase 3: Offer (2 min)
- **Clear CTA**: One specific next step
- **Scarcity**: Limited capacity, timeline, or availability (real, not manufactured)
- **Terms**: Simple, no jargon
- Rule: Cognitive load rule — max 3 decision points total

### Phase 4: Stack Frames for Hot Cognition (3 min)
- **Intrigue Frame**: Brief story that reengages emotion if they went analytical
- **Time Frame**: "This offer/availability is valid until [date]"
- **Prize Frame**: Position yourself as selective — "Here's what we look for in partners we work with"
- Rule: End on emotion, not logic. The croc brain decides first.

## Frame Control System

### Frame Detection (integrated with sentiment-classifier)
When prospect communication shows frame grabs:

| Their Frame | Your Counter | Template |
|-------------|-------------|----------|
| Power ("we'll let you know") | Prize | "We're selective about partnerships. Here's what we need from you to proceed." |
| Time ("send proposal by Friday") | Reframe | "The proposal takes the time it needs to be right. Let's focus on whether this is the right fit first." |
| Analyst ("show me the ROI model") | Intrigue | "Let me share what happened with [similar company] instead — the numbers tell the story better than any model." |
| Moral Authority ("industry standard is...") | Redirect | "Standards exist for average results. Here's what produces exceptional ones." |

### Intrigue Story Bank
Maintained in `skills/pitch-builder/stories.json`:
- 5-10 customer success stories, each with:
  - Protagonist (similar to prospect's situation)
  - Risk/danger (what was at stake)
  - Time pressure (why they had to act)
  - Resolution (specific outcome with numbers)
- Indexed by: industry, deal size, objection type

### Ready-to-Use Czech Intrigue Stories

**Story 1: Grammer — "The 34% Discovery"**
> "Měli jsme klienta v automotive — 400+ lidí. CEO si myslel, že je vše v pořádku.
> Za 6 týdnů Echo Pulse ukázal, že 34 % klíčových lidí v produkci plánuje odchod.
> Ne kvůli penězům — kvůli komunikaci s přímým nadřízeným.
> Včasný zásah jim ušetřil přes 2 miliony na náboru."
*Use when: prospect thinks everything is fine / doesn't see urgency*

**Story 2: Valxon — "Wrong Assumption"**
> "CEO ve výrobní firmě, 200 lidí, mi řekl: 'Víme, že problém je v odměnách.'
> Echo Pulse za týden ukázal, že problém vůbec nejsou odměny — je to komunikace.
> Za 2 měsíce rozjeli program pro celou firmu."
*Use when: prospect thinks they already know the problem*

**Story 3: 365.bank — "The Hidden Risk"**
> "Fintech firma, 300+ lidí. HR ředitelka chtěla měřit psychologické bezpečí.
> Našli 2 oddělení, kde se lidé báli mluvit o problémech.
> Restrukturalizace managementu ušetřila 1,8M Kč ročně na náboru."
*Use when: prospect worries about what results might show*

**Story 4: The Turnover Math**
> "Průměrná firma s 200 zaměstnanci ztratí 2-4 miliony ročně na nežádoucí fluktuaci.
> Jeden odchod stojí 6-9 měsíčních platů. Echo Pulse stojí méně než jeden odchod."
*Use when: price objection / ROI discussion*

## Pricing Strategy (Anchoring-First)

### Rules
1. **Always anchor high**: Present premium option first
2. **Three-tier pricing**: Premium → Standard → Starter (decoy effect)
3. **Never discount first**: Counter with added value instead
4. **Reciprocity concessions**: Pre-approved small concessions for deal momentum
   - Extended trial (+1 week): costs nothing, triggers reciprocity
   - Free onboarding call: builds relationship
   - Early access to feature: creates insider feeling

### Concession Bank
Stored in `skills/pitch-builder/concessions.json`:
- Low-cost concessions with estimated value perception
- Pre-approved by Josef (no approval loop needed)
- Track which concessions correlate with closes

## Cognitive Load Management

### Proposal Rules (from Negotiation Neuroscience)
1. Max 3 decision points per communication
2. One CTA per email
3. Progressive disclosure across touchpoints:
   - Touch 1: Overview (what + why)
   - Touch 2: Details (how + who)
   - Touch 3: Pricing (how much + when)
   - Touch 4: Next steps (decision)
4. Never send a proposal >3 pages without a preceding conversation

## Rapport Sequence (Oxytocin-Building)

Before any pitch, InboxForge runs a 3-touch rapport sequence:
1. **Personalized insight** about their business (not generic)
2. **Relevant resource** share (article, tool, insight)
3. **Brief check-in** referencing something specific from touches 1-2

Timebox spaces these 2-3 days apart. Only after 3 rapport touches does the pitch sequence begin.

## Output
- Pitch outline in `intel/PITCH_PREP.md`
- Proposal draft for review
- Pricing recommendation with anchor strategy
- Objection-handling playcard (linked to intrigue stories)

## Czech Market Pitch Adaptations
- NEVER use American-style enthusiasm ("Game-changer!", "Amazing!")
- Lead with DATA, not testimonials — Czechs trust numbers over stories
- Always offer "pilotní projekt" not "free trial" — reduces perceived risk
- Reference Czech companies (Grammer, Vodafone, Valxon, 365.bank) — NEVER US examples
- Price transparency: show pricing upfront, don't make them ask
- Two-option close ALWAYS: "Preferujete pilot pro 1 tým, nebo rovnou celé oddělení?"
- 100% money-back guarantee: "Pokud nenajdeme nic relevantního, vracíme peníze"

## ROI Calculator Framework
Use this formula in every pitch:
```
Počet zaměstnanců × průměrná měsíční mzda × 7.5 (replacement months) × fluktuace (%) = roční náklad fluktuace
→ Echo Pulse investice = zlomek tohoto nákladu
→ "Stačí zabránit 1 odchodu za rok a investice se vrátí 3×"
```

## Knowledge Sources
- `knowledge/OBJECTION_LIBRARY.md` — 10 objections with reframes
- `knowledge/COPYWRITER_KNOWLEDGE_BASE.md` — product details, case studies, ROI data
- `knowledge/JOSEF_TONE_OF_VOICE.md` — voice matching for pitch delivery

## Review Gates
- All proposals → review gate (user_facing_release)
- Pricing below floor → auto-block + Bridge alert
- First pitch to new prospect → require Josef review
