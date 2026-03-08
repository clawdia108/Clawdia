#!/usr/bin/env python3
"""
LUSHA Contact Enricher — enriches Pipedrive deals with contact data from LUSHA API.

Usage:
    python3 scripts/lusha_enricher.py              # Scan + enrich (dry run)
    python3 scripts/lusha_enricher.py --write-back  # Scan + enrich + update Pipedrive
    python3 scripts/lusha_enricher.py --status       # Show credit usage

Free plan: 40 credits/month. Only enriches deals in sales stages 7-12
(Interested/Qualified through Pilot), prioritized by deal value descending.
Max 5 enrichments per run to preserve credits.
"""

import json
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, date
from pathlib import Path

from lib.paths import WORKSPACE
from lib.secrets import load_secrets
from lib.logger import make_logger
from lib.notifications import notify_telegram

# --- Config ---

ENRICHMENT_OUTPUT = WORKSPACE / "knowledge" / "LUSHA_ENRICHMENT.md"
CREDIT_TRACKER = WORKSPACE / "knowledge" / "lusha_credits.json"
MAX_ENRICHMENTS_PER_RUN = 5
MONTHLY_CREDIT_LIMIT = 40
LUSHA_BASE = "https://api.lusha.com"

# Sales stages worth enriching (qualified through pilot)
ENRICHABLE_STAGE_IDS = {7, 8, 28, 9, 10, 12}

STAGE_NAMES = {
    7: "Interested/Qualified",
    8: "Demo Scheduled",
    28: "Ongoing Discussion",
    9: "Proposal made",
    10: "Negotiation",
    12: "Pilot",
}

log = make_logger("lusha-enricher")


# --- Pipedrive helpers (urllib, no requests) ---

def pd_request(base, token, method, path, params=None, data=None, retry=3):
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
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504) and attempt < retry - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    return None


def pd_paged_get(base, token, path, params=None):
    out = []
    start = 0
    while True:
        p = dict(params or {})
        p.update({"start": start, "limit": 500})
        resp = pd_request(base, token, "GET", path, params=p)
        if not resp or not resp.get("success"):
            break
        out.extend(resp.get("data") or [])
        pag = (resp.get("additional_data") or {}).get("pagination") or {}
        if not pag.get("more_items_in_collection"):
            break
        start = pag.get("next_start", start + 500)
    return out


def pd_get_person(base, token, person_id):
    resp = pd_request(base, token, "GET", f"/api/v1/persons/{person_id}")
    if resp and resp.get("success"):
        return resp.get("data")
    return None


def pd_update_person(base, token, person_id, data):
    resp = pd_request(base, token, "PUT", f"/api/v1/persons/{person_id}", data=data)
    if resp and resp.get("success"):
        return resp.get("data")
    return None


# --- LUSHA API ---

def lusha_lookup(api_key, first_name, last_name, company):
    params = {
        "firstName": first_name,
        "lastName": last_name,
        "companyName": company,
    }
    url = f"{LUSHA_BASE}/v2/person?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"api_key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = json.loads(resp.read().decode("utf-8"))
            # LUSHA v2 wraps data in contact.data
            contact = raw.get("contact", {})
            if contact.get("error"):
                return {"error": contact["error"]}
            data = contact.get("data", {})
            return data
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        log(f"LUSHA API error {e.code}: {body}", "ERROR")
        if e.code == 429:
            log("LUSHA rate limit hit — stopping enrichments", "WARN")
            return {"error": "rate_limit"}
        if e.code == 403:
            log("LUSHA credits exhausted or invalid key", "WARN")
            return {"error": "credits_exhausted"}
        return {"error": f"http_{e.code}"}
    except Exception as e:
        log(f"LUSHA lookup failed: {e}", "ERROR")
        return {"error": str(e)}


# --- Credit tracking ---

def load_credits():
    if CREDIT_TRACKER.exists():
        try:
            data = json.loads(CREDIT_TRACKER.read_text())
            # Reset if month changed
            current_month = date.today().strftime("%Y-%m")
            if data.get("month") != current_month:
                return {"month": current_month, "used": 0, "log": []}
            return data
        except (json.JSONDecodeError, KeyError):
            pass
    return {"month": date.today().strftime("%Y-%m"), "used": 0, "log": []}


