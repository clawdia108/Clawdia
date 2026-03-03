#!/usr/bin/env python3
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = ROOT / "control-plane" / "agent-registry.json"
ARMY_PATH = ROOT / "openclaw.agent-army.json"
ROUTING_PATH = ROOT / "workspace" / "openclaw.model-routing.json"
AGENTS_DIR = ROOT / "agents"


def load(path: Path):
    return json.loads(path.read_text())


def main():
    registry = load(REGISTRY_PATH)
    army = load(ARMY_PATH)
    routing = load(ROUTING_PATH)

    registry_agents = set(registry["agents"].keys())
    roster_agents = set(army["agentArmy"]["agents"]) | {army["agentArmy"]["main"]}
    routing_agents = set(routing["agents"]["entries"].keys())
    filesystem_agents = {path.name for path in AGENTS_DIR.iterdir() if path.is_dir()} | {"main"}

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

    if errors:
        print("CONTROL PLANE CHECK FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("CONTROL PLANE CHECK OK")
    print(f"- registry agents: {sorted(registry_agents)}")
    print(f"- routing agents: {sorted(routing_agents)}")
    print(f"- filesystem agents: {sorted(filesystem_agents)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
