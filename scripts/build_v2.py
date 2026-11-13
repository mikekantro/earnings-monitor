#!/usr/bin/env python3
"""Render the v2 single-page dashboard (mockup layout) from v2_data.json.

One page, portal-style left sidebar with a section tree, bordered cards,
stat boxes with tooltips, heat-shaded tables. Regenerated on every build.
"""
import json, os, html

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
V = json.load(open(f"{ROOT}/v2_data.json"))
OUT = f"{ROOT}/docs/research/v2/index.html"
os.makedirs(os.path.dirname(OUT), exist_ok=True)

esc = lambda x: html.escape(str(x if x is not None else ""))

TIPS = {
 "composite": "Weighted average of the six sub-indexes (new orders 30%, output 25%, employment 15%, prices 10%, supply chains 10%, demand breadth 10%), scored 0-100 from each company's earnings call under a fixed rubric; 50 divides expansion from contraction. This index's empirical neutral is %NEUT% (pooled median, 15 seasons)." ,
 "above50": "Share of reported companies whose composite is above 50. Earnings-call narratives skew optimistic, so read against the empirical neutral of %NEUT%, not 50.",
 "impdec": "Companies whose composite rose vs fell against their own Q2 score (matched sample).",
 "pairs": "Companies scored in both Q2 and Q3; all season-over-season figures use this matched sample.",
 "subidx": "Same companies, each season. Scores 0-100.",
 "secchg": "Mean composite change, Q3 vs the same companies' Q2, by sector.",
 "through": "Equal-weight mean of every scored company, each earnings season, on the same rubric and model throughout.",
 "movers": "Largest same-company composite swings, Q2 to Q3, with the key signal line from the company's own call.",
 "mega": "The five largest index weights; levels are composite scores, change vs own Q2.",
 "sectors": "Every sub-index by sector; heat shading is within-column.",
 "industries": "GICS industries with at least 2 reporters; search, filter and page through all rows.",
}

def tip(key):
    t = TIPS.get(key, "")
    t = t.replace("%NEUT%", str(V["neut"]))
    return f'<span class="info" title="{esc(t)}">i</span>'

def statcards():
    sc = V["sc"]
    cards = [
      ("Q3 COMPOSITE", f"{sc['comp2']:.1f}", f"{sc['comp2']-sc['comp1']:+.1f} vs Q2 ({sc['comp1']:.1f})", "composite"),
      ("ABOVE 50", f"{sc['breadth']}%", "of companies reporting expansion", "above50"),
      ("IMPROVING / DECLINING", f"<span class='pos'>{sc['up']}</span> / <span class='neg'>{sc['down']}</span>", "vs their own Q2 score", "impdec"),
      ("SAME-COMPANY PAIRS", f"{sc['n']:,}", f"in both Q2 and Q3 · {V['reported']:,} reported", "pairs"),
    ]
    inner = "".join(
      f'<div class="stat"><p class="slab">{lab} {tip(k)}</p><p class="sval">{val}</p><p class="ssub">{sub}</p></div>'
      for lab, val, sub, k in cards)
    return f'<div class="stats">{inner}</div>'

def subidx_table():
    rows = "".join(
      f'<tr class="{ "hero" if r["k"]=="Composite" else "" }"><td>{esc(r["k"])}</td>'
      f'<td class="num">{r["q1"]:.1f}</td><td class="num">{r["q2"]:.1f}</td>'
      f'<td class="num"><b>{r["q3"]:.1f}</b></td>'
      f'<td class="num {"pos" if r["d"]>0 else "neg"}">{r["d"]:+.1f}</td></tr>'
      for r in V["score"])
    return (f'<table class="t"><thead><tr><th></th><th class="num">Q1</th><th class="num">Q2</th>'
            f'<th class="num">Q3</th><th class="num">CHG</th></tr></thead><tbody>{rows}</tbody></table>')

def secbars():
    mx = max(abs(x["d"]) for x in V["sectors"]) or 1
    rows = "".join(
      f'<div class="brow"><span class="bl">{esc(x["s"])}</span>'
      f'<span class="bar {"up" if x["d"]>=0 else "dn"}" style="width:{abs(x["d"])/mx*120:.0f}px"></span>'
      f'<span class="bv {"pos" if x["d"]>=0 else "neg"}">{x["d"]:+.1f}</span></div>'
      for x in sorted(V["sectors"], key=lambda x: -x["d"]))
    return f'<div class="bars">{rows}</div>'

