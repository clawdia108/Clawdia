# HEARTBEAT.md — Codex (System Builder)

## Active Cron Tasks
1. **Morning build sprint** (08:00 M-F) → scripts/, control-plane/ improvements
2. **Afternoon experiment** (14:00 M-F) → new features, integrations, tools
3. **Evening deploy + test** (19:00 M-F) → push, deploy to VPS, verify
4. **Weekend deep build** (Sat 10:00) → bigger features, architecture improvements

## Build Queue (auto-updated from IMPROVEMENT_PROPOSALS.md)
Check knowledge/IMPROVEMENT_PROPOSALS.md for latest proposals from KnowledgeKeeper.
Check reviews/HEALTH_REPORT.md for system issues to fix.
Check reviews/WEEKLY_REVIEW.md for architecture recommendations.

## Rules
- Every cron run MUST produce a commit (even if small)
- Test before push — run scripts locally first
- Never break existing agent cron functionality
- Implement book insights from knowledge/book-insights/ into actual code
- When building something new, check if a book has a framework for it first
- Push to GitHub after every successful build
- Deploy to VPS (git pull on 157.180.43.83) after push

## Fun Facts Protocol
When you discover something interesting during building/experimenting:
1. Write it to knowledge/FUN_FACTS.md with timestamp
2. Make it genuinely interesting — not "I updated a file"
3. Examples: "Pipedrive API can do X which saves Y", "Found that agent Z produces 3x better output when..."
