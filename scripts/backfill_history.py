#!/usr/bin/env python3
"""
backfill_history.py -- score a 2025 earnings season with the LIVE pipeline's
exact prompt and model, via the Anthropic Batch API (50% price).

Method-consistency: uses em.PMI_SCORE_PROMPT and claude-sonnet-4-6, the same
content template as em.score_earnings, with analysis and SEC excerpts empty
(score-only mode, as the 430-company Q2 backfill effectively ran). Records
carry the EVENT date, not the run date.

Usage: python3 scripts/backfill_history.py --quarter 2025Q3
Crash-safe: a submitted batch's id is saved; re-runs poll it rather than
resubmitting. Already-scored tickers in the output file are skipped.
"""
import argparse, json, os, sys, time
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import earnings_monitor as em  # noqa: E402
import requests                # noqa: E402
import anthropic               # noqa: E402

WINDOWS = {
    "2025Q1": ("2025-04-05", "2025-06-25"),
    "2025Q2": ("2025-07-05", "2025-09-25"),
    "2025Q3": ("2025-10-05", "2025-12-24"),
    "2025Q4": ("2026-01-05", "2026-03-25"),
}
MODEL = "claude-sonnet-4-6"


def get_events_range(start_iso, end_iso):
    symbols = [f"{t}-US" for t in em.SP500]
    results = []
    for i in range(0, len(symbols), 100):
        chunk = symbols[i:i + 100]
        payload = {"data": {
            "dateTime": {"start": f"{start_iso}T00:00:00Z", "end": f"{end_iso}T23:59:59Z"},
            "universe": {"symbols": chunk, "type": "Tickers"},
            "eventTypes": ["Earnings", "ConfirmedEarningsRelease", "SalesRevenueCall"]}}
        try:
            resp = requests.post(f"{em.FS_BASE}/calendar/events", auth=em.FS_AUTH,
                                 headers=em.HEADERS, json=payload, timeout=20)
            resp.raise_for_status()
            for item in resp.json().get("data", []):
                t = item.get("identifier", "").replace("-US", "")
                if t in em.SP500:
                    results.append({"symbol": t, "name": item.get("entityName", t),
                                    "eventId": item.get("eventId", ""),
                                    "date": (item.get("eventDateTime") or "")[:10]})
        except Exception as e:
            print(f"calendar chunk {i//100}: {e}")
        time.sleep(0.3)
    seen, uniq = set(), []
    for r in results:
        if r["symbol"] not in seen:
            seen.add(r["symbol"]); uniq.append(r)
    return uniq


def content_for(name, ticker, transcript):
    # mirrors em.score_earnings with empty analysis and SEC excerpts
    return (f"COMPANY: {name} ({ticker})\n\n"
            f"EARNINGS ANALYSIS SUMMARY:\n\n\n"
            f"TRANSCRIPT EXCERPT:\n{transcript[:8000]}\n\n"
            f"SEC FILING EXCERPT:\n[Not available]\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarter", required=True, choices=sorted(WINDOWS))
    args = ap.parse_args()
    q = args.quarter
    start, end = WINDOWS[q]
    out_path = f"pmi_scores_{q.lower()}.json"
    state_path = f".batch_{q.lower()}.json"

    # universe = every ticker either season file knows
    uni = set(em.SP500)
    for f in ("pmi_scores.json", "pmi_scores_q1_2026.json"):
        try:
            uni |= {r["ticker"] for r in json.load(open(f))["scores"]}
        except Exception:
            pass
    em.SP500 = uni
    print(f"universe {len(uni)} | window {start}..{end}")

    have = {}
    if os.path.exists(out_path):
        have = {r["ticker"]: r for r in json.load(open(out_path))["scores"]}
        print(f"already scored for {q}: {len(have)}")

    client = anthropic.Anthropic()

    # phase 2 first: an in-flight batch takes priority
    if os.path.exists(state_path):
        st = json.load(open(state_path))
        finish(client, st, out_path, state_path, q)
        return

    events = [e for e in get_events_range(start, end) if e["symbol"] not in have]
    print(f"events needing scores: {len(events)}")
    reqs, meta = [], {}
    for i, ev in enumerate(events, 1):
        t = ev["symbol"]
        try:
            rid = em.get_transcript_report_id(t, ev.get("eventId", ""))
            tx = em.get_transcript_text(rid) if rid else ""
        except Exception:
            tx = ""
        if not tx:
            continue
        meta[t] = {"name": ev["name"], "date": ev.get("date") or start}
        reqs.append({"custom_id": t, "params": {
            "model": MODEL, "max_tokens": 400,
            "system": em.PMI_SCORE_PROMPT,
            "messages": [{"role": "user", "content": content_for(ev["name"], t, tx)}]}})
        if i % 50 == 0:
            print(f"  transcripts: {i}/{len(events)} fetched, {len(reqs)} usable")
        time.sleep(0.25)
    if not reqs:
        print("nothing to score"); return
    batch = client.messages.batches.create(requests=reqs)
    st = {"batch_id": batch.id, "meta": meta}
    json.dump(st, open(state_path, "w"))
    print(f"batch submitted: {batch.id} ({len(reqs)} requests)")
    finish(client, st, out_path, state_path, q)


def finish(client, st, out_path, state_path, q):
    bid = st["batch_id"]; meta = st["meta"]
    while True:
        b = client.messages.batches.retrieve(bid)
        print(f"batch {b.processing_status}: {b.request_counts}")
        if b.processing_status == "ended":
            break
        time.sleep(60)
    have = {}
    if os.path.exists(out_path):
        have = {r["ticker"]: r for r in json.load(open(out_path))["scores"]}
    import re as _re
    ok = err = 0
    for res in client.messages.batches.results(bid):
        t = res.custom_id
        if res.result.type != "succeeded":
            err += 1; continue
        raw = res.result.message.content[0].text.strip()
        raw = _re.sub(r"```json|```", "", raw).strip()
        try:
            sc = json.loads(raw)
        except Exception:
            err += 1; continue
        sc["ticker"] = t
        sc["name"] = meta.get(t, {}).get("name", t)
        sc["date"] = meta.get(t, {}).get("date", "")
        have[t] = sc; ok += 1
    json.dump({"quarter": q, "generated": date.today().isoformat(),
               "scores": sorted(have.values(), key=lambda r: r["ticker"])},
              open(out_path, "w"), indent=1)
    os.remove(state_path)
    print(f"{q}: {ok} scored, {err} failed -> {out_path} (total {len(have)})")


if __name__ == "__main__":
    main()
