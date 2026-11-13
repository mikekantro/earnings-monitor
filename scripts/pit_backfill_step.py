#!/usr/bin/env python3
"""One step of the point-in-time constituent backfill.

backfill_queue.json holds one item per historical season: the scores file,
the call-date window, and the tickers that were index members that quarter
but have no score. Each run takes the first item with targets left, scores
as many as fit in the time budget (the digest saves per company), then
prunes the queue. A season is retired when a run finds nothing left to
discover; whatever remains is recorded as unavailable (no transcript).
"""
import json, os, subprocess, sys, datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QP = os.path.join(ROOT, "backfill_queue.json")
LOG = os.path.join(ROOT, "backfill_log.json")

def scored(path):
    try:
        return {r["ticker"] for r in json.load(open(os.path.join(ROOT, path)))["scores"]}
    except Exception:
        return set()

def main():
    q = json.load(open(QP))
    item = next((x for x in q if x.get("targets")), None)
    if not item:
        print("backfill: queue empty — nothing to do")
        return
    before = scored(item["file"])
    targets = [t for t in item["targets"] if t not in before and not t.startswith("@")]
    if not targets:
        item["targets"] = []
        json.dump(q, open(QP, "w"), separators=(",", ":"))
        print(f"backfill: {item['key']} already complete")
        return

    tf = os.path.join(ROOT, ".backfill_targets.json")
    json.dump(targets, open(tf, "w"))
    label = item.get("season") or f"Q{item['key'][-1]} {item['key'][:4]}"
    env = dict(os.environ, DIGEST_START=item["start"], DIGEST_END=item["end"],
               SCORES_FILE=item["file"], SEASON_LABEL=label, TARGETS_FILE=tf, SKIP_EMAIL="1")
    print(f"backfill: {item['key']} — {len(targets)} targets, window {item['start']}..{item['end']}")
    try:
        subprocess.run([sys.executable, os.path.join(ROOT, "src", "earnings_monitor.py")],
                       env=env, cwd=ROOT, timeout=int(os.environ.get("BACKFILL_BUDGET_S", "2900")))
    except subprocess.TimeoutExpired:
        print("backfill: time budget reached (scores are saved per company)")
    finally:
        try: os.remove(tf)
        except OSError: pass

    after = scored(item["file"])
    gained = sorted((after - before) & set(targets))
    remaining = [t for t in targets if t not in after]

    # did the run get to look? (throttled runs must not retire a season)
    diag = {}
    try: diag = json.load(open(os.path.join(ROOT, "digest_diag.json")))
    except Exception: pass
    looked = str(diag.get("transcripts_probe")) == "200"
    exhausted = looked and not gained and int(diag.get("to_process") or 0) == 0

    item["targets"] = [] if exhausted else remaining
    if exhausted:
        item["unavailable"] = remaining
    json.dump(q, open(QP, "w"), separators=(",", ":"))

    try: log = json.load(open(LOG))
    except Exception: log = []
    log.append({"at": datetime.datetime.utcnow().isoformat(timespec="minutes"), "season": item["key"],
                "scored": len(gained), "remaining": len(item["targets"]),
                "retired": bool(exhausted), "probe": diag.get("transcripts_probe")})
    json.dump(log[-200:], open(LOG, "w"), indent=1)
    left = sum(len(x.get("targets") or []) for x in q)
    print(f"backfill: {item['key']} +{len(gained)} scored, {len(item['targets'])} left in season"
          f"{' (retired; ' + str(len(remaining)) + ' unavailable)' if exhausted else ''}; {left} left overall")

if __name__ == "__main__":
    main()
