# Agent Work Definitions — 2026-03-08

## 🔗 Spojka (Bridge)
*Koordinátor mezi agenty, hlavní komunikační uzel*

**Continuous Tasks:**
- Generuj morning briefing (knowledge/USER_DIGEST_AM.md) — reálná data
- Kontroluj bus/ na nerozeslanou poštu a přepošli správným agentům
- Zkontroluj approval-queue/ na čekající schválení
- Monitoruj konflikty mezi agenty a vyřeš je
- Konsoliduj výstupy ze všech agentů do denního přehledu

**Learning Goals:**
- Naučit se predikovat, který agent bude potřebovat pomoc
- Optimalizovat routing zpráv — méně latence, méně chyb
- Budovat kontext-awareness — co říkali agenti minulý týden

**Schedule:** Každý cyklus (30 min)

## 📊 Obchodák (Pipeline Pilot)
*Pipeline management, deal scoring, lead enrichment*

**Continuous Tasks:**
- Scoring dealů — spusť pipedrive_lead_scorer.py každých 4h
- Detekce stale dealů (>14 dní bez aktivity) → STALE_DEALS.md
- Pipeline hygiene — kontrola aktivit (activity guard)
- Analyzuj patterns vyhranych vs prohraných dealů
- Enrichuj nové leady přes Lusha API
- Aktualizuj PIPELINE_STATUS.md s reálnými čísly

**Learning Goals:**
- Zlepšit scoring model — přidej industry-specific váhy
- Naučit se predikovat win probability per deal
- Trackuj velocity — kolik dní v každém stage v průměru
- Analyzuj, které lead sources mají nejlepší konverzi

**Schedule:** Každé 4 hodiny (9, 13, 17)

## 📮 Pošťák (Inbox Forge)
*Email drafts, follow-up sequences, inbox monitoring*

**Continuous Tasks:**
- Generuj email drafty pro top stale dealy (Claude Sonnet)
- Personalizuj emaily podle deal kontextu a stage
- Kontroluj drafts/ na drafty ke kontrole
- Připrav follow-up sequences pro nové dealy
- Analyzuj inbox na odpovědi od prospectů

**Learning Goals:**
- Zlepšit email copy — A/B testování subject lines
- Naučit se timing — kdy posílat emaily (den, hodina)
- Budovat template library — co funguje per industry
- Analyzuj response rates per template typ

**Schedule:** Ráno v 8:00 + po každém pipeline update

## 🎯 Stratég (Growth Lab)
*Market research, competitive intel, growth strategy*

**Continuous Tasks:**
- Monitoruj konkurenci — competitive_intel.py scan
- Analyzuj trendy v HR tech a engagement industry
- Připrav battle cards per competitor
- Generuj weekly strategic brief
- Analyzuj win/loss patterny a doporuč strategy změny

**Learning Goals:**
- Mapovat competitive landscape — kdo co dělá
- Identifikovat emerging trends v employee engagement
- Predikovat competitor moves
- Budovat pricing intelligence — jak se mění trh

**Schedule:** Denně ráno + triggered při competitive mention

## 📅 Kalendář (Calendar Captain)
*Schedule management, meeting prep, time optimization*

**Continuous Tasks:**
- Generuj TODAY.md z reálného Google Calendar
- Kalkuluj volné focus bloky (>45 min) pro deep work
- Připrav Pomodoro schedule pro hovory
- Kontroluj konflikty v kalendáři
- Generuj meeting prep pro upcoming schůzky

**Learning Goals:**
- Optimalizovat schedule — najdi patterns v produktivitě
- Predikovat kolik času calls zabere (historická data)
- Naučit se buffer time management pro ADHD
- Trackovat focus time vs meeting time ratio

**Schedule:** Každý cyklus + triggered při calendar change

## ✅ Kontrolor (Reviewer)
*Quality assurance, output review, system health*

**Continuous Tasks:**
- Review všech agent výstupů — kontrola kvality
- Kontroluj system health — SYSTEM_HEALTH.md
- Validuj data konzistenci mezi agenty
- Kontroluj logy na errory a warningy
- Audtuj email drafty před schválením

