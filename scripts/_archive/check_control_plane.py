#!/usr/bin/env python3
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "control-plane" / "agent-registry.json"
PATTERNS_PATH = ROOT / "control-plane" / "coordination-patterns.json"
CONTRACTS_PATH = ROOT / "control-plane" / "output-contracts.json"
RUNTIME_PATH = ROOT / "control-plane" / "runtime-policies.json"
GATES_PATH = ROOT / "control-plane" / "review-gates.json"
ARMY_PATH = ROOT / "openclaw.agent-army.json"
ROUTING_PATH = ROOT / "workspace" / "openclaw.model-routing.json"
MODEL_ROUTER_PATH = ROOT / "control-plane" / "model-router.json"
TASK_TEMPLATE_PATH = ROOT / "tasks" / "templates" / "task.json"
TASKS_OPEN_DIR = ROOT / "tasks" / "open"
AGENTS_DIR = ROOT / "agents"


def load(path: Path):
    return json.loads(path.read_text())


def iter_tasks():
    for path in sorted(TASKS_OPEN_DIR.glob("*.json")):
        yield path, load(path)


def get_model_ids(routing: dict) -> set[str]:
    model_ids = set()
    for provider, meta in routing["models"]["providers"].items():
        for model in meta.get("models", []):
            model_ids.add(f"{provider}/{model['id']}")
    return model_ids


def main():
    registry = load(REGISTRY_PATH)
    patterns = load(PATTERNS_PATH)
    contracts = load(CONTRACTS_PATH)
    runtime = load(RUNTIME_PATH)
    gates = load(GATES_PATH)
    army = load(ARMY_PATH)
    routing = load(ROUTING_PATH)
    model_router = load(MODEL_ROUTER_PATH)
    task_template = load(TASK_TEMPLATE_PATH)

    registry_agents = set(registry["agents"].keys())
    roster_agents = set(army["agentArmy"]["agents"]) | {army["agentArmy"]["main"]}
    routing_agents = set(routing["agents"]["entries"].keys())
    filesystem_agents = {path.name for path in AGENTS_DIR.iterdir() if path.is_dir()} | {"main"}
    pattern_ids = set(patterns["patterns"].keys())
    contract_ids = set(contracts["contracts"].keys())
    model_ids = get_model_ids(routing)

    errors = []
    if registry_agents != roster_agents:
        errors.append(
            f"registry vs army mismatch: {sorted(registry_agents ^ roster_agents)}"
        )
    if not registry_agents.issubset(routing_agents):
        missing = sorted(registry_agents - routing_agents)
        errors.append(f"registry agents missing from routing: {missing}")
    if not (registry_agents - {"main"}).issubset(filesystem_agents):
        missing = sorted((registry_agents - {"main"}) - filesystem_agents)
        errors.append(f"registry agents missing from agents/: {missing}")
    if routing.get("task_routing", {}).get("router_config") != "control-plane/model-router.json":
        errors.append("task_routing.router_config must point to control-plane/model-router.json")
    if routing.get("coordination", {}).get("patterns_config") != "control-plane/coordination-patterns.json":
        errors.append("coordination.patterns_config mismatch")
    if "scopes" not in runtime.get("sessions", {}):
        errors.append("runtime-policies.json missing sessions.scopes")

    for rule in model_router.get("routing_rules", []):
        if rule["pattern"] not in pattern_ids:
            errors.append(f"router rule {rule['id']} references unknown pattern {rule['pattern']}")
        contract = rule.get("output_contract")
        if contract and contract not in contract_ids:
            errors.append(f"router rule {rule['id']} references unknown contract {contract}")
        for key in ("lead_model", "worker_model", "aggregator_model", "reviewer_model", "output_model"):
            model = rule.get(key)
            if model and model not in model_ids:
                errors.append(f"router rule {rule['id']} references unknown model {model}")

    for gate in gates.get("gates", []):
        reviewer = gate.get("reviewer")
        if reviewer and reviewer not in registry_agents:
            errors.append(f"review gate {gate['id']} references unknown reviewer {reviewer}")

    required_template_fields = {
        "task_type",
        "risk_level",
        "coordination_pattern",
        "expected_output_contract",
        "approval_state",
        "route_snapshot",
    }
    missing_fields = sorted(required_template_fields - set(task_template))
    if missing_fields:
        errors.append(f"task template missing fields: {missing_fields}")

    for path, task in iter_tasks():
        owner = task.get("owner")
        if owner not in registry_agents:
            errors.append(f"{path.name}: owner {owner!r} not in registry")
        reviewer = task.get("reviewer")
        if reviewer not in registry_agents:
            errors.append(f"{path.name}: reviewer {reviewer!r} not in registry")
        pattern = task.get("coordination_pattern")
        if pattern not in pattern_ids:
            errors.append(f"{path.name}: unknown coordination_pattern {pattern!r}")
        contract = task.get("expected_output_contract")
        if contract not in contract_ids:
            errors.append(f"{path.name}: unknown expected_output_contract {contract!r}")

    if errors:
        print("CONTROL PLANE CHECK FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("CONTROL PLANE CHECK OK")
    print(f"- registry agents: {sorted(registry_agents)}")
    print(f"- routing agents: {sorted(routing_agents)}")
    print(f"- filesystem agents: {sorted(filesystem_agents)}")
    print(f"- coordination patterns: {sorted(pattern_ids)}")
    print(f"- output contracts: {sorted(contract_ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
