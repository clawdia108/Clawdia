#!/usr/bin/env python3
"""
Synthetic Test Data Generator — Create realistic pipeline test data
====================================================================
Generates fake but realistic deals, contacts, companies, and activities
for testing all Clawdia pipeline components in CI/CD.

Usage:
  python3 scripts/test_data_generator.py generate [--deals 50] [--dir test_data]
  python3 scripts/test_data_generator.py populate     # Fill all state files with test data
  python3 scripts/test_data_generator.py clean         # Remove test data
"""

import json
import random
import sys
import hashlib
from datetime import datetime, date, timedelta
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]

# ── NAME POOLS ──────────────────────────────────────

FIRST_NAMES = [
    "Jan", "Petr", "Martin", "Tomáš", "David", "Ondřej", "Jakub", "Filip",
    "Eva", "Lucie", "Tereza", "Michaela", "Klára", "Barbora", "Anna", "Martina",
    "Robert", "Jiří", "Pavel", "Radek", "Marek", "Lukáš", "Daniel", "Vojtěch",
]

LAST_NAMES = [
    "Novák", "Svoboda", "Novotný", "Dvořák", "Černý", "Procházka", "Kučera",
    "Veselý", "Horák", "Němec", "Marková", "Pokorná", "Pospíšilová", "Marek",
    "Hájek", "Jelínek", "Kadlec", "Kolář", "Šimek", "Bartoš", "Fiala",
]

COMPANIES = [
    ("Apify", "SaaS", 150), ("Keboola", "SaaS", 120), ("Rossum", "SaaS", 200),
    ("Emplifi", "SaaS", 500), ("Kiwi.com", "E-commerce", 800),
    ("Rohlík", "E-commerce", 400), ("Zásilkovna", "Logistics", 300),
    ("Productboard", "SaaS", 350), ("Mews", "SaaS", 250),
    ("Kentico", "SaaS", 200), ("JetBrains CZ", "SaaS", 150),
    ("Avast", "Cybersecurity", 600), ("GoodData", "SaaS", 180),
    ("Socialbakers", "SaaS", 220), ("Y Soft", "Manufacturing", 450),
    ("Cleverlance", "Consulting", 300), ("Seyfor", "SaaS", 280),
    ("Datamole", "SaaS", 50), ("Recombee", "SaaS", 40),
    ("Blindspot Solutions", "SaaS", 30), ("Adastra", "Consulting", 350),
    ("MSD IT", "Healthcare", 250), ("Innogy", "Energy", 500),
    ("PPF Group", "Fintech", 400), ("ČSOB", "Fintech", 300),
]

TITLES = [
    "CEO", "CTO", "CPO", "VP Engineering", "Head of HR",
    "HR Director", "People Operations Manager", "COO",
    "VP People", "Chief People Officer", "Head of Engineering",
]

STAGES = [
    ("Lead In", 0.15), ("Contacted", 0.25), ("Qualified", 0.40),
    ("Proposal Sent", 0.55), ("Demo Scheduled", 0.65),
    ("Negotiation", 0.75), ("Pilot", 0.85), ("Won", 1.0), ("Lost", 0.0),
]

DEAL_SIZES = [5000, 8000, 12000, 18000, 25000, 35000, 50000, 75000, 100000]

ACTIVITY_TYPES = ["email", "call", "meeting", "demo", "proposal", "note"]

LOSS_REASONS = [
    "Budget constraints", "Went with competitor", "No decision made",
    "Timing not right", "Internal restructuring", "Champion left company",
]


def _id():
    """Generate a random ID."""
    return random.randint(1000, 99999)


def generate_company(name, industry, size):
    return {
        "id": _id(),
        "name": name,
        "industry": industry,
        "employee_count": size + random.randint(-20, 50),
        "address": f"Prague {random.randint(1, 10)}, Czech Republic",
        "website": f"https://www.{name.lower().replace(' ', '')}.com",
        "created_at": (date.today() - timedelta(days=random.randint(30, 365))).isoformat(),
    }