def movers_card(side, title):
    rows = "".join(
      f'<div class="mcard"><p class="mh"><b>{esc(m["t"])}</b> <span class="msec">{esc(m["s"])}</span>'
      f'<span class="mnum">{m["q1"]} → {m["q2"]} <span class="{"pos" if m["q2"]>=m["q1"] else "neg"}">{m["q2"]-m["q1"]:+d}</span></span></p>'
      f'<p class="mq">{esc(m["k"])}</p></div>'
      for m in V["movers"][side])
    return (f'<div class="card"><h3>{title} {tip("movers")} <span class="sub">composite, Q2 → Q3</span></h3>'
            f'<div class="scrollbox">{rows}</div><p class="src">{SRC}</p></div>')

SRC = "Source: Piper Sandler Portfolio Strategy Earnings Intelligence"

mega_chips = "".join(
  f'<span class="chip">{esc(m["t"])} {m["q2"]} <span class="{"pos" if m["q2"]>=m["q1"] else "neg"}">{m["q2"]-m["q1"]:+d}</span></span>'
  for m in V["mega"])

PAYLOAD = json.dumps({
  "hdata": V["hdata"], "ihdata": V["ihdata"], "ihsec": V["ihsec"], "neut": V["neut"],
  "secdata": V["secdata"], "inddata": V["inddata"], "tbl": V["tbl"], "rt": V["rt"],
}, separators=(",", ":"))

PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Earnings Intelligence</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root{--ink:#0A0A0A;--rule:#E5E5E5;--muted:#666;--acc:#1E5162;--dn:#C24F1F;--band:#F5F5F5}
*{box-sizing:border-box}
body{margin:0;font-family:Inter,Helvetica,Arial,sans-serif;color:var(--ink);background:#fff;font-size:14px;line-height:1.55;font-variant-numeric:tabular-nums}
a{color:var(--acc);text-decoration:none}
.top{border-bottom:1px solid var(--rule);padding:14px 24px;display:flex;align-items:center;gap:10px;position:sticky;top:0;background:#fff;z-index:60}
.top b{font-weight:700;font-size:13px;letter-spacing:.06em}
.top i{width:2px;height:14px;background:var(--acc);display:inline-block}
.top span{font-weight:600;font-size:11px;letter-spacing:.14em;color:var(--muted);text-transform:uppercase}
.layout{display:flex;min-height:100vh}
aside{width:232px;flex:0 0 232px;border-right:1px solid var(--rule);padding:22px 18px;position:sticky;top:49px;height:calc(100vh - 49px);overflow-y:auto}
.se{font-size:10px;font-weight:600;letter-spacing:.13em;color:var(--muted);text-transform:uppercase;margin:0 0 4px}
.sse{font-size:15px;font-weight:600;margin:0}
.ssn{font-size:12px;color:var(--muted);margin:2px 0 16px}
aside .g{font-size:13px;font-weight:600;margin:14px 0 3px}
aside .g a{color:var(--ink)}
aside .l{display:block;font-size:12.5px;color:var(--muted);padding:3px 0 3px 12px;border-left:2px solid transparent}
aside .l:hover{color:var(--ink)}
aside .l.on{color:var(--acc);border-left-color:var(--acc);font-weight:600}
main{flex:1;min-width:0;padding:26px 30px 70px;max-width:1240px}
h1{font-weight:300;font-size:28px;margin:0 0 4px}
.thesis{font-size:14.5px;color:#333;margin:0 0 16px}
h2{font-weight:300;font-size:22px;margin:40px 0 12px;padding-top:10px}
h2 .grp{color:var(--muted)}
h3{font-size:16px;font-weight:600;margin:0 0 10px}
h3 .sub{font-weight:400;font-size:12.5px;color:var(--muted);margin-left:6px}
.info{display:inline-flex;align-items:center;justify-content:center;width:14px;height:14px;border:1px solid #C6CCD1;border-radius:50%;font-size:9px;font-style:italic;color:var(--muted);cursor:help;vertical-align:1px}
.stats{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:14px;margin:0 0 18px}
.stat{border:1px solid var(--rule);border-radius:8px;padding:12px 16px;background:#fff}
.slab{font-size:10.5px;font-weight:600;letter-spacing:.09em;color:var(--muted);margin:0 0 6px;text-transform:uppercase}
.sval{font-size:24px;font-weight:500;margin:0}
.ssub{font-size:12px;color:var(--muted);margin:4px 0 0}
.card{border:1px solid var(--rule);border-radius:8px;padding:16px 18px;background:#fff;margin:0 0 16px}
.grid2{display:grid;grid-template-columns:3fr 2fr;gap:16px;align-items:start}
.grid2eq{display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:start}
@media(max-width:1000px){.grid2,.grid2eq{grid-template-columns:1fr}aside{display:none}}
.t{width:100%;border-collapse:collapse;font-size:13px}
.t th{font-size:10px;font-weight:600;letter-spacing:.08em;text-transform:uppercase;color:var(--muted);text-align:left;padding:7px 8px;border-bottom:1px solid var(--rule)}
.t th.num{text-align:right}
.t td{padding:7px 8px;border-bottom:1px solid #F0F0F0}
.t td.num{text-align:right;white-space:nowrap}
.t tr.hero td{background:#F4F8F9;font-weight:600}
.t td.heat{text-align:right;color:#fff;font-weight:600;border-radius:3px}
.pos{color:var(--acc);font-weight:600}.neg{color:var(--dn);font-weight:600}
.chip{display:inline-block;border:1px solid var(--rule);border-radius:16px;padding:5px 12px;font-size:12.5px;font-weight:600;margin:0 6px 6px 0;background:#fff;cursor:pointer}
.chip.on{background:var(--acc);color:#fff;border-color:var(--acc)}
.bars .brow{display:flex;align-items:center;gap:8px;margin:5px 0}
.bars .bl{flex:0 0 165px;font-size:12.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.bars .bar{height:10px;border-radius:2px}
.bars .bar.up{background:var(--acc)}.bars .bar.dn{background:var(--dn)}
.bars .bv{font-size:12px;min-width:38px;text-align:right}
.scrollbox{max-height:430px;overflow-y:auto;padding-right:6px}
.mcard{border-bottom:1px solid #F0F0F0;padding:9px 0}
.mh{margin:0;font-size:13px;display:flex;gap:8px;align-items:baseline}
.msec{color:var(--muted);font-size:11.5px}
.mnum{margin-left:auto;white-space:nowrap}
.mq{margin:4px 0 0;font-size:12.5px;color:#4A4F54}
.src{font-size:9.5px;color:#9AA4AB;margin:8px 0 0}
input[type=search],select{font:13px Inter,Helvetica,Arial,sans-serif;padding:7px 10px;border:1px solid #D8DEE2;border-radius:6px}
.more button,.pg button{font:12.5px Inter;font-weight:600;padding:6px 12px;border:1px solid var(--rule);border-radius:4px;background:#fff;color:var(--acc);cursor:pointer}
.pg{display:flex;gap:8px;align-items:center;justify-content:flex-end;margin-top:8px;font-size:12px;color:var(--muted)}
.mockup{display:inline-block;background:var(--dn);color:#fff;font-size:10px;font-weight:700;letter-spacing:.06em;border-radius:4px;padding:3px 8px;vertical-align:4px;margin-left:8px}
.coming{color:var(--muted);font-size:13px;border:1px dashed var(--rule);border-radius:8px;padding:18px;margin:0 0 16px}
svg text{font-family:Inter,Helvetica,Arial,sans-serif}
</style></head><body>

<div class="top"><b>PIPER</b><i></i><span>Sandler &middot; Portfolio Strategy</span></div>
<div class="layout">
<aside>
  <p class="se">Earnings season</p>
  <p class="sse">%SEASON% season</p>
  <p class="ssn">%REPORTED% of %UNIV% reported</p>
  <div id="nav"></div>
</aside>
<main>
<h1>Earnings Intelligence <span class="mockup">V2 PREVIEW</span></h1>
<p class="thesis">%THESIS%</p>

<section id="pmi"><a id="pmi-overview"></a>
<h2><span class="grp">Earnings PMI &middot;</span> Overview</h2>
%STATS%
<div class="grid2">
  <div class="card"><h3>The index through time %TIP_THROUGH% <span class="sub">select a series</span>
    <select id="v2sec" style="float:right;margin-top:-4px"></select></h3>
    <div class="clegend" id="v2hleg"></div>
    <div id="v2hchart"></div><p class="src">%SRC%</p></div>
  <div>
    <div class="card"><h3>Sub-indexes %TIP_SUB% <span class="sub">same companies, each season</span></h3>
      %SUBIDX%<p class="src">%SRC%</p></div>
    <div class="card"><h3>Composite change by sector %TIP_SECCHG% <span class="sub">Q3 vs Q2</span></h3>
      %SECBARS%<p class="src">%SRC%</p></div>
  </div>
</div>
</section>

<a id="pmi-sectors"></a>
<h2><span class="grp">Earnings PMI &middot;</span> Sectors &amp; industries</h2>
<p style="margin:0 0 10px">Sub-index: <span id="v2chips"></span></p>
<div class="grid2eq">
  <div class="card"><h3>Sectors %TIP_SECTORS%</h3><table class="t" id="v2sect"></table><p class="src">%SRC%</p></div>
  <div class="card"><h3>Industries %TIP_IND%</h3>
    <p style="margin:0 0 8px"><input type="search" id="v2isrch" placeholder="Industry"> <select id="v2isec"><option value="">All sectors</option></select> <span class="sub" id="v2icount"></span></p>
    <table class="t" id="v2indt"></table>
    <div class="pg"><button id="v2ipr">&lsaquo;</button><span id="v2ipg"></span><button id="v2inx">&rsaquo;</button></div>
    <p class="src">%SRC%</p></div>
</div>
<div class="card"><h3>Industry time series <span class="sub">locked scale across industries</span>
  <select id="v2itsel" style="float:right;margin-top:-4px"></select></h3>
  <div class="clegend" id="v2itleg"></div><div id="v2itchart"></div><p class="src">%SRC%</p></div>
<div class="card"><h3>Compare sectors &amp; industries <span class="sub">up to six series, one metric, one scale</span></h3>
  <p style="margin:0 0 8px"><span id="v2cmet"></span></p>
  <p style="margin:0 0 8px"><select id="v2csec"><option value="">+ add sector&hellip;</option></select>
  <select id="v2cind"><option value="">+ add industry&hellip;</option></select></p>
  <div id="v2csel"></div><div class="clegend" id="v2cleg"></div><div id="v2cchart"></div><p class="src">%SRC%</p></div>

<a id="pmi-movers"></a>
<h2><span class="grp">Earnings PMI &middot;</span> Movers</h2>
<p style="margin:0 0 10px">Mega-caps %TIP_MEGA%: %MEGA%</p>
<div class="grid2eq">%MOVUP%%MOVDN%</div>

<a id="pmi-companies"></a>
<h2><span class="grp">Earnings PMI &middot;</span> Every company</h2>
<div class="card">
  <p style="margin:0 0 10px"><input type="search" id="v2q" placeholder="Search ticker, sector, or what the company said&hellip;" style="width:340px">
  <select id="v2fsec"><option value="">All sectors</option></select>
  <select id="v2fsort"><option value="d_desc">Sort: biggest improvement</option><option value="d_asc">Sort: biggest decline</option><option value="q2_desc">Sort: highest Q3</option><option value="q2_asc">Sort: lowest Q3</option><option value="t">Ticker A&ndash;Z</option></select>
  <span class="sub" id="v2count"></span></p>
  <table class="t"><thead><tr><th>Ticker</th><th>Sector</th><th class="num">Q2</th><th class="num">Q3</th><th class="num">&Delta;</th><th>Key signal from the latest call</th></tr></thead><tbody id="v2tb"></tbody></table>
  <div class="more" style="text-align:center;margin-top:10px"><button id="v2more">Show 100 more</button></div>
  <p class="src">%SRC%</p></div>

<a id="rt"></a><a id="rt-overview"></a>
<h2><span class="grp">Read-Through &middot;</span> Who reports next</h2>
<div class="coming">Carried from the Read-Through tab &mdash; lands in this preview next pass, along with Pricing, AI adoption, AI build-out, AI &amp; hiring, Tariff refunds, Portfolio screen and About the data. The live v1 pages remain the production site.</div>

</main></div>

<script>const V2=%PAYLOAD%;</script>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/&/g,"&amp;").replace(/</g,"&lt;");
const FL=[["composite","#0A0A0A",3.0,"Composite"],["new_orders","#1E5162",1.8,"New orders"],["prices","#C24F1F",1.8,"Prices"],["employment","#9AA4AB",1.8,"Employment"]];
const SF=[["composite","Composite"],["new_orders","New orders"],["output","Output"],["employment","Employment"],["prices","Prices"],["supply_chains","Supply chains"],["demand_breadth","Demand breadth"],["confidence","Confidence"]];
const NEUT=V2.neut;
function leg(id,items){$(id).innerHTML=items.map(x=>`<span style="margin-right:14px;font-size:12px;color:#444B50"><i style="display:inline-block;width:10px;height:10px;border-radius:2px;background:${x[1]};margin-right:6px;vertical-align:-1px"></i>${esc(x[0])}</span>`).join("")}
function line(id,rowsBy,sel,ext){ // multi-sub-index chart for one selection
const rows=rowsBy[sel]||[];
const W=760,H=300,L=46,Bm=40,T=14,R=52;
const y0=ext[0],y1=ext[1],n=rows.length;
const X=i=>L+(i/Math.max(n-1,1))*(W-L-R),Y=v=>H-Bm-(v-y0)/(y1-y0)*(H-Bm-T);
let o=`<svg viewBox="0 0 ${W} ${H}" style="width:100%">`;
for(let v=Math.ceil(y0/2)*2;v<=y1;v+=2){o+=`<line x1="${L}" y1="${Y(v)|0}" x2="${W-R}" y2="${Y(v)|0}" stroke="#F0F2F4"/><text x="${L-6}" y="${Y(v)|0}" font-size="10" fill="#666" text-anchor="end" dominant-baseline="middle">${v}</text>`}
rows.forEach((r,i)=>{if((i%2===0&&i<n-2)||i===n-1)o+=`<text x="${X(i)|0}" y="${H-Bm+15}" font-size="10" fill="#666" text-anchor="middle">${r.l}</text>`});
const labs=[];
FL.forEach(f=>{const pts=rows.map((r,i)=>r[f[0]]!=null?[X(i),Y(r[f[0]]),r[f[0]]]:null).filter(Boolean);
if(pts.length<2)return;
o+=`<path d="M${pts.map(p=>(p[0]|0)+" "+(p[1]|0)).join(" L")}" fill="none" stroke="${f[1]}" stroke-width="${f[2]}"/>`;
pts.forEach(p=>o+=`<circle cx="${p[0]|0}" cy="${p[1]|0}" r="2.4" fill="${f[1]}"/>`);
labs.push({y:pts[pts.length-1][1]+3,x:pts[pts.length-1][0]+8,c:f[1],t:pts[pts.length-1][2].toFixed(1)})});
labs.sort((a,b)=>a.y-b.y);for(let i=1;i<labs.length;i++)if(labs[i].y-labs[i-1].y<13)labs[i].y=labs[i-1].y+13;
labs.forEach(l=>o+=`<text x="${l.x|0}" y="${l.y|0}" font-size="11" font-weight="600" fill="${l.c}">${l.t}</text>`);
$(id).innerHTML=o+"</svg>"}
const HEXT=(()=>{const ys=[];Object.values(V2.hdata).forEach(rs=>rs.forEach(r=>FL.forEach(f=>{if(r[f[0]]!=null)ys.push(r[f[0]])})));return[Math.min(...ys)-2,Math.max(...ys)+2]})();
const IEXT=(()=>{const ys=[];Object.values(V2.ihdata).forEach(rs=>rs.forEach(r=>FL.forEach(f=>{if(r[f[0]]!=null)ys.push(r[f[0]])})));return[Math.min(...ys)-2,Math.max(...ys)+2]})();
// overview chart + selector
(function(){const s=$("v2sec");Object.keys(V2.hdata).forEach(k=>{const o=document.createElement("option");o.value=k;o.textContent=k==="All"?"All sectors":k;s.appendChild(o)});
leg("v2hleg",FL.map(f=>[f[3],f[1]]));
s.onchange=()=>line("v2hchart",V2.hdata,s.value,HEXT);line("v2hchart",V2.hdata,"All",HEXT)})();
// industry TS
(function(){const s=$("v2itsel");const by={};Object.keys(V2.ihdata).forEach(k=>{(by[V2.ihsec[k]||"Other"]=by[V2.ihsec[k]||"Other"]||[]).push(k)});
Object.keys(by).sort().forEach(g=>{const og=document.createElement("optgroup");og.label=g;by[g].sort().forEach(k=>{const o=document.createElement("option");o.value=k;o.textContent=k;og.appendChild(o)});s.appendChild(og)});
const d=V2.ihdata["Semiconductors & Semiconductor Equipment"]?"Semiconductors & Semiconductor Equipment":Object.keys(V2.ihdata)[0];
s.value=d;leg("v2itleg",FL.map(f=>[f[3],f[1]]));
s.onchange=()=>line("v2itchart",V2.ihdata,s.value,IEXT);line("v2itchart",V2.ihdata,d,IEXT)})();
// sector/industry tables with heat + chips
let fld="composite";
function heat(v,min,max){const t=(v-min)/Math.max(max-min,.001);const a=.15+.75*t;return `background:rgba(30,81,98,${a.toFixed(2)})`}
function chips(){$("v2chips").innerHTML=SF.filter(f=>V2.secdata[f[0]]&&V2.secdata[f[0]].length).map(f=>`<span class="chip ${f[0]===fld?"on":""}" onclick="fld='${f[0]}';chips();sect();indt()">${f[1]}</span>`).join("")}
let ssort=[2,-1];
function sect(){let rows=[...(V2.secdata[fld]||[])];rows.sort((a,b)=>(a[ssort[0]]<b[ssort[0]]?-1:1)*(typeof a[ssort[0]]==="string"?-ssort[1]:-1)*-1*ssort[1]||0);
rows.sort((a,b)=>{const x=a[ssort[0]],y=b[ssort[0]];return (typeof x==="string"?x.localeCompare(y):x-y)*ssort[1]});
const vals=rows.map(r=>r[2]);const mn=Math.min(...vals),mx=Math.max(...vals);
$("v2sect").innerHTML=`<thead><tr><th onclick="ssort=[0,ssort[0]===0?-ssort[1]:1];sect()">Sector</th><th class="num" onclick="ssort=[1,ssort[0]===1?-ssort[1]:-1];sect()">cos.</th><th class="num" onclick="ssort=[2,ssort[0]===2?-ssort[1]:-1];sect()">Q3 level</th><th class="num" onclick="ssort=[3,ssort[0]===3?-ssort[1]:-1];sect()">chg</th></tr></thead><tbody>`+
rows.map(r=>`<tr><td>${esc(r[0])}</td><td class="num">${r[1]}</td><td class="num"><span class="heat" style="${heat(r[2],mn,mx)};color:#fff;padding:2px 8px;border-radius:3px;font-weight:600">${r[2].toFixed(1)}</span></td><td class="num ${r[3]>0?"pos":"neg"}">${r[3]>0?"+":""}${r[3].toFixed(1)}</td></tr>`).join("")+"</tbody>"}
let ipage=0,isrch="",isecf="";
function indt(){let rows=(V2.inddata[fld]||[]).filter(r=>(!isrch||r[0].toLowerCase().includes(isrch))&&(!isecf||r[1]===isecf));
const vals=rows.map(r=>r[3]);const mn=Math.min(...vals),mx=Math.max(...vals);
const per=12,np=Math.max(1,Math.ceil(rows.length/per));ipage=Math.min(ipage,np-1);
const pg=rows.slice(ipage*per,ipage*per+per);
$("v2indt").innerHTML=`<thead><tr><th>Industry</th><th>Sector</th><th class="num">cos.</th><th class="num">Q3 level</th><th class="num">chg</th></tr></thead><tbody>`+
pg.map(r=>`<tr><td>${esc(r[0])}</td><td style="color:#666;font-size:12px">${esc(r[1])}</td><td class="num">${r[2]}</td><td class="num"><span style="${heat(r[3],mn,mx)};color:#fff;padding:2px 8px;border-radius:3px;font-weight:600">${r[3].toFixed(1)}</span></td><td class="num ${r[4]>0?"pos":"neg"}">${r[4]>0?"+":""}${r[4].toFixed(1)}</td></tr>`).join("")+"</tbody>";
$("v2ipg").textContent=`${ipage*per+1}–${Math.min(rows.length,(ipage+1)*per)} of ${rows.length}`;
$("v2icount").textContent=rows.length+" rows"}
$("v2isrch").oninput=e=>{isrch=e.target.value.toLowerCase();ipage=0;indt()};
(function(){const s=$("v2isec");[...new Set((V2.inddata.composite||[]).map(r=>r[1]))].sort().forEach(x=>{const o=document.createElement("option");o.value=x;o.textContent=x;s.appendChild(o)});s.onchange=e=>{isecf=e.target.value;ipage=0;indt()}})();
$("v2ipr").onclick=()=>{ipage=Math.max(0,ipage-1);indt()};$("v2inx").onclick=()=>{ipage++;indt()};
chips();sect();indt();
// compare chart
const CMPCOL=["#1E5162","#C24F1F","#5B8CA3","#8A6FA8","#A3772E","#444B50"];
let cmet="new_orders",csel=[["S","Technology"],["S","Industrials"],["S","Consumer Discretionary"]];
const CLBL=V2.hdata.All.map(r=>r.l);
function crow(k,n){return k==="S"?(V2.hdata[n]||[]):(V2.ihdata[n]||[])}
function cmchips(){$("v2cmet").innerHTML=SF.map(f=>`<span class="chip ${f[0]===cmet?"on":""}" onclick="cmet='${f[0]}';cmchips();crender()">${f[1]}</span>`).join("");
$("v2csel").innerHTML=csel.map((c,i)=>`<span class="chip" style="border-color:${CMPCOL[i%6]};color:${CMPCOL[i%6]}" onclick="csel.splice(${i},1);cmchips();crender()">${esc(c[1])} ×</span>`).join("");
leg("v2cleg",csel.map((c,i)=>[c[1],CMPCOL[i%6]]))}
(function(){const ss=$("v2csec"),si=$("v2cind");
Object.keys(V2.hdata).filter(k=>k!=="All").sort().forEach(k=>{const o=document.createElement("option");o.value=k;o.textContent=k;ss.appendChild(o)});
const by={};Object.keys(V2.ihdata).forEach(k=>{(by[V2.ihsec[k]||"Other"]=by[V2.ihsec[k]||"Other"]||[]).push(k)});
Object.keys(by).sort().forEach(g=>{const og=document.createElement("optgroup");og.label=g;by[g].sort().forEach(k=>{const o=document.createElement("option");o.value=k;o.textContent=k;og.appendChild(o)});si.appendChild(og)});
const add=k=>e=>{const v=e.target.value;if(!v)return;e.target.value="";if(csel.length>=6||csel.some(c=>c[1]===v))return;csel.push([k,v]);cmchips();crender()};
ss.onchange=add("S");si.onchange=add("I")})();
function crender(){const W=900,H=320,L=46,Bm=40,T=14,R=52;
const sr=csel.map((c,i)=>({n:c[1],col:CMPCOL[i%6],m:Object.fromEntries(crow(c[0],c[1]).map(r=>[r.l,r[cmet]]))}));
const ys=[];sr.forEach(x=>CLBL.forEach(l=>{if(x.m[l]!=null)ys.push(x.m[l])}));
if(!ys.length){$("v2cchart").innerHTML="";return}
const y0=Math.min(...ys)-2,y1=Math.max(...ys)+2,n=CLBL.length;
const X=i=>L+(i/Math.max(n-1,1))*(W-L-R),Y=v=>H-Bm-(v-y0)/(y1-y0)*(H-Bm-T);
let o=`<svg viewBox="0 0 ${W} ${H}" style="width:100%">`;
for(let v=Math.ceil(y0/2)*2;v<=y1;v+=2){o+=`<line x1="${L}" y1="${Y(v)|0}" x2="${W-R}" y2="${Y(v)|0}" stroke="#F0F2F4"/><text x="${L-6}" y="${Y(v)|0}" font-size="10" fill="#666" text-anchor="end" dominant-baseline="middle">${v}</text>`}
CLBL.forEach((l,i)=>{if(i%2===0||i===n-1)o+=`<text x="${X(i)|0}" y="${H-Bm+15}" font-size="10" fill="#666" text-anchor="middle">${l}</text>`});
const labs=[];
sr.forEach(x=>{const pts=CLBL.map((l,i)=>x.m[l]!=null?[X(i),Y(x.m[l]),x.m[l]]:null).filter(Boolean);
if(pts.length<2)return;
o+=`<path d="M${pts.map(p=>(p[0]|0)+" "+(p[1]|0)).join(" L")}" fill="none" stroke="${x.col}" stroke-width="2.3"/>`;
pts.forEach(p=>o+=`<circle cx="${p[0]|0}" cy="${p[1]|0}" r="2.4" fill="${x.col}"/>`);
labs.push({y:pts[pts.length-1][1]+3,x:pts[pts.length-1][0]+8,c:x.col,t:pts[pts.length-1][2].toFixed(1)})});
labs.sort((a,b)=>a.y-b.y);for(let i=1;i<labs.length;i++)if(labs[i].y-labs[i-1].y<13)labs[i].y=labs[i-1].y+13;
labs.forEach(l=>o+=`<text x="${l.x|0}" y="${l.y|0}" font-size="11" font-weight="600" fill="${l.c}">${l.t}</text>`);
$("v2cchart").innerHTML=o+"</svg>"}
cmchips();crender();
// every company
let shown=25;
(function(){const s=$("v2fsec");[...new Set(V2.tbl.map(r=>r.s))].sort().forEach(x=>{const o=document.createElement("option");o.value=x;o.textContent=x;s.appendChild(o)})})();
function view(){const ql=$("v2q").value.trim().toLowerCase(),sv=$("v2fsec").value,so=$("v2fsort").value;
let rows=V2.tbl.filter(r=>(!sv||r.s===sv)&&(!ql||r.t.toLowerCase().includes(ql)||r.s.toLowerCase().includes(ql)||(r.k||"").toLowerCase().includes(ql)));
const key={d_desc:(a,b)=>(b.d??-99)-(a.d??-99),d_asc:(a,b)=>(a.d??99)-(b.d??99),q2_desc:(a,b)=>b.q2-a.q2,q2_asc:(a,b)=>a.q2-b.q2,t:(a,b)=>a.t.localeCompare(b.t)};
rows.sort(key[so]||key.d_desc);
$("v2count").textContent=rows.length+" of "+V2.tbl.length;
$("v2tb").innerHTML=rows.slice(0,shown).map(r=>`<tr><td><b>${esc(r.t)}</b></td><td style="color:#666;font-size:12px">${esc(r.s)}</td><td class="num">${r.q1??"—"}</td><td class="num"><b>${r.q2}</b></td><td class="num ${r.d>0?"pos":(r.d<0?"neg":"")}">${r.d!=null?(r.d>0?"+":"")+r.d:"—"}</td><td style="font-size:12.5px;color:#4A4F54">${esc(r.k)}</td></tr>`).join("");
$("v2more").style.display=rows.length>shown?"":"none"}
["v2q","v2fsec","v2fsort"].forEach(id=>$(id).addEventListener("input",()=>{shown=25;view()}));
$("v2more").onclick=()=>{shown+=100;view()};view();
// sidebar nav + scrollspy
const NAV=[["Earnings PMI","#pmi",[["Overview","#pmi-overview"],["Sectors & industries","#pmi-sectors"],["Movers","#pmi-movers"],["Every company","#pmi-companies"]]],
["Read-Through","#rt",[["Who reports next","#rt-overview"]]],
["Pricing · soon","#rt",[]],["AI adoption · soon","#rt",[]],["AI build-out · soon","#rt",[]],["Tariff refunds · soon","#rt",[]],["Portfolio · soon","#rt",[]]];
$("nav").innerHTML=NAV.map(g=>`<p class="g"><a href="${g[1]}">${g[0]}</a></p>`+g[2].map(l=>`<a class="l" href="${l[1]}">${l[0]}</a>`).join("")).join("");
const anchors=[...document.querySelectorAll("main a[id]")];
addEventListener("scroll",()=>{let cur=anchors[0];anchors.forEach(a=>{if(a.getBoundingClientRect().top<120)cur=a});
document.querySelectorAll("aside .l").forEach(l=>l.classList.toggle("on",l.getAttribute("href")==="#"+cur.id))},{passive:true});
</script>
</body></html>"""

page = (PAGE
  .replace("%SEASON%", esc(V["season"]))
  .replace("%REPORTED%", f"{V['reported']:,}")
  .replace("%UNIV%", f"{V['univ']:,}")
  .replace("%THESIS%", V.get("thesis") or "Live Q3 2026 earnings-season intelligence across the S&P 1500.")
  .replace("%STATS%", statcards())
  .replace("%SUBIDX%", subidx_table())
  .replace("%SECBARS%", secbars())
  .replace("%MEGA%", mega_chips)
  .replace("%MOVUP%", movers_card("up", "Biggest improvers"))
  .replace("%MOVDN%", movers_card("down", "Biggest decliners"))
  .replace("%TIP_THROUGH%", tip("through"))
  .replace("%TIP_SUB%", tip("subidx"))
  .replace("%TIP_SECCHG%", tip("secchg"))
  .replace("%TIP_SECTORS%", tip("sectors"))
  .replace("%TIP_IND%", tip("industries"))
  .replace("%TIP_MEGA%", tip("mega"))
  .replace("%SRC%", SRC)
  .replace("%PAYLOAD%", PAYLOAD))

open(OUT, "w").write(page)
print(f"v2 rendered: {len(page)//1024}KB, {V['reported']} companies")
