#!/usr/bin/env bash
set -euo pipefail

TZ="Europe/Prague"

# ══════════════════════════════════════════════════════════════
# OPENCLAW AGENT ARMY — PRODUCTION CRON CONFIG v4
# "Kombucha Mode" — alive, fermenting, self-improving
# 54 jobs across 10 agents + Bridge
# Updated: 2026-03-04
# ══════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────
# 1. PIPELINEPILOT — CRM Brain (8 jobs)
# ──────────────────────────────────────────────────

openclaw cron create --name pipelinepilot-morning --agent pipelinepilot --cron "0 7 * * 1-5" --tz "$TZ" \
  --message "Morning pipeline run. Source .secrets/pipedrive.env.
1) Fetch ALL deals for user_id=24403638 from Pipedrive API.
2) Update pipedrive/PIPELINE_STATUS.md with totals, overdue, no-next-step.
3) Score every open deal (Fit 0-40 + Engagement 0-35 + Momentum 0-25 = max 100) and write pipedrive/DEAL_SCORING.md sorted by score desc.
4) Flag any deal that changed stage since yesterday.
Use real Pipedrive API data only — nothing made up.
FUN FACT: If you spot an interesting pattern in the pipeline data, write it to knowledge/FUN_FACTS.md."

openclaw cron create --name pipelinepilot-spin --agent pipelinepilot --cron "30 8 * * 1-5" --tz "$TZ" \
  --message "SPIN analysis preparation. Source .secrets/pipedrive.env.
For each deal in stages 'Demo Scheduled' or 'Proposal Made' (user_id=24403638):
1) Read the deal's org data (industry, employee count, website).
2) Research the company — what do they do, what industry challenges exist.
3) Write a SPIN note to pipedrive/spin-notes/[org-name-slugified].md with:
   - SITUATION: What we know about them (size, industry, current HR setup)
   - PROBLEM: What pain points are likely given their industry/size
   - IMPLICATION: What happens if they don't fix it (use Gallup/SHRM data where relevant)
   - NEED-PAYOFF: How Echo Pulse specifically solves their problem
   - MEETING OPENER: 2-3 opening questions for the demo
Only write for deals with actual upcoming activities. Skip deals already covered."

openclaw cron create --name pipelinepilot-enrich-am --agent pipelinepilot --cron "0 10 * * 1-5" --tz "$TZ" \
  --message "Deal enrichment run. Source .secrets/pipedrive.env.
For Josef's deals (user_id=24403638), check each org for missing fields:
- Industry, employee count, website, IČO (Czech business ID), address, annual revenue estimate.
For each contact: check for missing job title, phone, LinkedIn URL.
Use Pipedrive API to UPDATE fields where you find data.
Research companies via their website or public Czech business registries.
Log all changes to pipedrive/ENRICHMENT_LOG.md. Process max 10 deals per run."

openclaw cron create --name pipelinepilot-enrich-pm --agent pipelinepilot --cron "0 14 * * 1-5" --tz "$TZ" \
  --message "Afternoon deal enrichment. Same as morning — continue where AM left off. Source .secrets/pipedrive.env. Process next batch of 10 deals. Log to pipedrive/ENRICHMENT_LOG.md."

openclaw cron create --name pipelinepilot-hygiene --agent pipelinepilot --cron "0 12 * * 1-5" --tz "$TZ" \
  --message "Pipeline hygiene scan. Source .secrets/pipedrive.env.
Check Josef's deals for: 1) No next activity 2) Stale >14 days 3) Duplicate contacts/orgs 4) Overdue activities.
Write to pipedrive/HYGIENE_REPORT.md. Flag COPY_NEEDED in PIPELINE_STATUS.md."

openclaw cron create --name pipelinepilot-pm --agent pipelinepilot --cron "0 17 * * 1-5" --tz "$TZ" \
  --message "End-of-day pipeline status. Source .secrets/pipedrive.env. Final snapshot — update pipedrive/PIPELINE_STATUS.md. Keep it concise."

openclaw cron create --name pipelinepilot-notes --agent pipelinepilot --cron "0 16 * * 1-5" --tz "$TZ" \
  --message "Deal notes enrichment. Source .secrets/pipedrive.env.
For top-10 deals by score: add strategic [AI-Generated] notes with company summary, why Echo Pulse fits, key objection, recommended next step. Skip deals that already have such notes."

