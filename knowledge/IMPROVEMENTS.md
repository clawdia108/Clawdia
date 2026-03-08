# Improvements — Deep System Improvement Backlog

> 60 tasks across 6 categories. Each task has: ID, subject, description, activeForm (present continuous).
> Status: OPEN | IN_PROGRESS | DONE

---

## INFRASTRUCTURE (Tasks 29-38)

### Task 29 [DONE]: Add structured JSON logging across all scripts
**Status:** DONE
**Active:** Adding structured JSON logging across all scripts
**Description:** Replace plain-text log output in all shell and Python scripts with structured JSON lines (timestamp, level, source, message, metadata). This enables log parsing, filtering, and feeding into analytics dashboards. Update `notify.sh`, `orchestrator.py`, `sales-autopilot.sh`, and all other scripts in `/scripts/`.

### Task 30 [DONE]: Build config manager — centralize all configuration
**Status:** DONE
**Active:** Building a centralized config manager
**Description:** Create a single `config.json` or `config.yaml` that holds all configuration currently scattered across individual scripts (API URLs, thresholds, file paths, timing intervals). Build a Python module and shell helper that reads from this central config, so changes propagate everywhere from one file.

### Task 31 [DONE]: Add health endpoint for external monitoring
**Status:** DONE
**Active:** Adding a health endpoint for external monitoring
**Description:** Spin up a lightweight HTTP server on localhost (e.g., port 9090) that exposes `/health` and `/status` endpoints. The health endpoint returns OK/DEGRADED/DOWN based on last heartbeat age, orchestrator PID, and critical file freshness. This allows external uptime monitors (UptimeRobot, Healthchecks.io) to watch Clawdia.

### Task 32: Build log aggregator — unified timeline from all logs
**Status:** DONE
**Active:** Building a log aggregator for unified timeline
**Description:** Create a script that merges logs from all sources (orchestrator, heartbeat, sales-autopilot, agent outputs, cron) into a single chronological timeline. Output as both a readable text file and a JSON array. Include source tagging so you can filter by component.

### Task 33 [DONE]: Add file locking to prevent concurrent writes
**Status:** DONE
**Active:** Adding file locking to prevent concurrent writes
**Description:** Implement file locking (using `flock` in shell scripts, `fcntl` in Python) for all shared state files — `EXECUTION_STATE.json`, `score_state.json`, `PIPELINE_STATUS.md`, `HEARTBEAT.md`. This prevents data corruption when the orchestrator and heartbeat scripts write simultaneously.

### Task 34 [DONE]: Build backup system for critical state files
**Status:** DONE
**Active:** Building a backup system for critical state files
**Description:** Create a backup script that snapshots all critical state files (JSON state, scoring data, pipeline status, task queue) every hour into a timestamped directory under `backups/`. Keep last 48 snapshots, auto-rotate older ones. Add a restore command that can roll back to any snapshot.

### Task 35 [DONE]: Add rate limiter for external API calls
**Status:** DONE
**Active:** Adding a rate limiter for external API calls
**Description:** Build a rate-limiting wrapper for Pipedrive, Ollama, and any other external API calls. Track calls per minute/hour, enforce configurable limits, and queue excess requests. Log rate limit events. This prevents API quota exhaustion and 429 errors during heavy automation cycles.

### Task 36 [DONE]: Build dependency checker for all tools and packages
**Status:** DONE
**Active:** Building a dependency checker for tools and packages
**Description:** Create a pre-flight script that verifies all required tools are installed and accessible — Python 3, required pip packages, jq, curl, ollama, launchctl services. Output a clear pass/fail checklist with install instructions for anything missing. Run automatically on orchestrator startup.

### Task 37 [DONE]: Add graceful shutdown handling to orchestrator
**Status:** DONE
**Active:** Adding graceful shutdown handling to orchestrator
**Description:** Register SIGTERM and SIGINT signal handlers in `orchestrator.py` so it finishes the current task cycle, writes a clean shutdown marker to `EXECUTION_STATE.json`, and exits cleanly. Currently a kill leaves orphaned state that the next startup has to reconcile.

