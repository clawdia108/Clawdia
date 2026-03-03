# Pipedrive API Reference — Sales Agent Operations Manual

> Complete reference for building AI sales automation agents on Pipedrive.
> Covers every major endpoint, practical patterns, and curl examples.
> Last updated: March 2026

---

## Table of Contents

1. [Authentication & Setup](#1-authentication--setup)
2. [Rate Limits & Pagination](#2-rate-limits--pagination)
3. [Deals](#3-deals)
4. [Persons (Contacts)](#4-persons-contacts)
5. [Organizations (Companies)](#5-organizations-companies)
6. [Activities (Calls, Meetings, Tasks)](#6-activities)
7. [Notes](#7-notes)
8. [Pipelines & Stages](#8-pipelines--stages)
9. [Filters](#9-filters)
10. [Products](#10-products)
11. [Leads](#11-leads)
12. [Files](#12-files)
13. [Users](#13-users)
14. [Webhooks](#14-webhooks)
15. [Goals](#15-goals)
16. [Recents (Changelog)](#16-recents)
17. [ItemSearch (Global Search)](#17-itemsearch)
18. [Custom Fields (DealFields / PersonFields / OrgFields)](#18-custom-fields)
19. [Mailbox (Email Tracking)](#19-mailbox)
20. [Call Logs](#20-call-logs)
21. [Activity Types](#21-activity-types)
22. [Lead Labels & Sources](#22-lead-labels--sources)
23. [Subscriptions & Revenue (Deprecated → Products/Installments)](#23-subscriptions--revenue)
24. [Common Patterns for Sales Agents](#24-common-patterns-for-sales-agents)

---

## 1. Authentication & Setup

### Base URL
```
https://api.pipedrive.com
```

### API Token Auth (simple, for internal tools)
Pass token in header:
```bash
curl -X GET "https://api.pipedrive.com/api/v2/deals" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN"
```

Or as query param (legacy, still works):
```bash
curl "https://api.pipedrive.com/v1/deals?api_token=$PIPEDRIVE_API_TOKEN"
```

### OAuth 2.0 (for marketplace apps)
- Token endpoint: `https://oauth.pipedrive.com/oauth/token`
- Auth endpoint: `https://oauth.pipedrive.com/oauth/authorize`
- Access token in header: `Authorization: Bearer {access_token}`
- Tokens expire — use `refresh_token` to renew
- Scopes: `deals:read`, `deals:full`, `activities:read`, `activities:full`, `contacts:read`, `contacts:full`, etc.

### API Versions
- **v2** — Current, preferred. Better performance, cursor pagination, lower token costs.
- **v1** — Legacy, some endpoints still v1-only. Being deprecated gradually.

This reference uses v2 endpoints where available, falls back to v1 where v2 doesn't exist yet.

---

## 2. Rate Limits & Pagination

### Token-Based Rate Limits
Each API call costs tokens (1-80 depending on endpoint complexity). Your daily budget:

```
Daily Budget = 30,000 base tokens × plan_multiplier × number_of_seats
```

Plan multipliers vary by tier (Essential < Advanced < Professional < Enterprise). When budget is exhausted, requests return `429 Too Many Requests` until next day reset.

### Burst Limits
- Per-token (per-user), rolling 2-second window
- Don't hammer the API — space requests ~200ms apart for safety

### Rate Limit Headers
Check these in every response:
- `X-RateLimit-Limit` — your limit
- `X-RateLimit-Remaining` — tokens left
- `X-RateLimit-Reset` — when it resets (epoch)
- `X-Daily-Requests-Left` — daily budget remaining

### Pagination

**Cursor-based (v2 endpoints):**
```bash
# First page
curl "https://api.pipedrive.com/api/v2/deals?limit=100" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN"

# Next page — use cursor from previous response
curl "https://api.pipedrive.com/api/v2/deals?limit=100&cursor=eyJpZCI6MTAwfQ" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN"
```

**Offset-based (v1 endpoints):**
```bash
# Page 1
curl "https://api.pipedrive.com/v1/notes?start=0&limit=100&api_token=$PIPEDRIVE_API_TOKEN"

# Page 2
curl "https://api.pipedrive.com/v1/notes?start=100&limit=100&api_token=$PIPEDRIVE_API_TOKEN"
```

- Default limit: 100
- Max limit: 500 (most endpoints), 100 (Files), 50 (CallLogs)
- Check `additional_data.pagination.more_items_in_collection` (v1) or `additional_data.next_cursor` (v2)

---

## 3. Deals

The core of Pipedrive. Deals = sales opportunities moving through your pipeline.

### List All Deals
```
GET /api/v2/deals
```
**Parameters:** `filter_id`, `ids`, `owner_id`, `person_id`, `org_id`, `pipeline_id`, `stage_id`, `status` (open/won/lost), `updated_since`, `updated_until`, `sort_by`, `sort_direction`, `include_fields`, `custom_fields`, `limit`, `cursor`

```bash
# Get all open deals in pipeline 1, owned by user 5
curl "https://api.pipedrive.com/api/v2/deals?status=open&pipeline_id=1&owner_id=5&limit=200" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN"
```

**Agent use:** Daily pipeline review, finding stale deals, monitoring deal flow.

### Get Archived Deals
```
GET /api/v2/deals/archived
```
Same params as above. Cost: 20 tokens.

### Get One Deal
```
GET /api/v2/deals/{id}
```
**Parameters:** `include_fields`, `custom_fields`

```bash
curl "https://api.pipedrive.com/api/v2/deals/42" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN"
```

### Search Deals
```
GET /api/v2/deals/search
```
**Parameters:** `term` (required, min 2 chars), `fields` (custom_fields/notes/title), `exact_match`, `person_id`, `organization_id`, `status`, `include_fields`, `limit`, `cursor`

```bash
# Find deals mentioning "enterprise" in title or notes
curl "https://api.pipedrive.com/api/v2/deals/search?term=enterprise&fields=title,notes" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN"
```

**Agent use:** Before creating a new deal, search to avoid duplicates.

### Create Deal
```
POST /api/v2/deals
```
**Required:** `title`
**Optional:** `owner_id`, `person_id`, `org_id`, `pipeline_id`, `stage_id`, `value`, `currency`, `status`, `probability`, `lost_reason`, `visible_to`, `expected_close_date`, `label_ids`, `custom_fields`

```bash
curl -X POST "https://api.pipedrive.com/api/v2/deals" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Acme Corp — Enterprise Plan",
    "person_id": 123,
    "org_id": 456,
    "pipeline_id": 1,
    "stage_id": 2,
    "value": 50000,
    "currency": "USD",
    "expected_close_date": "2026-04-15"
  }'
```

**Agent use:** Auto-create deals from qualified leads, inbound form submissions, or AI-identified opportunities.

### Update Deal
```
PATCH /api/v2/deals/{id}
```
Any deal field can be updated.

```bash
# Move deal to next stage + update value
curl -X PATCH "https://api.pipedrive.com/api/v2/deals/42" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"stage_id": 3, "value": 75000}'
```

**Agent use:** Auto-advance deals based on activity completion, update values after pricing calls.

### Delete Deal
```
DELETE /api/v2/deals/{id}
```

### Merge Deals
```
PUT /api/v2/deals/{id}/merge
```
Merges another deal into this one. Use when duplicates are found.

### Duplicate Deal
```
POST /v1/deals/{id}/duplicate
```

### Deals Summary (Pipeline Stats)
```
GET /v1/deals/summary
```
**Parameters:** `status`, `filter_id`, `user_id`, `pipeline_id`, `stage_id`

```bash
# Pipeline performance overview
curl "https://api.pipedrive.com/v1/deals/summary?pipeline_id=1&status=open&api_token=$PIPEDRIVE_API_TOKEN"
```
**Returns:** Total count, total value, weighted value, average value, per-currency breakdowns.

**Agent use:** Daily/weekly sales reports, pipeline health monitoring.

### Deals Timeline
```
GET /v1/deals/timeline
```
**Required:** `start_date` (YYYY-MM-DD), `interval` (day/week/month/quarter), `amount` (number of intervals), `field_key` (date field to use)
**Optional:** `user_id`, `pipeline_id`, `filter_id`, `exclude_deals`, `totals_convert_currency`

```bash
# Next 12 weeks of expected closes
curl "https://api.pipedrive.com/v1/deals/timeline?start_date=2026-03-01&interval=week&amount=12&field_key=expected_close_date&api_token=$PIPEDRIVE_API_TOKEN"
```

**Agent use:** Revenue forecasting, close date analysis, pipeline velocity tracking.

### Deal Sub-Resources

| Endpoint | Method | What it gives you |
|----------|--------|-------------------|
| `/api/v2/deals/{id}/products` | GET | Products attached to deal |
| `/v1/deals/{id}/activities` | GET | Activities on deal |
| `/v1/deals/{id}/flow` | GET | Full update history (changelog) |
| `/v1/deals/{id}/changelog` | GET | Field-level change log |
| `/v1/deals/{id}/files` | GET | Attached files |
| `/v1/deals/{id}/mailMessages` | GET | Email threads linked to deal |
| `/v1/deals/{id}/participants` | GET | People involved |
| `/api/v2/deals/{id}/followers` | GET | Users following the deal |
| `/v1/deals/{id}/permittedUsers` | GET | Who can see this deal |
| `/api/v2/deals/{id}/discounts` | GET | Deal discounts |
| `/api/v2/deals/installments` | GET | Billing installments (needs `deal_ids`) |

### Deal Participant Management
```bash
# Add participant
curl -X POST "https://api.pipedrive.com/v1/deals/42/participants?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"person_id": 789}'

# Remove participant
curl -X DELETE "https://api.pipedrive.com/v1/deals/42/participants/789?api_token=$PIPEDRIVE_API_TOKEN"
```

### Deal Product Management
```bash
# Attach product to deal
curl -X POST "https://api.pipedrive.com/api/v2/deals/42/products" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": 10,
    "item_price": 999.99,
    "quantity": 5,
    "discount": 10,
    "discount_type": "percentage"
  }'

# Bulk add products (up to 100)
curl -X POST "https://api.pipedrive.com/api/v2/deals/42/products/bulk" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"data": [{"product_id": 10, "item_price": 999, "quantity": 1}, {"product_id": 11, "item_price": 499, "quantity": 2}]}'
```

### Convert Deal to Lead
```
POST /api/v2/deals/{id}/convert
```
Async operation — poll status with:
```
GET /api/v2/deals/{id}/convert/status/{conversion_id}
```

---

## 4. Persons (Contacts)

Persons = individual people. The humans you're selling to.

### List All Persons
```
GET /api/v2/persons
```
**Parameters:** `filter_id`, `ids`, `owner_id`, `org_id`, `deal_id`, `updated_since`, `updated_until`, `sort_by`, `sort_direction`, `include_fields`, `custom_fields`, `limit`, `cursor`

```bash
# All contacts at org 456
curl "https://api.pipedrive.com/api/v2/persons?org_id=456" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN"
```

### Get One Person
```
GET /api/v2/persons/{id}
```

### Search Persons
```
GET /api/v2/persons/search
```
**Parameters:** `term` (required), `fields` (custom_fields/email/name/notes/phone), `exact_match`, `organization_id`, `include_fields`, `limit`, `cursor`

```bash
# Search by email
curl "https://api.pipedrive.com/api/v2/persons/search?term=john@acme.com&fields=email&exact_match=true" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN"
```

**Agent use:** Deduplicate contacts before creation. Look up contacts from inbound emails.

### Create Person
```
POST /api/v2/persons
```
**Parameters:** `name`, `owner_id`, `org_id`, `emails` (array), `phones` (array), `visible_to`, `label_ids`, `marketing_status`, `custom_fields`

```bash
curl -X POST "https://api.pipedrive.com/api/v2/persons" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "John Smith",
    "org_id": 456,
    "emails": [{"value": "john@acme.com", "label": "work", "primary": true}],
    "phones": [{"value": "+14155551234", "label": "work", "primary": true}],
    "marketing_status": "subscribed"
  }'
```

### Update Person
```
PATCH /api/v2/persons/{id}
```

### Merge Persons
```
PUT /v1/persons/{id}/merge
```
**Required:** `merge_with_id` — the person to merge into this one.

```bash
curl -X PUT "https://api.pipedrive.com/v1/persons/100/merge?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"merge_with_id": 101}'
```

**Agent use:** Automatic deduplication after finding matches.

### Delete Person
```
DELETE /api/v2/persons/{id}
```

### Person Sub-Resources

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/persons/{id}/activities` | GET | Activities with this person |
| `/v1/persons/{id}/deals` | GET | All deals involving this person |
| `/v1/persons/{id}/files` | GET | Attached files |
| `/v1/persons/{id}/flow` | GET | Full update history |
| `/v1/persons/{id}/changelog` | GET | Field change log |
| `/api/v2/persons/{id}/followers` | GET | Users following |
| `/v1/persons/{id}/mailMessages` | GET | Email threads |
| `/v1/persons/{id}/permittedUsers` | GET | Access permissions |
| `/api/v2/persons/{id}/picture` | GET | Profile picture URLs |
| `/v1/persons/{id}/products` | GET | Products associated |

### Person Picture
```bash
# Upload picture
curl -X POST "https://api.pipedrive.com/v1/persons/123/picture?api_token=$PIPEDRIVE_API_TOKEN" \
  -F "file=@photo.jpg" \
  -F "crop_x=0" -F "crop_y=0" -F "crop_width=200" -F "crop_height=200"
```

---

## 5. Organizations (Companies)

Organizations = companies that persons belong to.

### List All Organizations
```
GET /api/v2/organizations
```
**Parameters:** `filter_id`, `ids`, `owner_id`, `updated_since`, `updated_until`, `sort_by`, `sort_direction`, `include_fields`, `custom_fields`, `limit`, `cursor`

### Get One Organization
```
GET /api/v2/organizations/{id}
```

### Search Organizations
```
GET /api/v2/organizations/search
```
**Parameters:** `term` (required), `fields` (address/custom_fields/name/notes), `exact_match`, `limit`, `cursor`

```bash
curl "https://api.pipedrive.com/api/v2/organizations/search?term=Acme" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN"
```

### Create Organization
```
POST /api/v2/organizations
```
**Parameters:** `name`, `owner_id`, `visible_to`, `label_ids`, `address`, `custom_fields`

```bash
curl -X POST "https://api.pipedrive.com/api/v2/organizations" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Acme Corporation",
    "address": "123 Main St, San Francisco, CA",
    "owner_id": 1
  }'
```

### Update Organization
```
PATCH /api/v2/organizations/{id}
```

### Merge Organizations
```
PUT /v1/organizations/{id}/merge
```
**Required:** `merge_with_id`

### Delete Organization
```
DELETE /api/v2/organizations/{id}
```

### Organization Sub-Resources

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/organizations/{id}/activities` | GET | Activities linked to org |
| `/v1/organizations/{id}/deals` | GET | All deals (params: `status`, `only_primary_association`) |
| `/v1/organizations/{id}/persons` | GET | People at this org |
| `/v1/organizations/{id}/files` | GET | Attached files |
| `/v1/organizations/{id}/flow` | GET | Update history |
| `/v1/organizations/{id}/changelog` | GET | Field changes |
| `/api/v2/organizations/{id}/followers` | GET | Following users |
| `/v1/organizations/{id}/mailMessages` | GET | Email threads |
| `/v1/organizations/{id}/permittedUsers` | GET | Access permissions |

**Agent use:** When a new company is mentioned in a call, search first, create if not found, then link to person and deal.

---

## 6. Activities

Activities = calls, meetings, emails, tasks, deadlines. The action layer of the CRM.

### List All Activities
```
GET /api/v2/activities
```
**Parameters:** `filter_id`, `ids`, `owner_id`, `deal_id`, `lead_id`, `person_id`, `org_id`, `done` (boolean), `updated_since`, `updated_until`, `sort_by` (id/update_time/add_time/due_date), `sort_direction`, `include_fields` (attendees), `limit`, `cursor`

```bash
# Undone activities for user 5, sorted by due date
curl "https://api.pipedrive.com/api/v2/activities?owner_id=5&done=false&sort_by=due_date&sort_direction=asc" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN"
```

**Agent use:** Daily task list, overdue activity alerts, follow-up scheduling.

### Get One Activity
```
GET /api/v2/activities/{id}
```

### Create Activity
```
POST /api/v2/activities
```
**Parameters:** `subject`, `type` (call/meeting/task/email/lunch/deadline or custom), `owner_id`, `deal_id`, `lead_id`, `person_id`, `org_id`, `project_id`, `due_date`, `due_time`, `duration` (HH:MM), `busy` (boolean), `done` (boolean), `location` (object), `participants` (array of person_id), `attendees` (array), `public_description`, `priority`, `note`

```bash
# Schedule a follow-up call
curl -X POST "https://api.pipedrive.com/api/v2/activities" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subject": "Follow-up call with John",
    "type": "call",
    "deal_id": 42,
    "person_id": 123,
    "due_date": "2026-03-05",
    "due_time": "14:00",
    "duration": "00:30",
    "note": "Discuss pricing and timeline"
  }'
```

**Agent use:** Auto-schedule follow-ups after calls, create reminder tasks, log completed activities.

### Update Activity
```
PATCH /api/v2/activities/{id}
```

```bash
# Mark activity as done
curl -X PATCH "https://api.pipedrive.com/api/v2/activities/999" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"done": true}'
```

### Delete Activity
```
DELETE /api/v2/activities/{id}
```
Soft delete — permanent after 30 days.

---

## 7. Notes

HTML-formatted text attached to deals, persons, organizations, leads, or projects.

### List All Notes
```
GET /v1/notes
```
**Parameters:** `user_id`, `lead_id`, `deal_id`, `person_id`, `org_id`, `project_id`, `start`, `limit`, `sort`, `start_date`, `end_date`, `updated_since`, `pinned_to_lead_flag`, `pinned_to_deal_flag`, `pinned_to_organization_flag`, `pinned_to_person_flag`, `pinned_to_project_flag`

```bash
# All notes on deal 42
curl "https://api.pipedrive.com/v1/notes?deal_id=42&api_token=$PIPEDRIVE_API_TOKEN"
```

### Get One Note
```
GET /v1/notes/{id}
```

### Create Note
```
POST /v1/notes
```
**Required:** `content` (HTML string) + at least one of: `deal_id`, `person_id`, `org_id`, `lead_id`, `project_id`
**Optional:** `user_id`, `add_time`, `pinned_to_*_flag` (0 or 1)

```bash
# Add call summary note to a deal
curl -X POST "https://api.pipedrive.com/v1/notes?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "<h3>Call Summary — March 3, 2026</h3><p>Spoke with John about enterprise pricing. Key points:</p><ul><li>Budget approved for Q2</li><li>Needs SSO integration</li><li>Decision by March 15</li></ul>",
    "deal_id": 42,
    "person_id": 123,
    "pinned_to_deal_flag": 1
  }'
```

**Agent use:** Auto-log call summaries, meeting notes, AI-generated insights. Pin important notes to deals.

### Update Note
```
PUT /v1/notes/{id}
```

### Delete Note
```
DELETE /v1/notes/{id}
```

### Note Comments
```
GET    /v1/notes/{id}/comments              — List all comments
GET    /v1/notes/{id}/comments/{commentId}   — Get one comment
POST   /v1/notes/{id}/comments              — Add comment (body: content)
PUT    /v1/notes/{id}/comments/{commentId}   — Update comment
DELETE /v1/notes/{id}/comments/{commentId}   — Delete comment
```

---

## 8. Pipelines & Stages

Pipelines define your sales process. Stages are the steps within each pipeline.

### Pipelines

```
GET    /api/v2/pipelines                — List all pipelines
GET    /api/v2/pipelines/{id}           — Get one pipeline
POST   /api/v2/pipelines               — Create pipeline (name required)
PATCH  /api/v2/pipelines/{id}           — Update pipeline
DELETE /api/v2/pipelines/{id}           — Delete pipeline
```

**Create params:** `name` (required), `is_deal_probability_enabled`

```bash
curl -X POST "https://api.pipedrive.com/api/v2/pipelines" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Enterprise Sales", "is_deal_probability_enabled": true}'
```

### Pipeline Analytics
```
GET /v1/pipelines/{id}/conversion_statistics
```
**Parameters:** `start_date`, `end_date`, `user_id`
**Returns:** Stage-to-stage conversion rates, pipeline-to-close rates.

```
GET /v1/pipelines/{id}/movement_statistics
```
**Parameters:** `start_date`, `end_date`, `user_id`
**Returns:** Deal movement stats between stages.

**Agent use:** Weekly pipeline health reports, identifying bottleneck stages.

### Stages

```
GET    /api/v2/stages                    — List all stages (filter by pipeline_id)
GET    /api/v2/stages/{id}               — Get one stage
POST   /api/v2/stages                    — Create stage
PATCH  /api/v2/stages/{id}               — Update stage
DELETE /api/v2/stages/{id}               — Delete stage
```

**Create params:** `name` (required), `pipeline_id` (required), `deal_probability`, `is_deal_rot_enabled`, `days_to_rotten`

```bash
# Create stage with deal rot detection (flag stale deals after 14 days)
curl -X POST "https://api.pipedrive.com/api/v2/stages" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Proposal Sent",
    "pipeline_id": 1,
    "deal_probability": 50,
    "is_deal_rot_enabled": true,
    "days_to_rotten": 14
  }'
```

### Get Deals in a Stage (v1, deprecated)
```
GET /v1/stages/{id}/deals
```
**Parameters:** `filter_id`, `user_id`, `everyone` (0 or 1), `start`, `limit`

Better alternative: `GET /api/v2/deals?stage_id={id}`

---

## 9. Filters

Saved filter conditions for querying deals, persons, orgs, activities, leads, products, projects.

### Endpoints
```
GET    /v1/filters              — List all filters (optional: type param)
GET    /v1/filters/{id}         — Get one filter
GET    /v1/filters/helpers      — Get available conditions & operators
POST   /v1/filters              — Create filter
PUT    /v1/filters/{id}         — Update filter
DELETE /v1/filters/{id}         — Delete single filter
DELETE /v1/filters?ids=1,2,3    — Bulk delete
```

### Filter Types
`deals`, `leads`, `org`, `people`, `products`, `activity`, `projects`

### Condition Format
```json
{
  "glue": "and",
  "conditions": [
    {
      "glue": "and",
      "conditions": [
        {
          "object": "deal",
          "field_id": "stage_id",
          "operator": "=",
          "value": "3"
        },
        {
          "object": "deal",
          "field_id": "value",
          "operator": ">=",
          "value": "10000"
        }
      ]
    }
  ]
}
```

### Supported Operators
`=`, `!=`, `<`, `>`, `<=`, `>=`, `IS NULL`, `IS NOT NULL`, `LIKE '$%'` (starts with), `LIKE '%$%'` (contains), `NOT LIKE '$%'`

**Max 16 conditions per filter.** Date values: `YYYY-MM-DD`.

```bash
# Create a filter for high-value open deals in proposal stage
curl -X POST "https://api.pipedrive.com/v1/filters?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "High Value Proposals",
    "type": "deals",
    "conditions": {
      "glue": "and",
      "conditions": [{
        "glue": "and",
        "conditions": [
          {"object": "deal", "field_id": "stage_id", "operator": "=", "value": "3"},
          {"object": "deal", "field_id": "value", "operator": ">=", "value": "10000"},
          {"object": "deal", "field_id": "status", "operator": "=", "value": "open"}
        ]
      }]
    }
  }'
```

**Agent use:** Create filters programmatically, then use `filter_id` parameter when listing deals/persons/activities for targeted queries.

---

## 10. Products

Products/services you sell. Can be attached to deals with pricing, quantity, discounts.

### Endpoints
```
GET    /api/v2/products                             — List all products
GET    /api/v2/products/{id}                        — Get one product
GET    /api/v2/products/search                      — Search products
POST   /api/v2/products                             — Create product
PATCH  /api/v2/products/{id}                        — Update product
DELETE /api/v2/products/{id}                        — Delete product
POST   /api/v2/products/{id}/duplicate              — Duplicate product
```

**Create params:** `name` (required), `code`, `description`, `unit`, `tax`, `category`, `owner_id`, `is_linkable`, `visible_to`, `prices` (array with currency/price/cost/overhead), `custom_fields`, `billing_frequency` (one-time/annually/semi-annually/quarterly/monthly/weekly), `billing_frequency_cycles`

```bash
curl -X POST "https://api.pipedrive.com/api/v2/products" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Enterprise License",
    "code": "ENT-001",
    "prices": [{"currency": "USD", "price": 999, "cost": 200}],
    "billing_frequency": "monthly",
    "unit": "seat"
  }'
```

### Product Sub-Resources

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/products/{id}/deals` | GET | Deals using this product |
| `/v1/products/{id}/files` | GET | Attached files |
| `/api/v2/products/{id}/followers` | GET | Following users |
| `/v1/products/{id}/permittedUsers` | GET | Access permissions |
| `/api/v2/products/{id}/variations` | GET/POST/PATCH/DELETE | Product variations (sizes, tiers) |
| `/api/v2/products/{id}/images` | GET/POST/PUT/DELETE | Product images |

---

## 11. Leads

Pre-deal stage. Leads are unqualified opportunities that convert into deals.

### Endpoints
```
GET    /v1/leads                  — List active leads
GET    /v1/leads/archived         — List archived leads
GET    /v1/leads/{id}             — Get one lead (UUID)
GET    /api/v2/leads/search       — Search leads
POST   /v1/leads                  — Create lead
PATCH  /v1/leads/{id}             — Update lead
DELETE /v1/leads/{id}             — Delete lead permanently
```

**Create params (required):** `title` + (`person_id` OR `organization_id`)
**Optional:** `owner_id`, `label_ids`, `value` (object: amount + currency), `expected_close_date`, `visible_to`, `was_seen`

**Filtering:** `owner_id`, `person_id`, `organization_id`, `filter_id`, `sort`

```bash
# Create a lead
curl -X POST "https://api.pipedrive.com/v1/leads?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Inbound — website form",
    "person_id": 123,
    "organization_id": 456,
    "label_ids": ["hot-lead-label-uuid"],
    "value": {"amount": 5000, "currency": "USD"}
  }'
```

### Convert Lead to Deal
```
POST /api/v2/leads/{id}/convert/deal
```
Async operation. Poll status:
```
GET /api/v2/leads/{id}/convert/status/{conversion_id}
```
**Status values:** `not_started`, `running`, `completed`, `failed`, `rejected`

```bash
# Convert lead to deal
curl -X POST "https://api.pipedrive.com/api/v2/leads/abc-123-uuid/convert/deal" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

**Agent use:** Triage inbound leads, auto-qualify based on criteria, convert to deals when ready.

### Permitted Users
```
GET /v1/leads/{id}/permittedUsers
```

---

## 12. Files

Attach files to deals, persons, orgs, activities, leads, products.

### Endpoints
```
GET    /v1/files                      — List all files
GET    /v1/files/{id}                 — Get file metadata
GET    /v1/files/{id}/download        — Download file (binary)
POST   /v1/files                      — Upload file
POST   /v1/files/remote               — Create Google Drive file & link
POST   /v1/files/remoteLink           — Link existing remote file
PUT    /v1/files/{id}                 — Update file (name, description)
DELETE /v1/files/{id}                 — Delete file
```

```bash
# Upload file and attach to deal
curl -X POST "https://api.pipedrive.com/v1/files?api_token=$PIPEDRIVE_API_TOKEN" \
  -F "file=@proposal.pdf" \
  -F "deal_id=42"

# Link Google Doc to a deal
curl -X POST "https://api.pipedrive.com/v1/files/remote?api_token=$PIPEDRIVE_API_TOKEN" \
  -d "file_type=gdoc&title=Proposal Draft&item_type=deal&item_id=42&remote_location=googledrive"
```

**Remote file types:** `gdoc`, `gslides`, `gsheet`, `gform`, `gdraw`

**Agent use:** Attach proposals, contracts, call recordings to deals.

---

## 13. Users

Team members in your Pipedrive account.

### Endpoints
```
GET  /v1/users                        — List all users
GET  /v1/users/me                     — Current authenticated user
GET  /v1/users/{id}                   — Get one user
GET  /v1/users/find                   — Search by name/email
GET  /api/v2/users/{id}/followers     — User followers
GET  /v1/users/{id}/permissions       — User permissions
GET  /v1/users/{id}/roleAssignments   — Role assignments
GET  /v1/users/{id}/roleSettings      — Role settings
POST /v1/users                        — Add user (email, access required)
PUT  /v1/users/{id}                   — Update user (active_flag only)
```

```bash
# Get current user info
curl "https://api.pipedrive.com/v1/users/me?api_token=$PIPEDRIVE_API_TOKEN"

# Find user by email
curl "https://api.pipedrive.com/v1/users/find?term=john@company.com&search_by_email=1&api_token=$PIPEDRIVE_API_TOKEN"
```

**Agent use:** Look up owner IDs for deal assignment, check permissions before operations.

---

## 14. Webhooks

Real-time push notifications when data changes in Pipedrive. Essential for reactive automations.

### Endpoints
```
GET    /v1/webhooks          — List all webhooks
POST   /v1/webhooks          — Create webhook
DELETE /v1/webhooks/{id}     — Delete webhook
```

### Create Webhook
**Required:** `subscription_url`, `event_action`, `event_object`, `name`

**event_action values:** `create`, `change`, `delete`, `*` (all)
**event_object values:** `activity`, `deal`, `lead`, `note`, `organization`, `person`, `pipeline`, `product`, `stage`, `user`, `*` (all)

**Optional:** `user_id`, `http_auth_user`, `http_auth_password`, `version` (1.0 or 2.0, default: 2.0)

```bash
# Notify when any deal changes
curl -X POST "https://api.pipedrive.com/v1/webhooks?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subscription_url": "https://your-agent.com/webhook/deal-change",
    "event_action": "change",
    "event_object": "deal",
    "name": "Deal Change Monitor"
  }'

# Notify on all events (wildcard)
curl -X POST "https://api.pipedrive.com/v1/webhooks?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "subscription_url": "https://your-agent.com/webhook/all",
    "event_action": "*",
    "event_object": "*",
    "name": "Catch All"
  }'
```

### Important Notes
- **Max 40 webhooks per user**
- **v2 is now default** (since March 2025). v1 webhooks still work but will be deprecated in 2026.
- Webhook payload includes `current` and `previous` data for change events
- Your endpoint must respond with 2xx within 10 seconds or it's considered failed
- After repeated failures, webhook gets deactivated

**Agent use:** Trigger follow-up sequences on deal stage change, notify Slack on new deals, sync data to external systems, trigger AI analysis on new notes.

---

## 15. Goals

Sales targets and tracking.

### Endpoints
```
GET    /v1/goals/find            — Search goals
GET    /v1/goals/{id}/results    — Get goal progress
POST   /v1/goals                 — Create goal
PUT    /v1/goals/{id}            — Update goal
DELETE /v1/goals/{id}            — Delete goal
```

### Goal Types
- `deals_won` — Won deals count/value
- `deals_progressed` — Deals moved to a stage
- `activities_completed` — Completed activities
- `activities_added` — New activities created
- `deals_started` — New deals created

### Create Goal
```bash
curl -X POST "https://api.pipedrive.com/v1/goals?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Q2 Revenue Target",
    "assignee": {"id": 1, "type": "person"},
    "type": {"name": "deals_won", "params": {"pipeline_id": [1]}},
    "expected_outcome": {"target": 100000, "tracking_metric": "sum", "currency_id": 1},
    "duration": {"start": "2026-04-01", "end": "2026-06-30"},
    "interval": "monthly"
  }'
```

### Check Goal Progress
```bash
curl "https://api.pipedrive.com/v1/goals/abc123/results?period.start=2026-04-01&period.end=2026-06-30&api_token=$PIPEDRIVE_API_TOKEN"
```

**Goal intervals:** `weekly`, `monthly`, `quarterly`, `yearly`
**Assignee types:** `person` (user), `company`, `team`

**Agent use:** Daily goal progress reports, alert when falling behind, celebrate when targets are hit.

---

## 16. Recents

What changed recently across your entire Pipedrive account. A single endpoint changelog.

### Endpoint
```
GET /v1/recents
```
**Required:** `since_timestamp` (YYYY-MM-DD HH:MM:SS in UTC)
**Optional:** `items` (comma-separated types), `start`, `limit`

**Supported item types:** `activity`, `activityType`, `deal`, `file`, `filter`, `note`, `person`, `organization`, `pipeline`, `product`, `stage`, `user`

```bash
# Everything changed in the last hour
curl "https://api.pipedrive.com/v1/recents?since_timestamp=2026-03-03+12:00:00&api_token=$PIPEDRIVE_API_TOKEN"

# Only deal and person changes since yesterday
curl "https://api.pipedrive.com/v1/recents?since_timestamp=2026-03-02+00:00:00&items=deal,person&api_token=$PIPEDRIVE_API_TOKEN"
```

**Response includes:** Item type, ID, and full data object for each changed item. Pagination via `last_timestamp_on_page`.

**Agent use:** Polling-based sync (alternative to webhooks), daily change digest, audit trail.

---

## 17. ItemSearch

Global search across all entity types. The "search everything" endpoint.

### Search Across Types
```
GET /api/v2/itemSearch
```
**Required:** `term` (min 2 chars)
**Optional:** `item_types`, `fields`, `search_for_related_items`, `exact_match`, `include_fields`, `limit` (max 100), `cursor`

**Searchable item types:** `deal`, `person`, `organization`, `product`, `lead`, `file`, `mail_attachment`, `project`

**Searchable fields per type:**

| Type | Fields |
|------|--------|
| Deal | custom_fields, notes, title |
| Person | custom_fields, email, name, notes, phone |
| Organization | address, custom_fields, name, notes |
| Product | code, custom_fields, name |
| Lead | custom_fields, notes, title |
| File | name |
| Mail attachment | name |
| Project | custom_fields, notes, title, description |

```bash
# Search everything for "Acme"
curl "https://api.pipedrive.com/api/v2/itemSearch?term=Acme&item_types=deal,person,organization" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN"
```

### Search by Specific Field
```
GET /api/v2/itemSearch/field
```
**Required:** `term`, `entity_type`, `field`
**Optional:** `match` (exact/beginning/middle), `limit` (max 500), `cursor`

```bash
# Find all persons with phone starting with +1415
curl "https://api.pipedrive.com/api/v2/itemSearch/field?term=%2B1415&entity_type=person&field=phone&match=beginning" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN"
```

**Agent use:** Universal search before creating anything (dedup check), find related entities, power a conversational CRM interface.

---

## 18. Custom Fields (DealFields / PersonFields / OrgFields)

Every entity in Pipedrive has system fields + custom fields. Custom fields let you track anything specific to your business.

### Endpoints (same pattern for Deal/Person/Org fields)

**DealFields:**
```
GET    /api/v2/dealFields                              — List all
GET    /api/v2/dealFields/{field_code}                 — Get one
POST   /api/v2/dealFields                              — Create
POST   /api/v2/dealFields/{field_code}/options          — Add options (enum/set)
PATCH  /api/v2/dealFields/{field_code}                 — Update
PATCH  /api/v2/dealFields/{field_code}/options          — Update options
DELETE /api/v2/dealFields/{field_code}                 — Delete one
DELETE /v1/dealFields?ids=1,2,3                        — Bulk delete
DELETE /api/v2/dealFields/{field_code}/options          — Delete options
```

**PersonFields:** Same pattern at `/api/v2/personFields`
**OrganizationFields:** Same pattern at `/api/v2/organizationFields`

### Field Types
`varchar` (text), `text` (long text), `double` (number), `monetary` (money), `date`, `daterange`, `time`, `timerange`, `enum` (single select), `set` (multi select), `address`, `phone`, `user`, `org`, `people`, `varchar_auto` (autocomplete)

### Create Custom Field
```bash
# Create a "Lead Source" dropdown on deals
curl -X POST "https://api.pipedrive.com/api/v2/dealFields" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "field_name": "Lead Source",
    "field_type": "enum",
    "options": [
      {"label": "Website"},
      {"label": "Cold Call"},
      {"label": "Referral"},
      {"label": "Conference"},
      {"label": "LinkedIn"}
    ]
  }'
```

### Using Custom Fields in Records
Custom fields are referenced by their `field_key` (e.g., `abc123_lead_source_42` or a hash key). When creating/updating deals, persons, or orgs, pass custom field values in the `custom_fields` object:

```bash
# Update deal with custom field values
curl -X PATCH "https://api.pipedrive.com/api/v2/deals/42" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "custom_fields": {
      "abc123_lead_source_42": "Website",
      "def456_score_99": 85
    }
  }'
```

### Retrieving Custom Fields Efficiently
When fetching entities, pass `custom_fields` param to get only the fields you need (max 15 keys):
```bash
curl "https://api.pipedrive.com/api/v2/deals/42?custom_fields=abc123_lead_source_42,def456_score_99" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN"
```

### Field Metadata
Each field response includes: `field_key`, `field_name`, `field_type`, `options` (for enum/set), `mandatory_flag`, `edit_flag`, `add_visible_flag`.

**Agent use:** Read field definitions on startup to know the schema. Map external data to custom fields. Create fields programmatically for new integrations.

---

## 19. Mailbox

Email tracking — read synced emails linked to deals and contacts.

### Endpoints
```
GET /v1/mailbox/mailThreads                       — List threads (by folder)
GET /v1/mailbox/mailThreads/{id}                  — Get one thread
GET /v1/mailbox/mailThreads/{id}/mailMessages     — Get messages in thread
GET /v1/mailbox/mailMessages/{id}                 — Get one message
PUT /v1/mailbox/mailThreads/{id}                  — Update thread
DELETE /v1/mailbox/mailThreads/{id}               — Delete thread
```

### List Threads
```bash
# Get inbox threads
curl "https://api.pipedrive.com/v1/mailbox/mailThreads?folder=inbox&api_token=$PIPEDRIVE_API_TOKEN"
```
**Folder values:** `inbox`, `drafts`, `sent`, `archive`

### Read a Message with Body
```bash
curl "https://api.pipedrive.com/v1/mailbox/mailMessages/123?include_body=1&api_token=$PIPEDRIVE_API_TOKEN"
```

### Link Thread to Deal
```bash
curl -X PUT "https://api.pipedrive.com/v1/mailbox/mailThreads/456?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"deal_id": 42, "shared_flag": 1}'
```

**Update params:** `deal_id`, `lead_id`, `shared_flag` (0/1), `read_flag` (0/1), `archived_flag` (0/1)

**Agent use:** Scan incoming emails for deal mentions, auto-link threads, extract action items from email bodies.

---

## 20. Call Logs

Log phone calls and attach recordings. Separate from activities — more structured call data.

### Endpoints
```
GET    /v1/callLogs                     — List all call logs (max 50/page)
GET    /v1/callLogs/{id}                — Get one call log
POST   /v1/callLogs                     — Create call log
POST   /v1/callLogs/{id}/recordings     — Attach audio recording
DELETE /v1/callLogs/{id}                — Delete call log
```

### Create Call Log
**Required:** `to_phone_number`, `outcome`, `start_time`, `end_time`
**Optional:** `user_id`, `activity_id`, `subject`, `duration`, `from_phone_number`, `person_id`, `org_id`, `deal_id`, `lead_id`, `note`

**Outcome values:** `connected`, `no_answer`, `left_message`, `left_voicemail`, `wrong_number`, `busy`

```bash
# Log a completed call
curl -X POST "https://api.pipedrive.com/v1/callLogs?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to_phone_number": "+14155551234",
    "from_phone_number": "+14155559999",
    "outcome": "connected",
    "start_time": "2026-03-03 14:00:00",
    "end_time": "2026-03-03 14:15:00",
    "duration": "00:15:00",
    "subject": "Discovery Call — Acme Corp",
    "person_id": 123,
    "deal_id": 42,
    "note": "Discussed pricing. Follow-up scheduled for Thursday."
  }'

# Attach recording
curl -X POST "https://api.pipedrive.com/v1/callLogs/abc123/recordings?api_token=$PIPEDRIVE_API_TOKEN" \
  -F "file=@recording.mp3"
```

**Agent use:** Auto-log calls from VoIP/dialer systems, attach AI-transcribed recordings.

---

## 21. Activity Types

Configure what types of activities exist (call, meeting, email, lunch, custom types).

### Endpoints
```
GET    /v1/activityTypes           — List all activity types
POST   /v1/activityTypes           — Create new type (name + icon_key required)
PUT    /v1/activityTypes/{id}      — Update type
DELETE /v1/activityTypes/{id}      — Delete type
```

```bash
# Create custom activity type
curl -X POST "https://api.pipedrive.com/v1/activityTypes?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "AI Follow-up", "icon_key": "call", "color": "4CC2FF"}'
```

**Agent use:** Create custom types for automated activities so they're distinguishable from human ones.

---

## 22. Lead Labels & Sources

### Lead Labels
```
GET    /v1/leadLabels              — List all labels
POST   /v1/leadLabels              — Create label (name + color required)
PATCH  /v1/leadLabels/{id}         — Update label (UUID)
DELETE /v1/leadLabels/{id}         — Delete label
```

**Colors:** `blue`, `brown`, `dark-gray`, `gray`, `green`, `orange`, `pink`, `purple`, `red`, `yellow`

```bash
curl -X POST "https://api.pipedrive.com/v1/leadLabels?api_token=$PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "Hot Lead", "color": "red"}'
```

### Lead Sources
```
GET /v1/leadSources               — List all lead sources
```
Read-only — sources are configured in Pipedrive UI.

---

## 23. Subscriptions & Revenue (Deprecated → Products/Installments)

> **DEPRECATED as of June 2025.** The old Subscriptions API (`/v1/subscriptions/*`) is removed.
> Use **Products API** with `billing_frequency` + **Deal Installments API** instead.

### Old Endpoints (REMOVED — do not use)
```
GET    /v1/subscriptions/{id}
GET    /v1/subscriptions/find/{dealId}
GET    /v1/subscriptions/{id}/payments
POST   /v1/subscriptions/recurring
POST   /v1/subscriptions/installment
PUT    /v1/subscriptions/recurring/{id}
PUT    /v1/subscriptions/installment/{id}
DELETE /v1/subscriptions/{id}
```

### New Approach: Products + Installments
1. Create product with `billing_frequency` (monthly, quarterly, annually, etc.)
2. Attach product to deal via `POST /api/v2/deals/{id}/products`
3. Manage installments via `POST/GET/PATCH/DELETE /api/v2/deals/{id}/installments`

```bash
# Add recurring product to deal
curl -X POST "https://api.pipedrive.com/api/v2/deals/42/products" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "product_id": 10,
    "item_price": 499,
    "quantity": 1,
    "billing_frequency": "monthly",
    "billing_frequency_cycles": 12,
    "billing_start_date": "2026-04-01"
  }'
```

---

## 24. Common Patterns for Sales Agents

### Pattern 1: Inbound Lead Processing
```
1. Search for existing person by email  →  GET /api/v2/persons/search
2. Search for existing org by name      →  GET /api/v2/organizations/search
3. Create org if not found              →  POST /api/v2/organizations
4. Create person if not found           →  POST /api/v2/persons
5. Create lead                          →  POST /v1/leads
6. Add note with source details         →  POST /v1/notes
7. Schedule follow-up activity          →  POST /api/v2/activities
```

### Pattern 2: Post-Call Automation
```
1. Log the call                         →  POST /v1/callLogs
2. Attach recording                     →  POST /v1/callLogs/{id}/recordings
3. Add AI-generated summary note        →  POST /v1/notes (pinned to deal)
4. Update deal stage if qualified       →  PATCH /api/v2/deals/{id}
5. Schedule next activity               →  POST /api/v2/activities
6. Mark current activity as done        →  PATCH /api/v2/activities/{id}
```

### Pattern 3: Daily Pipeline Review Agent
```
1. Get pipeline stats                   →  GET /v1/deals/summary
2. Get conversion rates                 →  GET /v1/pipelines/{id}/conversion_statistics
3. Find stale deals (no activity)       →  GET /api/v2/deals?filter_id={stale_filter}
4. Check goal progress                  →  GET /v1/goals/{id}/results
5. Get recent changes                   →  GET /v1/recents?since_timestamp=...
6. Generate report & post as notes or send via external channel
```

### Pattern 4: Contact Deduplication
```
1. Search by email                      →  GET /api/v2/persons/search?fields=email
2. Search by phone                      →  GET /api/v2/persons/search?fields=phone
3. Search by name + org                 →  GET /api/v2/persons/search?organization_id=...
4. If duplicates found, merge           →  PUT /v1/persons/{id}/merge
5. Also check & merge orgs              →  PUT /v1/organizations/{id}/merge
```

### Pattern 5: Webhook-Driven Reactive Agent
```
1. Register webhooks for key events     →  POST /v1/webhooks
   - deal.create, deal.change, activity.create, person.create
2. On deal stage change:
   - If moved to "Proposal" → auto-generate proposal, attach file
   - If moved to "Won" → celebrate, update goals
   - If moved to "Lost" → log reason, schedule re-engagement
3. On new person created:
   - Enrich with external data
   - Update custom fields
4. On activity completed:
   - Schedule follow-up if no next activity exists
```

### Pattern 6: Revenue Forecasting
```
1. Get deals timeline                   →  GET /v1/deals/timeline
   (by expected_close_date, weekly intervals, 12 weeks)
2. Get deal products with billing       →  GET /api/v2/deals/{id}/products
3. Get installment schedule             →  GET /api/v2/deals/installments
4. Combine with goal targets            →  GET /v1/goals/find + GET /v1/goals/{id}/results
5. Generate forecast report
```

### Pattern 7: Full Entity Creation (Contact + Company + Deal + Activity)
```bash
# Step 1: Create org
ORG_ID=$(curl -s -X POST "https://api.pipedrive.com/api/v2/organizations" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name": "New Corp"}' | jq -r '.data.id')

# Step 2: Create person linked to org
PERSON_ID=$(curl -s -X POST "https://api.pipedrive.com/api/v2/persons" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"name\": \"Jane Doe\", \"org_id\": $ORG_ID, \"emails\": [{\"value\": \"jane@newcorp.com\", \"label\": \"work\", \"primary\": true}]}" | jq -r '.data.id')

# Step 3: Create deal
DEAL_ID=$(curl -s -X POST "https://api.pipedrive.com/api/v2/deals" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"title\": \"New Corp — Starter Plan\", \"person_id\": $PERSON_ID, \"org_id\": $ORG_ID, \"value\": 5000, \"currency\": \"USD\"}" | jq -r '.data.id')

# Step 4: Schedule intro call
curl -s -X POST "https://api.pipedrive.com/api/v2/activities" \
  -H "x-api-token: $PIPEDRIVE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"subject\": \"Intro call with Jane\", \"type\": \"call\", \"deal_id\": $DEAL_ID, \"person_id\": $PERSON_ID, \"due_date\": \"2026-03-05\", \"due_time\": \"10:00\"}"
```

---

## Quick Reference: All Endpoint Costs (API Tokens)

| Cost | Endpoints |
|------|-----------|
| 1 | Get single entity (deal, person, org, activity, field) |
| 3 | Delete activity, delete field, delete field options |
| 5 | Create entity, update entity, add follower, delete follower, delete deal |
| 6 | Delete note, delete comment, delete webhook, delete activity type, delete goal |
| 10 | Notes CRUD, call logs, deal participants, permitted users, webhooks, goals, activity types, pipelines stats, followers list, lead labels |
| 20 | List endpoints (deals, persons, orgs, activities, notes), search, recents, files list, pipeline conversion/movement, filters |
| 25 | Bulk product operations |
| 40 | Deal flow/updates, deals summary |
| 80 | Archived deals summary |

---

## Response Format (Standard)

Every API response follows this structure:
```json
{
  "success": true,
  "data": { ... },
  "additional_data": {
    "pagination": {
      "start": 0,
      "limit": 100,
      "more_items_in_collection": true,
      "next_start": 100
    }
  },
  "related_objects": { ... }
}
```

v2 cursor pagination:
```json
{
  "success": true,
  "data": [ ... ],
  "additional_data": {
    "next_cursor": "eyJpZCI6MTAwfQ"
  }
}
```

---

## Error Handling

| HTTP Code | Meaning | Action |
|-----------|---------|--------|
| 200 | Success | Process data |
| 201 | Created | Entity created successfully |
| 400 | Bad Request | Check params/body |
| 401 | Unauthorized | Check API token |
| 403 | Forbidden | Check permissions/plan |
| 404 | Not Found | Entity doesn't exist |
| 410 | Gone | Endpoint deprecated/removed |
| 429 | Rate Limited | Back off, check headers, retry |
| 500 | Server Error | Retry with backoff |

---

## SDKs & Tools

- **Official Node.js SDK:** `npm install pipedrive`
- **Official PHP SDK:** via Composer
- **OpenAPI 3 Spec:** Available for import into Postman, code generators
- **Developer Sandbox:** Free sandbox accounts for testing at developers.pipedrive.com

---

*This reference was compiled from the official Pipedrive API documentation at developers.pipedrive.com and pipedrive.readme.io. Always check the latest docs for breaking changes — Pipedrive is actively migrating from v1 to v2.*
