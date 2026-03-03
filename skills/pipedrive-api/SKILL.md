---
name: pipedrive-api
description: Interact with Pipedrive CRM API for deal management, contact operations, and activity tracking. Use when any agent needs to read or write CRM data.
tools: Bash
---

# Pipedrive API Skill

## Authentication
API token is in workspace secrets. Access via environment variable: $PIPEDRIVE_API_TOKEN
Base URL: https://api.pipedrive.com/v1/

## Common Operations

### List deals
```bash
curl -s "https://api.pipedrive.com/v1/deals?api_token=$PIPEDRIVE_API_TOKEN&status=open&limit=50" | jq '.data[] | {id, title, status, stage_id, value, person_name: .person_id.name}'
```

### Get deal details
```bash
curl -s "https://api.pipedrive.com/v1/deals/$DEAL_ID?api_token=$PIPEDRIVE_API_TOKEN" | jq '.data'
```

### List recent changes
```bash
curl -s "https://api.pipedrive.com/v1/recents?since_timestamp=$(date -d '30 minutes ago' +%Y-%m-%d%%20%H:%M:%S)&items=deal,person,activity&api_token=$PIPEDRIVE_API_TOKEN" | jq '.data'
```

### Get all persons (contacts)
```bash
curl -s "https://api.pipedrive.com/v1/persons?api_token=$PIPEDRIVE_API_TOKEN&limit=100" | jq '.data[] | {id, name, email: .email[0].value, org_name: .org_id.name}'
```

### Get activities
```bash
curl -s "https://api.pipedrive.com/v1/activities?api_token=$PIPEDRIVE_API_TOKEN&type=all&done=0&limit=50" | jq '.data[] | {id, type, subject, due_date, person_name}'
```

### Update deal
```bash
curl -X PUT "https://api.pipedrive.com/v1/deals/$DEAL_ID?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"status": "won"}'
```

## Rate Limits
- 30,000 tokens/day base
- 80-300 req per 2-second burst window
- PUT/POST limit: 10,000/day
- ALWAYS check rate limit headers: X-RateLimit-Remaining

## Rules
- NEVER delete records without explicit human approval
- ALWAYS log operations to pipedrive/SCORING_LOG.md
- Search before creating to prevent duplicates
- Use Pipedrive entity IDs as idempotency keys
