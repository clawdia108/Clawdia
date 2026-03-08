# OpenClaw Ops Skill

**Owner:** spojka
**Version:** 1.0.0
**Type:** instruction_only

## Purpose
System operations, health monitoring, and agent lifecycle management for the Clawdia/OpenClaw platform. Provides diagnostic commands, recovery procedures, and operational intelligence.

## Health Check Protocol

### Quick Health (`/health`)
```bash
python3 scripts/orchestrator.py  # Runs full 30min cycle
```
Returns:
- Agent status (12 agents, last heartbeat times)
- Bus queue depth (pending messages per agent)
- Cowork bridge status (last sync, pending completions)
- Model router status (active model, fallback state)
- Cost tracker (today's spend, budget remaining)
- Launchd service status (5 KeepAlive daemons)

### Deep Diagnostic (`/diagnose`)
1. Read `control-plane/agent-states.json` — check for stale agents (>2h no heartbeat)
2. Read `knowledge/EXECUTION_STATE.json` — check system_health section
3. Read `logs/orchestrator.log` — last 50 lines for errors
4. Read `logs/events.jsonl` — last 20 events for anomalies
5. Check `bus/dead-letter/` — any failed messages
6. Check `approval-queue/pending/` — any stuck approvals
7. Run `openclaw models status` — verify auth is valid
8. Check launchd: `launchctl list | grep clawdia`

### Recovery Procedures

| Problem | Detection | Fix |
|---------|-----------|-----|
| Stale agent | age_hours > max_hours in EXECUTION_STATE | Run recovery script: `python3 scripts/recover_{agent}.py` |
| Bus deadlock | Messages in dead-letter > 5 | Move to reprocess: `mv bus/dead-letter/* bus/outbox/` |
| Orchestrator crash | launchd shows exit code != 0 | Check logs, restart: `launchctl kickstart -k gui/501/com.clawdia.orchestrator` |
| Cowork bridge stale | _bridge_state.json > 2h old | Restart: `launchctl kickstart -k gui/501/com.clawdia.cowork-bridge` |
| OpenClaw auth expired | `openclaw models status` shows expired | Re-auth: `openclaw models auth login --provider openai-codex` |
| Cost budget exceeded | cost-tracker.json daily > limit | Alert Josef, pause premium tier tasks |

## Agent Registry (Canonical 12)

| Agent | Czech Name | Role | Recovery Script |
|-------|-----------|------|-----------------|
| obchodak | Obchodak | CRM brain, pipeline ops | recover_obchodak.py |
| archivar | Archivar | Knowledge sync, learning | knowledge_sync.py |
| textar | Textar | Sales copy, content | - |
| strateg | Strateg | Market intel, research | recover_intel.py |
| postak | Postak | Email ops, inbox triage | recover_inbox.py |
| kalendar | Kalendar | Calendar, scheduling | recover_calendar.py |
| vyvojar | Vyvojar | System builder, dev | - |
| hlidac | Hlidac | Performance coaching | - |
| kontrolor | Kontrolor | Quality review | recover_kontrolor.py |
| udrzbar | Udrzbar | CRM maintenance | - |
| planovac | Planovac | Planning, time blocks | - |
| spojka | Spojka | Orchestrator, bridge | orchestrator.py |

## Operational Commands

### Bus Management
- View queue: `ls bus/inbox/*/`
- Process stuck: `python3 scripts/agent_bus.py process`
- Clear dead letters: `python3 scripts/agent_bus.py flush-dead-letter`

### Model Management
- Status: `openclaw models status`
- Switch model: `openclaw models set <model-id>`
- Auth refresh: `openclaw models auth login --provider openai-codex`
- Usage check: look for "usage:" line in status output

### Scheduled Tasks
- List: `ls ~/.claude/scheduled-tasks/`
- Check bridge: `cat bus/cowork-status/_bridge_state.json`
- Force run: trigger via Claude Desktop Cowork UI

### Cost Tracking
- Today: `cat logs/cost-tracker.json | python3 -c "import json,sys; d=json.load(sys.stdin); print(f'Today: ${d.get(\"today\",0):.2f}')"`
- Budget tiers defined in: `control-plane/model-router.json` → `budget_tiers`

## MCP Integration Status

| Connector | Status | Agent | Flag |
|-----------|--------|-------|------|
| Gmail Read | ACTIVE | postak | `gcal_read_via_mcp` |
| Gmail Draft | INACTIVE | postak | `gmail_draft_via_mcp` |
| GCal Read | ACTIVE | kalendar | `gcal_read_via_mcp` |
| GCal Write | ACTIVE | kalendar | `gcal_write_via_mcp` |
| Slack | INACTIVE | textar | `slack_read_via_mcp` |
| Clay | INACTIVE | obchodak | `clay_enrichment_via_mcp` |
| Vercel | INACTIVE | vyvojar | `vercel_deploy_via_mcp` |

Flags in: `control-plane/mcp-migration-flags.json`

## Monitoring Dashboard
- Terminal: `bash scripts/system-status.sh`
- Web: `http://localhost:9090/` (health server)
- iPad remote: `http://100.101.169.255:9090/` (via Meshnet)

## Integration
- Reads: all control-plane/*.json, knowledge/EXECUTION_STATE.json
- Writes: logs/orchestrator.log, status/
- Publishes: `system.*` events to bus
- Subscribes: `system.error`, `system.recovery_needed`
