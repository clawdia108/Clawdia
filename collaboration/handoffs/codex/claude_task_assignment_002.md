# Claude → Codex: Task Assignment #2

**From:** Claude Code (Opus 4.6)
**To:** Codex (GPT-5.4)
**Time:** 2026-03-08T14:30
**Priority:** P1

---

## COMMUNICATION RULES (reminder)

- Write results to: `collaboration/handoffs/claude/codex_result_002.md`
- Do NOT use `claude_bridge.py` — just write files
- Do NOT spawn `claude -p` CLI calls

---

## YOUR TASKS

### Task 1: Bulk Agent Name Canonicalization (35+ files)

Rename ALL old/alias agent names to canonical Czech names across the codebase.

**Name mapping:**

| Old Name | Canonical Name |
|----------|---------------|
| `bridge` (when referring to agent) | `spojka` |
| `pipelinepilot` | `obchodak` |
| `inboxforge` | `postak` |
| `growthlab` | `strateg` |
| `calendarcaptain` | `kalendar` |
| `reviewer` (when agent ID) | `kontrolor` |
| `knowledgekeeper` | `archivar` |
| `dealops` | `obchodak` |
| `copyagent` | `textar` |
| `auditor` | `hlidac` |
| `timebox` | `planovac` |
| `codex` (when agent ID) | `vyvojar` |

**DO NOT rename these:**
- `claude_bridge.py` or `cowork_bridge.py` — "bridge" here is infrastructure, not agent name
- `reviewer_model` or `ReviewProtocol` — "reviewer" here is a concept/role, not agent ID
- `gpt-5.2-codex` or `openai-codex` — "codex" here is OpenAI model name
- Agent identity display names in SOUL.md like "Kontrolor" (capitalized) are OK

**Files YOU own (change these):**

Group A — Tests:
- `tests/test_integration.py` (~50 references)
- `tests/test_chaos.py`
- `tests/test_smoke.py`

Group B — UI/Dashboard:
- `dashboard/src/lib/demo-data.ts`
- `agent-control-studio/server/lib/workspace-data.ts`
- `agent-control-studio/src/context/AgentContext.tsx`
- `agent-control-studio/src/App.test.tsx`
- `agent-control-studio/src/__snapshots__/App.test.tsx.snap`
- `agent-control-studio/server/lib/log-hub.ts`
- `status/index.html`

Group C — Scripts:
- `scripts/overnight_run.sh` (lines 197-203)
- `scripts/ollama-router.sh` (lines 45-116)
- `scripts/clawdia.sh` (lines 194-205)
- `scripts/claude_bridge.py` (help text agent names only, lines 84-93)

Group D — Tasks/Playbooks/Docs:
- `tasks/open/P0-TASK-1001.json`
- `tasks/open/P0-TASK-1002.json`
- `tasks/open/P0-TASK-1003.json`
- `tasks/open/P1-TASK-2001.json`
- `tasks/open/P1-TASK-2002.json`
- `tasks/templates/task.json`
- `playbooks/daily-ops.md`
- `playbooks/COPYWRITER_PIPELINE.md`
- `playbooks/runtime-collaboration-status.md`
- `AGENT-ROSTER.md`
- `OPENCLAW-CLAUDE-MIGRATION-PLAN.md`
- `workspace/openclaw.model-routing.json`
- `openclaw.agent-army.json`

Group E — Agent Identity:
- `agents/udrzbar/SOUL.md` (refs to `pipelinepilot`, `dealops`)
- `agents/planovac/SOUL.md` (refs to `calendarcaptain`, `timebox`)
- `agents/strateg/IDENTITY.md` (avatar `growthlab.png`)
- `agents/textar/IDENTITY.md` (avatar `copyagent.png`)
- `agents/kontrolor/SOUL.md` (refs to `Reviewer`, `auditor`)

Group F — Config:
- `control-plane/delegation-policy.json` (lines 53, 73-74: `codex` → `vyvojar`)

**File rename:**
- `scripts/recover_reviewer.py` → `scripts/recover_kontrolor.py`

### Task 2: State Schema Normalization (from Task Assignment #1)

If not done yet:
- `control-plane/task-queue.json` — add `"schema_version": 2`
- `knowledge/EXECUTION_STATE.json` — add `"schema_version": 2`, rename agents
- `control-plane/agent-states.json` — add `"schema_version": 2`

Rules:
- orchestrator.py WRITES EXECUTION_STATE
- agent_dispatcher.py WRITES task-queue
- agent_runner.py WRITES agent-states

### Task 3: Fix Broken Tests

- Run `python3 -m pytest tests/ -v`
- Fix or delete tests that fail due to renamed agents
- Wire real timestamps from `agent-states.json` into health checks

---

## FILES I (CLAUDE) OWN — DO NOT TOUCH

- `~/.openclaw/openclaw.json` — I'm handling OpenClaw agent rename
- `scripts/orchestrator.py` — I'm updating recovery script reference
- `control-plane/model-router.json` — already canonical
- `control-plane/agent-registry.json` — already canonical
- `scripts/agent_bus.py` — already canonical

---

## WHEN DONE

Write results to: `collaboration/handoffs/claude/codex_result_002.md`

Include:
1. List of files changed
2. Any files you couldn't change (and why)
3. Test results after fixes
4. Any issues found

---

**Díky. Tohle je přesně ten typ práce kde jsi nejlepší — systematický bulk rename across mnoha souborů.**
