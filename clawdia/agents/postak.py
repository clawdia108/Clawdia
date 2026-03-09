"""Postak (Outreach Agent) — cold calls, morning prep, email sequences."""

from .base import BaseAgent, Task, Result


class PostakAgent(BaseAgent):
    name = "postak"
    czech_name = "postak"
    description = "Outreach coordination — cold call lists, morning prep, email sequences"
    capabilities = ["cold_calls", "morning_prep", "email_sequences"]

    SCRIPTS = {
        "cold_calls": "scripts/cold_call_list.py --export",
        "morning_prep": "scripts/morning_sales_prep.py",
        "email_sequences": "scripts/email_sequences.py advance",
    }

    def execute(self, task: Task) -> Result:
        script = self.SCRIPTS.get(task.type, self.SCRIPTS["morning_prep"])
        if task.type == "morning_prep" and task.params.get("send"):
            script = "scripts/morning_sales_prep.py --send"
        return self.run_script(script)
