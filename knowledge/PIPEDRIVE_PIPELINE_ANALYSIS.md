# Behavera Pipedrive Pipeline Analysis
**Generated: 2026-03-03 | Data source: Pipedrive API (live)**

---

## Executive Summary

Behavera has **145 open deals** worth **3,781,577 CZK** (combined CZK + EUR converted) across 4 pipelines. The weighted pipeline value is **3,283,529 CZK**. The team has 9 registered users (4 currently active: Jana Sramkova, Jiri Valena, Josef Hofman, Veronika, Gio).

**Critical finding:** 57 open deals (39%) have NO next activity scheduled. 76 deals (52%) are stale with no activity in 14+ days. This is a massive revenue leak -- deals are rotting in the pipeline because nobody is following up.

**The #1 problem isn't lead generation. It's follow-through.**

---

## 1. Pipeline Structure

### Pipeline 1: Sales Pipeline (ID: 2)
The main revenue engine. 8 stages:

| Order | Stage | Probability | Open Deals |
|-------|-------|------------|------------|
| 1 | Interested/Qualified | 25% | 2 |
| 2 | Demo Scheduled | 40% | 13 |
| 3 | Ongoing Discussion | 100% | 8 |
| 4 | Proposal Made | 50% | 4 |
| 5 | Negotiation | 60% | 3 |
| 6 | Pilot | 75% | 4 |
| 7 | Contract Sent | 85% | 0 |
| 8 | Invoice Sent | 95% | 0 |

**Total: ~55 deals** (with page 2 data) | **Open value: ~1.2M CZK**

**Observation:** Heavy bottleneck at "Demo Scheduled" (13 deals) and "Ongoing Discussion" (8 deals). Zero deals at Contract Sent or Invoice Sent -- meaning nothing is in the final closing stages right now. The funnel is wide at the top and empty at the bottom.

### Pipeline 2: Onboarding Pipeline (ID: 3)
Post-sale customer onboarding. 7 stages:

| Order | Stage | Open Deals |
|-------|-------|------------|
| 1 | Sales Action Needed | 0 |
| 2 | Waiting for Customer | 4 |
| 3 | 1. Pulse Planned | 1 |
| 4 | Probation Period | 0 |
| 5 | Customers | 10 |
| 6 | Test Only | 1 |
| 7 | Not Converted | 9 |

**Total: 25 deals**

**Observation:** 9 deals in "Not Converted" -- these are failed onboardings. That's a 36% not-converted rate in the onboarding pipeline. Testuj.to, Benefit Plus, Reddo, Scaleup Board, WPJ, Juice Up, Sunnymont, My Value Officer -- these all stalled during onboarding. This is a product/CS problem, not a sales problem.

### Pipeline 3: Partnerships (ID: 4)
Partner/channel relationships. 5 stages:

| Order | Stage | Open Deals |
|-------|-------|------------|
| 1 | Talking | 13 |
| 2 | Serious Talks | 6 |
| 3 | Preparations | 2 |
| 4 | Active Partnership | 1 |
| 5 | No Partnership | 0 |

**Total: 22 deals**

**Observation:** Only 1 active partnership (Givt). 13 stuck at "Talking" with zero values. Most have no next activity. Partnership pipeline is neglected -- Jana owns most of these and hasn't touched many in months.

### Pipeline 4: Churned Customers / Onetime Deals (ID: 5)
Historical/churned accounts. 2 stages:

| Order | Stage | Open Deals |
|-------|-------|------------|
| 1 | Churned Customers | 18 |
| 2 | Onetime Deals | 1 |

**Total: 19 deals | Value: 1,111,849 CZK + 58,600 EUR**

**Observation:** This pipeline holds the HIGHEST absolute value but it's all dormant revenue. Vodafone alone has 768,770 CZK in churned deals. Skoda Auto (150K CZK), Lidl (100K CZK), Postova banka (33K EUR), 365.bank (22K EUR) -- these are big logos sitting untouched.

---

## 2. Total Open Value by Pipeline

| Pipeline | CZK Value | EUR Value | EUR->CZK Converted | Total CZK |
|----------|-----------|-----------|---------------------|-----------|
| Sales Pipeline | ~1,200,000 | 0 | 0 | ~1,200,000 |
| Onboarding | 133,080 | 0 | 0 | 133,080 |
| Partnerships | 0 | 0 | 0 | 0 |
| Churned/Onetime | 1,111,849 | 58,600 | ~1,422,112 | ~2,533,961 |
| **TOTAL** | **2,359,465** | **58,600** | **1,422,112** | **3,781,577** |