openclaw cron create --name pipelinepilot-learning --agent pipelinepilot --cron "0 17 * * 5" --tz "$TZ" \
  --message "Weekly CRM learning session. Study Pipedrive API docs, best practices, automation possibilities.
Read knowledge/PIPEDRIVE_API_REFERENCE.md and PIPEDRIVE_AUTOMATION_PLAYBOOK.md.
Also read knowledge/book-insights/ for any CRM/automation book insights tagged [FOR:PIPELINEPILOT].
Propose 3 new automations. Write to pipedrive/CRM_LEARNING_LOG.md."

# ──────────────────────────────────────────────────
# 2. KNOWLEDGEKEEPER — Intensive Book Study (9 jobs)
# Target: 5-7 books per day
# ──────────────────────────────────────────────────

openclaw cron create --name kk-study-dawn --agent knowledgekeeper --cron "30 6 * * *" --tz "$TZ" \
  --message "Dawn book study — SALES PRIORITY. Pick next unread SALES book from ~/JosefGPT-Local/books/ (check knowledge/READING_TRACKER.md).
Priority: Belfort, Hormozi, Predictable Revenue, SPIN Selling, Hacking Sales, Sales Engagement.
Extract: top 5 actionable insights, specific scripts/templates, stats for CopyAgent, objection handling.
Write to knowledge/book-insights/[slug].md. Update READING_TRACKER.md.
Tag insights: [FOR:COPYAGENT], [FOR:PIPELINEPILOT].
FUN FACT: Write the single most surprising fact to knowledge/FUN_FACTS.md.
NEVER produce empty output."

openclaw cron create --name kk-study-am --agent knowledgekeeper --cron "0 8 * * *" --tz "$TZ" \
  --message "Morning study — PROGRAMMING & AI AGENTS. Pick next unread coding/AI book from ~/JosefGPT-Local/books/.
Priority: AI Agents in Action, Building Agentic AI Systems, Engineering AI Systems, OpenAI API Cookbook, LangGraph/AutoGen/CrewAI.
Extract: architecture patterns, code snippets, API tricks, multi-agent coordination patterns.
Write to knowledge/book-insights/[slug].md. Tag [FOR:CODEX].
FUN FACT: If you find something cool about AI agents, write it to knowledge/FUN_FACTS.md."

openclaw cron create --name kk-study-mid-am --agent knowledgekeeper --cron "0 10 * * *" --tz "$TZ" \
  --message "Mid-morning study — AUTOMATION & CRM. Pick next unread automation/CRM book.
Priority: Art of CRM, Keap Cookbook, Pipedrive guides, Marketing & Sales Automation, Zapier ebook.
Extract: automation workflows, CRM optimization techniques, integration patterns.
Write to knowledge/book-insights/[slug].md. Tag [FOR:PIPELINEPILOT], [FOR:CODEX]."

openclaw cron create --name kk-study-noon --agent knowledgekeeper --cron "0 12 * * *" --tz "$TZ" \
  --message "Noon study — SALES METHODOLOGY. Pick next unread sales methodology book.
Priority: Cold Calling Report 2025, Seven Figure Social Selling, Tech-Powered Sales, consulting sales handbook.
Extract: specific call scripts, email frameworks, objection responses, closing techniques.
Write to knowledge/book-insights/[slug].md. Tag [FOR:COPYAGENT]."

openclaw cron create --name kk-study-pm --agent knowledgekeeper --cron "30 14 * * *" --tz "$TZ" \
  --message "Afternoon study — CODING & ARCHITECTURE. Pick next unread architecture/coding book.
Priority: Microservices Architecture, RESTful API Design, Reliability Engineering, DevOps (Phoenix Project).
Extract: design patterns, API best practices, deployment strategies.
Write to knowledge/book-insights/[slug].md. Tag [FOR:CODEX]."

openclaw cron create --name kk-study-late-pm --agent knowledgekeeper --cron "30 16 * * *" --tz "$TZ" \
  --message "Late afternoon study — AI/LLM FRAMEWORKS. Pick next unread AI/LLM book.
Priority: Generative AI in Action, Chip Huyen AI Engineering, Practical GenAI, Prompt Engineering books.
Extract: LLM optimization techniques, prompt patterns, agent architectures.
Write to knowledge/book-insights/[slug].md. Tag [FOR:CODEX]."