### Task 38 [DONE]: Build rollback mechanism for failed state updates
**Status:** DONE
**Active:** Building a rollback mechanism for failed state updates
**Description:** Before any write to a state file, copy the current version to a `.bak` sidecar. If the write fails or produces invalid JSON, automatically restore from `.bak`. Add a `--rollback` flag to key scripts that restores the last known-good state for any given file.

---

## AGENT IMPROVEMENTS (Tasks 39-48)

### Task 39 [DONE]: Add agent capability auto-discovery from IDENTITY.md
**Status:** DONE
**Active:** Adding agent capability auto-discovery from IDENTITY.md files
**Description:** Parse each agent's `IDENTITY.md` file to extract declared capabilities, tools, and specializations into a structured registry. Build an `agent_registry.json` that maps agent names to their capabilities, so the system can programmatically match tasks to agents without hardcoded routing.

### Task 40 [DONE]: Build agent skill router — match tasks by capability score
**Status:** DONE
**Active:** Building an agent skill router for task matching
**Description:** Create a routing engine that scores each available agent against an incoming task based on capability overlap, current load, and past success rate. Return a ranked list of best-fit agents. This replaces the current manual `for: AgentName` tagging in TASK_QUEUE with intelligent auto-assignment.

### Task 41: Add agent warm-up protocol — pre-check deps before first task
**Status:** DONE
**Active:** Adding an agent warm-up protocol
**Description:** Before an agent claims its first task, run a warm-up sequence that checks all its dependencies are available — required files exist, APIs are reachable, credentials are valid, local models are loaded. Report warm-up status to the bus. Block task assignment until warm-up passes.

### Task 42 [DONE]: Build agent collaboration protocol for multi-agent tasks
**Status:** DONE
**Active:** Building an agent collaboration protocol
**Description:** Design and implement a protocol where 2+ agents can work on the same task in defined roles (lead, support, reviewer). Define handoff points, shared workspace directories, and conflict resolution for concurrent outputs. Start with a simple pattern: one agent drafts, another reviews.

### Task 43 [DONE]: Add agent context sharing — agents read each other's outputs
**Status:** DONE
**Active:** Adding agent context sharing capability
**Description:** Build a shared context layer where agents can publish key outputs (summaries, findings, decisions) to a common location that other agents can query. Use a structured format (JSON with agent, timestamp, topic, content) so consuming agents can filter for relevant context without reading raw files.

### Task 44 [DONE]: Build agent priority queue for task processing
**Status:** DONE
**Active:** Building an agent priority queue
**Description:** Replace the flat UNCLAIMED list with a proper priority queue that agents pull from. Implement CRITICAL > HIGH > MEDIUM > LOW ordering with FIFO within each level. Add task age escalation — a MEDIUM task that sits for 4+ hours auto-escalates to HIGH. Persist queue state to JSON.

### Task 45 [DONE]: Add agent resource limits — max concurrent tasks per agent
**Status:** DONE
**Active:** Adding agent resource limits
**Description:** Implement per-agent concurrency limits that prevent any single agent from hoarding tasks or overloading. Track active tasks per agent in a `agent_load.json` file. Default limit: 1 task. Configurable per agent type. The skill router checks load before assignment.

### Task 46 [DONE]: Build agent handoff protocol for structured transfers
**Status:** DONE
**Active:** Building an agent handoff protocol
**Description:** Create a formal handoff mechanism when one agent needs to pass work to another (e.g., GrowthLab researches a lead, then hands to CopyAgent for email drafting). The handoff includes: task context, work done so far, expected next steps, and any artifacts produced. Logged to the bus for traceability.

### Task 47 [DONE]: Add agent health self-check — validate own outputs
**Status:** DONE
**Active:** Adding agent health self-checks
**Description:** Each agent runs a self-validation step after producing output — checking that files were actually written, JSON is valid, required fields are present, and output meets minimum quality bar (e.g., email draft has subject + body + recipient). Report self-check results to the bus with pass/fail and details.

