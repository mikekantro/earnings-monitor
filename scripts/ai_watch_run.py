#!/usr/bin/env python3
"""
ai_watch_run.py
---------------
Sweep the earnings-season transcripts and extract, per company, a GROUNDED
"AI use" snippet (the Lowe's/Mylow adopter signal) — the thing your PMI digest
can't see. Produces ai_highlights.json, which you upload back to chat to build
the comprehensive adopter report.

Pipeline per company:
  1. POST /content/events/v2/transcripts  -> latest earnings transcript metadata
  2. GET the returned transcriptsUrl       -> transcript text
  3. ai_highlight.get_ai_highlight(...)     -> grounded snippet (or nothing),
     with the verbatim-quote check so nothing is fabricated

Reuses your existing ai_highlight.py (keep it in the same folder).

Run on your Mac:
    cd ~/Downloads/earnings-monitor-factset
    export FACTSET_USERNAME="COREMAC-395908"
    export FACTSET_API_KEY="your-key"
    export ANTHROPIC_API_KEY="your-key"

    # smoke-test on a few known adopters first:
    python3 ai_watch_run.py --tickers LOW WMT AMZN ETSY --start 2026-04-01

    # then the full universe (uses tickers from pmi_scores.json):
    python3 ai_watch_run.py --start 2026-04-01

Flags:
    --tickers T1 T2 ...   only these (default: all in pmi_scores.json)
    --limit N             cap number of companies (testing)
    --start / --end       transcript date window (default 2026-04-01 .. today)
    --scores PATH         pmi_scores.json (for the ticker+name list)
    --out PATH            output (default ai_highlights.json)
    --model NAME          override AI_HIGHLIGHT_MODEL (Haiku = cheaper for bulk)
"""
import os, sys, re, json, time, argparse, datetime, requests

try:
    from ai_highlight import get_ai_highlight
except ImportError:
    sys.exit("Put ai_watch_run.py next to ai_highlight.py (same folder).")

TX_URL = "https://api.factset.com/content/events/v2/transcripts"
USER = os.environ.get("FACTSET_USERNAME")
KEY  = os.environ.get("FACTSET_API_KEY")
if not (USER and KEY):
    sys.exit("export FACTSET_USERNAME and FACTSET_API_KEY first.")
if not os.environ.get("ANTHROPIC_API_KEY"):
    sys.exit("export ANTHROPIC_API_KEY first.")
AUTH = (USER, KEY)
HDRS = {"Content-Type": "application/json", "Accept": "application/json"}


def _get(url, **kw):
    for attempt in range(3):
        r = requests.get(url, auth=AUTH, timeout=90, **kw)
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1)); continue
        return r
    return r

def fetch_transcript(ticker, start, end):
    """Return (text, event_date, headline) for the company's earnings call, or None."""
    fid = f"{ticker}-US"
    body = {"data": {"ids": [fid], "startDate": start, "endDate": end, "eventType": "Earnings"},
            "meta": {"pagination": {"limit": 1, "offset": 0}}}
    for attempt in range(3):
        r = requests.post(TX_URL, json=body, auth=AUTH, headers=HDRS, timeout=60)
        if r.status_code == 429:
            time.sleep(10 * (attempt + 1)); continue
        break
    if r.status_code != 200:
        return None
    data = r.json().get("data", [])
    if not data or not data[0].get("documents"):
        return None
    doc = data[0]["documents"][0]
    url = doc.get("transcriptsUrl")
    if not url:
        return None
    rc = _get(url)
    if rc.status_code != 200 or not rc.text:
        return None
    text = re.sub(r"<[^>]+>", " ", rc.text)      # strip XML/NLP tags -> plain text
    text = re.sub(r"\s+", " ", text).strip()
    return text, doc.get("eventDate"), doc.get("headline", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", nargs="+")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--start", default="2026-04-01")
    ap.add_argument("--end", default=datetime.date.today().isoformat())
    ap.add_argument("--scores", default="pmi_scores.json")
    ap.add_argument("--out", default="ai_highlights.json")
    ap.add_argument("--model")
    ap.add_argument("--debug", action="store_true", help="print model output + filter reason per ticker")
    ap.add_argument("--resume", action="store_true",
                    help="skip tickers already processed successfully (reads <out>.done); errors are retried")
    args = ap.parse_args()
    if args.model:
        os.environ["AI_HIGHLIGHT_MODEL"] = args.model

    names = {}
    try:
        blob = json.load(open(args.scores))
        for r in blob.get("scores", blob):
            names[r["ticker"]] = r.get("name", r["ticker"])
    except Exception:
        pass

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
    print(f"Scanning {len(tickers)} companies  ({args.start} .. {args.end})\n")

    no_tx, no_ai, errors = 0, 0, 0
    done_f = open(done_path, "a")
    for i, t in enumerate(tickers, 1):
        try:
            got = fetch_transcript(t, args.start, args.end)
            if not got:
                no_tx += 1
                print(f"[{i}/{len(tickers)}] {t:6s} no transcript"); continue
            text, edate, headline = got
            h = get_ai_highlight(t, names.get(t, t), text, debug=args.debug)
            if h:
                h["event_date"] = edate
                hits.append(h)
                print(f"[{i}/{len(tickers)}] {t:6s} ✅ {h['category']:10s} {h['headline'][:60]}")
            else:
                no_ai += 1
                print(f"[{i}/{len(tickers)}] {t:6s} —  no AI-use signal")
            done_f.write(t + "\n"); done_f.flush()
        except Exception as e:
            errors += 1
            print(f"[{i}/{len(tickers)}] {t:6s} ⚠️  {str(e)[:80]}")

        # incremental save so a long run is never lost
        if i % 10 == 0 or i == len(tickers):
            json.dump({"generated": datetime.datetime.now().isoformat(),
                       "window": [args.start, args.end], "highlights": hits},
                      open(args.out, "w"), indent=1)
        time.sleep(0.4)   # be gentle on both APIs

    json.dump({"generated": datetime.datetime.now().isoformat(),
               "window": [args.start, args.end], "highlights": hits},
              open(args.out, "w"), indent=1)

    print(f"\n{'='*55}")
    print(f"AI-use adopters found: {len(hits)}")
    from collections import Counter
    print("By category:", dict(Counter(h["category"] for h in hits)))
    print(f"No transcript: {no_tx} | No AI signal: {no_ai} | Errors: {errors}")
    print(f"\nSaved -> {args.out}. Upload that file to chat and I'll build the report.")


if __name__ == "__main__":
    main()
