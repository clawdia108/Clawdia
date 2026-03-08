# Claude Bridge

Mailbox bridge mezi Clawdia workspace a lokálním `claude` CLI.

## Co to dělá

- čte requesty z `bus/inbox/claude/`
- spouští je přes `claude -p`
- ukládá raw výsledky do `bus/claude-results/`
- vrací reply event zpět do agent busu
- importuje handoff pro cílového agenta do `collaboration/handoffs/claude/`

## Formát requestu

```json
{
  "id": "req_123",
  "source": "vyvojar",
  "topic": "claude.run",
  "type": "REQUEST",
  "priority": "P1",
  "target": "claude",
  "payload": {
    "action": "claude_run",
    "prompt": "Projdi poslední změny a napiš review findings.",
    "model": "claude-opus-4-6",
    "resume_session": null,
    "notify_agent": "vyvojar",
    "permission_mode": "bypassPermissions",
    "artifacts": [
      "control-plane/agent-registry.json",
      "scripts/agent_runner.py"
    ],
    "save_to": "reports/claude-review-latest.md"
  }
}
```

## Rychlé použití

```bash
./scripts/clawdia.sh claude-send --source vyvojar --notify-agent vyvojar "Projdi tenhle repozitář a navrhni 3 největší zlepšení."
python3 scripts/claude_bridge.py once
python3 scripts/agent_bus.py route
python3 scripts/agent_runner.py --once
```

## Režimy

- `python3 scripts/claude_bridge.py once`
- `python3 scripts/claude_bridge.py daemon`
- `python3 scripts/claude_bridge.py status`
- `python3 scripts/claude_bridge.py send --source vyvojar --notify-agent vyvojar "..." `

## Artefakty

- raw odpovědi: `bus/claude-results/*.json`
- hotové requesty: `bus/processed/claude/`
- failnuté requesty: `bus/dead-letter/claude/`
- agent handoffy: `collaboration/handoffs/claude/*.json` a `*.md`

## Poznámky

- Když nastavíš `notify_agent`, bridge po dokončení vrátí reply přímo do inboxu daného agenta.
- Když nastavíš `save_to`, čistý text výsledku se zapíše i do zvoleného souboru ve workspace.
- `resume_session` můžeš použít pro navázání na konkrétní běžící nebo uloženou Claude session.
