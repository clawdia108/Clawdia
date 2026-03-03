# {{period}} — {{date}}

## Co je dnes důležité
{{#priorities}}
{{index}}. **{{headline}}**{{#detail}} — {{detail}}{{/detail}}
{{/priorities}}

{{^priorities}}
Žádné urgentní položky.
{{/priorities}}

## Co jsem udělal
{{#completed}}
- {{summary}}
{{/completed}}

{{^completed}}
- Zatím nic nového.
{{/completed}}

## Potřebuji od tebe
{{#actions}}
- [ ] {{action}}
{{/actions}}

{{^actions}}
Nic — vše běží.
{{/actions}}

---

<!--
PRAVIDLA PRO GENEROVÁNÍ:
- Max 15 řádků celkem
- Max 5 položek v každé sekci
- Žádné task IDs (TASK-1001), agent names (dealops), timestamps
- Čísla > vágní popisy ("5 dealů" ne "několik")
- Čeština, neformální ale profesionální
- Priority sekce: jen věci vyžadující akci nebo pozornost
- Completed sekce: jen co se reálně změnilo od posledního reportu
- Actions sekce: jen věci kde čekám na tvé rozhodnutí/schválení
-->
