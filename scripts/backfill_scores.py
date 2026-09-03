#!/usr/bin/env python3
"""
backfill_scores.py -- score any S&P 1500 reporters missed by the daily digest.

Queries the FactSet calendar for a date RANGE, skips companies already in
pmi_scores.json this season, and runs the digest's own analyze+score pipeline
on the rest. Safe to re-run: already-scored tickers are always skipped.

Usage: python3 scripts/backfill_scores.py --start 2026-07-15 --end 2026-09-03
"""
import argparse, os, sys, time, json
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import earnings_monitor as em  # noqa: E402  (imports config from env)
import requests  # noqa: E402


def get_events_range(start_iso: str, end_iso: str) -> list[dict]:
    """Parametrized version of em.get_todays_earnings for an explicit range."""
    start_str = f"{start_iso}T00:00:00Z"
    end_str = f"{end_iso}T23:59:59Z"
    symbols = [f"{t}-US" for t in em.SP500]
    results = []
    for i in range(0, len(symbols), 100):
        chunk = symbols[i:i + 100]
        payload = {"data": {
            "dateTime": {"start": start_str, "end": end_str},
            "universe": {"symbols": chunk, "type": "Tickers"},
            "eventTypes": ["Earnings", "ConfirmedEarningsRelease", "SalesRevenueCall"]}}
        try:
            resp = requests.post(f"{em.FS_BASE}/calendar/events",
                                 auth=em.FS_AUTH, headers=em.HEADERS,
                                 json=payload, timeout=20)
            resp.raise_for_status()
            for item in resp.json().get("data", []):
                ticker = item.get("identifier", "").replace("-US", "")
                if ticker in em.SP500:
                    results.append({
                        "symbol": ticker,
                        "name": item.get("entityName", ticker),
                        "eventId": item.get("eventId", ""),
                        "quarter": f"Q{item.get('fiscalPeriod','')} {item.get('fiscalYear','')}".strip(),
                    })
        except Exception as e:
            print(f"calendar chunk {i//100} error: {e}")
        time.sleep(0.3)
    seen, uniq = set(), []
    for r in results:
        if r["symbol"] not in seen:
            seen.add(r["symbol"])
            uniq.append(r)
    return uniq


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--limit", type=int, default=0, help="cap for a test run")
    args = ap.parse_args()

    data = em.load_pmi_scores()
    have = {s["ticker"] for s in data.get("scores", [])}
    print(f"already scored this season: {len(have)}")

    # full S&P 1500 universe: Q1 season file union current scores union hardcoded list
    universe = set(em.SP500)
    for f in ("pmi_scores_q1_2026.json",):
        try:
            universe |= {s["ticker"] for s in json.load(open(f))["scores"]}
        except Exception as e:
            print(f"universe file {f}: {e}")
    universe |= have
    em.SP500 = universe   # get_events_range and its in-filter use this
    print(f"universe for calendar query: {len(universe)}")

    events = get_events_range(args.start, args.end)
    todo = [e for e in events if e["symbol"] not in have]
    print(f"calendar events in window: {len(events)} | missing from scores: {len(todo)}")
    if args.limit:
        todo = todo[:args.limit]

    scored, no_tx, errors = [], 0, 0
    for i, ev in enumerate(todo, 1):
        t = ev["symbol"]
        try:
            rid = em.get_transcript_report_id(t, ev.get("eventId", ""))
            tx = em.get_transcript_text(rid) if rid else ""
            if not tx:
                no_tx += 1
                print(f"[{i}/{len(todo)}] {t:6s} no transcript")
                continue
            sec = ""
            try:
                sec = em.get_sec_press_release(t)
            except Exception:
                pass
            analysis = em.analyze_earnings(t, ev["name"], ev["quarter"], tx, sec)
            sc = em.score_earnings(t, ev["name"], analysis, tx, sec)
            if sc:
                scored.append(sc)
                print(f"[{i}/{len(todo)}] {t:6s} scored {sc.get('composite','?')}")
            else:
                errors += 1
        except Exception as e:
            errors += 1
            print(f"[{i}/{len(todo)}] {t:6s} error: {str(e)[:80]}")
        if scored and (i % 10 == 0 or i == len(todo)):
            em.add_pmi_scores(scored)   # incremental merge+save (dedupes)
            scored = []
        time.sleep(0.4)
    if scored:
        em.add_pmi_scores(scored)

    print("=" * 50)
    print(f"backfill complete | newly scored: see log above | no transcript: {no_tx} | errors: {errors}")


if __name__ == "__main__":
    main()
