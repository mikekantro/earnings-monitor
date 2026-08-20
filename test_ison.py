#!/usr/bin/env python3
"""
test_ison.py
------------
Find the correct, entitled FactSet membership formula by testing candidate
spellings on a SMALL known set of tickers via the Formula API cross-sectional
endpoint (the mode you've confirmed works on supplied ids).

Key idea: ISON_* is a per-security 1/0 membership flag. You evaluate it on ids
YOU provide -- no universe-expansion entitlement needed (that's what blocked
FG_CONSTITUENTS). Once we know which spelling works, we run it across all 1,348
tickers you already have and keep the S&P 500 hits.

Test set is chosen to discriminate:
  AAPL, MSFT, WHR  -> in S&P 500  (flag should be 1)
  CLB,  MBC        -> NOT in S&P 500 (flag should be 0; still in S&P 1500)

Run on your Mac:
    export FACTSET_USERNAME="COREMAC-395908"
    export FACTSET_API_KEY="your-key"
    python3 test_ison.py
"""
import os, sys, json, requests

URL  = "https://api.factset.com/formula-api/v1/cross-sectional"
USER = os.environ.get("FACTSET_USERNAME")
KEY  = os.environ.get("FACTSET_API_KEY")
if not (USER and KEY):
    sys.exit("ERROR: export FACTSET_USERNAME and FACTSET_API_KEY first.")
AUTH = (USER, KEY)

TEST_IDS = ["AAPL-US", "MSFT-US", "WHR-US", "CLB-US", "MBC-US"]

# Candidate membership-flag spellings to try (one request each, errors isolated)
CANDIDATES = [
    "ISON_SP1500",        # your suggestion (will be 1 for all -> confirms it works)
    "ISON_SP500",
    'ISON("SP50",0)',     # general ISON with the confirmed S&P 500 benchmark id
    'ISON("SP500",0)',
    "ISON_SP500(0)",
]

def try_formula(formula):
    body = {"data": {"ids": TEST_IDS,
                     "formulas": ["FG_COMPANY_NAME", formula],
                     "flatten": "Y"}}
    try:
        r = requests.post(URL, json=body, auth=AUTH,
                          headers={"Accept": "application/json",
                                   "Content-Type": "application/json"}, timeout=60)
    except Exception as e:
        return f"request failed: {e}", None
    if r.status_code >= 400:
        try:
            err = r.json().get("errors", [{}])[0].get("title", r.text[:200])
        except Exception:
            err = r.text[:200]
        return f"HTTP {r.status_code}: {err}", None
    return "OK", r.json()

def main():
    print(f"Testing {len(CANDIDATES)} membership-formula spellings on {TEST_IDS}\n")
    winners = []
    for f in CANDIDATES:
        status, resp = try_formula(f)
        print(f"=== {f}")
        print(f"    {status}")
        if resp is not None:
            rows = resp.get("data", resp)
            # print compact name + flag per row so we can see if it discriminates
            try:
                for row in rows:
                    print(f"      {json.dumps(row)[:200]}")
            except Exception:
                print(f"      raw: {json.dumps(resp)[:300]}")
            winners.append(f)
        print()
    print("-" * 50)
    if winners:
        print("Entitled spelling(s) that returned data:", winners)
        print("Look for the one where AAPL/MSFT/WHR = 1 and CLB/MBC = 0 -> that's S&P 500.")
        print("(ISON_SP1500 should show 1 for ALL five -> confirms the mechanism works.)")
    else:
        print("None worked. Paste the error titles above and we'll adjust.")

if __name__ == "__main__":
    main()
