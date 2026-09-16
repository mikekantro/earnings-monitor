"""
buildout_watch.py -- extract AI-infrastructure demand claims from transcripts.

Answers one question per company: does management cite AI-infrastructure
demand (data centers, hyperscaler capex, GPUs/compute, power, grid, cooling,
networking) as a driver of ITS OWN results or outlook?

House rules, same as every extractor in this suite:
- Verbatim quote or no entry. The quote must state the link between AI-driven
  infrastructure demand and the company's own business.
- At most one " ... " join of two fragments, each independently verified.
- "We use AI internally" is AI Watch's domain, NOT a build-out claim. The
  build-out cohort SELLS INTO or IS the infrastructure wave.
"""
import json
import re

CHANNELS = ["data_center_construction", "power_energy", "equipment_components",
            "networking_compute", "cooling_thermal", "materials",
            "hyperscaler_platform", "services_other"]

PROMPT = """You are auditing an earnings-call transcript for one question:
does management cite AI-INFRASTRUCTURE DEMAND as a driver of the company's
own results or outlook?

AI-infrastructure demand means: data-center construction and fit-out,
hyperscaler capital spending, GPU/compute demand, AI-driven power and
electricity demand, grid buildout, cooling/thermal, AI networking, or
materials feeding that chain. The company must be a SELLER INTO or DIRECT
BENEFICIARY of that demand (or a hyperscaler/platform citing AI demand for
its own infrastructure and cloud). A company merely USING AI internally does
NOT qualify.

Respond ONLY with JSON:
{
  "cites_buildout": boolean -- true ONLY if management explicitly links
      AI-infrastructure demand to the company's own revenue, orders, backlog,
      utilization, or outlook,
  "channel": one of %s,
  "quote": VERBATIM text stating that link. Prefer one continuous span
      (<=40 words). If driver and result sit in nearby sentences you may join
      AT MOST TWO verbatim fragments from the same passage with " ... ",
      each fragment copied exactly. "" if cites_buildout is false,
  "metric": the quantified figure management tied to this demand ("$14.1B
      backlog", "backlog up 116%%", "1.2 gigawatts contracted", "40%% of
      revenue from data center customers"), else null,
  "direction": "accelerating" | "steady" | "slowing" per management's
      characterization, else null,
  "headline": one neutral sentence naming company, channel, and claim, "" if false
}

Channel examples:
- A utility or power producer selling electricity/PPAs into data-center load
  (e.g., nuclear deals with hyperscalers) -> "power_energy"
- A chip, server, GPU, or electrical-equipment maker -> "equipment_components"
- The hyperscaler/cloud platform itself citing AI demand for its own
  infrastructure and cloud revenue -> "hyperscaler_platform"
- A builder, contractor, or building-products supplier on data-center
  construction -> "data_center_construction"

Rules:
- ALWAYS return the JSON object, including when cites_buildout is false.
- Copy quotes exactly; do not paraphrase inside them; no stitching beyond the
  single permitted " ... " join.
- Generic AI enthusiasm ("AI is a big opportunity") without a stated link to
  the company's own demand is FALSE.
- Selling AI software/features to end users is NOT infrastructure; that is
  AI Watch's domain. Physical/compute/power/network infrastructure only.
""" % json.dumps(CHANNELS)


def _norm(s: str) -> str:
    s = re.sub(r"&amp;", "&", s)
    s = re.sub(r"&#\d+;|&[a-z]+;", " ", s)
    s = re.sub(r"[\u2018\u2019]", "'", s)
    s = re.sub(r"[\u201c\u201d]", '"', s)
    s = re.sub(r"[\u2013\u2014\-]+", " ", s)   # en/em dashes and hyphens -> space
    s = re.sub(r"\s+", " ", s)
    return s.lower().strip()


def _verify_span(q: str, transcript_norm: str) -> bool:
    qn = _norm(q)
    if not qn:
        return False
    if qn in transcript_norm:
        return True
    words = qn.split()
    if len(words) >= 8:
        idxs = {0, max(0, len(words)//2 - 4), len(words)-8}
        return any(" ".join(words[i:i+8]) in transcript_norm for i in idxs)
    return False


def _verify_quote(q: str, transcript: str) -> bool:
    tn = _norm(transcript)
    frags = [f.strip() for f in re.split(r"\.\.\.|\u2026", q) if f.strip()]
    if not frags or len(frags) > 2:
        return False
    return all(_verify_span(f, tn) for f in frags)


import os
import anthropic
_client = None
def _get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    return _client


def _ask(ticker, company, transcript, model):
    msg = _get_client().messages.create(
        model=model, max_tokens=500,
        system=PROMPT,
        messages=[{"role": "user",
                   "content": f"COMPANY: {company} ({ticker})\n\nTRANSCRIPT:\n{transcript[:28000]}"}])
    raw = msg.content[0].text.strip()
    raw = re.sub(r"```json|```", "", raw).strip()
    try:
        return json.loads(raw), raw
    except Exception:
        return None, raw


def get_buildout_highlight(ticker, company, transcript, debug=False):
    """Returns a dict for build-out claimers, None otherwise.

    Haiku sweeps; a claim whose quote fails the verbatim check gets ONE
    retry on Sonnet, which is far more exact at verbatim extraction. The
    verification rule itself never loosens.
    """
    model = os.environ.get("AI_HIGHLIGHT_MODEL", "claude-haiku-4-5-20251001")
    data, raw = _ask(ticker, company, transcript, model)
    if data is None:
        if re.search(r'cites_buildout"?\s*:\s*false', raw, re.I):
            return None            # clean negative, badly wrapped
        if debug:
            print(f"  [debug {ticker}] unparseable model output")
        return None
    if not data.get("cites_buildout"):
        return None
    q = (data.get("quote") or "").strip()
    if not q or not _verify_quote(q, transcript):
        esc_model = "claude-sonnet-4-6"
        if debug:
            print(f"  [debug {ticker}] verbatim check failed on {model}; retrying on {esc_model}")
        data2, _ = _ask(ticker, company, transcript, esc_model)
        if data2 and data2.get("cites_buildout"):
            q2 = (data2.get("quote") or "").strip()
            if q2 and _verify_quote(q2, transcript):
                data, q = data2, q2
            else:
                if debug:
                    print(f"  [debug {ticker}] dropped: quote failed verbatim on both models: {q2[:60]!r}")
                return None
        else:
            if debug:
                print(f"  [debug {ticker}] dropped: escalation returned no claim")
            return None
    ch = data.get("channel")
    if ch not in CHANNELS:
        ch = "services_other"
    return {"ticker": ticker, "company": company,
            "channel": ch,
            "quote": q,
            "metric": data.get("metric") or None,
            "direction": data.get("direction") if data.get("direction") in
                         ("accelerating", "steady", "slowing") else None,
            "headline": (data.get("headline") or "").strip()}