**Weighted total: 3,283,529 CZK**

---

## 3. Top 10 Highest-Value Open Deals

| Rank | Deal | Value | Currency | Pipeline | Stage | Owner | Next Activity |
|------|------|-------|----------|----------|-------|-------|---------------|
| 1 | Vodafone CC Expert (won but related open: Vodafone Licence 2nd year) | 384,441 | CZK | Churned | Churned | Jiri Valena | NONE |
| 2 | Postova banka | 33,000 | EUR (~801K CZK) | Churned | Churned | Jiri Valena | NONE |
| 3 | Vodafone Future Retail Skills | 266,889 | CZK | Churned | Churned | Jiri Valena | NONE |
| 4 | 365.bank | 22,000 | EUR (~534K CZK) | Churned | Churned | Jiri Valena | NONE |
| 5 | Prusa Research 3D printers deal | 200,000 | CZK | Sales | Negotiation | Jana Sramkova | 2026-03-06 |
| 6 | Hyundai Motor Manufacturing deal | 178,200 | CZK | Sales | Pilot | Jiri Valena | 2026-03-03 |
| 7 | Smidl & NIKA deal | 178,800 | CZK | Sales | Negotiation | Jana Sramkova | 2026-03-04 |
| 8 | Skoda Auto | 150,000 | CZK | Churned | Churned | Jiri Valena | NONE |
| 9 | Nobilis deal | 120,000 | CZK | Sales | Ongoing Discussion | Josef Hofman | 2026-03-23 |
| 10 | Ecomail.cz | 112,860 | CZK | Sales | Proposal Made | Gio | 2026-03-13 |

**Red flag:** 6 of the top 10 highest-value deals have NO next activity. They're all churned accounts being left to rot. Combined value of neglected top deals: ~2.2M CZK.

---

## 4. Stale Deals (No Activity 14+ Days)

**76 out of 145 deals (52%) are stale.** Here are the most critical ones in the active Sales Pipeline:

### Sales Pipeline Stale Deals (Action Required)
| Deal | Days Stale | Value | Owner | Stage |
|------|-----------|-------|-------|-------|
| Cross Masters deal | 75 days | 38,016 CZK | Jiri Valena | Pilot |
| 2HHOLINGER deal | 43 days | 0 CZK | Josef Hofman | Demo Scheduled |
| GARTAL Corporate Group | 36 days | 95,040 CZK | Josef Hofman | Proposal Made |
| WPJ deal | 35 days | 55,000 CZK | Jana Sramkova | Pilot |
| Narodni zemedelske muzeum | 34 days | 0 CZK | Josef Hofman | Demo Scheduled |
| HABRA deal | 22 days | 0 CZK | Jiri Valena | Proposal Made |
| Be DNA deal | 20 days | 0 CZK | Josef Hofman | Ongoing Discussion |
| SIAD Czech deal | 20 days | 0 CZK | Jiri Valena | Demo Scheduled |
| DPP deal | 20 days | 0 CZK | Josef Hofman | Ongoing Discussion |
| DI industrial deal | 20 days | 0 CZK | Josef Hofman | Demo Scheduled |
| Nobilis deal | 19 days | 120,000 CZK | Josef Hofman | Ongoing Discussion |
| DPMHK deal | 19 days | 0 CZK | Jiri Valena | Ongoing Discussion |
| VOP Group deal | 19 days | 0 CZK | Josef Hofman | Demo Scheduled |
| BeePartner deal | 15 days | 0 CZK | Josef Hofman | Demo Scheduled |
| ProCare Medical deal | 15 days | 0 CZK | Josef Hofman | Ongoing Discussion |
| Mycroft Mind | 15 days | 106,920 CZK | Josef Hofman | Proposal Made |

**Josef is the biggest offender** -- he has 10+ stale sales deals. Some with real money (GARTAL 95K, Nobilis 120K, Mycroft Mind 107K).

### Partnership Pipeline -- Fully Neglected
13 deals in "Talking" stage, most with ZERO activity ever. Jana owns nearly all of them. This pipeline is effectively dead.

### Churned Pipeline -- Untouched Gold
18 churned customers totaling over 1.1M CZK + 58.6K EUR sit with zero follow-up. Nobody is running a win-back campaign.

---

## 5. Deals With No Next Activity Scheduled

**57 deals (39%) have no next activity.** This means nobody is planning to do anything with them.

