#!/usr/bin/env bash
set -euo pipefail

TZ="Europe/Prague"

# ══════════════════════════════════════════════════════════════
# OPENCLAW AGENT ARMY — PRODUCTION CRON CONFIG v2
# 35 jobs across 7 agents + Bridge
# Updated: 2026-03-04
# ══════════════════════════════════════════════════════════════

# ──────────────────────────────────────────────────
# 1. PIPELINEPILOT — CRM Brain (8 jobs)
# ──────────────────────────────────────────────────

# 07:00 — Morning pipeline snapshot + deal scoring
openclaw cron create --name pipelinepilot-morning --agent pipelinepilot --cron "0 7 * * 1-5" --tz "$TZ" \
  --message "Morning pipeline run. Source .secrets/pipedrive.env.
1) Fetch ALL deals for user_id=24403638 from Pipedrive API.
2) Update pipedrive/PIPELINE_STATUS.md with totals, overdue, no-next-step.
3) Score every open deal (Fit 0-40 + Engagement 0-35 + Momentum 0-25 = max 100) and write pipedrive/DEAL_SCORING.md sorted by score desc.
4) Flag any deal that changed stage since yesterday.
Use real Pipedrive API data only — nothing made up."

# 08:30 — SPIN prep for upcoming demos/meetings
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
Only write for deals with actual upcoming activities. Skip deals already covered (check file modification date)."

# 10:00 — Enrichment run 1
openclaw cron create --name pipelinepilot-enrich-am --agent pipelinepilot --cron "0 10 * * 1-5" --tz "$TZ" \
  --message "Deal enrichment run. Source .secrets/pipedrive.env.
For Josef's deals (user_id=24403638), check each org for missing fields:
- Industry, employee count, website, IČO (Czech business ID), address, annual revenue estimate.
For each contact: check for missing job title, phone, LinkedIn URL.
Use Pipedrive API to UPDATE fields where you find data (PUT /v1/organizations/{id}, PUT /v1/persons/{id}).
Research companies via their website or public Czech business registries (justice.cz, firmy.cz).
Log all changes to pipedrive/ENRICHMENT_LOG.md. Process max 10 deals per run to stay within rate limits."

# 14:00 — Enrichment run 2
openclaw cron create --name pipelinepilot-enrich-pm --agent pipelinepilot --cron "0 14 * * 1-5" --tz "$TZ" \
  --message "Afternoon deal enrichment. Same as morning enrichment — continue where AM left off. Source .secrets/pipedrive.env. Process next batch of 10 deals with missing fields. Update Pipedrive directly via API. Log to pipedrive/ENRICHMENT_LOG.md."

# 12:00 — Midday hygiene scan
openclaw cron create --name pipelinepilot-hygiene --agent pipelinepilot --cron "0 12 * * 1-5" --tz "$TZ" \
  --message "Pipeline hygiene scan. Source .secrets/pipedrive.env.
Check Josef's deals for:
1) Deals with no next activity → list them with recommended action
2) Deals stale >14 days → flag for reactivation email
3) Duplicate contacts or orgs → list for merge
4) Activities overdue → suggest re-date
Write to pipedrive/HYGIENE_REPORT.md. Flag deals needing COPY_NEEDED in pipedrive/PIPELINE_STATUS.md."

# 17:00 — PM pipeline status
openclaw cron create --name pipelinepilot-pm --agent pipelinepilot --cron "0 17 * * 1-5" --tz "$TZ" \
  --message "End-of-day pipeline status. Source .secrets/pipedrive.env. Final snapshot of the day — update pipedrive/PIPELINE_STATUS.md with current totals, won/lost today, stage changes, overdue count. Keep it concise — Josef reads this in 30 seconds."

# 16:00 — Add deal notes with key insights
openclaw cron create --name pipelinepilot-notes --agent pipelinepilot --cron "0 16 * * 1-5" --tz "$TZ" \
  --message "Deal notes enrichment. Source .secrets/pipedrive.env.