def generate_contact(company):
    first = random.choice(FIRST_NAMES)
    last = random.choice(LAST_NAMES)
    domain = company["name"].lower().replace(" ", "")
    return {
        "id": _id(),
        "first_name": first,
        "last_name": last,
        "name": f"{first} {last}",
        "email": f"{first.lower()}.{last.lower()}@{domain}.com",
        "phone": f"+420 {random.randint(600, 799)} {random.randint(100, 999)} {random.randint(100, 999)}",
        "title": random.choice(TITLES),
        "company_id": company["id"],
        "company_name": company["name"],
    }


def generate_deal(company, contacts):
    stage_name, probability = random.choice(STAGES)
    champion = random.choice(contacts) if contacts else None
    days_ago = random.randint(5, 180)
    value = random.choice(DEAL_SIZES)

    deal = {
        "id": _id(),
        "title": f"{company['name']} — Echo Pulse",
        "value": value,
        "currency": "EUR",
        "stage": stage_name,
        "probability": probability,
        "company_id": company["id"],
        "company_name": company["name"],
        "contact_id": champion["id"] if champion else None,
        "contact_name": champion["name"] if champion else None,
        "created_at": (date.today() - timedelta(days=days_ago)).isoformat(),
        "updated_at": (date.today() - timedelta(days=random.randint(0, min(days_ago, 14)))).isoformat(),
        "expected_close": (date.today() + timedelta(days=random.randint(7, 90))).isoformat(),
        "pipeline_days": days_ago,
    }

    if stage_name == "Lost":
        deal["loss_reason"] = random.choice(LOSS_REASONS)
        deal["lost_at"] = (date.today() - timedelta(days=random.randint(1, 30))).isoformat()

    if stage_name == "Won":
        deal["won_at"] = (date.today() - timedelta(days=random.randint(1, 30))).isoformat()

    return deal


def generate_activities(deal, count=None):
    if count is None:
        count = random.randint(2, 12)
    activities = []
    start = datetime.fromisoformat(deal["created_at"])
    for i in range(count):
        act_date = start + timedelta(days=random.randint(1, max(1, deal["pipeline_days"])))
        activities.append({
            "id": _id(),
            "deal_id": deal["id"],
            "type": random.choice(ACTIVITY_TYPES),
            "subject": f"{'Follow-up' if i > 0 else 'Initial'} {random.choice(ACTIVITY_TYPES)} with {deal['company_name']}",
            "date": act_date.strftime("%Y-%m-%d"),
            "done": random.random() > 0.2,
            "note": f"Auto-generated test activity {i+1}",
        })
    return activities


def generate_full_dataset(n_deals=50):
    """Generate a complete dataset."""
    companies_data = []
    contacts_data = []
    deals_data = []
    activities_data = []

    # Use all companies, cycling if needed
    for i in range(n_deals):
        comp_info = COMPANIES[i % len(COMPANIES)]
        company = generate_company(*comp_info)
        companies_data.append(company)

        n_contacts = random.randint(1, 3)
        contacts = [generate_contact(company) for _ in range(n_contacts)]
        contacts_data.extend(contacts)

        deal = generate_deal(company, contacts)
        deals_data.append(deal)

        acts = generate_activities(deal)
        activities_data.extend(acts)

    dataset = {
        "generated_at": datetime.now().isoformat(),
        "generator": "clawdia-test-data-v1",
        "counts": {
            "companies": len(companies_data),
            "contacts": len(contacts_data),
            "deals": len(deals_data),
            "activities": len(activities_data),
        },
        "companies": companies_data,
        "contacts": contacts_data,
        "deals": deals_data,
        "activities": activities_data,
    }

    return dataset


