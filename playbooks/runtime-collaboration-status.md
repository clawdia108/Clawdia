# Runtime Collaboration Status

Updated: 2026-03-08 13:06 CET

## Single Boss

- Control-plane owner: `OpenClaw / Spojka`
- Rule: only `OpenClaw` decides routing, ownership, approvals, and final state publication
- `Claude Code` and `Codex` are delegated specialists, not competing orchestrators

## Runtime Roles

- `OpenClaw`: mission control, task routing, approvals, shared state, operator-facing outputs
- `Claude Code`: deep reasoning, architecture critique, naming cleanup, model/MCP governance
- `Codex`: implementation, bridge wiring, automation, health checks, repo-level technical fixes

## What Codex Built

- Claude mailbox bridge: `bus/inbox/claude/ -> bus/claude-results/ -> bus/outbox/ -> collaboration/handoffs/claude/`
- External inbox protection in `agent_runner.py` so the runner does not steal Claude mailbox requests
- Delegation policy declaring `OpenClaw / Spojka` as the only control-plane owner
- Control-plane drift checker for registry/state/routing consistency
- Runtime-first health helper using `control-plane/agent-states.json` with output-file fallback

## What Claude Confirmed

- `Claude` owns naming canonicalization, model-router authority cleanup, and MCP flag cleanup/activation
- `Codex` owns shared state consistency, stale test repair, and health/reporting fixes
- `OpenClaw` owns the runtime boundary between Python orchestration and scheduled tasks

## Current Flow

1. Codex or OpenClaw writes a request JSON to `bus/inbox/claude/`
2. `scripts/claude_bridge.py` runs `claude -p` locally, optionally with `--resume <session>`
3. Raw Claude result is saved to `bus/claude-results/`
4. Bridge emits a reply event into `bus/outbox/`
5. `agent_bus.py route` forwards the reply
6. `agent_runner.py` imports the reply into `collaboration/handoffs/claude/`

## Verified Today

- Claude roundtrip works end-to-end after runner restart
- New handoffs are created automatically for `vyvojar`
- `scripts/system-status.sh` now reports agent health from runtime timestamps, not just file age
- `scripts/health_server.py --check` returns healthy status using the same shared health logic

## Remaining Drift

- `workspace/openclaw.model-routing.json` still uses legacy runtime IDs like `dealops`, `growthlab`, `timebox`
- `control-plane/agent-states.json` still mixes top-level records and nested `agents{}`
- Some older dead-letter bus items still exist and should be triaged separately
