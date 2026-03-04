# TASK_QUEUE.md — Shared Agent Task Board

> Agents claim tasks from here on heartbeat. CommandCenter monitors for stuck tasks.

## How It Works
1. Any agent (or Josef) adds tasks to UNCLAIMED
2. On heartbeat, agent checks for tasks matching their role
3. Agent moves task to IN PROGRESS with name + timestamp
4. After completion, agent moves task to DONE with result summary
5. Tasks stuck IN PROGRESS >2 hours get flagged by CommandCenter

## Priority Levels
- **CRITICAL** — Revenue at risk, do immediately
- **HIGH** — Directly impacts Echo Pulse sales pipeline
- **MEDIUM** — Important but can wait 1-2 heartbeats
- **LOW** — Nice to have, pick up when idle

---

## UNCLAIMED

- [ ] [HIGH] Update SPIN notes for all deals with demos this week | for: PipelinePilot
- [ ] [HIGH] Draft follow-up emails for 4 overdue activities (FNUSA, ProCare, DI industrial, Národní zemědělské muzeum) | for: InboxForge
- [ ] [HIGH] Research companies on tomorrow's call list — find CEO names, employee count, pain points | for: GrowthLab
- [ ] [MEDIUM] Generate 3 fresh cold email variants for manufacturing CEOs | for: CopyAgent
- [ ] [MEDIUM] Cross-reference book insights with agent capabilities, tag improvements | for: KnowledgeKeeper
- [ ] [MEDIUM] Review all cron outputs from last 24h — flag empty/error outputs | for: Reviewer
- [ ] [LOW] Analyze email response patterns — which subject lines get replies? | for: InboxForge
- [ ] [LOW] Build auto-enrichment script for new Pipedrive deals | for: Codex

## IN PROGRESS

(none)

## DONE (today)

(none yet)

---

## Self-Generated Tasks
> Agents add tasks here when they discover work during execution.
> Format: `- [ ] [PRIORITY] Description | source: AgentName | for: TargetAgent`

(none yet)

---

## Rules
1. **Claim before starting.** Move to IN PROGRESS with your name.
2. **One task at a time.** Finish or release before claiming another.
3. **Don't hoard.** If you can't finish in 2 hours, release it.
4. **Cross-pollinate.** If you find work for another agent, add to UNCLAIMED.
5. **Be honest.** If you failed, say so. Don't mark DONE with empty output.
