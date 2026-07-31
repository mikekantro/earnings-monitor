#!/usr/bin/env python3
"""
ai_watch_digest.py
------------------
AI Watch section for the daily earnings digest + cumulative storage for the
quarter-over-quarter panel.

Drop this next to earnings_monitor.py (same folder as ai_highlight.py).
See the 4 edits to earnings_monitor.py in the chat / at the bottom of this file.

Styling matches your existing PMI snapshot block (Georgia, #f8f6f0 panel,
3px accent border) so it looks native in the email.
"""
from __future__ import annotations
import os, json, datetime

STORE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ai_highlights.json")
STORE = os.path.normpath(STORE)   # repo root, next to pmi_scores.json

ACCENT = {"revenue": "#0d9488", "efficiency": "#b45309", "product": "#1d4ed8"}
ICON   = {"revenue": "📈", "efficiency": "⚙️", "product": "🧩"}
LABEL  = {"revenue": "revenue", "efficiency": "efficiency", "product": "in-product"}


# ---------------------------------------------------------------- storage
def load_ai_highlights() -> dict:
    if not os.path.exists(STORE):
        return {"highlights": []}
    try:
        with open(STORE) as f:
            return json.load(f)
    except Exception:
        return {"highlights": []}


def add_ai_highlights(new_hits: list[dict]) -> dict:
    """
    Append today's hits to the cumulative store. Deduped on (ticker, event_date)
    so a re-run never double-counts. This file IS the panel: one row per company
    per quarter, which is what makes the same-company Q1->Q2 test possible.
    """
    data = load_ai_highlights()
    seen = {(h.get("ticker"), h.get("event_date")) for h in data["highlights"]}
    added = 0
    for h in new_hits:
        k = (h.get("ticker"), h.get("event_date"))
        if k not in seen:
            data["highlights"].append(h)
            seen.add(k)
            added += 1
    data["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
    with open(STORE, "w") as f:
        json.dump(data, f, indent=1)
    print(f"   🤖 AI Watch: +{added} new highlight(s) → {len(data['highlights'])} total in ai_highlights.json")
    return data


# ---------------------------------------------------------------- email block
def ai_watch_block(hits: list[dict], n_companies: int) -> str:
    """
    Returns the AI Watch HTML for the daily email. Always renders — a day where
    nobody mentioned AI is a real datapoint for the adoption-rate trend, not an
    empty section to hide.
    """
    n = len(hits)
    header = (f"🤖 AI Watch — {n} of {n_companies} companies cited AI use"
              if n else f"🤖 AI Watch — none of {n_companies} companies cited AI use today")
    bar = "#0d9488" if n else "#c9c4b8"

    if not hits:
        inner = ('<p style="margin:0;font-size:14px;color:#777">'
                 'No company described using AI in its own operations on today\'s calls.</p>')
    else:
        order = {"revenue": 0, "efficiency": 1, "product": 2}
        rows = []
        for h in sorted(hits, key=lambda x: order.get(x["category"], 9)):
            c = ACCENT.get(h["category"], "#555")
            metric = (f' <span style="background:{c};color:#fff;font-size:11px;'
                      f'padding:1px 6px;border-radius:3px;white-space:nowrap">{h["metric"]}</span>'
                      if h.get("metric") else "")
            rows.append(f"""
  <div style="margin:0 0 12px;padding-left:10px;border-left:3px solid {c}">
    <p style="margin:0 0 3px;font-size:14px">
      {ICON.get(h['category'],'🤖')} <b>{h['ticker']}</b>
      <span style="color:#888;font-size:12px">· {LABEL.get(h['category'],'')}</span>{metric}
    </p>
    <p style="margin:0 0 3px;font-size:13px;color:#333">{h['headline']}</p>
    <p style="margin:0;font-size:12px;color:#777;font-style:italic">&ldquo;{h['quote']}&rdquo;</p>
  </div>""")
        inner = "".join(rows)

    return f"""
<div style="margin-top:32px;padding:16px;background:#f8f6f0;border-radius:6px;border-top:3px solid {bar}">
  <p style="margin:0 0 10px;font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#888">
    {header}
  </p>
  {inner}
  <p style="margin:10px 0 0;font-size:11px;color:#999">
    Quotes verbatim from the call and verified against the transcript. Companies that only sell AI
    to others are excluded. Measures disclosure, not deployment.
  </p>
</div>"""


# ---------------------------------------------------------------------------
# EDITS TO earnings_monitor.py  (4 small changes)
# ---------------------------------------------------------------------------
#
# 1) near the top, with the other imports:
#
#       from ai_highlight import get_ai_highlight
#       from ai_watch_digest import ai_watch_block, add_ai_highlights
#
# 2) in main(), beside the other accumulators:
#
#       analyses         = []
#       pmi_scores_today = []
#       ai_hits          = []                      # <-- add
#
# 3) in the per-company loop, REPLACE the transcript fetch block with this.
#    Fetches ONCE at full length; the [:30_000] slice keeps analyze_earnings and
#    score_earnings byte-identical to today's behaviour, while AI Watch gets the
#    whole call (its keyword window needs the Q&A -- that's where Mylow lives).
#
#       transcript_full = ""
#       if report_id:
#           transcript_full = get_transcript_text(report_id, max_chars=300_000)
#       if not transcript_full:
#           found_id = get_transcript_report_id(ticker, event_id)
#           if found_id:
#               transcript_full = get_transcript_text(found_id, max_chars=300_000)
#
#       transcript = transcript_full[:30_000]     # unchanged inputs downstream
#
#    ...then right after the `pmi_score = score_earnings(...)` block, add:
#
#       if transcript_full:
#           hit = get_ai_highlight(ticker, name, transcript_full)
#           if hit:
#               hit["event_date"] = date.today().isoformat()
#               ai_hits.append(hit)
#               print(f"   🤖 AI Watch: {hit['category']} — {hit['headline'][:60]}")
#
# 4) where the email is assembled, insert the block between the analyses and the
#    PMI snapshot, and persist the hits:
#
#       ai_html = ai_watch_block(ai_hits, len(analyses))
#       full_html = EMAIL_TEMPLATE.format(
#           date=date.today().strftime("%B %d, %Y"),
#           content="\n".join(analyses) + ai_html + pmi_snapshot
#       )
#       ...
#       add_ai_highlights(ai_hits)        # after send_email(...), always call it
#
# GITHUB ACTIONS: add ai_highlights.json to whatever step commits pmi_scores.json,
# e.g.  git add pmi_scores.json ai_highlights.json
# Without that, the panel resets every run and you lose the quarter-over-quarter data.
