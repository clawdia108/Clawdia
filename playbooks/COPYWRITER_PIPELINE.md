# Copywriter Pipeline — Write → Review → Rewrite Loop
# Playbook for perfect copy every time

---

## ARCHITECTURE

```
┌─────────────────────────────┐
│   1. BRIEFING               │
│   Input: what to write,     │
│   for whom, goal            │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│   2. COPYWRITER: Draft v1   │
│   Agent: GrowthLab or       │
│   dedicated CopyAgent       │
│   Uses: COPYWRITER_KB +     │
│   JOSEF_TONE_OF_VOICE       │
│   Output → drafts/          │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│   3. REVIEWER: Deep Review  │
│   Agent: Reviewer           │
│   Uses: REVIEW_CHECKLIST    │
│   Output: scored critique + │
│   line-by-line edits        │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│   4. COPYWRITER: Rewrite v2 │
│   Implements ALL reviewer   │
│   suggestions               │
│   Output → drafts/          │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│   5. REVIEWER: Final Check  │
│   Pass/Fail decision        │
│   Score must be 8+/10       │
│   If <8 → back to step 4   │
│   If 8+ → "SHIP IT"        │
└──────────┬──────────────────┘
           │
           ▼
┌─────────────────────────────┐
│   6. DELIVER                │
│   Final copy → delivery/    │
│   Notify Josef via Telegram │
└─────────────────────────────┘
```

---

## STEP 1: BRIEFING FORMAT

Before writing anything, the brief must contain:

```markdown
## Copy Brief
- **Type:** [blog post / email / offer / email template / LinkedIn post / landing page]
- **Target persona:** [CEO / HR Director / Team Leader / Partner]
- **Goal:** [awareness / consideration / conversion / retention]
- **Key message:** [1 sentence — what should the reader take away?]
- **CTA:** [what action should they take?]
- **Tone:** [Josef sales email / Blog editorial / Formal proposal]
- **Length:** [word count or "as needed"]
- **Context:** [any specific situation, customer, event, product feature]
- **Reference files:** [which knowledge base sections to consult]
```

---

## STEP 2: COPYWRITER DRAFT v1

### Pre-writing checklist (agent must do before writing):
1. Read `knowledge/COPYWRITER_KNOWLEDGE_BASE.md` — relevant sections
2. Read `knowledge/JOSEF_TONE_OF_VOICE.md` — match tone to content type
3. If blog: read `Behaveranewsite/docs/blog-rewrite-prompt.md` for voice guide
4. If email: study the "Navazuje to na" pattern and two-option close
5. If offer: combine blog authority voice + email directness

### Writing rules:
- First draft should be 80% there — not lazy placeholder
- Include all structural elements (hook, body, CTA, FAQ if blog)
- Mark uncertain spots with `[REVIEW: reason]` flags
- Save to `workspace/drafts/[type]-[topic]-v1.md`

---

## STEP 3: REVIEWER DEEP REVIEW

### The reviewer agent scores on 10 dimensions:

```markdown
## Review Scorecard

| # | Dimension | Score (1-10) | Notes |
|---|-----------|-------------|-------|
| 1 | **Hook quality** — Does the first 3 sentences grab? | | |
| 2 | **Voice match** — Does it sound like Josef / Behavera brand? | | |
| 3 | **Value density** — Is every paragraph earning its place? | | |
| 4 | **Specificity** — Concrete numbers, examples, not vague? | | |
| 5 | **Flow** — Does it read naturally, no awkward transitions? | | |
| 6 | **CTA clarity** — Is the next step obvious and low-friction? | | |
| 7 | **Persona fit** — Written FOR the target reader, not AT them? | | |
| 8 | **SEO/discoverability** — Keywords, structure, FAQ (if blog)? | | |
| 9 | **Shareability** — Would someone forward/post this? | | |
| 10 | **Factual accuracy** — All claims backed by sources? | | |
| **TOTAL** | | **/100** | |

### Verdict: [REWRITE NEEDED / MINOR EDITS / SHIP IT]
```

### Reviewer output format:

```markdown
## Line-by-Line Edits

### MUST FIX (blocks shipping)
1. [Line/section] — [What's wrong] → [Specific fix]
2. ...

### SHOULD FIX (improves quality)
1. [Line/section] — [What's wrong] → [Suggested fix]
2. ...

### NICE TO HAVE (polish)
1. [Line/section] — [Suggestion]
2. ...

### What's Working Well
- [Specific callout of strong elements to KEEP]
```

