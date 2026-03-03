# Briefs Queue
# CopyAgent kontroluje tento soubor při každém heartbeatu
# Nové briefy přidávej na začátek tabulky

Last checked: never
Next check: pending

---

## Aktivní briefy (seřazeno dle priority)

| ID | Type | Persona | Status | Priority | Deadline | Draft |
|----|------|---------|--------|----------|----------|-------|
| BRIEF-0001 | email | CEO | DONE | HIGH | 2026-03-04 | drafts/email-cold-ceo-v1.md |
| BRIEF-0002 | blog-post | HR/CEO | DONE | MEDIUM | 2026-03-07 | drafts/blog-proc-pruzkumy-nefunguji-v1.md |
| BRIEF-0003 | email | CEO | DONE | HIGH | 2026-03-05 | drafts/email-follow-up-day3-v1.md |

## Dokončené briefy
_(přesunout sem po delivery)_

## Poznámky
- Status: NEW → IN_PROGRESS → REVIEW → DONE
- CopyAgent bere první NEW brief s nejvyšší prioritou
- Pokud není žádný brief → self-improvement routine
