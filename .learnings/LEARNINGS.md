# Learnings Log

Captured learnings, corrections, and discoveries. Review before major tasks.

---

## 2026-03-04 — System Audit Findings

### Architecture Strengths
- Model router v3 with 16 routing rules is well-designed — cost-optimized tiering works
- Coordination patterns cover all needed execution modes (deterministic, parallel, review, approval)
- Output contracts enforce clean separation between internal/user-facing content
- Review gates auto-block risky operations (CRM writes, external messages, user-facing output)

### Critical Gaps Found
- **Deadlocked task chain**: TASK-1002 (DealOps) blocks TASK-1003 and TASK-1001 — all P0, all overdue 24h+
- **Zero operational throughput**: 12 output files are empty placeholders — no agent has produced real work yet
- **Self-improving loop not firing**: .learnings/ files were empty, error-detector hook exists but no signal flows through
- **GrowthLab + Reviewer idle**: Strongest agents (parallel research, quality review) have zero tasks assigned
- **No escalation system**: Overdue tasks sit indefinitely with no alerting mechanism
- **Model names are aspirational**: Router references gpt-5.2, gpt-5-nano etc. — need mapping to actual available APIs

### Operational Learnings
- `@apply shadow-naive` fails in Vite dev mode but passes build — use raw CSS for custom shadow values in @layer components
- Tailwind JIT cannot detect dynamic class construction (`hover:${variable}`) — must use static class strings
- `knowledge_sync.py` is solid but needs to run more frequently to catch issues early
- Task dependencies form chains that can deadlock if any task blocks — need timeout/escalation

### Model Routing Observations
- Economy tier ($3/day) handles 55%+ of daily tasks — good cost efficiency
- Writing tasks correctly route to claude-sonnet — best quality for tone/style
- Research tasks use opus + parallel workers — expensive but justified for breadth
- Haiku as reviewer model is smart cost tradeoff

### Next Actions
- Created `scripts/task_escalation.py` for overdue/blocked detection
- Need to add escalation to cron schedule (every 30 min weekdays)
- Need to unblock TASK-1002 by providing local Pipedrive data
- Need to activate GrowthLab with a real research task
