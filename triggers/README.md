# Inter-Agent Triggers

Místo čekání na cron cyklus — agent zapíše trigger a cílový agent ho zpracuje do 5 minut.

## Jak to funguje

1. PipelinePilot zjistí, že deal je at risk
2. Zapíše trigger: `triggers/copy-needed-mycroft.json`
3. CopyAgent to do 5 minut zpracuje a vygeneruje draft
4. Draft jde do approval-queue

## Formát

```json
{
  "from": "PipelinePilot",
  "to": "CopyAgent",
  "type": "copy_needed",
  "context": {
    "deal": "Mycroft",
    "reason": "5 dní bez odpovědi, CEO odjíždí v pátek",
    "suggested_action": "re-engagement email"
  },
  "created_at": "2026-03-06T07:15:00",
  "processed": false
}
```

## Trigger typy

| Typ | Od | K | Kdy |
|-----|----|---|-----|
| `copy_needed` | PipelinePilot | CopyAgent | Deal potřebuje komunikaci |
| `research_needed` | DealOps | GrowthLab | Prospect potřebuje research |
| `approval_ready` | jakýkoliv | Bridge | Akce čeká na schválení |
| `insight_found` | GrowthLab | KnowledgeKeeper | Nový insight k zalogování |
| `health_alert` | jakýkoliv | Reviewer | Něco je broken |
| `content_opportunity` | GrowthLab | CopyAgent | Příležitost pro obsah |
