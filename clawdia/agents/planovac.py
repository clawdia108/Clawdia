"""Planovac (Planner Agent) — strategic briefs, weekly intel."""

from .base import BaseAgent, Task, Result


class PlanovacAgent(BaseAgent):
    name = "planovac"
    czech_name = "planovac"
    description = "Strategic planning — weekly intel, strategic briefs, forecasting"
    capabilities = ["strategic_brief", "weekly_intel"]

    SCRIPTS = {
        "strategic_brief": "scripts/strategic_brief.py generate",
        "weekly_intel": "scripts/weekly_intel.py",
    }

    def execute(self, task: Task) -> Result:
        script = self.SCRIPTS.get(task.type, self.SCRIPTS["weekly_intel"])
        return self.run_script(script)
