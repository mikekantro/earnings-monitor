#!/usr/bin/env python3
"""
pull_sp500_formula.py
---------------------
Pull S&P 500 (SP50) constituents via the FactSet FORMULA API ("functions" access),
using the FG_CONSTITUENTS universe-expansion function. This is the route that works
when the dedicated Benchmarks /constituents endpoint is NOT entitled but Formula is.

Confirmed from FactSet's official Formula SDK:
    universe = "FG_CONSTITUENTS(SP50,0,CLOSE)"   # expands index -> members
    formulas = ["FG_COMPANY_NAME", ...]          # data per member

Endpoint (you've used cross-sectional before, so it's entitled):
    POST https://api.factset.com/formula-api/v1/cross-sectional
    Auth: HTTP Basic (FACTSET_USERNAME : FACTSET_API_KEY)

Run on your Mac:
    export FACTSET_USERNAME="COREMAC-395908"
    export FACTSET_API_KEY="your-key"
    python3 pull_sp500_formula.py

This FIRST run is diagnostic: it prints the raw shape of the first few records and
saves the full response, so we can lock the parser to the exact field names your
entitlement returns before wiring it into the PMI backfill.
"""
import os, sys, json, requests

BASE = "https://api.factset.com/formula-api/v1/cross-sectional"
USER = os.environ.get("FACTSET_USERNAME")
KEY  = os.environ.get("FACTSET_API_KEY")
if not (USER and KEY):
    sys.exit("ERROR: export FACTSET_USERNAME and FACTSET_API_KEY first.")
AUTH = (USER, KEY)

# CONFIRMED items (from FactSet's Formula SDK example): FG_COMPANY_NAME, P_PRICE.
# The others are best-guess names; if any errors, the response will tell us which —
# we'll adjust. Keeping the list short keeps the first diagnostic run clean.
UNIVERSE = "FG_CONSTITUENTS(SP50,0,CLOSE)"
FORMULAS = [
    "FG_COMPANY_NAME",        # confirmed
    "FG_FACTSET_TICKER",      # ticker (verify name)
    "FG_BENCH_WGT(SP50,0)",   # S&P 500 weight (verify name)
]

def fetch():
    body = {"data": {"universe": UNIVERSE, "formulas": FORMULAS, "flatten": "Y"}}
    r = requests.post(BASE, json=body, auth=AUTH,
                      headers={"Accept": "application/json",
                               "Content-Type": "application/json"}, timeout=120)
    print(f"HTTP {r.status_code}")
    if r.status_code >= 400:
        print(r.text[:1500])
        if r.status_code == 403:
            print("\n403 -> 'functions'/FG_CONSTITUENTS still not entitled, or the "
                  "formula list hit an unauthorized item. Try FORMULAS=['FG_COMPANY_NAME'] only.")
        r.raise_for_status()
    return r.json()

def main():
    resp = fetch()
    json.dump(resp, open("sp500_formula_raw.json", "w"), indent=2)
    print("Saved full response -> sp500_formula_raw.json")

    # Defensive: the Formula API wraps rows under 'data' (flattened) in most cases.
    rows = resp.get("data") if isinstance(resp, dict) else resp
    if not isinstance(rows, list):
        print("\nUnexpected top-level shape. Top-level keys:",
              list(resp.keys()) if isinstance(resp, dict) else type(resp))
        print("Open sp500_formula_raw.json and paste me the structure.")
        return

    print(f"\nGot {len(rows)} rows.")
    print("\n--- first 3 raw records (so we can lock the parser) ---")
    for rec in rows[:3]:
        print(json.dumps(rec, indent=2)[:600])
        print("-")

    print("\nNEXT: paste those records back and I'll (1) finalize the ticker/weight "
          "field mapping, (2) write the list the PMI backfill consumes, and (3) decide "
          "cap-weighted vs equal-weighted scoring.")

if __name__ == "__main__":
    main()