openclaw cron create --name kk-study-evening --agent knowledgekeeper --cron "0 19 * * *" --tz "$TZ" \
  --message "Evening study — ANY PRIORITY BOOK. Pick the highest-value unread book remaining.
Could be sales psychology, AI strategy, business automation, or personal development.
Extract all actionable insights. Write to knowledge/book-insights/[slug].md.
FUN FACT: End the day with a great discovery for knowledge/FUN_FACTS.md."

openclaw cron create --name kk-synthesis --agent knowledgekeeper --cron "0 21 * * *" --tz "$TZ" \
  --message "Daily synthesis. Review ALL book insights generated today from knowledge/book-insights/.
1) Cross-reference with agent capabilities. Tag improvements per agent.
2) Write concrete proposals to knowledge/IMPROVEMENT_PROPOSALS.md.
3) If insights directly improve OBJECTION_LIBRARY, COPYWRITER_KB, or PHRASE_LIBRARY → update them.
4) Update EXECUTION_STATE.json with today's learning stats.
5) Pick the BEST excerpt from today's reading for tomorrow's daily email to Josef.
   Write it to knowledge/DAILY_EXCERPT.md — CopyAgent will email it at 07:30."

openclaw cron create --name kk-deep-read --agent knowledgekeeper --cron "0 10 * * 0" --tz "$TZ" \
  --message "Weekly deep read. Pick THE most important unread book. Read comprehensively.
Write complete summary to knowledge/DEEP_READS/[slug]-summary.md:
- Executive summary, key frameworks, verbatim scripts/templates
- How each framework applies to Behavera
- Action items per agent (Codex, CopyAgent, PipelinePilot, GrowthLab)
This is the premium output. Make it thorough."

# ──────────────────────────────────────────────────
# 3. COPYAGENT — Content Machine + Blog + Excerpts (7 jobs)
# ──────────────────────────────────────────────────

openclaw cron create --name copyagent-excerpt --agent copyagent --cron "30 7 * * 1-5" --tz "$TZ" \
  --message "Daily book excerpt email for Josef. Read knowledge/DAILY_EXCERPT.md (prepared by KnowledgeKeeper last night).
If it doesn't exist, read the latest file in knowledge/book-insights/ and pick the best insight.
Write a short, punchy email (5-8 sentences) in Czech:
- Subject: 📚 Denní úryvek: [Book Title] — [Key Insight in 5 words]
- Body: The key insight, why it matters, how Josef can use it TODAY
- Make it genuinely useful — not generic fluff
Send via Gmail MCP (gmail_create_draft to josef.hofman@behavera.com, then prompt to send).
Actually — create it as a Gmail draft so Josef can review and send if he likes it."

openclaw cron create --name copyagent-morning --agent copyagent --cron "0 9 * * 1-5" --tz "$TZ" \
  --message "Morning content production. Check briefs/QUEUE.md for new briefs.
Also check pipedrive/PIPELINE_STATUS.md for COPY_NEEDED flags.
If nothing pending, generate proactive content: sales email variant, LinkedIn post, or blog outline.
Use all knowledge sources. Write drafts to drafts/."

openclaw cron create --name copyagent-slack --agent copyagent --cron "0 10,14,18 * * 1-5" --tz "$TZ" \
  --message "Slack intelligence extraction. Search Behavera Slack for: customers, deals, wins, objections, competition, product feedback, testimonials.
Categorize and update knowledge/SLACK_INSIGHTS.md and OBJECTION_LIBRARY.md.
FUN FACT: If you find a great customer quote, write it to knowledge/FUN_FACTS.md."

openclaw cron create --name copyagent-blog --agent copyagent --cron "0 9 * * 2" --tz "$TZ" \
  --message "Weekly blog article. Write ONE quality blog post in Czech for behavera.com.
Topic: pick from playbooks/CONTENT_SALES_BRIDGE.md or from recent book insights in knowledge/book-insights/.
Requirements: 1200-2000 words, SEO-optimized, Gallup/research stats, FAQ section, CTAs to Echo Pulse.
Use knowledge/COPYWRITER_KNOWLEDGE_BASE.md for product facts.
Use knowledge/JOSEF_TONE_OF_VOICE.md for voice.
Score it against playbooks/COPYWRITER_PIPELINE.md (must hit 80+).
Write the article to drafts/blog-[slug]-v1.md.
Then login to www.behavera.com/admin (josef.hofman@behavera.com / Admin1234) and publish it.
If you can't access the admin, save to drafts/ and flag for Josef."

