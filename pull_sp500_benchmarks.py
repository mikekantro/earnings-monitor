#!/usr/bin/env python3
"""
pull_sp500_benchmarks.py
------------------------
Fetch S&P 500 (benchmark id SP50) constituents from the FactSet Benchmarks API,
now that the Benchmarks entitlement is enabled for serial COREMAC-395908.

Endpoint (from your benchmarks-api spec):
    GET https://api.factset.com/content/factset-benchmarks/v1/constituents
        ?ids=SP50&date=YYYY-MM-DD&currency=USD
    Auth: HTTP Basic (FACTSET_USERNAME : FACTSET_API_KEY)

Run on your Mac (FactSet creds + network live there, NOT in the Claude sandbox):
    export FACTSET_USERNAME="COREMAC-395908"
    export FACTSET_API_KEY="your-key"
    python3 pull_sp500_benchmarks.py                 # as of today
    python3 pull_sp500_benchmarks.py 2026-03-31      # as of a specific date
"""
import os, sys, json, datetime, requests

BASE = "https://api.factset.com/content"
USER = os.environ.get("FACTSET_USERNAME")
KEY  = os.environ.get("FACTSET_API_KEY")
if not (USER and KEY):
    sys.exit("ERROR: export FACTSET_USERNAME and FACTSET_API_KEY first.")
AUTH = (USER, KEY)


def fetch_constituents(benchmark="SP50", date=None, currency="USD"):
    if date is None:
        date = datetime.date.today().isoformat()
    url = f"{BASE}/factset-benchmarks/v1/constituents"
    params = {"ids": benchmark, "date": date, "currency": currency}
    r = requests.get(url, params=params, auth=AUTH,
                     headers={"Accept": "application/json"}, timeout=60)
    if r.status_code == 403:
        sys.exit("403 Forbidden — serial still not entitled for Benchmarks. "
                 "If you just turned it on, give it a few minutes or check the "
                 "exact product name with your FactSet rep.")
    r.raise_for_status()
    return r.json().get("data", [])


def main():
    date = sys.argv[1] if len(sys.argv) > 1 else datetime.date.today().isoformat()
    print(f"Fetching SP50 constituents as of {date} ...")
    data = fetch_constituents("SP50", date)

    # keep equity holdings (-R regional ids); drop cash/generic rows
    rows = [c for c in data if "-R" in str(c.get("fsymRegionalId") or "")]
    rows.sort(key=lambda c: (c.get("weightClose") or 0), reverse=True)

    out = [{
        "fsymRegionalId": c.get("fsymRegionalId"),
        "fsymSecurityId": c.get("fsymSecurityId"),
        "weight":         c.get("weightClose"),
        "price":          c.get("price"),
        "marketValueMM":  c.get("adjMarketValue"),
        "date":           c.get("date"),
    } for c in rows]

    json.dump(out, open("sp500_constituents.json", "w"), indent=2)
    print(f"Got {len(out)} constituents (raw rows incl. cash/generic: {len(data)})")
    print("Saved -> sp500_constituents.json")

    print("\nTop 10 by index weight:")
    for c in out[:10]:
        w  = c["weight"] or 0
        mv = c["marketValueMM"] or 0
        print(f"  {c['fsymRegionalId']:12s}  w={w:6.3f}%   mktval={mv:>12,.0f}MM")

    tot = sum((c["weight"] or 0) for c in out)
    print(f"\nWeights sum to {tot:.2f}% (sanity check, should be ~100).")
    print("\nNEXT: map fsymRegionalId -> ticker, then feed into the PMI backfill.")
    print("See the ticker-mapping note in chat.")


if __name__ == "__main__":
    main()