def save_credits(credits_data):
    CREDIT_TRACKER.parent.mkdir(exist_ok=True, parents=True)
    CREDIT_TRACKER.write_text(json.dumps(credits_data, indent=2))


def record_credit_use(credits_data, deal_title, contact_name, success):
    credits_data["used"] += 1
    credits_data["log"].append({
        "time": datetime.now().isoformat(),
        "deal": deal_title,
        "contact": contact_name,
        "success": success,
    })
    save_credits(credits_data)


# --- Contact analysis helpers ---

def person_has_email(person_data):
    if not person_data:
        return False
    emails = person_data.get("email", [])
    if isinstance(emails, list):
        return any(
            isinstance(e, dict) and e.get("value") and e["value"].strip()
            for e in emails
        )
    return False


def person_has_phone(person_data):
    if not person_data:
        return False
    phones = person_data.get("phone", [])
    if isinstance(phones, list):
        return any(
            isinstance(p, dict) and p.get("value") and p["value"].strip()
            for p in phones
        )
    return False


def extract_name_parts(person_data):
    if not person_data:
        return None, None
    name = person_data.get("name", "") or ""
    first = person_data.get("first_name", "") or ""
    last = person_data.get("last_name", "") or ""
    if first and last:
        return first.strip(), last.strip()
    parts = name.strip().split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    if len(parts) == 1:
        return parts[0], ""
    return None, None


# --- Main logic ---

def scan_deals(pd_base, pd_token):
    """Scan open deals, return (missing_contact, no_person) lists."""
    log("Fetching open deals from Pipedrive...")
    deals = pd_paged_get(pd_base, pd_token, "/api/v1/deals", {"status": "open"})
    log(f"Fetched {len(deals)} open deals")

    missing_contact = []  # has person but missing email/phone
    no_person = []        # has org but no person

    for deal in deals:
        stage_id = deal.get("stage_id")
        if stage_id not in ENRICHABLE_STAGE_IDS:
            continue

        org_name = deal.get("org_name") or ""
        deal_title = deal.get("title") or ""
        deal_value = deal.get("value") or 0
        deal_id = deal.get("id")

        # Check person_id — can be dict or int or None
        person_ref = deal.get("person_id")
        person_id = None
        person_name = None
        if isinstance(person_ref, dict):
            person_id = person_ref.get("id")
            person_name = person_ref.get("name")
        elif isinstance(person_ref, int) and person_ref > 0:
            person_id = person_ref

        if not person_id:
            if org_name:
                no_person.append({
                    "deal_id": deal_id,
                    "deal_title": deal_title,
                    "org_name": org_name,
                    "stage_id": stage_id,
                    "stage": STAGE_NAMES.get(stage_id, f"Stage {stage_id}"),
                    "value": deal_value,
                })
            continue

        # Fetch full person to check contact details
        person = pd_get_person(pd_base, pd_token, person_id)
        if not person:
            continue
        time.sleep(0.2)  # gentle rate limiting on Pipedrive

        has_email = person_has_email(person)
        has_phone = person_has_phone(person)

        if not has_email or not has_phone:
            first, last = extract_name_parts(person)
            missing_contact.append({
                "deal_id": deal_id,
                "deal_title": deal_title,
                "org_name": org_name,
                "stage_id": stage_id,
                "stage": STAGE_NAMES.get(stage_id, f"Stage {stage_id}"),
                "value": deal_value,
                "person_id": person_id,
                "person_name": person.get("name", ""),
                "first_name": first,
                "last_name": last,
                "has_email": has_email,
                "has_phone": has_phone,
            })

    # Sort by value descending (prioritize high-value deals)
    missing_contact.sort(key=lambda d: d["value"], reverse=True)
    no_person.sort(key=lambda d: d["value"], reverse=True)

    return missing_contact, no_person


