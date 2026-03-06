# OpenClaw ↔ Claude MCP Migration Plan

**Verze:** 1.0
**Datum:** 2026-03-06
**Autor:** Systems Architect
**Status:** DRAFT — k review Josefem

---

## Executive Summary

OpenClaw zůstává **master orchestrátor** (cron scheduling, state management, rozhodování, audit trail, inter-agent triggers). Claude MCP konektory přebírají roli **tool executor** tam, kde nabízejí spolehlivější, levnější nebo méně údržbový přístup k externím službám.

**Princip:** OpenClaw = mozek. Claude konektory = ruce.

**Očekávaný dopad:**
- Eliminace 4 custom skriptů (gog skill, části pipedrive integrací)
- Snížení maintenance burden o ~30 %
- Zachování 100 % auditability a rollback schopnosti
- Nulová ztráta proaktivity nebo determinismu

---

## 1. Inventura: Co máme

### OpenClaw (10 agentů, 54 cronjobů)

| Agent | Cronů | Integrace | Model |
|-------|-------|-----------|-------|
| Bridge | 2 | Filesystem, approval-queue | claude-sonnet |
| PipelinePilot | 8 | Pipedrive API (MATON_API_KEY) | gpt-4o-mini |
| KnowledgeKeeper | 9+3 | Filesystem, books/, supadata | gpt-4o-mini |
| CopyAgent | 7 | Filesystem, templates/ | claude-sonnet |
| GrowthLab | 3+1 | Web search, supadata, YouTube | claude-sonnet |
| InboxForge | 3 | Gmail (gog skill) | claude-sonnet |
| CalendarCaptain | 3 | Google Calendar (gog skill) | gpt-4o-mini |
| Codex | 4 | Git, filesystem, scripts/ | gpt-4o |
| Auditor | 4 | Pipedrive data (read-only) | gpt-4o-mini |
| Reviewer | 4 | Filesystem (all outputs) | gpt-4o |

### Dostupné Claude MCP konektory

| Konektor | Read | Write | Klíčové omezení |
|----------|------|-------|-----------------|
| **Gmail** | search, read, threads, labels | create draft | **NEMŮŽE posílat** — jen drafty. Žádné labeling/archive. |
| **Google Calendar** | list, get, find free time, find meeting times | create, update, delete, respond | **Plně pokrytý.** Kompletní CRUD. |
| **Slack** | search (public+private), read channels, threads, users, canvases | send message, draft, schedule, create canvas | **Nemůže editovat/mazat zprávy.** Nemůže spravovat kanály. |
| **Clay (enrichment)** | find company, find contacts, get accounts | enrich companies, enrich contacts, run subroutines | **Async** — nutný polling. Potřebuje doménu/LinkedIn URL. |
| **Supabase** | SQL, tables, migrations, logs, edge functions | SQL, migrations, deploy edge functions | Plný DB přístup. |
| **Make.com** | scenarios, executions, connections | create/run/update scenarios, tools, data stores | Kompletní automation platform. |
| **Vercel** | deployments, logs, projects | deploy | Žádné env vars, project creation. |
| **Guru** | search docs, answer generation, get cards | create draft, update card | Knowledge base CRUD. |
| **Scheduled Tasks** | list tasks | create, update tasks | Claude-native cron scheduling. |

---

## 2. Workflow kategorizace (A / B / C)

### Legenda
- **A** = Delegovat na Claude MCP konektor (méně údržby, stejná/lepší spolehlivost)
- **B** = Nechat v OpenClaw (jasná výhoda: proaktivita, stav, determinismus, audit, vendor-independence)
- **C** = Hybridní (OpenClaw řídí, Claude vykoná dílčí operaci)

---

### 2.1 InboxForge (Gmail Operations)

| Krok | Aktuálně | Kategorie | Zdůvodnění |
|------|----------|-----------|------------|
| **Gmail scan/triage** | gog skill → TRIAGE.md | **C** | Gmail MCP umí search+read spolehlivěji než custom gog wrapper. OpenClaw řídí timing (6×/den), ukládá stav do TRIAGE.md, rozhoduje o prioritách. Claude provede jen `gmail_search_messages` + `gmail_read_message`. |
| **Draft návrhy** | gog skill → DRAFTS.md | **C** | Gmail MCP umí `gmail_create_draft` přímo. OpenClaw generuje text (CopyAgent), Claude jej vloží jako Gmail draft. Výhoda: draft se objeví přímo v Gmail UI. |
| **Follow-up tracking** | gog skill + filesystem | **B** | Vyžaduje cross-referenci s Pipedrive daty, historií, deal stage. OpenClaw drží stav v FOLLOW_UPS.md a rozhoduje logiku. Gmail MCP neumí labelovat/archivovat. |
| **Email odesílání** | approval-queue → gog skill | **B** | Gmail MCP **NEMŮŽE posílat emaily** — jen drafty. OpenClaw musí zachovat vlastní send mechanismus nebo Josef posílá ručně z draftu. |