### Task 48 [DONE]: Build agent metrics dashboard — per-agent performance
**Status:** DONE
**Active:** Building an agent metrics dashboard
**Description:** Track and display per-agent metrics over time: tasks completed, average completion time, success/failure rate, output quality scores. Store metrics in `agent_metrics.json`, updated after each task. Build a terminal-printable summary and a JSON API endpoint for the dashboard.

---

## SALES AUTOMATION (Tasks 49-58)

### Task 49: Build automatic lead enrichment pipeline
**Status:** DONE
**Active:** Building an automatic lead enrichment pipeline
**Description:** Create an end-to-end pipeline that takes a new Pipedrive deal and automatically enriches it with data from LinkedIn (via Lusha API), company website scraping, and public databases. Populate deal custom fields with employee count, tech stack, decision-maker contacts, and recent news. Trigger on deal creation.

### Task 50 [DONE]: Add deal stage change detection with triggered actions
**Status:** DONE
**Active:** Adding deal stage change detection
**Description:** Monitor Pipedrive for deal stage transitions (e.g., Lead -> Qualified, Qualified -> Proposal). On each transition, trigger stage-specific actions: update SPIN notes, schedule follow-ups, generate stage-appropriate email templates, alert Josef. Use Pipedrive webhooks or polling with diff detection.

### Task 51 [DONE]: Build competitive intelligence collector
**Status:** DONE
**Active:** Building a competitive intelligence collector
**Description:** Create an automated system that monitors competitor mentions across news, social media, and industry sites. Track competitors like Peakon, Culture Amp, Officevibe. Aggregate findings into `intel/competitive/` with alerts for significant moves (pricing changes, new features, partnerships). Run weekly.

### Task 52 [DONE]: Add email template personalization engine
**Status:** DONE
**Active:** Adding an email template personalization engine
**Description:** Build an engine that takes email templates and merges in deal-specific data — company name, contact name, industry pain points, recent company news, deal stage context. Use Ollama for generating personalized opening lines. Output ready-to-send drafts with personalization quality scoring.

### Task 53 [DONE]: Build meeting prep auto-generator
**Status:** DONE
**Active:** Building a meeting prep auto-generator
**Description:** Before any scheduled call or demo, automatically compile a prep document: company background, deal history, last interaction summary, SPIN questions for this stage, competitor comparison points, and recommended talking points. Pull from Pipedrive deal data, enrichment data, and knowledge base.

### Task 54 [DONE]: Add deal velocity tracker
**Status:** DONE
**Active:** Adding a deal velocity tracker
**Description:** Track how long each deal spends in every pipeline stage. Calculate averages, identify deals moving slower than normal, and flag stalled deals before they go cold. Store velocity data per deal in `pipedrive/deal_velocity.json`. Compare individual deals against pipeline averages in the dashboard.

### Task 55 [DONE]: Build win/loss analysis system
**Status:** DONE
**Active:** Building a win/loss analysis system
**Description:** After a deal closes (won or lost), automatically generate an analysis: what worked, what didn't, time in pipeline, number of touchpoints, competitive factors, and deal characteristics. Aggregate patterns over time to identify what winning deals have in common. Store in `reviews/win_loss/`.

### Task 56: Add referral network builder
**Status:** DONE
**Active:** Adding a referral network builder
**Description:** Track connections between contacts across deals — who referred whom, which companies share board members, industry connections. Build a graph of relationships that surfaces warm introduction paths to new prospects. Store in `leads/referral_network.json` and surface relevant connections during lead research.

### Task 57: Build proposal auto-generator from deal context
**Status:** DONE
**Active:** Building a proposal auto-generator
**Description:** Given a deal's context (company size, pain points, selected product tier, competitive situation), auto-generate a proposal document from templates. Include personalized ROI calculations, relevant case studies, pricing, and implementation timeline. Output as markdown and PDF-ready format.

### Task 58 [DONE]: Add follow-up cadence engine
**Status:** DONE
**Active:** Adding a follow-up cadence engine
**Description:** Define stage-specific follow-up cadences (e.g., after demo: day 1 thank-you, day 3 case study, day 7 check-in, day 14 nudge). Auto-schedule these touchpoints when a deal enters a stage. Track execution, skip if the prospect responds, and escalate if no engagement after full cadence.

