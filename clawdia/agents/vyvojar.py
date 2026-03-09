"""Vyvojar (Developer Agent) — reports, system development."""

from .base import BaseAgent, Task, Result


class VyvojarAgent(BaseAgent):
    name = "vyvojar"
    czech_name = "vyvojar"
    description = "System development — report generation, tooling"
    capabilities = ["report"]

    SCRIPTS = {
        "report": "scripts/report_generator.py generate",
    }

    def execute(self, task: Task) -> Result:
        script = self.SCRIPTS.get(task.type, self.SCRIPTS["report"])
        return self.run_script(script)
