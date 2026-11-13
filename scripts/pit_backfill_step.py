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

    # live season first: hard cap on backfill scoring per rolling 20 hours
    cap = int(os.environ.get("BACKFILL_DAILY_CAP", "500"))
    try: _log = json.load(open(LOG))
    except Exception: _log = []
    _cut = (datetime.datetime.utcnow() - datetime.timedelta(hours=20)).isoformat(timespec="minutes")
    used = sum(int(e.get("scored") or 0) for e in _log if e.get("at", "") >= _cut)
    room = cap - used
    if room <= 0:
        print(f"backfill: daily cap reached ({used}/{cap}); leaving quota for the live season")
        return
    targets = targets[:min(room, 120)]

    tf = os.path.join(ROOT, ".backfill_targets.json")
    json.dump(targets, open(tf, "w"))
    label = item.get("season") or f"Q{item['key'][-1]} {item['key'][:4]}"
    env = dict(os.environ, DIGEST_START=item["start"], DIGEST_END=item["end"],
               SCORES_FILE=item["file"], SEASON_LABEL=label, TARGETS_FILE=tf, SKIP_EMAIL="1")
    print(f"backfill: {item['key']} — {len(targets)} targets, window {item['start']}..{item['end']}")
    err_tail, rc = "", None
    errp = os.path.join(ROOT, ".backfill_stderr.txt")
    try:
        with open(errp, "w") as ef:
            r = subprocess.run([sys.executable, os.path.join(ROOT, "src", "earnings_monitor.py")],
                               env=env, cwd=ROOT, stderr=ef,
                               timeout=int(os.environ.get("BACKFILL_BUDGET_S", "2900")))
        rc = r.returncode
    except subprocess.TimeoutExpired:
        print("backfill: time budget reached (scores are saved per company)")
    try:
        import re
        raw = open(errp).read()[-600:]
        # the log is committed to a public repo: strip anything that looks like an address or key
        err_tail = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "<email>", raw)
        err_tail = re.sub(r"[A-Za-z0-9_\-]{28,}", "<redacted>", err_tail)[-400:]
        os.remove(errp)
    except Exception:
        pass
    finally:
        try: os.remove(tf)
        except OSError: pass

    after = scored(item["file"])
    gained = sorted((after - before) & set(targets))
    remaining = [t for t in item["targets"] if t not in after and not t.startswith("@")]

    # did the run get to look? (throttled runs must not retire a season)
    diag = {}
    try: diag = json.load(open(os.path.join(ROOT, "digest_diag.json")))
    except Exception: pass
    looked = (str(diag.get("transcripts_probe")) == "200"
              and (diag.get("window") or [""])[0][:10] == item["start"])
    exhausted = (looked and not gained and int(diag.get("to_process") or 0) == 0
                 and len(targets) >= len(remaining))
    if looked and not gained and not exhausted:
        # this slice had no transcripts: set it aside so the next run tries new names
        item.setdefault("unavailable", []).extend(targets)
        remaining = [t for t in remaining if t not in set(targets)]

    item["targets"] = [] if exhausted else remaining
    if exhausted:
        item["unavailable"] = remaining
    json.dump(q, open(QP, "w"), separators=(",", ":"))

    try: log = json.load(open(LOG))
    except Exception: log = []
    log.append({"at": datetime.datetime.utcnow().isoformat(timespec="minutes"), "season": item["key"],
                "scored": len(gained), "remaining": len(item["targets"]),
                "retired": bool(exhausted), "probe": diag.get("transcripts_probe"),
                "window": (diag.get("window") or [""])[0][:10], "rc": rc, "err": err_tail})
    json.dump(log[-200:], open(LOG, "w"), indent=1)
    left = sum(len(x.get("targets") or []) for x in q)
    print(f"backfill: {item['key']} +{len(gained)} scored, {len(item['targets'])} left in season"
          f"{' (retired; ' + str(len(remaining)) + ' unavailable)' if exhausted else ''}; {left} left overall")

if __name__ == "__main__":
    main()
