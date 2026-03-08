#!/usr/bin/env python3
"""Resolve the execution pattern and model route for a task."""
import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "control-plane" / "agent-registry.json"
MODEL_ROUTER_PATH = ROOT / "control-plane" / "model-router.json"
OUTPUT_CONTRACTS_PATH = ROOT / "control-plane" / "output-contracts.json"
REVIEW_GATES_PATH = ROOT / "control-plane" / "review-gates.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def matches(task_value, expected) -> bool:
    if isinstance(expected, list):
        if isinstance(task_value, list):
            return all(item in task_value for item in expected)
        return task_value in expected
    return task_value == expected


def task_matches(task: dict, criteria: dict) -> bool:
    for key, expected in criteria.items():
        if not matches(task.get(key), expected):
            return False
    return True


def load_context(task: dict) -> dict:
    registry = load_json(REGISTRY_PATH)
    owner = task.get("owner")
    agent_meta = registry["agents"].get(owner, {})
    normalized = dict(task)
    normalized["agent"] = owner
    normalized.setdefault("task_type", "general")
    normalized.setdefault("risk_level", "medium")
    normalized.setdefault("complexity", "medium")
    normalized.setdefault("output_visibility", "internal")
    normalized.setdefault("capabilities_required", [])
    normalized.setdefault("guardrails", [])
    normalized.setdefault("requires_tools", False)
    normalized.setdefault("requires_parallel_workers", False)
    normalized.setdefault("skills_required", [])
    normalized.setdefault("expected_output_contract", "internal_snapshot")
    normalized.setdefault(
        "coordination_pattern",
        (agent_meta.get("preferred_patterns") or ["deterministic_router"])[0],
    )
    return normalized


def resolve_route(task: dict) -> dict:
    router = load_json(MODEL_ROUTER_PATH)
    contracts = load_json(OUTPUT_CONTRACTS_PATH)
    gates = load_json(REVIEW_GATES_PATH)
    task_ctx = load_context(task)

    selected_rule = None
    for rule in router["routing_rules"]:
        if task_matches(task_ctx, rule.get("match", {})):
            selected_rule = rule
            break
    if selected_rule is None:
        default_rule_id = router["default_rule"]
        selected_rule = next(rule for rule in router["routing_rules"] if rule["id"] == default_rule_id)

    active_gates = []
    bypass_low_internal = (
        gates.get("bypass_rules", {}).get("complexity_low_internal")
        and task_ctx.get("complexity") == "low"
        and task_ctx.get("output_visibility") == "internal"
    )
    bypass_heartbeat = (
        gates.get("bypass_rules", {}).get("heartbeat_tasks")
        and task_ctx.get("task_type") == "heartbeat"
    )
    if not (bypass_low_internal or bypass_heartbeat):
        for gate in gates["gates"]:
            if task_matches(task_ctx, gate.get("match", {})):
                active_gates.append(
                    {
                        "id": gate["id"],
                        "reviewer": gate["reviewer"],
                        "auto_block": gate["auto_block"],
                        "block_message": gate["block_message"],
                    }
                )

    contract_name = task_ctx.get("expected_output_contract") or selected_rule.get("output_contract")
    return {
        "task_id": task_ctx.get("id"),
        "owner": task_ctx.get("owner"),
        "rule_id": selected_rule["id"],
        "pattern": task_ctx.get("coordination_pattern") or selected_rule["pattern"],
        "lead_model": selected_rule.get("lead_model"),
        "worker_model": selected_rule.get("worker_model"),
        "aggregator_model": selected_rule.get("aggregator_model"),
        "reviewer_model": selected_rule.get("reviewer_model"),
        "output_model": selected_rule.get("output_model") or selected_rule.get("lead_model"),
        "fallbacks": selected_rule.get("fallbacks", []),
        "output_contract": contract_name,
        "output_contract_visibility": contracts["contracts"][contract_name]["visibility"],
        "reasoning_effort": selected_rule.get("reasoning_effort", "medium"),
        "review_gates": active_gates,
    }


def main():
    parser = argparse.ArgumentParser(description="Resolve the route for a task JSON file.")
    parser.add_argument("task_path", help="Path to a task JSON file")
    parser.add_argument("--write", action="store_true", help="Write route_snapshot back to the task file")
    args = parser.parse_args()

    task_path = Path(args.task_path)
    task = load_json(task_path)
    route = resolve_route(task)

    if args.write:
        task["route_snapshot"] = {
            "rule_id": route["rule_id"],
            "lead_model": route["lead_model"],
            "worker_model": route.get("worker_model"),
            "reviewer_model": route.get("reviewer_model"),
            "output_model": route["output_model"],
            "output_contract": route["output_contract"],
        }
        task_path.write_text(json.dumps(task, indent=2) + "\n")

    print(json.dumps(route, indent=2))


if __name__ == "__main__":
    main()
