#!/usr/bin/env python3
"""
Claude Bridge — mailbox bridge between Clawdia and Claude Code CLI
===================================================================
Consumes requests from bus/inbox/claude/, runs them via `claude -p`,
stores results under bus/claude-results/, and sends a structured reply
back into the agent bus.

Usage:
    python3 scripts/claude_bridge.py once
    python3 scripts/claude_bridge.py daemon
    python3 scripts/claude_bridge.py status
    python3 scripts/claude_bridge.py send --source vyvojar --notify-agent vyvojar "Review this repo"
"""

import argparse
import json
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

from lib.paths import (
    WORKSPACE,
    BUS_INBOX,
    BUS_OUTBOX,
    BUS_PROCESSED,
    BUS_DEAD_LETTER,
    BUS_CLAUDE_RESULTS,
    LOGS_DIR,
)

CLAUDE_INBOX = BUS_INBOX / "claude"
CLAUDE_PROCESSED = BUS_PROCESSED / "claude"
CLAUDE_DEAD = BUS_DEAD_LETTER / "claude"
CLAUDE_LOG = LOGS_DIR / "claude-bridge.log"
POLL_INTERVAL = 30
DEFAULT_TIMEOUT_SECONDS = 900
DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_PERMISSION_MODE = "bypassPermissions"
AGENT_INBOX_ROOT = BUS_INBOX


