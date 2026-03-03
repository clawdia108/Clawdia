#!/usr/bin/env bash
set -euo pipefail

TZ="Europe/Prague"

# ══════════════════════════════════════════════════════════════
# OPENCLAW AGENT ARMY — PRODUCTION CRON CONFIG v3
# "Kombucha Mode" — alive, fermenting, self-improving
# 48 jobs across 8 agents + Bridge
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
  --message "Morning planning. Check Google Calendar. Write calendar/TODAY.md.
For sales meetings: pull SPIN notes, deal status, relevant intel.
Write meeting prep to calendar/meeting-prep/[date]-[company].md."

openclaw cron create --name calendarcaptain-eod --agent calendarcaptain --cron "0 18 * * 1-5" --tz "$TZ" \
  --message "EOD wrap. Check tomorrow's calendar. Write calendar/TOMORROW_PREP.md.
Flag meetings needing SPIN notes. Suggest follow-up emails for today's meetings."

# ──────────────────────────────────────────────────
# 8. REVIEWER — Quality + Coaching + Self-Improvement (4 jobs)
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

echo ""
echo "══════════════════════════════════════════════════"
echo " Agent Army Cron v3 — KOMBUCHA MODE"
echo " 48 jobs across 8 agents + Bridge"
echo "══════════════════════════════════════════════════"
echo " PipelinePilot:    8 jobs (enrichment, SPIN, scoring, hygiene, learning)"
echo " KnowledgeKeeper:  9 jobs (7x book study + synthesis + deep read) — 5-7 books/day"
echo " CopyAgent:        7 jobs (briefs, Slack, polish, blog, blog improve, excerpt, content plan)"
echo " Codex:            4 jobs (morning build, afternoon experiment, evening deploy, weekend deep build)"
echo " GrowthLab:        3 jobs (research, competitive, battle cards)"
echo " InboxForge:       3 jobs (Gmail scan, follow-ups, drafts)"
echo " CalendarCaptain:  2 jobs (morning plan, EOD)"
echo " Reviewer:         4 jobs (health, coaching, weekly, security)"
echo " Bridge:           2 jobs (AM/PM reports)"
echo "══════════════════════════════════════════════════"
echo " NEW: Codex agent — builds, experiments, deploys continuously"
echo " NEW: 7 book study sessions/day (target: 35+ books/week)"
echo " NEW: Daily book excerpt email to Josef"
echo " NEW: Weekly blog + blog improvement on behavera.com"
echo " NEW: Fun facts system — agents share discoveries"
echo " NEW: Self-improvement loop — Codex implements book insights"
echo "══════════════════════════════════════════════════"
