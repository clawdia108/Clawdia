# Jak oživit agenty — brutálně upřímný plán

> Stav k 6. 3. 2026: Máme Ferrari bez benzínu. 54 cron jobů, fungují 3-4.
> 551 knih, přečtených nula. 20 skills, všechny jenom návody bez kódu.
> Revenue-machine plán: 0 zaškrtnutých položek.
>
> **Tohle se mění teď.**

---

## Fáze 1: Okamžitě (tento týden)

### 1.1 Approval Queue místo review gates

**Problém:** Review gates blokují VŠECHNO. InboxForge nemůže poslat email.
CopyAgent nemůže publikovat. Všichni jen navrhují a čekají do nekonečna.

**Řešení:** `approval-queue/` systém. Agenti navrhnou akci → Bridge
je 2x denně zabalí do digestu → Josef schválí hromadně za 5 minut →
schválené se provedou automaticky.

**Stav:** ✅ Struktura vytvořena. Čeká na napojení na Bridge cron.

### 1.2 Supadata Intelligence

**Problém:** Agenti jsou slepí a hluší. Nevidí co se děje na trhu,
u konkurence, v obsahu prospektů.

**Řešení:** Supadata API dává GrowthLabu oči — YouTube transcripce,
competitor monitoring, web scraping, prospect research.

**Stav:** ✅ Skill vytvořen (`skills/supadata-intel/`). Čeká na
napojení na GrowthLab cron.

### 1.3 Heartbeat systém

**Problém:** Nikdo neví jestli agenti běží. Cron failne a nikdo
se nedozví. Reviewer má kontrolovat health, ale sám neběží.

**Řešení:** Každý agent píše heartbeat po každém běhu. 3 faily za
sebou → eskalace. 24h ticho → alert v Josefově digestu.

**Stav:** ✅ Struktura vytvořena (`memory/heartbeats/`).

### 1.4 Lidské zprávy místo robot-speaku

**Problém:** Briefingy jsou nečitelné. Žargon, korporátní struktura,
nulová zajímavost.

**Řešení:** `knowledge/TELEGRAM_STYLE_GUIDE.md` — kompletní bible.
Nové šablony. Nové output contracts s forbidden words.

**Stav:** ✅ Hotovo.

---

## Fáze 2: Tento týden (do pátku)

### 2.1 Rozjet GrowthLab s Supadata

Konkrétní úkoly:
- [ ] GrowthLab cron: každé ráno prohledej YouTube "HR engagement tools Czech"
- [ ] Přepiš top 3 nová videa z posledních 7 dní
- [ ] Extrahuj: kdo mluví, o čem, jaké firmy zmiňují, co nabízí
- [ ] Zapiš do `knowledge/DAILY-INTEL.md`
- [ ] Scrape pricing stránky: Sloneek, Survio, Arnold, LutherOne, PeopleGoal
- [ ] Porovnej s minulým týdnem → `knowledge/COMPETITOR_WATCH.md`

### 2.2 Rozjet KnowledgeKeeper s 1 knihou/den

Místo 7 knih/den (nerealistické), začni s 1:
- [ ] Vyber top knihu z READING_TRACKER.md
- [ ] Extrahuj 10 klíčových insights
- [ ] Zapiš do `knowledge/book-insights/{nazev-knihy}.md`
- [ ] Navrhni 2 konkrétní použití pro sales/content

### 2.3 Napojit CopyAgent na pipeline triggers

- [ ] Když PipelinePilot najde stalled deal → trigger na CopyAgent
- [ ] CopyAgent vygeneruje draft emailu v Josefově tónu
- [ ] Draft jde do approval-queue
- [ ] Josef schválí → InboxForge pošle

### 2.4 DealOps prospect research se Supadata

- [ ] Před každou schůzkou: najdi YouTube přítomnost prospekta
- [ ] Přepiš jejich videa/rozhovory
- [ ] Doplň do SPIN prep dokumentu
- [ ] Zapiš do approval-queue jako "research ready"

---

## Fáze 3: Příští týden

### 3.1 Self-improvement loop

1. Reviewer kontroluje output všech agentů → píše do IMPROVEMENT_PROPOSALS.md
2. KnowledgeKeeper čte proposals → navrhne jak zlepšit
3. Změny se implementují → měří se dopad

### 3.2 A/B testování emailů

1. CopyAgent generuje 2 varianty pro každý follow-up
2. InboxForge střídá varianty
3. GrowthLab měří response rate
4. Vítězná varianta se stává defaultem

### 3.3 Content pipeline

1. GrowthLab najde trending téma přes Supadata
2. KnowledgeKeeper dodá relevantní insights z knih
3. CopyAgent napíše draft článku
4. Reviewer zkontroluje kvalitu
5. Josef schválí → publikuje se

---

## Metriky "živosti"

Denně chceme vidět:

| Metrika | Cíl | Teď |
|---------|-----|-----|
| Heartbeaty (agenti co běží) | 8/10 | ~2/10 |
| Nové insighty v knowledge/ | 5+ | 0 |
| Drafty v approval-queue | 3-5 | 0 |
| Triggers mezi agenty | 5+ | 0 |
| Knihy zpracované | 1/den | 0 celkem |
| Competitor updates | 1/den | 0 celkem |
| YouTube videa přepsaná | 3/den | 0 celkem |
| A/B testy běžící | 1-2 | 0 |

Týdně:

| Metrika | Cíl | Teď |
|---------|-----|-----|
| Follow-up emaily odeslané (schválené) | 15+ | manuálně |
| Blog drafty připravené | 2 | 0 |
| Nové experimenty spuštěné | 2 | 0 |
| Self-improvement proposals | 3 | 0 |
| Competitor pricing updates | 1 | 0 |

---

## Co se NEBUDE dělat

- Žádná další architektura. Dost plánů. Teď se staví.
- Žádné nové agenti. Rozjet ty co máme.
- Žádné nové skill-manifesty. Přeměnit existující na kód.
- Žádné nové cron joby dokud stávající neběží.

---

*Poslední update: 6. 3. 2026*
*Autor: Josef + Claude*
*Review: po 1 týdnu (13. 3. 2026)*