---

## KNOWLEDGE & INTELLIGENCE (Tasks 59-68)

### Task 59 [DONE]: Build knowledge graph for deals, contacts, and companies
**Status:** DONE
**Active:** Building a knowledge graph
**Description:** Create a graph data structure linking deals, contacts, companies, interactions, and insights. Enable queries like "which companies in manufacturing have we contacted in the last 30 days?" or "what topics came up with companies that converted?" Store as JSON adjacency list with typed edges.

### Task 60: Add automatic meeting notes processor
**Status:** DONE
**Active:** Adding an automatic meeting notes processor
**Description:** Build a pipeline that takes raw meeting notes (or audio transcription output) and extracts: key decisions, action items, follow-ups, objections raised, and next steps. Structure the output into a standard format and link to the relevant Pipedrive deal. Store in `knowledge/meeting_notes/`.

### Task 61: Build market trend detector from intel data
**Status:** DONE
**Active:** Building a market trend detector
**Description:** Analyze accumulated market intelligence data over time to identify emerging trends — growing industries, shifting buyer priorities, new technology adoption patterns. Use Ollama to classify and cluster intel entries, then surface trend summaries weekly. Store trend reports in `intel/trends/`.

### Task 62: Add competitor pricing tracker
**Status:** DONE
**Active:** Adding a competitor pricing tracker
**Description:** Monitor competitor pricing pages and public pricing information for changes. Track historical pricing data points for Peakon, Culture Amp, Officevibe, and others. Alert when significant changes are detected (new tier, price increase/decrease, feature bundling changes). Store in `intel/competitive/pricing.json`.

### Task 63: Build customer success predictor
**Status:** DONE
**Active:** Building a customer success predictor
**Description:** Analyze historical deal patterns to predict which current deals are most likely to succeed. Score based on: engagement velocity, number of stakeholders involved, response times, stage duration vs. averages, and deal characteristics. Surface predictions in the pipeline dashboard with confidence scores.

### Task 64: Add knowledge deduplication — merge duplicate insights
**Status:** DONE
**Active:** Adding knowledge deduplication
**Description:** Build a dedup engine that identifies similar or duplicate knowledge entries across the knowledge base. Use text similarity (Jaccard, cosine with Ollama embeddings) to find near-duplicates. Present merge candidates for review, auto-merge high-confidence duplicates. Run weekly as a maintenance task.

### Task 65: Build book/article insight extractor
**Status:** DONE
**Active:** Building a book and article insight extractor
**Description:** Create a pipeline that takes book notes, article links, or pasted text and extracts actionable insights relevant to Behavera's business. Tag insights by category (sales technique, product idea, market trend, operational improvement). Cross-reference with existing knowledge and surface relevant insights during agent tasks.

### Task 66 [DONE]: Add weekly strategic brief — synthesize all intelligence
**Status:** DONE
**Active:** Adding a weekly strategic brief
**Description:** Every Sunday evening, automatically compile a strategic brief from all intelligence gathered that week: pipeline changes, competitive moves, market trends, win/loss patterns, and agent performance. Prioritize the top 3-5 actionable recommendations. Output to `reviews/strategic_brief/` and notify Josef.

### Task 67: Build FAQ auto-generator from customer interactions
**Status:** DONE
**Active:** Building an FAQ auto-generator
**Description:** Analyze email exchanges, call notes, and demo feedback to identify recurring questions and objections. Auto-generate FAQ entries with answers derived from successful responses. Organize by topic (pricing, implementation, ROI, security). Keep in `knowledge/faq.md` and update weekly.

### Task 68: Add industry news filter — relevant articles from web sources
**Status:** DONE
**Active:** Adding an industry news filter
**Description:** Set up RSS/web monitoring for HR tech, employee engagement, and Czech business news. Filter articles for relevance using Ollama classification. Summarize relevant articles and store in `intel/news/`. Surface top 3 articles in the morning briefing. Track sources that consistently produce useful content.

---

## UX & WORKFLOW (Tasks 69-78)

