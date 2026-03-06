# Errors Log

Command failures, exceptions, and unexpected behaviors.

---

## 2026-03-04

### TASK-1002 Deadlock (DealOps CRM Audit)
- **Error**: Task stuck in `in_progress` for 24h+
- **Root cause**: Blocker `live_crm_exports_must_stay_local_only` — DealOps cannot read live CRM data because guardrail prevents it, but no local export mechanism exists
- **Impact**: Blocks TASK-1003 (InboxForge follow-ups) and TASK-1001 (Timebox daily plan) — entire P0 chain stalled
- **Fix**: Need to either (a) create a Pipedrive export skill that writes sanitized data locally, or (b) provide a manual local snapshot for DealOps to process
- **Prevention**: Add timeout escalation for tasks in_progress > 4h

### TASK-1003 Double Block (InboxForge Follow-ups)
- **Error**: Blocked on both `explicit_send_approval_missing` AND `deal_context_not_finalized`
- **Root cause**: First blocker (approval) is by design. Second blocker (deal context) depends on TASK-1002 output which doesn't exist yet
- **Impact**: No follow-up queue generated, no email drafts prepared
- **Fix**: Resolve TASK-1002 first, then provide explicit approval for TASK-1003

### Stale Output Cascade
- **Error**: 12 output files contain only placeholder text (9-15 bytes each)
- **Root cause**: Initial system setup created placeholder files but agents haven't run real work through them
- **Impact**: Dashboard shows 12 stale outputs, KPIs show zero progress
- **Fix**: Run agents through their cron cycles to populate outputs with real data
