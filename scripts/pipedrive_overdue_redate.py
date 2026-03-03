#!/usr/bin/env python3
"""Re-date Josef's overdue Pipedrive activities to today."""
from __future__ import annotations

import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[1] / ".secrets" / "pipedrive.env"


def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def api_request(base: str, token: str, method: str, path: str, params=None, data=None, retry: int = 3):
    params = dict(params or {})
    params["api_token"] = token
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"
    headers = {}
    body = None
    if data is not None:
        body = json.dumps(data).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)

    for attempt in range(retry):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="ignore")
            if exc.code in (429, 500, 502, 503, 504) and attempt < retry - 1:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise RuntimeError(f"HTTP {exc.code}: {raw[:300]}")


def paged_get(base: str, token: str, path: str, params):
    out = []
    start = 0
    limit = 500
    while True:
        query = dict(params)
        query.update({"start": start, "limit": limit})
        payload = api_request(base, token, "GET", path, params=query)
        if not payload.get("success"):
            raise RuntimeError(f"API error: {payload}")
        data = payload.get("data") or []
        out.extend(data)
        pagination = (payload.get("additional_data") or {}).get("pagination") or {}
        if not pagination.get("more_items_in_collection"):
            break
        start = pagination.get("next_start", start + limit)
    return out


def is_overdue(activity: dict, today: dt.date) -> bool:
    due = activity.get("due_date")
    if not due:
        return False
    try:
        due_date = dt.date.fromisoformat(due)
    except ValueError:
        return False
    return due_date < today


def main() -> int:
    env = load_env(ENV_PATH)
    base = env["PIPEDRIVE_BASE_URL"].rstrip("/")
    token = env["PIPEDRIVE_API_TOKEN"]
    user_id = int(env["PIPEDRIVE_USER_ID"])

    today = dt.date.today()

    activities = paged_get(
        base,
        token,
        "/api/v1/activities",
        {"user_id": user_id, "done": 0},
    )

    overdue = [a for a in activities if is_overdue(a, today)]
    if not overdue:
        print(json.dumps({"updated": 0, "message": "No overdue activities found."}))
        return 0

    updated = []
    today_iso = today.isoformat()
    for act in overdue:
        act_id = act.get("id")
        if not act_id:
            continue
        payload = {"due_date": today_iso}
        resp = api_request(base, token, "PUT", f"/api/v1/activities/{act_id}", data=payload)
        if resp.get("success"):
            updated.append({
                "activity_id": act_id,
                "deal_id": act.get("deal_id"),
                "subject": act.get("subject"),
                "previous_due_date": act.get("due_date"),
            })

    print(json.dumps({
        "updated": len(updated),
        "target_date": today_iso,
        "sample": updated[:10],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
