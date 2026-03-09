"""Udrzbar (Maintenance Agent) — backups, status page."""

from .base import BaseAgent, Task, Result


class UdrzbarAgent(BaseAgent):
    name = "udrzbar"
    czech_name = "udrzbar"
    description = "System maintenance — backups, status page, cleanup"
    capabilities = ["backup", "status_page"]

    SCRIPTS = {
        "backup": "scripts/backup_system.py snapshot",
        "status_page": "scripts/status_page.py",
    }

    def execute(self, task: Task) -> Result:
        script = self.SCRIPTS.get(task.type, self.SCRIPTS["backup"])
        return self.run_script(script)
