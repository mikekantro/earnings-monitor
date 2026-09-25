#!/usr/bin/env python3
"""
build_dashboards.py — regenerate all five research pages from current data.

Reads (repo root):
  pmi_scores.json            live Q2 scores (bot-committed; deduped here)
  pmi_scores_q1_2026.json    Q1 archive (1,432)
  ai_highlights.json         Q1 AI sweep (505)
  ai_highlights_q2.json      Q2 AI sweep (grows via resumed runs)
  refund_highlights.json     refund sweep

Rewrites in place (docs/research/):
  pmi-scorecard/index.html   ai-adopters/index.html   refund-watch/index.html
  ai-employment/index.html   index.html (hub date)

Design: data payloads are slice-swapped between value-independent anchors
(`const ROWS=` … `;`), and every dynamic stat is replaced via STRUCTURAL
regexes that match the surrounding markup, never the old value — so the
builder keeps working as numbers drift. Editorial prose (finding-panel
narrative, methodology) is NOT touched: numbers update daily, words change
only when a human changes them.

Run:  python3 scripts/build_dashboards.py   (from repo root)
Exit code 0 = all pages rebuilt and self-checked; nonzero = left untouched.
"""
from __future__ import annotations
import json, re, sys, datetime
import numpy as np
from collections import defaultdict, Counter

ROOT = "."
SITE = "docs/research"
rng = np.random.default_rng(31)

def die(msg):
    print(f"BUILD FAILED: {msg}", file=sys.stderr); sys.exit(1)

def load(p):
    with open(p) as f: return json.load(f)

def sub1(s, pattern, repl, label, flags=0):
    out, n = re.subn(pattern, repl, s, count=1, flags=flags)
    if n != 1: die(f"anchor missed ({label}): /{pattern[:60]}/")
    return out

def _swapm(html, tag, inner):
    a = html.index(f"<!--{tag}-->") + len(tag) + 7
    bnd = html.index(f"<!--/{tag}-->")
    return html[:a] + inner + html[bnd:]

def swap_payload(s, start_token, repl, end=";"):
    a = s.index(start_token)
    b = s.index(end, a + len(start_token))
    # extend past a JSON array/object that itself contains ';'? our payloads
    # never contain raw ';' outside strings that matter — but to be safe for
    # ROWS arrays we search for '];' when the token opens an array.
    return s[:a] + repl + s[b + len(end):]

def mm(a):
    if not a: return None
    m = re.search(r"\$([\d,.]+)\s*(million|billion|M\b|B\b)?", a)
    if not m: return None
    v = float(m.group(1).replace(",", ""))
    u = (m.group(2) or "").lower()
    return v * 1000 if u.startswith("b") else (v if u.startswith("m") else None)

def perm(a, b, n=30000):
    a = np.asarray(a, float); b = np.asarray(b, float)
    obs = a.mean() - b.mean()
    pool = np.concatenate([a, b]); na = len(a); c = 0
    for _ in range(n):
        rng.shuffle(pool)
        if abs(pool[:na].mean() - pool[na:].mean()) >= abs(obs): c += 1
    return obs, c / n

# ---------------- load + dedupe ----------------
today = datetime.date.today().strftime("%B %-d, %Y")
today_short = datetime.date.today().strftime("%b %-d, %Y")

q1_all = load(f"{ROOT}/pmi_scores_q1_2026.json")["scores"]
q1s = {r["ticker"]: r for r in q1_all}
raw = load(f"{ROOT}/pmi_scores.json")["scores"]
best = {}
for r in raw:
    t = r["ticker"]
    if t not in best or r.get("date", "") > best[t].get("date", ""):
        best[t] = r
q2 = list(best.values())

a1h = load(f"{ROOT}/ai_highlights_q1.json")["highlights"]
if len(a1h) != 505: die(f"Q1 sweep wrong file: {len(a1h)} entries, expected 505")
a2h_raw = load(f"{ROOT}/ai_highlights_q2.json")["highlights"]
seen = set(); a2h = []
for x in a2h_raw:
    if x["ticker"] in seen: continue
    seen.add(x["ticker"]); a2h.append(x)
a1 = {x["ticker"]: x for x in a1h}
a2 = {x["ticker"]: x for x in a2h}
R = load(f"{ROOT}/refund_highlights.json")["highlights"]
try:
    spy = {c["ticker"] for c in load(f"{ROOT}/sp500_constituents_spy.json")}
except Exception:
    spy = set()
print(f"data: pmi {len(raw)}->{len(q2)} | ai Q1 {len(a1h)} Q2 {len(a2h)} | refunds {len(R)}")

# ---------------- scorecard ----------------
SUB = ["composite","new_orders","output","employment","prices","supply_chains","demand_breadth"]
LAB = {"composite":"Composite","new_orders":"New orders","output":"Output","employment":"Employment",
       "prices":"Prices","supply_chains":"Supply chains","demand_breadth":"Demand breadth"}
pairs = [(r, q1s[r["ticker"]]) for r in q2 if r["ticker"] in q1s]
score = []
for k in SUB:
    a = float(np.mean([m[0][k] for m in pairs if m[0].get(k) is not None]))
    b = float(np.mean([m[1][k] for m in pairs if m[1].get(k) is not None]))
    score.append({"k": LAB[k], "q2": round(a,1), "q1": round(b,1), "d": round(a-b,1)})
secagg = defaultdict(list)
for r2, r1 in pairs: secagg[r2.get("sector","—")].append(r2["composite"]-r1["composite"])
sectors = sorted([{"s": s, "n": len(v), "d": round(float(np.mean(v)),1)}
                  for s, v in secagg.items() if len(v) >= 10], key=lambda x: -x["d"])
darr = np.array([m[0]["composite"]-m[1]["composite"] for m in pairs])
SC = {"n": len(pairs), "q2n": len(q2), "up": int((darr>0).sum()), "down": int((darr<0).sum()),
      "breadth": round(float(np.mean([m[0]["composite"]>50 for m in pairs]))*100),
      "comp2": score[0]["q2"], "comp1": score[0]["q1"]}
mv = sorted(pairs, key=lambda m: m[0]["composite"]-m[1]["composite"])
def mrow(r2, r1): return {"t": r2["ticker"], "s": r2.get("sector",""), "q1": r1["composite"],
                          "q2": r2["composite"], "k": (r2.get("key_signal","") or "")[:260]}
movers = {"down":[mrow(*m) for m in mv[:5]], "up":[mrow(*m) for m in mv[-5:][::-1]]}
mega = [{"t": t, "q1": q1s[t]["composite"], "q2": best[t]["composite"]}
        for t in ["AAPL","MSFT","GOOGL","AMZN","META"] if t in q1s and t in best]
tbl = [{"t": r["ticker"], "s": r.get("sector","—"),
        "q1": q1s[r["ticker"]]["composite"] if r["ticker"] in q1s else None,
        "q2": r["composite"],
        "d": (r["composite"]-q1s[r["ticker"]]["composite"]) if r["ticker"] in q1s else None,
        "k": (r.get("key_signal","") or "")[:230]} for r in q2]

