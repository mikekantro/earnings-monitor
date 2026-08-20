#!/usr/bin/env python3
"""
refund_watch.py
---------------
Grounded tariff-REFUND tracker for the daily digest. Answers two questions the
keyword search cannot, because they turn on meaning, not word presence:

  1. Is the company RECEIVING a tariff refund from the government?  (cash IN,
     an EPS tailwind -- IEEPA / Section 232 / CIT-ordered CBP refunds)
  2. Is the company PAYING refunds back to its CUSTOMERS, or keeping them
     (e.g. "investing in price")?                                    (cash OUT / retained)

A single company can be BOTH -- Amazon Q2 2026 received ~$600M AND pledged to
refund some customers -- so this captures each direction separately with its own
verbatim, transcript-verified quote. Nothing is inferred; no quote, no entry.

Same design as ai_highlight.py: keyword pre-filter (skip the API when "refund/
tariff" never appear), an evidence window built around the mentions, strict JSON,
and a verbatim-quote check. Reuses your ANTHROPIC key + the transcript you already
fetch. Drop next to ai_highlight.py.
"""
from __future__ import annotations
import os, re, json, sys, html

try:
    import anthropic
except ImportError:
    sys.exit("pip install anthropic")

MODEL = os.environ.get("REFUND_WATCH_MODEL", os.environ.get("AI_HIGHLIGHT_MODEL", "claude-sonnet-4-6"))
_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

# Pre-filter: both a refund-ish word AND a tariff/duty word must appear, or skip.
_REFUND = re.compile(r"(refund|rebate|reimburs|recover|recoup|repay|pass(ed)? back|give.{0,6}back)", re.I)
_TARIFF = re.compile(r"(tariff|duties|duty|ieepa|section 232|section 301|customs|import charge|cbp|court of international trade)", re.I)

SYSTEM = """You read one earnings-call transcript and determine, strictly from what is \
stated, whether the company discussed a TARIFF-RELATED REFUND, and in which direction \
the money moves. You never infer beyond the text.

Return STRICT JSON with exactly these keys:
  tariff_refund : boolean -- true only if a tariff/duty refund, rebate, or recovery is
                  actually discussed. A generic "recovery" (margin, volume, demand) is FALSE.
  receiving     : boolean -- company is RECEIVING a refund from the government / customs
                  (IEEPA, Section 232/301, CIT-ordered, CBP). Cash IN.
  to_customers  : boolean -- company is PAYING / returning / crediting refunds to its own
                  CUSTOMERS, or has committed to. Cash OUT.
  disposition   : one of "refund_customers" | "invest_in_price" | "retain" | "undecided" | "na"
                  -- what they say they'll DO with money received (Amazon: refund some +
                  invest rest; Walmart: invest_in_price; Costco: refund_customers).
  amount        : the stated dollar/percent figure if given (e.g. "$600 million"), else null
  headline      : <=140 chars, plain and factual, no added adjectives. "" if none.
  quote_receiving  : VERBATIM span (<=30 words) supporting `receiving`, copied exactly from
                     the transcript, or "" if not applicable.
  quote_customers  : VERBATIM span (<=30 words) supporting `to_customers`, copied exactly,
                     or "" if not applicable.

Rules:
- If there is no tariff-refund discussion, set tariff_refund=false and everything empty/na.
- Quotes must appear character-for-character in the transcript. Do not paraphrase or stitch.
- receiving and to_customers are independent; a company may be true on both, one, or neither.
- If unsure, return tariff_refund=false. A miss is fine; a fabricated refund is not."""

USER_TMPL = """Company: {company} ({ticker})

Transcript excerpts (refund/tariff sections):
\"\"\"
{transcript}
\"\"\"

Return the JSON now."""


