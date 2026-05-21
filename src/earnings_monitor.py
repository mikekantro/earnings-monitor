"""
S&P 500 Earnings Monitor — FactSet Edition
Fetches earnings calendar + transcripts from FactSet,
SEC filings from EDGAR, analyzes via Claude, emails digest.
"""

import os
import re
import time
import smtplib
import requests
import anthropic
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Config (set via GitHub Secrets) ─────────────────────────────────────────
ANTHROPIC_API_KEY   = os.environ["ANTHROPIC_API_KEY"]
GMAIL_USER          = os.environ["GMAIL_USER"]
GMAIL_APP_PASS      = os.environ["GMAIL_APP_PASS"]
EMAIL_TO            = os.environ.get("EMAIL_TO", GMAIL_USER)
FACTSET_USERNAME    = os.environ["FACTSET_USERNAME"]   # e.g. COREMAC-XXXXXX
FACTSET_API_KEY     = os.environ["FACTSET_API_KEY"]

client   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
FS_AUTH  = (FACTSET_USERNAME, FACTSET_API_KEY)
FS_BASE  = "https://api.factset.com"

# ── FactSet: S&P 500 tickers ─────────────────────────────────────────────────
def get_sp500_tickers() -> set[str]:
    """
    Fetch current S&P 500 constituents via FactSet Concordance / Index API.
    Falls back to a hardcoded list of major constituents if the API call fails.
    """
    url = f"{FS_BASE}/content/index-api/v1/constituents"
    params = {"ids": "SP50", "as_of_date": date.today().isoformat()}
    try:
        resp = requests.get(url, auth=FS_AUTH, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        tickers = {item["requestId"].split("-")[0]
                   for item in data.get("data", [])}
        if tickers:
            return tickers
    except Exception as e:
        print(f"   ⚠️  Could not fetch S&P 500 from FactSet: {e}")

    # Fallback: use FactSet's security endpoint with a known index id
    try:
        url2 = f"{FS_BASE}/content/factset-fundamentals/v2/company-reports/index-members"
        resp2 = requests.post(
            url2, auth=FS_AUTH, json={"index": "SP50"}, timeout=15
        )
        resp2.raise_for_status()
        return {item["ticker"] for item in resp2.json().get("data", [])}
    except Exception as e2:
        print(f"   ⚠️  Fallback also failed: {e2}")
        return set()


# ── FactSet: Earnings calendar ───────────────────────────────────────────────
def get_todays_earnings(sp500_tickers: set[str]) -> list[dict]:
    """
    Return S&P 500 companies reporting earnings today via FactSet
    Events & Transcripts API — calendar endpoint.
    """
    today = date.today().isoformat()
    url   = f"{FS_BASE}/content/events-and-transcripts/v1/events/earnings-releases"
    params = {
        "startDate": today,
        "endDate":   today,
        "categories": "EarningsAnnouncement",
        "_paginationLimit": 100,
    }
    try:
        resp = requests.get(url, auth=FS_AUTH, params=params, timeout=15)
        resp.raise_for_status()
        events = resp.json().get("data", [])
    except Exception as e:
        print(f"   ⚠️  Could not fetch earnings calendar: {e}")
        return []

    results = []
    for event in events:
        ticker = event.get("ticker", "")
        # Normalize: FactSet tickers may include exchange suffix (e.g. AAPL-US)
        base_ticker = ticker.split("-")[0]
        if base_ticker in sp500_tickers:
            results.append({
                "symbol":  base_ticker,
                "name":    event.get("companyName", base_ticker),
                "eventId": event.get("eventId", ""),
                "quarter": event.get("fiscalQuarter", ""),
                "year":    event.get("fiscalYear", ""),
            })
    return results


# ── FactSet: Earnings call transcript ────────────────────────────────────────
def get_transcript(ticker: str, event_id: str = "") -> str:
    """
    Fetch the most recent earnings call transcript from FactSet
    Events & Transcripts API. Returns full transcript text.
    """
    # If we have an event_id from the calendar, use it directly
    if event_id:
        url = f"{FS_BASE}/content/events-and-transcripts/v1/transcripts/{event_id}"
        try:
            resp = requests.get(url, auth=FS_AUTH, timeout=20)
            resp.raise_for_status()
            data = resp.json()
            sections = data.get("data", {}).get("transcriptSections", [])
            return "\n\n".join(
                f"[{s.get('speakerName', '')} — {s.get('title', '')}]\n{s.get('transcriptText', '')}"
                for s in sections
            )[:30_000]
        except Exception as e:
            print(f"   ⚠️  Could not fetch transcript by event ID: {e}")

    # Fallback: search by ticker for the most recent transcript
    url = f"{FS_BASE}/content/events-and-transcripts/v1/transcripts"
    params = {
        "ids":         f"{ticker}-US",
        "startDate":   (date.today() - timedelta(days=7)).isoformat(),
        "endDate":     date.today().isoformat(),
        "eventType":   "earnings",
        "_paginationLimit": 1,
    }
    try:
        resp = requests.get(url, auth=FS_AUTH, params=params, timeout=20)
        resp.raise_for_status()
        items = resp.json().get("data", [])
        if not items:
            return ""
        transcript_id = items[0].get("transcriptId", "")
        if not transcript_id:
            return ""
        detail_url = f"{FS_BASE}/content/events-and-transcripts/v1/transcripts/{transcript_id}"
        detail = requests.get(detail_url, auth=FS_AUTH, timeout=20).json()
        sections = detail.get("data", {}).get("transcriptSections", [])
        return "\n\n".join(
            f"[{s.get('speakerName', '')} — {s.get('title', '')}]\n{s.get('transcriptText', '')}"
            for s in sections
        )[:30_000]
    except Exception as e:
        print(f"   ⚠️  Could not fetch transcript for {ticker}: {e}")
        return ""


# ── FactSet: Estimates vs Actuals ────────────────────────────────────────────
def get_estimates(ticker: str) -> str:
    """
    Fetch consensus estimates vs. actuals from FactSet Estimates API.
    Returns a formatted summary string for Claude to interpret.
    """
    url = f"{FS_BASE}/content/factset-estimates/v2/surprise"
    payload = {
        "ids":       [f"{ticker}-US"],
        "metrics":   ["EPS", "SALES"],
        "periodType": "ANN",
        "fiscalPeriodStart": "0",
        "fiscalPeriodEnd":   "0",
        "currency":  "USD",
    }
    try:
        resp = requests.post(url, auth=FS_AUTH, json=payload, timeout=15)
        resp.raise_for_status()
        items = resp.json().get("data", [])
        if not items:
            return ""
        lines = ["=== CONSENSUS ESTIMATES vs ACTUALS ==="]
        for item in items:
            metric   = item.get("metric", "")
            actual   = item.get("actual", "N/A")
            estimate = item.get("mean", "N/A")
            surprise = item.get("surprisePercent", "N/A")
            lines.append(f"{metric}: Actual={actual} | Consensus={estimate} | Surprise={surprise}%")
        return "\n".join(lines)
    except Exception as e:
        print(f"   ⚠️  Could not fetch estimates for {ticker}: {e}")
        return ""


# ── SEC EDGAR: Filing text ────────────────────────────────────────────────────
def get_sec_filing_text(ticker: str, max_chars: int = 25_000) -> str:
    """
    Pull the most recent 10-Q or 10-K text from SEC EDGAR (free, no key needed).
    Used as a supplement to the FactSet transcript for MD&A and guidance language.
    """
    headers = {"User-Agent": "EarningsMonitor mikekantro@gmail.com"}
    try:
        tickers_resp = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=headers, timeout=15
        )
        tickers_data = tickers_resp.json()
        cik = None
        for entry in tickers_data.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                break
        if not cik:
            return f"[Could not resolve CIK for {ticker}]"

        subs = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers=headers, timeout=15
        ).json()
        filings   = subs.get("filings", {}).get("recent", {})
        forms     = filings.get("form", [])
        acc_nums  = filings.get("accessionNumber", [])
        docs      = filings.get("primaryDocument", [])

        target = next((i for i, f in enumerate(forms) if f in ("10-Q", "10-K")), None)
        if target is None:
            return f"[No 10-Q/10-K found for {ticker}]"

        acc_no = acc_nums[target].replace("-", "")
        doc    = docs[target]
        url    = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}/{doc}"
        text   = requests.get(url, headers=headers, timeout=20).text
        text   = re.sub(r"<[^>]+>", " ", text)
        text   = re.sub(r"\s{3,}", "\n\n", text)
        return text[:max_chars]
    except Exception as e:
        return f"[SEC EDGAR error for {ticker}: {e}]"


