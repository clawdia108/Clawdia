#!/usr/bin/env python3
"""
Dependency Checker — Pre-flight verification for all tools and packages
========================================================================
Verifies all required tools are installed and accessible.
Run automatically on orchestrator startup or manually before deployment.

Usage:
  python3 scripts/preflight.py          # Full check
  python3 scripts/preflight.py --quick  # Quick essentials only
"""

import importlib
import shutil
import subprocess
import sys
from pathlib import Path

BASE = Path("/Users/josefhofman/Clawdia")

# Check results
PASS = "\033[0;32mPASS\033[0m"
FAIL = "\033[0;31mFAIL\033[0m"
WARN = "\033[0;33mWARN\033[0m"
SKIP = "\033[0;36mSKIP\033[0m"


def check_command(name, cmd, min_version=None):
    """Check if a command-line tool is available."""
    path = shutil.which(name)
    if not path:
        return False, f"not found in PATH"

    if min_version:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            version = result.stdout.strip() or result.stderr.strip()
            return True, version.splitlines()[0][:60]
        except (subprocess.TimeoutExpired, OSError):
            return True, "found but version check failed"

    return True, path


def check_python_module(name):
    """Check if a Python module is importable."""
    try:
        mod = importlib.import_module(name)
        version = getattr(mod, "__version__", "installed")
        return True, str(version)
    except ImportError:
        return False, "not installed"


def check_file(path, description):
    """Check if a required file exists."""
    p = Path(path) if not isinstance(path, Path) else path
    if not p.exists():
        return False, "missing"
    size = p.stat().st_size
    return True, f"{size}B"


def check_directory(path, description):
    """Check if a required directory exists."""
    p = Path(path) if not isinstance(path, Path) else path
    if not p.exists():
        return False, "missing"
    count = len(list(p.iterdir()))
    return True, f"{count} items"


def check_service(service_name):
    """Check if a launchd service is loaded."""
    try:
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True, text=True, timeout=5,
        )
        if service_name in result.stdout:
            return True, "loaded"
        return False, "not loaded"
    except (subprocess.TimeoutExpired, OSError):
        return False, "launchctl not available"


