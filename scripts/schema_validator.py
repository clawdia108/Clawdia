#!/usr/bin/env python3
"""
JSON Schema Validation — Validate all state files against defined schemas
==========================================================================
Defines schemas for every critical JSON state file.
Validates on read/write operations with clear error messages.

Usage:
  python3 scripts/schema_validator.py validate          # Validate all state files
  python3 scripts/schema_validator.py validate <file>    # Validate specific file
  python3 scripts/schema_validator.py fix <file>         # Auto-fix common issues
  python3 scripts/schema_validator.py schemas            # List all schemas
"""

import json
import sys
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/josefhofman/Clawdia")

# Schema definitions: path → schema
# Schema format: {"type": "object", "required": [...], "properties": {field: {"type": ...}}}
# Supports: "type" (str/int/float/list/dict/bool/null), "required", "properties", "min", "max"

SCHEMAS = {
    "knowledge/EXECUTION_STATE.json": {
        "type": "object",
        "required": ["last_orchestrator_run"],
        "properties": {
            "last_orchestrator_run": {"type": "str"},
            "tasks": {"type": "list"},
            "counts": {"type": "dict"},
            "system_health": {"type": "dict"},
            "stale_outputs": {"type": "list"},
            "approval_queue": {"type": "dict"},
            "cost_summary": {"type": "dict"},
        },
    },
    "reviews/daily-scorecard/score_state.json": {
        "type": "object",
        "required": ["total_points", "level"],
        "properties": {
            "total_points": {"type": "int", "min": 0},
            "current_streak": {"type": "int", "min": 0},
            "best_streak": {"type": "int", "min": 0},
            "level": {"type": "int", "min": 0},
            "title": {"type": "str"},
            "achievements": {"type": "list"},
            "daily_scores": {"type": "dict"},
        },
    },
    "control-plane/model-router.json": {
        "type": "object",
        "required": ["version"],
        "properties": {
            "version": {"type": "int", "min": 1},
            "default_model": {"type": "str"},
            "routes": {"type": "dict"},
        },
    },
    "control-plane/agent-states.json": {
        "type": "object",
        "required": [],
        "properties": {},
        "value_schema": {
            "type": "object",
            "required": ["state"],
            "properties": {
                "state": {"type": "str", "enum": ["idle", "assigned", "working", "reviewing", "done", "failed"]},
                "current_task": {"type": ["str", "null"]},
                "entered_state_at": {"type": "str"},
                "total_tasks_completed": {"type": "int", "min": 0},
                "total_tasks_failed": {"type": "int", "min": 0},
            },
        },
    },
    "control-plane/task-queue.json": {
        "type": "object",
        "required": ["tasks"],
        "properties": {
            "tasks": {"type": "list"},
            "next_id": {"type": "int"},
        },
    },
    "logs/cost-tracker.json": {
        "type": "object",
        "required": [],
        "properties": {
            "daily": {"type": "dict"},
            "total": {"type": "float", "min": 0},
            "by_model": {"type": "dict"},
            "by_task_type": {"type": "dict"},
        },
    },
    "logs/circuit-breaker.json": {
        "type": "object",
        "required": [],
        "properties": {},
        "value_schema": {
            "type": "object",
            "properties": {
                "failures": {"type": "int", "min": 0},
                "open": {"type": "bool"},
                "last_failure": {"type": ["str", "null"]},
            },
        },
    },
    "knowledge/AGENT_LEARNINGS.json": {
        "type": "object",
        "required": [],
        "properties": {
            "agent_scores": {"type": "dict"},
            "template_performance": {"type": "dict"},
            "routing_performance": {"type": "dict"},
            "total_outcomes": {"type": "int", "min": 0},
            "insights": {"type": "list"},
        },
    },
    "pipedrive/deal_velocity.json": {
        "type": "object",
        "required": [],
        "properties": {
            "deals": {"type": "dict"},
            "stage_averages": {"type": "dict"},
            "updated_at": {"type": "str"},
        },
    },
}


def validate_value(value, schema, path="$"):
    """Validate a value against a schema. Returns list of errors."""
    errors = []
    expected_type = schema.get("type")

    if expected_type:
        type_map = {
            "str": str, "int": int, "float": (int, float),
            "list": list, "dict": dict, "bool": bool, "null": type(None),
            "object": dict,
        }

        if isinstance(expected_type, list):
            # Union type
            valid = any(isinstance(value, type_map.get(t, type(None))) for t in expected_type)
            if not valid:
                errors.append(f"{path}: expected one of {expected_type}, got {type(value).__name__}")
        else:
            expected_cls = type_map.get(expected_type)
            if expected_cls and not isinstance(value, expected_cls):
                errors.append(f"{path}: expected {expected_type}, got {type(value).__name__}")

    # Check enum
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value '{value}' not in allowed values {schema['enum']}")

    # Check min/max
    if "min" in schema and isinstance(value, (int, float)) and value < schema["min"]:
        errors.append(f"{path}: value {value} below minimum {schema['min']}")
    if "max" in schema and isinstance(value, (int, float)) and value > schema["max"]:
        errors.append(f"{path}: value {value} above maximum {schema['max']}")

    # Check required fields
    if isinstance(value, dict) and "required" in schema:
        for req in schema["required"]:
            if req not in value:
                errors.append(f"{path}: missing required field '{req}'")

    # Validate properties
    if isinstance(value, dict) and "properties" in schema:
        for prop_name, prop_schema in schema["properties"].items():
            if prop_name in value:
                errors.extend(validate_value(value[prop_name], prop_schema, f"{path}.{prop_name}"))

    # Validate dict values against value_schema
    if isinstance(value, dict) and "value_schema" in schema:
        for key, val in value.items():
            errors.extend(validate_value(val, schema["value_schema"], f"{path}[{key}]"))

    return errors


