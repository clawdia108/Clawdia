# Agent Control Studio

Local operator console for the OpenClaw workspace.

## What it does

- reads live workspace files:
  - `../calendar/TODAY.md`
  - `../intel/DAILY-INTEL.md`
  - `../pipedrive/.pipeline_snapshot.json`
- exposes an Express API for those sources
- streams mock log events over WebSocket
- lets you trigger mocked agent runs from a single neobrutalist dashboard

## Run locally

```bash
pnpm install
pnpm server:dev
pnpm dev
```

Frontend:
- `http://localhost:5173`

Backend:
- `http://localhost:4310`

## Scripts

- `pnpm dev` — Vite frontend
- `pnpm server:dev` — Express + WebSocket backend via `tsx`
- `pnpm build` — typecheck + production frontend build
- `pnpm test` — Vitest suite
- `pnpm lint` — ESLint

## Notes

- `Cmd+Enter` triggers the run panel submit button.
- The WebSocket endpoint is `/ws/logs`.
- The backend uses in-memory run storage only.
- File change events from the workspace are pushed into the log stream through `chokidar`.
