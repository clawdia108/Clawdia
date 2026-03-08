#!/usr/bin/env python3
"""
Workflow Engine — DAG-based multi-step execution
=================================================
Define workflows as directed acyclic graphs. Each step is an agent action.
Supports: parallel branches, join points, conditional routing, retries.

Workflow definition format (JSON):
{
  "id": "sales_pipeline",
  "name": "Sales Pipeline Automation",
  "steps": {
    "score": {"agent": "obchodak", "action": "score_deals", "next": ["draft"]},
    "draft": {"agent": "textar", "action": "draft_emails", "next": ["review"], "depends_on": ["score"]},
    "review": {"agent": "kontrolor", "action": "review_drafts", "next": ["approve"], "depends_on": ["draft"]},
    "approve": {"agent": "human", "action": "approve_drafts", "next": ["send"], "depends_on": ["review"]},
    "send": {"agent": "postak", "action": "send_emails", "depends_on": ["approve"]}
  },
  "entry": ["score"],
  "max_duration_hours": 48
}
"""

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from collections import defaultdict

BASE = Path("/Users/josefhofman/Clawdia")
WORKFLOW_DEFS = BASE / "workflows" / "definitions"
WORKFLOW_RUNS = BASE / "workflows" / "runs"
WORKFLOW_COMPLETED = BASE / "workflows" / "completed"
WORKFLOW_LOG = BASE / "logs" / "workflow.log"