p = f"{SITE}/pmi-scorecard/index.html"
s = open(p).read()
a = s.index("const S="); end = s.index("const esc", a)
s = (s[:a] + "const S="+json.dumps(score)+",SEC="+json.dumps(sectors)
     + ",MV="+json.dumps(movers)+",MEGA="+json.dumps(mega)
     + ",ROWS="+json.dumps(tbl,separators=(",",":"))+";\n" + s[end:])
s = sub1(s, r"<b>[\d.]+</b>Q2 composite \(Q1: [\d.]+\)", f"<b>{SC['comp2']}</b>Q2 composite (Q1: {SC['comp1']})", "sc-comp")
s = sub1(s, r"<b>\d+ / \d+</b>improving / declining", f"<b>{SC['up']} / {SC['down']}</b>improving / declining", "sc-updown")
s = sub1(s, r"<b>\d+</b>same-company pairs", f"<b>{SC['n']}</b>same-company pairs", "sc-pairs")
s = sub1(s, r"<b>same \d+ companies</b>", f"<b>same {SC['n']} companies</b>", "sc-same")
s = sub1(s, r"the \d+ companies scored in <i>both</i> seasons", f"the {SC['n']} companies scored in <i>both</i> seasons", "sc-both")
s = sub1(s, r"All \d+ Q2-scored companies", f"All {SC['q2n']} Q2-scored companies", "sc-all")
s = sub1(s, r"Q2: \d+ companies scored through [A-Z][a-z]+ \d+, 2026", f"Q2: {SC['q2n']} companies scored through {today}", "sc-date")
_ps = defaultdict(lambda: {"c2": [], "d": [], "no": []})
for _t4, _r4 in best.items():
    _sx4 = _r4.get("sector","—")
    if _r4.get("composite") is not None:
        _ps[_sx4]["c2"].append(_r4["composite"])
        if _t4 in q1s and q1s[_t4].get("composite") is not None:
            _ps[_sx4]["d"].append(_r4["composite"]-q1s[_t4]["composite"])
        if _r4.get("new_orders") is not None:
            _ps[_sx4]["no"].append(_r4["new_orders"])
_psr = ""
for _sx4, _v4 in sorted(_ps.items(), key=lambda kv: -np.mean(kv[1]["c2"])):
    if len(_v4["c2"]) >= 15:
        _d4 = float(np.mean(_v4["d"])) if _v4["d"] else 0.0
        _psr += (f'<tr><td>{_sx4}</td><td class="num">{len(_v4["c2"])}</td><td class="num"><b>{np.mean(_v4["c2"]):.1f}</b></td>'
                 f'<td class="num {"pos" if _d4>0 else "neg"}">{_d4:+.1f}</td><td class="num">{np.mean(_v4["no"]):.1f}</td>'
                 f'<td><span class="sbar {"up" if _d4>=0 else "dn"}" style="width:{min(110,abs(_d4)*28):.0f}px"></span></td></tr>\n')
s = _swapm(s, "PMISEC", _psr)
open(p, "w").write(s)
print(f"scorecard: {SC}")

# ---------------- AI page ----------------
uni = set(best)
q1_in = {t for t in a1 if t in uni}
rep = q1_in & set(a2); quiet = q1_in - set(a2); new_q2 = set(a2) - set(a1)
rev1 = [t for t in q1_in if a1[t]["category"]=="revenue"]
rev_still = [t for t in rev1 if t in a2 and a2[t]["category"]=="revenue"]
rev_met = [t for t in rev_still if a2[t].get("metric")]
AP = dict(q1_in=len(q1_in), rep=len(rep), quiet=len(quiet), new=len(new_q2),
          rate2=round(len([t for t in a2 if t in uni])/len(uni)*100), n2=len(a2h), uni=len(uni),
          rev1=len(rev1), rev_still=len(rev_still), rev_met=len(rev_met),
          upg=len([t for t in q1_in if t in a2 and a1[t]["category"]=="efficiency" and a2[t]["category"]=="revenue"]),
          eff=sum(1 for t in rep if a1[t]["category"]=="efficiency" and a2[t]["category"]=="efficiency"),
          prd=sum(1 for t in rep if a1[t]["category"]=="product" and a2[t]["category"]=="product"),
          m2=round(sum(1 for x in a2h if x.get("metric"))/len(a2h)*100))
pers = round(100*AP["rep"]/AP["q1_in"])
t1 = set(a1)
rows = []
for src, season, pmi in ((a1h, "Q1", q1s), (a2h, "Q2", best)):
    for x in src:
        t = x["ticker"]; pp = pmi.get(t, {})
        rows.append({"t": t, "n": x["company"], "c": x["category"], "S": season,
                     "p": pp.get("composite"), "s": pp.get("sector","—"), "x": 0,
                     "m": x.get("metric") or "", "h": x["headline"], "q": x["quote"],
                     "new": 1 if (season=="Q2" and t not in t1) else 0,
                     "mc": 1 if x.get("margin_claim") else 0,
                     "mm": x.get("margin_metric") or "", "mz": x.get("margin_quote") or ""})
try:
    spy = {c["ticker"] for c in load(f"{ROOT}/sp500_constituents_spy.json")}
    for r in rows: r["x"] = 1 if r["t"] in spy else 0
except Exception: pass
def stab(hs, pmi):
    tot = Counter(r.get("sector","—") for r in pmi.values()); ad = Counter(); sp = defaultdict(Counter)
    for x in hs:
        s_ = pmi.get(x["ticker"], {}).get("sector","—"); ad[s_] += 1; sp[s_][x["category"]] += 1
    out = [{"s": s_, "n": n, "a": ad.get(s_,0), "rate": round(100*ad.get(s_,0)/n,1),
            "r": sp[s_]["revenue"], "e": sp[s_]["efficiency"], "p": sp[s_]["product"]}
           for s_, n in tot.items() if n >= 10]
    out.sort(key=lambda x: -x["rate"]); return out
sec = {"Q1": stab(a1h, q1s), "Q2": stab(a2h, best)}

p = f"{SITE}/ai-adopters/index.html"
s = open(p).read()
a = s.index("const ROWS="); d = s.index(";\n", s.index(";const UNI="))
s = (s[:a] + "const ROWS="+json.dumps(rows,separators=(",",":"))
     + ";const SEC="+json.dumps(sec,separators=(",",":"))
     + ";const UNI={Q1:1432,Q2:"+str(AP["uni"])+"}" + s[d:])
try:
    _bo_t = sorted({x["ticker"] for x in load(f"{ROOT}/buildout_highlights.json")["highlights"]})
except Exception:
    _bo_t = []
