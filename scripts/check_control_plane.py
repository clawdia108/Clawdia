#!/usr/bin/env python3
"""
Control Plane Checker — detect drift between declared and live runtime layers
=============================================================================
Audits the current workspace reality instead of assuming one perfect historical
architecture. Reports mismatches between:
- control-plane registry
- workspace routing config
- execution state / task queue ownership
- filesystem agents
- bus inboxes
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

BASE = Path("/Users/josefhofman/Clawdia")

REGISTRY_PATH = BASE / "control-plane" / "agent-registry.json"
EXECUTION_STATE_PATH = BASE / "knowledge" / "EXECUTION_STATE.json"
TASK_QUEUE_PATH = BASE / "control-plane" / "task-queue.json"
TASKS_OPEN_DIR = BASE / "tasks" / "open"
ROUTING_PATH = BASE / "workspace" / "openclaw.model-routing.json"
DELEGATION_POLICY_PATH = BASE / "control-plane" / "delegation-policy.json"
AGENTS_DIR = BASE / "agents"
BUS_INBOX_DIR = BASE / "bus" / "inbox"


def load_json(path):
    if not path.exists():
        return None
    return json.loads(path.read_text())


def registry_identity_sets(registry):
    registry_ids = set(registry.get("agents", {}).keys())
    alias_map = defaultdict(set)
    all_known_ids = set(registry_ids)

    for agent_id, meta in registry.get("agents", {}).items():
        alias_map[agent_id].add(agent_id)
        for alias in meta.get("aliases", []):
            alias_map[agent_id].add(alias)
            all_known_ids.add(alias)

    return registry_ids, alias_map, all_known_ids


def collect_execution_state_owners(execution_state):
    owners = set()
    if not execution_state:
        return owners

    for section_name in ("top_priorities", "blocked_tasks", "needs_review", "tasks"):
        for task in execution_state.get(section_name, []):
            owner = task.get("owner")
            if owner:
                owners.add(owner)
    return owners


def collect_task_queue_agents(task_queue):
    agents = set()
    if not task_queue:
        return agents
    for task in task_queue.get("tasks", []):
        assigned = task.get("assigned_to")
        if assigned:
            agents.add(assigned)
    return agents


def collect_open_task_agents():
    owners = set()
    reviewers = set()
    for path in sorted(TASKS_OPEN_DIR.glob("*.json")):
        task = load_json(path) or {}
        owner = task.get("owner")
        reviewer = task.get("reviewer")
        if owner:
            owners.add(owner)
        if reviewer:
            reviewers.add(reviewer)
    return owners, reviewers


def collect_routing_agents(routing):
    entries = (((routing or {}).get("agents") or {}).get("entries") or {})
    return set(entries.keys())


def collect_filesystem_agents():
    if not AGENTS_DIR.exists():
        return set()
    return {path.name for path in AGENTS_DIR.iterdir() if path.is_dir()}


def collect_bus_inboxes():
    if not BUS_INBOX_DIR.exists():
        return set()
    return {path.name for path in BUS_INBOX_DIR.iterdir() if path.is_dir()}


def main():
    registry = load_json(REGISTRY_PATH)
    if not registry:
        print("CONTROL PLANE CHECK FAILED")
        print("- Missing or invalid control-plane/agent-registry.json")
        return 1

    execution_state = load_json(EXECUTION_STATE_PATH) or {}
    task_queue = load_json(TASK_QUEUE_PATH) or {}
    routing = load_json(ROUTING_PATH) or {}
    delegation_policy = load_json(DELEGATION_POLICY_PATH) or {}

    registry_ids, alias_map, all_known_ids = registry_identity_sets(registry)
    routing_agents = collect_routing_agents(routing)
    filesystem_agents = collect_filesystem_agents()
    bus_inboxes = collect_bus_inboxes()
    execution_owners = collect_execution_state_owners(execution_state)
    queue_agents = collect_task_queue_agents(task_queue)
    task_owners, task_reviewers = collect_open_task_agents()

    warnings = []
    errors = []

    if delegation_policy.get("single_control_plane_owner") != registry.get("main_agent"):
        warnings.append("delegation-policy single_control_plane_owner does not match agent-registry main_agent")

    missing_filesystem = sorted((registry_ids - {"main"}) - filesystem_agents)
    if missing_filesystem:
        warnings.append(f"registry agents missing from agents/: {missing_filesystem}")

    missing_inbox = sorted((registry_ids - {"main"}) - bus_inboxes)
    if missing_inbox:
        warnings.append(f"registry agents missing bus inboxes: {missing_inbox}")

    if "claude" not in bus_inboxes:
        warnings.append("claude inbox missing; Claude Bridge mailbox is not initialized until first run")

    unknown_execution_owners = sorted(execution_owners - all_known_ids)
    if unknown_execution_owners:
        warnings.append(f"execution_state references unknown owners: {unknown_execution_owners}")

    unknown_queue_agents = sorted(queue_agents - all_known_ids)
    if unknown_queue_agents:
        warnings.append(f"task_queue references unknown assignees: {unknown_queue_agents}")

    unknown_task_owners = sorted(task_owners - all_known_ids)
    if unknown_task_owners:
        errors.append(f"tasks/open references unknown owners: {unknown_task_owners}")

    unknown_task_reviewers = sorted(task_reviewers - all_known_ids)
    if unknown_task_reviewers:
        errors.append(f"tasks/open references unknown reviewers: {unknown_task_reviewers}")

    routing_only = sorted(routing_agents - all_known_ids)
    if routing_only:
        warnings.append(f"routing config contains runtime-only or drifted agent ids: {routing_only}")

    registry_not_in_routing = sorted(registry_ids - routing_agents)
    if registry_not_in_routing:
        warnings.append(f"registry agents missing from workspace/openclaw.model-routing.json: {registry_not_in_routing}")

    duplicate_state_shape = load_json(BASE / "control-plane" / "agent-states.json") or {}
    if duplicate_state_shape and "agents" in duplicate_state_shape and any(key != "agents" for key in duplicate_state_shape.keys()):
        warnings.append("control-plane/agent-states.json mixes top-level agent records with nested agents{} records")

    print("CONTROL PLANE CHECK")
    print(f"- main owner: {registry.get('main_agent')}")
    print(f"- registry ids: {sorted(registry_ids)}")
    print(f"- routing ids: {sorted(routing_agents)}")
    print(f"- filesystem agents: {sorted(filesystem_agents)}")
    print(f"- bus inboxes: {sorted(bus_inboxes)}")
    print(f"- execution_state owners: {sorted(execution_owners)}")
    print(f"- task_queue assignees: {sorted(queue_agents)}")

    if warnings:
        print("\nWARNINGS")
        for warning in warnings:
            print(f"- {warning}")

    if errors:
        print("\nERRORS")
        for error in errors:
            print(f"- {error}")
        return 1

    print("\nSTATUS")
    print("- control plane is internally usable")
    if warnings:
        print("- drift exists and should be remediated")
        return 0

    print("- no drift detected by current checks")
    return 0


if __name__ == "__main__":
    sys.exit(main())