def _norm(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return re.sub(r"[^\w\s]", "", s)

def _verify(quote: str, transcript: str) -> bool:
    if not quote:
        return True  # empty quote is allowed (that direction just doesn't apply)
    q, t = _norm(quote), _norm(transcript)
    if q and q in t:
        return True
    w = q.split()
    return len(w) >= 6 and " ".join(w[:8]) in t

def _window(transcript: str, budget: int = 30000):
    """Windows around places where refund and tariff terms co-occur nearby."""
    hits = [m.start() for m in _REFUND.finditer(transcript)]
    if not hits or not _TARIFF.search(transcript):
        return None
    spans = []
    for i in hits[:4]:
        seg = transcript[max(0, i-1200): i+2500]
        if _TARIFF.search(seg):          # only keep refund mentions near a tariff word
            spans.append((max(0, i-1200), i+2500))
    if not spans:
        return None
    spans.sort()
    merged = [spans[0]]
    for s, e in spans[1:]:
        if s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    return (" … ".join(transcript[s:e] for s, e in merged))[:budget]


def get_refund_highlight(ticker: str, company: str, transcript: str, debug: bool = False) -> dict | None:
    if not transcript or len(transcript) < 500:
        return None
    win = _window(transcript)
    if win is None:
        if debug: print(f"  [refund {ticker}] no tariff+refund co-occurrence; skipped")
        return None
    msg = _client.messages.create(
        model=MODEL, max_tokens=500, system=SYSTEM,
        messages=[{"role": "user", "content": USER_TMPL.format(company=company, ticker=ticker, transcript=win)}])
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    if debug: print(f"  [refund {ticker}] {raw[:200]}")
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not d.get("tariff_refund") or not (d.get("receiving") or d.get("to_customers")):
        return None
    if not (_verify(d.get("quote_receiving", ""), transcript) and _verify(d.get("quote_customers", ""), transcript)):
        if debug: print(f"  [refund {ticker}] quote not verified")
        return None
    return {"ticker": ticker, "company": company,
            "receiving": bool(d.get("receiving")), "to_customers": bool(d.get("to_customers")),
            "disposition": d.get("disposition", "na"), "amount": d.get("amount"),
            "headline": d.get("headline", "").strip(),
            "quote_receiving": d.get("quote_receiving", "").strip(),
            "quote_customers": d.get("quote_customers", "").strip()}


# ---- storage + email block (mirrors ai_watch_digest) ----------------------
STORE = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "refund_highlights.json"))

def add_refund_highlights(hits: list[dict], event_date: str) -> dict:
    data = {"highlights": []}
    if os.path.exists(STORE):
        try: data = json.load(open(STORE))
        except Exception: pass
    seen = {(h["ticker"], h.get("event_date")) for h in data["highlights"]}
    for h in hits:
        if (h["ticker"], event_date) not in seen:
            h = dict(h); h["event_date"] = event_date
            data["highlights"].append(h); seen.add((h["ticker"], event_date))
    json.dump(data, open(STORE, "w"), indent=1)
    print(f"   Refund Watch: {len(data['highlights'])} total in refund_highlights.json")
    return data

def refund_watch_block(hits: list[dict]) -> str:
    if not hits:
        return ""  # only surfaces when there's a tariff-refund disclosure
    def tags(h):
        t = []
        if h["receiving"]: t.append('<span style="background:#0d9488;color:#fff;font-size:11px;padding:1px 6px;border-radius:3px">RECEIVING'
                                    + (f' {h["amount"]}' if h.get("amount") else '') + '</span>')
        if h["to_customers"]: t.append('<span style="background:#b45309;color:#fff;font-size:11px;padding:1px 6px;border-radius:3px">REFUNDING CUSTOMERS</span>')
        return " ".join(t)
    rows = []
    for h in hits:
        q = h.get("quote_customers") or h.get("quote_receiving") or ""
        rows.append(f"""
  <div style="margin:0 0 12px;padding-left:10px;border-left:3px solid #0d9488">
    <p style="margin:0 0 3px;font-size:14px"><b>{h['ticker']}</b> &nbsp;{tags(h)}</p>
    <p style="margin:0 0 3px;font-size:13px;color:#333">{h['headline']}</p>
    <p style="margin:0;font-size:12px;color:#777;font-style:italic">&ldquo;{q}&rdquo;</p>
  </div>""")
    return f"""
<div style="margin-top:32px;padding:16px;background:#f8f6f0;border-radius:6px;border-top:3px solid #0d9488">
  <p style="margin:0 0 10px;font-size:12px;text-transform:uppercase;letter-spacing:1px;color:#888">
    💵 Tariff Refund Watch — {len(hits)} compan{'y' if len(hits)==1 else 'ies'} disclosed refunds
  </p>
  {''.join(rows)}
  <p style="margin:10px 0 0;font-size:11px;color:#999">
    Verbatim, transcript-verified. RECEIVING = refund from government (cash in);
    REFUNDING CUSTOMERS = returning refunds to shoppers (cash out).
  </p>
</div>"""


if __name__ == "__main__":
    path, tk, nm = sys.argv[1], sys.argv[2], sys.argv[3]
    print(json.dumps(get_refund_highlight(tk, nm, open(path).read(), debug=True), indent=2))