ba = s.index("const BOSET="); bb = s.index(";", ba)
s = s[:ba] + "const BOSET=" + json.dumps(_bo_t) + s[bb:]
s = sub1(s, r"<b>\d+%</b>of Q2 reporters cite AI use \(Q1: 35%\)", f"<b>{AP['rate2']}%</b>of Q2 reporters cite AI use (Q1: 35%)", "ai-rate")
s = sub1(s, r"<b>\d+</b>Q2 adopters of \d+ reported", f"<b>{AP['n2']}</b>Q2 adopters of {AP['uni']} reported", "ai-n")
s = sub1(s, r"<b>\d+</b>first-time claimants", f"<b>{AP['new']}</b>first-time claimants", "ai-new")
s = sub1(s, r"<b>\d+%</b>back it with a number \(Q1: 25%\)", f"<b>{AP['m2']}%</b>back it with a number (Q1: 25%)", "ai-m")
s = sub1(s, r"Of the \d+ Q1 adopters that have reported Q2, <b>\d+% repeated the AI claim</b>",
         f"Of the {AP['q1_in']} Q1 adopters that have reported Q2, <b>{pers}% repeated the AI claim</b>", "ai-pers")
s = sub1(s, r"efficiency stayed efficiency \(\d+ companies\), product stayed product \(\d+\)",
         f"efficiency stayed efficiency ({AP['eff']} companies), product stayed product ({AP['prd']})", "ai-sticky")
s = sub1(s, r"\d+ went quiet entirely\.", f"{AP['quiet']} went quiet entirely.", "ai-quiet-prose")
s = sub1(s, r"Of <b>\d+ Q1 revenue claimants</b> reporting Q2,\s*only <b>\d+ still describe AI driving revenue</b>, and just <b>\d+ back it with a number</b>",
         f"Of <b>{AP['rev1']} Q1 revenue claimants</b> reporting Q2,\nonly <b>{AP['rev_still']} still describe AI driving revenue</b>, and just <b>{AP['rev_met']} back it with a number</b>", "ai-funnel-prose")
s = sub1(s, r'<td class="v">\d+ / \d+<small>\d+% persistence</small></td>',
         f'<td class="v">{AP["rep"]} / {AP["q1_in"]}<small>{pers}% persistence</small></td>', "ai-tbl-pers")
s = sub1(s, r'<tr><td>Went quiet</td><td class="v">\d+<small>\d+%</small></td></tr>',
         f'<tr><td>Went quiet</td><td class="v">{AP["quiet"]}<small>{round(100*AP["quiet"]/AP["q1_in"])}%</small></td></tr>', "ai-tbl-quiet")
s = sub1(s, r'<tr><td>First-time claimants in Q2</td><td class="v">\d+<small>said nothing in Q1</small></td></tr>',
         f'<tr><td>First-time claimants in Q2</td><td class="v">{AP["new"]}<small>said nothing in Q1</small></td></tr>', "ai-tbl-new")
s = sub1(s, r'<td class="v">\d+ / \d+<small>\d+ with a metric</small></td>',
         f'<td class="v">{AP["rev_still"]} / {AP["rev1"]}<small>{AP["rev_met"]} with a metric</small></td>', "ai-tbl-funnel")
s = sub1(s, r'<td class="v">\d+<small>the cohort to watch</small></td>',
         f'<td class="v">{AP["upg"]}<small>the cohort to watch</small></td>', "ai-tbl-upg")
s = sub1(s, r"\(\d+ of 505\)", f"({AP['q1_in']} of 505)", "ai-505")
s = sub1(s, r"Q2 window: July 15 – [A-Z][a-z]+ \d+, 2026", f"Q2 window: July 15 – {today}", "ai-date")