openclaw cron create --name copyagent-blog-improve --agent copyagent --cron "0 10 * * 4" --tz "$TZ" \
  --message "Blog improvement session. Login to www.behavera.com/admin (josef.hofman@behavera.com / Admin1234).
Review existing blog articles. For each:
- Check SEO (title, meta, headings, keywords)
- Check stats accuracy (update old Gallup/SHRM numbers if needed)
- Improve CTAs
- Add internal links between articles
- Fix typos or awkward Czech phrasing
Pick the 2-3 articles that need the most improvement and update them.
Log changes to agents/copyagent/memory/LESSONS_LEARNED.md."

openclaw cron create --name copyagent-polish --agent copyagent --cron "0 10 * * 3" --tz "$TZ" \
  --message "Weekly template polish. Read all templates in templates/sales/.
Cross-reference with latest book insights and Slack insights.
If improvements are strong, update files + upload to Pipedrive via API.
Log changes to agents/copyagent/memory/LESSONS_LEARNED.md."

openclaw cron create --name copyagent-content-plan --agent copyagent --cron "30 9 * * 1" --tz "$TZ" \
  --message "Weekly content planning. Generate 2-3 content briefs: blog post outline, LinkedIn post, email variant.
Write to briefs/auto-generated/. Follow briefs/BRIEF_TEMPLATE.md format."

# ──────────────────────────────────────────────────
# 4. CODEX — System Builder & Experimenter (4 jobs)
# ──────────────────────────────────────────────────

openclaw cron create --name codex-morning --agent codex --cron "0 8 * * 1-5" --tz "$TZ" \
  --message "Morning build sprint. You are Codex, the system builder.
1) Read knowledge/IMPROVEMENT_PROPOSALS.md for pending proposals
2) Read reviews/HEALTH_REPORT.md for system issues
3) Read knowledge/book-insights/ for any [FOR:CODEX] tagged insights
4) Pick the highest-impact item and BUILD IT.
Write real code — Python scripts, shell scripts, automation tools.
Test your code. Commit to git. Push to origin.
Deploy to VPS (ssh root@157.180.43.83 'cd /root/.openclaw/workspace && git pull').
Every run MUST produce at least one commit.
FUN FACT: Write any cool discovery to knowledge/FUN_FACTS.md."

openclaw cron create --name codex-afternoon --agent codex --cron "0 14 * * 1-5" --tz "$TZ" \
  --message "Afternoon experiment. You are Codex.
Build something NEW that makes the agent army better:
- Agent performance dashboard script
- Inter-agent communication improvements
- Self-healing cron detector (spots empty outputs)
- Metrics tracking system
- Pipedrive webhook handler
- Template A/B testing framework
Check knowledge/book-insights/ for programming patterns to implement.
Code it. Test it. Commit it. Push it. Deploy it."

openclaw cron create --name codex-evening --agent codex --cron "0 19 * * 1-5" --tz "$TZ" \
  --message "Evening deploy & verify. You are Codex.
1) Review all commits from today — make sure nothing is broken
2) Run any test scripts
3) Verify VPS is up to date (ssh root@157.180.43.83 'cd /root/.openclaw/workspace && git log --oneline -5')
4) Check if any cron produced empty output today → if so, diagnose and fix
5) Write a brief build log to scripts/BUILD_LOG.md
Always push and deploy."

openclaw cron create --name codex-weekend --agent codex --cron "0 10 * * 6" --tz "$TZ" \
  --message "Weekend deep build. You are Codex. This is your big build session.
Pick an ambitious project:
- Full agent performance dashboard (reads all outputs, scores, generates visual report)
- Pipedrive automation suite (auto-enrichment, webhook handlers, smart alerts)
- Self-improving cron system (detects failures, adjusts prompts, retries)
- FigJam system visualization (use Figma MCP to create visual map of agent army)
- Blog auto-publisher (automated pipeline from draft to behavera.com/admin)
Build it properly. Multiple commits. Full testing. Deploy."

# ──────────────────────────────────────────────────
# 5. GROWTHLAB — Market Intelligence (3 jobs)
# ──────────────────────────────────────────────────