For each of Josef's top-10 deals by score: read existing notes from Pipedrive API (GET /v1/notes?deal_id=X).
If the deal has no strategic note, add one via POST /v1/notes with:
- Company summary (what they do, size, industry)
- Why Echo Pulse fits them
- Key objection to anticipate
- Recommended next step
Tag notes with [AI-Generated] prefix. Skip deals that already have an [AI-Generated] note."

# Pátek 17:00 — CRM learning & optimization
openclaw cron create --name pipelinepilot-learning --agent pipelinepilot --cron "0 17 * * 5" --tz "$TZ" \
  --message "Weekly CRM learning session. Study Pipedrive API documentation, best practices, and automation possibilities.
1) Read knowledge/PIPEDRIVE_API_REFERENCE.md and knowledge/PIPEDRIVE_AUTOMATION_PLAYBOOK.md
2) Research new Pipedrive features, workflow automations, webhooks
3) Analyze our pipeline data patterns — what's working, what's not
4) Propose 3 new automations or workflow improvements
5) Write findings to pipedrive/CRM_LEARNING_LOG.md
Focus on things that directly help Josef close more deals faster."

# ──────────────────────────────────────────────────
# 2. KNOWLEDGEKEEPER — Book Worm + System Improver (5 jobs)
# ──────────────────────────────────────────────────

# Every 3 hours — Ebook study session
openclaw cron create --name knowledgekeeper-study-am --agent knowledgekeeper --cron "0 7 * * *" --tz "$TZ" \
  --message "Ebook study session. Pick the next unread book from ~/JosefGPT-Local/books/ (check knowledge/READING_TRACKER.md for what's been read).
Priority order: sales methodology > AI/automation > psychology > productivity > other.
Read the book (or as much as context allows). Extract:
1) Top 5 actionable insights for Behavera's sales process
2) Specific frameworks, scripts, or templates that agents can use
3) Statistics or data points for CopyAgent's templates
4) Objection handling techniques for OBJECTION_LIBRARY.md
Write to knowledge/book-insights/[author-title-slug].md.
Update knowledge/READING_TRACKER.md with book name, date read, quality score 1-5.
NEVER produce empty or generic output — every insight must be specific and actionable."

openclaw cron create --name knowledgekeeper-study-mid --agent knowledgekeeper --cron "0 11 * * *" --tz "$TZ" \
  --message "Midday ebook study session. Same as morning — continue with next unread book from ~/JosefGPT-Local/books/. Check knowledge/READING_TRACKER.md. Focus on books about CRM, sales automation, cold outreach, or HR tech. Extract actionable insights to knowledge/book-insights/. Update tracker."

openclaw cron create --name knowledgekeeper-study-pm --agent knowledgekeeper --cron "0 15 * * *" --tz "$TZ" \
  --message "Afternoon ebook study session. Continue reading books from ~/JosefGPT-Local/books/. Check knowledge/READING_TRACKER.md. This session focus on psychology, persuasion, negotiation books (Cialdini, Kahneman, Hormozi, Belfort). Extract actionable insights. Update tracker."

# 21:00 — Daily synthesis + improvement proposals
openclaw cron create --name knowledgekeeper-synthesis --agent knowledgekeeper --cron "0 21 * * *" --tz "$TZ" \
  --message "Daily synthesis. Review ALL book insights generated today from knowledge/book-insights/.
1) Cross-reference insights with current agent capabilities
2) Identify specific improvements for: CopyAgent templates, PipelinePilot SPIN notes, GrowthLab competitive intel
3) Write concrete improvement proposals to knowledge/IMPROVEMENT_PROPOSALS.md
4) If any insight directly improves an existing knowledge file (OBJECTION_LIBRARY, COPYWRITER_KB, PHRASE_LIBRARY), update it.
5) Update knowledge/EXECUTION_STATE.json with today's learning stats.
Every proposal must have: what to change, why, expected impact, which agent benefits."