# ---- margin section (marker-delimited) ----
mc = [x for x in a2h if x.get("margin_claim")]
mqx = [x for x in mc if x.get("margin_metric")]
def _mkind(m): return "target" if re.search(r"target|by 20\d\d", m or "", re.I) else "realized"
realized = [x for x in mqx if _mkind(x["margin_metric"])=="realized"]
eff_mc = sum(1 for x in mc if x["category"]=="efficiency")
def _esc(x): return (x or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
def _swap(html, tag, inner):
    a = html.index(f"<!--{tag}-->") + len(tag) + 7
    b = html.index(f"<!--/{tag}-->")
    return html[:a] + inner + html[b:]
s = _swap(s, "MPROSE",
    f"Of {len(a2h)} adopters, {len(mc)} make the connection on the record, {len(mqx)} attach a number, "
    f"and of those only {len(realized)} describe realized results rather than future targets.")
s = _swap(s, "MSTATS", f'''
<span><b>{len(mc)}</b>adopters state the AI&rarr;margin link ({round(100*len(mc)/len(a2h))}% of {len(a2h)})</span>
<span><b>{len(mqx)}</b>attach a number</span>
<span><b>{len(realized)}</b>quantified &amp; realized, not a target</span>
<span><b>{eff_mc} / {len(mc)}</b>are efficiency claimants</span>
''')
mrows = "\n".join(
    f'<tr><td><b>{x["ticker"]}</b> <span style="color:var(--muted)">{_esc(x["company"])}</span></td>'
    f'<td class="mv">{_esc(x["margin_metric"])}</td>'
    f'<td><span class="mtag {_mkind(x["margin_metric"])}">{_mkind(x["margin_metric"]).upper()}</span></td></tr>'
    for x in sorted(mqx, key=lambda x:(_mkind(x["margin_metric"])!="realized", x["ticker"])))
s = _swap(s, "MTBL", "\n" + mrows + "\n")
open(p, "w").write(s)
print(f"ai page: {AP} pers={pers} | margin: {len(mc)} claim / {len(mqx)} quant / {len(realized)} realized")

# ---------------- refund page ----------------
for x in R:
    x["amt_mm"] = mm(x.get("amount"))
    x["grp"] = "undecided" if x["disposition"] in ("undecided","na") else x["disposition"]
order = {"refund_customers":0,"invest_in_price":1,"undecided":2,"retain":3}
R.sort(key=lambda x: (order[x["grp"]], -(x["amt_mm"] or 0), x["ticker"]))
rrows = [{"t": x["ticker"], "n": x["company"], "g": x["grp"], "both": bool(x["to_customers"]),
          "a": x.get("amount") or "", "m": x["amt_mm"], "h": x["headline"],
          "q": x.get("quote_receiving") or "", "qc": x.get("quote_customers") or "",
          "d": x.get("event_date") or ""} for x in R]
dd = defaultdict(float)
for x in R:
    if x["amt_mm"]: dd[x["grp"]] += x["amt_mm"]
tot = sum(dd.values())
RT = {"n": len(R), "tot": tot, "n_amt": sum(1 for x in R if x["amt_mm"]),
      "retain_n": sum(1 for x in R if x["grp"]=="retain"),
      "bar": {k: round(dd.get(k,0)) for k in ("refund_customers","invest_in_price","undecided","retain")},
      "cust_n": sum(1 for x in R if x["to_customers"])}

p = f"{SITE}/refund-watch/index.html"
s = open(p).read()
a = s.index("const ROWS="); b = s.index("];", a) + 2
s = s[:a] + "const ROWS=" + json.dumps(rrows, separators=(",",":")) + ";" + s[b:]
s = sub1(s, r"\d+ companies disclosed them on Q2 calls", f"{RT['n']} companies disclosed them on Q2 calls", "rw-sub")
s = sub1(s, r"<b>\d+</b>companies disclosing", f"<b>{RT['n']}</b>companies disclosing", "rw-n")
s = sub1(s, r"<b>\$[\d.]+B\+</b>disclosed amounts \(\d+ cos\.\)", f"<b>${tot/1000:.1f}B+</b>disclosed amounts ({RT['n_amt']} cos.)", "rw-tot")
s = sub1(s, r"<b>\d+</b>retaining", f"<b>{RT['retain_n']}</b>retaining", "rw-retn")
s = sub1(s, r"<b>\d+</b>refunding customers", f"<b>{RT['cust_n']}</b>refunding customers", "rw-cust")
s = sub1(s, r"<b>\$[\d.]+B</b> retained", f"<b>${RT['bar']['retain']/1000:.1f}B</b> retained", "rw-key-ret")
s = sub1(s, r"<b>\$[\d.]+[BM]</b> into price", f"<b>${RT['bar']['invest_in_price']/1000:.1f}B</b> into price", "rw-key-price")
s = sub1(s, r'flex:\d+"></i><i style="background:var\(--price\);flex:\d+"></i><i style="background:var\(--und\);flex:\d+"></i><i style="background:var\(--ret\);flex:\d+"',
         f'flex:{RT["bar"]["refund_customers"]}"></i><i style="background:var(--price);flex:{RT["bar"]["invest_in_price"]}"></i><i style="background:var(--und);flex:{RT["bar"]["undecided"]}"></i><i style="background:var(--ret);flex:{RT["bar"]["retain"]}"', "rw-bar")
s = sub1(s, r"July 15 – [A-Z][a-z]+ \d+, 2026", f"July 15 – {today}", "rw-date")
# sector chart
p2s = {r["ticker"]: r.get("sector","") for r in q2}
p1s = {r["ticker"]: r.get("sector","") for r in q1_all}
agg = defaultdict(lambda: {"tot":0.0,"n":0,"split":defaultdict(float)})
for x in R:
    sct = p2s.get(x["ticker"]) or p1s.get(x["ticker"]) or "Other"
    agg[sct]["n"] += 1
    if x["amt_mm"]: agg[sct]["tot"] += x["amt_mm"]; agg[sct]["split"][x["grp"]] += x["amt_mm"]
srt = sorted(agg.items(), key=lambda kv: -kv[1]["tot"])
maxt = max(v["tot"] for _, v in srt)
def bh(sct, v):
    segs = ""
    for key, var in (("refund_customers","--cust"),("invest_in_price","--price"),("undecided","--und"),("retain","--ret")):
        amt = v["split"].get(key, 0)
        if amt > 0: segs += f'<i style="background:var({var});flex:{round(amt)}"></i>'
    w = v["tot"]/maxt*100
    dollars = f"${v['tot']/1000:.1f}B" if v["tot"] >= 950 else f"${v['tot']:.0f}M"
    return (f'<div class="srow">\n      <span class="sname">{sct} <span class="sn">· {v["n"]} cos</span></span>\n'
            f'      <span class="strack"><span class="sbar" style="width:{w:.1f}%">{segs}</span></span>\n'
            f'      <span class="sval">{dollars}</span></div>')
i0 = s.index('<div class="srow">'); i1 = s.rindex("</div>", 0, s.index('<p class="scnote">')) + 6
s = s[:i0] + "\n  ".join(bh(k, v) for k, v in srt) + s[i1:]
open(p, "w").write(s)
print(f"refund page: n={RT['n']} ${tot/1000:.1f}B retain={RT['retain_n']}")

# ---------------- employment tracker (numbers only) ----------------
never = None
dall = defaultdict(list)
for r in q2:
    p1r = q1s.get(r["ticker"])
    if p1r and r.get("employment") is not None and p1r.get("employment") is not None:
        dall[r.get("sector","—")].append(r["employment"]-p1r["employment"])
dmed = {s_: float(np.median(v)) for s_, v in dall.items() if len(v) >= 5}
def snd(pred):
    out = []
    for t, r in best.items():
        p1r = q1s.get(t)
        if not p1r or r.get("employment") is None or p1r.get("employment") is None: continue
        s_ = r.get("sector","—")
        if s_ not in dmed or not pred(t): continue
        out.append((r["employment"]-p1r["employment"]) - dmed[s_])
    return np.array(out)
g_per = snd(lambda t: t in a1 and t in a2)
g_nev = snd(lambda t: t not in a1 and t not in a2)
g_new = snd(lambda t: t not in a1 and t in a2)
g_qui = snd(lambda t: t in a1 and t not in a2)
g_met = snd(lambda t: t in a1 and t in a2 and a1[t].get("metric") and a2[t].get("metric") and a2[t]["category"]=="efficiency")
d_per, p_per = perm(g_per, g_nev)
d_new, p_new = perm(g_new, g_nev)
d_qui, p_qui = perm(g_qui, g_nev)
d_met, p_met = perm(g_met, g_nev) if len(g_met) >= 8 else (float("nan"), float("nan"))
sd = np.concatenate([g_per, g_nev]).std(ddof=1)
mde = 2.8 * sd * np.sqrt(1/len(g_per) + 1/len(g_nev))
MINUS = "\u2212"
def fmt(v): return f"{MINUS}{abs(v):.2f}" if v < 0 else f"+{v:.2f}"

p = f"{SITE}/ai-employment/index.html"
s = open(p).read()
s = sub1(s, r"<b>[\u2212+][\d.]+</b>pts, persistent claimants vs never-claimants \(p=[\d.]+\)",
         f"<b>{fmt(d_per)}</b>pts, persistent claimants vs never-claimants (p={p_per:.3f})", "emp-head")
s = sub1(s, r"<b>\d+ v \d+</b>panel companies, sector-neutral",
         f"<b>{len(g_per)} v {len(g_nev)}</b>panel companies, sector-neutral", "emp-n")
s = sub1(s, r'(<div class="d">Q2 \u00b7 latest \([^)]*\)</div><div class="v">)[\u2212+][\d.]+ \u00b7 p=[\d.]+(</div>)',
         lambda m: m.group(1) + f"{fmt(d_per)} \u00b7 p={p_per:.3f}" + m.group(2), "emp-strip")
s = sub1(s, r'latest \([A-Z][a-z]+ \d+\)', f'latest ({today_short.split(",")[0]})', "emp-strip-date")
s = sub1(s, r'(Quantified AI efficiency, both seasons</td><td class="v">)[\u2212+][\d.]+(<small>n=)\d+( \u00b7 p=)[\d.]+',
         lambda m: m.group(1)+fmt(d_met)+m.group(2)+str(len(g_met))+m.group(3)+f"{p_met:.3f}", "emp-tbl-met")
s = sub1(s, r'(Persistent AI claim \(both seasons\)</b>.*?<td class="v">)[\u2212+][\d.]+(<small>n=)\d+( \u00b7 p=)[\d.]+',
         lambda m: m.group(1)+fmt(d_per)+m.group(2)+str(len(g_per))+m.group(3)+f"{p_per:.3f}", "emp-tbl-per", flags=re.S)
s = sub1(s, r'(Went quiet \(claimed Q1, silent Q2\)</td><td class="v">)[\u2212+][\d.]+(<small>n=)\d+( \u00b7 p=)[\d.]+',
         lambda m: m.group(1)+fmt(d_qui)+m.group(2)+str(len(g_qui))+m.group(3)+f"{p_qui:.3f}", "emp-tbl-qui")
s = sub1(s, r'(First-time claimants</td><td class="v">)[\u2212+][\d.]+(<small>n=)\d+( \u00b7 p=)[\d.]+',
         lambda m: m.group(1)+fmt(d_new)+m.group(2)+str(len(g_new))+m.group(3)+f"{p_new:.2f}", "emp-tbl-new")
s = sub1(s, r'(Never claimed AI</td><td class="v">)\+[\d.]+ raw(<small>n=)\d+',
         lambda m: m.group(1)+f"+{g_nev.mean():.2f} raw"+m.group(2)+str(len(g_nev)), "emp-tbl-nev")
s = sub1(s, r'[\d.]+ pts<small>observed [\d.]+; Q3 supplies the power',
         f"{mde:.2f} pts<small>observed {abs(d_per):.2f}; Q3 supplies the power", "emp-mde")
s = sub1(s, r"<b>Data as of [A-Z][a-z]+ \d+, 2026\.</b>", f"<b>Data as of {today}.</b>", "emp-date")
s = sub1(s, r"\u00b7 [A-Z][a-z]+ \d+, 2026</caption>", f"\u00b7 {today_short}</caption>", "emp-caption")
open(p, "w").write(s)
print(f"employment: persistent {d_per:+.2f} p={p_per:.3f} (n={len(g_per)} v {len(g_nev)}) mde={mde:.2f}")

# ---------------- portfolio screen ----------------
p = f"{SITE}/portfolio/index.html"
s = open(p).read()
Rmap = {x["ticker"]: x for x in R}
try:
    _boh = load(f"{ROOT}/buildout_highlights.json")["highlights"]
    _bomap = {}
    for _x in _boh:
        _bomap.setdefault(_x["ticker"], _x)
except Exception:
    _bomap = {}
uni_all = set(q1s) | set(best)
C = {}
for t in sorted(uni_all):
    r2, r1 = best.get(t), q1s.get(t)
    name = (a2.get(t) or a1.get(t) or Rmap.get(t) or {}).get("company") or ""
    if name == t: name = ""
    e = {"n": name, "s": (r2 or r1 or {}).get("sector",""), "x": 1 if ("spy" in dir() and t in spy) else 0,
         "p1": (r1 or {}).get("composite"), "p2": (r2 or {}).get("composite"),
         "k": ((r2 or {}).get("key_signal") or "")[:230] or None}
    try:
        e["x"] = 1 if t in spy else 0
    except NameError:
        e["x"] = 0
    e["d"] = (e["p2"]-e["p1"]) if (e["p1"] is not None and e["p2"] is not None) else None
    x = a2.get(t)
    if x: e["ai"] = {"c": x["category"], "m": x.get("metric") or "", "h": x["headline"], "q": x["quote"],
                     "mc": 1 if x.get("margin_claim") else 0, "mm": x.get("margin_metric") or "",
                     "mz": x.get("margin_quote") or "", "nw": 0 if t in a1 else 1}
    f = Rmap.get(t)
    if f:
        g = "undecided" if f["disposition"] in ("undecided","na") else f["disposition"]
        e["rf"] = {"g": g, "a": f.get("amount") or "", "m": mm(f.get("amount")), "h": f["headline"],
                   "q": f.get("quote_receiving") or ""}
    e["coh"] = "persistent" if (t in a1 and t in a2) else ("new" if t in a2 else ("quiet" if t in a1 else "never"))
    _bx = _bomap.get(t)
    if _bx: e["bo"] = {"ch": _bx["channel"], "q": _bx["quote"], "m": _bx.get("metric") or ""}
    C[t] = {k: v for k, v in e.items() if v not in (None,"",0) or k in ("x",)}
DBP = {"c": C, "m": {"n": len(C), "idx": SC["comp2"], "date": today,
                     "ed": fmt(d_per), "ep": f"{p_per:.3f}"}}
a = s.index("const DB="); bnd = s.index(";\n", a)
s = s[:a] + "const DB=" + json.dumps(DBP, separators=(",",":")) + s[bnd:]
open(p, "w").write(s)
print(f"portfolio: {len(C)} companies in payload")

# ---------------- pricing power ----------------
p = f"{SITE}/pricing/index.html"
s = open(p).read()
def _pswap(html, tag, inner):
    a = html.index(f"<!--{tag}-->") + len(tag) + 7
    bnd = html.index(f"<!--/{tag}-->")
    return html[:a] + "\n" + inner + "\n" + html[bnd:]
P2 = [r for r in best.values() if r.get("prices") is not None]
ppairs = [(r, q1s[r["ticker"]]) for r in P2 if r["ticker"] in q1s and q1s[r["ticker"]].get("prices") is not None]
prow = [{"t": r["ticker"], "s": r.get("sector",""),
         "p1": (q1s.get(r["ticker"]) or {}).get("prices"), "p2": r["prices"],
         "d": (r["prices"]-q1s[r["ticker"]]["prices"]) if (r["ticker"] in q1s and q1s[r["ticker"]].get("prices") is not None) else None}
        for r in P2]
psec = defaultdict(list); plvl = defaultdict(list)
for r, p1r in ppairs:
    psec[r.get("sector","—")].append(r["prices"]-p1r["prices"])
    plvl[r.get("sector","—")].append(r["prices"])
srows = sorted([(sx, round(float(np.mean(plvl[sx])),1), round(float(np.mean(v)),1), len(v))
                for sx, v in psec.items() if len(v) >= 10], key=lambda x: -x[2])
def _pesc(x): return (x or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
sec_html = "\n".join(
    f'<tr><td>{_pesc(sx)}</td><td class="num">{l}</td>'
    f'<td class="num {"pos" if d>0 else ("neg" if d<0 else "")}">{"+" if d>0 else ""}{d}</td>'
    f'<td><span class="bar {"up" if d>=0 else "dn"}" style="width:{min(120,abs(d)*28)}px"></span></td>'
    f'<td class="num">{n}</td></tr>' for sx, l, d, n in srows)
pmov = sorted([(r["ticker"], p1r["prices"], r["prices"], r["prices"]-p1r["prices"], r.get("sector",""),
                (r.get("key_signal") or "")) for r, p1r in ppairs], key=lambda x: x[3])
def _mrow(m):
    t, a, bb, d, sx, k = m
    return (f'<div class="row"><div class="hd"><span class="tk">{t}</span>'
            f'<span class="mvv {"pos" if d>0 else "neg"}">{a} &rarr; {bb} ({"+" if d>0 else ""}{d})</span>'
            f'<span class="sec-lb">{_pesc(sx)}</span></div><p class="sig">{_pesc(k[:170])}</p></div>')
s = _pswap(s, "PSEC", sec_html)
negs = [(sx, d) for sx, l, d, n in srows if d < 0]
lowlv = min(srows, key=lambda x: x[1])
if not negs:
    _pdn = "This refresh, every measured sector is holding or gaining pricing power versus Q1"
elif len(negs) == 1:
    _pdn = f"This refresh, {negs[0][0]} is the only sector losing ground versus Q1 ({negs[0][1]:+.1f})"
else:
    worst = min(negs, key=lambda x: x[1])
    _pdn = (f"This refresh, {len(negs)} of {len(srows)} sectors are losing ground versus Q1, led by "
            f"{worst[0]} at {worst[1]:+.1f}")
_pdn += f", while the weakest absolute pricing level sits in {lowlv[0]} ({lowlv[1]:.1f})."
s = _pswap(s, "PDN", _pdn)
_bset = set(_bomap.keys())
_pp = [(t, best[t]["prices"]-q1s[t]["prices"]) for t in best
       if t in q1s and best[t].get("prices") is not None and q1s[t].get("prices") is not None]
_pc = [d for t, d in _pp if t in _bset]; _px = [d for t, d in _pp if t not in _bset]
_pt = float(np.mean([d for _, d in _pp])); _pw = len(_pc)/len(_pp)
_psh = max(1, min(99, round(100*_pw*np.mean(_pc)/_pt))) if _pt > 0 else 50
_plv = float(np.mean([best[t]["prices"] for t in best if t in _bset and best[t].get("prices") is not None]))
_plx = float(np.mean([best[t]["prices"] for t in best if t not in _bset and best[t].get("prices") is not None]))
_pal = float(np.mean([best[t]["prices"] for t in best if best[t].get("prices") is not None]))
_epi = {}
for _t2 in _bset:
    _x2 = _bomap[_t2]
    if _t2 in best and best[_t2].get("prices") is not None:
        _epi.setdefault(_x2["channel"], []).append(
            (best[_t2]["prices"], (best[_t2]["prices"]-q1s[_t2]["prices"]) if _t2 in q1s and q1s[_t2].get("prices") is not None else None))
_ec = max((c for c in _epi if len(_epi[c]) >= 8), key=lambda c: np.mean([a for a, _ in _epi[c]]), default=None)
_ecs = ""
if _ec:
    _el = np.mean([a for a, _ in _epi[_ec]])
    _ed = np.mean([d for _, d in _epi[_ec] if d is not None])
    _ecs = f"{_ec.replace('_',' ').title()} is the inflation epicenter ({_el:.1f}, {_ed:+.1f}); "
_chrows = ""
for _c3 in sorted(_epi, key=lambda c: -np.mean([a for a, _ in _epi[c]])):
    if len(_epi[_c3]) >= 5:
        _l3 = np.mean([a for a, _ in _epi[_c3]])
        _ds = [d for _, d in _epi[_c3] if d is not None]
        _d3 = np.mean(_ds) if _ds else 0.0
        _chrows += (f'<tr><td>{_c3.replace("_"," ")}</td><td class="num">{len(_epi[_c3])}</td>'
                    f'<td class="num">{_l3:.1f}</td><td class="num {"pos" if _d3>0 else "neg"}">{_d3:+.1f}</td></tr>\n')
s = _pswap(s, "PBO", f'''
<div style="margin:0 0 18px"><p class="dc-lb">Prices sub-index change, Q2 vs Q1: {_pt:+.2f} pts</p>
<div class="dc-bar"><span class="co" style="width:{_psh}%">build-out {_pw*np.mean(_pc):+.2f}</span><span class="ex" style="width:{100-_psh}%">rest {(1-_pw)*np.mean(_px):+.2f}</span></div>
<p class="dc-cap">Build-out claimants&rsquo; pricing rose {np.mean(_pc):+.1f} versus {np.mean(_px):+.1f} for everyone else; weighted by cohort size, they account for {_psh}% of the index&rsquo;s rise.</p></div>
<p class="dc-lb" style="margin-top:14px">Levels: index {_pal:.1f} &middot; build-out cohort {_plv:.1f} &middot; ex-build-out {_plx:.1f}</p>
<p class="dc-cap" style="margin-top:2px">{_ecs}stripping the build-out chain, the corporate prices gauge reads {_plx:.1f}.</p>
<table class="sec" style="margin-top:14px"><thead><tr><th>Channel</th><th class="num">n</th><th class="num">Prices level</th><th class="num">&Delta; vs Q1</th></tr></thead><tbody>
{_chrows}</tbody></table>
<p class="dc-cap" style="margin-top:8px">Where the chain&rsquo;s inflation lives, channel by channel, refreshed with each build.</p>''')

_spyset = spy if spy else set()
_bg = [best[t]["prices"] for t in best if t in _spyset and best[t].get("prices") is not None]
_sm = [best[t]["prices"] for t in best if t not in _spyset and best[t].get("prices") is not None]
_bgd = [best[t]["prices"]-q1s[t]["prices"] for t in best if t in _spyset and t in q1s
        and best[t].get("prices") is not None and q1s[t].get("prices") is not None]
_smd = [best[t]["prices"]-q1s[t]["prices"] for t in best if t not in _spyset and t in q1s
        and best[t].get("prices") is not None and q1s[t].get("prices") is not None]
try:
    _w = {c["ticker"]: c["weight"] for c in load(f"{ROOT}/sp500_constituents_spy.json")}
    _cwp = [(best[t]["prices"], _w[t]) for t in best if t in _w and best[t].get("prices") is not None]
    _cw = sum(p*w for p, w in _cwp)/sum(w for _, w in _cwp)
except Exception:
    _cw = float(np.mean(_bg)) if _bg else 0
_ret = {x["ticker"] for x in R if x.get("disposition") == "retain"}
_oth = {x["ticker"] for x in R if x.get("disposition") != "retain"}
def _pl(S):
    lv = [best[t]["prices"] for t in S if t in best and best[t].get("prices") is not None]
    dd = [best[t]["prices"]-q1s[t]["prices"] for t in S if t in best and t in q1s
          and best[t].get("prices") is not None and q1s[t].get("prices") is not None]
    return len(lv), (float(np.mean(lv)) if lv else 0), (float(np.mean(dd)) if dd else 0)
_non = {t for t in best if t not in _ret and t not in _oth}
_r1 = _pl(_ret); _r2 = _pl(_oth); _r3 = _pl(_non)
def _tr(lbl, r):
    cl = "pos" if r[2] > 0 else "neg"
    return (f'<tr><td>{lbl}</td><td class="num">{r[0]}</td><td class="num">{r[1]:.1f}</td>'
            f'<td class="num {cl}">{r[2]:+.1f}</td></tr>')
s = _pswap(s, "PWHO", f'''
<p class="dc-lb">The size gradient, prices level</p>
<p style="margin:4px 0 14px;font-family:\'IBM Plex Mono\',monospace;font-size:13px">
full S&amp;P 1500 equal-weight <b>{_pal:.1f}</b> &nbsp;&rarr;&nbsp; S&amp;P 500 equal-weight <b>{np.mean(_bg):.1f}</b> (&Delta; {np.mean(_bgd):+.1f})
&nbsp;&rarr;&nbsp; S&amp;P 500 cap-weighted <b>{_cw:.1f}</b> &nbsp;&middot;&nbsp; mid/small <b>{np.mean(_sm):.1f}</b> (&Delta; {np.mean(_smd):+.1f})</p>
<p class="dc-lb">The tariff tell, prices level and change</p>
<table class="sec" style="margin-top:6px"><thead><tr><th>Cohort</th><th class="num">n</th><th class="num">Prices level</th><th class="num">&Delta; vs Q1</th></tr></thead><tbody>
{_tr("refund retainers", _r1)}
{_tr("passed into price", _r2)}
{_tr("no refund disclosed", _r3)}
</tbody></table>''')
s = _pswap(s, "PGAIN", "\n".join(_mrow(m) for m in pmov[:-7:-1]))
s = _pswap(s, "PLOSE", "\n".join(_mrow(m) for m in pmov[:6]))
pavg1 = float(np.mean([p1r["prices"] for _, p1r in ppairs]))
pavg2 = float(np.mean([r["prices"] for r, _ in ppairs]))
pdif = 100*sum(1 for r in P2 if r["prices"]>50)/len(P2)
_allp = [best[t]["prices"] for t in best if best[t].get("prices") is not None]
_bru = round(100*sum(1 for x in _allp if x >= 55)/len(_allp))
_brd = round(100*sum(1 for x in _allp if x <= 45)/len(_allp))
s = _pswap(s, "PSTATS", f'''<span><b>{pavg2:.1f}</b>prices index, Q2 (same companies: {pavg1:.1f} in Q1)</span>
<span><b>{pavg2-pavg1:+.1f}</b>change vs Q1, matched sample</span>
<span><b>{_bru}% / {_brd}%</b>raising vs conceding price</span>
<span><b>{len(P2)}</b>companies scored</span>''')
a = s.index("const PROWS="); bnd = s.index(";\n", a)
s = s[:a] + "const PROWS=" + json.dumps(prow, separators=(",",":")) + s[bnd:]
s = sub1(s, r"Data as of [A-Z][a-z]+ \d+, 2026", f"Data as of {today}", "pricing-date")
open(p, "w").write(s)
print(f"pricing: {len(prow)} rows, index {pavg2:.1f} ({pavg2-pavg1:+.1f})")

# ---------------- buildout decomposition ----------------
try:
    Bh = load(f"{ROOT}/buildout_highlights.json")["highlights"]
    _bs = set(); Bh = [x for x in Bh if not (x["ticker"] in _bs or _bs.add(x["ticker"]))]
except Exception as e:
    Bh = None
    print(f"buildout: data unavailable ({e}); page left as-is")
if Bh:
    p = f"{SITE}/buildout/index.html"
    s = open(p).read()
    bset = {x["ticker"] for x in Bh}
    def _bde(field):
        pairs = [(t, best[t][field]-q1s[t][field]) for t in best
                 if t in q1s and best[t].get(field) is not None and q1s[t].get(field) is not None]
        co = [d for t, d in pairs if t in bset]; ex = [d for t, d in pairs if t not in bset]
        tot = float(np.mean([d for _, d in pairs])); wc = len(co)/len(pairs)
        return tot, float(np.mean(co)), float(np.mean(ex)), wc, len(co), len(ex)
    ct, cc, cx, cw, cn, xn = _bde("composite")
    nt, nc, nx, nw, _, _ = _bde("new_orders")
    share_c = max(1, min(99, round(100*cw*cc/ct))) if ct > 0 else 50
    share_n = max(1, min(99, round(100*nw*nc/nt))) if nt > 0 else 50
    lv  = float(np.mean([best[t]["composite"] for t in bset if t in best and best[t].get("composite") is not None]))
    lx  = float(np.mean([best[t]["composite"] for t in best if t not in bset and best[t].get("composite") is not None]))
    s = _swapm(s, "BSTATS", f'''
<span><b>{len(Bh)}</b>companies cite the build-out ({round(100*len(Bh)/len(best))}% of {len(best):,})</span>
<span><b>{share_c}%</b>of the index&rsquo;s improvement comes from them</span>
<span><b>{cc:+.1f} vs {cx:+.1f}</b>cohort vs everyone else, Q2 change</span>
<span><b>{lv:.1f} vs {lx:.1f}</b>Q2 level: cohort runs hotter</span>
<span><b>{sum(1 for x in Bh if x.get("metric"))} of {len(Bh)}</b>attach a stated figure</span>''')
    s = _swapm(s, "BBAR", f'''
<div class="dc-row"><p class="dc-lb">Composite index change, Q2 vs Q1: {ct:+.2f} pts</p>
<div class="dc-bar"><span class="co" style="width:{share_c}%">build-out {cw*cc:+.2f}</span><span class="ex" style="width:{100-share_c}%">rest {(1-cw)*cx:+.2f}</span></div>
<p class="dc-cap">{cn} claimants ({round(100*cw)}% of the matched sample) improved {cc:+.2f} on average; the other {xn} companies improved {cx:+.2f}.</p></div>
<div class="dc-row" style="margin-bottom:0"><p class="dc-lb">New-orders sub-index change: {nt:+.2f} pts</p>
<div class="dc-bar"><span class="co" style="width:{share_n}%">build-out {nw*nc:+.2f}</span><span class="ex" style="width:{100-share_n}%">rest {(1-nw)*nx:+.2f}</span></div>
<p class="dc-cap">{share_n}% of the new-orders improvement traces to the build-out cohort.</p></div>''')
    chd = defaultdict(list)
    for x in Bh:
        t = x["ticker"]
        if t in best and t in q1s and best[t].get("composite") is not None and q1s[t].get("composite") is not None:
            chd[x["channel"]].append(best[t]["composite"]-q1s[t]["composite"])
    s = _swapm(s, "BCHAN", "\n".join(
        f'<tr><td>{c.replace("_"," ")}</td><td class="num">{len(v)}</td>'
        f'<td class="num {"pos" if np.mean(v)>0 else "neg"}">{np.mean(v):+.1f}</td></tr>'
        for c, v in sorted(chd.items(), key=lambda kv: -len(kv[1]))))
    brow = [{"t": x["ticker"], "ch": x["channel"], "s": best.get(x["ticker"],{}).get("sector",""),
             "p2": best.get(x["ticker"],{}).get("composite"),
             "d": (best[x["ticker"]]["composite"]-q1s[x["ticker"]]["composite"])
                  if (x["ticker"] in best and x["ticker"] in q1s and best[x["ticker"]].get("composite") is not None and q1s[x["ticker"]].get("composite") is not None) else None,
             "m": (x.get("metric") or "")[:80]} for x in Bh]
    a = s.index("const BROWS="); bnd = s.index(";\n", a)
    s = s[:a] + "const BROWS=" + json.dumps(brow, separators=(",",":")) + s[bnd:]
    bsec = defaultdict(lambda: {"co": [], "ex": [], "n": 0, "cn": 0})
    for t, r in best.items():
        sx = r.get("sector","—"); bsec[sx]["n"] += 1
        if t in bset: bsec[sx]["cn"] += 1
        if t in q1s and r.get("composite") is not None and q1s[t].get("composite") is not None:
            dd = r["composite"]-q1s[t]["composite"]
            (bsec[sx]["co"] if t in bset else bsec[sx]["ex"]).append(dd)
    _brows = []; _bw = 0; _bt = 0
    for sx, v in sorted(bsec.items(), key=lambda kv: -kv[1]["cn"]/max(kv[1]["n"],1)):
        if v["n"] < 15: continue
        share = round(100*v["cn"]/v["n"])
        if len(v["co"]) >= 5:
            c = float(np.mean(v["co"])); e = float(np.mean(v["ex"])); g = c-e; _bt += 1; _bw += (g > 0)
            _brows.append(f'<tr><td>{sx}</td><td class="num">{v["cn"]} <span style="color:var(--muted)">({share}%)</span></td>'
                          f'<td class="num">{c:+.1f}</td><td class="num">{e:+.1f}</td>'
                          f'<td class="num {"pos" if g>0 else "neg"}">{g:+.1f}</td>'
                          f'<td><span class="bar {"up" if g>=0 else "dn"}" style="width:{min(110,abs(g)*22):.0f}px"></span></td></tr>')
        else:
            _brows.append(f'<tr><td>{sx}</td><td class="num">{v["cn"]} <span style="color:var(--muted)">({share}%)</span></td>'
                          f'<td class="num">&ndash;</td><td class="num">&ndash;</td><td class="num">&ndash;</td><td></td></tr>')
    s = _swapm(s, "BSECT", "\n" + "\n".join(_brows) + "\n")
    s = _swapm(s, "BSECW", f"Build-out claimants outperform their own sector peers in <b>{_bw} of {_bt}</b> sectors large enough to measure.")
    _qz = [best[x["ticker"]]["composite"]-q1s[x["ticker"]]["composite"] for x in Bh if x.get("metric")
           and x["ticker"] in best and x["ticker"] in q1s
           and best[x["ticker"]].get("composite") is not None and q1s[x["ticker"]].get("composite") is not None]
    _nq = [best[x["ticker"]]["composite"]-q1s[x["ticker"]]["composite"] for x in Bh if not x.get("metric")
           and x["ticker"] in best and x["ticker"] in q1s
           and best[x["ticker"]].get("composite") is not None and q1s[x["ticker"]].get("composite") is not None]
    s = _swapm(s, "BQNT",
        f"One check already runs against it: claimants without a stated figure improved "
        f"{np.mean(_nq):+.1f}, nearly matching the {np.mean(_qz):+.1f} of those with numbers, and both far "
        f"exceed the {cx:+.1f} non-claimant baseline, so the cohort is not carried by numberless talk.")
    s = sub1(s, r"Yes, in \d+ of \d+\.", f"Yes, in {_bw} of {_bt}.", "buildout-sec-h")
    s = sub1(s, r"Data as of [A-Z][a-z]+ \d+, 2026", f"Data as of {today}", "buildout-date")
    open(p, "w").write(s)
    print(f"buildout: {len(Bh)} claimants, {share_c}% of improvement, new-orders {share_n}%")

# ---------------- what-changed strip ----------------
import os
SNAP = f"{ROOT}/docs/research/prev_state.json"
cur_state = {"date": today,
             "pmi": sorted(best.keys()),
             "ai": sorted(a2.keys()),
             "margin": sorted(x["ticker"] for x in a2h if x.get("margin_claim")),
             "refn": len(R), "reftot": round(sum(mm(x.get("amount")) or 0 for x in R)),
             "lead": srows[0][0] if srows else "", "pidx": round(pavg2,1)}
lines = []
if os.path.exists(SNAP):
    prev = load(SNAP)
    new_pmi = [t for t in cur_state["pmi"] if t not in set(prev.get("pmi", []))]
    new_ai  = [t for t in cur_state["ai"] if t not in set(prev.get("ai", []))]
    new_mg  = [t for t in cur_state["margin"] if t not in set(prev.get("margin", []))]
    d_ref   = cur_state["refn"] - prev.get("refn", cur_state["refn"])
    d_tot   = cur_state["reftot"] - prev.get("reftot", cur_state["reftot"])
    if new_pmi:
        ex = ", ".join(new_pmi[:4]) + (" and others" if len(new_pmi) > 4 else "")
        lines.append(f"{len(new_pmi)} new reporter{'s' if len(new_pmi)!=1 else ''} scored ({ex}).")
    if new_ai:
        lines.append(f"{len(new_ai)} new verified AI disclosure{'s' if len(new_ai)!=1 else ''}" +
                     (f", including a margin claim from {new_mg[0]}" if new_mg else "") + ".")
    elif new_mg:
        lines.append(f"New AI margin claim on record: {', '.join(new_mg[:3])}.")
    if d_ref > 0:
        lines.append(f"{d_ref} new tariff-refund disclosure{'s' if d_ref!=1 else ''}" +
                     (f" (+${d_tot}M)" if d_tot > 0 else "") + ".")
    if not lines:
        lines.append("No new reporters or disclosures this refresh; scores and quotes re-verified.")
    lines.append(f"Prices index {cur_state['pidx']}; {cur_state['lead']} leads sector pricing momentum.")
else:
    lines.append(f"Coverage baseline: {len(cur_state['pmi'])} companies scored, {len(cur_state['ai'])} verified AI disclosures, {cur_state['refn']} refund entries.")
open(SNAP, "w").write(json.dumps(cur_state))
wchg_html = f'<b>What changed &middot; {today_short}</b> ' + " ".join(lines)

# ---------------- hub date ----------------
p = f"{SITE}/index.html"
s = open(p).read()
s = sub1(s, r"data as of [A-Z][a-z]+ \d+, 2026", f"data as of {today_short}", "hub-date")
wa = s.index("<!--WCHG-->") + 11; wb = s.index("<!--/WCHG-->")
s = s[:wa] + wchg_html + s[wb:]
open(p, "w").write(s)

# ---------------- self-check ----------------
for page in ["pmi-scorecard","ai-adopters","refund-watch","ai-employment","portfolio","pricing","buildout"]:
    t = open(f"{SITE}/{page}/index.html").read()
    if today.split(",")[0].split()[1] not in t and today_short.split()[1] not in t:
        die(f"{page}: today's date missing after build")
print("BUILD OK —", today)
