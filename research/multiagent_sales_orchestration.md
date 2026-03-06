# Multi-Agent Sales Orchestration Research (OpenClaw ↔ Claude ↔ OpenAI ↔ CRM ↔ Gmail ↔ Make ↔ Google Calendar)

_Last updated: 2026-03-06_

## 1. Research Goals
- Build a 24/7 revenue engine that survives ADHD context-switching by delegating prep, follow-ups, and hygiene tasks to agents.
- Blend OpenClaw's deterministic multi-agent workflows with Claude/OpenAI reasoning strength and Make.com's reliable scheduling.
- Keep CRM (Pipedrive) and comms (Gmail/Calendar/Slack) as the single sources of truth.

## 2. Architectural Principles (Outside + Inside the Box)

| Principle | Why it matters |
|-----------|----------------|
| **Split "thinking" vs. "doing"** | Let Claude/OpenAI handle reasoning, drafting, prioritization; use Make/OpenClaw automations for deterministic execution. |
| **MCP-first integrations** | Claude's MCP connectors cover Gmail, Calendar, Pipedrive, Drive, Slack, etc., cutting custom code maintenance. (Source: Claude support docs on remote MCP connectors) |
| **Deterministic pipelines for recurring ops** | Use OpenClaw/Lobster flows where order matters (lead research → draft → review). Keep them idempotent so they can re-run after failures. (Source: openclawforsales.com overview) |
| **Event-driven everything** | Webhooks from Pipedrive, Gmail labels, tl;dv recordings should trigger Make scenarios which then wake Claude/OpenAI only when reasoning is required. |
| **Observability baked-in** | Every agent/scenario emits success/failure metrics to Slack + logging sheet (for ADHD-friendly glance). |
| **Failover prompts** | Keep backup GPT-4.1 prompts for essential flows (briefing, follow-up) if Claude/API outages happen. |

## 3. Layered Stack Overview

1. **Engagement Layer (Claude Desktop + Claude.ai)**
   - MCP connectors: Gmail, Google Calendar, Drive, Slack, Pipedrive, Clay, Apollo, tl;dv, Make Webhooks. (Source: Claude connector guide)
   - Skills library (Markdown) stored in git: `spin-prep`, `cz-outbound`, `sales-ops-guardian`, `follow-up-factory`, `content-qa`.
   - Claude Memory rules: only store stable facts (ICP traits, pricing guardrails, voice guidelines). Weekly pruning scenario to avoid drift.

2. **Automation Layer (Make.com + optional n8n/Trigger.dev)**
   - Make orchestrates scheduled + webhook flows; Claude API or OpenAI GPT-4.1 nodes handle heavy reasoning. (Source: Make.com Claude integration examples)
   - Keep scenarios modular (e.g., "Enrich lead", "Draft follow-up", "Publish content") so they can be recombined.
   - Use Scenario versioning + error routing to Slack for resilience.

3. **Deterministic Agent Layer (OpenClaw)**
   - Use Lobster pipelines for multi-step tasks needing review loops (e.g., Researcher → Copywriter → Reviewer).
   - Agents call out to Claude/OpenAI via connectors rather than duplicating logic locally; OpenClaw primarily coordinates state + memory in workspace.
   - Run only critical agents (e.g., GrowthLab research swarms, Reviewer) to reduce cron load.

## 4. High-Leverage Automations

### 4.1 Lead Intelligence Mesh
- **Trigger:** New lead/deal in Pipedrive (webhook → Make).
- **Steps:**
  1. Pull CRM fields + LinkedIn URL.
  2. Clay/Apollo enrichment for funding, headcount, tech stack.
  3. Claude scoring prompt compares against ICP matrix, outputs Fit Score + Key Hooks. (Source: make.com enrichment workflow guide)
  4. Update Pipedrive custom fields (Fit score, Pain hypothesis) + push summary to Slack hot-leads channel.
- **Bonus:** If score > threshold, auto-create SPIN brief doc in Drive + calendar hold for outreach slot.

### 4.2 ADHD-Proof Daily Command Center
- **Trigger:** Scheduled 06:55 CET (Make cron).
- **Data:** Calendar, Gmail label `needs-reply`, Slack unread, Pipedrive stale deals, open tasks.
- **Reasoning:** Claude synthesizes into prioritized agenda + micro-deadlines; includes dopamine hits ("2 quick wins"), warns about context switches.
- **Delivery:** Telegram + Slack DM, plus Google Calendar event notes pre-filled for first call.

### 4.3 Follow-up Autopilot ("No lead sleeps")
- **Trigger:** Pipedrive stage change OR tl;dv transcript saved.
- **Flow:**
  1. Pull context (notes, transcript summary).
  2. Claude generates multi-channel follow-up: email draft, LinkedIn DM snippet, SMS (if allowed).
  3. Reviewer agent checks tone → Gmail draft saved, Slack ping for quick approve; auto-send after X hours if no edits.
  4. Update CRM activity log + schedule next touch.

