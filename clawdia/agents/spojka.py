"""Spojka (Communication Agent) — daily digest, standup, scorecard, nudges."""

from .base import BaseAgent, Task, Result


class SpojkaAgent(BaseAgent):
    name = "spojka"
    czech_name = "spojka"
    description = "Communication hub — daily digest, standup, scorecard, motivational nudges"
    capabilities = ["daily_digest", "standup", "scorecard", "nudge"]

    SCRIPTS = {
        "daily_digest": "scripts/daily_digest.py preview",
        "standup": "scripts/standup_generator.py",
        "scorecard": "scripts/adhd-scorecard.py",
        "nudge": "scripts/motivational_nudge.py auto",
    }

    def execute(self, task: Task) -> Result:
        script = self.SCRIPTS.get(task.type, self.SCRIPTS["daily_digest"])
        if task.type == "daily_digest" and task.params.get("send"):
            script = "scripts/daily_digest.py"
        return self.run_script(script)