# ── Claude analysis ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a senior macro research analyst at a top-tier hedge fund.
You have access to a company's earnings call transcript, SEC filing, and consensus estimates vs actuals.

Extract the 5 most important takeaways with emphasis on MACRO implications:
signals about the broader economy, consumer behavior, credit conditions, supply chains,
inflation, labor markets, interest rate sensitivity, geopolitical exposure, and sector-wide trends.

Format your response as clean HTML for an email digest using this exact structure:

<div class="company-block">
  <h2 class="ticker">{TICKER} — {COMPANY_NAME} | {QUARTER}</h2>
  <ol class="takeaways">
    <li><strong>Takeaway title</strong> — Explanation with macro context. What does this tell us about the broader economy? Cite specific numbers. (2-3 sentences)</li>
    [5 total]
  </ol>
  <p class="macro-signal"><em>🌐 Macro Signal:</em> One crisp sentence: the single biggest macro implication from this report.</p>
</div>

Rules:
- Cite actual figures (EPS beats/misses, revenue growth rates, margin changes, guidance ranges)
- Prioritize signals that cut across the whole sector or economy, not just this company
- Note any language about consumer trade-downs, pricing power, hiring freezes, capex cuts, or demand softening
- Flag any geographic exposure shifts (China, Europe, EM) and what they signal
- Be direct and specific — no generic observations"""


def analyze_earnings(ticker: str, name: str, quarter: str,
                     transcript: str, filing: str, estimates: str) -> str:
    content = f"""COMPANY: {name} ({ticker})