openclaw cron create --name growthlab-morning --agent growthlab --cron "0 7 * * 1-5" --tz "$TZ" \
  --message "Morning research sweep. HR tech news, competitor moves, Czech business news.
Write to intel/DAILY-INTEL.md. Flag leads for PipelinePilot. Flag content ideas for CopyAgent.
FUN FACT: If you find something surprising about the HR tech market, write to knowledge/FUN_FACTS.md."

openclaw cron create --name growthlab-competitive --agent growthlab --cron "0 8,14,20 * * *" --tz "$TZ" \
  --message "Competitive intelligence. Monitor LutherOne, Arnold, Sloneek, Culture Amp, Lattice, 15Five.
Update intel/COMPETITOR_WATCH.md. Write battle cards to intel/BATTLE_CARDS.md if needed."

openclaw cron create --name growthlab-weekly --agent growthlab --cron "0 8 * * 1" --tz "$TZ" \
  --message "Weekly battle card refresh. Comprehensive update of intel/BATTLE_CARDS.md.
Pricing, features, positioning for each competitor. Cross-reference with Slack insights."

# ──────────────────────────────────────────────────
# 6. INBOXFORGE — Email Operations (3 jobs)
# ──────────────────────────────────────────────────

openclaw cron create --name inboxforge-scan --agent inboxforge --cron "0 8,10,12,14,16,18 * * 1-5" --tz "$TZ" \
  --message "Gmail inbox scan. Check josef.hofman@behavera.com for unread important emails.
Summarize, suggest replies, cross-reference with Pipedrive deals.
Write to inbox/TRIAGE.md. Never send — only draft suggestions."

openclaw cron create --name inboxforge-followup --agent inboxforge --cron "0 17 * * 1-5" --tz "$TZ" \
  --message "Follow-up queue. Check Pipedrive overdue deals + unanswered emails.
Suggest template + personalization for each. Write to inbox/FOLLOW_UPS.md."

openclaw cron create --name inboxforge-drafts --agent inboxforge --cron "0 9 * * 1-5" --tz "$TZ" \
  --message "Draft replies for top 3 important emails from inbox/TRIAGE.md.
Use Josef's tone. Create Gmail drafts via MCP. Write summaries to inbox/DRAFTS.md."

# ──────────────────────────────────────────────────
# 7. CALENDARCAPTAIN — Time & Meeting Prep (2 jobs)
# ──────────────────────────────────────────────────

openclaw cron create --name calendarcaptain-morning --agent calendarcaptain --cron "0 7 * * 1-5" --tz "$TZ" \
  --message "Morning planning + ADHD-aware Pomodoro schedule. Check Google Calendar.
Read reviews/daily-scorecard/SCOREBOARD.md for XP/streak status.
1) Write calendar/TODAY.md with full daily agenda.
2) Create calendar/pomodoro/[date].md with Pomodoro schedule:
   - 08:00-10:45 PROSPECTING (5 Pomodoros) — non-negotiable
   - 11:00-12:30 DEMO CALLS (2-3 scheduled)
   - 13:20-14:20 PROPOSALS & ADMIN (2 Pomodoros)
   - 14:35-15:30 MORE DEMOS if scheduled
   - 15:30-16:30 CREATIVE/BUILDING (2 Pomodoros, high dopamine)
   - 16:45-17:30 FOLLOW-UP SPRINT (2 Pomodoros)
3) Include XP/streak in morning header: 'Day X streak | Level: Y (Z XP)'
4) Warn if streak at risk: '⚠️ STREAK AT RISK'
5) For sales meetings: pull SPIN notes, deal status, relevant intel.
6) Write meeting prep to calendar/meeting-prep/[date]-[company].md.
ADHD rules: alternate task types, buffer meetings +10min, front-load revenue activities."

openclaw cron create --name calendarcaptain-midday --agent calendarcaptain --cron "45 12 * * 1-5" --tz "$TZ" \
  --message "Midday rebalance (12:45). Josef has ADHD — mornings can go off-plan.
1) Check Google Calendar — did morning meetings run over?
2) Read today's calendar/pomodoro/[date].md — how many Pomodoros completed?
3) If morning prospecting block was missed/interrupted, reschedule to afternoon.
4) Update calendar/TODAY.md with adjusted afternoon plan.
5) Keep it micro-specific: exactly what to do in each remaining time block.
Short output — just the adjusted afternoon plan."