def enrich_contacts(missing_contact, lusha_key, pd_base, pd_token, write_back):
    """Enrich contacts via LUSHA. Returns list of enrichment results."""
    credits = load_credits()
    remaining = MONTHLY_CREDIT_LIMIT - credits["used"]

    if remaining <= 0:
        log("No LUSHA credits remaining this month", "WARN")
        print(f"No LUSHA credits remaining ({credits['used']}/{MONTHLY_CREDIT_LIMIT} used)")
        return []

    budget = min(MAX_ENRICHMENTS_PER_RUN, remaining)
    candidates = [
        c for c in missing_contact
        if c.get("first_name") and c.get("org_name")
    ]

    if not candidates:
        log("No enrichable candidates (need first_name + org_name)")
        return []

    to_enrich = candidates[:budget]
    log(f"Enriching {len(to_enrich)} contacts (budget: {budget}, remaining credits: {remaining})")
    print(f"\nEnriching {len(to_enrich)} contacts (credits: {credits['used']}/{MONTHLY_CREDIT_LIMIT} used)")

    results = []

    for contact in to_enrich:
        first = contact["first_name"]
        last = contact["last_name"] or ""
        company = contact["org_name"]
        print(f"  Looking up: {first} {last} @ {company}...", end=" ")

        lusha_data = lusha_lookup(lusha_key, first, last, company)

        if lusha_data.get("error"):
            print(f"FAILED ({lusha_data['error']})")
            record_credit_use(credits, contact["deal_title"], f"{first} {last}", False)
            if lusha_data["error"] in ("rate_limit", "credits_exhausted"):
                break
            results.append({**contact, "enriched": False, "error": lusha_data["error"]})
            time.sleep(1)
            continue

        # Extract data from LUSHA v2 response (contact.data already unwrapped)
        email_found = None
        phone_found = None

        # LUSHA v2: emailAddresses [{email, emailType, emailConfidence}]
        emails = lusha_data.get("emailAddresses") or []
        if isinstance(emails, list) and emails:
            # Prefer work email
            for e in emails:
                if isinstance(e, dict) and e.get("emailType") == "work":
                    email_found = e.get("email")
                    break
            if not email_found and isinstance(emails[0], dict):
                email_found = emails[0].get("email")

        # LUSHA v2: phoneNumbers [{internationalNumber, localNumber, type}]
        phones = lusha_data.get("phoneNumbers") or []
        if isinstance(phones, list) and phones:
            for p in phones:
                if isinstance(p, dict):
                    phone_found = p.get("internationalNumber") or p.get("localNumber")
                    if phone_found:
                        break

        social = {}
        social_links = lusha_data.get("socialLinks") or {}
        if isinstance(social_links, dict) and social_links.get("linkedin"):
            social["linkedin"] = social_links["linkedin"]

        success = bool(email_found or phone_found)
        record_credit_use(credits, contact["deal_title"], f"{first} {last}", success)

        result = {
            **contact,
            "enriched": success,
            "email_found": email_found,
            "phone_found": phone_found,
            "social": social,
        }
        results.append(result)

        if success:
            print(f"FOUND (email: {'yes' if email_found else 'no'}, phone: {'yes' if phone_found else 'no'})")
        else:
            print("no data found")

        # Write back to Pipedrive if requested
        if write_back and success:
            update = {}
            if email_found and not contact["has_email"]:
                update["email"] = [{"value": email_found, "primary": True, "label": "work"}]
            if phone_found and not contact["has_phone"]:
                update["phone"] = [{"value": phone_found, "primary": True, "label": "work"}]

            if update:
                try:
                    pd_update_person(pd_base, pd_token, contact["person_id"], update)
                    log(f"Updated person {contact['person_id']} ({contact['person_name']}) in Pipedrive")
                    print(f"    -> Updated Pipedrive contact")
                except Exception as e:
                    log(f"Failed to update person {contact['person_id']}: {e}", "ERROR")
                    print(f"    -> Pipedrive update FAILED: {e}")

        time.sleep(1)  # be gentle with LUSHA rate limits

    return results


