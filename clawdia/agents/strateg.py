"""Strateg (Intelligence Agent) — market intel, competitive analysis, signal scanning."""

from .base import BaseAgent, Task, Result


class StrategAgent(BaseAgent):
    name = "strateg"
    czech_name = "strateg"
    description = "Market intelligence — signal scanning, competitive intel, trend analysis"
    capabilities = ["market_intel", "competitive", "signals"]

    SCRIPTS = {
        "market_intel": "scripts/market_trends.py report",
        "competitive": "scripts/competitive_intel.py scan",
        "signals": "scripts/signal_scanner.py",
    }

    def execute(self, task: Task) -> Result:
        script = self.SCRIPTS.get(task.type, self.SCRIPTS["signals"])
        deal_id = task.params.get("deal_id")
        if task.type == "signals" and deal_id:
            script = f"scripts/signal_scanner.py --deal {deal_id}"
        return self.run_script(script)
