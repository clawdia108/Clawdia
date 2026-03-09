"""Kalendar (Calendar Agent) — meeting prep, Fathom sync, auto next-step."""

from .base import BaseAgent, Task, Result


class KalendarAgent(BaseAgent):
    name = "kalendar"
    czech_name = "kalendar"
    description = "Calendar management — meeting prep, Fathom call sync, auto next-step"
    capabilities = ["meeting_prep", "fathom_sync", "auto_next_step"]

    SCRIPTS = {
        "meeting_prep": "scripts/meeting_prep.py --upcoming",
        "fathom_sync": "scripts/fathom_sync.py",
        "auto_next_step": "scripts/auto_next_step.py --days 3",
    }

    def execute(self, task: Task) -> Result:
        script = self.SCRIPTS.get(task.type, self.SCRIPTS["meeting_prep"])
        deal_id = task.params.get("deal_id")
        if task.type == "meeting_prep" and deal_id:
            script = f"scripts/meeting_prep.py {deal_id}"
        return self.run_script(script)