def write_report(results, missing_contact, no_person, credits_data):
    """Write LUSHA_ENRICHMENT.md report."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# LUSHA Enrichment Log",
        f"*Credits: {credits_data['used']}/{MONTHLY_CREDIT_LIMIT} used | Last run: {now}*",
        "",
    ]

    # Enriched contacts
    enriched = [r for r in results if r.get("enriched")]
    failed = [r for r in results if not r.get("enriched")]

    lines.append("## Enriched Contacts")
    lines.append("")
    if enriched:
        lines.append("| Deal | Company | Contact | Email Found | Phone Found |")
        lines.append("|------|---------|---------|-------------|-------------|")
        for r in enriched:
            email_cell = r.get("email_found") or "-"
            phone_cell = r.get("phone_found") or "-"
            lines.append(
                f"| {r['deal_title'][:30]} | {r['org_name'][:25]} "
                f"| {r['person_name'][:25]} | {email_cell} | {phone_cell} |"
            )
        lines.append("")
    else:
        lines.append("_No contacts enriched this run._")
        lines.append("")

    if failed:
        lines.append("## Failed Lookups")
        lines.append("")
        lines.append("| Deal | Company | Contact | Reason |")
        lines.append("|------|---------|---------|--------|")
        for r in failed:
            reason = r.get("error", "no data")
            lines.append(
                f"| {r['deal_title'][:30]} | {r['org_name'][:25]} "
                f"| {r.get('person_name', '-')[:25]} | {reason} |"
            )
        lines.append("")

    # Remaining candidates not yet enriched
    unenriched = [
        c for c in missing_contact
        if c["deal_id"] not in {r["deal_id"] for r in results}
    ]
    if unenriched:
        lines.append(f"## Remaining Candidates ({len(unenriched)} deals missing contact info)")
        lines.append("")
        lines.append("| Deal | Company | Contact | Missing |")
        lines.append("|------|---------|---------|---------|")
        for c in unenriched[:20]:
            missing = []
            if not c["has_email"]:
                missing.append("email")
            if not c["has_phone"]:
                missing.append("phone")
            lines.append(
                f"| {c['deal_title'][:30]} | {c['org_name'][:25]} "
                f"| {c['person_name'][:25]} | {', '.join(missing)} |"
            )
        if len(unenriched) > 20:
            lines.append(f"| ... | +{len(unenriched) - 20} more | | |")
        lines.append("")

    # Deals with no person at all
    if no_person:
        lines.append(f"## Deals Needing Contacts ({len(no_person)} deals with no person)")
        lines.append("")
        lines.append("| Deal | Company | Stage | Value |")
        lines.append("|------|---------|-------|-------|")
        for d in no_person[:20]:
            val = f"{d['value']:,.0f}" if d["value"] else "-"
            lines.append(
                f"| {d['deal_title'][:30]} | {d['org_name'][:25]} "
                f"| {d['stage']} | {val} |"
            )
        if len(no_person) > 20:
            lines.append(f"| ... | +{len(no_person) - 20} more | | |")
        lines.append("")

    # Credit usage history
    if credits_data.get("log"):
        lines.append("## Credit Usage This Month")
        lines.append("")
        lines.append("| Time | Deal | Contact | Result |")
        lines.append("|------|------|---------|--------|")
        for entry in credits_data["log"][-20:]:
            ts = entry.get("time", "")[:16]
            result = "found" if entry.get("success") else "miss"
            lines.append(
                f"| {ts} | {entry.get('deal', '-')[:25]} "
                f"| {entry.get('contact', '-')[:25]} | {result} |"
            )
        lines.append("")

    report = "\n".join(lines)
    ENRICHMENT_OUTPUT.parent.mkdir(exist_ok=True, parents=True)
    ENRICHMENT_OUTPUT.write_text(report)
    log(f"Report written to {ENRICHMENT_OUTPUT}")


def lusha_check_usage(api_key):
    """Check LUSHA account usage via GET /account/usage."""
    url = f"{LUSHA_BASE}/account/usage"
    req = urllib.request.Request(url, headers={"api_key": api_key})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        log(f"LUSHA usage check error {e.code}: {body}", "ERROR")
        return None
    except Exception as e:
        log(f"LUSHA usage check failed: {e}", "ERROR")
        return None


def show_status():
    """Show credit usage status, including live LUSHA account usage."""
    # Local tracking
    credits = load_credits()
    remaining = MONTHLY_CREDIT_LIMIT - credits["used"]
    print(f"\nLUSHA Credit Status ({credits['month']})")
    print(f"  Local tracking:")
    print(f"    Used:      {credits['used']}/{MONTHLY_CREDIT_LIMIT}")
    print(f"    Remaining: {remaining}")

    # Live LUSHA usage
    secrets = load_secrets()
    lusha_key = secrets.get("LUSHA_API_KEY")
    if lusha_key:
        usage = lusha_check_usage(lusha_key)
        if usage:
            print(f"\n  LUSHA Account (live):")
            for k, v in usage.items():
                print(f"    {k}: {v}")
    else:
        print("\n  (No LUSHA_API_KEY found — cannot check live usage)")

    if credits.get("log"):
        successful = sum(1 for e in credits["log"] if e.get("success"))
        print(f"\n  Successful: {successful}/{len(credits['log'])} lookups")
        print(f"\n  Recent lookups:")
        for entry in credits["log"][-5:]:
            ts = entry.get("time", "")[:16]
            result = "found" if entry.get("success") else "miss"
            print(f"    {ts} | {entry.get('deal', '-')[:30]} | {result}")

    if ENRICHMENT_OUTPUT.exists():
        mtime = datetime.fromtimestamp(ENRICHMENT_OUTPUT.stat().st_mtime)
        print(f"\n  Last report: {mtime.strftime('%Y-%m-%d %H:%M')}")
    print()


def main():
    if "--status" in sys.argv:
        show_status()
        return

    write_back = "--write-back" in sys.argv

    # Load secrets
    secrets = load_secrets()
    lusha_key = secrets.get("LUSHA_API_KEY")
    pd_base = secrets.get("PIPEDRIVE_BASE_URL", "").rstrip("/")
    pd_token = secrets.get("PIPEDRIVE_API_TOKEN", "")

    if not pd_base or not pd_token:
        log("Missing PIPEDRIVE_BASE_URL or PIPEDRIVE_API_TOKEN in secrets", "ERROR")
        print("ERROR: Missing Pipedrive credentials. Check .secrets/")
        sys.exit(1)

    if not lusha_key:
        log("Missing LUSHA_API_KEY in secrets", "ERROR")
        print("ERROR: Missing LUSHA_API_KEY. Add it to .secrets/ALL_CREDENTIALS.env")
        sys.exit(1)

    # Check credits before doing any work
    credits = load_credits()
    remaining = MONTHLY_CREDIT_LIMIT - credits["used"]
    print(f"LUSHA credits: {credits['used']}/{MONTHLY_CREDIT_LIMIT} used, {remaining} remaining")

    if remaining <= 0:
        print("No credits remaining this month. Skipping enrichment.")
        log("No credits remaining, aborting", "WARN")
        # Still scan and report
        missing_contact, no_person = scan_deals(pd_base, pd_token)
        write_report([], missing_contact, no_person, credits)
        print(f"\nReport written (scan only): {ENRICHMENT_OUTPUT}")
        return

    # Scan deals
    missing_contact, no_person = scan_deals(pd_base, pd_token)
    print(f"\nScan results:")
    print(f"  Deals missing contact info: {len(missing_contact)}")
    print(f"  Deals with no person:       {len(no_person)}")

    if not missing_contact:
        print("\nAll qualified deals have contact info. Nothing to enrich.")
        write_report([], missing_contact, no_person, credits)
        print(f"Report written: {ENRICHMENT_OUTPUT}")
        return

    # Enrich
    mode = "WRITE-BACK" if write_back else "DRY RUN"
    print(f"\nMode: {mode}")
    results = enrich_contacts(missing_contact, lusha_key, pd_base, pd_token, write_back)

    # Reload credits after enrichment
    credits = load_credits()

    # Write report
    write_report(results, missing_contact, no_person, credits)

    # Summary
    enriched_count = sum(1 for r in results if r.get("enriched"))
    print(f"\nDone. {enriched_count}/{len(results)} contacts enriched.")
    print(f"Credits used: {credits['used']}/{MONTHLY_CREDIT_LIMIT}")
    print(f"Report: {ENRICHMENT_OUTPUT}")

    log(f"Run complete: {enriched_count}/{len(results)} enriched, "
        f"credits {credits['used']}/{MONTHLY_CREDIT_LIMIT}, mode={mode}")

    # Notify if we found good data
    if enriched_count > 0:
        notify_telegram(
            f"LUSHA: enriched {enriched_count} contacts "
            f"(credits: {credits['used']}/{MONTHLY_CREDIT_LIMIT})"
        )


if __name__ == "__main__":
    main()