### By Owner (no next activity count):
| Owner | Deals Without Next Activity |
|-------|---------------------------|
| Jana Sramkova | 23 |
| Jiri Valena | 22 |
| Veronika | 7 |
| Josef Hofman | 5 |

Jana and Jiri together account for 45 of 57 abandoned deals.

### Highest-Value Deals With No Next Activity:
1. **Vodafone Licence 2nd year** -- 384,441 CZK (Jiri)
2. **Postova banka** -- 33,000 EUR (Jiri)
3. **Vodafone Future Retail Skills** -- 266,889 CZK (Jiri)
4. **365.bank** -- 22,000 EUR (Jiri)
5. **Skoda Auto** -- 150,000 CZK (Jiri)
6. **Lidl** -- 100,000 CZK (Jiri)
7. **Expando** -- 75,000 CZK (Jiri)
8. **Vodafone First Pilot** -- 58,080 CZK (Jiri)
9. **Vodafone SMB Care Teams** -- 58,440 CZK (Jiri)
10. **WPJ deal** -- 55,000 CZK (Jana)

**Jiri Valena holds 9 of the top 10 highest-value unattended deals.** Total unattended value under Jiri: ~1.7M CZK.

---

## 6. Win/Loss Pattern Analysis

### Won Deals: 26 total

**Key patterns in won deals:**
- **Average won deal value:** ~63,000 CZK (excluding outliers)
- **Biggest win:** Vodafone CC Expert Analysis -- 532,763 CZK
- **Second biggest:** PSAS (Prazske Sluzby) -- 297,000 CZK
- **Most wins by owner:** Jana Sramkova (10), Jiri Valena (11), Josef Hofman (2), Veronika (1), Tomas Geryk (1)
- **Pipeline 2 (Sales) wins:** 15 deals -- this is where real revenue comes from
- **Pipeline 5 (Churned) wins:** 5 deals -- upsells to existing customers
- **Pipeline 4 (Partnerships) wins:** 3 deals
- **Win time pattern:** Most deals won within 1-3 months of creation
- **Common traits of won deals:**
  - Had a named organization attached
  - Most had activities logged (demos, calls)
  - Tended to be mid-market Czech companies or known brands
  - Several were "assessments" or "pilot" projects (lower barrier to entry)

### Lost Deals: 100 total

**Lost reason breakdown:**

| Reason | Count | % |
|--------|-------|---|
| Ghosting | 31 | 31% |
| Bad timing | 19 | 19% |
| Not impressed | 14 | 14% |
| Internal decision blocker | 8 | 8% |
| Bad timing (consider nurturing) | 7 | 7% |
| Internal solution | 6 | 6% |
| Not relevant | 6 | 6% |
| Not a fit | 2 | 2% |
| Budget | 1 | 1% |
| Competitors solution | 1 | 1% |
| Other | 5 | 5% |

**Critical insight:** **Ghosting is the #1 loss reason at 31%.** This means prospects are simply not responding. Combined with "Bad timing" (26% including nurture tags), **57% of lost deals are potentially recoverable** -- they didn't say "no", they just went quiet or said "not now."

**Only 1 deal was lost to a competitor** (Siemens Healthineers). This means Behavera isn't losing on product -- it's losing on timing and follow-up cadence.

**"Not impressed" at 14%** is worth investigating. 14 prospects saw the product and weren't convinced. This is a demo quality / product-market fit signal.

### Lost Deal Values:
- BREMBO CZECH: 2,138,400 CZK (ghosted -- massive loss)
- BTL: 831,600 CZK (bad timing)
- DataSentics: 297,000 CZK (internal decision blocker)
- ABRA Software: 200,000 CZK (internal solution)
- STRV: 178,800 CZK (ghosted)
- Accace: 178,800 CZK (bad timing)
- Cantina La Fresca: 178,800 CZK (bad timing)
- BCL: 170,000 CZK (internal decision blocker)
- Carvago: 100,000 CZK (bad timing)

**Total lost deal value in the dataset: ~4.8M CZK** -- more than the entire current open pipeline.

---

## 7. Team Members & Deal Ownership

### Active Users
| Name | Role | Active | Deals Owned | Last Login |
|------|------|--------|-------------|------------|
| Jana Sramkova | Admin | Yes | 34 | 2026-03-03 |
| Jiri Valena | Admin (company creator) | Yes | 29 | 2026-03-03 |
| Josef Hofman | Admin | Yes | 28 | 2026-02-25 |
| Veronika (Novakova) | Admin | Yes | 8 | 2026-03-03 |
| Gio (Giuseppe Solazzo) | Admin | Yes | ~16 (page 2) | 2026-02-12 |