**Trade-off:** Gmail MCP nahradí gog skill pro READ operace (search, read). WRITE zůstává hybridní (draft ano, send ne).

---

### 2.2 CalendarCaptain (Google Calendar)

| Krok | Aktuálně | Kategorie | Zdůvodnění |
|------|----------|-----------|------------|
| **Morning calendar pull** | gog skill → TODAY.md | **A** | Google Calendar MCP je plně pokrytý. `gcal_list_events` + `gcal_find_my_free_time` jsou spolehlivější než custom gog wrapper. Přímý JSON response, žádný parsing. |
| **Pomodoro block creation** | gog skill + logic | **C** | OpenClaw vypočítá bloky (ADHD-aware scheduling), Claude provede `gcal_create_event` pro každý blok. OpenClaw drží logiku a stav. |
| **Meeting prep** | filesystem + SPIN notes | **B** | Čistě interní — čte z pipedrive/spin-notes/ a píše meeting-prep/. Žádná external integrace. |
| **Midday rebalance** | gog skill + logic | **C** | OpenClaw sleduje odchylky od plánu, Claude přes MCP čte aktuální kalendář a případně updatuje eventy. |
| **Tomorrow prep** | gog skill | **A** | Jednoduchý pull zítřejšího kalendáře. `gcal_list_events` s timeMin/timeMax. |
| **Find meeting times** | N/A (manual) | **A** | `gcal_find_meeting_times` je nová capability — OpenClaw ji může využít pro automatické návrhy meeting slotů. |

**Trade-off:** Kalendář je jasný kandidát na plnou migraci čtení/zápisu na Claude MCP. Scheduling logika (Pomodoro, ADHD bloky) zůstává v OpenClaw.

---

### 2.3 PipelinePilot (Pipedrive CRM)

| Krok | Aktuálně | Kategorie | Zdůvodnění |
|------|----------|-----------|------------|
| **Deal fetching + scoring** | pipedrive_lead_scorer.py | **B** | Custom scoring formula (Fit 0-40 + Engagement 0-35 + Momentum 0-25). Deterministický výpočet. Pipedrive API přes MATON_API_KEY s rate limiting. Claude MCP nemá Pipedrive konektor. |
| **SPIN analysis prep** | PipelinePilot cron | **B** | Vyžaduje hlubokou znalost deal context, stage mapping, custom fields. Čistě interní zpracování. |
| **Deal enrichment** | PipelinePilot + supadata | **C** | Clay MCP může enrichovat firmy (headcount, tech stack, funding, news). OpenClaw řídí kdy a co enrichovat, Clay provede lookup. **Nahrazuje část supadata-intel pro company research.** |
| **CRM hygiene** | pipedrive_open_deal_activity_guard.py | **B** | Deterministic rules, custom Pipedrive API calls, field updates. Vendor-independent. |
| **Contact enrichment** | manual/supadata | **C** | Clay MCP `find-and-enrich-contacts-at-company` + `add-contact-data-points` (email, work history). OpenClaw triggeruje, Clay vykonává. |
| **Activity logging** | Pipedrive API | **B** | Direct API writes. Potřebuje MATON_API_KEY a custom field mapping. |

**Trade-off:** Pipedrive core zůstává v OpenClaw (žádný MCP konektor existuje). Clay MCP přidává novou enrichment schopnost, kterou OpenClaw nemá.

---

### 2.4 CopyAgent (Content Production)

| Krok | Aktuálně | Kategorie | Zdůvodnění |
|------|----------|-----------|------------|
| **Email drafting** | CopyAgent → drafts/ | **B** | Jádro CopyAgenta — tone matching, Josef's voice, SPIN-based templates. Žádný konektor tohle nenahradí. |
| **Slack insights extraction** | copyagent-slack cron | **C** | Slack MCP umí `slack_search_public_and_private` + `slack_read_channel` spolehlivěji než custom scraping. OpenClaw řídí co hledat, Claude vykoná search. |
| **Blog writing** | CopyAgent cron | **B** | Čistě generativní úloha. Interní workflow. |
| **Content plan** | CopyAgent cron | **B** | Strategické rozhodování, interní stav. |

