#!/usr/bin/env python3
"""
industry_map.py -- classify every scored company into a GICS industry.

One-shot enrichment: reads tickers from both season score files, asks the
model for the GICS industry (level 3) given ticker, company name, and the
already-known sector, and writes industry_map.json. Resumable: already-
mapped tickers are skipped, so re-runs only fill gaps (new reporters).
"""
import json
import os
import re
import time

import anthropic

MODEL = "claude-haiku-4-5-20251001"
OUT = "industry_map.json"
BATCH = 40

PROMPT = """You are given US public companies with ticker, name, and GICS sector.
For each, return its GICS INDUSTRY (level 3 of the GICS hierarchy, e.g.
"Semiconductors & Semiconductor Equipment", "Health Care Providers & Services",
"Electric Utilities", "Specialty Retail"). Use standard GICS industry names
only. If genuinely unsure, use the sector name itself.

Respond ONLY with a JSON object mapping ticker to industry string. No prose,
no markdown fences."""


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
        have = json.load(open(OUT))
    todo = sorted(t for t in tickers if t not in have)
    print(f"universe {len(tickers)} | mapped {len(have)} | to map {len(todo)}")
    client = anthropic.Anthropic()
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
                if isinstance(data.get(t), str) and data[t].strip():
                    have[t] = data[t].strip()
            json.dump(have, open(OUT, "w"), indent=1, sort_keys=True)
            print(f"[{min(i+BATCH,len(todo))}/{len(todo)}] mapped {len(have)}")
        except Exception as e:
            print(f"batch {i//BATCH}: {e}")
        time.sleep(0.5)
    print(f"done: {len(have)} tickers mapped -> {OUT}")


if __name__ == "__main__":
    main()
