# Approval Queue

Agenti sem odkládají akce, které potřebují Josefovo schválení.
Bridge je 2x denně (ráno + odpoledne) balí do digestu pro Josefa.
Josef schválí/zamítne. Schválené akce se automaticky provedou.

## Jak to funguje

1. Agent chce něco udělat (poslat email, aktualizovat CRM, publikovat obsah)
2. Místo blokování vytvoří soubor v `approval-queue/pending/`
3. Bridge při ranním/odpoledním digestu přečte pending akce
4. Josefovi pošle souhrn: "Tady je 8 věcí co chtějí agenti udělat. OK?"
5. Josef schválí/zamítne (ideálně hromadně)
6. Schválené se přesunou do `approved/` a provedou na dalším cron cyklu
7. Zamítnuté do `rejected/` s důvodem (agenti se z toho učí)

## Formát souboru

```json
{
  "id": "2026-03-06-001",
  "agent": "InboxForge",
  "action": "send_email",
  "priority": "high",
  "target": "CEO @ Mycroft",
  "summary": "Follow-up email — čekají 5 dní, CEO odjíždí v pátek",
  "detail": "Krátký email s odkazem na demo, 2 věty",
  "draft_path": "drafts/mycroft-followup-2026-03-06.md",
  "created_at": "2026-03-06T07:15:00",
  "expires_at": "2026-03-06T18:00:00",
  "status": "pending"
}
```

## Pravidla

- Max 15 pending akcí najednou (víc = agenti se musí prioritizovat)
- Akce starší 24h se automaticky přesouvají do `expired/`
- Zamítnuté akce se logují do `knowledge/AGENT_INSIGHTS.md` jako learning
- High priority akce se zvýrazní v Telegram digestu
