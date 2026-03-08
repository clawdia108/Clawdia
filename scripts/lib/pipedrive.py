"""Pipedrive & Fathom API helpers — shared across all scripts."""

import json
import logging
import urllib.parse
import urllib.request

PIPEDRIVE_BASE = "https://behavera.pipedrive.com"
FATHOM_BASE = "https://api.fathom.ai/external/v1"

log = logging.getLogger("clawdia.api")


def pipedrive_get(base_url, api_token, path, params=None):
    """GET request to Pipedrive API. Returns data list or []."""
    params = dict(params or {})
    params["api_token"] = api_token
    url = f"{base_url}{path}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url), timeout=20) as r:
            data = json.loads(r.read())
            if data.get("success"):
                return data.get("data") or []
    except Exception:
        pass
    return []


def pipedrive_api(token, method, path, data=None):
    """Full Pipedrive API request (GET/POST/PUT/DELETE).

    Returns data on success, None on error.
    """
    url = f"{PIPEDRIVE_BASE}/api/v1{path}"
    if method == "GET":
        params = {**(data or {}), "api_token": token}
        url += "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url)
    else:
        url += f"?api_token={token}"
        body = json.dumps(data or {}).encode()
        req = urllib.request.Request(url, data=body, method=method)
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            result = json.loads(r.read())
            if result.get("success"):
                return result.get("data")
    except Exception as e:
        log.warning("Pipedrive API error %s %s: %s", method, path, e)
    return None


def pipedrive_get_all(token, path, params=None):
    """Paginated GET — fetches all records automatically."""
    params = dict(params or {})
    all_data = []
    start = 0
    while True:
        params["start"] = str(start)
        params["limit"] = "100"
        batch = pipedrive_api(token, "GET", path, params)
        if not batch:
            break
        all_data.extend(batch)
        if len(batch) < 100:
            break
        start += 100
    return all_data


def pipedrive_search(token, entity, term, fields=None):
    """Search persons/orgs/deals in Pipedrive.

    entity: 'persons', 'organizations', 'deals'
    """
    params = {"term": term, "limit": "10"}
    if fields:
        params["fields"] = fields
    result = pipedrive_api(token, "GET", f"/{entity}/search", params)
    if result and result.get("items"):
        return result["items"]
    return []


def fathom_api(api_key, path, params=None):
    """Call Fathom API. Returns parsed JSON or None."""
    url = f"{FATHOM_BASE}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url)
    req.add_header("X-Api-Key", api_key)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        log.warning("Fathom API error %s: %s", path, e)
    return None