**Trade-off:** CopyAgent je primarily generativní — konektory mu jen dodávají vstupní data (Slack insights).

---

### 2.5 GrowthLab (Market Intelligence)

| Krok | Aktuálně | Kategorie | Zdůvodnění |
|------|----------|-----------|------------|
| **HR tech news scan** | web-research skill | **B** | Custom research methodology, strukturovaný output do DAILY-INTEL.md. Web search je core capability. |
| **Competitor monitoring** | supadata-intel + web scraping | **C** | Clay MCP `find-and-enrich-company` + custom data points ("recent product announcements", "pricing changes") mohou nahradit část supadata web scraping. OpenClaw řídí competitor list a frekvenci. |
| **YouTube research** | youtube-watcher + supadata | **B** | Supadata API je levnější a determinističtější pro transcript extraction. Žádný YouTube MCP konektor. |
| **Company research pre-call** | supadata + manual | **C** | Clay MCP: company enrichment (tech stack, headcount, funding, news, competitors). OpenClaw integruje s deal context z Pipedrive. |
| **Battle card updates** | GrowthLab synthesis | **B** | Interní analytická práce, custom format. |

**Trade-off:** Clay MCP rozšiřuje research schopnosti (structured company data), ale nenahrazuje volné web research a YouTube monitoring.

---

### 2.6 Bridge (Orchestrator)

| Krok | Aktuálně | Kategorie | Zdůvodnění |
|------|----------|-----------|------------|
| **AM/PM digest generation** | Bridge cron → USER_DIGEST | **B** | Core orchestration. Čte ze všech agentů, koreluje, generuje report v Josefově tónu. |
| **Approval queue processing** | Bridge reads approval-queue/ | **B** | Security-critical. Lidský approval boundary. Nesmí být delegován. |
| **Task routing** | resolve_task_route.py | **B** | Deterministické rozhodování, model-router.json. Jádro systému. |
| **Inter-agent triggers** | triggers/ JSON files | **B** | Interní event system. Žádná external dependency. |
| **Digest delivery (future)** | Manual / Telegram | **C** | Slack MCP `slack_send_message` může doručit digest do Slack kanálu. OpenClaw generuje, Claude doručí. |

**Trade-off:** Bridge je mozek systému — zůstává 100 % v OpenClaw. Delivery mechanismus může být delegován.

---

### 2.7 Codex (System Builder)

| Krok | Aktuálně | Kategorie | Zdůvodnění |
|------|----------|-----------|------------|
| **Morning build** | Codex cron → git commit | **B** | Git operations, code changes, local filesystem. Žádný konektor nepomůže. |
| **Improvement proposals** | reads IMPROVEMENT_PROPOSALS.md | **B** | Interní workflow. |
| **Deployment** | manual / scripts | **C** | Vercel MCP `deploy_to_vercel` může automatizovat deploy dashboard. OpenClaw rozhoduje kdy. |

---

### 2.8 Auditor (Performance Coach)

| Krok | Aktuálně | Kategorie | Zdůvodnění |
|------|----------|-----------|------------|
| **Daily scoring** | Auditor reads Pipedrive data | **B** | Deterministické počítání XP, streak tracking, gamification logic. Čistě interní. |
| **Accountability reports** | Auditor writes SCOREBOARD.md | **B** | Custom format, ADHD-aware messaging. |
| **Weekly roast** | Friday 18:00 | **B** | Generativní + analytické. Interní. |

**Trade-off:** Auditor je 100 % interní analytik. Žádná migrace.

---

### 2.9 Reviewer (Quality Control)

| Krok | Aktuálně | Kategorie | Zdůvodnění |
|------|----------|-----------|------------|
| **Health check** | Reviewer reads all outputs | **B** | File freshness, quality scoring, anomaly detection. Filesystem-based. |
| **Prompt coaching** | Reviewer writes prompt-coaching/ | **B** | Interní optimalizace. |
| **System health report** | SYSTEM_HEALTH.md | **B** | Cross-agent correlation. Jádro kvality systému. |

**Trade-off:** Reviewer je 100 % interní. Žádná migrace.

---

### 2.10 KnowledgeKeeper (Learning & Knowledge)