**Learning Goals:**
- Budovat quality metrics per agent
- Naučit se rozpoznat degradaci kvality
- Identifikovat data inconsistencies automaticky
- Budovat regression test suite pro agenty

**Schedule:** Každý cyklus (30 min)

## 📚 Archivář (Knowledge Keeper)
*Knowledge management, graph building, deduplication*

**Continuous Tasks:**
- Buduj knowledge graph z deal dat a interakcí
- Deduplikuj knowledge base (knowledge_dedup.py)
- Organizuj meeting-prep/ do archivu
- Indexuj nové informace z agentů
- Exportuj knowledge graph pro ostatní agenty

**Learning Goals:**
- Budovat relationship map — kdo zná koho
- Trackovat knowledge gaps — co nám chybí
- Optimalizovat search — aby se agenti rychle dostali k info
- Analyzovat knowledge utilization — co se používá, co ne

**Schedule:** Noční run + po velkých datech

## 🔧 Údržbář (Deal Ops)
*System maintenance, CRM sync, data hygiene*

**Continuous Tasks:**
- Pipedrive write-back — aktualizuj CRM z agent outputů
- Cleanup starých logů (>7 dní)
- Kontroluj disk space a performance
- Validuj credential soubory
- Synchronizuj agent states s reality

**Learning Goals:**
- Automatizovat více CRM operací
- Budovat self-healing capabilities
- Optimalizovat resource usage (API calls, tokens)
- Predikovat system failures před tím než nastanou

**Schedule:** Noční run + on-demand

## ✍️ Textař (Copy Agent)
*Content creation, email copy, social posts*

**Continuous Tasks:**
- Generuj SPIN email drafty pro deals (Claude Sonnet)
- Piš LinkedIn posty pro Josefa
- Připrav case study drafty z vyhranych dealů
- Personalizuj obsah per industry/persona
- Generuj follow-up templaty

**Learning Goals:**
- Zlepšit český copy — natural, ne robotický
- Naučit se Josef's voice — jak on píše
- A/B testovat email subject lines
- Budovat content calendar — co kdy postovat

**Schedule:** Ráno v 8:00 + triggered při novém dealu

## 👁️ Hlídač (Auditor)
*Monitoring, anomaly detection, competitor watch*

**Continuous Tasks:**
- Monitoruj anomálie v pipeline (anomaly_detector.py)
- Sleduj competitor zmínky v deal notes
- Kontroluj engagement skóre — kdo klesá?
- Alert při neobvyklých patterech (velký deal lost, apod.)
- Monitoruj market news relevantní pro Behavera

**Learning Goals:**
- Budovat baseline pro 'normální' chování pipeline
- Zlepšit anomaly detection — méně false positives
- Predikovat deal risk na základě engagement patterns
- Trackovat industry trends automaticky

**Schedule:** Každé 4 hodiny + event-triggered

## ⏰ Plánovač (Timebox)
*Time management, scheduling, ADHD support*

**Continuous Tasks:**
- Generuj Pomodoro plány per den
- Trackuj Josefovu produktivitu — focus vs meeting time
- Plánuj follow-up reminders
- Optimalizuj scheduling — minimalizuj context switching
- Generuj weekly planning overview

**Learning Goals:**
- Naučit se Josefovy productivity patterns
- Optimalizovat pro ADHD — správné bloky ve správný čas
- Predikovat energy levels per denní dobu
- Budovat time audit — kam čas skutečně jde

**Schedule:** Ráno + event-triggered

## 💻 Vývojář (Codex)
*Code improvements, bug fixes, new integrations*

**Continuous Tasks:**
- Monitoring system logů na errory
- Identifikuj scripts co selhávají a navrhni fix
- Sleduj TODOs v kódu a prioritizuj
- Testuj integraci — Pipedrive, Telegram, Gmail
- Optimalizuj performance kritických skriptů

**Learning Goals:**
- Budovat automated test suite
- Identifikovat tech debt a prioritizovat
- Navrhnout nové integrace (Slack, HubSpot, etc.)
- Optimalizovat token usage — méně tokenů, stejná kvalita

**Schedule:** Noční run + on-demand
