# Agent Control Studio — current state and next backlog

Tento soubor je aktuální podklad pro další Codex běhy v `agent-control-studio/`.

## Aktuální stav

Projekt už není scaffold. Teď už obsahuje:

- **Frontend (React + TS + Vite)**
  - dashboard v `src/App.tsx`
  - panely pro agents, pipeline, focus blocks, intel, live logs a reports
  - `RunPanel` s:
    - výběrem agenta
    - modelem (`Auto route` + manuální override)
    - task type
    - capabilities
    - promptem
    - overrides (`temperature`, `maxTokens`, `sandbox`)
  - `RoutingDrawer` pro session-only JSON konfiguraci
  - `ReportDrawer` + `JsonTree` pro detail run reportu
  - toasty a dark mode

- **Backend (Express + WebSocket)**
  - `GET /api/agents`
  - `GET /api/models`
  - `GET /api/session-config`
  - `PUT /api/session-config`
  - `GET /api/files/today`
  - `GET /api/files/intel`
  - `GET /api/pipeline`
  - `GET /api/reports`
  - `GET /api/reports/latest`
  - `GET /api/reports/:id`
  - `POST /api/run`
  - WebSocket `/ws/logs`

- **Data sources**
  - `../calendar/TODAY.md`
  - `../intel/DAILY-INTEL.md`
  - `../pipedrive/.pipeline_snapshot.json`
  - `../control-plane/model-router.json`
  - `../workspace/openclaw.model-routing.json`
  - `../control-plane/agent-registry.json`

- **Runtime execution**
  - `/api/run` už nepoužívá mock sequence
  - spouští skutečný lokální `openclaw agent --local --json`
  - výstup ukládá do in-memory report store
  - logy z běhu posílá do websocket feedu

## Důležité omezení

1. **Model override ve Studiu je advisory**
   - Studio umí route recommendation a auto-selection.
   - Samotný `openclaw agent` CLI ale momentálně jede s modelem nakonfigurovaným u runtime agenta.
   - Proto report ukazuje:
     - požadovaný route model
     - skutečný runtime model

2. **Runtime agent drift**
   - UI/control-plane používá:
     - `dealops`
     - `timebox`
   - OpenClaw runtime aktuálně používá:
     - `pipelinepilot`
     - `calendarcaptain`
   - V backendu je bridge mapování:
     - `dealops -> pipelinepilot`
     - `timebox -> calendarcaptain`

3. **Session config není perzistentní**
   - `PUT /api/session-config` ukládá změny jen do paměti backend procesu.

## Jak spustit

```bash
pnpm install
pnpm server:dev
pnpm dev
```

- frontend: `http://localhost:5173`
- backend: `http://localhost:4310`

## Co je hotové vůči původnímu záměru

- hotový read/write operator dashboard
- hotové live file panely
- hotový real log stream
- hotové session routing overrides
- hotový report gallery + drawer
- hotový export všech reportů do JSON
- hotové testy, lint, build

## Co zbývá jako další backlog

1. **True per-run model override**
   - zjistit, zda OpenClaw CLI/Gateway umí model override bez přepisování agent configu
   - pokud ano, dopojit skutečný runtime model selection místo advisory route

2. **Structured run presets**
   - uložit reusable playbook presets typu:
     - morning pipeline sweep
     - daily briefing
     - intel refresh
     - review pass

3. **Report persistence**
   - nenechávat reports jen v RAM
   - ukládat je do `agent-control-studio/data/` nebo do workspace knowledge/report složky

4. **Richer runtime telemetry**
   - přidat gateway health panel
   - přidat live status OpenClaw agentů
   - přidat token/cost counters z `agentMeta.usage`

5. **Safer runtime controls**
   - explicitní confirmation gate pro runy, které mohou vést k externím akcím
   - clear badge pro `safe read-only` vs `tool-using` run

## Pokud bude Codex pokračovat

Další nejlepší krok je:

1. zjistit skutečný per-run model override v OpenClaw CLI/Gateway
2. pokud neexistuje, přidat to do UI explicitně jako “route recommendation only”
3. udělat persistenci reportů a run history