openclaw cron create --name calendarcaptain-eod --agent calendarcaptain --cron "0 18 * * 1-5" --tz "$TZ" \
  --message "EOD wrap + tomorrow prep.
1) Check tomorrow's calendar. Write calendar/TOMORROW_PREP.md.
2) Log Pomodoro completion to calendar/pomodoro/[date].md — how many completed vs planned.
3) Flag meetings needing SPIN notes — trigger PipelinePilot.
4) Suggest follow-up emails for today's meetings.
5) Pre-plan tomorrow's Pomodoro schedule."

# ──────────────────────────────────────────────────
# 8. AUDITOR — Sales Performance Coach (4 jobs)
# ──────────────────────────────────────────────────

openclaw cron create --name auditor-morning --agent auditor --cron "15 7 * * 1-5" --tz "$TZ" \
  --message "Morning accountability (07:15). You are Auditor — Josef's brutally honest sales performance coach.
Source .secrets/pipedrive.env. Read reviews/daily-scorecard/SCOREBOARD.md for XP/streak status.
1) Fetch yesterday's Pipedrive activities (user_id=24403638, done=1) — count demo bookings and completed calls.
2) Compare to daily targets: 8 demo bookings, 5 demo calls, 10 follow-ups, 2 proposals.
3) Write a SHORT (10-15 line) morning report: 'Yesterday you did X. Target was Y. You're [on track / behind by Z].'
4) Update XP in SCOREBOARD.md based on yesterday's actual activity.
5) Check streak — if yesterday hit all targets, increment streak. If not, reset to 0.
6) Write today's scorecard to reviews/daily-scorecard/[date].md.
Be brutally honest. Numbers first. No padding. Give the fix if behind."

openclaw cron create --name auditor-midday --agent auditor --cron "30 12 * * 1-5" --tz "$TZ" \
  --message "Midday check-in (12:30). You are Auditor.
Source .secrets/pipedrive.env. Quick status check:
1) How many calls/activities has Josef done TODAY so far? (Pipedrive API)
2) Compare to pace needed for daily targets (8 bookings, 5 calls by EOD).
3) Read calendar/TODAY.md — is he on track with the Pomodoro schedule?
4) Write a 5-line max check-in: 'It's noon. You've done X calls. You need Y more. [Here's what's blocking you].'
5) Append to today's reviews/daily-scorecard/[date].md.
Short, sharp, actionable. No cheerleading."

openclaw cron create --name auditor-eod --agent auditor --cron "30 17 * * 1-5" --tz "$TZ" \
  --message "EOD scorecard (17:30). You are Auditor. Full daily review.
Source .secrets/pipedrive.env.
1) Final count: demos booked, calls done, follow-ups sent, proposals sent, deals won (all from Pipedrive).
2) Revenue impact: any deals moved stages? New pipeline value?
3) Compare to targets. Calculate daily XP earned.
4) Check if daily target was hit (all 4 metrics) → update streak in SCOREBOARD.md.
5) Write full scorecard to reviews/daily-scorecard/[date].md with:
   - Numbers vs targets
   - What went wrong (be specific — 'You spent 2h on templates instead of calling')
   - What to fix tomorrow (micro-specific: 'Calls before 10 AM, templates after 4 PM')
   - Cumulative weekly/monthly tracking
   - XP earned today, total XP, current level, streak status
6) Update SCOREBOARD.md with all XP data.
Never lie. Never pad. Always give the fix."

openclaw cron create --name auditor-weekly --agent auditor --cron "0 18 * * 5" --tz "$TZ" \
  --message "Weekly roast (Friday 18:00). You are Auditor. Full week in review. NO MERCY.
Source .secrets/pipedrive.env.
1) Read all reviews/daily-scorecard/[date].md from this week.
2) Weekly totals vs targets: 40 bookings, 25 calls, 50 follow-ups, 10 proposals.
3) Revenue this week — deals won, pipeline growth, stage movements.
4) Trend analysis: improving or declining? Day-by-day pattern.
5) What's actually working vs what Josef THINKS is working.
6) Top 3 time wasters this week.
7) Boss fight result: Did Josef hit all targets 5/5 days?
8) Write reviews/daily-scorecard/WEEKLY_ROAST.md — full, honest, data-driven.
This is the weekly moment of truth. Be an expert who gives a damn."