QUARTER: {quarter}

{estimates}

=== EARNINGS CALL TRANSCRIPT ===
{transcript[:20_000]}

=== SEC FILING EXCERPT (MD&A / Forward Guidance) ===
{filing[:15_000]}
"""
    msg = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}]
    )
    return msg.content[0].text


# ── Email ─────────────────────────────────────────────────────────────────────
EMAIL_TEMPLATE = """<!DOCTYPE html>
<html>
<head><meta charset="utf-8">
<style>
  body {{ font-family: Georgia, serif; background: #f4f1ec; color: #1a1a1a; margin: 0; padding: 20px; }}
  .wrapper {{ max-width: 680px; margin: 0 auto; background: #fffef9; border: 1px solid #ddd; border-radius: 4px; }}
  .header {{ background: #1a1a2e; color: #e8d5b0; padding: 28px 32px; }}
  .header h1 {{ margin: 0; font-size: 22px; letter-spacing: 2px; text-transform: uppercase; }}
  .header p {{ margin: 6px 0 0; font-size: 13px; color: #a89880; }}
  .body {{ padding: 24px 32px; }}
  .company-block {{ border-left: 3px solid #c0932a; margin: 24px 0; padding: 0 0 0 16px; }}
  .company-block h2.ticker {{ margin: 0 0 12px; font-size: 17px; color: #1a1a2e; }}
  .takeaways {{ margin: 0; padding-left: 20px; }}
  .takeaways li {{ margin-bottom: 10px; font-size: 14px; line-height: 1.6; }}
  .macro-signal {{ background: #f0ede4; border-radius: 4px; padding: 10px 14px; font-size: 13px; margin-top: 12px; }}
  .footer {{ padding: 16px 32px; font-size: 11px; color: #999; border-top: 1px solid #eee; }}
</style>
</head>
<body>
<div class="wrapper">
  <div class="header">
    <h1>📊 Earnings Intelligence</h1>
    <p>S&P 500 · {date} · Macro-Focused Digest · Powered by FactSet + Claude</p>
  </div>
  <div class="body">{content}</div>
  <div class="footer">
    Sources: FactSet Events &amp; Transcripts API, FactSet Estimates API, SEC EDGAR filings. Analyzed by Claude.
  </div>
</div>
</body>
</html>"""


def send_email(subject: str, html_body: str):
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = GMAIL_USER
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(html_body, "html"))
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(GMAIL_USER, GMAIL_APP_PASS)
        server.sendmail(GMAIL_USER, EMAIL_TO, msg.as_string())
    print(f"✅ Email sent to {EMAIL_TO}")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"🔍 Running earnings monitor for {date.today()}")

    sp500   = get_sp500_tickers()
    print(f"   Loaded {len(sp500)} S&P 500 tickers")

    todays  = get_todays_earnings(sp500)
    print(f"   Found {len(todays)} S&P 500 earnings today")

    if not todays:
        print("   No S&P 500 earnings today — skipping email.")
        return

    analyses = []
    for company in todays:
        ticker   = company["symbol"]
        name     = company["name"]
        q        = company.get("quarter", "")
        yr       = company.get("year", "")
        quarter  = f"Q{q} {yr}" if q and yr else f"Q{((date.today().month-1)//3)+1} {date.today().year}"
        event_id = company.get("eventId", "")

        print(f"\n   Processing {ticker} ({name})...")

        transcript = get_transcript(ticker, event_id)
        estimates  = get_estimates(ticker)
        filing     = get_sec_filing_text(ticker)

        if not transcript and filing.startswith("["):
            print(f"   ⚠️  No data for {ticker} — skipping.")
            continue

        analysis = analyze_earnings(ticker, name, quarter, transcript, filing, estimates)
        analyses.append(analysis)
        time.sleep(1)

    if not analyses:
        print("   No analyses produced.")
        return

    full_html = EMAIL_TEMPLATE.format(
        date=date.today().strftime("%B %d, %Y"),
        content="\n".join(analyses)
    )
    subject = f"📊 Earnings Intelligence — {len(analyses)} Reports | {date.today().strftime('%b %d')}"
    send_email(subject, full_html)


if __name__ == "__main__":
    main()