### Inactive Users
| Name | Last Login |
|------|------------|
| Daniel Walczysko | 2025-10-23 |
| Jan Cihak | 2026-02-09 |
| Pavol Junas | 2025-11-18 |
| Tomas Geryk | 2026-01-12 |

**Note:** Some inactive users still own deals. Daniel Walczysko and Pavol Junas haven't logged in for months but may still have orphaned records.

### Deal Ownership Distribution (all 145 open deals)
| Owner | Sales Pipeline | Onboarding | Partnerships | Churned | Total |
|-------|---------------|------------|-------------|---------|-------|
| Josef Hofman | ~20 | 5 | 0 | 0 | ~25 |
| Jana Sramkova | 5 | 4 | ~15 | 3 | ~27 |
| Jiri Valena | ~10 | 5 | ~8 | 15 | ~38 |
| Gio | ~15 | 0 | 0 | 0 | ~15 |
| Veronika | 0 | 8 | 0 | 0 | ~8 |

**Jiri has the most deals but the least activity on them.** He's sitting on ~38 deals including the highest-value churned accounts and is not following up.

**Gio** is relatively new (joined Feb 2026) and is actively prospecting -- mostly UK companies (Celtic Renewables, 3 Sided Cube, Outlier Ventures, Five AI, Modo Energy). He's generating pipeline activity but hasn't closed anything yet.

---

## 8. Custom Fields in Use

| Field | Type | Purpose |
|-------|------|---------|
| Company ID (ICO) | Text | Czech business registration number |
| MRR | Monetary | Monthly recurring revenue tracking |
| Archived Reason | Enum | Why deal was archived (Unreachable, Too small, Not relevant, Not impressed, Existing Solution, Data error, Duplicate) |
| Lead Source | Enum | Cold Outreach, Inbound (Marketing), Referral, Partner, Event, Current Customer |
| Lead Tag | Enum | Nurture email sequence classification (Cold/Warm) |
| First Call Outcome | Enum | Connected / Not Connected |
| Account Status | Enum | Trial / Active / Churned |
| Use Case | Multi-select | Recruitment, L&D, Engagement, Performance & Analytics, Combo, Unknown |
| Product | Multi-select | Echo Pulse, The Office Day, Culture Fit, The Game Changer, Wellbeing |
| Onboarding Information | Text | Free-form onboarding notes |
| Lead Sub-source | Enum | Startupjobs database, Atmoskop database, Cocuma database, UK-LINKEDIN |

**Observation:** Good field structure. The "Product" field shows Behavera has 5 products: Echo Pulse, The Office Day, Culture Fit, The Game Changer, and Wellbeing. Lead source tracking is in place. However, many deals have 0 CZK value -- the team isn't consistently filling in deal values, which makes pipeline forecasting unreliable.

---

## 9. Activity Patterns

### Active Activity Types
| Type | Status |
|------|--------|
| Call | Active |
| First Connected Call | Active |
| Demo Meeting | Active |
| Follow up Meeting | Active |
| Email | Active |
| Task | Active |

### Inactive (disabled) Types
Follow up Call, LinkedIn message, SMS, JustCall SMS (x2), Google Meet, Ebook Call Attempt 2, Cold Call 2, Deadline

**Today's activity load (2026-03-03):** Josef Hofman has **50 calls/tasks** scheduled for today alone. That's all lead-level cold calls ("1st call"). This is an unsustainable daily volume -- many of these are lead-level activities, not deal-level.