def wlog(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    WORKFLOW_LOG.parent.mkdir(exist_ok=True)
    with open(WORKFLOW_LOG, "a") as f:
        f.write(line + "\n")


class WorkflowStep:
    """A single step in a workflow"""

    def __init__(self, step_id, config):
        self.id = step_id
        self.agent = config.get("agent", "unassigned")
        self.action = config.get("action", "unknown")
        self.next_steps = config.get("next", [])
        self.depends_on = config.get("depends_on", [])
        self.timeout_minutes = config.get("timeout_minutes", 60)
        self.retries = config.get("retries", 1)
        self.condition = config.get("condition", None)  # Optional condition to evaluate
        self.config = config


class WorkflowDefinition:
    """A workflow template (DAG)"""

    def __init__(self, data):
        self.id = data["id"]
        self.name = data["name"]
        self.description = data.get("description", "")
        self.entry_steps = data.get("entry", [])
        self.max_duration_hours = data.get("max_duration_hours", 48)
        self.steps = {}
        for step_id, config in data.get("steps", {}).items():
            self.steps[step_id] = WorkflowStep(step_id, config)

    def validate(self):
        """Validate DAG: check for cycles, missing deps, orphan steps"""
        errors = []

        # Check entry steps exist
        for entry in self.entry_steps:
            if entry not in self.steps:
                errors.append(f"Entry step '{entry}' not defined")

        # Check all dependencies exist
        for step_id, step in self.steps.items():
            for dep in step.depends_on:
                if dep not in self.steps:
                    errors.append(f"Step '{step_id}' depends on undefined step '{dep}'")
            for nxt in step.next_steps:
                if nxt not in self.steps:
                    errors.append(f"Step '{step_id}' points to undefined next step '{nxt}'")

        # Check for cycles (simple DFS)
        visited = set()
        rec_stack = set()

        def has_cycle(node):
            visited.add(node)
            rec_stack.add(node)
            for neighbor in self.steps.get(node, WorkflowStep(node, {})).next_steps:
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    errors.append(f"Cycle detected involving step '{neighbor}'")
                    return True
            rec_stack.discard(node)
            return False

        for step_id in self.steps:
            if step_id not in visited:
                has_cycle(step_id)

        return errors

    @classmethod
    def load(cls, path):
        return cls(json.loads(path.read_text()))

    @classmethod
    def load_all(cls):
        defs = {}
        WORKFLOW_DEFS.mkdir(parents=True, exist_ok=True)
        for f in WORKFLOW_DEFS.glob("*.json"):
            try:
                wf = cls.load(f)
                defs[wf.id] = wf
            except (json.JSONDecodeError, KeyError) as e:
                wlog(f"Invalid workflow definition {f.name}: {e}", "ERROR")
        return defs


class WorkflowRun:
    """A running instance of a workflow"""

    def __init__(self, definition, run_id=None, context=None):
        self.run_id = run_id or f"run_{int(time.time())}_{definition.id}"
        self.workflow_id = definition.id
        self.workflow_name = definition.name
        self.definition = definition
        self.context = context or {}  # Shared context passed between steps
        self.status = "running"  # running, completed, failed, timed_out
        self.created_at = datetime.now().isoformat()
        self.completed_at = None
        self.step_states = {}  # step_id → {status, started_at, completed_at, output, error, attempts}
        self.events = []  # Timeline of events

        # Initialize all steps as pending
        for step_id in definition.steps:
            self.step_states[step_id] = {
                "status": "pending",  # pending, ready, running, completed, failed, skipped
                "started_at": None,
                "completed_at": None,
                "output": None,
                "error": None,
                "attempts": 0,
                "agent": definition.steps[step_id].agent,
                "action": definition.steps[step_id].action,
            }

    def _add_event(self, event_type, step_id=None, details=None):
        self.events.append({
            "ts": datetime.now().isoformat(),
            "type": event_type,
            "step": step_id,
            "details": details or {},
        })

    def get_ready_steps(self):
        """Find steps whose dependencies are all completed"""
        ready = []
        for step_id, step in self.definition.steps.items():
            state = self.step_states[step_id]
            if state["status"] != "pending":
                continue

            # Check all dependencies are completed
            deps_met = all(
                self.step_states.get(dep, {}).get("status") == "completed"
                for dep in step.depends_on
            )

            if deps_met:
                # Check condition if any
                if step.condition:
                    if not self._evaluate_condition(step.condition):
                        state["status"] = "skipped"
                        self._add_event("step_skipped", step_id, {"reason": "condition not met"})
                        continue

                ready.append(step_id)

        return ready

    def _evaluate_condition(self, condition):
        """Evaluate a step condition against workflow context"""
        if isinstance(condition, dict):
            field = condition.get("field", "")
            op = condition.get("op", "eq")
            value = condition.get("value")

            actual = self.context.get(field)
            if op == "eq":
                return actual == value
            elif op == "neq":
                return actual != value
            elif op == "gt":
                return (actual or 0) > (value or 0)
            elif op == "exists":
                return actual is not None
        return True

    def start_step(self, step_id):
        """Mark a step as running"""
        state = self.step_states[step_id]
        state["status"] = "running"
        state["started_at"] = datetime.now().isoformat()
        state["attempts"] += 1
        self._add_event("step_started", step_id, {"attempt": state["attempts"]})
        wlog(f"[{self.run_id}] Step '{step_id}' started (attempt {state['attempts']})")

    def complete_step(self, step_id, output=None):
        """Mark a step as completed with output"""
        state = self.step_states[step_id]
        state["status"] = "completed"
        state["completed_at"] = datetime.now().isoformat()
        state["output"] = output

        # Merge output into workflow context
        if isinstance(output, dict):
            self.context.update(output)

        self._add_event("step_completed", step_id, {"output_keys": list(output.keys()) if isinstance(output, dict) else None})
        wlog(f"[{self.run_id}] Step '{step_id}' completed")

        # Check if workflow is complete
        if self.is_complete():
            self.status = "completed"
            self.completed_at = datetime.now().isoformat()
            self._add_event("workflow_completed")
            wlog(f"[{self.run_id}] Workflow COMPLETED")

    def fail_step(self, step_id, error=None):
        """Mark a step as failed"""
        state = self.step_states[step_id]
        step = self.definition.steps[step_id]

        if state["attempts"] < step.retries:
            # Retry
            state["status"] = "pending"
            state["error"] = error
            self._add_event("step_retry", step_id, {"error": str(error)[:200], "attempt": state["attempts"]})
            wlog(f"[{self.run_id}] Step '{step_id}' failed, retrying ({state['attempts']}/{step.retries})")
        else:
            state["status"] = "failed"
            state["error"] = error
            state["completed_at"] = datetime.now().isoformat()
            self._add_event("step_failed", step_id, {"error": str(error)[:200]})
            wlog(f"[{self.run_id}] Step '{step_id}' FAILED after {state['attempts']} attempts", "ERROR")

            # Fail the workflow
            self.status = "failed"
            self.completed_at = datetime.now().isoformat()
            self._add_event("workflow_failed", step_id)

    def is_complete(self):
        """Check if all steps are completed or skipped"""
        return all(
            s["status"] in ("completed", "skipped")
            for s in self.step_states.values()
        )

    def is_timed_out(self):
        """Check if workflow exceeded max duration"""
        created = datetime.fromisoformat(self.created_at)
        return datetime.now() > created + timedelta(hours=self.definition.max_duration_hours)

    def progress(self):
        """Get completion percentage"""
        total = len(self.step_states)
        done = sum(1 for s in self.step_states.values() if s["status"] in ("completed", "skipped"))
        return round(done / total * 100) if total else 0

    def summary(self):
        """Human-readable summary"""
        return {
            "run_id": self.run_id,
            "workflow": self.workflow_name,
            "status": self.status,
            "progress": f"{self.progress()}%",
            "steps": {
                sid: {"status": s["status"], "agent": s["agent"]}
                for sid, s in self.step_states.items()
            },
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    def save(self):
        """Save run state to disk"""
        directory = WORKFLOW_COMPLETED if self.status in ("completed", "failed") else WORKFLOW_RUNS
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{self.run_id}.json"
        data = {
            "run_id": self.run_id,
            "workflow_id": self.workflow_id,
            "workflow_name": self.workflow_name,
            "status": self.status,
            "context": self.context,
            "step_states": self.step_states,
            "events": self.events,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False))
        return path

    @classmethod
    def load(cls, path, definitions):
        data = json.loads(path.read_text())
        wf_id = data["workflow_id"]
        if wf_id not in definitions:
            raise ValueError(f"Unknown workflow: {wf_id}")
        run = cls(definitions[wf_id], run_id=data["run_id"], context=data.get("context"))
        run.status = data["status"]
        run.step_states = data["step_states"]
        run.events = data.get("events", [])
        run.created_at = data["created_at"]
        run.completed_at = data.get("completed_at")
        return run


class WorkflowEngine:
    """Manages workflow definitions and running instances"""

    def __init__(self):
        self.definitions = WorkflowDefinition.load_all()
        self.active_runs = self._load_active_runs()

    def _load_active_runs(self):
        runs = {}
        WORKFLOW_RUNS.mkdir(parents=True, exist_ok=True)
        for f in WORKFLOW_RUNS.glob("*.json"):
            try:
                run = WorkflowRun.load(f, self.definitions)
                runs[run.run_id] = run
            except (json.JSONDecodeError, KeyError, ValueError) as e:
                wlog(f"Invalid run file {f.name}: {e}", "ERROR")
        return runs

    def start_workflow(self, workflow_id, context=None):
        """Start a new workflow instance"""
        if workflow_id not in self.definitions:
            raise ValueError(f"Unknown workflow: {workflow_id}")

        definition = self.definitions[workflow_id]
        errors = definition.validate()
        if errors:
            raise ValueError(f"Invalid workflow: {'; '.join(errors)}")

        run = WorkflowRun(definition, context=context)
        run.save()
        self.active_runs[run.run_id] = run

        wlog(f"Started workflow '{definition.name}' (run_id={run.run_id})")
        return run

    def advance_all(self):
        """Advance all active workflows — find and dispatch ready steps"""
        dispatched = []

        for run_id, run in list(self.active_runs.items()):
            if run.status != "running":
                continue

            # Check timeout
            if run.is_timed_out():
                run.status = "timed_out"
                run.completed_at = datetime.now().isoformat()
                run.save()
                wlog(f"Workflow {run_id} TIMED OUT", "WARN")
                continue

            # Find and dispatch ready steps
            ready = run.get_ready_steps()
            for step_id in ready:
                run.start_step(step_id)
                dispatched.append({
                    "run_id": run_id,
                    "step_id": step_id,
                    "agent": run.definition.steps[step_id].agent,
                    "action": run.definition.steps[step_id].action,
                    "context": run.context,
                })

            run.save()

        return dispatched

    def complete_step(self, run_id, step_id, output=None):
        """Complete a step in a running workflow"""
        if run_id not in self.active_runs:
            raise ValueError(f"Unknown run: {run_id}")

        run = self.active_runs[run_id]
        run.complete_step(step_id, output)
        run.save()

        # If workflow completed, move to completed
        if run.status in ("completed", "failed"):
            del self.active_runs[run_id]

        return run

    def fail_step(self, run_id, step_id, error=None):
        """Fail a step in a running workflow"""
        if run_id not in self.active_runs:
            raise ValueError(f"Unknown run: {run_id}")

        run = self.active_runs[run_id]
        run.fail_step(step_id, error)
        run.save()

        if run.status in ("completed", "failed"):
            del self.active_runs[run_id]

        return run

    def status(self):
        """Get engine status"""
        return {
            "definitions": len(self.definitions),
            "active_runs": len(self.active_runs),
            "runs": {rid: run.summary() for rid, run in self.active_runs.items()},
        }


# ── PREDEFINED WORKFLOWS ────────────────────────────
SALES_PIPELINE_WORKFLOW = {
    "id": "sales_pipeline",
    "name": "Sales Pipeline Automation",
    "description": "End-to-end: Score → Draft → Review → Approve → Execute",
    "max_duration_hours": 48,
    "entry": ["score_deals"],
    "steps": {
        "score_deals": {
            "agent": "obchodak",
            "action": "run_lead_scoring",
            "next": ["identify_stale", "identify_hot"],
            "timeout_minutes": 30,
        },
        "identify_stale": {
            "agent": "udrzbar",
            "action": "find_stale_deals",
            "next": ["draft_followups"],
            "depends_on": ["score_deals"],
        },
        "identify_hot": {
            "agent": "udrzbar",
            "action": "find_hot_deals",
            "next": ["draft_outreach"],
            "depends_on": ["score_deals"],
        },
        "draft_followups": {
            "agent": "textar",
            "action": "draft_followup_emails",
            "next": ["review_content"],
            "depends_on": ["identify_stale"],
        },
        "draft_outreach": {
            "agent": "textar",
            "action": "draft_outreach_emails",
            "next": ["review_content"],
            "depends_on": ["identify_hot"],
        },
        "review_content": {
            "agent": "kontrolor",
            "action": "review_email_drafts",
            "next": ["submit_approval"],
            "depends_on": ["draft_followups", "draft_outreach"],
            "retries": 2,
        },
        "submit_approval": {
            "agent": "kontrolor",
            "action": "submit_for_approval",
            "next": ["execute_sends"],
            "depends_on": ["review_content"],
        },
        "execute_sends": {
            "agent": "postak",
            "action": "send_approved_emails",
            "depends_on": ["submit_approval"],
        },
    },
}

MORNING_BRIEFING_WORKFLOW = {
    "id": "morning_briefing",
    "name": "Morning Briefing Generation",
    "description": "Generate comprehensive morning briefing with all context",
    "max_duration_hours": 2,
    "entry": ["fetch_pipeline", "fetch_calendar", "fetch_inbox"],
    "steps": {
        "fetch_pipeline": {
            "agent": "obchodak",
            "action": "get_pipeline_snapshot",
            "next": ["compile_briefing"],
            "timeout_minutes": 10,
        },
        "fetch_calendar": {
            "agent": "kalendar",
            "action": "get_today_schedule",
            "next": ["compile_briefing"],
            "timeout_minutes": 10,
        },
        "fetch_inbox": {
            "agent": "postak",
            "action": "get_inbox_summary",
            "next": ["compile_briefing"],
            "timeout_minutes": 10,
        },
        "compile_briefing": {
            "agent": "spojka",
            "action": "compile_morning_briefing",
            "next": ["adhd_focus"],
            "depends_on": ["fetch_pipeline", "fetch_calendar", "fetch_inbox"],
        },
        "adhd_focus": {
            "agent": "planovac",
            "action": "generate_focus_plan",
            "depends_on": ["compile_briefing"],
        },
    },
}

DEAL_WON_WORKFLOW = {
    "id": "deal_won",
    "name": "Deal Won Celebration & Onboarding",
    "description": "When a deal is won: celebrate, update scorecard, start onboarding",
    "max_duration_hours": 24,
    "entry": ["log_win"],
    "steps": {
        "log_win": {
            "agent": "hlidac",
            "action": "log_deal_win",
            "next": ["update_scorecard", "draft_onboarding", "notify_team"],
        },
        "update_scorecard": {
            "agent": "hlidac",
            "action": "add_win_points",
            "depends_on": ["log_win"],
        },
        "draft_onboarding": {
            "agent": "textar",
            "action": "draft_onboarding_email",
            "next": ["review_onboarding"],
            "depends_on": ["log_win"],
        },
        "review_onboarding": {
            "agent": "kontrolor",
            "action": "review_onboarding_draft",
            "depends_on": ["draft_onboarding"],
            "retries": 2,
        },
        "notify_team": {
            "agent": "spojka",
            "action": "send_win_notification",
            "depends_on": ["log_win"],
        },
    },
}


def install_default_workflows():
    """Save predefined workflow definitions to disk"""
    WORKFLOW_DEFS.mkdir(parents=True, exist_ok=True)
    for wf in [SALES_PIPELINE_WORKFLOW, MORNING_BRIEFING_WORKFLOW, DEAL_WON_WORKFLOW]:
        path = WORKFLOW_DEFS / f"{wf['id']}.json"
        path.write_text(json.dumps(wf, indent=2, ensure_ascii=False))
    print(f"Installed {3} workflow definitions to {WORKFLOW_DEFS}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1]

        if cmd == "install":
            install_default_workflows()

        elif cmd == "list":
            defs = WorkflowDefinition.load_all()
            for wf_id, wf in defs.items():
                errors = wf.validate()
                status = "VALID" if not errors else f"ERRORS: {'; '.join(errors)}"
                print(f"  [{wf_id}] {wf.name} — {len(wf.steps)} steps — {status}")

        elif cmd == "start" and len(sys.argv) > 2:
            engine = WorkflowEngine()
            run = engine.start_workflow(sys.argv[2])
            print(json.dumps(run.summary(), indent=2))

        elif cmd == "advance":
            engine = WorkflowEngine()
            dispatched = engine.advance_all()
            print(f"Dispatched {len(dispatched)} steps:")
            for d in dispatched:
                print(f"  [{d['run_id']}] {d['step_id']} → {d['agent']}.{d['action']}")

        elif cmd == "status":
            engine = WorkflowEngine()
            print(json.dumps(engine.status(), indent=2))

        else:
            print("Usage: workflow_engine.py [install|list|start <workflow_id>|advance|status]")
    else:
        print("Workflow Engine")
        engine = WorkflowEngine()
        print(json.dumps(engine.status(), indent=2))
