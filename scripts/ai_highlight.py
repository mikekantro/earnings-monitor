#!/usr/bin/env python3
"""
ai_highlight.py  (v2)
---------------------
Extracts a GROUNDED "AI use" snippet per earnings transcript — the Lowe's/Mylow,
Walmart/Sparky adopter signal — or nothing if the call doesn't substantively
cover the company USING AI.

v2 changes (fixes the LOW false-negative + cuts cost):
- AI-keyword pre-filter: if the transcript never mentions AI, we skip the API
  call entirely (huge saving across a 1,400-company sweep).
- AI-centered window: instead of blindly sending the first 30k chars, we send the
  intro PLUS windows built around the actual AI mentions, so a Mylow discussion
  buried mid-call still reaches the model.
- Looser quote verification: HTML entities decoded, punctuation-insensitive, and
  a leading-fragment fallback — so a lightly-normalized verbatim quote isn't wrongly
  rejected (that's what dropped LOW).
- Sharper categories: "revenue" = using AI to drive the company's OWN sales
  (Sparky/Rufus/Mylow); "vendor" = selling AI/infra to others (NVDA); etc.
"""
from __future__ import annotations  # 3.9-safe type hints
import os, re, json, sys, html

try:
    import anthropic
except ImportError:
    sys.exit("pip install anthropic")

MODEL = os.environ.get("AI_HIGHLIGHT_MODEL", "claude-sonnet-4-6")
_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

AI_TERMS = re.compile(
    r"(artificial intelligence|\bA\.?I\b|generative|gen ?ai|agentic|machine learning|"
    r"chatbot|co-?pilot|\bllm\b|large language model|ai assistant|ai-powered|ai-driven|"
    r"ai agent|virtual assistant|automation|openai|chatgpt|gpt-|\bgemini\b|copilot)", re.I)

SYSTEM = """You extract, from a single earnings-call transcript, whether and how the \
company is USING artificial intelligence in its own business. You never infer or \
embellish; you only report what the transcript explicitly states.

Return STRICT JSON, no prose, with exactly these keys:
  uses_ai   : boolean  -- true only if the company describes deploying/using AI itself
  category  : one of "revenue" | "efficiency" | "product" | "vendor" | "mention_only" | "none"
      revenue      = the company uses AI to drive ITS OWN sales/conversion/engagement
                     (e.g. an AI shopping assistant like Sparky, Rufus, or Mylow that
                     lifts the company's own revenue). THIS is the primary target.
      efficiency   = the company uses AI to cut its own cost / lift its own productivity
      product      = the company embeds AI in a product/service it SELLS to customers
      vendor       = the company SELLS AI hardware/infrastructure/compute to others and
                     benefits from AI demand, but did not describe using AI internally
                     (e.g. a chipmaker, a cloud provider selling AI capacity)
      mention_only = AI named in passing with no substance
      none         = AI not meaningfully discussed
  headline  : <=140 chars, plain, factual, no adjectives you added yourself. "" if none.
  quote     : a VERBATIM span copied from the transcript supporting the headline,
              <=30 words, appearing in the transcript. "" if none.
  metric    : any quantified AI figure the company stated ("3x conversion", "$60M savings",
              "200 bps"), else null

Rules:
- If you cannot find a verbatim supporting quote in the transcript, return uses_ai=false,
  category="none", empty strings, metric null.
- Copy the quote exactly; do not paraphrase inside it; do not stitch passages together.
- A retailer/bank/consumer company running an AI assistant for its own customers is
  "revenue" (or "efficiency"), NOT "product" and NOT "vendor".
- If the company BOTH sells AI to others AND uses AI in its own operations or customer
  experience, classify by the INTERNAL use (revenue/efficiency/product). Reserve "vendor"
  for companies whose ONLY AI story is selling to others (e.g. a pure-play chipmaker).
  Example: a company with both a cloud-AI business and its own AI shopping assistant is
  "revenue" (the shopping assistant), not "vendor". Prefer the quote about internal use.
- If unsure, return none. A missed highlight is fine; a fabricated one is not."""

