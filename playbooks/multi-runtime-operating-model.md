# Multi-Runtime Operating Model

## Jediný šéf

`OpenClaw / Spojka` zůstává jediný control-plane owner.

To znamená:

- jen Spojka/OpenClaw vlastní sdílený stav systému
- jen Spojka/OpenClaw routuje práci mezi runtime vrstvami
- jen Spojka/OpenClaw skládá finální digesty a uživatelské výstupy
- Claude a Codex jsou specialisté, ne alternativní řídicí vrstvy

Kanonická policy je v `control-plane/delegation-policy.json`.

## Role runtime vrstev

### OpenClaw

- orchestrátor
- approval flow
- execution state
- task queue
- cross-runtime routing
- final publication

### Claude Code / Cowork

- deep reasoning
- research
- critique
- second opinion
- scheduled knowledge work

### Codex / ChatGPT agents

- code changes
- repo surgery
- tooling
- debug
- implementation

## Anti-patterny

Nedělat:

- Claude i Codex současně jako dva leady na stejném tasku
- Claude nebo Codex zapisující přímo do shared control-plane souborů bez handoffu
- více runtime vrstev publishujících finální truth do stejného souboru
- více schedulerů, které si myslí, že jsou primární orchestrátor

## Povolené collaboration patterny

### 1. OpenClaw -> Claude -> OpenClaw

Použij pro:

- research
- architecture critique
- review findings
- strategic framing

Tok:

1. OpenClaw vytvoří request
2. Claude vrátí artifact/handoff
3. OpenClaw rozhodne, co přijme do shared state

### 2. OpenClaw -> Codex -> OpenClaw

Použij pro:

- code implementation
- bugfix
- refactor
- scripts

Tok:

1. OpenClaw zadá implementaci
2. Codex vrátí diff / artifact / handoff
3. OpenClaw rozhodne o integraci

### 3. OpenClaw -> Claude -> Codex -> OpenClaw

Použij pro:

- složitější systémové změny
- architecture review + implementation

Tok:

1. Claude udělá review nebo návrh
2. Codex implementuje
3. OpenClaw uzavře task a zapíše výsledný stav

## Rozdělení odpovědnosti teď

- `Spojka/OpenClaw`: šéf, routing, integrace, approvals
- `Claude`: review partner a reasoning specialist
- `Codex`: builder a technical executor

## Praktický mailbox flow

Claude:

- inbox: `bus/inbox/claude/`
- results: `bus/claude-results/`
- handoffs: `collaboration/handoffs/claude/`

Pravidlo:

- každý secondary runtime vrací výsledek jako artifact, ne jako nový source of truth

## První remediační vlna

1. explicitní delegation policy
2. mailbox bridge pro Claude
3. shared handoff artifacts
4. postupné narovnání naming driftu
5. postupné narovnání state driftu
6. později symetrický bridge pro Codex