# Sunday 20:00 — Deep read (full book)
openclaw cron create --name knowledgekeeper-deep-read --agent knowledgekeeper --cron "0 20 * * 0" --tz "$TZ" \
  --message "Weekly deep read session. Pick the highest-priority unread book from ~/JosefGPT-Local/books/ (prefer: Hormozi, Belfort, Predictable Revenue, SPIN Selling, Challenger Sale, or any AI/sales book).
Read comprehensively. Write a complete summary to knowledge/DEEP_READS/[author-title]-summary.md with:
- Executive summary (5 sentences)
- Key frameworks (with diagrams in text if possible)
- Specific scripts/templates extracted verbatim
- How each framework applies to Behavera's sales process
- Action items for each agent
This is the premium output — make it thorough and excellent."

# ──────────────────────────────────────────────────
# 3. COPYAGENT — Sales Content Machine (4 jobs)
# ──────────────────────────────────────────────────

# 09:00 — Brief check + draft production
openclaw cron create --name copyagent-morning --agent copyagent --cron "0 9 * * 1-5" --tz "$TZ" \
  --message "Morning content production. Check briefs/QUEUE.md for new briefs with status TODO.
For each pending brief: produce a draft following playbooks/COPYWRITER_PIPELINE.md quality standards.
Use knowledge/COPYWRITER_KNOWLEDGE_BASE.md for product facts, knowledge/JOSEF_TONE_OF_VOICE.md for voice, knowledge/CZECH_PHRASE_LIBRARY.md for authentic phrases.
Write drafts to drafts/. Update brief status in QUEUE.md.
Also check pipedrive/PIPELINE_STATUS.md for COPY_NEEDED flags — auto-generate matching email from templates/sales/.
If no briefs pending, generate a proactive piece: sales email variant, LinkedIn post draft, or blog outline."

# Every 4h — Slack intel extraction
openclaw cron create --name copyagent-slack --agent copyagent --cron "0 10,14,18 * * 1-5" --tz "$TZ" \
  --message "Slack intelligence extraction. Search Behavera Slack for recent messages mentioning: customers, deals, wins, objections, competition, product feedback, testimonials.
Extract and categorize:
- New customer quotes → add to knowledge/SLACK_INSIGHTS.md
- Objection patterns → add to knowledge/OBJECTION_LIBRARY.md
- Product updates → note for template refresh
- Competitive mentions → flag for GrowthLab
Be careful with sensitive data — anonymize personal details, skip salary/financial info about individuals."

# Wednesday 10:00 — Template polish
openclaw cron create --name copyagent-polish --agent copyagent --cron "0 10 * * 3" --tz "$TZ" \
  --message "Weekly template polish. Read all 5 templates in templates/sales/.
Cross-reference with:
- Latest book insights from knowledge/book-insights/ (new psychology, frameworks)
- New Slack insights from knowledge/SLACK_INSIGHTS.md (fresh quotes, data)
- Any feedback in reviews/copy/
Propose specific improvements. If improvements are strong, update the template files.
Also update the Pipedrive versions via API (source .secrets/pipedrive.env, POST new versions).
Log changes to agents/copyagent/memory/LESSONS_LEARNED.md."

# Monday 09:30 — Content calendar
openclaw cron create --name copyagent-content-plan --agent copyagent --cron "30 9 * * 1" --tz "$TZ" \
  --message "Weekly content planning. Based on:
- This week's sales pipeline (pipedrive/PIPELINE_STATUS.md)
- Recent competitive intel (intel/DAILY-INTEL.md)
- Knowledge gaps identified by KnowledgeKeeper
Generate 2-3 content briefs and write to briefs/auto-generated/:
- 1 blog post outline (SEO-optimized, Czech, 1200+ words target)
- 1 LinkedIn post draft for Josef
- 1 email sequence variant or new template idea
Write each as a proper brief following briefs/BRIEF_TEMPLATE.md format."

