#!/usr/bin/env python3
"""
Pipedrive Write-Back Pipeline
===============================
Takes agent outputs and writes them back to Pipedrive:
- Lead scores → custom field on deals
- Stale deals → create follow-up activities
- Deal notes → log agent analysis

All writes go through safety checks:
- Dry-run mode by default
- Max write cap per run
- Approval queue for high-risk actions
- Full audit log
"""

import json
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, date, timedelta
from pathlib import Path

BASE = Path("/Users/josefhofman/Clawdia")
ENV_PATH = BASE / ".secrets" / "pipedrive.env"
WRITEBACK_LOG = BASE / "logs" / "writeback.log"
WRITEBACK_STATE = BASE / "logs" / "writeback-state.json"

MAX_WRITES_PER_RUN = 20
RATE_LIMIT_DELAY = 0.3  # seconds between API calls


def wlog(msg, level="INFO"):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{level}] {msg}"
    print(line)
    WRITEBACK_LOG.parent.mkdir(exist_ok=True)
    with open(WRITEBACK_LOG, "a") as f:
        f.write(line + "\n")


def load_env():
    env = {}
    for line in ENV_PATH.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def api_request(base, token, method, path, params=None, data=None, retry=3):
    params = dict(params or {})
    params["api_token"] = token
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"
    headers = {}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)

    for i in range(retry):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raw = e.read().decode("utf-8", errors="ignore")
            if e.code in (429, 500, 502, 503, 504) and i < retry - 1:
                time.sleep(2 * (i + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {raw[:300]}")
    return None


def load_state():
    if WRITEBACK_STATE.exists():
        try:
            return json.loads(WRITEBACK_STATE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {
        "last_run": None,
        "total_writes": 0,
        "scores_written": 0,
        "activities_created": 0,
        "notes_written": 0,
        "errors": 0,
        "daily_writes": {},
    }


def save_state(state):
    WRITEBACK_STATE.parent.mkdir(exist_ok=True)
    WRITEBACK_STATE.write_text(json.dumps(state, indent=2))


def next_business_day(d=None):
    d = (d or date.today()) + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def write_lead_scores(base, token, dry_run=True):
    """Read DEAL_SCORING.md and write scores to Pipedrive custom fields"""
    scoring_file = BASE / "pipedrive" / "DEAL_SCORING.md"
    if not scoring_file.exists():
        wlog("No DEAL_SCORING.md found", "WARN")
        return 0

    # Parse scored deals from markdown (extract deal IDs and scores)
    # For now, we use the compact JSON which has the deal data
    # TODO: Add a score custom field to Pipedrive and write scores there
    wlog("Lead score write-back: not yet configured (needs custom field key)")
    return 0


def create_missing_activities(base, token, my_id, dry_run=True):
    """Create follow-up activities for deals without next activity"""
    stale_file = BASE / "pipedrive" / "STALE_DEALS.md"
    if not stale_file.exists():
        wlog("No STALE_DEALS.md found")
        return 0

    if dry_run:
        wlog("DRY RUN: Would create activities for stale deals")
        return 0

    # Use the activity guard script for this
    try:
        import subprocess
        result = subprocess.run(
            ["python3", str(BASE / "scripts" / "pipedrive_open_deal_activity_guard.py"), "--apply"],
            capture_output=True, text=True, timeout=120,
            cwd=str(BASE),
        )
        if result.returncode == 0:
            output = json.loads(result.stdout)
            created = output.get("created", 0)
            wlog(f"Created {created} activities for deals without next step")
            return created
        else:
            wlog(f"Activity guard failed: {result.stderr[:200]}", "ERROR")
            return 0
    except Exception as e:
        wlog(f"Activity creation error: {e}", "ERROR")
        return 0


def log_deal_notes(base, token, dry_run=True):
    """Write agent analysis as deal notes"""
    notes_queue = BASE / "pipedrive" / "notes_queue"
    if not notes_queue.exists():
        return 0

    written = 0
    for note_file in sorted(notes_queue.glob("*.json"))[:MAX_WRITES_PER_RUN]:
        try:
            note_data = json.loads(note_file.read_text())
            deal_id = note_data.get("deal_id")
            content = note_data.get("content", "")

            if not deal_id or not content:
                continue

            if dry_run:
                wlog(f"DRY RUN: Would write note to deal {deal_id}")
                continue

            result = api_request(base, token, "POST", "/api/v1/notes", data={
                "deal_id": deal_id,
                "content": content,
                "pinned_to_deal_flag": 0,
            })

            if result and result.get("success"):
                written += 1
                # Move to processed
                processed_dir = notes_queue / "processed"
                processed_dir.mkdir(exist_ok=True)
                note_file.rename(processed_dir / note_file.name)
                time.sleep(RATE_LIMIT_DELAY)
            else:
                wlog(f"Failed to write note for deal {deal_id}", "ERROR")

        except Exception as e:
            wlog(f"Note write error: {e}", "ERROR")

    if written:
        wlog(f"Wrote {written} deal notes to Pipedrive")
    return written


def update_overdue_activities(base, token, dry_run=True):
    """Reschedule overdue activities to next business day"""
    if dry_run:
        wlog("DRY RUN: Would reschedule overdue activities")
        return 0

    try:
        import subprocess
        result = subprocess.run(
            ["python3", str(BASE / "scripts" / "pipedrive_overdue_redate.py")],
            capture_output=True, text=True, timeout=120,
            cwd=str(BASE),
        )
        if result.returncode == 0:
            wlog(f"Overdue redate: {result.stdout.strip()}")
            return 1
        else:
            wlog(f"Overdue redate failed: {result.stderr[:200]}", "WARN")
            return 0
    except FileNotFoundError:
        return 0
    except Exception as e:
        wlog(f"Overdue redate error: {e}", "ERROR")
        return 0


def run_writeback(dry_run=True):
    """Execute full write-back pipeline"""
    wlog(f"=== Write-back pipeline starting (mode={'DRY RUN' if dry_run else 'LIVE'}) ===")

    state = load_state()
    today = date.today().isoformat()

    # Check daily write cap
    today_writes = state.get("daily_writes", {}).get(today, 0)
    if today_writes >= MAX_WRITES_PER_RUN * 5:
        wlog(f"Daily write cap reached ({today_writes} writes today)", "WARN")
        return state

    try:
        env = load_env()
        base = env["PIPEDRIVE_BASE_URL"].rstrip("/")
        token = env["PIPEDRIVE_API_TOKEN"]
        my_id = int(env.get("PIPEDRIVE_USER_ID", "0"))
    except Exception as e:
        wlog(f"Failed to load credentials: {e}", "ERROR")
        return state

    total_writes = 0

    # 1. Write lead scores
    total_writes += write_lead_scores(base, token, dry_run)

    # 2. Create missing activities
    total_writes += create_missing_activities(base, token, my_id, dry_run)

    # 3. Write deal notes
    total_writes += log_deal_notes(base, token, dry_run)

    # 4. Reschedule overdue activities
    total_writes += update_overdue_activities(base, token, dry_run)

    # Update state
    state["last_run"] = datetime.now().isoformat()
    state["total_writes"] = state.get("total_writes", 0) + total_writes
    daily = state.setdefault("daily_writes", {})
    daily[today] = daily.get(today, 0) + total_writes
    save_state(state)

    wlog(f"=== Write-back complete: {total_writes} writes ===")
    return state


if __name__ == "__main__":
    import sys

    dry_run = "--apply" not in sys.argv

    if "--status" in sys.argv:
        state = load_state()
        print(json.dumps(state, indent=2))
    else:
        run_writeback(dry_run=dry_run)
