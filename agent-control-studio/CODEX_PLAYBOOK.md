# Agent Control Studio — Codex backlog

Tento soubor slouží jako podklad pro Codex/VS Code běh. Aktuální stav:

- Vite + React TS projekt je scaffoldnutý (`pnpm install` hotovo).
- Základní neobrutalist UI (panely Agents / Pipeline alerts / Activity log / Focus blocks) je v `src/App.tsx` + `App.css` + `index.css`.
- Zatím chybí backend, reálná data i interakce s gateway.

## Jak spustit lokálně
```bash
pnpm dev        # frontend na http://localhost:5173
pnpm server:dev # (až bude přidán Express server)
```

## Co má Codex dál vybudovat

1. **Backend (Express + WebSocket)**
   - V kořeni projektu vytvoř složku `server/` a soubor `server/index.ts`.
   - Použij `express`, `cors`, `ws`, `chokidar`, `yaml` nebo `gray-matter` podle potřeby.
   - Endpointy:
     - `GET /api/files/today` → vrátí data z `../calendar/TODAY.md`.
     - `GET /api/files/intel` → vrátí data z `../intel/DAILY-INTEL.md`.
     - `GET /api/pipeline` → načte `../pipedrive/.pipeline_snapshot.json` a vrátí agregované počty.
   - WebSocket `/ws/logs` → streamuje tail `openclaw logs` (prototypově zatím jen mockuj JSON zprávy).
   - Přidej skript `"server:dev": "tsx server/index.ts"` do `package.json` a potřebné dependencies (`express`, `cors`, `ws`, `chokidar`, `gray-matter`, `dotenv`).

2. **Data hooks na frontendu**
   - Vytvoř `src/lib/api.ts` s funkcemi `fetchToday()`, `fetchIntel()`, `fetchPipeline()`.
   - V `App.tsx` nahraď mock data real-time fetchem (použij React Query nebo vlastní `useEffect` + `useState`).
   - Zaved’ kontext `AgentContext` pro sdílení stavu (vybraný agent, logs, atd.).

3. **Log stream + command composer**
   - Komponenta `LogStream` připojí WebSocket a zobrazuje realtime zprávy.
   - Komponenta `RunPanel` → formulář (select agent, multiselect capability, textarea prompt) → POST na `/api/run` (zatím mockni).

4. **Styling & UX**
   - Přidej tmavý režim toggle.
   - Implementuj layout responsivní do 320px.
   - Přidej skeleton state pro fetch (pulsující placeholders).

5. **Testy & lint**
   - Přidej `vitest` + `@testing-library/react` a jednoduchý snapshot test pro `App`.

Feel free to iterovat – hlavní cíl: jediná obrazovka, kde vidím stavy agentů, pipeline alerts a můžu poslat prompt + sledovat logy.