# ──────────────────────────────────────────────────
# 4. GROWTHLAB — Market Intelligence (3 jobs)
# ──────────────────────────────────────────────────

# 07:00 — Morning research sweep
openclaw cron create --name growthlab-morning --agent growthlab --cron "0 7 * * 1-5" --tz "$TZ" \
  --message "Morning research sweep. Search for:
1) HR tech news in Czech Republic and CEE (employee engagement, people analytics, AI in HR)
2) Competitor moves — LutherOne, Arnold, Sloneek, Culture Amp, Lattice, 15Five
3) Gallup/McKinsey/Deloitte reports on engagement, retention, workplace trends
4) Czech business news — companies hiring, restructuring, or facing HR challenges (potential leads)
Write findings to intel/DAILY-INTEL.md. Flag leads for PipelinePilot. Flag content ideas for CopyAgent.
Every finding must include source URL. No speculation."

# Every 6h — Competitive watch
openclaw cron create --name growthlab-competitive --agent growthlab --cron "0 8,14,20 * * *" --tz "$TZ" \
  --message "Competitive intelligence check. Monitor:
- LutherOne.com, Arnold (heyarnold.ai), Sloneek.cz — pricing, features, blog posts
- Culture Amp, Lattice, 15Five — enterprise moves relevant to CEE
- Czech HR conferences, events, webinars
Update intel/COMPETITOR_WATCH.md with any changes. Include pricing comparisons where available.
If a competitor launches something relevant, write a quick battle card to intel/BATTLE_CARDS.md."

# Monday 08:00 — Weekly battle card refresh
openclaw cron create --name growthlab-weekly --agent growthlab --cron "0 8 * * 1" --tz "$TZ" \
  --message "Weekly battle card update. Comprehensive refresh of intel/BATTLE_CARDS.md.
For each competitor (LutherOne, Arnold/HeyArnold, Sloneek, Culture Amp, Lattice):
- Current pricing vs Echo Pulse
- Feature comparison (what they have that we don't, what we have that they don't)
- Their messaging/positioning
- How to position against them in a demo
- Win/loss patterns from Pipedrive data
Cross-reference with knowledge/SLACK_INSIGHTS.md for internal competitive discussions.
This file is used by PipelinePilot for SPIN notes — make it practical."

# ──────────────────────────────────────────────────
# 5. INBOXFORGE — Email Operations (3 jobs)
# ──────────────────────────────────────────────────

# Every 2h — Gmail monitoring
openclaw cron create --name inboxforge-scan-1 --agent inboxforge --cron "0 8,10,12,14,16,18 * * 1-5" --tz "$TZ" \
  --message "Gmail inbox scan. Use Gmail MCP tools to check josef.hofman@behavera.com inbox.
1) Search for unread important emails (from customers, prospects, partners)
2) For each important email: summarize content, suggest reply approach, flag urgency
3) Cross-reference senders with Pipedrive deals (check pipedrive/PIPELINE_STATUS.md)
4) Write triage to inbox/TRIAGE.md
Never send emails — only draft suggestions. Flag anything needing Josef's immediate attention."

# 17:00 — Follow-up queue
openclaw cron create --name inboxforge-followup --agent inboxforge --cron "0 17 * * 1-5" --tz "$TZ" \
  --message "Follow-up queue review. Check:
1) Pipedrive deals with overdue activities (from pipedrive/HYGIENE_REPORT.md)
2) Emails sent 3+ days ago with no reply
3) Prospects who opened emails but didn't respond (if tracking data available)
For each, suggest: which template to use (from templates/sales/), personalization notes, urgency level.
Write to inbox/FOLLOW_UPS.md. This feeds into Josef's daily follow-up routine."