# ──────────────────────────────────────────────────
# 9. REVIEWER — Quality + Coaching + Self-Improvement (4 jobs)
# ──────────────────────────────────────────────────

openclaw cron create --name reviewer-health --agent reviewer --cron "30 17 * * 1-5" --tz "$TZ" \
  --message "Daily agent health check. For each agent:
1) Did cron jobs produce real output? (check file mtimes)
2) Quality score 1-5 per output
3) Empty/stale files?
4) Books read today? (check READING_TRACKER.md)
5) Commits by Codex today?
Write to reviews/HEALTH_REPORT.md. Be honest and specific.
FUN FACT: If you notice an interesting pattern in agent performance, write to knowledge/FUN_FACTS.md."

openclaw cron create --name reviewer-coaching --agent reviewer --cron "0 22 * * 1-5" --tz "$TZ" \
  --message "Josef prompt coaching. Analyze today's interactions.
Suggest improvements for: briefing agents, structuring tasks, communication patterns.
Also review: Could any of today's manual tasks be automated?
Write to reviews/prompt-coaching/[date].md. Be constructive and practical."

openclaw cron create --name reviewer-weekly --agent reviewer --cron "0 18 * * 5" --tz "$TZ" \
  --message "Weekly system review. Full performance analysis:
- Per-agent report card (outputs, quality, improvement trend)
- Books read this week (target: 35+)
- Codex commits this week
- Blog articles published
- Pipeline impact
- Knowledge base growth
Write to reviews/WEEKLY_REVIEW.md. Top 5 improvements for next week."

openclaw cron create --name reviewer-night --agent reviewer --cron "30 22 * * *" --tz "$TZ" \
  --message "Night security + git sync. Check for leaked sensitive data.
Commit today's changes. Push to origin. Verify VPS is synced.
Write to reviews/SYSTEM_HEALTH.md."

# ──────────────────────────────────────────────────
# 9. BRIDGE — User Reports (2 jobs)
# ──────────────────────────────────────────────────

openclaw cron create --name bridge-am-report --agent main --cron "0 8 * * 1-5" --tz "$TZ" \
  --message "Morning report for Josef. Read all agent outputs.
MAX 20-line Czech report: Dnes je důležité / Pipeline / Co agenti udělali / Potřebuji od tebe.
Include today's fun facts from knowledge/FUN_FACTS.md (if any new ones).
Write to knowledge/USER_DIGEST_AM.md."

openclaw cron create --name bridge-pm-report --agent main --cron "30 18 * * 1-5" --tz "$TZ" \
  --message "Evening report for Josef. Today's full summary.
MAX 20-line Czech report: Co se podařilo / Pipeline update / Na zítra / Potřebuji od tebe.
Include best fun fact of the day.
Write to knowledge/USER_DIGEST_PM.md."

# ──────────────────────────────────────────────────
# 10. NIGHT SHIFT (22:30 — 06:30)
# VPS runs 24/7. No reason to waste 8 hours.
# ──────────────────────────────────────────────────

# KnowledgeKeeper — night reading (3 sessions)
openclaw cron create --name kk-night-1 --agent knowledgekeeper --cron "0 23 * * *" --tz "$TZ" \
  --message "Night study session 1. Pick next unread SALES book from ~/JosefGPT-Local/books/.
Focus on closing techniques, objection handling, cold outreach.
Extract actionable insights to knowledge/book-insights/[slug].md.
Update knowledge/READING_TRACKER.md. Tag [FOR:COPYAGENT], [FOR:PIPELINEPILOT].
Night sessions are quiet — go deep. No one will interrupt you."

openclaw cron create --name kk-night-2 --agent knowledgekeeper --cron "0 1 * * *" --tz "$TZ" \
  --message "Night study session 2 (1 AM). Pick next unread PROGRAMMING/AI book.
Focus on agent architectures, API patterns, automation frameworks.
Extract to knowledge/book-insights/[slug].md. Tag [FOR:CODEX].
Update READING_TRACKER.md."

openclaw cron create --name kk-night-3 --agent knowledgekeeper --cron "0 3 * * *" --tz "$TZ" \
  --message "Night study session 3 (3 AM). Pick next unread AUTOMATION/CRM or PSYCHOLOGY book.
