# AGENTS.md — PipelinePilot specifická pravidla

## Pipedrive integrace

Používej Pipedrive REST API:
- Base URL: https://api.pipedrive.com/v1/
- Auth: API token z secrets
- Rate limit: 30,000 tokenů/den, 80 req/2s burst

### Klíčové endpointy:
- `GET /deals` — seznam dealů
- `GET /persons` — kontakty
- `GET /activities` — aktivity
- `GET /recents` — změny za posledních X minut
- `PUT /deals/{id}` — update dealu
- `POST /activities` — vytvoření aktivity

## CRM Safety Rules
- HARD RULE: nikdy neupravovat Pipedrive aktivity/dealy/kontakty mimo záznamy vlastněné uživatelem Josef Hofman (user_id 24403638), pokud Josef explicitně neschválí výjimku.
- NIKDY nemazej data bez potvrzení
- VŽDY loguj operace do pipedrive/SCORING_LOG.md
- Před hromadnou operací (>5 záznamů) vyžádej potvrzení
