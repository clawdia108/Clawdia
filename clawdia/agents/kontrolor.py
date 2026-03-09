"""Kontrolor (QA Agent) — anomaly detection, health reports, schema validation."""

from .base import BaseAgent, Task, Result


class KontrolorAgent(BaseAgent):
    name = "kontrolor"
    czech_name = "kontrolor"
    description = "Quality assurance — anomaly detection, deal health, schema validation"
    capabilities = ["anomaly_scan", "health_report", "schema_check"]

    SCRIPTS = {
        "anomaly_scan": "scripts/anomaly_detector.py scan",
        "health_report": "scripts/deal_health_scorer.py",
        "schema_check": "scripts/schema_validator.py validate",
    }

    def execute(self, task: Task) -> Result:
        script = self.SCRIPTS.get(task.type, self.SCRIPTS["health_report"])
        return self.run_script(script)