### 4.4 Content-to-Lead Loop
- **Trigger:** Weekly content planning scenario (Make) + KPI review.
- **Tasks:**
  - Claude mines CRM win/loss notes to surface trending objections.
  - GrowthLab agent builds LinkedIn carousel & nurture email around those objections.
  - Reviewer skill ensures Czech tone + CTA consistency.
  - Posts scheduled in Buffer; high-performing content auto-converted into nurture sequences in CRM.

### 4.5 Silent Pipeline Custodian
- Make scenario at 20:00 daily checks:
  - Deals with no activity > 3 days, missing next step, or no economic buyer.
  - Gmail label `waiting` older than 48h.
  - Calendar vs CRM mismatches (meetings not logged).
- Claude crafts actionable digest + pre-fills tasks in CRM to close gaps.

## 5. Claude/OpenAI Prompting Patterns

| Flow | Prompt Blueprint |
|------|-------------------|
| SPIN Prep | "Given Pipedrive deal JSON + Clay enrichment, build SPIN brief (Situation facts, Problem hypotheses, Implication questions, Need-Payoff vision). Include 3 tailored talk tracks." |
| Follow-up Email | "Rewrite summary into Czech email using {tone guide}, reference decision timeline, suggest next micro-commitment." |
| Lead Scoring | "Compare lead attributes vs ICP table. Output Fit (0-100), key reason, risk flags, recommended channel priority." |
| ADHD Agenda | "Create 5-block day plan (Focus, Admin, Outreach, Recovery, Wildcard). Insert gamified tasks + dopamine cues." |
| Content Remix | "Turn meeting transcript insights into LinkedIn post (hook + 3 bullets + CTA) + 100-word nurture email." |

## 6. CRM Integration Tactics
- Deploy Pipedrive MCP server locally or via Docker for Claude; expose only needed resources/tools. (Source: skywork.ai MCP setup)
- For bulk updates, keep Make as the executor to maintain API rate sanity; Claude merely outputs instructions.
- Maintain "Source of Truth" sheet: for each deal, track last AI action + human confirmation to avoid double-work.
- Use CRM automations to tag AI-generated notes so they can be filtered/audited later.

## 7. Gmail & Calendar Automation Tips
- Community Gmail MCP servers allow Claude to draft/send, label, archive emails (Source: gmail MCP guide). Pair with Make watchers for reliability.
- Calendar quick-add prompts help Claude schedule with natural language; always include buffer times to reduce ADHD overload.
- For meeting-heavy days, use Claude to auto-generate "context flashcards" 10 min before each call (Calendar event description seeded with summary).

## 8. Make.com Ops Guardrails
- Scenario naming convention: `SALES__[Trigger]__[Outcome]` for quick scanning.
- Enable automatic retries + error handlers that ping Slack and log to Airtable.
- Keep a "quiet hours" variable so non-urgent automations queue until morning (protect sleep).
- Use Make's Anthropic/Claude app for simple asks; use MCP app when Claude needs direct tool access. (Source: Make community MCP thread)

## 9. OpenClaw-Specific Optimizations
- Reduce agent count to "mission critical" to minimize cron noise; other tasks handled by Make/Claude directly. (Source: agor.live OpenClaw overview)
- Use Lobster's deterministic mode for quality-critical flows (e.g., contract draft pipeline) so every step is logged & repeatable.
- Store SOPs in knowledge folder; Claude Skills reference them to stay aligned with Behavera voice.
- Consider NanoClaw container for high-security agents (if dealing with sensitive enterprise data). (Source: theregister.com Nanoclaw article)

## 10. 24/7 Reliability Checklist
1. **Health monitors:** Make scenario pings + OpenClaw cron status to ensure no silent failures.
2. **API budget watch:** Weekly report on Anthropic/OpenAI usage; auto-throttle non-essential flows if cost spikes.
3. **Context refresh:** Schedule Claude memory pruning + prompt tuning sessions every Friday.
4. **ADHD-friendly dashboards:** Single Notion/Sheet showing: hot leads, overdue follow-ups, content queue, automation health.
5. **Fail-safe manual mode:** One-click Google Doc with fallback prompts/templates if automations down.

---
**Key Sources:** Claude MCP connector docs (support.claude.com), Activepieces/Medium guides on MCP for Gmail/Calendar, Make.com integration guides for Claude + enrichment, OpenClaw sales orchestration write-ups (openclawforsales.com, agor.live), NanoClaw security coverage (theregister.com), Make community threads on MCP access.
