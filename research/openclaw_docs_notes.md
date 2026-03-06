# OpenClaw Docs Field Notes

_Last updated: 2026-03-06_

## Reading Plan & Coverage Checklist

| Area | Key Pages | Status |
|------|-----------|--------|
| Overview & Getting Started | `/index`, `/start/getting-started`, `/start/wizard`, `/web/control-ui` | ⏳ in progress |
| Core Concepts | Agent runtime/loop/workspace, gateway architecture, multi-agent routing, memory, messages, queue, retry, usage | ⏳ |
| Gateway Deep Dive | Configuration, security, remote access, tools invoke API, heartbeat, logging, sandboxing, secrets | ⏳ |
| Automation Stack | Cron vs heartbeat, hooks, webhooks, Gmail PubSub, auth monitoring, troubleshooting | ⏳ |
| CLI Surface | `openclaw` subcommands (status, gateway, agents, sessions, cron, browser, etc.) | ⏳ |
| Channels & Routing | WhatsApp, Telegram, Discord, Matrix, Slack, pairing, broadcast groups | ⏳ |
| Models & Providers | Model providers, model failover, local models, models CLI | ⏳ |
| Security & Reliability | Security guides, gateway lock, diagnostics, health checks | ⏳ |
| Experiments & Plans | ACP thread-bound agents, unified streaming refactor, process supervision, session binding | ⏳ |
| Install & Deploy | Node install, Docker, Ansible, remote gateway, development channels | ⏳ |

## Quick Notes from Initial Pass

- **OpenClaw = self-hosted gateway** that bridges chat apps (WhatsApp/Telegram/Discord/iMessage/etc.) with AI agents (Pi, Codex, Claude, etc.). Gateway routes sessions, enforces tool policy, and exposes CLI + browser dashboard.
- **Value props:** self-hosted (ownership), multi-channel (one gateway for all surfaces), agent-native (sessions, memory, multi-agent routing), open source (MIT).
- **Minimal requirements:** Node 22+, API key for chosen LLM provider, ~5 minutes to bring up gateway. Stronger models recommended for quality/safety.
- **High-level flow:** Chat apps → Gateway → Agents/CLIs/Web UI/macOS/iOS nodes. Gateway = single source of truth for sessions + channel connections.
- **Docs index:** `https://docs.openclaw.ai/llms.txt` enumerates >150 pages grouped into automation, channels, CLI, concepts, gateway, experiments, installation, troubleshooting, etc. This will serve as the crawl map for the deep dive.

## Next Actions

1. Systematically ingest concept pages (agent runtime/loop/workspace, architecture, multi-agent routing, memory, queue, retry, streaming, usage).
2. Document key interfaces (Tools Invoke API, OpenResponses API, Bridge protocol, CLI commands) for future architecture mapping.
3. Map automation + channel capabilities to Behavera’s multi-agent orchestration requirements (cron vs heartbeat, hooks, Gmail PubSub, Slack/Telegram specifics).
4. Track open questions + integration hooks as we go (e.g., how to tie Make.com + Claude memory into Gateway events).
