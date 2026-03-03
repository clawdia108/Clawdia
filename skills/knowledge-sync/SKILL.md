---
name: knowledge-sync
description: Synchronize and maintain the shared knowledge base across all agents. Used by KnowledgeKeeper for daily knowledge management.
tools: Bash, Read, Write
---

# Knowledge Sync Skill

## Purpose
Maintain the shared knowledge base by collecting, organizing, and distributing knowledge across agents.

## Workflow

### 1. Collect
- Read all agent daily notes (agents/*/memory/YYYY-MM-DD.md)
- Read all workspace output files (intel/, pipedrive/, inbox/, calendar/, reviews/)
- Identify new information worth preserving

### 2. Organize
- Add new facts to knowledge/KNOWLEDGE_BASE.md with metadata
- Update knowledge/RESEARCH_LOG.md with new findings
- Moderate knowledge/AGENT_INSIGHTS.md discussions

### 3. Archive
- Move daily notes older than 7 days to memory/archive/
- Remove stale/outdated information from knowledge base
- Deduplicate entries

### 4. Distribute
- If a finding is relevant to a specific agent, note it in AGENT_INSIGHTS.md
- Update IMPROVEMENTS.md with actionable proposals

## Rules
- NEVER delete another agent's original notes — archive them
- ALWAYS add metadata (date, source agent) to knowledge entries
- Keep KNOWLEDGE_BASE.md organized by category
- Deduplicate but preserve attribution
