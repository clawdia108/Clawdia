"""Kouc (Coach Agent) — post-call sales coaching and improvement tracking."""

from .base import BaseAgent, Task, Result


class KoucAgent(BaseAgent):
    name = "kouc"
    czech_name = "kouc"
    description = "Sales coaching — post-call analysis, talk ratio, SPIN usage, trends"
    capabilities = ["coach_call", "weekly_summary", "trends"]

    SCRIPTS = {
        "coach_call": "scripts/sales_coach.py",
        "weekly_summary": "scripts/sales_coach.py --weekly",
        "trends": "scripts/sales_coach.py --trends",
    }

    def execute(self, task: Task) -> Result:
        script = self.SCRIPTS.get(task.type, self.SCRIPTS["coach_call"])
        deal_id = task.params.get("deal_id")
        if task.type == "coach_call" and deal_id:
            script = f"scripts/sales_coach.py --deal {deal_id}"
        elif task.type == "coach_call" and task.params.get("all"):
            script = "scripts/sales_coach.py --all"
        return self.run_script(script)