def log(message, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {message}"
    CLAUDE_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(CLAUDE_LOG, "a") as handle:
        handle.write(line + "\n")
    print(line, flush=True)


def generate_id():
    return uuid.uuid4().hex[:16]


def ensure_dirs():
    for directory in [CLAUDE_INBOX, CLAUDE_PROCESSED, CLAUDE_DEAD, BUS_CLAUDE_RESULTS]:
        directory.mkdir(parents=True, exist_ok=True)


def safe_relpath(path):
    if not path:
        return None
    candidate = (WORKSPACE / path).resolve()
    try:
        candidate.relative_to(WORKSPACE)
    except ValueError as exc:
        raise ValueError(f"path escapes workspace: {path}") from exc
    return candidate


def build_prompt(payload):
    prompt = (payload.get("prompt") or "").strip()
    if not prompt:
        raise ValueError("payload.prompt is required")

    artifacts = payload.get("artifacts") or []
    if not artifacts:
        return prompt

    artifact_lines = ["Relevant workspace artifacts:"]
    for artifact in artifacts:
        artifact_lines.append(f"- {artifact}")
    artifact_lines.append("")
    artifact_lines.append(prompt)
    return "\n".join(artifact_lines)


def build_claude_command(payload):
    command = [
        "claude",
        "-p",
        "--output-format",
        payload.get("output_format", "json"),
        "--permission-mode",
        payload.get("permission_mode", DEFAULT_PERMISSION_MODE),
        "--model",
        payload.get("model", DEFAULT_MODEL),
    ]

    resume_session = payload.get("resume_session")
    if resume_session:
        command.extend(["--resume", resume_session])

    system_prompt = payload.get("system_prompt")
    if system_prompt:
        command.extend(["--system-prompt", system_prompt])

    append_system_prompt = payload.get("append_system_prompt")
    if append_system_prompt:
        command.extend(["--append-system-prompt", append_system_prompt])

    settings = payload.get("settings")
    if settings:
        command.extend(["--settings", json.dumps(settings) if isinstance(settings, dict) else str(settings)])

    allowed_tools = payload.get("allowed_tools") or payload.get("allowedTools")
    if allowed_tools:
        if isinstance(allowed_tools, (list, tuple)):
            allowed_tools = ",".join(str(item) for item in allowed_tools)
        command.extend(["--allowedTools", str(allowed_tools)])

    disallowed_tools = payload.get("disallowed_tools") or payload.get("disallowedTools")
    if disallowed_tools:
        if isinstance(disallowed_tools, (list, tuple)):
            disallowed_tools = ",".join(str(item) for item in disallowed_tools)
        command.extend(["--disallowedTools", str(disallowed_tools)])

    extra_dirs = payload.get("add_dirs") or []
    for extra_dir in extra_dirs:
        command.extend(["--add-dir", str(safe_relpath(extra_dir))])

    if payload.get("include_partial_messages"):
        command.append("--include-partial-messages")

    command.append(build_prompt(payload))
    return command


def parse_cli_output(stdout_text):
    text = stdout_text.strip()
    if not text:
        return {"text": "", "json": None}

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return {"text": text, "json": None}

    if isinstance(parsed, dict):
        result_text = parsed.get("result")
        if isinstance(result_text, str):
            return {"text": result_text.strip(), "json": parsed}
        messages = parsed.get("messages")
        if isinstance(messages, list):
            chunks = []
            for message in messages:
                if not isinstance(message, dict):
                    continue
                content = message.get("content")
                if isinstance(content, str):
                    chunks.append(content)
            return {"text": "\n".join(chunk for chunk in chunks if chunk).strip(), "json": parsed}

    return {"text": text, "json": parsed}


def write_result_file(request_id, message, payload, command, completed, stdout_text, stderr_text, parsed):
    result = {
        "request_id": request_id,
        "source": message.get("source"),
        "topic": message.get("topic"),
        "priority": message.get("priority", "P2"),
        "payload": payload,
        "command": command,
        "success": completed.returncode == 0,
        "exit_code": completed.returncode,
        "started_at": payload.get("_started_at"),
        "completed_at": datetime.now().isoformat(),
        "duration_seconds": round(time.time() - payload.get("_started_ts", time.time()), 2),
        "stdout": stdout_text,
        "stderr": stderr_text,
        "result_text": parsed["text"],
        "result_json": parsed["json"],
    }
    result_file = BUS_CLAUDE_RESULTS / f"{request_id}.json"
    result_file.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    return result_file


def maybe_write_output_artifact(payload, result_text):
    save_to = payload.get("save_to")
    if not save_to:
        return None
    target = safe_relpath(save_to)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(result_text or "")
    return target


def reply_target_for(message, payload):
    notify_agent = payload.get("notify_agent")
    if notify_agent and (AGENT_INBOX_ROOT / notify_agent).exists():
        return notify_agent

    source = message.get("source")
    if source and (AGENT_INBOX_ROOT / source).exists():
        return source

    return None


def publish_reply(message, payload, result_file, result_text, success, reason=""):
    target = reply_target_for(message, payload)
    if not target:
        return None

    topic = "claude.task_completed" if success else "claude.task_failed"
    reply_id = generate_id()
    reply_message = {
        "id": reply_id,
        "source": "claude-bridge",
        "topic": topic,
        "type": "EVENT",
        "payload": {
            "action": "claude_bridge_result",
            "request_id": message.get("id"),
            "source": message.get("source"),
            "success": success,
            "summary": (result_text or reason or "")[:1000],
            "result_file": str(result_file.relative_to(WORKSPACE)),
            "saved_output": payload.get("_saved_output"),
            "resume_session": payload.get("resume_session"),
            "model": payload.get("model", DEFAULT_MODEL),
        },
        "target": target,
        "priority": message.get("priority", "P2"),
        "ttl_hours": 24,
        "reply_to": message.get("id"),
        "correlation_id": message.get("correlation_id") or message.get("id") or reply_id,
        "created_at": datetime.now().isoformat(),
        "status": "pending",
        "delivery_attempts": 0,
        "max_retries": 3,
    }
    outbox_file = BUS_OUTBOX / f"{reply_message['priority']}_{reply_id}_{topic.replace('.', '_')}.json"
    BUS_OUTBOX.mkdir(parents=True, exist_ok=True)
    outbox_file.write_text(json.dumps(reply_message, indent=2, ensure_ascii=False))
    log(f"Reply queued for {target}: {topic} ({reply_id})")
    return outbox_file


def move_message(msg_file, destination_dir, extra=None):
    destination_dir.mkdir(parents=True, exist_ok=True)
    if not msg_file.exists():
        return
    try:
        payload = json.loads(msg_file.read_text())
    except (json.JSONDecodeError, OSError):
        payload = {"_raw_path": str(msg_file)}

    if extra:
        payload.update(extra)

    dest = destination_dir / msg_file.name
    dest.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    msg_file.unlink(missing_ok=True)


def process_message(msg_file):
    try:
        message = json.loads(msg_file.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        log(f"Malformed message {msg_file.name}: {exc}", "ERROR")
        move_message(msg_file, CLAUDE_DEAD, {"_reason": "malformed_json"})
        return False

    payload = dict(message.get("payload") or {})
    if payload.get("action") not in (None, "claude_run"):
        log(f"Unsupported Claude action in {msg_file.name}: {payload.get('action')}", "WARN")
        move_message(msg_file, CLAUDE_DEAD, {"_reason": "unsupported_action"})
        return False

    try:
        command = build_claude_command(payload)
    except Exception as exc:
        log(f"Invalid Claude payload in {msg_file.name}: {exc}", "ERROR")
        move_message(msg_file, CLAUDE_DEAD, {"_reason": f"invalid_payload: {exc}"})
        return False

    timeout_seconds = int(payload.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
    payload["_started_ts"] = time.time()
    payload["_started_at"] = datetime.now().isoformat()

    log(f"Running Claude request {message.get('id')} with model {payload.get('model', DEFAULT_MODEL)}")
    try:
        completed = subprocess.run(
            command,
            cwd=str(WORKSPACE),
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        stdout_text = completed.stdout
        stderr_text = completed.stderr
        parsed = parse_cli_output(stdout_text)
    except subprocess.TimeoutExpired as exc:
        stdout_text = exc.stdout or ""
        stderr_text = exc.stderr or ""
        parsed = {"text": "", "json": None}
        completed = subprocess.CompletedProcess(command, 124, stdout_text, stderr_text)
        stderr_text = (stderr_text or "") + "\nClaude request timed out."
    except Exception as exc:
        stdout_text = ""
        stderr_text = str(exc)
        parsed = {"text": "", "json": None}
        completed = subprocess.CompletedProcess(command, 1, stdout_text, stderr_text)

    result_file = write_result_file(
        message.get("id", generate_id()),
        message,
        payload,
        command,
        completed,
        stdout_text,
        stderr_text,
        parsed,
    )

    saved_output = maybe_write_output_artifact(payload, parsed["text"])
    payload["_saved_output"] = str(saved_output.relative_to(WORKSPACE)) if saved_output else None
    publish_reply(
        message,
        payload,
        result_file,
        parsed["text"],
        completed.returncode == 0,
        reason=stderr_text.strip(),
    )

    move_message(
        msg_file,
        CLAUDE_PROCESSED if completed.returncode == 0 else CLAUDE_DEAD,
        extra={
            "_processed_at": datetime.now().isoformat(),
            "_success": completed.returncode == 0,
            "_result_file": str(result_file.relative_to(WORKSPACE)),
            "_saved_output": payload["_saved_output"],
            "_exit_code": completed.returncode,
        },
    )

    if completed.returncode == 0:
        log(f"Claude request {message.get('id')} completed")
        return True

    log(f"Claude request {message.get('id')} failed: {stderr_text[:160]}", "ERROR")
    return False


def process_inbox(limit=3):
    ensure_dirs()
    messages = sorted(CLAUDE_INBOX.glob("*.json"))

    def priority_key(path):
        if path.name.startswith("P0"):
            return 0
        if path.name.startswith("P1"):
            return 1
        if path.name.startswith("P2"):
            return 2
        return 3

    messages.sort(key=priority_key)
    processed = 0
    failed = 0
    for msg_file in messages[:limit]:
        if process_message(msg_file):
            processed += 1
        else:
            failed += 1
    return processed, failed


def run_daemon():
    ensure_dirs()
    running = True

    def handle_signal(signum, _frame):
        nonlocal running
        log(f"Received signal {signum}, stopping Claude bridge.")
        running = False

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    log(f"Claude bridge daemon started (poll every {POLL_INTERVAL}s)")

    while running:
        try:
            processed, failed = process_inbox()
            if processed or failed:
                log(f"Cycle complete: processed={processed}, failed={failed}")
        except Exception as exc:
            log(f"Daemon cycle failed: {exc}", "ERROR")

        for _ in range(POLL_INTERVAL):
            if not running:
                break
            time.sleep(1)

    log("Claude bridge daemon stopped.")


def submit_request(prompt, source, notify_agent=None, priority="P2", model=None, resume_session=None):
    ensure_dirs()
    request_id = generate_id()
    message = {
        "id": request_id,
        "source": source,
        "topic": "claude.run",
        "type": "REQUEST",
        "priority": priority,
        "payload": {
            "action": "claude_run",
            "prompt": prompt,
            "model": model or DEFAULT_MODEL,
            "permission_mode": DEFAULT_PERMISSION_MODE,
            "notify_agent": notify_agent,
            "resume_session": resume_session,
        },
        "target": "claude",
        "created_at": datetime.now().isoformat(),
        "ttl_hours": 24,
        "correlation_id": request_id,
    }
    target = CLAUDE_INBOX / f"{priority}_{request_id}_claude_run.json"
    target.write_text(json.dumps(message, indent=2, ensure_ascii=False))
    return target


def show_status():
    ensure_dirs()
    pending = len(list(CLAUDE_INBOX.glob("*.json")))
    processed = len(list(CLAUDE_PROCESSED.glob("*.json")))
    dead = len(list(CLAUDE_DEAD.glob("*.json")))
    results = len(list(BUS_CLAUDE_RESULTS.glob("*.json")))
    print(f"\nClaude Bridge — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"Pending:   {pending}")
    print(f"Processed: {processed}")
    print(f"Dead:      {dead}")
    print(f"Results:   {results}")

    recent = sorted(BUS_CLAUDE_RESULTS.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)[:5]
    if recent:
        print("\nRecent results:")
        for item in recent:
            print(f"  - {item.name}")


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Mailbox bridge for Claude Code CLI")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("once")
    subparsers.add_parser("daemon")
    subparsers.add_parser("status")

    send_parser = subparsers.add_parser("send")
    send_parser.add_argument("prompt")
    send_parser.add_argument("--source", default="manual")
    send_parser.add_argument("--notify-agent", default=None)
    send_parser.add_argument("--priority", default="P2")
    send_parser.add_argument("--model", default=None)
    send_parser.add_argument("--resume-session", default=None)

    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    if args.command == "once":
        processed, failed = process_inbox()
        print(json.dumps({"processed": processed, "failed": failed}))
        return 0 if failed == 0 else 1
    if args.command == "daemon":
        run_daemon()
        return 0
    if args.command == "status":
        show_status()
        return 0
    if args.command == "send":
        target = submit_request(
            prompt=args.prompt,
            source=args.source,
            notify_agent=args.notify_agent,
            priority=args.priority,
            model=args.model,
            resume_session=args.resume_session,
        )
        print(str(target.relative_to(WORKSPACE)))
        return 0

    print("Usage: claude_bridge.py [once|daemon|status|send]")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
