# Clawdia OS

Operations hub for Josef’s CRM growth system.

## Purpose
Build and iterate a practical operating system for:
- Keeping Pipedrive clean and alive
- Daily activity prioritization
- Morning/afternoon execution reporting
- Lead and deal scoring iterations
- Revenue-focused experiments

## Structure
- `playbooks/` – executable SOPs for daily/weekly work
- `dashboards/` – working dashboards, metrics definitions, scorecards
- `templates/` – reusable report and checklist templates
- `research/` – market/trend notes and opportunity analyses
- `experiments/` – hypotheses, tests, outcomes
- `control-plane/` – canonical agent registry and control-plane docs
- `tasks/` – structured task handoff layer

## Current focus
Target outcomes per 30 days:
- Primary: 20,000 EUR
- Floor: 13,000 EUR

## How to use
1. Start with `playbooks/daily-ops.md`
2. Create or update work in `tasks/open/*.json`
3. Run `python3 scripts/knowledge_sync.py`
4. Fill AM/PM report from `templates/am-pm-report.md`
5. Track improvements in `experiments/experiment-log.md`