**Pattern:** Josef is doing heavy cold calling (all 50 of today's activities are his). The rest of the team has minimal scheduled activities visible in the recent feed. This suggests Josef is the primary outbound engine, while Jana/Jiri handle deal progression and Gio handles UK outreach.

### Filters / Saved Views
Notable custom filters:
- "Lost deals - for emailing" (Jan Cihak) -- suggests some lost deal nurturing was attempted
- "Atmoskop database" (Jana) -- lead sourcing from Atmoskop
- "Ebook leads This Q" (Jana) -- ebook-driven lead gen
- "Cloudtalk - cold calls list" (Jana) -- call lists for cold outreach
- CloudTalk sync filters active for Josef and Jana

---

## 10. Concrete Recommendations

### URGENT (This Week)

**1. Kill or revive 57 deals with no next activity.**
Schedule a 30-minute pipeline review. Every deal without a next activity gets one of three treatments:
- Schedule a follow-up (if still alive)
- Mark as lost with a reason (if dead)
- Move to a "nurture" sequence (if "bad timing")

**2. Josef: Reduce cold call volume, increase deal follow-through.**
50 cold calls in one day means zero time for deal progression. Josef has 10+ stale deals in the Sales Pipeline including GARTAL (95K), Nobilis (120K), and Mycroft Mind (107K). Those 3 deals alone are worth 320K CZK. One good follow-up call is worth more than 30 cold calls to strangers.

**3. Jiri: Address 1.7M CZK in abandoned churned accounts.**
Specifically: Vodafone (3 deals, ~710K CZK), Postova banka (33K EUR), 365.bank (22K EUR), Skoda Auto (150K CZK). Even a 10% win-back rate on these is worth 170K+ CZK. Create a dedicated win-back email sequence.

### HIGH PRIORITY (This Month)

**4. Fix the "0 CZK" deal value problem.**
85+ deals have zero value. This makes pipeline forecasting impossible. Rule: no deal enters "Demo Scheduled" without a value estimate. Even a rough range is better than 0.

**5. Close the Onboarding gap.**
9 out of 25 onboarding deals are "Not Converted" (36%). That's 36% of won deals failing post-sale. Investigate:
- Why did Testuj.to, Benefit Plus, Reddo, Scaleup Board fail?
- Is there a common pattern (product issues, bad fit, lack of CS support)?
- Consider a customer success role or automated onboarding sequence.

**6. Clean up the Partnership pipeline.**
13 deals stuck at "Talking" for months with no activity. Jana owns most. Either:
- Make partnership outreach someone's primary job
- Shut down partnerships that haven't progressed in 90 days
- Focus on the 2-3 highest-potential partners only

**7. Address the "Ghosting" epidemic (31% of losses).**
- Implement a 3-touch follow-up sequence before marking as lost
- Use the "Bad timing (consider nurturing)" tag more aggressively
- Build an automated drip campaign for ghosted prospects
- Consider: are you ghosted because the initial outreach is weak, or because follow-up cadence is too slow?

### STRATEGIC (This Quarter)

**8. Build a proper win-back playbook.**
The Churned pipeline has 1.1M CZK + 58.6K EUR sitting idle. These are people who already bought once. Win-back campaigns typically convert 5-15% at a fraction of new customer acquisition cost. Create:
- Quarterly check-in cadence for churned accounts
- "What's new" email highlighting new products (Wellbeing, The Game Changer)
- Personal outreach for accounts over 100K CZK

**9. Gio needs a ramp plan.**
He's prospecting UK companies aggressively but hasn't closed yet. His deals are early stage (Demo Scheduled, Interested). He needs:
- Clear UK pricing/packaging
- Case studies relevant to UK market
- A buddy system with Jana/Jiri for deal coaching

**10. Invest in "Not Impressed" feedback.**
14% of losses are "Not impressed." This is a product/demo quality signal. Get specific feedback:
- What did they expect vs. what they saw?
- Which product were they shown?
- Was the demo tailored to their use case?

**11. Pipeline stage cleanup.**
"Ongoing Discussion" has 100% probability set -- that's wrong. It should be ~50%. This inflates weighted pipeline values. Also, "Customers" in the Onboarding pipeline has 20% probability -- should be higher for active customers.

---

## Key Metrics Summary

| Metric | Value |
|--------|-------|
| Total open deals | 145 |
| Total pipeline value (converted) | 3,781,577 CZK |
| Weighted pipeline value | 3,283,529 CZK |
| Deals with no next activity | 57 (39%) |
| Deals stale 14+ days | 76 (52%) |
| Win rate (won / won+lost) | 26 / 126 = **20.6%** |
| Average won deal value | ~63,000 CZK |
| #1 loss reason | Ghosting (31%) |
| Recoverable losses (timing/ghosting) | 57% of all losses |
| Churned revenue sitting idle | ~2.5M CZK |
| Onboarding failure rate | 36% |
| Active team members selling | 5 |

---

## The Bottom Line

Behavera's sales machine has **good lead generation** (145 open deals, multiple sources, new UK expansion via Gio) but **terrible deal hygiene**. More than half the pipeline is stale. The highest-value deals are unattended. The team is spread too thin across 4 pipelines with no clear ownership.

**If you fix just three things -- deal values, next activity discipline, and churned account follow-up -- you could add 500K-1M CZK in revenue this quarter without generating a single new lead.**

---

*Analysis generated from Pipedrive API data on 2026-03-03. All values in CZK unless noted. EUR converted at ~24.27 CZK/EUR.*
