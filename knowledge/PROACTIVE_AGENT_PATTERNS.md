# Proactive Agent Patterns — Implementation Guide

> Research compiled 2026-03-04. Top patterns for making agents "alive" and self-driving.

---

## HIGH IMPACT — Implement First

### 1. HEARTBEAT.md with Real File Scanning
Every heartbeat, agents should SCAN workspace files — not just check memory. If `HEARTBEAT_OK`, the response is silently dropped (no alert fatigue).

### 2. BabyAGI Task Generation Loop
Agents don't just execute tasks — they GENERATE new tasks based on results. Three-agent inner loop: Execute → Create Tasks → Prioritize.

**Implementation:** `TASK_QUEUE.md` — agents claim tasks, execute, then ask: "What new tasks does this result reveal?"

### 3. Ralph Loop for Coding (Ship While You Sleep)
```
while tasks remain:
  1. Pick next task from TASK_QUEUE.md
  2. Implement it
  3. Run validation (tests, build, lint)
  4. If pass → commit, mark done, next
  5. If fail → inject error, retry (max 3)
  6. Reset context (fresh spawn each iteration)
```
Cost: ~$10/hour with Sonnet. A single overnight session can knock out a full day's dev work.

### 4. Four-Channel Persistence
| Channel | File | Purpose |
|---------|------|---------|
| Knowledge Base | `knowledge/KNOWLEDGE_BASE.md` | Patterns, conventions |
| Git History | Git commits | Traceable changes |
| Progress Log | `memory/YYYY-MM-DD.md` | Chronological record |
| Task State | `TASK_QUEUE.md` | Done/pending/failed |

### 5. Cron + Heartbeat Layering
- **Cron = clockwork** (always fires): Daily intel, email checks, weekly reports
- **Heartbeat = awareness** (agent decides): Monitoring, anomaly detection, idle task pickup

### 6. Shared Task Board with Claim Protocol
```markdown
## UNCLAIMED
- [ ] [HIGH] Draft response to investor email | source: InboxForge

## IN PROGRESS
- [x] [HIGH] Prepare meeting notes | claimed: CalendarCaptain | started: 08:30

## DONE (today)
- [x] Morning email triage | InboxForge | 07:15
```
CommandCenter checks for tasks stuck IN PROGRESS >2 hours → re-assigns.

---

## MEDIUM IMPACT — Week 1-2

### 7. Self-Prompting / Reverse Prompting
Add to each agent's heartbeat:
> "Before checking your task list, think: What's the most valuable thing I could do right now that nobody asked me to do?"

### 8. Event-Driven Hooks
- New file in inbox/ → trigger InboxForge immediately
- Git push → trigger Reviewer
- Agent fails → auto-create retry task + notify CommandCenter

### 9. Model Routing (Local for Boring, Cloud for Thinking)
- Heartbeat checks, file scanning → ollama/qwen2.5:7b ($0)
- Research, writing, analysis → claude-sonnet-4
- Complex reasoning → claude-opus-4-6 (sparingly)
At $0/heartbeat, 7 agents can fire 336 heartbeats/day at zero cost.

### 10. Continuous-Claude PR Loop
Create branch → Claude Code works → commit → open PR → wait for CI → auto-merge → repeat.

### 11. Cross-Agent Knowledge Pollination
KnowledgeKeeper scans each agent's memory/, identifies insights relevant to OTHER agents, cross-posts with tags.

### 12. Active Hours + Quiet Mode
- Full (06:00-23:00): All agents active
- Night watch (23:00-06:00): Only InboxForge (urgent email detection), local model only
- Weekend: Reduce heartbeat to every 2 hours

---

## LOW IMPACT — Nice-to-Have

### 13. Self-Healing HEARTBEAT.md
Agent rewrites its own heartbeat instructions over time. Remove dead checks, add useful ones.

### 14. Reflection-to-Improvement Pipeline
After each task: What worked? What was hard? What would I do differently? KnowledgeKeeper reviews weekly.

### 15. GitHub Agentic Workflows
Auto-triage issues, auto-fix lint errors, auto-label PRs.

---

## Implementation Priority

| Week | Pattern | Effort |
|------|---------|--------|
| Now | Heartbeat + file scanning (#1) | 1h |
| Now | TASK_QUEUE.md + claim protocol (#6) | 1h |
| Now | Cron + Heartbeat layering (#5) | 2h |
| 1 | Self-prompting in heartbeat (#7) | 30m |
| 1 | Model routing local/cloud (#9) | Done |
| 2 | BabyAGI task generation (#2) | 3h |
| 2 | Cross-agent pollination (#11) | 2h |
| 3 | Ralph Loop for coding (#3) | 3h |
| 3 | Continuous-claude PR loop (#10) | 2h |
| 4 | Self-healing HEARTBEAT.md (#13) | 30m |

*Sources: OpenClaw docs, BabyAGI, CrewAI, Ralph Loop, continuous-claude, Addy Osmani*
