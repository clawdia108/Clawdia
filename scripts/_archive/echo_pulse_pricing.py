#!/usr/bin/env python3
"""Echo Pulse Pricing Calculator

Purpose: give Josef instant pricing + ROI talking points for Echo Pulse demos.
Inputs: employee count (required) plus optional salary assumptions, pilots, and discounts.
Outputs: human-readable table AND (optionally) JSON for pasting into CRM / emails.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from datetime import date
from textwrap import dedent

DEFAULT_SALARY = 70000  # CZK, fully loaded monthly cost (assumption)
PILOT_PRICE = 29900  # CZK, 3-month pilot flat fee up to 200 people
PRICE_TIERS = [
    (50, 129),   # 50-79 employees
    (80, 119),   # 80-119 employees
    (120, 109),  # 120-159 employees
    (160, 99),   # 160-200 employees
]
MAX_EMPLOYEES = 200


@dataclass
class PricingScenario:
    label: str
    per_person_czk: float
    employees: int

    @property
    def monthly_total(self) -> float:
        return self.per_person_czk * self.employees

    @property
    def quarterly_total(self) -> float:
        return self.monthly_total * 3

    def to_dict(self):
        d = asdict(self)
        d.update({
            "monthly_total_czk": round(self.monthly_total, 2),
            "quarterly_total_czk": round(self.quarterly_total, 2),
        })
        return d


def pick_price(employees: int) -> list[PricingScenario]:
    scenarios: list[PricingScenario] = []
    for lower_bound, price in PRICE_TIERS:
        if employees >= lower_bound:
            label = f"{price} CZK/person (≥{lower_bound})"
            scenarios.append(PricingScenario(label, price, employees))
    # Always add premium tier (129) so Josef can anchor higher price
    if not any(s.per_person_czk == 129 for s in scenarios):
        scenarios.insert(0, PricingScenario("129 CZK/person (premium)", 129, employees))
    return scenarios


def attrition_cost(salary_czk: float) -> tuple[float, float]:
    """Return low/high attrition cost based on 6-12 months fully-loaded salary."""
    return salary_czk * 6, salary_czk * 12


def roi_statement(pilot_cost: float, salary_czk: float) -> str:
    low, high = attrition_cost(salary_czk)
    roi_low = low / pilot_cost
    return (
        f"Jedna zbytečná výpověď (6–12 platů ≈ {low:,.0f}–{high:,.0f} Kč) stojí {roi_low:.1f}× víc "
        f"než pilot Echo Pulse za {pilot_cost:,.0f} Kč."
    )


def render_table(scenarios: list[PricingScenario]) -> str:
    header = "| Varianta | Cena/osoba | Měsíčně | 3 měsíce |"
    sep = "|---|---|---|---|"
    rows = [header, sep]
    for s in scenarios:
        rows.append(
            "| {label} | {pp:,.0f} Kč | {m:,.0f} Kč | {q:,.0f} Kč |".format(
                label=s.label,
                pp=s.per_person_czk,
                m=s.monthly_total,
                q=s.quarterly_total,
            )
        )
    return "\n".join(rows)


def build_summary(employees: int, salary: float, include_json: bool) -> str:
    scenarios = pick_price(employees)
    pilot_note = (
        f"Pilot na 3 měsíce: {PILOT_PRICE:,.0f} Kč flat (až {MAX_EMPLOYEES} lidí)."
    )
    roi = roi_statement(PILOT_PRICE, salary)
    table_md = render_table(scenarios)

    lines = [
        f"• Počet lidí: {employees}",
        "• Doporučené price pointy (podle velikosti):",
        table_md,
        f"• {pilot_note}",
        f"• ROI: {roi}",
        f"• Vzorec: Echo Pulse 99–129 Kč / osoba / měsíc, cap {MAX_EMPLOYEES} lidí.",
    ]

    if include_json:
        payload = {
            "generated": date.today().isoformat(),
            "employees": employees,
            "pilot_price_czk": PILOT_PRICE,
            "salary_assumption_czk": salary,
            "roi_statement": roi,
            "scenarios": [s.to_dict() for s in scenarios],
        }
        lines.append("\nJSON:\n" + json.dumps(payload, indent=2, ensure_ascii=False))
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Echo Pulse pricing helper")
    parser.add_argument("employees", type=int, help="Headcount to price (50-200)")
    parser.add_argument("--salary", type=float, default=DEFAULT_SALARY,
                        help="Average fully loaded monthly salary in CZK (default: 70k)")
    parser.add_argument("--json", action="store_true", help="Append JSON payload")
    args = parser.parse_args()
    if args.employees < 1:
        parser.error("Employee count must be positive")
    if args.employees > MAX_EMPLOYEES:
        parser.error(f"Employee count capped at {MAX_EMPLOYEES} for pilot pricing")
    return args


def main():
    args = parse_args()
    summary = build_summary(args.employees, args.salary, args.json)
    print(summary)


if __name__ == "__main__":
    main()
