# Agentic Modernization 2026

Research-backed upgrade plan for OpenClaw as of 2026-03-03.

## What changed in this repo

- Added explicit coordination patterns in `control-plane/coordination-patterns.json`
- Added output-layer contracts in `control-plane/output-contracts.json`
- Added session, checkpoint, and approval runtime policies in `control-plane/runtime-policies.json`
- Added an A2A-ready agent card in `control-plane/a2a-agent-card.json`
- Upgraded model routing to a multi-model, pattern-aware router in `control-plane/model-router.json`
- Added `scripts/resolve_task_route.py` to freeze route decisions into each task
- Added `scripts/render_user_report.py` and `knowledge/EXECUTION_STATE.json` so the user sees simple reports while internals stay detailed

## Design principles

1. Structured state beats prose-only coordination.
2. Internal work can be deep and technical; user-facing output must stay simple.
3. Approval boundaries must pause and resume cleanly.
4. Handoffs should carry scoped context, not whole chat history.
5. Multi-agent cooperation should be explicit, inspectable, and cost-aware.

## Source-backed architecture choices

- OpenAI Agents SDK: handoffs, guardrails, tracing, and sessions justify explicit route snapshots, approval resumes, and trace/session fields.
- Anthropic long-running agent guidance: keep plans and progress in files, use bounded subagents, preserve state, and compact context.
- LangGraph multi-agent guidance: use supervisor/orchestrator-worker and evaluator-optimizer patterns instead of one giant prompt.
- AutoGen team patterns: heterogeneous agents and reviewer loops improve reliability on complex work.
- A2A: use agent cards plus stateful task artifacts for future remote delegation.
- MCP: keep tool surfaces and context boundaries explicit at the host/orchestrator layer.

## Immediate operating model

- Specialists work from `tasks/open/*.json`
- `scripts/resolve_task_route.py --write` freezes routing metadata
- `scripts/knowledge_sync.py` emits machine-readable execution state
- `scripts/render_user_report.py` turns that state into a short digest for the user
- Bridge delivers only the digest, not the internal agent chatter
