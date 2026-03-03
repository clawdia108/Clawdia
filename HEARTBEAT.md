# HEARTBEAT.md — Self-Healing Checklist

## Na každém heartbeatu zkontroluj:

### 1. Zdraví cron jobů
Zkontroluj zda všechny denní cron joby běžely v posledních 26 hodinách.
Pokud je některý stale, spusť ho ručně:
`openclaw cron run <jobId> --force`

### 2. Soubory workspace
- Existuje `intel/DAILY-INTEL.md` s dnešním datem? Pokud ne → GrowthLab neběžel.
- Existuje `calendar/TODAY.md` s dnešním datem? Pokud ne → CalendarCaptain neběžel.
- Existuje `pipedrive/PIPELINE_STATUS.md` aktualizovaný dnes? Pokud ne → PipelinePilot neběžel.

### 3. Zdraví systému
- Je gateway responsive? Zkontroluj: `openclaw status`
- Je disk pod 80%? Zkontroluj: `df -h /`

### 4. Knowledge base údržba
Jednou denně (kolem 22:00):
- Projdi denní zápisky všech agentů
- Extrahuj nejdůležitější poznatky do `knowledge/KNOWLEDGE_BASE.md`
- Archivuj zápisky starší než 7 dní (přesuň do memory/archive/)

### 5. Pokud nic z výše nepotřebuje pozornost
Odpověz HEARTBEAT_OK