### Task 69: Build voice command integration for terminal control
**Status:** DONE
**Active:** Building voice command integration
**Description:** Add voice-to-text capability that lets Josef speak commands to Clawdia from the terminal. Use macOS built-in speech recognition or Whisper for transcription. Map spoken commands to existing operations (check pipeline, run briefing, score deals). Keep the command vocabulary small and reliable.

### Task 70 [DONE]: Add quick-action shortcuts for common operations
**Status:** DONE
**Active:** Adding quick-action shortcuts
**Description:** Create a `clawdia` CLI wrapper with short commands for the most common operations: `clawdia status`, `clawdia deals`, `clawdia brief`, `clawdia score`, `clawdia logs`. Each maps to the underlying script with sensible defaults. Add tab completion for zsh. Keep it under 100 lines of shell script.

### Task 71 [DONE]: Build daily standup generator for team meetings
**Status:** DONE
**Active:** Building a daily standup generator
**Description:** Auto-generate a 3-bullet standup summary every morning: what was done yesterday (from execution state + completed tasks), what's planned today (from task queue + scheduled jobs), and blockers (from error logs + stale deals). Format for quick copy-paste into Slack or email.

### Task 72: Add time tracking integration for deals and tasks
**Status:** DONE
**Active:** Adding time tracking integration
**Description:** Track how much time is spent on each deal and task category. Log start/end times when agents claim and complete tasks. Aggregate into weekly time reports showing: time per deal, time per task type, most time-consuming activities. Store in `reviews/time_tracking/`. Surface insights about where effort goes.

### Task 73: Build report generator for stakeholder reports
**Status:** DONE
**Active:** Building a report generator
**Description:** Create a weekly/monthly report generator that compiles pipeline metrics, win rates, deal velocity, agent performance, and system health into a polished format. Output as markdown (for terminal) and HTML (for email/browser). Include charts rendered as ASCII art in terminal mode. Template-driven for easy customization.

### Task 74: Add Slack integration for key notifications
**Status:** DONE
**Active:** Adding Slack integration for notifications
**Description:** Connect Clawdia to a Slack channel for push notifications on critical events: deal stage changes, system errors, morning briefing ready, scorecard updates, stale deal alerts. Use Slack webhook for outbound. Keep notification volume low — only genuinely important events, not every log line.

### Task 75 [DONE]: Build mobile-friendly status page
**Status:** DONE
**Active:** Building a mobile-friendly status page
**Description:** Create a simple static HTML status page (served locally or deployed to Vercel) that shows system health, pipeline summary, today's tasks, and recent alerts. Designed for phone screen — large text, color-coded status indicators, tap-to-expand details. Auto-refresh every 5 minutes.

### Task 76: Add keyboard shortcut system for terminal dashboard
**Status:** DONE
**Active:** Adding keyboard shortcuts for the terminal dashboard
**Description:** If/when a terminal dashboard exists, add keyboard shortcuts for common actions: `r` to refresh, `d` for deals view, `a` for agents view, `l` for logs, `q` to quit. Use Python `curses` or similar for key capture. Display shortcut legend at the bottom of the dashboard.

### Task 77: Build quick deal lookup — instant context by company name
**Status:** DONE
**Active:** Building a quick deal lookup tool
**Description:** Create a `clawdia lookup <company>` command that instantly returns everything the system knows about a deal: stage, value, contacts, last activity, SPIN notes, enrichment data, email history, and next scheduled action. Pull from Pipedrive + local knowledge. Format for quick terminal reading.

### Task 78 [DONE]: Add natural language task creation
**Status:** DONE
**Active:** Adding natural language task creation
**Description:** Let Josef type a task description in plain language (e.g., "research Keboola's new product launch") and have the system automatically parse it into a structured task: assign priority, identify target agent, extract keywords, and add to TASK_QUEUE. Use Ollama for NLP parsing. Confirm before adding.

---

## TESTING & QUALITY (Tasks 79-88)

### Task 79 [DONE]: Add unit tests for agent_bus.py
**Status:** DONE
**Active:** Adding unit tests for agent_bus.py
**Description:** Write comprehensive unit tests for the agent bus module covering: message publishing, subscription, message routing, error handling, and edge cases (malformed messages, missing agents, bus overflow). Use pytest. Mock external dependencies. Target 90%+ coverage of bus logic.

