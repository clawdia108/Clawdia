# Deal Stage Playbook — CopyAgent × PipelinePilot

> How CopyAgent auto-generates the right copy at the right time, driven by pipeline signals.

---

## Pipeline ↔ CopyAgent Integration

### How PipelinePilot Signals CopyAgent

PipelinePilot writes to `PIPELINE_STATUS.md` with a `COPY_NEEDED` flag:

```
## COPY_NEEDED
- deal_id: 12345
- company: "Grammer CZ"
- contact: "Mario Tulia"
- role: CEO | HR | TEAM_LEADER
- stage: talking | proposal | negotiation | pilot | closed
- trigger: stage_change | stale_deal | follow_up_due | objection_detected
- objection_ref: (optional) OBJECTION_LIBRARY.md#N
- context: "Free-form note from PipelinePilot or Josef"
- priority: normal | urgent
- created: 2026-03-03T10:00:00
```

CopyAgent reads this, generates a draft, saves it, and clears the flag.

### File Naming for Deal-Specific Drafts

```
drafts/sales/{company_slug}_{stage}_{YYYY-MM-DD}.md
```

Example: `drafts/sales/grammer_proposal_2026-03-03.md`

### Escalation → Josef

CopyAgent pings Josef (via Slack/digest) when:
- Deal is marked `priority: urgent`
- Deal has been stale 14+ days with no response after reactivation attempt
- Objection #6 ("Vedení to neschválí") or #7 ("Bojíme se") detected — these need personal touch
- Any deal > 100K CZK entering Negotiation

---

## Stage 1: TALKING (První kontakt)

**Goal:** Build rapport, qualify need, get them curious about Echo Pulse.

**CopyAgent Trigger:**
- New deal created in Pipedrive
- First meeting scheduled or completed
- No response 5 days after intro

**Templates:**
- `templates/sales/first_touch.md` — initial outreach
- `templates/sales/post_meeting_recap.md` — after first call
- `templates/sales/nudge_soft.md` — 5-day no-response

**Timeline/SLA:**
| Action | When |
|--------|------|
| First touch email | Within 24h of deal creation |
| Post-meeting recap | Same day as meeting |
| Soft nudge | Day 5 if no response |
| Second nudge | Day 10 — include TOFU article |
| Escalate to Josef | Day 14 if still silent |

**Copy Approach:**
- Warm, curious tone. "Navazuju na..."
- Reference their specific pain (use context from PipelinePilot)
- Drop 1 TOFU article link naturally — don't hard sell
- CEO: cost/retention angle. HR: engagement/data angle.

**Blog to Attach:**
- CEO → `kolik-stoji-ticha-fluktuace` or `proc-lide-odchazeji`
- HR → `co-se-deje-pred-vypovedi` or `quiet-quitting`

---

## Stage 2: PROPOSAL MADE (Nabídka odeslána)

**Goal:** Present Echo Pulse clearly, anchor the 29,900 CZK price, highlight risk reversal.

**CopyAgent Trigger:**
- Stage changed to "Proposal made"
- 3 days after proposal sent with no response
- Objection detected in notes

**Templates:**
- `templates/sales/proposal_email.md` — formal proposal delivery
- `templates/sales/proposal_followup.md` — Day 3 check-in
- `templates/sales/objection_response.md` — if objection flagged (pulls from OBJECTION_LIBRARY.md)

**Timeline/SLA:**
| Action | When |
|--------|------|
| Proposal email | Same day as stage change |
| "Jak to dopadlo?" follow-up | Day 3 |
| Objection-specific response | Within 24h of detection |
| Two-option close attempt | Day 7 |
| Escalate to Josef | Day 10 if no movement |

**Copy Approach:**
- Lead with the free 1-team trial — zero risk framing
- Anchor price: "29 900 Kč za 3měsíční pilot, s garancí vrácení peněz"
- Two-option close: "Dává smysl začít pilotem na jednom týmu, nebo chcete rovnou širší nasazení?"
- If objection → pull exact reframe from OBJECTION_LIBRARY.md

**Blog to Attach:**
- `jak-funguje-echo-pulse` (how it works)
- `vysledky-okamzite` (immediate results)

---

## Stage 3: NEGOTIATION (Vyjednávání)

**Goal:** Handle objections, finalize terms, push toward pilot commitment.

**CopyAgent Trigger:**
- Stage changed to "Negotiation"
- New objection logged
- 5 days without activity
- Multiple stakeholders identified (generate role-specific versions)

