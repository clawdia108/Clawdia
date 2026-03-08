
## CRM Safety Rules
- HARD RULE (Josef): nikdy neupravovat Pipedrive aktivity/dealy/kontakty mimo záznamy vlastněné uživatelem Josef Hofman (user_id 24403638), pokud Josef explicitně neschválí výjimku.

## Multi-Runtime Rules
- `OpenClaw / Spojka` zůstává jediný control-plane owner. Claude a Codex jsou specialisté a vrací výsledky přes mailbox/handoff artefakty, ne jako konkurenční orchestrátoři.
- Health reporting má používat primárně runtime timestamps z `control-plane/agent-states.json`; stáří output souborů je jen fallback.