### Reviewer rules:
- Be brutal but constructive — specific fixes, not vague "make it better"
- Check every claim against COPYWRITER_KNOWLEDGE_BASE.md
- Check tone against JOSEF_TONE_OF_VOICE.md
- Flag any "AI-sounding" phrases (see forbidden words list)
- Flag any missing internal links (for blog posts)
- If score < 60: "FULL REWRITE" — start over with different angle
- If score 60-79: "REWRITE NEEDED" — major structural changes
- If score 80-89: "MINOR EDITS" — polish and ship
- If score 90+: "SHIP IT" — ready to publish

Save review to `workspace/reviews/[type]-[topic]-review-v[N].md`

---

## STEP 4: COPYWRITER REWRITE

### Rewrite rules:
- Address ALL "MUST FIX" items — no exceptions
- Address all "SHOULD FIX" items — skip only with written justification
- Consider "NICE TO HAVE" items
- DO NOT change things the reviewer called out as "Working Well"
- Save to `workspace/drafts/[type]-[topic]-v[N+1].md`

---

## STEP 5: FINAL CHECK

### Ship criteria:
- Total score 80+/100
- Zero "MUST FIX" items remaining
- Voice match score 8+/10
- Factual accuracy score 9+/10

### If not shipping:
- Loop back to Step 4
- Maximum 3 loops — if still not 80+ after 3 rounds, escalate to Josef

---

## STEP 6: DELIVERY

### File naming convention:
```
workspace/delivery-queue/
├── blog-quiet-quitting-FINAL-2026-03-03.md
├── email-follow-up-template-FINAL-2026-03-03.md
├── offer-pilot-proposal-FINAL-2026-03-03.md
└── linkedin-post-engagement-stats-FINAL-2026-03-03.md
```

### Telegram notification:
```
📝 New copy ready for review:
Type: [blog post]
Topic: [Quiet Quitting v českých firmách]
Score: [87/100]
File: delivery-queue/blog-quiet-quitting-FINAL-2026-03-03.md
Review: reviews/blog-quiet-quitting-review-v2.md
```

---

## REFERENCE FILES (must be loaded by agents)

| File | When to Load | Who Loads |
|------|-------------|-----------|
| `knowledge/COPYWRITER_KNOWLEDGE_BASE.md` | Every writing task | Copywriter |
| `knowledge/JOSEF_TONE_OF_VOICE.md` | Every writing task | Copywriter + Reviewer |
| `Behaveranewsite/docs/blog-rewrite-prompt.md` | Blog posts only | Copywriter |
| `Behaveranewsite/behavera_cz_full_text.txt` | Product claims | Copywriter |
| `Behaveranewsite/docs/blog-all-articles-export.txt` | Blog internal linking | Copywriter |

---

## AGENT ASSIGNMENT

### Option A: Use existing agents
- **GrowthLab** → Copywriter role (research + writing)
- **Reviewer** → Review role (already exists, add copy review checklist)

### Option B: Create dedicated CopyAgent (RECOMMENDED)
- **CopyAgent** → Dedicated copywriter, writes + rewrites
- **Reviewer** → Reviews (existing agent, expanded scope)

### Option C: Single agent, dual hat
- One agent writes in "copywriter mode" then switches to "editor mode"
- Less reliable — same blind spots in both passes
- NOT recommended for "perfect outcomes every time"

---

## CRON SCHEDULE (suggested)

```
# Morning: Check if any copy briefs are waiting
0 8 * * 1-5  copyagent  "Check workspace/briefs/ for new tasks"

# After draft: Trigger review
# (event-driven, not cron — triggered when draft file appears)

# Evening: Report on copy pipeline status
0 18 * * 1-5  commandcenter  "Report copy pipeline status to Telegram"
```

---

## LEARNING LOOP

After Josef approves or edits the final copy:
1. Reviewer compares Josef's edits to the submitted version
2. Patterns extracted → added to `knowledge/JOSEF_TONE_OF_VOICE.md`
3. Common mistakes → added to `knowledge/COPYWRITER_KNOWLEDGE_BASE.md` Section 5
4. This creates a **self-improving system** — each piece of copy makes the next one better

---

*This playbook is the operating manual for all copy production. Follow it exactly. No shortcuts.*
