# Agent Heartbeat System

Každý agent po každém běhu zapíše heartbeat. Reviewer kontroluje heartbeaty a eskaluje problémy.

## Formát

Soubor: `memory/heartbeats/{agent-name}.json`

```json
{
  "agent": "GrowthLab",
  "last_run": "2026-03-06T07:15:00",
  "status": "success",
  "output_produced": true,
  "output_path": "knowledge/DAILY-INTEL.md",
  "output_bytes": 2847,
  "consecutive_failures": 0,
  "last_error": null,
  "next_scheduled": "2026-03-06T18:00:00",
  "metrics": {
    "runs_today": 2,
    "outputs_today": 2,
    "triggers_sent": 1,
    "approvals_queued": 0
  }
}
```

## Pravidla

- 3 po sobě jdoucí selhání → Reviewer dostane `health_alert` trigger
- 24h bez heartbeatu → Bridge to zmíní v Josefově digestu
- Agent s `output_produced: false` 3x za sebou → pravděpodobně broken, eskaluj
