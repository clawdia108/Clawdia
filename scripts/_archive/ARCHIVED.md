# Archived Scripts

Moved here 2026-03-08 during dead script cleanup.

These scripts are NOT referenced by any active launchd service, orchestrator, agent_runner, agent_dispatcher, or overnight_run.sh. They are not imported by any actively-running script.

## Why each was archived

| Script | Reason |
|--------|--------|
| `config.py` | Replaced by `lib/secrets.py` and `lib/paths.py`. Only self-references. |
| `check_control_plane.py` | Only referenced in playbook docs and smoke test list. Never called at runtime. |
| `render_user_report.py` | Only referenced in playbook/README docs. Never called at runtime. |
| `resolve_task_route.py` | Only referenced in README/playbook docs. Never called at runtime. |
| `echo_pulse_pricing.py` | Only mentioned in a comment in `proposal_generator.py` (not imported). |
| `mission_control.py` | Only listed in smoke test file. Never called by any agent or orchestrator. |
| `task_escalation.py` | Only listed in smoke test and learnings doc. Not called at runtime. |
| `nightly_git_sync.sh` | Not referenced by any script, plist, or doc. |
| `setup_agent_army_crons.sh` | One-time setup script. Only in a playbook doc. |
| `dashboard_aggregator.py` | Only accessible via `clawdia.sh` CLI. Replaced by `health_server.py`. |
| `ab_testing.py` | Only accessible via `clawdia.sh` CLI. No A/B tests configured or running. |
| `test_data_generator.py` | Only accessible via `clawdia.sh` CLI. One-time dev utility. |
| `deal_timeline.py` | Only accessible via `clawdia.sh` CLI. Never integrated into agent system. |
| `nlp_task.py` | Only accessible via `clawdia.sh` CLI. Imports from task_queue but nothing imports it. |
| `cowork_bridge.py` | Not referenced by any script, plist, or config. Completely orphaned. |
| `agent_work_definitions.py` | Not referenced by any script, plist, or config. Reference-only utility. |

## What was kept and why

Scripts that remain in `scripts/` are actively used by at least one of:
- A launchd plist (14 registered services)
- `orchestrator.py` (imports agent_bus, agent_lifecycle, workflow_engine, task_queue, agent_collaboration, agent_warmup, time_tracker, telegram_notify, knowledge_sync)
- `agent_runner.py` (calls pipedrive_lead_scorer, draft_generator, email_sequences, competitive_intel, meeting_prep, knowledge_dedup, knowledge_graph, anomaly_detector, humanizer_trainer)
- `agent_dispatcher.py` (dispatches work to all 12 agents)
- `overnight_run.sh` (launchd-registered, calls 20+ scripts)
- Cross-imports between active scripts (e.g., structured_log imported by market_trends, competitive_intel, anomaly_detector)

## Recovery

To restore any script: `mv scripts/_archive/script_name.py scripts/`