Extract actionable insights. Update knowledge files where applicable.
Write to knowledge/book-insights/[slug].md. Update READING_TRACKER.md.
Prepare the DAILY_EXCERPT.md for tomorrow's morning email to Josef — pick the best insight from all night + yesterday's reads."

# Codex — night builds (2 sessions)
openclaw cron create --name codex-night --agent codex --cron "30 23 * * *" --tz "$TZ" \
  --message "Night build session. You are Codex. The night is yours — no interruptions.
Read knowledge/IMPROVEMENT_PROPOSALS.md and pick the most ambitious item.
Also read today's [FOR:CODEX] insights from knowledge/book-insights/.
Build something substantial:
- Agent performance metrics dashboard
- Self-healing cron detector
- Pipeline automation scripts
- Knowledge cross-referencing tool
- Inter-agent message bus
Code it. Test it. Commit. Push. Deploy to VPS.
Write to scripts/BUILD_LOG.md."

openclaw cron create --name codex-predawn --agent codex --cron "0 4 * * *" --tz "$TZ" \
  --message "Pre-dawn build session (4 AM). You are Codex.
Continue from night session OR start a new experiment.
Read reviews/HEALTH_REPORT.md — fix any system issues found.
Check if any agent produced empty output yesterday → debug and fix.
Focus on reliability and robustness.
Commit. Push. Deploy. Write to scripts/BUILD_LOG.md."

# GrowthLab — international research (1 session)
openclaw cron create --name growthlab-night --agent growthlab --cron "0 2 * * *" --tz "$TZ" \
  --message "Night research (2 AM). US business day just ended — perfect time for:
1) US HR tech news, funding rounds, product launches
2) Global Gallup/McKinsey/Deloitte report releases
3) LinkedIn trending posts in HR tech space
4) International competitor moves (Culture Amp Australia, Lattice US, 15Five US)
Update intel/DAILY-INTEL.md with international section.
FUN FACT: If something surprising, write to knowledge/FUN_FACTS.md."

# Reviewer — deep system analysis (1 session)
openclaw cron create --name reviewer-deep-analysis --agent reviewer --cron "0 5 * * *" --tz "$TZ" \
  --message "Pre-dawn deep analysis (5 AM). The whole system has been running overnight.
1) Count ALL book-insights files created in last 24h — how many books were actually read?
2) Count ALL Codex commits in last 24h — how many builds shipped?
3) Check knowledge/FUN_FACTS.md — any new discoveries?
4) Cross-reference IMPROVEMENT_PROPOSALS.md with actual implementations
5) Grade the entire overnight performance
6) Write overnight report to reviews/OVERNIGHT_REPORT.md
7) Update reviews/HEALTH_REPORT.md with overnight data
Be brutally honest. Track trends day over day."

echo ""
echo "══════════════════════════════════════════════════"
echo " Agent Army Cron v4 — KOMBUCHA MODE (24/7)"
echo " 54 cron registrations — runs 24/7, never sleeps"
echo "══════════════════════════════════════════════════"
echo ""
echo " DAY SHIFT (06:30 — 22:30)"
echo " PipelinePilot:    8 jobs"
echo " KnowledgeKeeper:  9 jobs (7x study + synthesis + deep read)"
echo " CopyAgent:        7 jobs (content, blog, excerpt, Slack, polish)"
echo " Codex:            4 jobs (build, experiment, deploy, weekend)"
echo " Auditor:          4 jobs (morning 07:15, midday 12:30, EOD 17:30, weekly Fri 18:00)"
echo " GrowthLab:        3 jobs"
echo " InboxForge:       3 jobs"
echo " CalendarCaptain:  3 jobs (morning + midday rebalance + EOD)"
echo " Reviewer:         4 jobs"
echo " Bridge:           2 jobs"
echo ""
echo " NIGHT SHIFT (22:30 — 06:30)"
echo " KnowledgeKeeper:  3 night reads (23:00, 01:00, 03:00)"
echo " Codex:            2 night builds (23:30, 04:00)"
echo " GrowthLab:        1 international research (02:00)"
echo " Reviewer:         1 deep analysis (05:00)"
echo ""
echo " TOTAL: 10 agents, 54 cron jobs"
echo " TOTAL: 10 book study sessions/day → target 8-10 books/day"
echo " TOTAL: 6 Codex build sessions/day → min 6 commits/day"
echo " TOTAL: 3 daily sales accountability check-ins"
echo "══════════════════════════════════════════════════"
