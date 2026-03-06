# {{greeting}} {{date}}

{{#main_message}}
{{main_message}}
{{/main_message}}

{{#schedule}}
{{schedule}}
{{/schedule}}

{{#numbers}}
{{numbers}}
{{/numbers}}

{{#headsup}}
{{headsup}}
{{/headsup}}

{{#need_from_you}}
**Potřebuju od tebe:**
{{#actions}}
- {{action}}
{{/actions}}
{{/need_from_you}}

{{^need_from_you}}
Nic nepotřebuju, vše jede.
{{/need_from_you}}

<!--
PRAVIDLA — PŘEČTI PŘED GENEROVÁNÍM:

Povinně přečti: knowledge/TELEGRAM_STYLE_GUIDE.md

STRUKTURA:
- greeting: "Dobré ráno ☀️" / "Večerní shrnutí 🌙" / "Dobré odpoledne"
- date: "úterý 4. 3." (den česky + datum, bez roku)
- main_message: 1-3 věty co je dneska hlavní. Normální česká věta, ne seznam.
- schedule: konkrétní schůzky/cally s časem. Jen důležité. Volitelné.
- numbers: pipeline/čísla JEN pokud se něco změnilo nebo je zajímavé. Volitelné.
- headsup: co hoří nebo blokuje. Volitelné — pokud nic nehoří, vynech.
- actions: konkrétní věci kde čekám na Josefovo rozhodnutí. Max 3.

STYL:
- Max 15 řádků celkem
- Žádné task ID, agent names, timestamps
- Čísla zaokrouhlená (1,1M ne 1 114 536)
- Firmy jménem, ne kódem
- Vždycky říct PROČ, ne jen CO
- Konkrétní doporučení, ne jen hlášení stavu
- Tón: chytrý kolega, ne dashboard

KONTROLA PŘED ODESLÁNÍM:
- Přečetl bych si to rád na mobilu? → pokud ne, přepiš
- Je tam žargon? → odstraň
- Je to zajímavé čtení? → pokud ne, přepiš
-->
