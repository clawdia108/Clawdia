#!/usr/bin/env python3
"""
Backup System — Snapshot critical state files with auto-rotation
================================================================
Snapshots all critical state files every hour into backups/.
Keeps last 48 snapshots, auto-rotates older ones.
Restore command to roll back to any snapshot.

Usage:
  python3 scripts/backup_system.py snapshot    # Create snapshot now
  python3 scripts/backup_system.py list        # List available snapshots
  python3 scripts/backup_system.py restore <timestamp>  # Restore snapshot
  python3 scripts/backup_system.py rotate      # Clean old snapshots
  python3 scripts/backup_system.py verify      # Verify latest snapshot integrity
"""

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

BASE = Path("/Users/josefhofman/Clawdia")
BACKUP_DIR = BASE / "backups"
MAX_SNAPSHOTS = 48

# Critical files to backup
CRITICAL_FILES = [
    "knowledge/EXECUTION_STATE.json",
    "reviews/daily-scorecard/score_state.json",
    "control-plane/model-router.json",
    "control-plane/agent-states.json",
    "control-plane/task-queue.json",
    "control-plane/agent-load.json",
    "logs/cost-tracker.json",
    "logs/circuit-breaker.json",
    "logs/notification-state.json",
    "logs/agent-performance.json",
    "knowledge/AGENT_LEARNINGS.json",
    "pipedrive/deal_velocity.json",
    "pipedrive/cadences.json",
    "knowledge/graph.json",
    "pipedrive/DEAL_SCORING.md",
    "pipedrive/PIPELINE_STATUS.md",
    "pipedrive/STALE_DEALS.md",
    "knowledge/USER_DIGEST_AM.md",
    "memory/HEARTBEAT.md",
]


def create_snapshot():
    """Create a timestamped snapshot of all critical files."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    snap_dir = BACKUP_DIR / ts
    snap_dir.mkdir(parents=True, exist_ok=True)

    backed_up = 0
    manifest = {"timestamp": datetime.now().isoformat(), "files": {}}

    for rel_path in CRITICAL_FILES:
        src = BASE / rel_path
        if not src.exists():
            continue

        # Preserve directory structure in backup
        dest = snap_dir / rel_path
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dest))
        backed_up += 1

        manifest["files"][rel_path] = {
            "size": src.stat().st_size,
            "mtime": datetime.fromtimestamp(src.stat().st_mtime).isoformat(),
        }

    # Write manifest
    manifest["backed_up"] = backed_up
    (snap_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))

    print(f"Snapshot created: {ts} ({backed_up} files)")
    return ts


def list_snapshots():
    """List all available snapshots."""
    if not BACKUP_DIR.exists():
        print("No backups found")
        return []

    snapshots = sorted(
        [d for d in BACKUP_DIR.iterdir() if d.is_dir() and (d / "MANIFEST.json").exists()],
        key=lambda d: d.name,
        reverse=True,
    )

    if not snapshots:
        print("No backups found")
        return []

    print(f"{'Timestamp':<20} {'Files':<8} {'Size':<10}")
    print("-" * 40)
    for snap in snapshots:
        try:
            manifest = json.loads((snap / "MANIFEST.json").read_text())
            files = manifest.get("backed_up", "?")
            # Calculate total size
            total = sum(f.stat().st_size for f in snap.rglob("*") if f.is_file())
            size_str = f"{total / 1024:.1f}KB" if total < 1_000_000 else f"{total / 1_000_000:.1f}MB"
            print(f"{snap.name:<20} {files:<8} {size_str:<10}")
        except (json.JSONDecodeError, OSError):
            print(f"{snap.name:<20} {'?':<8} {'?':<10}")

    return snapshots


def restore_snapshot(timestamp):
    """Restore files from a snapshot."""
    snap_dir = BACKUP_DIR / timestamp
    if not snap_dir.exists():
        print(f"Snapshot not found: {timestamp}")
        return False

    manifest_path = snap_dir / "MANIFEST.json"
    if not manifest_path.exists():
        print(f"Invalid snapshot (no manifest): {timestamp}")
        return False

    manifest = json.loads(manifest_path.read_text())

    # First, create a safety backup of current state
    safety_ts = create_snapshot()
    print(f"Safety backup created: {safety_ts}")

    restored = 0
    for rel_path in manifest.get("files", {}).keys():
        src = snap_dir / rel_path
        dest = BASE / rel_path
        if src.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dest))
            restored += 1

    print(f"Restored {restored} files from snapshot {timestamp}")
    return True


def rotate_snapshots():
    """Remove old snapshots beyond MAX_SNAPSHOTS."""
    if not BACKUP_DIR.exists():
        return 0

    snapshots = sorted(
        [d for d in BACKUP_DIR.iterdir() if d.is_dir()],
        key=lambda d: d.name,
    )

    removed = 0
    while len(snapshots) > MAX_SNAPSHOTS:
        oldest = snapshots.pop(0)
        shutil.rmtree(str(oldest))
        removed += 1

    if removed:
        print(f"Rotated {removed} old snapshots (keeping {MAX_SNAPSHOTS})")
    else:
        print(f"No rotation needed ({len(snapshots)}/{MAX_SNAPSHOTS} snapshots)")
    return removed


def verify_latest():
    """Verify the latest snapshot is valid."""
    if not BACKUP_DIR.exists():
        print("No backups to verify")
        return False

    snapshots = sorted(
        [d for d in BACKUP_DIR.iterdir() if d.is_dir() and (d / "MANIFEST.json").exists()],
        key=lambda d: d.name,
        reverse=True,
    )

    if not snapshots:
        print("No valid snapshots found")
        return False

    latest = snapshots[0]
    manifest = json.loads((latest / "MANIFEST.json").read_text())

    print(f"Verifying snapshot: {latest.name}")
    errors = 0
    for rel_path, info in manifest.get("files", {}).items():
        backup_file = latest / rel_path
        if not backup_file.exists():
            print(f"  MISSING: {rel_path}")
            errors += 1
            continue

        actual_size = backup_file.stat().st_size
        expected_size = info.get("size", 0)
        if actual_size != expected_size:
            print(f"  SIZE MISMATCH: {rel_path} (expected {expected_size}, got {actual_size})")
            errors += 1

        # For JSON files, verify parseable
        if rel_path.endswith(".json"):
            try:
                json.loads(backup_file.read_text())
            except json.JSONDecodeError:
                print(f"  CORRUPT JSON: {rel_path}")
                errors += 1

    if errors:
        print(f"Verification FAILED: {errors} errors")
    else:
        print(f"Verification PASSED: {manifest.get('backed_up', '?')} files OK")

    return errors == 0


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "snapshot"

    if cmd == "snapshot":
        create_snapshot()
    elif cmd == "list":
        list_snapshots()
    elif cmd == "restore" and len(sys.argv) > 2:
        restore_snapshot(sys.argv[2])
    elif cmd == "rotate":
        rotate_snapshots()
    elif cmd == "verify":
        verify_latest()
    else:
        print("Usage: backup_system.py [snapshot|list|restore <timestamp>|rotate|verify]")
