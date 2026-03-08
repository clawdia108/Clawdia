# SPIN Sales Prep Skill

**Owner:** obchodak
**Version:** 1.0.0
**Type:** instruction_only

## Purpose
Complete pre-call preparation combining SPIN selling (Rackham), Pitch Anything (Klaff), and Czech B2B cultural adaptation. Generates ready-to-use call scripts, objection playbooks, and meeting strategies.

## Pre-Call Preparation Workflow

### Step 1: Intelligence Gathering (automated)
Before any scheduled call/meeting, pull:
- **Pipedrive**: deal value, stage, notes, last activity, custom fields
- **LUSHA**: contact phone, email, social links (if not enriched yet)
- **Knowledge base**: `knowledge/engagement-scores.json`, market intel
- **Google Calendar**: meeting details, attendees, previous meetings
- **Gmail**: last 5 email exchanges with this contact
- **Web**: latest company news, funding, hiring (last 30 days)

### Step 2: Prospect Profile Card
```
## Profil: [Jméno] — [Pozice] @ [Firma]
**Firma:** [velikost] zaměstnanců | [odvětví] | [město]
**Rozhodovací pravomoc:** [CEO/HR Director/Manager]
**Deal:** [hodnota] Kč | Fáze: [stage] | Health: [score]/100
**Poslední kontakt:** [datum] — [typ: email/call/meeting]
**Sentiment:** [pozitivní/neutrální/chladný/negativní]

### Co víme (NEPTEJ SE na to)
- [Zjištěné info z enrichmentu a předchozích konverzací]

### Co nevíme (ZEPTEJ SE)
- [Mezery v informacích důležité pro kvalifikaci]
```

### Step 3: SPIN Script Generation
Uses `spin-questions` skill framework but adds:

**Czech-adapted openers:**
- CEO: "Pane [příjmení], v přípravě na náš hovor jsem si prošel [specific thing]. Mám k tomu pár otázek."
- HR: "Paní [příjmení], mluvil jsem s několika HR řediteli ve vašem odvětví — objevuje se jeden vzorec. Zajímalo by mě, jestli to platí i u vás."

**Frame control (Klaff) for Czech market:**
| Situace | Technika | Příklad |
|---------|----------|---------|
| CEO testuje vaši znalost | Status frame | "[Specifický insight o jejich firmě z výzkumu]" |
| "Pošlete nabídku" | Prize frame | "Rád. Nejdřív se ale ujistěme, že to pro vás dává smysl." |
| "Kolik to stojí?" | Anchor high | "Firmy vaší velikosti typicky investují 150-200K ročně. Pro pilotní projekt je to 0 Kč." |
| "Nemáme rozpočet" | Implication | "Rozumím. Co vás stojí, když klíčový člověk odejde bez varování?" |
| "Používáme [competitor]" | Reframe | "Jak jste spokojeni s [specific weakness of competitor]?" |

### Step 4: Meeting Agenda Card
```
## Agenda: [Firma] | [Datum] [Čas]
**Cíl:** [Advance to = konkrétní další krok]
**Minimum:** [Fallback = co je minimum akceptovatelný výsledek]
**Časování:**
- 0-5 min: Rapport + kontext
- 5-15 min: SPIN discovery
- 15-20 min: Představení řešení (pokud kvalifikovaní)
- 20-25 min: Pricing + pilot nabídka
- 25-30 min: Další kroky + commitment

**Red flags (zastavit pitch pokud):**
- Není rozhodovací pravomoc
- Nemají reálný problém s fluktuací/engagementem
- Rozpočet <50K ročně
- Méně než 30 zaměstnanců

**Advance options (od nejlepšího):**
1. Podpis pilot smlouvy → start za 2 týdny
2. Domluvit demo pro celý tým → konkrétní datum
3. Poslat nabídku → follow-up call za 3 dny
4. Intro k dalšímu stakeholderovi
```

## Objection Playbook (10 objections — memorize the reframes)

### 1. "Nemáme čas" (No time)
- **Reframe:** "Rozumím. Echo Pulse zabere 3 minuty. Kolik času stojí neplánovaný odchod klíčového člověka?"
- **CEO hook:** "Nejde o další HR projekt. Jde o prevenci — 3 minuty teď vs. 3 měsíce hledání náhrady."
- **Call script:** "To chápu. Většina našich klientů to říkala taky. Pak jeden klíčový člověk odešel a stálo je to [X] měsíců a [Y] Kč. Echo Pulse zabere 3 minuty."

### 2. "Už děláme průzkumy" (Already do surveys)
- **Reframe:** "Skvěle. Jak rychle dostáváte výsledky? A jaká je návratnost vyplnění?"
- **Differentiation:** "Klasické průzkumy = 40 otázek, 20 minut, výsledky za měsíc. Echo Pulse = gamifikovaný chatbot, 3 minuty, výsledky za 24h, AI doporučení."
- **Call script:** "Jakou máte návratnost? U klasických průzkumů bývá 30-40 %. U Echo Pulse je to přes 85 % díky gamifikaci."

