# Agent Control Studio

Local operator console for the OpenClaw workspace.

## What it does

- reads live workspace files:
  - `../calendar/TODAY.md`
  - `../intel/DAILY-INTEL.md`
  - `../pipedrive/.pipeline_snapshot.json`
- exposes an Express API for those sources and control-plane metadata
- streams runtime logs over WebSocket
- lets you trigger real local `openclaw agent --local` turns from a single neobrutalist dashboard
- shows route recommendation vs actual runtime model in reports

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
- `dealops` is bridged to runtime agent `pipelinepilot`.
- `timebox` is bridged to runtime agent `calendarcaptain`.
- Studio model routing is currently a recommendation layer; OpenClaw runtime may still execute with the agent's configured model.
