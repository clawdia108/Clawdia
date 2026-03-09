"""Obchodak (Sales Agent) — deal scoring, health checks, writeback."""

from .base import BaseAgent, Task, Result


class ObchodakAgent(BaseAgent):
    name = "obchodak"
    czech_name = "obchodak"
    description = "Sales pipeline management — scoring, health, stale cleanup, writeback"
    capabilities = ["deal_scoring", "deal_health", "stale_cleanup", "writeback"]

    SCRIPTS = {
        "deal_scoring": "scripts/pipedrive_lead_scorer.py",
        "deal_health": "scripts/deal_health_scorer.py --snapshot",
        "stale_cleanup": "scripts/stale_deal_cleanup.py --report",
        "writeback": "scripts/pipedrive_writeback.py",
    }

    def execute(self, task: Task) -> Result:
        script = self.SCRIPTS.get(task.type, self.SCRIPTS["deal_scoring"])
        return self.run_script(script)