| Krok | Aktuálně | Kategorie | Zdůvodnění |
|------|----------|-----------|------------|
| **Book processing** | reads ~/JosefGPT-Local/books/ | **B** | Local filesystem, custom extraction pipeline, tagging system. |
| **Knowledge synthesis** | writes IMPROVEMENT_PROPOSALS.md | **B** | Cross-referencing, deduplication, agent-specific tagging. |
| **Excerpt delivery** | CopyAgent email | **C** | Gmail MCP `gmail_create_draft` pro daily excerpt email. OpenClaw generuje obsah. |
| **Deep reads** | Night shift 23:00-03:00 | **B** | Autonomous, long-running, filesystem-based. |

---

## 3. Target Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    OPENCLAW (Master)                      │
│                                                           │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐   │
│  │  Cron    │ │  State   │ │  Router  │ │  Audit   │   │
│  │ Scheduler│ │  Manager │ │  (model) │ │  Logger  │   │
│  └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘   │
│       │             │            │             │          │
│  ┌────┴─────────────┴────────────┴─────────────┴────┐   │
│  │              Agent Pipeline                        │   │
│  │  Bridge → PipelinePilot → CopyAgent → InboxForge │   │
│  │  GrowthLab → KnowledgeKeeper → Codex → Auditor   │   │
│  │  CalendarCaptain → Reviewer                        │   │
│  └────────────────────┬──────────────────────────────┘   │
│                       │                                   │
│  ┌────────────────────┴──────────────────────────────┐   │
│  │          Claude MCP Gateway (Interface Layer)      │   │
│  │                                                    │   │
│  │  request_id + agent_id + operation + context       │   │
│  │         ↓ ↓ ↓ ↓ ↓ ↓ ↓                           │   │
│  └────────┬──┬──┬──┬──┬──┬──┬────────────────────────┘   │
└───────────┼──┼──┼──┼──┼──┼──┼────────────────────────────┘
            │  │  │  │  │  │  │
    ┌───────┘  │  │  │  │  │  └───────┐
    ▼          ▼  ▼  ▼  ▼  ▼          ▼
┌──────┐ ┌─────┐ ┌─────┐ ┌────┐ ┌──────┐ ┌───────┐ ┌──────┐
│Gmail │ │GCal │ │Slack│ │Clay│ │Supa- │ │Vercel│ │Make  │
│ MCP  │ │ MCP │ │ MCP │ │MCP │ │base  │ │ MCP  │ │ MCP  │
│      │ │     │ │     │ │    │ │ MCP  │ │      │ │      │
│search│ │CRUD │ │send │ │enr-│ │SQL   │ │deploy│ │scen- │
│read  │ │full │ │read │ │ich │ │edge  │ │logs  │ │arios │
│draft │ │     │ │srch │ │    │ │fn    │ │      │ │tools │
└──────┘ └─────┘ └─────┘ └────┘ └──────┘ └──────┘ └──────┘
```

### Datové toky (po migraci)

**Gmail Read Flow (InboxForge):**
```
OpenClaw cron (6×/den)
  → InboxForge agent aktivován
  → OpenClaw: "Proveď Gmail scan pro josef.hofman@behavera.com"
  → Claude MCP: gmail_search_messages(q="is:unread after:YYYY-MM-DD")
  → Claude MCP: gmail_read_message(messageId) × N
  → OpenClaw: zpracuje výsledky, zapíše TRIAGE.md
  → OpenClaw: rozhodne o prioritách, triggeruje CopyAgent pokud potřeba
```

**Calendar Flow (CalendarCaptain):**
```
OpenClaw cron (07:00)
  → CalendarCaptain aktivován
  → Claude MCP: gcal_list_events(timeMin=today, timeMax=today+1)
  → Claude MCP: gcal_find_my_free_time(calendarIds=["primary"])
  → OpenClaw: Pomodoro scheduling logic (ADHD blocks)
  → Claude MCP: gcal_create_event() × N (bloky)
  → OpenClaw: zapíše TODAY.md, pomodoro/[date].md
```

**Enrichment Flow (PipelinePilot + Clay):**
```
OpenClaw cron (pipelinepilot-enrich-am)
  → PipelinePilot identifikuje deals k obohacení
  → OpenClaw: "Enrichuj firmu [domain]"
  → Claude MCP: find-and-enrich-company(domain, dataPoints=[tech_stack, funding, headcount])
  → Claude MCP: find-and-enrich-contacts-at-company(domain, filters={job_title: "CEO"})
  → [poll via get-existing-search]
  → OpenClaw: zapíše do ENRICHMENT_LOG.md
  → OpenClaw: updatuje Pipedrive custom fields přes vlastní API