### Task 80 [DONE]: Add unit tests for workflow_engine.py
**Status:** DONE
**Active:** Adding unit tests for workflow_engine.py
**Description:** Write unit tests for the workflow engine covering: workflow definition parsing, step execution order, conditional branching, error recovery, and state persistence. Use pytest with fixtures for sample workflows. Test both happy path and failure scenarios for each workflow type.

### Task 81 [DONE]: Add unit tests for agent_lifecycle.py
**Status:** DONE
**Active:** Adding unit tests for agent_lifecycle.py
**Description:** Write unit tests for agent lifecycle management: agent creation, initialization, task assignment, execution tracking, and shutdown. Test state transitions (idle -> active -> completing -> idle). Mock the bus and file system. Verify lifecycle hooks fire in correct order.

### Task 82: Add integration test for full orchestration cycle
**Status:** DONE
**Active:** Adding an integration test for full orchestration cycle
**Description:** Build an end-to-end integration test that runs one complete orchestrator cycle with mocked external APIs. Verify: task pickup, agent assignment, execution, state updates, heartbeat, and cleanup all work together. Use temporary directories for state files. Should complete in under 30 seconds.

### Task 83 [DONE]: Build smoke test suite for all scripts
**Status:** DONE
**Active:** Building a smoke test suite for all scripts
**Description:** Create a test runner that imports/sources every script in `/scripts/` and verifies it can at least parse without errors. For Python scripts, test import. For shell scripts, test `bash -n` (syntax check). For scripts with `--help` flags, verify they respond. Report pass/fail per script.

### Task 84: Add regression tests for lead scoring formula
**Status:** DONE
**Active:** Adding regression tests for lead scoring formula
**Description:** Lock down the current lead scoring logic with a set of test cases: known inputs that should produce known scores. Cover edge cases (missing data, zero values, maximum scores). Run these tests before any change to scoring logic. Store test cases in `tests/fixtures/scoring_cases.json`.

### Task 85: Build chaos testing framework for recovery verification
**Status:** DONE
**Active:** Building a chaos testing framework
**Description:** Create a test harness that randomly injects failures — corrupt a state file, kill the orchestrator mid-cycle, make an API return errors, fill disk space for log directory. Verify the system recovers gracefully in each case. Run monthly as a resilience check. Document expected recovery behavior.

### Task 86 [DONE]: Add data validation for all JSON state files
**Status:** DONE
**Active:** Adding data validation for JSON state files
**Description:** Define JSON schemas for every state file (`EXECUTION_STATE.json`, `score_state.json`, `agent_metrics.json`, etc.). Add validation checks that run before reads and after writes. Reject invalid data with clear error messages. Store schemas in `schemas/`. Use jsonschema Python library.

### Task 87: Build synthetic test data generator
**Status:** DONE
**Active:** Building a synthetic test data generator
**Description:** Create a script that generates realistic but fake test data — Pipedrive deals, contacts, email threads, agent outputs, scoring history. Configurable quantity and characteristics. Use for development and testing without touching production data. Output to a `test-data/` directory.

### Task 88: Add CI/CD pipeline for running tests before deployment
**Status:** DONE
**Active:** Adding a CI/CD pipeline
**Description:** Set up a GitHub Actions workflow that runs on every push: syntax checks for all scripts, unit tests, smoke tests, JSON schema validation, and a basic integration test. Block merges to main if any test fails. Add a status badge to README. Keep pipeline under 3 minutes total.

---

## Summary

| Category | Task Range | Count |
|----------|-----------|-------|
| Infrastructure | 29-38 | 10 |
| Agent Improvements | 39-48 | 10 |
| Sales Automation | 49-58 | 10 |
| Knowledge & Intelligence | 59-68 | 10 |
| UX & Workflow | 69-78 | 10 |
| Testing & Quality | 79-88 | 10 |
| **Total** | **29-88** | **60** |

Completed: **36/60** tasks
Created: 2026-03-07 | Updated: 2026-03-07 20:35