def populate_state_files(dataset):
    """Fill state files with test data for integration testing."""
    deals = dataset["deals"]

    # Generate DEAL_SCORING.md
    lines = ["# Deal Scoring — Test Data\n"]
    lines.append(f"Generated: {datetime.now().isoformat()}\n")
    for d in sorted(deals, key=lambda x: x.get("value", 0), reverse=True):
        score = int(d["probability"] * 100) + random.randint(-10, 10)
        score = max(0, min(100, score))
        lines.append(f"\n## {d['title']}")
        lines.append(f"- Score: {score}")
        lines.append(f"- Stage: {d['stage']}")
        lines.append(f"- Value: €{d['value']:,}")
        lines.append(f"- Pipeline Days: {d['pipeline_days']}")
    (WORKSPACE / "pipedrive" / "DEAL_SCORING.md").write_text("\n".join(lines))

    # Generate PIPELINE_STATUS.md
    from collections import Counter
    stage_counts = Counter(d["stage"] for d in deals)
    stage_values = {}
    for d in deals:
        stage_values.setdefault(d["stage"], 0)
        stage_values[d["stage"]] += d["value"]

    lines = ["# Pipeline Status — Test Data\n"]
    for stage, count in stage_counts.most_common():
        lines.append(f"**{stage}**: {count} deals (€{stage_values.get(stage, 0):,.0f})")
    lines.append(f"\nTotal: {len(deals)} deals, €{sum(d['value'] for d in deals):,.0f}")
    won = sum(1 for d in deals if d["stage"] == "Won")
    lost = sum(1 for d in deals if d["stage"] == "Lost")
    lines.append(f"Won: {won} | Lost: {lost}")
    (WORKSPACE / "pipedrive" / "PIPELINE_STATUS.md").write_text("\n".join(lines))

    # Generate deal_velocity.json
    velocity = {"deals": {}, "stage_averages": {}, "updated_at": datetime.now().isoformat()}
    for stage, _ in STAGES:
        stage_deals = [d for d in deals if d["stage"] == stage]
        if stage_deals:
            velocity["stage_averages"][stage] = sum(d["pipeline_days"] for d in stage_deals) / len(stage_deals)
    for d in deals:
        velocity["deals"][str(d["id"])] = {
            "stage": d["stage"],
            "days_in_stage": random.randint(1, 30),
            "total_days": d["pipeline_days"],
        }
    (WORKSPACE / "pipedrive" / "deal_velocity.json").write_text(json.dumps(velocity, indent=2))

    print(f"  Populated state files with {len(deals)} test deals")


def clean_test_data():
    """Remove generated test data markers."""
    test_dir = WORKSPACE / "test_data"
    if test_dir.exists():
        import shutil
        shutil.rmtree(test_dir)
        print("  Removed test_data/")
    print("  Note: state files may still contain test data — restore from backup")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "generate"

    if cmd == "generate":
        n = 50
        for i, arg in enumerate(sys.argv):
            if arg == "--deals" and i + 1 < len(sys.argv):
                n = int(sys.argv[i + 1])

        dataset = generate_full_dataset(n)
        out_dir = WORKSPACE / "test_data"
        out_dir.mkdir(exist_ok=True)
        out_file = out_dir / "dataset.json"
        out_file.write_text(json.dumps(dataset, indent=2, ensure_ascii=False))

        print(f"\nTest Data Generated")
        print(f"  Companies: {dataset['counts']['companies']}")
        print(f"  Contacts: {dataset['counts']['contacts']}")
        print(f"  Deals: {dataset['counts']['deals']}")
        print(f"  Activities: {dataset['counts']['activities']}")
        print(f"  Output: {out_file}")

    elif cmd == "populate":
        ds_path = WORKSPACE / "test_data" / "dataset.json"
        if not ds_path.exists():
            print("No dataset — run `generate` first")
            return
        dataset = json.loads(ds_path.read_text())
        populate_state_files(dataset)

    elif cmd == "clean":
        clean_test_data()

    else:
        print("Usage: test_data_generator.py [generate [--deals N]|populate|clean]")


if __name__ == "__main__":
    main()
