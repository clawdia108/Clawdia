"""Hlidac (Guard Agent) — pipeline guard, activity guard."""

from .base import BaseAgent, Task, Result


class HlidacAgent(BaseAgent):
    name = "hlidac"
    czech_name = "hlidac"
    description = "Pipeline guard — deal activity monitoring, pipeline automation"
    capabilities = ["pipeline_guard", "activity_guard"]

    SCRIPTS = {
        "pipeline_guard": "scripts/pipeline_automation.py check",
        "activity_guard": "scripts/pipedrive_open_deal_activity_guard.py",
    }

    def execute(self, task: Task) -> Result:
        script = self.SCRIPTS.get(task.type, self.SCRIPTS["activity_guard"])
        return self.run_script(script)
