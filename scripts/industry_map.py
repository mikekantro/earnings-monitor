#!/usr/bin/env python3
"""
industry_map.py (v2) -- classify every scored company into a GICS industry.

v2: the model chooses from the canonical GICS industry list embedded below,
verbatim, so labels can never fragment. Off-list answers fall back to the
company's sector. v1 output files (unconstrained vocabulary) are discarded
and fully remapped; v2 files resume normally.
"""
import json
import os
import re
import time

import anthropic

MODEL = "claude-haiku-4-5-20251001"
OUT = "industry_map.json"
BATCH = 40

CANON = ["Aerospace & Defense", "Air Freight & Logistics", "Automobile Components",
"Automobiles", "Banks", "Beverages", "Biotechnology", "Broadline Retail",
"Building Products", "Capital Markets", "Chemicals", "Commercial Services & Supplies",
"Communications Equipment", "Construction & Engineering", "Construction Materials",
"Consumer Finance", "Consumer Staples Distribution & Retail", "Containers & Packaging",
"Distributors", "Diversified Consumer Services", "Diversified REITs",
"Diversified Telecommunication Services", "Electric Utilities", "Electrical Equipment",
"Electronic Equipment, Instruments & Components", "Energy Equipment & Services",
"Entertainment", "Financial Services", "Food Products", "Gas Utilities",
"Ground Transportation", "Health Care Equipment & Supplies",
"Health Care Providers & Services", "Health Care REITs", "Health Care Technology",
"Hotel & Resort REITs", "Hotels, Restaurants & Leisure", "Household Durables",
"Household Products", "Independent Power and Renewable Electricity Producers",
"Industrial Conglomerates", "Industrial REITs", "Insurance",
"Interactive Media & Services", "IT Services", "Leisure Products",
"Life Sciences Tools & Services", "Machinery", "Marine Transportation", "Media",
"Metals & Mining", "Mortgage REITs", "Multi-Utilities", "Office REITs",
"Oil, Gas & Consumable Fuels", "Paper & Forest Products", "Passenger Airlines",
"Personal Care Products", "Pharmaceuticals", "Professional Services",
"Real Estate Management & Development", "Residential REITs", "Retail REITs",
"Semiconductors & Semiconductor Equipment", "Software", "Specialized REITs",
"Specialty Retail", "Technology Hardware, Storage & Peripherals",
"Textiles, Apparel & Luxury Goods", "Tobacco", "Trading Companies & Distributors",
"Transportation Infrastructure", "Water Utilities", "Wireless Telecommunication Services"]

PROMPT = ("You are given US public companies with ticker, name, and GICS sector.\n"
          "Classify each into EXACTLY ONE industry from this canonical GICS list,\n"
          "copied verbatim (no variants, no abbreviations, no new labels):\n\n"
          + "\n".join(CANON) +
          "\n\nRespond ONLY with a JSON object mapping ticker to industry string. "
          "No prose, no markdown fences.")


def main():
    tickers = {}
    for f in ("pmi_scores.json", "pmi_scores_q1_2026.json"):
        try:
            for r in json.load(open(f))["scores"]:
                tickers[r["ticker"]] = (r.get("name", r["ticker"]), r.get("sector", ""))
        except Exception as e:
            print(f"{f}: {e}")
    have = {}
    if os.path.exists(OUT):
        prior = json.load(open(OUT))
        if prior.get("__v") == 2:
            have = {k: v for k, v in prior.items() if k != "__v"}
        else:
            print("v1 map found: unconstrained vocabulary, remapping everything")
    todo = sorted(t for t in tickers if t not in have)
    print(f"universe {len(tickers)} | mapped {len(have)} | to map {len(todo)}")
    client = anthropic.Anthropic()
    cs = set(CANON)
    for i in range(0, len(todo), BATCH):
        chunk = todo[i:i + BATCH]
        lines = "\n".join(f"{t} | {tickers[t][0]} | {tickers[t][1]}" for t in chunk)
        try:
            msg = client.messages.create(
                model=MODEL, max_tokens=2000, system=PROMPT,
                messages=[{"role": "user", "content": lines}])
            raw = re.sub(r"```json|```", "", msg.content[0].text).strip()
            data = json.loads(raw)
            for t in chunk:
                v = data.get(t)
                v = v.strip() if isinstance(v, str) else ""
                have[t] = v if v in cs else (tickers[t][1] or "Unclassified")
            out = dict(have)
            out["__v"] = 2
            json.dump(out, open(OUT, "w"), indent=1, sort_keys=True)
            print(f"[{min(i+BATCH,len(todo))}/{len(todo)}] mapped {len(have)}")
        except Exception as e:
            print(f"batch {i//BATCH}: {e}")
        time.sleep(0.5)
    out = dict(have)
    out["__v"] = 2
    json.dump(out, open(OUT, "w"), indent=1, sort_keys=True)
    print(f"done: {len(have)} tickers mapped -> {OUT}")


if __name__ == "__main__":
    main()