### 3. "Je to drahé" (Too expensive)
- **Reframe:** "99 Kč na osobu za měsíc. Jeden odchod zaměstnance stojí 6-9 měsíčních platů. Kolik lidí vám odešlo loni?"
- **ROI math:** "200 zaměstnanců × 99 Kč = 19 800 Kč/měsíc. Jeden odchod = 300 000+ Kč. Stačí zabránit 1 odchodu za rok."
- **Fallback:** "Pilotní projekt pro 1 tým je zdarma. Žádné riziko."

### 4. "Lidé nebudou upřímní" (Won't be honest)
- **Reframe:** "Proto je Echo anonymní. A je to chatbot, ne formulář — lidé jsou upřímnější s chatbotem než s HR."
- **Data:** "Naše data ukazují, že anonymní chatbot dostává o 40 % upřímnější odpovědi než klasický dotazník."

### 5. "Teď není dobrý čas" (Bad timing)
- **Reframe:** "Kdy bude lepší čas? Fluktuace nečeká na konec kvartálu."
- **Soft alternative:** "Rozumím. Co takhle — zarezervujeme si 15 minut za [3 týdny]? Mezitím vám pošlu benchmark pro vaše odvětví."

### 6. "Vedení to neschválí" (Leadership won't approve)
- **Reframe:** "Co kdyby vedení vidělo, kolik je stojí neřešení? Připravím vám ROI kalkulaci pro váš board."
- **Offer:** "Můžu udělat krátkou prezentaci pro vašeho CEO — 15 minut, jen fakta a čísla."

### 7. "Bojíme se výsledků" (Afraid of findings)
- **Reframe:** "To je pochopitelné. Ale problém existuje, ať ho měříte, nebo ne. Data vám dají kontrolu."
- **Guarantee:** "Máme 100% garanci vrácení peněz, pokud nenajdeme nic relevantního."

### 8. "Jsme moc malí" (Too small)
- **Reframe:** "Echo Pulse funguje od 30 lidí. Menší firma = rychlejší výsledky. Změny vidíte za týdny, ne za měsíce."

### 9. "Co máme s výsledky dělat?" (What to do with results)
- **Reframe:** "Echo Pulse nedává jen data — AI generuje konkrétní doporučení s prioritami. Říkáme vám CO dělat a PROČ."

### 10. "Už jsme to zkoušeli" (Tried before)
- **Reframe:** "Co přesně jste zkoušeli? Klasický dotazník? Echo Pulse je jiný — gamifikovaný chatbot, AI analýza, hotové doporučení."
- **Probe:** "Jak dopadl ten předchozí pokus? Co na něm nefungovalo?"

## Signal-Based Call Triggers
Before calling, check for buying signals:
- **HR hiring** → company is investing in people = warm
- **Funding announcement** → money to spend = warm
- **Glassdoor complaints** → engagement problem = hot
- **Leadership change** → new leader wants data = hot
- **Growth milestone (50+, 100+, 200+ employees)** → informal culture breaking down = warm
- **Competitor mention on LinkedIn** → already thinking about engagement = hot

## Post-Call Processing

After every call, immediately:
1. Log call notes to Pipedrive (structured: outcome, next step, sentiment)
2. Update deal health score based on call outcome
3. Trigger appropriate cadence: advance → nurture, no-advance → re-engage
4. If ADVANCE: auto-generate follow-up email with summary + next steps
5. If CONTINUATION: schedule next touch via cadence-engine
6. If meeting was recorded (Fireflies/Otter): upload transcript for Claude coaching analysis
7. Publish `pipeline.call_completed` event to bus

## ADHD Call Prep Quick Card (for Josef)
```
⏱️ 5 min before call — scan this card
🎯 ONE goal for this call: [advance to]
❓ TOP 3 questions to ask:
   1. [Implication question — the money maker]
   2. [Problem question — surface pain]
   3. [Need-payoff — let THEM sell the solution]
🛡️ Most likely objection: [X] → Response: [Y]
⚡ Pattern interrupt opener: [specific to this prospect]
📏 RULE: Talk max 20% of the time. Listen 80%.
```

## Trigger
- Auto-generates 30 min before any Pipedrive activity of type "call" or "meeting"
- Can be manually triggered: write to `bus/inbox/obchodak/` with `task_type: "spin_prep"`
- Google Calendar events with [Behavera] or [Echo Pulse] in title also trigger prep
- Signal-based: when lead score jumps >20 points, auto-generate prep for immediate call

## Output
- Pre-call brief: `meeting-prep/[company]-[date].md`
- SPIN script: embedded in pre-call brief
- ADHD quick card: top of the brief
- Post-call log: Pipedrive activity note + `knowledge/AGENT_INSIGHTS.md`

## Knowledge Sources
- `knowledge/OBJECTION_LIBRARY.md` — 10 objections with reframes and scripts
- `knowledge/JOSEF_TONE_OF_VOICE.md` — voice matching for call scripts
- `knowledge/CZECH_PHRASE_LIBRARY.md` — real phrases for natural conversation
- `knowledge/COPYWRITER_KNOWLEDGE_BASE.md` — product details, case studies, competitive data