**Templates:**
- `templates/sales/negotiation_update.md` — status/next steps
- `templates/sales/objection_response.md` — with OBJECTION_LIBRARY.md ref
- `templates/sales/stakeholder_brief.md` — one-pager for internal champion to share
- `templates/sales/two_option_close.md` — closing push

**Timeline/SLA:**
| Action | When |
|--------|------|
| Negotiation recap email | Within 24h of stage change |
| Objection response | Same day |
| Check-in if quiet | Day 5 |
| Close attempt | Day 8 |
| Josef takes over | Day 12 or if deal > 100K CZK |

**Copy Approach:**
- Direct but not pushy. Acknowledge their concern, reframe, offer proof.
- Use social proof heavily: "Grammer to rozjeli na jednom týmu, teď škálují na celou firmu"
- Reference specific data from OBJECTION_LIBRARY.md
- Always give them a clear next step — never end with "dejte vědět"

**Blog to Attach:**
- `jak-nastavit-pulse` (setup is easy)
- `jak-dosahnout-ucast` (participation rates)
- `co-delat-po-vysledcich` (what happens with results)

---

## Stage 4: PILOT (Pilotní provoz)

**Goal:** Ensure successful pilot execution, collect wins, build case for expansion.

**CopyAgent Trigger:**
- Stage changed to "Pilot"
- Pilot week 2 check-in due
- Pilot results ready
- Pilot ending — upsell window

**Templates:**
- `templates/sales/pilot_kickoff.md` — welcome + onboarding
- `templates/sales/pilot_checkin.md` — mid-pilot check-in
- `templates/sales/pilot_results.md` — results summary + next steps
- `templates/sales/pilot_upsell.md` — expansion proposal

**Timeline/SLA:**
| Action | When |
|--------|------|
| Pilot kickoff email | Day 1 of pilot |
| Week 2 check-in | Day 14 |
| Results delivery | Within 48h of pilot end |
| Expansion proposal | Day 3 after results |
| Case study ask | Day 7 after results (if positive) |

**Copy Approach:**
- Supportive, partner tone — we're in this together
- Share early wins immediately ("Máme první data a je to zajímavé")
- At results: lead with the most actionable finding, not vanity metrics
- Upsell: "Výsledky z jednoho týmu jsou X — chcete vidět, jak to vypadá across the board?"

---

## Stage 5: CLOSED (Uzavřeno)

**Goal:** Onboard, deliver value, get referrals and case studies.

**CopyAgent Trigger:**
- Stage changed to "Closed"
- 30-day post-close check-in
- Quarterly review due
- Referral ask window

**Templates:**
- `templates/sales/closed_welcome.md` — onboarding sequence
- `templates/sales/quarterly_review.md` — QBR prep
- `templates/sales/referral_ask.md` — referral request
- `templates/sales/case_study_ask.md` — case study collaboration

**Timeline/SLA:**
| Action | When |
|--------|------|
| Welcome/onboarding email | Day 1 |
| 30-day check-in | Day 30 |
| Referral ask | Day 45 (only if satisfaction confirmed) |
| Quarterly review | Every 90 days |

---

## Stale Deal Reactivation Workflow

**Definition:** No activity for 14+ days in any stage before Closed.

**Workflow:**
1. PipelinePilot detects stale deal → writes `COPY_NEEDED` with `trigger: stale_deal`
2. CopyAgent generates reactivation email based on:
   - Last known stage
   - Last objection (if any)
   - Time elapsed
3. Reactivation sequence:
   - **Day 14:** Soft re-engage — value-add article, no ask
   - **Day 21:** Direct check-in — "Stále to řešíte? Rád pomůžu."
   - **Day 28:** Break-up email — "Nechci otravovat, ale..."
   - **Day 35:** Final ping + archive recommendation to Josef

**Template:** `templates/sales/reactivation_sequence.md`

**Escalation:** If deal > 50K CZK and stale 14+ days → immediate Josef notification, don't wait for sequence.

---

## Quick Reference: Stage → Template Map

| Stage | Primary Template | Follow-up | Objection |
|-------|-----------------|-----------|-----------|
| Talking | first_touch.md | nudge_soft.md | objection_response.md |
| Proposal | proposal_email.md | proposal_followup.md | objection_response.md |
| Negotiation | negotiation_update.md | two_option_close.md | objection_response.md |
| Pilot | pilot_kickoff.md | pilot_checkin.md | — |
| Closed | closed_welcome.md | quarterly_review.md | — |
| Stale (any) | reactivation_sequence.md | — | — |

---

*Maintained by CopyAgent. Last update: 2026-03-03*