def validate_file(rel_path):
    """Validate a single state file against its schema."""
    full_path = BASE / rel_path

    if not full_path.exists():
        return {"status": "skip", "path": rel_path, "reason": "file not found", "errors": []}

    schema = SCHEMAS.get(rel_path)
    if not schema:
        return {"status": "skip", "path": rel_path, "reason": "no schema defined", "errors": []}

    try:
        data = json.loads(full_path.read_text())
    except json.JSONDecodeError as e:
        return {"status": "fail", "path": rel_path, "reason": f"invalid JSON: {e}", "errors": [str(e)]}

    errors = validate_value(data, schema)

    return {
        "status": "pass" if not errors else "fail",
        "path": rel_path,
        "reason": f"{len(errors)} error(s)" if errors else "valid",
        "errors": errors,
    }


def validate_all():
    """Validate all state files."""
    results = []
    for rel_path in SCHEMAS:
        result = validate_file(rel_path)
        results.append(result)

    return results


def auto_fix(rel_path):
    """Attempt to auto-fix common issues in a state file."""
    full_path = BASE / rel_path
    schema = SCHEMAS.get(rel_path)
    if not schema or not full_path.exists():
        return False

    try:
        data = json.loads(full_path.read_text())
    except json.JSONDecodeError:
        return False

    fixed = False

    # Add missing required fields with defaults
    defaults = {
        "str": "", "int": 0, "float": 0.0,
        "list": [], "dict": {}, "bool": False,
    }

    for req in schema.get("required", []):
        if req not in data:
            prop_schema = schema.get("properties", {}).get(req, {})
            prop_type = prop_schema.get("type", "str")
            if isinstance(prop_type, list):
                prop_type = prop_type[0]
            data[req] = defaults.get(prop_type, None)
            fixed = True

    if fixed:
        full_path.write_text(json.dumps(data, indent=2, ensure_ascii=False))

    return fixed


def main():
    if len(sys.argv) < 2:
        # Default: validate all
        cmd = "validate"
    else:
        cmd = sys.argv[1]

    if cmd == "validate":
        if len(sys.argv) > 2:
            # Validate specific file
            rel_path = sys.argv[2]
            result = validate_file(rel_path)
            icon = {"pass": "PASS", "fail": "FAIL", "skip": "SKIP"}
            color = {"pass": "\033[0;32m", "fail": "\033[0;31m", "skip": "\033[0;36m"}
            print(f"  {color[result['status']]}{icon[result['status']]}\033[0m  {result['path']}: {result['reason']}")
            for err in result.get("errors", []):
                print(f"         {err}")
        else:
            # Validate all
            results = validate_all()
            passed = sum(1 for r in results if r["status"] == "pass")
            failed = sum(1 for r in results if r["status"] == "fail")
            skipped = sum(1 for r in results if r["status"] == "skip")

            print(f"\n{'='*50}")
            print(f"  JSON Schema Validation")
            print(f"{'='*50}\n")

            for r in results:
                icon = {"pass": "\033[0;32mPASS\033[0m", "fail": "\033[0;31mFAIL\033[0m",
                        "skip": "\033[0;36mSKIP\033[0m"}
                print(f"  {icon[r['status']]}  {r['path']}")
                if r["status"] == "fail":
                    for err in r.get("errors", [])[:5]:
                        print(f"         {err}")

            print(f"\n  {passed} passed, {failed} failed, {skipped} skipped")
            if failed == 0:
                print(f"  \033[0;32mAll validations passed!\033[0m\n")
            else:
                print(f"  \033[0;31m{failed} files need attention\033[0m\n")

    elif cmd == "fix" and len(sys.argv) > 2:
        rel_path = sys.argv[2]
        if auto_fix(rel_path):
            print(f"Fixed: {rel_path}")
        else:
            print(f"No fixes needed or unable to fix: {rel_path}")

    elif cmd == "schemas":
        print(f"\nDefined Schemas ({len(SCHEMAS)}):\n")
        for path, schema in SCHEMAS.items():
            required = schema.get("required", [])
            props = list(schema.get("properties", {}).keys())
            print(f"  {path}")
            print(f"    Required: {required or 'none'}")
            print(f"    Properties: {props[:5]}{'...' if len(props) > 5 else ''}")
            print()

    else:
        print("Usage: schema_validator.py [validate [file]|fix <file>|schemas]")


if __name__ == "__main__":
    main()
