# Codex Task: Refaktor duplikovaného Pipedrive API kódu

## Priority: MEDIUM
## Assigned: 2026-03-08
## Status: PENDING

## Problém
Funkce `pipedrive_api(token, method, path, data)` je copy-pasted v 8+ skriptech:
- scripts/followup_engine.py
- scripts/weekly_intel.py
- scripts/deal_health_scorer.py
- scripts/signal_scanner.py
- scripts/fathom_sync.py
- scripts/tldv_sync.py
- scripts/spin_prep_generator.py
- scripts/post_call_processor.py

Stejný kód ~20 řádků je duplikovaný 8x.

## Co udělat

### 1. Rozšiř `scripts/lib/pipedrive.py`
Už existuje `pipedrive_get()`. Přidej plnou `pipedrive_api(token, method, path, data=None)` funkci:
- GET: query params s api_token
- POST/PUT/DELETE: JSON body
- Error handling s logováním
- Timeout 20s
- Return data on success, None on error

### 2. Přidej helper funkce
```python
def pipedrive_get_all(token, path, params=None):
    """Paginated GET — fetches all records."""
    # Handles start/limit pagination automatically

def pipedrive_search(token, entity, term, fields=None):
    """Search persons/orgs/deals."""
```

### 3. Nahraď ve všech 8 skriptech
Nahraď lokální `pipedrive_api()` za:
```python
from lib.pipedrive import pipedrive_api
```

### 4. Testy
Ověř, že všechny skripty stále fungují:
```bash
python3 scripts/followup_engine.py --scan
python3 scripts/weekly_intel.py --stdout
python3 scripts/deal_health_scorer.py --deal 360
python3 scripts/signal_scanner.py --list
python3 scripts/fathom_sync.py --list
```

## Pravidla
- NECOMMITUJ bez schválení
- Neměň logiku, jen přesuň kód
- Zachovej zpětnou kompatibilitu
- Base URL: `https://behavera.pipedrive.com`

## Výstup
- Rozšířený `scripts/lib/pipedrive.py`
- 8 skriptů s importem místo lokální funkce
- Commit message: "refactor: deduplicate pipedrive_api into shared lib"
