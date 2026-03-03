# AGENTS.md — InboxForge specifická pravidla

## Emailový workflow

1. Přečti nové emaily (přes Gmail skill nebo API)
2. Roztřiď na URGENT / ACTION / INFO / SPAM
3. Pro ACTION emaily napiš draft odpověď do inbox/DRAFTS.md
4. Aktualizuj inbox/INBOX_DIGEST.md
5. Zkontroluj inbox/FOLLOW_UPS.md — je něco overdue?

## Formát digest

```
# Inbox Digest — YYYY-MM-DD

## 🔴 URGENT (vyžaduje okamžitou akci)
- [odesílatel] předmět — krátký popis — DRAFT READY / NEEDS INPUT

## 🟡 ACTION (vyžaduje odpověď do 24h)
- ...

## 🟢 INFO (pro informaci)
- ...

## Statistiky
- Přijato: X emailů
- Drafty připraveny: X
- Follow-upy overdue: X
```

## Tón draftů

Josef komunikuje: stručně, profesionálně, přátelsky.
Žádné zbytečné fráze. Žádné "Doufám, že se máte dobře."
Rovnou k věci. Podpis: Josef
