"""Archivar (Archive Agent) — Notion sync, knowledge graph, deduplication."""

from .base import BaseAgent, Task, Result


class ArchivarAgent(BaseAgent):
    name = "archivar"
    czech_name = "archivar"
    description = "Knowledge management — Notion sync, knowledge graph, deduplication"
    capabilities = ["notion_sync", "knowledge_graph", "dedup"]

    SCRIPTS = {
        "notion_sync": "scripts/notion_sync.py",
        "knowledge_graph": "scripts/knowledge_graph.py build",
        "dedup": "scripts/knowledge_dedup.py scan",
    }

    def execute(self, task: Task) -> Result:
        script = self.SCRIPTS.get(task.type, self.SCRIPTS["notion_sync"])
        return self.run_script(script)
