#!/usr/bin/env python3
"""Clawdia CLI — unified entry point for all operations.

Usage:
    clawdia agents                  List all agents and their status
    clawdia agents <name>           Show agent details
    clawdia run <agent> <task>      Run a specific task on an agent
    clawdia supervisor status       Show supervisor status
    clawdia supervisor start        Start the supervisor daemon
    clawdia supervisor once         Run one supervisor cycle
    clawdia bus stats               Show message bus statistics
    clawdia bus clean               Clean expired messages
    clawdia health                  System health summary
"""

import argparse
import sys

from .agents import create_all_agents, get_agent, AGENT_CLASSES
from .agents.base import Task
from .core.supervisor import Supervisor
from .core.bus import MessageBus
from .core.state import StateStore
from .core.metrics import MetricsCollector


def cmd_agents(args):
    """List agents or show details for one."""
    if args.name:
        try:
            agent = get_agent(args.name)
        except ValueError as e:
            print(f"Error: {e}")
            return 1
        print(f"\n  Agent: {agent.name} ({agent.czech_name})")
        print(f"  Description: {agent.description}")
        print(f"  Capabilities: {', '.join(agent.capabilities)}")
        print(f"  Status: {agent.status.value}")
        if hasattr(agent, 'SCRIPTS'):
            print(f"\n  Scripts:")
            for cap, script in agent.SCRIPTS.items():
                print(f"    {cap:20s} → {script}")
        print()
        return 0

    agents = create_all_agents()
    state = StateStore()
    all_state = state.get_all_agents()

    print(f"\n{'='*55}")
    print(f"  CLAWDIA AGENTS ({len(agents)})")
    print(f"{'='*55}\n")

    for name, agent in sorted(agents.items()):
        st = all_state.get(name, {})
        status = st.get("status", "idle")
        emoji = {"idle": "🟢", "active": "🔵", "error": "🔴"}.get(status, "⚪")
        caps = ", ".join(agent.capabilities[:3])
        if len(agent.capabilities) > 3:
            caps += f" +{len(agent.capabilities)-3}"
        print(f"  {emoji} {name:12s} │ {agent.description[:40]:40s} │ {caps}")

    print()
    return 0


def cmd_run(args):
    """Run a specific task on an agent."""
    try:
        agent = get_agent(args.agent)
    except ValueError as e:
        print(f"Error: {e}")
        return 1

    if args.task not in agent.capabilities:
        print(f"Error: {args.agent} can't handle '{args.task}'")
        print(f"Available: {', '.join(agent.capabilities)}")
        return 1

    task = Task(type=args.task, source="cli")
    state = StateStore()

    print(f"Running {args.agent}:{args.task}...")
    result = agent.run(task, state)

    if result.success:
        print(f"OK: {result.output[:200]}")
    else:
        print(f"FAILED: {result.error[:200]}")
    return 0 if result.success else 1


def cmd_supervisor(args):
    """Supervisor commands."""
    sup = Supervisor()

    if args.action == "status":
        sup.print_status()
    elif args.action == "once":
        print("Running single supervisor cycle...")
        sup.run_once()
        sup.print_status()
    elif args.action == "start":
        print("Starting supervisor daemon (Ctrl+C to stop)...")
        sup.run()
    else:
        print(f"Unknown action: {args.action}")
        return 1
    return 0


def cmd_bus(args):
    """Message bus commands."""
    bus = MessageBus()

    if args.action == "stats":
        stats = bus.stats()
        print(f"\n{'='*40}")
        print(f"  MESSAGE BUS")
        print(f"{'='*40}")
        print(f"  Inbox:       {stats.get('total_inbox', 0)}")
        print(f"  Outbox:      {stats.get('outbox', 0)}")
        print(f"  Dead-letter: {stats.get('dead_letter', 0)}")
        agents = stats.get("per_agent", {})
        if agents:
            print(f"\n  Per-agent inbox:")
            for name, count in sorted(agents.items()):
                print(f"    {name:12s}: {count}")
        print()
    elif args.action == "clean":
        cleaned = bus.cleanup(max_age_hours=48)
        print(f"Cleaned {cleaned} expired messages")
    elif args.action == "purge":
        count = bus.purge_dead_letters()
        print(f"Purged {count} dead-letter messages")
    else:
        print(f"Unknown action: {args.action}")
        return 1
    return 0


def cmd_health(args):
    """System health summary."""
    state = StateStore()
    bus = MessageBus()
    agents = create_all_agents()

    summary = state.get_summary()
    bus_stats = bus.stats()
    agent_states = state.get_all_agents()

    print(f"\n{'='*55}")
    print(f"  CLAWDIA SYSTEM HEALTH")
    print(f"{'='*55}")

    # Agents
    errors = [n for n, s in agent_states.items() if s.get("status") == "error"]
    active = [n for n, s in agent_states.items() if s.get("status") == "active"]
    print(f"\n  Agents: {len(agents)} registered, {len(active)} active, {len(errors)} errors")
    if errors:
        print(f"  ⚠ Error agents: {', '.join(errors)}")

    # Bus
    print(f"\n  Bus: {bus_stats.get('total_inbox', 0)} inbox, "
          f"{bus_stats.get('dead_letter', 0)} dead-letter")

    # Tasks
    recent = state.get_recent_tasks(20)
    completed = sum(1 for t in recent if t.get("status") == "completed")
    failed = sum(1 for t in recent if t.get("status") == "failed")
    print(f"\n  Recent tasks (last 20): {completed} completed, {failed} failed")

    # Cycle count
    print(f"  Total cycles: {summary.get('cycle_count', 0)}")

    # Overall health
    if errors:
        print(f"\n  🔴 DEGRADED — {len(errors)} agents in error state")
    elif bus_stats.get("dead_letter", 0) > 100:
        print(f"\n  🟡 WARNING — {bus_stats['dead_letter']} dead-letter messages")
    else:
        print(f"\n  🟢 HEALTHY")

    print()
    return 0


def cmd_metrics(args):
    """Show metrics dashboard."""
    mc = MetricsCollector()
    mc.print_dashboard()
    return 0


def main():
    parser = argparse.ArgumentParser(prog="clawdia", description="Clawdia AI Sales Assistant")
    sub = parser.add_subparsers(dest="command")

    # agents
    p_agents = sub.add_parser("agents", help="List agents")
    p_agents.add_argument("name", nargs="?", help="Agent name for details")

    # run
    p_run = sub.add_parser("run", help="Run a task")
    p_run.add_argument("agent", help="Agent name")
    p_run.add_argument("task", help="Task type")

    # supervisor
    p_sup = sub.add_parser("supervisor", help="Supervisor commands")
    p_sup.add_argument("action", choices=["status", "start", "once"], help="Action")

    # bus
    p_bus = sub.add_parser("bus", help="Message bus commands")
    p_bus.add_argument("action", choices=["stats", "clean", "purge"], help="Action")

    # health
    sub.add_parser("health", help="System health summary")

    # metrics
    sub.add_parser("metrics", help="Show metrics dashboard")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    handlers = {
        "agents": cmd_agents,
        "run": cmd_run,
        "supervisor": cmd_supervisor,
        "bus": cmd_bus,
        "health": cmd_health,
        "metrics": cmd_metrics,
    }

    return handlers[args.command](args)


if __name__ == "__main__":
    sys.exit(main())
