# Behavera Sales Engine 2.0 — Hybrid Claude/OpenClaw Blueprint

_Last updated: 2026-03-06_

## 1. Objectives & Success Metrics

| Dimension | Current | Target (90 days) | Metric Source |
|-----------|---------|------------------|---------------|
| Qualified sales convos / week | 6–8 | 20+ | Pipedrive activity log |
| Deals advanced per week | 2–3 | 8–10 | Pipedrive stage transitions |
| Content assets shipped / week | 2–3 | 6–7 | Notion/Docs publish log |
| Time spent on ops/tooling | 10–12 h/w | < 2 h/w | Google Calendar time audit |
| Lead follow-up SLA | 12–24 h | < 2 h | Gmail label age |

## 2. Target Architecture (3 Layers)

1. **Interaction Layer — Claude.ai + Claude Desktop (Cowork)**
   - MCP connectors enabled: Gmail, Slack, Google Calendar, Google Drive, Pipedrive, Clay, Apollo, Figma, tl;dv, Make Webhooks.
   - Core Skills (Markdown):
     - `spin-sales-prep` → fetch Pipedrive deal, Clay/Apollo intel, craft SPIN brief.
     - `cz-b2b-copywriter` → enforce Czech tone and style for outbound comms.
     - `sales-ops-guardian` → watches for stale reminders, missing notes, unlogged calls.
   - Memory slots: lead-specific facts, objections, last commitments.

2. **Automation Layer — Make.com (primary orchestrator)**
   - Scheduled automations (cron-like reliability without local cron jobs).
   - Event-driven automations triggered by Pipedrive webhooks, Gmail labels, tl;dv exports.
   - Claude API module for reasoning-heavy steps, Clay/Apollo modules for enrichment.

3. **Edge Layer — Thin Clawdia Bot & Residual Scripts**
   - Telegram bot acts only as a proxy to Claude (no local reasoning, no cron).
   - Optional lightweight Python scripts (hosted on Render/Fly) for specific webhooks if Make lacks connector depth.

## 3. Claude Configuration Checklist

| Item | Action | Notes |
|------|--------|-------|
| Claude Desktop (Cowork) | Install, sign in (Max plan), grant full disk access | Provides local file/browse automation |
| MCP Connector Pack | Enable Gmail, Google Calendar, Google Drive, Slack, Pipedrive, Clay, Apollo, Figma | Use Anthropic workspace settings |
| Custom MCP (tl;dv) | Add via MCP endpoint | Needed for transcript retrieval |
| Skills Library | Store in Git repo, sync via Claude Skills CLI | Add tests & linting |
| Memory Governance | Weekly prune (Make scenario prompts Claude to summarize/prune) | Prevents drift + token waste |

## 4. Make.com Scenario Portfolio

### 4.1 Morning Briefing (Daily 07:00)
- Triggers at 06:55 CET.
- Steps:
  1. Pull Google Calendar events for next 48h.
  2. Query Gmail label `needs-reply` for unread threads.
  3. Pipedrive API: deals without activity in last 48h + hot leads stage.
  4. Clay enrichment refresh for net-new contacts.
  5. Claude API: synthesize briefing (calendar, inbox, pipeline, flags).
  6. Deliver via Slack DM + Telegram bot message.

### 4.2 Lead Enrichment + Follow-up
- Trigger: New person or deal in Pipedrive (webhook).
- Flow:
  1. Fetch contact/company details.
  2. Clay enrichment → job title, funding, team size.
  3. Apollo email intelligence (if missing data).
  4. Claude API: generate personalized outreach draft (Czech & English variants).
  5. Save draft in Gmail, attach summary in Pipedrive note, Slack notification for approval.

### 4.3 Post-Call Package
- Trigger: tl;dv meeting exported to Drive.
- Flow:
  1. Grab transcript + highlights.
  2. Claude summarization skill: call recap, SPIN data (Situation, Problem, Implication, Need-payoff), action items.
  3. Update Pipedrive deal note + schedule next task.
  4. Draft follow-up email referencing action items.

### 4.4 Content Conveyor
- Trigger: Weekly template on Monday 08:00.
- Flow:
  1. Pull content backlog (Google Sheet/Notion DB).
  2. Claude generates 5 LinkedIn posts + 1 long-form outline.
  3. Reviewer Skill runs on outputs.
  4. Store drafts in Google Docs, queue posts in Buffer (via Make connector).

### 4.5 Pipeline Hygiene
- Daily 18:00.
- Steps: Identify deals with no activity > 3 days, tasks overdue, missing decision maker info. Claude crafts reminder digest + suggested nudges.

