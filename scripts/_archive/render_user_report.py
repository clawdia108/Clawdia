#!/usr/bin/env python3
"""Render a short user-facing digest from execution_state.json."""
import argparse
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXECUTION_STATE_PATH = ROOT / "knowledge" / "EXECUTION_STATE.json"
OUTPUT_CONTRACTS_PATH = ROOT / "control-plane" / "output-contracts.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text())


def clean_summary(task: dict) -> str:
    return task.get("user_summary") or task.get("summary") or task.get("title", "Bez popisu")


def priority_line(task: dict) -> str:
    detail = ""
    if task.get("status") == "blocked":
        detail = "zablokováno"
    elif task.get("due_at") not in {None, "n/a"}:
        detail = "termín dnes"
    if detail:
        return f"**{clean_summary(task)}** — {detail}"
    return f"**{clean_summary(task)}**"


def action_line(task: dict) -> str:
    approval_state = task.get("approval_state")
    if approval_state == "pending_human":
        return clean_summary(task)
    blockers = task.get("blockers") or []
    if blockers:
        return f"{clean_summary(task)} ({blockers[0].replace('_', ' ')})"
    return clean_summary(task)


def render(period: str, output_path: Path):
    state = load_json(EXECUTION_STATE_PATH)
    contract = load_json(OUTPUT_CONTRACTS_PATH)["contracts"]["user_report"]

    priorities = state.get("top_priorities", [])[:3]
    completed = state.get("recently_completed", [])[:3]
    actions = [
        task for task in state.get("blocked_tasks", [])
        if task.get("approval_state") in {"pending_human", "pending_bridge"} or task.get("status") == "blocked"
    ][:3]

    date = datetime.now().date().isoformat()
    period_label = "Ráno" if period.upper() == "AM" else "Večer"
    lines = [f"# {period_label} — {date}", "", "## Co je dnes důležité"]

    if priorities:
        for index, task in enumerate(priorities, start=1):
            lines.append(f"{index}. {priority_line(task)}")
    else:
        lines.append("Žádné urgentní položky.")

    lines.extend(["", "## Co jsem udělal"])
    if completed:
        for task in completed:
            lines.append(f"- {clean_summary(task)}")
    else:
        lines.append("- Zatím nic nového.")

    lines.extend(["", "## Potřebuji od tebe"])
    if actions:
        for task in actions:
            lines.append(f"- [ ] {action_line(task)}")
    else:
        lines.append("Nic — vše běží.")

    output_path.write_text("\n".join(lines[:contract["max_lines"]]).rstrip() + "\n")
    print(f"render_user_report: wrote {output_path.relative_to(ROOT)}")


def main():
    parser = argparse.ArgumentParser(description="Render a user-facing digest.")
    parser.add_argument("--period", choices=["AM", "PM"], default="AM")
    parser.add_argument("--output", help="Optional output path")
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else ROOT / "knowledge" / f"USER_DIGEST_{args.period}.md"
    render(args.period, output_path)


if __name__ == "__main__":
    main()
