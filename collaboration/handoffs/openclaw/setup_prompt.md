# OpenClaw Setup Prompt — Full System Configuration

**From:** Claude Code (Opus 4.6)
**For:** OpenClaw TUI / Spojka agent
**Date:** 2026-03-08
**Priority:** P0 — run immediately

---

## CONTEXT

Jsi Spojka — control-plane owner celého Clawdia systému. Máš přístup k celému Josefovu počítači a ke všem aplikacím. Tvůj úkol je nastavit VŠECHNO co je potřeba aby systém fungoval na maximum.

Projekt Clawdia je v `/Users/josefhofman/Clawdia/`. OpenClaw config je v `~/.openclaw/openclaw.json`.

---

## TASK 1: Claude Desktop Scheduled Tasks

Otevři Claude Desktop app a nastav scheduling pro tyto 3 NOVÉ tasky (SKILL.md soubory už existují v `~/.claude/scheduled-tasks/`):

1. **spin-call-prep** → Každé 2 hodiny, jen v pracovní době (08:00-18:00, weekdays)
2. **deal-follow-ups** → Denně v 16:00 (weekdays)
3. **weekly-forecast** → Pondělí 7:30

Ověř že existujících 7 tasků je taky naplánovaných:
- morning-briefing: denně 7:00
- inbox-triage: denně 7:30 + 13:00
- pipeline-hygiene: denně 8:00
- market-intel: denně 9:00
- scorecard-update: denně 18:00
- evening-review: denně 20:00
- agent-recovery: denně 22:00

## TASK 2: Claude.ai Connectors

Jdi na https://claude.ai → Settings → Connectors a zapni/ověř tyto:

### Musí být zapnuté:
- **Gmail** — email drafts, search, read (clawdia108@gmail.com)
- **Google Calendar** — events, free time, create events
- **Slack** — read/write messages (pokud máme Slack workspace)
- **Clay** — lead enrichment, contact data, company data
- **Google Drive** — document access
- **Figma** — design access (už je)
- **Vercel** — deploy (už je)
- **Supabase** — database (už je)
- **GitHub** — code (už je)

### Custom MCP connector (pokud je to možné):
Přidej custom connector pro Pipedrive:
- Name: "Pipedrive CRM"
- URL: potřebujeme vytvořit MCP server — zatím přeskoč

## TASK 3: Claude.ai Projects

Jdi na https://claude.ai → Projects a nastav tyto projekty s instrukcemi:

### Project: "Behavera Sales"
**Instructions:**
```
Jsi Josefův sales asistent pro Behavera / Echo Pulse. Mluvíš česky.

Kontext:
- Prodáváme Echo Pulse — AI-powered pulse surveys pro české firmy 50-500 zaměstnanců
- Cílíme na CEO a HR ředitele
- Pricing: 99-129 Kč/osoba/měsíc, free pilot pro 1 tým
- SPIN selling metodologie (Rackham)

Styl komunikace:
- Přímý, teplý, datově podložený
- Žádné korporátní floskule
- Vykání v první komunikaci
- Max 5 vět na email
- Vždy konkrétní CTA

Když píšeš emaily nebo copy:
1. Přečti skills/czech-b2b-copywriting/SKILL.md pro šablony
2. Přečti skills/spin-questions/SKILL.md pro SPIN otázky
3. Přečti skills/behavera-brand/SKILL.md pro brand guidelines
4. Používej brand barvy: #2D1B69 (primary), #9F7AEA (accent)

Pipeline data: pipedrive/PIPELINE_STATUS.md
Intel: intel/DAILY-INTEL.md
```

### Project: "Clawdia Ops"
**Instructions:**
```
Jsi operátor systému Clawdia — AI sales automation engine.

12 agentů: obchodak, archivar, textar, strateg, postak, kalendar, vyvojar, hlidac, kontrolor, udrzbar, planovac, spojka

Když řešíš systém:
1. Přečti skills/openclaw-ops/SKILL.md pro diagnostiku
2. Přečti control-plane/agent-states.json pro stav agentů
3. Přečti knowledge/EXECUTION_STATE.json pro health
4. Přečti control-plane/model-router.json pro routing pravidla

Důležité:
- OpenClaw TUI běží na openai-codex/gpt-5.3-codex (ChatGPT subscription, ZDARMA)
- Fallback: anthropic/claude-sonnet-4-6 (subscription token)
- NIKDY nepoužívej API keys — vždy subscription auth
- Launchd services: orchestrator, agent-runner, health-server, cowork-bridge, code-server
```

## TASK 4: Claude.ai Skills

Jdi na Claude.ai → Customize → Skills a nainstaluj/ověř tyto Anthropic official skills:

1. **skill-creator** — pro tvorbu dalších custom skills
2. **mcp-builder** — pro stavbu custom MCP serverů (Pipedrive, Lusha)
3. **doc-coauthoring** — pro spolupráci na dokumentech
4. **internal-comms** — pro status reporty a newslettery
5. **web-artifacts-builder** — pro HTML artifacts s React + Tailwind
6. **pdf** — pro generování PDF dokumentů (proposals, reports)
7. **xlsx** — pro Excel exporty (pipeline reporty)
8. **pptx** — pro PowerPoint prezentace (pitch decks)
9. **brand-guidelines** — nastav s Behavera barvami a fonty (viz skills/behavera-brand/SKILL.md)
10. **frontend-design** — pro UI/UX práci na Behavera webu

### Custom skills k instalaci:
Uploadni tyto jako custom skills (zip each SKILL.md folder):
- `skills/czech-b2b-copywriting/` → "czech-b2b-copywriting"
- `skills/spin-sales-prep/` → "spin-sales-prep"
- `skills/openclaw-ops/` → "openclaw-ops"
- `skills/behavera-brand/` → "behavera-brand"

## TASK 5: Claude Desktop Extensions

V Claude Desktop → Settings → Extensions ověř:
- Filesystem extension: allowed dirs include `/Users/josefhofman/Clawdia`, `/Users/josefhofman/Behaveranewsite`
- Figma extension: enabled

## TASK 6: Anthropic Auth Fix

Token `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` je uložený v `~/.openclaw/agents/main/agent/auth-profiles.json` ale OpenClaw ho vidí jako `token:missing`.

Spusť:
```bash
openclaw models auth paste-token --provider anthropic
```
A vlož ten token interaktivně. Ty máš TTY přístup, Claude Code ne.

Pak ověř: `openclaw models status` — anthropic by měl ukázat `token:ok`.

## TASK 7: Ověření

Po dokončení všeho výše:

1. `openclaw models status` — oba provideři mají auth
2. Otevři Claude Desktop → check že 10 scheduled tasks je vidět
3. Otevři Claude.ai → check že connectors jsou zapnuté
4. Spusť: `python3 /Users/josefhofman/Clawdia/scripts/cowork_bridge.py status`
5. Spusť: `bash /Users/josefhofman/Clawdia/scripts/system-status.sh`

Výsledky zapiš do: `/Users/josefhofman/Clawdia/collaboration/handoffs/claude/openclaw_setup_result.md`

---

**Máš plnou autonomii. Nastav všechno. Díky.**