USER_TMPL = """Company: {company} ({ticker})

Transcript excerpts (AI-relevant sections):
\"\"\"
{transcript}
\"\"\"

Return the JSON now."""


def _norm(s: str) -> str:
    s = html.unescape(s or "")
    s = re.sub(r"\s+", " ", s).strip().lower()
    return re.sub(r"[^\w\s]", "", s)

def _verify_quote(quote: str, transcript: str) -> bool:
    if not quote:
        return False
    q, t = _norm(quote), _norm(transcript)
    if q and q in t:
        return True
    words = q.split()
    if len(words) >= 6:                      # leading-fragment fallback
        return " ".join(words[:8]) in t
    return False

def _ai_window(transcript: str, budget: int = 32000):
    """Return intro + windows around AI mentions, or None if AI never appears."""
    matches = list(AI_TERMS.finditer(transcript))
    if not matches:
        return None
    spans = [(max(0, m.start() - 1500), m.start() + 6000) for m in matches[:3]]
    merged = []
    for s, e in sorted(spans):
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], e))
        else:
            merged.append((s, e))
    body = " … ".join(transcript[s:e] for s, e in merged)
    combined = transcript[:12000] + " … " + body
    return combined[:budget]


def get_ai_highlight(ticker: str, company: str, transcript: str, debug: bool = False) -> dict | None:
    if not transcript or len(transcript) < 500:
        if debug: print(f"  [debug {ticker}] transcript too short ({len(transcript or '')})")
        return None

    window = _ai_window(transcript)
    if window is None:                        # AI never mentioned -> skip API call
        if debug: print(f"  [debug {ticker}] no AI term in transcript; skipped API")
        return None

    msg = _client.messages.create(
        model=MODEL, max_tokens=400, system=SYSTEM,
        messages=[{"role": "user",
                   "content": USER_TMPL.format(company=company, ticker=ticker, transcript=window)}])
    raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
    raw = raw.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    if debug: print(f"  [debug {ticker}] model -> {raw[:280]}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        if debug: print(f"  [debug {ticker}] JSON parse failed")
        return None

    if not data.get("uses_ai") or data.get("category") not in ("revenue", "efficiency", "product"):
        if debug: print(f"  [debug {ticker}] filtered: uses_ai={data.get('uses_ai')} cat={data.get('category')}")
        return None
    if not _verify_quote(data.get("quote", ""), transcript):
        if debug: print(f"  [debug {ticker}] quote NOT verified: {data.get('quote','')[:80]!r}")
        return None

    return {"ticker": ticker, "company": company, "category": data["category"],
            "headline": data.get("headline", "").strip(),
            "quote": data.get("quote", "").strip(), "metric": data.get("metric")}


_ICON = {"revenue": "📈", "efficiency": "⚙️", "product": "🧩"}

def render_text(h: dict) -> str:
    tag = f" [{h['metric']}]" if h.get("metric") else ""
    return f"{_ICON.get(h['category'],'🤖')} {h['ticker']} — {h['headline']}{tag}"

def render_html(h: dict) -> str:
    tag = f" <b>({h['metric']})</b>" if h.get("metric") else ""
    return (f"<tr><td style='padding:4px 8px;font:13px Helvetica'>"
            f"{_ICON.get(h['category'],'🤖')} <b>{h['ticker']}</b> — {h['headline']}{tag}"
            f"<br><span style='color:#666;font-style:italic'>&ldquo;{h['quote']}&rdquo;</span></td></tr>")


if __name__ == "__main__":
    path, tk, nm = sys.argv[1], sys.argv[2], sys.argv[3]
    h = get_ai_highlight(tk, nm, open(path).read(), debug=True)
    print(json.dumps(h, indent=2) if h else "(no AI-use highlight)")