def check_ollama():
    """Check if Ollama is running and has models."""
    try:
        result = subprocess.run(
            ["curl", "-s", "-m", "3", "http://localhost:11434/api/tags"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            models = [m["name"] for m in data.get("models", [])]
            if models:
                return True, ", ".join(models)
            return True, "running but no models"
        return False, "not responding"
    except Exception:
        return False, "not reachable"


def check_pid_running(pid_file):
    """Check if a PID file exists and the process is running."""
    if not pid_file.exists():
        return False, "no PID file"
    try:
        pid = int(pid_file.read_text().strip())
        result = subprocess.run(["kill", "-0", str(pid)], capture_output=True)
        if result.returncode == 0:
            return True, f"PID {pid}"
        return False, f"PID {pid} not running"
    except (ValueError, OSError):
        return False, "invalid PID file"


def run_checks(quick=False):
    """Run all pre-flight checks."""
    results = []
    total_pass = 0
    total_fail = 0
    total_warn = 0

    def add(category, name, ok, detail, critical=True):
        nonlocal total_pass, total_fail, total_warn
        if ok:
            total_pass += 1
            status = PASS
        elif critical:
            total_fail += 1
            status = FAIL
        else:
            total_warn += 1
            status = WARN
        results.append((category, name, status, detail))

    # ── System Tools ──
    print("\n\033[1m=== System Tools ===\033[0m")

    ok, d = check_command("python3", ["python3", "--version"])
    add("Tools", "Python 3", ok, d)

    ok, d = check_command("bash", ["bash", "--version"])
    add("Tools", "Bash", ok, d)

    ok, d = check_command("git", ["git", "--version"])
    add("Tools", "Git", ok, d)

    ok, d = check_command("curl", ["curl", "--version"])
    add("Tools", "curl", ok, d)

    ok, d = check_command("jq", ["jq", "--version"])
    add("Tools", "jq", ok, d, critical=False)

    if not quick:
        ok, d = check_command("gh", ["gh", "--version"])
        add("Tools", "GitHub CLI", ok, d, critical=False)

    # ── Python Modules ──
    print("\n\033[1m=== Python Modules ===\033[0m")

    for mod in ["json", "pathlib", "subprocess", "hashlib", "fcntl"]:
        ok, d = check_python_module(mod)
        add("Python", mod, ok, d)

    if not quick:
        for mod in ["http.server", "collections", "re"]:
            ok, d = check_python_module(mod)
            add("Python", mod, ok, d)

    # ── Services ──
    print("\n\033[1m=== Services ===\033[0m")

    ok, d = check_ollama()
    add("Services", "Ollama", ok, d, critical=False)

    ok, d = check_pid_running(BASE / "logs" / "orchestrator.pid")
    add("Services", "Orchestrator", ok, d)

    ok, d = check_service("com.clawdia.orchestrator")
    add("Services", "Launchd: orchestrator", ok, d, critical=False)

    ok, d = check_service("com.clawdia.heartbeat")
    add("Services", "Launchd: heartbeat", ok, d, critical=False)

    # ── Critical Files ──
    print("\n\033[1m=== Critical Files ===\033[0m")

    critical_files = [
        (BASE / ".secrets" / "ALL_CREDENTIALS.env", "Credentials"),
        (BASE / ".secrets" / "pipedrive.env", "Pipedrive env"),
        (BASE / "knowledge" / "EXECUTION_STATE.json", "Execution state"),
        (BASE / "control-plane" / "model-router.json", "Model router"),
        (BASE / "control-plane" / "agent-states.json", "Agent states"),
    ]

    for path, desc in critical_files:
        ok, d = check_file(path, desc)
        add("Files", desc, ok, d)

    # ── Directories ──
    print("\n\033[1m=== Directories ===\033[0m")

    required_dirs = [
        (BASE / "bus" / "outbox", "Bus outbox"),
        (BASE / "bus" / "inbox", "Bus inbox"),
        (BASE / "workflows" / "definitions", "Workflow definitions"),
        (BASE / "triggers" / "outbox", "Trigger outbox"),
        (BASE / "approval-queue" / "pending", "Approval queue"),
        (BASE / "logs", "Logs"),
    ]

    for path, desc in required_dirs:
        ok, d = check_directory(path, desc)
        add("Dirs", desc, ok, d)

    # ── Scripts ──
    if not quick:
        print("\n\033[1m=== Core Scripts ===\033[0m")
        core_scripts = [
            "orchestrator.py", "agent_bus.py", "workflow_engine.py",
            "agent_lifecycle.py", "adhd-scorecard.py", "agent_collaboration.py",
            "task_queue.py", "deal_velocity.py", "structured_log.py",
            "check_control_plane.py",
        ]
        for script in core_scripts:
            path = BASE / "scripts" / script
            ok, d = check_file(path, script)
            if ok:
                # Also check it compiles
                try:
                    compile(path.read_text(), str(path), "exec")
                    d = "OK (compiles)"
                except SyntaxError as e:
                    ok = False
                    d = f"SyntaxError: {e}"
            add("Scripts", script, ok, d)

    # ── Print Results ──
    print()
    for cat, name, status, detail in results:
        print(f"  {status}  {name:<25} {detail}")

    # ── Summary ──
    total = total_pass + total_fail + total_warn
    print(f"\n{'='*50}")
    print(f"  {total_pass} passed, {total_fail} failed, {total_warn} warnings")
    if total_fail == 0:
        print(f"  \033[0;32mAll critical checks passed!\033[0m")
    else:
        print(f"  \033[0;31m{total_fail} critical issues need attention\033[0m")
    print(f"{'='*50}\n")

    return total_fail == 0


if __name__ == "__main__":
    quick = "--quick" in sys.argv
    ok = run_checks(quick)
    sys.exit(0 if ok else 1)
