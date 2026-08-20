#!/usr/bin/env python3
"""
refund_watch_run.py
-------------------
Sweep Q2 earnings transcripts for TARIFF-REFUND disclosures — who is receiving
refunds from the government (cash in), who is refunding customers (cash out),
and what recipients say they'll do with the money. Produces
refund_highlights.json for the updated report/dashboard.

Same design as ai_watch_run.py: FactSet transcript fetch, grounded extraction
via refund_watch.py (verbatim quotes verified against the transcript), keyword
pre-filter so most companies never hit the Claude API, incremental saves.

Put next to refund_watch.py. Run on your Mac:
    cd ~/Downloads/earnings-monitor-factset
    source ~/Downloads/earnings-monitor/.env 2>/dev/null || true
    # (or export ANTHROPIC_API_KEY / FACTSET_USERNAME / FACTSET_API_KEY)

    # smoke test on the known Q2 refund stories first:
    python3 refund_watch_run.py --tickers AMZN WMT COST TGT F DE --start 2026-07-15 --debug

    # then the full Q2 sweep (universe = tickers in the repo's pmi_scores.json):
    python3 refund_watch_run.py --start 2026-07-15 \
        --scores ~/Downloads/earnings-monitor/pmi_scores.json
"""
from __future__ import annotations
import os, sys, re, json, time, argparse, datetime, requests

try:
    from refund_watch import get_refund_highlight
except ImportError:
    sys.exit("Put refund_watch_run.py next to refund_watch.py (same folder).")

TX_URL = "https://api.factset.com/content/events/v2/transcripts"
USER = os.environ.get("FACTSET_USERNAME"); KEY = os.environ.get("FACTSET_API_KEY")
if not (USER and KEY):
    sys.exit("export FACTSET_USERNAME and FACTSET_API_KEY first.")
if not os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit("export ANTHROPIC_API_KEY first.")
AUTH = (USER, KEY)
HDRS = {"Content-Type": "application/json", "Accept": "application/json"}


def fetch_transcript(ticker: str, start: str, end: str):
    body = {"data": {"ids": [f"{ticker}-US"], "startDate": start, "endDate": end,
                     "eventType": "Earnings"},
            "meta": {"pagination": {"limit": 1, "offset": 0}}}
    for attempt in range(3):
        try:
            r = requests.post(TX_URL, json=body, auth=AUTH, headers=HDRS, timeout=60)
        except Exception:
            time.sleep(5); continue
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1)); continue
        if r.status_code != 200:
            return None
        data = r.json().get("data", [])
        if not data or not data[0].get("documents"):
            return None
        doc = data[0]["documents"][0]
        url = doc.get("transcriptsUrl")
        if not url:
            return None
        rc = requests.get(url, auth=AUTH, timeout=90)
        if rc.status_code != 200 or not rc.text:
            return None
        text = re.sub(r"<[^>]+>", " ", rc.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text, (doc.get("eventDate") or "")[:10]
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="+")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--start", default="2026-07-15")
    ap.add_argument("--end", default=datetime.date.today().isoformat())
    ap.add_argument("--scores", default="pmi_scores.json",
                    help="pmi_scores.json used as the ticker universe")
    ap.add_argument("--out", default="refund_highlights.json")
    ap.add_argument("--debug", action="store_true")
    ap.add_argument("--resume", action="store_true",
                    help="skip tickers already processed successfully (reads <out>.done); errors are retried")
    args = ap.parse_args()

    names = {}
    try:
        blob = json.load(open(os.path.expanduser(args.scores)))
        for r in blob.get("scores", blob):
            names[r["ticker"]] = r.get("name", r["ticker"])
    except Exception as e:
        print(f"note: couldn't read {args.scores} ({e}); need --tickers")

    tickers = args.tickers or sorted(names.keys())
    if args.limit:
        tickers = tickers[:args.limit]

    done_path = args.out + ".done"
    done = set()
    hits = []
    if args.resume:
        if os.path.exists(done_path):
            done = set(open(done_path).read().split())
        if os.path.exists(args.out):
            try:
                hits = json.load(open(args.out)).get("highlights", [])
            except Exception:
                hits = []
        before = len(tickers)
        tickers = [t for t in tickers if t not in done]
        print(f"RESUME: {len(done)} already processed, {len(hits)} prior hits kept, "
              f"{before-len(tickers)} skipped, {len(tickers)} to do")
    print(f"Sweeping {len(tickers)} companies for tariff-refund disclosures "
          f"({args.start} .. {args.end})\n")

    skipped, no_tx, errors = 0, 0, 0
    done_f = open(done_path, "a")
    for i, t in enumerate(tickers, 1):
        try:
            got = fetch_transcript(t, args.start, args.end)
            if not got:
                no_tx += 1
                if args.debug: print(f"[{i}/{len(tickers)}] {t:6s} no transcript")
                continue
            text, edate = got
            h = get_refund_highlight(t, names.get(t, t), text, debug=args.debug)
            if h:
                h["event_date"] = edate
                hits.append(h)
                tags = ("IN" if h["receiving"] else "") + ("+OUT" if h["to_customers"] else "")
                amt = f" {h['amount']}" if h.get("amount") else ""
                print(f"[{i}/{len(tickers)}] {t:6s} ✅ {tags:6s}{amt}  {h['headline'][:55]}")
            else:
                skipped += 1
                if args.debug: print(f"[{i}/{len(tickers)}] {t:6s} —")
            done_f.write(t + "\n"); done_f.flush()
        except Exception as e:
            errors += 1
            print(f"[{i}/{len(tickers)}] {t:6s} ⚠️  {str(e)[:70]}")

        if i % 10 == 0 or i == len(tickers):
            json.dump({"generated": datetime.datetime.now().isoformat(),
                       "window": [args.start, args.end], "highlights": hits},
                      open(args.out, "w"), indent=1)
        time.sleep(0.4)

    json.dump({"generated": datetime.datetime.now().isoformat(),
               "window": [args.start, args.end], "highlights": hits},
              open(args.out, "w"), indent=1)
    print(f"\n{'='*55}")
    print(f"refund disclosures found : {len(hits)}")
    print(f"  receiving (cash in)    : {sum(1 for h in hits if h['receiving'])}")
    print(f"  refunding customers    : {sum(1 for h in hits if h['to_customers'])}")
    from collections import Counter
    print(f"  disposition            : {dict(Counter(h['disposition'] for h in hits))}")
    print(f"no signal: {skipped} | no transcript: {no_tx} | errors: {errors}")
    print(f"\nSaved -> {args.out}. Upload it to chat for the updated report.")


if __name__ == "__main__":
    main()
