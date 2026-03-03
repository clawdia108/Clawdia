#!/usr/bin/env python3
import argparse
import datetime as dt
import json
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

ENV_PATH = Path(__file__).resolve().parents[1] / ".secrets" / "pipedrive.env"
SUBJECT = "naplánovat další krok"
ACTIVITY_TYPE = "task"
WRITE_ACK = "YES"
CROSS_OWNER_ACK = "I_UNDERSTAND"
DEFAULT_MAX_CREATE = 25


def load_env(path: Path) -> dict:
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def parse_args():
    parser = argparse.ArgumentParser(
        description="Ensure open deals have an upcoming Pipedrive activity."
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually create missing activities. Defaults to dry-run.",
    )
    parser.add_argument(
        "--allow-owner-id",
        action="append",
        type=int,
        default=[],
        help="Additional owner id allowed in scope. Cross-owner writes still require an env ack.",
    )
    parser.add_argument(
        "--max-create",
        type=int,
        default=DEFAULT_MAX_CREATE,
        help=f"Safety cap for writes. Default: {DEFAULT_MAX_CREATE}.",
    )
    parser.add_argument(
        "--due-date",
        help="Override due date in YYYY-MM-DD format.",
    )
    return parser.parse_args()


def parse_owner_ids(raw: str) -> set[int]:
    owners = set()
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        owners.add(int(item))
    return owners


def next_business_day(d: dt.date) -> dt.date:
    d = d + dt.timedelta(days=1)
    while d.weekday() >= 5:  # 5=Sat, 6=Sun
        d += dt.timedelta(days=1)
    return d


def api_request(base: str, token: str, method: str, path: str, params=None, data=None, retry=3):
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
                time.sleep(1.5 * (i + 1))
                continue
            raise RuntimeError(f"HTTP {e.code}: {raw[:300]}")


def paged_get(base, token, path, params):
    out = []
    start = 0
    limit = 500
    while True:
        p = dict(params)
        p.update({"start": start, "limit": limit})
        j = api_request(base, token, "GET", path, params=p)
        if not j.get("success"):
            raise RuntimeError(f"API error: {j}")
        out.extend(j.get("data") or [])
        pag = (j.get("additional_data") or {}).get("pagination") or {}
        if not pag.get("more_items_in_collection"):
            break
        start = pag.get("next_start", start + limit)
    return out


def main():
    args = parse_args()
    env = load_env(ENV_PATH)
    base = env["PIPEDRIVE_BASE_URL"].rstrip("/")
    token = env["PIPEDRIVE_API_TOKEN"]
    my_user_id = int(env["PIPEDRIVE_USER_ID"])
    allowed_owner_ids = {my_user_id}
    allowed_owner_ids.update(parse_owner_ids(env.get("PIPEDRIVE_ALLOWED_OWNER_IDS", "")))
    allowed_owner_ids.update(args.allow_owner_id)
    cross_owner_ids = allowed_owner_ids - {my_user_id}

    if cross_owner_ids and env.get("PIPEDRIVE_CROSS_OWNER_WRITE_ACK") != CROSS_OWNER_ACK:
        raise SystemExit(
            "Refusing cross-owner scope without PIPEDRIVE_CROSS_OWNER_WRITE_ACK=I_UNDERSTAND"
        )

    all_open_deals = paged_get(base, token, "/api/v1/deals", {"status": "open"})
    open_deals = []
    for d in all_open_deals:
        owner = d.get("user_id")
        if isinstance(owner, dict):
            owner = owner.get("id")
        if owner in allowed_owner_ids:
            open_deals.append(d)

    open_ids = {d["id"] for d in open_deals}

    undone_activities = paged_get(base, token, "/api/v1/activities", {"done": 0})
    covered_deals = {
        a.get("deal_id")
        for a in undone_activities
        if a.get("deal_id") in open_ids
    }

    missing = [d for d in open_deals if d["id"] not in covered_deals]
    due_date = args.due_date or next_business_day(dt.date.today()).isoformat()
    if args.due_date:
        dt.date.fromisoformat(args.due_date)

    result = {
        "mode": "apply" if args.apply else "dry_run",
        "open_deals": len(open_deals),
        "covered_deals": len(covered_deals),
        "missing_before": len(missing),
        "subject": SUBJECT,
        "due_date": due_date,
        "allowed_owner_ids": sorted(allowed_owner_ids),
        "sample_missing_deal_ids": [d["id"] for d in missing[:10]],
    }

    if not args.apply:
        result["would_create"] = len(missing)
        result["write_guard"] = (
            "Set PIPEDRIVE_WRITE_ACK=YES and rerun with --apply to create activities."
        )
        print(json.dumps(result, ensure_ascii=False))
        return

    if env.get("PIPEDRIVE_WRITE_ACK") != WRITE_ACK:
        raise SystemExit("Refusing to write without PIPEDRIVE_WRITE_ACK=YES")

    if len(missing) > args.max_create:
        raise SystemExit(
            f"Refusing to create {len(missing)} activities; exceeds --max-create={args.max_create}"
        )

    created = 0
    for d in missing:
        owner = d.get("user_id", {})
        if isinstance(owner, dict):
            owner = owner.get("id")

        payload = {
            "subject": SUBJECT,
            "type": ACTIVITY_TYPE,
            "deal_id": d["id"],
            "due_date": due_date,
        }
        if owner:
            payload["user_id"] = owner

        j = api_request(base, token, "POST", "/api/v1/activities", data=payload)
        if j.get("success"):
            created += 1

    result["created"] = created
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
