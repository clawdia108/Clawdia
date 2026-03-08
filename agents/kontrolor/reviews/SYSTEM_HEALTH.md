# System Health — 2026-03-03 17:30

## System Status
- Uptime: 2d 21h (load averages 1.45 / 1.93 / 2.71)
- CPU: 13.5% user · 13.7% sys · 72.8% idle
- RAM: 15 GB used / ~16 GB physical (1.9 GB wired, 5.8 GB compressed, 92 MB free)
- Disk: /System/Volumes/Data 263 GiB / 460 GiB (61%); / 11 GiB / 460 GiB (7%)

## Agent Quality Scores (1-5)
- InboxForge: 2/5 — Latest cron run (16:15) failed four times with `Connection error`, so no usable output.
- PipelinePilot: 2/5 — Cron job (16:00) missing `.secrets/pipedrive.env`, blocking automation.
- GrowthLab: 3/5 — No fresh artifacts in workspace to audit; last session 3h ago per `openclaw status`.
- CalendarCaptain: 3/5 — No new deliverables observed; health presumed stable.
- KnowledgeKeeper: 3/5 — No recent outputs in workspace; awaiting next sync.
- CopyAgent: 3/5 — No drafts in `drafts/`; idle since last check.

## Issues Found
- [CRITICAL] Open iMessage group policy with elevated/runtime tools exposed (per `openclaw status`). Fix: switch channels.imessage.groupPolicy to `allowlist`, tighten tool exposure, enable sandboxes.
- [CRITICAL] Telegram channel restarts + `getUpdates` 409 conflict at 16:28; indicates second bot instance. Ensure only one Telegram poller runs.
- [HIGH] PipelinePilot cron failing: missing `.secrets/pipedrive.env` prevents Pipedrive automation. Restore secret file or adjust job config before next run.
- [HIGH] InboxForge cron hitting repeated `Connection error` retries (16:15), so daily outbound drafts failed. Investigate network/API availability and rerun.
- [MEDIUM] OpenClaw update 2026.3.2 available. Schedule upgrade to pick up patches.

## Security
- Last check: 2026-03-03 17:30 (`openclaw status`)
- Notes: Security audit reports 3 critical findings (open group policy + elevated tools + iMessage exposure) and 1 warning (potential multi-user setup). No remediation logged yet.
