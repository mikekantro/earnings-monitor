#!/usr/bin/env python3
"""
backfill_ai_history.py -- run the live AI-adoption sweep over a historical
quarter's transcripts via the Batch API. Mirrors backfill_history.py:
state-file crash safety, --attach harvest of a paid batch, sanitized ids,
empty-content guards. Imports the LIVE sweep's prompt/model verbatim.

Usage:
  python3 scripts/backfill_ai_history.py --quarter 2025Q4 [--attach msgbatch_...]
Writes: ai_highlights_<quarter>.json   {"quarter": ..., "highlights": [...]}
"""
import argparse, json, os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from datetime import date
import requests                # noqa: E402
import anthropic               # noqa: E402
import anthropic
import earnings_monitor as em  # noqa: E402
import ai_highlight as ah      # noqa: E402

WINDOWS = {
    "2023Q1": ("2023-04-05", "2023-06-25"), "2023Q2": ("2023-07-05", "2023-09-25"),
    "2023Q3": ("2023-10-05", "2023-12-24"), "2023Q4": ("2024-01-05", "2024-03-25"),
    "2024Q1": ("2024-04-05", "2024-06-25"), "2024Q2": ("2024-07-05", "2024-09-25"),
    "2024Q3": ("2024-10-05", "2024-12-24"), "2024Q4": ("2025-01-05", "2025-03-25"),
    "2025Q1": ("2025-04-05", "2025-06-25"), "2025Q2": ("2025-07-05", "2025-09-25"),
    "2025Q3": ("2025-10-05", "2025-12-24"), "2025Q4": ("2026-01-05", "2026-03-25"),
}

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

def gather(q, start, end):
    events = get_events_range(start, end)
    print(f"{q}: {len(events)} earnings events in window", flush=True)
    reqs, meta = [], {}
    kept = 0
    for i, ev in enumerate(events):
        t = ev["symbol"]
        try:
            rid = em.get_transcript_report_id(ev)
            tx = em.get_transcript_text(rid) if rid else ""
        except Exception:
            tx = ""
        if not tx:
            continue
        if not ah.AI_TERMS.search(tx):
            continue  # live sweep's pre-filter: no AI language, no request
        kept += 1
        cid = t.replace(".", "-").replace("/", "-")
        meta[cid] = {"ticker": t, "name": ev["name"], "date": ev.get("date") or start}
        reqs.append({"custom_id": cid, "params": {
            "model": ah.MODEL, "max_tokens": 400,
            "system": ah.SYSTEM,
            "messages": [{"role": "user", "content":
                ah.USER_TMPL.format(company=ev["name"], ticker=t, transcript=tx[:180000])}],
        }})
        if i % 50 == 0:
            print(f"  transcripts: {i}/{len(events)} fetched, {len(reqs)} AI-relevant", flush=True)
    print(f"{q}: {kept} transcripts pass the AI-terms filter", flush=True)
    return reqs, meta

def finish(client, st, out_path, state_path, q):
    bid = st["batch_id"]; meta = st["meta"]
    while True:
        b = client.messages.batches.retrieve(bid)
        if b.processing_status == "ended":
            break
        print(f"batch {b.processing_status}: {b.request_counts}", flush=True)
        time.sleep(60)
    hits, err = [], 0
    for res in client.messages.batches.results(bid):
        cid = res.custom_id
        t = meta.get(cid, {}).get("ticker", cid)
        if res.result.type != "succeeded":
            err += 1; continue
        blocks = getattr(res.result.message, "content", None) or []
        if not blocks or not getattr(blocks[0], "text", "").strip():
            err += 1; continue
        raw = blocks[0].text.strip()
        raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        try:
            d = json.loads(raw)
        except Exception:
            err += 1; continue
        if not d.get("uses_ai"):
            continue
        hits.append({
            "ticker": t,
            "company": meta.get(cid, {}).get("name", t),
            "event_date": meta.get(cid, {}).get("date", ""),
            "category": d.get("category", "mention_only"),
            "headline": d.get("headline", ""),
            "quote": d.get("quote", ""),
            "metric": d.get("metric"),
            "margin_claim": bool(d.get("margin_claim")),
            "margin_quote": d.get("margin_quote", ""),
            "margin_metric": d.get("margin_metric"),
        })
    out = {"quarter": q, "highlights": sorted(hits, key=lambda r: r["ticker"])}
    json.dump(out, open(out_path, "w"), indent=1)
    if os.path.exists(state_path):
        os.remove(state_path)
    print(f"{q}: {len(hits)} adopters extracted, {err} failed -> {out_path}", flush=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quarter", required=True, choices=sorted(WINDOWS))
    ap.add_argument("--attach", default="", help="msgbatch_ id from a prior run's log")
    args = ap.parse_args()
    q = args.quarter
    start, end = WINDOWS[q]
    out_path = f"ai_highlights_{q.lower()}.json"
    state_path = f".aibatch_{q.lower()}.json"
    client = anthropic.Anthropic()

    if args.attach:
        meta = {}
        for ev in get_events_range(start, end):
            t = ev["symbol"]
            cid = t.replace(".", "-").replace("/", "-")
            meta[cid] = {"ticker": t, "name": ev["name"], "date": ev.get("date") or start}
        st = {"batch_id": args.attach, "meta": meta}
        json.dump(st, open(state_path, "w"))
        print(f"attached to {args.attach} with {len(meta)} event metadata entries", flush=True)
        finish(client, st, out_path, state_path, q)
        return

    if os.path.exists(state_path):
        st = json.load(open(state_path))
        finish(client, st, out_path, state_path, q)
        return

    reqs, meta = gather(q, start, end)
    if not reqs:
        print("nothing to sweep"); return
    try:
        batch = client.messages.batches.create(requests=reqs)
    except Exception as e:
        print(f"BATCH CREATE FAILED: {type(e).__name__}: {e}", flush=True)
        raise
    st = {"batch_id": batch.id, "meta": meta}
    json.dump(st, open(state_path, "w"))
    print(f"batch submitted: {batch.id} ({len(reqs)} requests)", flush=True)
    finish(client, st, out_path, state_path, q)

if __name__ == "__main__":
    main()
