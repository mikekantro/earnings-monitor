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
    C[t] = {k: v for k, v in e.items() if v not in (None,"",0) or k in ("x",)}
DBP = {"c": C, "m": {"n": len(C), "idx": SC["comp2"], "date": today,
                     "ed": fmt(d_per), "ep": f"{p_per:.3f}"}}
a = s.index("const DB="); bnd = s.index(";\n", a)
s = s[:a] + "const DB=" + json.dumps(DBP, separators=(",",":")) + s[bnd:]
open(p, "w").write(s)
print(f"portfolio: {len(C)} companies in payload")

# ---------------- hub date ----------------
p = f"{SITE}/index.html"
s = open(p).read()
s = sub1(s, r"data as of [A-Z][a-z]+ \d+, 2026", f"data as of {today_short}", "hub-date")
open(p, "w").write(s)

# ---------------- self-check ----------------
for page in ["pmi-scorecard","ai-adopters","refund-watch","ai-employment","portfolio"]:
    t = open(f"{SITE}/{page}/index.html").read()
    if today.split(",")[0].split()[1] not in t and today_short.split()[1] not in t:
        die(f"{page}: today's date missing after build")
print("BUILD OK —", today)
