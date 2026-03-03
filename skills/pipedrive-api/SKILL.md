---
name: pipedrive-api
description: Interact with Pipedrive CRM API for deal management, contact operations, activity tracking, scoring, and pipeline automation. Use when any agent needs to read or write CRM data.
tools: Bash
---

# Pipedrive API Skill

## Authentication
API token is in workspace secrets: `.secrets/pipedrive.env` → `$PIPEDRIVE_API_TOKEN`
Base URL: `https://api.pipedrive.com/v1/`
Instance: https://behavera.pipedrive.com

## Deep Knowledge
Full API reference: `knowledge/PIPEDRIVE_API_REFERENCE.md` (1500+ lines)
Pipeline analysis: `knowledge/PIPEDRIVE_PIPELINE_ANALYSIS.md`
Automation playbook: `knowledge/PIPEDRIVE_AUTOMATION_PLAYBOOK.md`

## Common Operations

### List open deals (paginated)
```bash
curl -s "https://api.pipedrive.com/v1/deals?api_token=$PIPEDRIVE_API_TOKEN&status=open&limit=100&start=0" | jq '.data[] | {id, title, status, stage_id, value, person_name: .person_id.name, org_name: .org_id.name, next_activity_date, last_activity_date}'
```

### Get deal details
```bash
curl -s "https://api.pipedrive.com/v1/deals/$DEAL_ID?api_token=$PIPEDRIVE_API_TOKEN" | jq '.data'
```

### Recent changes (last 30 min)
```bash
curl -s "https://api.pipedrive.com/v1/recents?api_token=$PIPEDRIVE_API_TOKEN&since_timestamp=$(date -u -v-30M +%Y-%m-%d%%20%H:%M:%S)&items=deal,person,activity" | jq '.data'
```

### Pipeline summary
```bash
curl -s "https://api.pipedrive.com/v1/deals/summary?api_token=$PIPEDRIVE_API_TOKEN&status=open" | jq '.data'
```

### Get all persons (contacts)
```bash
curl -s "https://api.pipedrive.com/v1/persons?api_token=$PIPEDRIVE_API_TOKEN&limit=100" | jq '.data[] | {id, name, email: .email[0].value, org_name: .org_id.name}'
```

### Get undone activities
```bash
curl -s "https://api.pipedrive.com/v1/activities?api_token=$PIPEDRIVE_API_TOKEN&done=0&limit=50" | jq '.data[] | {id, type, subject, due_date, deal_title: .deal_title, person_name}'
```

### Create follow-up activity
```bash
curl -X POST "https://api.pipedrive.com/v1/activities?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"type":"task","subject":"Follow-up needed","deal_id":DEAL_ID,"due_date":"YYYY-MM-DD","user_id":24403638}'
```

### Add note to deal
```bash
curl -X POST "https://api.pipedrive.com/v1/notes?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"content":"[PipelinePilot] Note text here","deal_id":DEAL_ID}'
```

### Update deal
```bash
curl -X PUT "https://api.pipedrive.com/v1/deals/$DEAL_ID?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status":"won"}'
```

### Search for anything
```bash
curl -s "https://api.pipedrive.com/v1/itemSearch?api_token=$PIPEDRIVE_API_TOKEN&term=SEARCH_TERM&item_types=deal,person,organization"
```

### Won/Lost deals (for pattern analysis)
```bash
curl -s "https://api.pipedrive.com/v1/deals?api_token=$PIPEDRIVE_API_TOKEN&status=won&limit=100"
curl -s "https://api.pipedrive.com/v1/deals?api_token=$PIPEDRIVE_API_TOKEN&status=lost&limit=100"
```

### Pipelines and stages
```bash
curl -s "https://api.pipedrive.com/v1/pipelines?api_token=$PIPEDRIVE_API_TOKEN"
curl -s "https://api.pipedrive.com/v1/stages?api_token=$PIPEDRIVE_API_TOKEN&pipeline_id=2"
```

### Custom deal fields
```bash
curl -s "https://api.pipedrive.com/v1/dealFields?api_token=$PIPEDRIVE_API_TOKEN&limit=100"
```

### Email templates (create shared)
```bash
curl -X POST "https://api.pipedrive.com/v1/mailbox/mailTemplates?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Template Name","subject":"Subject","content":"<p>HTML body</p>","shared_flag":"1"}'
```

## Pipeline IDs
- Sales Pipeline: 2 (main)
- Onboarding: 3
- Partnerships: 4
- Churned/Onetime: 5

## Rate Limits
- Token-budget per company/day (varies by plan)
- Burst: 80-300 req per 2-second window
- PUT/POST: ~10,000/day
- Search: 10 req/2s
- ALWAYS check: `X-RateLimit-Remaining` header
- On 429: wait `Retry-After` seconds

## Rules
- NEVER delete records without explicit human approval
- ALWAYS log operations to pipedrive/SCORING_LOG.md
- Search before creating to prevent duplicates
- Use Pipedrive entity IDs as idempotency keys
- Max 5 bulk operations without Josef's confirmation