```

**Slack Insights Flow (CopyAgent):**
```
OpenClaw cron (copyagent-slack)
  → CopyAgent aktivován
  → Claude MCP: slack_search_public("Echo Pulse OR Behavera OR engagement survey")
  → Claude MCP: slack_read_thread(channel_id, message_ts) × relevantní vlákna
  → OpenClaw: CopyAgent extrahuje insights, objections, wins
  → OpenClaw: zapíše SLACK_INSIGHTS.md, OBJECTION_LIBRARY.md
```

**Digest Delivery Flow (Bridge):**
```
OpenClaw cron (bridge-am-report / bridge-pm-report)
  → Bridge generuje USER_DIGEST_AM/PM.md (max 15 řádků, Czech)
  → Claude MCP: slack_send_message(channel_id=Josef_DM, message=digest)
  → OpenClaw: loguje delivery status
```

---

## 4. Rozhraní OpenClaw ↔ Claude MCP

### 4.1 Request Format (OpenClaw → Claude)

```json
{
  "request_id": "OC-2026-03-06-INB-001",
  "agent_id": "inboxforge",
  "operation": "gmail_scan",
  "connector": "gmail_mcp",
  "timestamp": "2026-03-06T08:00:00+01:00",
  "context": {
    "account": "josef.hofman@behavera.com",
    "query": "is:unread after:2026-03-05",
    "max_results": 50
  },
  "constraints": {
    "timeout_ms": 30000,
    "retry_count": 0,
    "max_retries": 3,
    "idempotent": true
  },
  "audit": {
    "cron_job": "inboxforge-scan-1",
    "trigger_reason": "scheduled",
    "session_id": "OC-SESSION-2026-03-06-08"
  }
}
```

### 4.2 Response Format (Claude → OpenClaw)

```json
{
  "request_id": "OC-2026-03-06-INB-001",
  "status": "success",
  "connector": "gmail_mcp",
  "operation": "gmail_scan",
  "timestamp": "2026-03-06T08:00:12+01:00",
  "duration_ms": 12400,
  "result": {
    "messages_found": 7,
    "messages": [
      {
        "id": "msg_abc123",
        "thread_id": "thr_xyz789",
        "from": "jan.novak@acme.cz",
        "subject": "Re: Echo Pulse demo",
        "snippet": "Díky za nabídku, rád bych...",
        "date": "2026-03-05T16:30:00+01:00",
        "labels": ["INBOX", "UNREAD"],
        "has_attachment": false
      }
    ]
  },
  "sensitivity": "internal",
  "suggested_next_steps": [
    {
      "action": "classify_priority",
      "target": "msg_abc123",
      "reason": "Prospect reply to demo invitation"
    }
  ],
  "errors": []
}
```

### 4.3 Error Handling

```json
{
  "request_id": "OC-2026-03-06-INB-001",
  "status": "error",
  "error": {
    "code": "CONNECTOR_TIMEOUT",
    "message": "Gmail MCP did not respond within 30000ms",
    "retryable": true,
    "retry_after_ms": 5000
  },
  "fallback": {
    "action": "use_gog_skill",
    "reason": "MCP connector unavailable"
  }
}
```

**Retry strategie:**
| Error type | Retry? | Backoff | Max retries | Fallback |
|------------|--------|---------|-------------|----------|
| CONNECTOR_TIMEOUT | Ano | Exponential (5s, 15s, 45s) | 3 | gog skill / custom script |
| AUTH_EXPIRED | Ne | — | 0 | Alert Josef, pause workflow |
| RATE_LIMITED | Ano | Respect Retry-After header | 5 | Queue for next cron cycle |
| INVALID_INPUT | Ne | — | 0 | Log error, alert Reviewer |
| PARTIAL_RESULT | Ano | Fixed 10s | 1 | Accept partial, flag incomplete |

**Idempotence:**
- Každý request má unikátní `request_id`
- Gmail reads jsou inherentně idempotentní
- Calendar creates kontrolují existenci eventu před vytvořením (summary + time match)
- Slack sends logují message_ts pro deduplikaci

### 4.4 Audit Logging

Každá MCP operace se loguje do `logs/mcp-audit/YYYY-MM-DD.jsonl`:

```jsonl
{"ts":"2026-03-06T08:00:00","req_id":"OC-...-001","agent":"inboxforge","op":"gmail_search","connector":"gmail_mcp","status":"success","duration_ms":3200,"result_count":7}
{"ts":"2026-03-06T08:00:04","req_id":"OC-...-002","agent":"inboxforge","op":"gmail_read","connector":"gmail_mcp","status":"success","duration_ms":800,"msg_id":"msg_abc123"}
```

**Retence:** 30 dní rolling. Weekly aggregace do `logs/mcp-audit/weekly-summary/`.

---

## 5. Migrační plán (ordered by risk)

### Phase 0: Příprava (den 1-2)

- [ ] Vytvořit `logs/mcp-audit/` directory + logging wrapper
- [ ] Vytvořit feature flag systém v `control-plane/mcp-migration-flags.json`
- [ ] Definovat health check pro každý MCP konektor (ping test)
- [ ] Nastavit dual-write mode: OpenClaw provede operaci OBOJÍM způsobem (starý + MCP), porovná výsledky

```json
// control-plane/mcp-migration-flags.json
{
  "version": 1,
  "flags": {
    "gmail_read_via_mcp": false,
    "gmail_draft_via_mcp": false,
    "gcal_read_via_mcp": false,
    "gcal_write_via_mcp": false,
    "slack_read_via_mcp": false,
    "slack_write_via_mcp": false,
    "clay_enrichment_via_mcp": false,
    "vercel_deploy_via_mcp": false,
    "digest_delivery_slack_mcp": false
  },
  "rollback_to": "gog_skill",
  "dual_write_mode": true,
  "updated_at": "2026-03-06"
}
```

### Phase 1: Read-only Calendar (den 3-5) — LOW RISK

**Co:** CalendarCaptain morning pull přes `gcal_list_events` místo gog skill.

**Proč první:** Read-only, deterministic output, snadno porovnatelný, žádný side-effect.

**Kroky:**
1. Zapnout `gcal_read_via_mcp: true`
2. CalendarCaptain cron volá MCP, ALE zároveň gog skill (dual-write)
3. Porovnat výstupy 3 dny
4. Pokud match ≥ 95 %, vypnout gog skill pro calendar read
5. Updatnout TODAY.md generation

**Rollback:** `gcal_read_via_mcp: false` → okamžitý návrat na gog skill.

### Phase 2: Read-only Gmail (den 6-10) — LOW RISK

**Co:** InboxForge scan přes `gmail_search_messages` + `gmail_read_message`.

**Kroky:**
1. Zapnout `gmail_read_via_mcp: true`
2. Dual-write 3 dny
3. Porovnat TRIAGE.md výstupy
4. Vypnout gog skill pro email read

**Rollback:** `gmail_read_via_mcp: false`.

### Phase 3: Calendar Write (den 11-15) — MEDIUM RISK

**Co:** CalendarCaptain Pomodoro block creation přes `gcal_create_event`.

**Kroky:**
1. Zapnout `gcal_write_via_mcp: true`
2. Dry-run: generuj eventy ale neposílej (log only) — 2 dny
3. Live: vytvářej eventy přes MCP — 3 dny s monitoringem
4. Duplikát check: před vytvořením ověř že event neexistuje

**Rollback:** `gcal_write_via_mcp: false` + manuální smazání duplikátů.

### Phase 4: Slack Read (den 16-20) — LOW RISK

**Co:** CopyAgent Slack insights extraction přes `slack_search_public_and_private`.

**Kroky:**
1. Zapnout `slack_read_via_mcp: true`
2. CopyAgent cron volá Slack MCP search
3. Porovnat s manuálně získanými insights
4. Stabilizovat SLACK_INSIGHTS.md pipeline

**Rollback:** `slack_read_via_mcp: false`, zpět na manual/scripted.

### Phase 5: Clay Enrichment (den 21-25) — MEDIUM RISK

**Co:** PipelinePilot enrichment přes Clay MCP (company + contact data).

**Kroky:**
1. Zapnout `clay_enrichment_via_mcp: true`
2. Pro 5 test deals: enrichuj přes Clay, porovnej s existujícími daty
3. Nastavit auto-enrichment pro nové deals (async polling)
4. Integrovat enrichment výsledky do ENRICHMENT_LOG.md

**Rollback:** `clay_enrichment_via_mcp: false`, zpět na supadata-intel only.

### Phase 6: Gmail Draft + Slack Send (den 26-30) — HIGH RISK

**Co:**
- InboxForge: `gmail_create_draft` místo gog skill pro draft creation
- Bridge: `slack_send_message` pro digest delivery

**Kroky:**
1. Gmail draft: zapnout `gmail_draft_via_mcp: true`
2. Ověřit že drafty se objeví v Gmail UI
3. Slack delivery: zapnout `digest_delivery_slack_mcp: true`
4. Bridge AM/PM report posílat do Slack DM
5. Monitor 5 dní

**Rollback:** Okamžitý — flags off.

### Phase 7: Vercel Deploy (den 31-35) — MEDIUM RISK

**Co:** Codex deploy dashboard přes `deploy_to_vercel`.

**Kroky:**
1. Zapnout `vercel_deploy_via_mcp: true`
2. Codex volá Vercel MCP pro dashboard deploy
3. Ověřit deployment logs přes `get_deployment_build_logs`

**Rollback:** Manual deploy / revert.

---

## 6. Non-Go List (NEMIGROVAT)

| Workflow | Proč NE | Co by se muselo ověřit pro změnu |
|----------|---------|----------------------------------|
| **Pipedrive API operations** | Žádný Pipedrive MCP konektor. Custom API s MATON_API_KEY, rate limiting, custom field mapping. | Existence spolehlivého Pipedrive MCP s full CRUD. |
| **Email sending** | Gmail MCP neumí send — jen draft. Kritický pro sales follow-ups. | Gmail MCP přidání send capability. |
| **Gmail label/archive** | Gmail MCP nemá modify_thread. InboxForge potřebuje labelovat pro tracking. | Gmail MCP přidání label management. |
| **Lead scoring formula** | Deterministický výpočet (Fit+Engagement+Momentum). Custom Python. Claude by nebyl deterministic. | Nic — vždy v OpenClaw. |
| **Approval queue** | Security boundary. Lidský review. Nesmí být automatizován. | Nic — vždy v OpenClaw. |
| **Inter-agent triggers** | Interní event bus. Sub-millisecond latence. Žádný external dependency. | Nic — vždy v OpenClaw. |
| **Book processing** | Local filesystem, custom extraction, 5-7 books/day. | Nic — vždy v OpenClaw. |
| **XP/Streak gamification** | Deterministické počítání, custom rules. | Nic — vždy v OpenClaw. |
| **Model routing** | Cost optimization, 4 budget tiers. Core orchestration logic. | Nic — vždy v OpenClaw. |
| **Reverse prompt system** | Proaktivní chování agentů. Core differentiator. | Nic — vždy v OpenClaw. |
| **Night shift operations** | Autonomous 22:30-06:30. Potřebuje continuous cron, ne on-demand Claude sessions. | Claude scheduled tasks nemají session persistence. |
| **SPIN analysis** | Deep deal context, custom Pipedrive data, structured output. | Nic — vždy v OpenClaw. |
| **Health checks (Reviewer)** | Cross-agent correlation, file freshness monitoring. Filesystem-based. | Nic — vždy v OpenClaw. |

---

## 7. Metriky a testy

### Klíčové metriky

| Metrika | Cíl | Měření | Alert threshold |
|---------|-----|--------|-----------------|
| **MCP operace úspěšnost** | > 98 % | success / total per day | < 95 % |
| **MCP latence (P95)** | < 15s | duration_ms z audit logu | > 30s |
| **Fallback rate** | < 5 % | fallback_used / total | > 10 % |
| **Dual-write match rate** | > 95 % | matching_results / total (Phase 0-2) | < 90 % |
| **Calendar event duplicates** | 0 | dedup check before create | > 0 |
| **Gmail draft delivery rate** | 100 % | drafts visible in Gmail / drafts created | < 100 % |
| **Enrichment completeness** | > 80 % | fields filled / fields requested | < 60 % |
| **Cost per MCP operation** | Track | Claude API billing per operation type | Budget TBD |
| **Digest delivery success** | 100 % | Slack send confirmed / digest generated | < 100 % |
| **Rollback count** | 0 | feature flag switches back | > 2/week |

### Test plan

| Test | Kdy | Jak |
|------|-----|-----|
| **MCP connector ping** | Před každým cron cycle | Trivial read operation per connector |
| **Dual-write comparison** | Phase 1-2 | Diff old vs. new output |
| **Calendar dedup test** | Phase 3 | Create event, verify no duplicate |
| **Slack delivery test** | Phase 6 | Send test message, verify receipt |
| **Enrichment quality** | Phase 5 | Compare Clay vs. supadata results for same company |
| **Fallback trigger test** | Weekly | Simulate MCP timeout, verify fallback fires |
| **Full rollback drill** | Monthly | Turn all flags off, verify system runs on old path |
| **End-to-end pipeline** | Weekly | Trace one deal through entire pipeline (Pipedrive → enrichment → email draft → calendar) |

---

## 8. Audit Checklist (pro třetí stranu)

### Je návrh skutečně optimální a ne vendor-driven?

- [ ] **Vendor-independence test:** Může OpenClaw fungovat bez Claude MCP konektorů? → ANO. Feature flags umožňují okamžitý rollback na custom skripty.

- [ ] **No capability loss:** Existuje workflow, který po migraci bude méně schopný? → NE. Všechny critical paths (sending, CRM writes, scoring, approval) zůstávají v OpenClaw.

- [ ] **Cost comparison:** Je MCP cesta levnější? → Ověřit: Claude API token cost za MCP volání vs. cost gog skill execution. Pokud MCP je >2× dražší, zvážit ponechání.

- [ ] **Latency comparison:** Je MCP rychlejší? → Měřit: dual-write mode porovnání latencí. Pokud MCP je >3× pomalejší, ponechat custom.

- [ ] **Reliability comparison:** Je MCP spolehlivější? → Měřit: uptime a error rate obou cest přes 14 dní dual-write.

- [ ] **Proactivity preservation:** Jsou proaktivní schopnosti zachovány? → ANO. Reverse prompt system, night shift, autonomous crons zůstávají v OpenClaw.

- [ ] **Audit trail completeness:** Jsou vstupy/výstupy MCP operací logované? → ANO. `logs/mcp-audit/` s request_id tracing.

- [ ] **Determinism check:** Jsou deterministické výpočty (scoring, scheduling) zachovány v OpenClaw? → ANO. Žádný výpočet nepřechází na Claude.

- [ ] **Security boundary:** Je approval queue nedotčen? → ANO. Zůstává 100 % v OpenClaw s lidským review.

- [ ] **Fallback path:** Existuje pro každý migrovaný workflow funkční fallback? → ANO. Feature flags + dual-write mode.

- [ ] **Night shift independence:** Funguje noční směna bez Claude session? → ANO. Night shift workflow zůstává v OpenClaw cronech.

- [ ] **Vendor lock-in assessment:** Kolik effort by vyžadoval odchod od Claude MCP? → Nízký. MCP konektory jsou nahraditelné (Gmail API, GCal API, Slack API přímo). OpenClaw wrapper abstrahuje konektor layer.

- [ ] **Data residency:** Procházejí citlivá data přes Claude? → Minimálně. Email obsah a calendar data. CRM credentials NE (Pipedrive zůstává custom). Audit log trackuje co prošlo.

- [ ] **Anti-pattern check:** Není Claude MCP použit jen proto, že "je to tu"? → Ověřit: pro každý A/C krok, existuje konkrétní benefit (méně údržby, lepší spolehlivost, nová capability)?

### Červené vlajky (pokud se objeví, přehodnotit migraci):

1. MCP konektor má error rate > 5 % po 14 dnech
2. Latence MCP operací je > 3× horší než custom skripty
3. Cost MCP operací přesahuje 2× cost vlastního řešení
4. Claude MCP session ztrácí kontext uprostřed multi-step operace
5. Rollback na custom skripty nefunguje okamžitě (> 1 min)
6. Audit log není kompletní (chybějící request_ids)

---

## Shrnutí rozhodnutí

| Kategorie | Počet workflow kroků | % |
|-----------|---------------------|---|
| **A — Plně delegovat na MCP** | 5 | 12 % |
| **B — Nechat v OpenClaw** | 28 | 67 % |
| **C — Hybridní** | 9 | 21 % |

**Co se reálně změní:**
1. **gog skill** (Gmail + Calendar custom wrapper) → nahrazen Gmail MCP + GCal MCP pro read + drafty
2. **Calendar writes** → GCal MCP pro Pomodoro bloky a event management
3. **Company enrichment** → Clay MCP jako nová capability (OpenClaw neměl)
4. **Slack insights** → Slack MCP pro search a read (nová capability)
5. **Digest delivery** → Slack MCP pro doručení AM/PM reportů
6. **Deploy** → Vercel MCP pro dashboard deployment

**Co se NEMĚNÍ:**
- Pipedrive integration (custom API zůstává)
- Scoring, routing, scheduling (deterministické, v OpenClaw)
- Approval queue (security boundary)
- Inter-agent triggers (interní)
- Night shift (autonomous)
- Book processing (local filesystem)
- Content generation (CopyAgent, KnowledgeKeeper)
- Health checks (Reviewer)
- Gamification (Auditor)

---

*Tento dokument je živý. Po každé migrační fázi aktualizovat výsledky dual-write porovnání a metriky.*