# 09:00 — Draft replies for important emails
openclaw cron create --name inboxforge-drafts --agent inboxforge --cron "0 9 * * 1-5" --tz "$TZ" \
  --message "Email draft preparation. Read inbox/TRIAGE.md from the morning scan.
For the top 3 most important emails:
1) Draft a reply in Josef's tone (use knowledge/JOSEF_TONE_OF_VOICE.md + knowledge/CZECH_PHRASE_LIBRARY.md)
2) Include relevant product facts from knowledge/COPYWRITER_KNOWLEDGE_BASE.md
3) Create Gmail drafts via Gmail MCP tools (gmail_create_draft)
Write draft summaries to inbox/DRAFTS.md. Josef approves before sending."

# ──────────────────────────────────────────────────
# 6. CALENDARCAPTAIN — Time & Meeting Prep (2 jobs)
# ──────────────────────────────────────────────────

# 07:00 — Daily planning + meeting prep
openclaw cron create --name calendarcaptain-morning --agent calendarcaptain --cron "0 7 * * 1-5" --tz "$TZ" \
  --message "Morning planning. Use Google Calendar MCP to check today's schedule.
1) Write calendar/TODAY.md with time blocks, priorities, meeting list
2) For each meeting today:
   - Check if it's a sales meeting → pull SPIN note from pipedrive/spin-notes/
   - Check deal status in pipedrive/PIPELINE_STATUS.md
   - Check intel from intel/DAILY-INTEL.md for relevant news about the company
   - Write meeting prep to calendar/meeting-prep/[date]-[company].md
3) Flag conflicts or overbooked slots
4) Suggest optimal time blocks for deep work, follow-ups, admin."

# 18:00 — EOD summary + tomorrow prep
openclaw cron create --name calendarcaptain-eod --agent calendarcaptain --cron "0 18 * * 1-5" --tz "$TZ" \
  --message "End-of-day wrap. Use Google Calendar MCP to check tomorrow's schedule.
1) Summarize today: what meetings happened, any outcomes noted
2) Prep calendar/TOMORROW_PREP.md with tomorrow's meetings and prep needed
3) Flag any meetings that need SPIN notes not yet generated (alert PipelinePilot)
4) Suggest follow-up emails for today's meetings (alert InboxForge/CopyAgent)"

# ──────────────────────────────────────────────────
# 7. REVIEWER — Quality Control + Josef Coaching (4 jobs)
# ──────────────────────────────────────────────────

# 17:30 — Daily health check
openclaw cron create --name reviewer-health --agent reviewer --cron "30 17 * * 1-5" --tz "$TZ" \
  --message "Daily agent health check. For each agent, evaluate:
1) Did their cron jobs produce real output today? (check file modification times)
2) Quality score 1-5 for each output file
3) Are there stale/empty placeholder files?
4) Any errors in agent logs?
Write comprehensive report to reviews/HEALTH_REPORT.md with:
- Per-agent score card
- Top 3 issues to fix
- Improvement trend (better/worse than yesterday)
- Specific file paths of empty/stale outputs
This is the accountability mechanism — be honest and specific."

# 22:00 — Josef prompt coaching
openclaw cron create --name reviewer-coaching --agent reviewer --cron "0 22 * * 1-5" --tz "$TZ" \
  --message "Josef prompt coaching session. Analyze today's interactions:
1) Review any conversation logs, task assignments, or brief submissions from Josef
2) Identify patterns: what works well, what could be more efficient
3) Suggest improvements for:
   - How to give better briefs to agents
   - How to structure tasks for faster execution
   - Communication patterns that save time
   - Tools or workflows Josef might not be using
Write to reviews/prompt-coaching/[date].md.
Be constructive, specific, and practical — Josef doesn't want theory, he wants actionable tips."

# Friday 18:00 — Weekly system review
openclaw cron create --name reviewer-weekly --agent reviewer --cron "0 18 * * 5" --tz "$TZ" \
  --message "Weekly comprehensive system review. Analyze the entire agent army's performance this week:
1) Read all HEALTH_REPORT.md entries from this week
2) Count real outputs vs empty runs per agent
3) Identify the best-performing and worst-performing agent
4) Review knowledge/IMPROVEMENT_PROPOSALS.md — which proposals were implemented?
5) Check pipeline impact — did agent work correlate with deal progress?
6) Review prompt coaching notes — is Josef's efficiency improving?
Write to reviews/WEEKLY_REVIEW.md with:
- Week summary (3 sentences)
- Per-agent report card
- Top 5 improvements to implement next week
- System architecture recommendations"

# 22:30 — Night security + git sync
openclaw cron create --name reviewer-night --agent reviewer --cron "30 22 * * *" --tz "$TZ" \
  --message "Night security check and knowledge integrity.
1) Verify no sensitive data (API tokens, passwords, personal emails) leaked into git-tracked files
2) Check .secrets/ files are in .gitignore
3) Verify all agents wrote valid output (no truncated files, no corruption)
4) Run git add + commit for today's changes (with descriptive message)
5) Push to origin if clean
Write findings to reviews/SYSTEM_HEALTH.md."

# ──────────────────────────────────────────────────
# 8. BRIDGE — User-Facing Reports (2 jobs)
# ──────────────────────────────────────────────────

# 08:00 — Morning report for Josef
openclaw cron create --name bridge-am-report --agent main --cron "0 8 * * 1-5" --tz "$TZ" \
  --message "Morning report for Josef. Read the latest outputs from all agents:
- pipedrive/PIPELINE_STATUS.md (deals, overdue, scoring)
- pipedrive/DEAL_SCORING.md (top deals)
- calendar/TODAY.md (today's schedule)
- inbox/TRIAGE.md (important emails)
- intel/DAILY-INTEL.md (market news)
- reviews/HEALTH_REPORT.md (system status)
Compose a MAX 20-line Czech report with sections:
1) Dnes je důležité (today's priorities + meetings)
2) Pipeline (key numbers, urgent deals)
3) Co agenti udělali (overnight work summary)
4) Potřebuji od tebe (decisions, approvals needed)
No agent names, no task IDs. Write to knowledge/USER_DIGEST_AM.md."

# 18:30 — Evening report for Josef
openclaw cron create --name bridge-pm-report --agent main --cron "30 18 * * 1-5" --tz "$TZ" \
  --message "Evening report for Josef. Read today's full output from all agents.
Compose MAX 20-line Czech evening report:
1) Co se dnes podařilo (deals moved, content produced, knowledge gained)
2) Pipeline update (changes since morning)
3) Na zítra (tomorrow's prep status, meetings ahead)
4) Potřebuji od tebe (pending approvals, decisions for tomorrow)
Write to knowledge/USER_DIGEST_PM.md."

echo ""
echo "══════════════════════════════════════════════════"
echo " Agent Army Cron v2 — 35 jobs registered"
echo "══════════════════════════════════════════════════"
echo " PipelinePilot:    8 jobs (enrichment, SPIN, scoring, hygiene, learning)"
echo " KnowledgeKeeper:  5 jobs (3x book study, synthesis, deep read)"
echo " CopyAgent:        4 jobs (briefs, Slack, polish, content plan)"
echo " GrowthLab:        3 jobs (research, competitive, battle cards)"
echo " InboxForge:       3 jobs (Gmail scan, follow-ups, drafts)"
echo " CalendarCaptain:  2 jobs (morning plan, EOD)"
echo " Reviewer:         4 jobs (health, coaching, weekly, security)"
echo " Bridge:           2 jobs (AM/PM reports)"
echo "══════════════════════════════════════════════════"
echo " Key fix: pipedrive.env now uses 'export' — API calls will work"
echo " Agent naming: using pipelinepilot + calendarcaptain (canonical names)"
echo "══════════════════════════════════════════════════"