## 5. Residual Lightweight Automations

| Need | Solution |
|------|----------|
| Telegram quick asks | Clawdia thin proxy → Claude `/beta/messages` endpoint. Handles short commands (`/brief`, `/lead <name>`). |
| High-availability webhooks | Use supabase/functions or Fly.io Micro VM to receive vendor webhooks, forward to Make via custom webhook if reliability required. |
| Local file operations (e.g., export to Keynote) | Use Claude Cowork with OS automations; fallback to simple AppleScript wrappers triggered manually. |

## 6. Implementation Roadmap (10 Working Days)

### Week 1 — Foundations
1. **Day 1** — Claude workspace hardening: enable MCPs, import skills, smoke-test Pipedrive connector.
2. **Day 2** — Gmail/Calendar migration: disable InboxForge cron, replicate workflows inside Claude (triage prompts, auto-draft instructions).
3. **Day 3** — Morning briefing scenario in Make (MVP). Validate Slack/Telegram delivery.
4. **Day 4** — Lead enrichment flow (Pipedrive → Clay → Gmail drafts). QA personalization quality.
5. **Day 5** — Decommission DealOps/Timebox cron jobs; document new SOP in `knowledge/SALES_ENGINE.md`.

### Week 2 — Automation Depth
6. **Day 6** — Post-call package integration (tl;dv + Claude). Backfill last 5 calls to test reliability.
7. **Day 7** — Content conveyor scenario; hook Reviewer Skill for QA.
8. **Day 8** — Simplify Clawdia bot (proxy only). Redeploy on lightweight serverless host.
9. **Day 9** — End-to-end dry run (briefing → call prep → call → follow-up). Capture gaps.
10. **Day 10** — Kill remaining OpenClaw cron jobs, archive configs, create rollback doc.

## 7. Operating Model & SOP Highlights

- **Daily cadence**
  - 07:00 briefing (Make).
  - 07:30 inbox zero with Claude triage.
  - 08:00–12:00 sales calls (Claude SPIN prep per call).
  - Immediate post-call automation triggered by tl;dv.
  - 16:00 pipeline hygiene (Claude reminder digest).

- **Weekly reviews**
  - Monday: Content planning, adjust Claude skill prompts based on engagement data.
  - Wednesday: Pipeline review with Claude summarizing stuck deals.
  - Friday: Automation health check (Make scenario logs, Claude skill errors).

- **Quality guardrails**
  - Reviewer Skill enforces tone + fact accuracy before publishing.
  - Claude memory pruning ensures no outdated pricing/positioning lingers.
  - Make scenarios emit success/fail metrics to Slack for transparency.

## 8. Risk & Mitigation

| Risk | Impact | Mitigation |
|------|--------|------------|
| Claude API/service outage | Sales ops slowdown | Keep lean backup prompts in OpenAI GPT-4.1 (manual). Maintain text templates library. |
| Make scenario failure | Missed briefings/follow-ups | Configure failure routing (Slack alert + manual SOP). Use scenario versioning & automatic retries. |
| Data leakage via connectors | Compliance risk | Scope access to Behavera workspace, review connector permissions monthly, log Claude conversations touching customer PII. |
| Skill drift (incorrect tone/action) | Brand/revenue impact | Weekly sample QC, maintain regression tests (Claude Skills CLI `test`). |
| Telegram bot abuse | Noise/security | Rate limit commands, require whitelisted user IDs, disable sensitive commands. |

## 9. Decommission Checklist for OpenClaw

1. Snapshot current workspace (git tag + zip) for archival.
2. Disable cron scheduler (`openclaw cron disable-all` after validation).
3. Export knowledge artifacts to Google Drive (Claude-accessible).
4. Update `AGENTS.md`, `SOUL.md`, `HEARTBEAT.md` to reflect retired agents.
5. Document new runbook in `knowledge/SALES_ENGINE.md`.

## 10. Next Steps

1. Approve roadmap + allocate 2 focused weeks (block calendar now).
2. Prep credentials list (Pipedrive API token, Clay, Apollo, Make, Slack, Gmail service account).
3. Spin up shared repo for Claude Skills + Make scenario definitions (version control!).
4. Kick off with Claude workspace reconfiguration (Day 1 task).

Once this blueprint is in motion, OpenClaw drops from “science project that runs your life” to “small toolkit for niche jobs,” while Claude+Make carry the revenue-critical load. This is the fastest path to 10× output with minimum maintenance overhead.
