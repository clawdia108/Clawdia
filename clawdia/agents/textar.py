"""Textar (Copywriter Agent) — email drafts, SPIN prep, follow-ups."""

from .base import BaseAgent, Task, Result


class TextarAgent(BaseAgent):
    name = "textar"
    czech_name = "textar"
    description = "Czech B2B copywriting — email drafts, SPIN prep, follow-up sequences"
    capabilities = ["email_draft", "spin_prep", "followup"]

    SCRIPTS = {
        "email_draft": "scripts/draft_generator.py 3",
        "spin_prep": "scripts/spin_prep_generator.py",
        "followup": "scripts/followup_engine.py --scan",
    }

    def execute(self, task: Task) -> Result:
        script = self.SCRIPTS.get(task.type, self.SCRIPTS["email_draft"])
        count = task.params.get("count")
        if task.type == "email_draft" and count:
            script = f"scripts/draft_generator.py {count}"
        return self.run_script(script)
