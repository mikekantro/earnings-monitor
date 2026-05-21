"""
S&P 500 Earnings Monitor — FactSet Edition
Uses FactSet Events & Transcripts API (v2) + SEC EDGAR + Claude
"""

import os
import re
import time
import smtplib
import requests
import anthropic
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# ── Config ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
GMAIL_USER        = os.environ["GMAIL_USER"]
GMAIL_APP_PASS    = os.environ["GMAIL_APP_PASS"]
EMAIL_TO          = os.environ.get("EMAIL_TO", GMAIL_USER)
FACTSET_USERNAME  = os.environ["FACTSET_USERNAME"]
FACTSET_API_KEY   = os.environ["FACTSET_API_KEY"]

client  = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
FS_AUTH = (FACTSET_USERNAME, FACTSET_API_KEY)
FS_BASE = "https://api.factset.com/content/events/v2"
HEADERS = {"Content-Type": "application/json", "Accept": "application/json"}

# ── S&P 500 tickers (hardcoded — update quarterly) ───────────────────────────
SP500 = {
    "MMM","AOS","ABT","ABBV","ACN","ADBE","AMD","AES","AFL","A","APD","ABNB",
    "AKAM","ALB","ARE","ALGN","ALLE","LNT","ALL","GOOGL","GOOG","MO","AMZN",
    "AMCR","AEE","AAL","AEP","AXP","AIG","AMT","AWK","AMP","AME","AMGN","APH",
    "ADI","ANSS","AON","APA","AAPL","AMAT","APTV","ACGL","ADM","ANET","AJG",
    "AIZ","T","ATO","ADSK","ADP","AZO","AVB","AVY","AXON","BKR","BALL","BAC",
    "BK","BBWI","BAX","BDX","BRK.B","BBY","BIO","TECH","BIIB","BLK","BX","BA",
    "BSX","BMY","AVGO","BR","BRO","BG","CDNS","CZR","CPT","CPB","COF","CAH",
    "KMX","CCL","CARR","CAT","CBOE","CBRE","CDW","CE","COR","CNC","CNP","CF",
    "CRL","SCHW","CHTR","CVX","CMG","CB","CHD","CI","CINF","CTAS","CSCO","C",
    "CFG","CLX","CME","CMS","KO","CTSH","CL","CMCSA","CMA","CAG","COP","ED",
    "STZ","CEG","COO","CPRT","GLW","CTVA","CSGP","COST","CTRA","CCI","CSX",
    "CMI","CVS","DHI","DHR","DRI","DVA","DAY","DE","DAL","XRAY","DVN","DXCM",
    "FANG","DLR","DFS","DG","DLTR","D","DPZ","DOV","DOW","DTE","DUK","DD",
    "EMN","ETN","EBAY","ECL","EIX","EW","EA","ELV","EMR","ENPH","ETR","EOG",
    "EPAM","EQT","EFX","EQIX","EQR","ESS","EL","ETSY","EG","EVRG","ES","EXC",
    "EXPE","EXPD","EXR","XOM","FFIV","FDS","FICO","FAST","FRT","FDX","FIS",
    "FITB","FSLR","FE","FI","FLT","FMC","F","FTNT","FTV","FOXA","FOX","BEN",
    "FCX","GRMN","IT","GE","GEHC","GEV","GEN","GNRC","GD","GIS","GM","GPC",
    "GILD","GPN","GL","GS","HAL","HIG","HAS","HCA","DOC","HSIC","HSY","HES",
    "HPE","HLT","HOLX","HD","HON","HRL","HST","HWM","HPQ","HUBB","HUM","HBAN",
    "HII","IBM","IEX","IDXX","ITW","INCY","IR","PODD","INTC","ICE","IFF","IP",
    "IPG","INTU","ISRG","IVZ","INVH","IQV","IRM","JBHT","JBL","JKHY","J",
    "JNJ","JCI","JPM","JNPR","K","KVUE","KDP","KEY","KEYS","KMB","KIM","KMI",
    "KLAC","KHC","KR","LHX","LH","LRCX","LW","LVS","LDOS","LEN","LLY","LIN",
    "LYV","LKQ","LMT","L","LOW","LULU","LYB","MTB","MRO","MPC","MKTX","MAR",
    "MMC","MLM","MAS","MA","MTCH","MKC","MCD","MCK","MDT","MRK","META","MET",
    "MTD","MGM","MCHP","MU","MSFT","MAA","MRNA","MHK","MOH","TAP","MDLZ",
    "MPWR","MNST","MCO","MS","MOS","MSI","MSCI","NDAQ","NTAP","NFLX","NEM",
    "NWSA","NWS","NEE","NKE","NI","NDSN","NSC","NTRS","NOC","NCLH","NRG",
    "NUE","NVDA","NVR","NXPI","ORLY","OXY","ODFL","OMC","ON","OKE","ORCL",
    "OTIS","PCAR","PKG","PANW","PH","PAYX","PAYC","PYPL","PNR","PEP","PFE",
    "PCG","PM","PSX","PNW","PNC","POOL","PPG","PPL","PFG","PG","PGR","PLD",
    "PRU","PEG","PTC","PSA","PHM","QRVO","PWR","QCOM","DGX","RL","RJF","RTX",
    "O","REG","REGN","RF","RSG","RMD","RVTY","ROK","ROL","ROP","ROST","RCL",
    "SPGI","CRM","SBAC","SLB","STX","SRE","NOW","SHW","SPG","SWKS","SJM","SNA",
    "SOLV","SO","LUV","SWK","SBUX","STT","STLD","STE","SYK","SYF","SNPS","SYY",
    "TMUS","TROW","TTWO","TPR","TRGP","TGT","TEL","TDY","TFX","TER","TSLA",
    "TXN","TXT","TMO","TJX","TSCO","TT","TDG","TRV","TRMB","TFC","TYL","TSN",
    "USB","UBER","UDR","ULTA","UNP","UAL","UPS","URI","UNH","UHS","VLO","VTR",
    "VRSN","VRSK","VZ","VRTX","VLTO","VFC","VTRS","VICI","V","VST","VMC","WRB",
    "GWW","WAB","WBA","WMT","DIS","WBD","WM","WAT","WEC","WFC","WELL","WST",
    "WDC","WY","WHR","WMB","WTW","WYNN","XEL","XYL","YUM","ZBRA","ZBH","ZTS"
}

# ── FactSet: Earnings calendar ────────────────────────────────────────────────
def get_todays_earnings() -> list[dict]:
    """
    Fetch today's S&P 500 earnings events from FactSet Calendar Events API.
    POST /calendar/events
    """
    today     = date.today()
    start_str = f"{today.isoformat()}T00:00:00Z"
    end_str   = f"{today.isoformat()}T23:59:59Z"

    # Build list of FactSet-formatted tickers (TICKER-US)
    symbols = [f"{t}-US" for t in SP500]

    # FactSet limits symbols per request — batch into chunks of 100
    results = []
    for i in range(0, len(symbols), 100):
        chunk = symbols[i:i+100]
        payload = {
            "data": {
                "dateTime": {"start": start_str, "end": end_str},
                "universe": {"symbols": chunk, "type": "Tickers"},
                "eventTypes": ["Earnings", "ConfirmedEarningsRelease", "SalesRevenueCall"]
            }
        }
        try:
            resp = requests.post(
                f"{FS_BASE}/calendar/events",
                auth=FS_AUTH, headers=HEADERS,
                json=payload, timeout=20
            )
            resp.raise_for_status()
            for item in resp.json().get("data", []):
                ticker = item.get("identifier", "").replace("-US", "")
                if ticker in SP500:
                    results.append({
                        "symbol":   ticker,
                        "name":     item.get("entityName", ticker),
                        "eventId":  item.get("eventId", ""),
                        "reportId": item.get("reportId", ""),
                        "quarter":  f"Q{item.get('fiscalPeriod','')} {item.get('fiscalYear','')}".strip(),
                        "eventType": item.get("eventType", ""),
                    })
        except Exception as e:
            print(f"   ⚠️  Calendar API error (chunk {i//100}): {e}")
        time.sleep(0.3)

    # Deduplicate by symbol
    seen = set()
    unique = []
    for r in results:
        if r["symbol"] not in seen:
            seen.add(r["symbol"])
            unique.append(r)
    return unique


# ── FactSet: Get transcript reportId for a ticker ────────────────────────────
def get_transcript_report_id(ticker: str, event_id: str = "") -> str:
    """
    Find the most recent earnings transcript reportId for this ticker.
    POST /transcripts  (search by IDs + date range)
    """
    today     = date.today()
    start     = (today - timedelta(days=5)).isoformat()
    end       = today.isoformat()

    payload = {
        "data": {
            "ids":       [f"{ticker}-US"],
            "startDate": start,
            "endDate":   end,
            "eventType": "Earnings",
            "dateType":  "uploadDateTime",
        },
        "meta": {"pagination": {"limit": 1, "offset": 0}}
    }
    try:
        resp = requests.post(
            f"{FS_BASE}/transcripts",
            auth=FS_AUTH, headers=HEADERS,
            json=payload, timeout=15
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])
        # Response can be list of documentResult or transcriptById wrappers
        for item in data:
            # Direct document result
            if item.get("transcriptResponseType") == "documentResult":
                return item.get("reportId", "")
            # Wrapped by requestId
            if item.get("transcriptResponseType") == "transcriptById":
                docs = item.get("documents", [])
                if docs:
                    return docs[0].get("reportId", "")
    except Exception as e:
        print(f"   ⚠️  Transcript search error for {ticker}: {e}")
    return ""


# ── FactSet: Download transcript content ─────────────────────────────────────
def get_transcript_text(report_id: str, max_chars: int = 30_000) -> str:
    """
    Download transcript XML content via GET /transcripts/response-type
    and extract plain text from the XML structure.
    """
    if not report_id:
        return ""
    params = {
        "reportIds": report_id,
        "format":    "ContentXML",
    }
    try:
        resp = requests.get(
            f"{FS_BASE}/transcripts/response-type",
            auth=FS_AUTH, params=params, timeout=30
        )
        resp.raise_for_status()

        content_type = resp.headers.get("Content-Type", "")
        raw = resp.text

        # If XML — parse out all <p> tag text regardless of namespace
        if "xml" in content_type or raw.strip().startswith("<"):
            try:
                root = ET.fromstring(raw)
                paragraphs = []
                # Iterate all elements looking for <p> tags (with or without namespace)
                for elem in root.iter():
                    if elem.tag.endswith("}p") or elem.tag == "p":
                        if elem.text and elem.text.strip():
                            paragraphs.append(elem.text.strip())
                if paragraphs:
                    return "\n\n".join(paragraphs)[:max_chars]
            except ET.ParseError:
                pass
            # Fallback: strip all XML tags
            text = re.sub(r"<[^>]+>", " ", raw)
            text = re.sub(r"\s{3,}", "\n\n", text)
            if len(text.strip()) > 50:
                return text[:max_chars]

        # If JSON — fetch the transcriptsUrl
        try:
            json_data = resp.json()
            for item in json_data.get("data", []):
                url = item.get("transcriptsUrl", "")
                if url:
                    txt_resp = requests.get(url, timeout=20)
                    # Returned URL may itself be XML
                    if "xml" in txt_resp.headers.get("Content-Type", "") or txt_resp.text.strip().startswith("<"):
                        try:
                            root2 = ET.fromstring(txt_resp.text)
                            paragraphs = []
                            for elem in root2.iter():
                                if elem.tag.endswith("}p") or elem.tag == "p":
                                    if elem.text and elem.text.strip():
                                        paragraphs.append(elem.text.strip())
                            if paragraphs:
                                return "\n\n".join(paragraphs)[:max_chars]
                        except ET.ParseError:
                            pass
                    text = re.sub(r"<[^>]+>", " ", txt_resp.text)
                    text = re.sub(r"\s{3,}", "\n\n", text)
                    return text[:max_chars]
        except Exception:
            pass

        # Last resort: strip tags from raw response
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s{3,}", "\n\n", text)
        return text[:max_chars]

    except Exception as e:
        print(f"   ⚠️  Transcript download error (reportId={report_id}): {e}")
        return ""


def get_sec_press_release(ticker: str, max_chars: int = 20_000) -> str:
    """Pull the most recent 8-K or 10-Q from SEC EDGAR as a supplement."""
    headers = {"User-Agent": "EarningsMonitor mikekantro@gmail.com"}
    try:
        tickers_data = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=headers, timeout=15
        ).json()
        cik = None
        for entry in tickers_data.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                break
        if not cik:
            return ""

        subs     = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers=headers, timeout=15
        ).json()
        filings  = subs.get("filings", {}).get("recent", {})
        forms    = filings.get("form", [])
        acc_nums = filings.get("accessionNumber", [])
        docs     = filings.get("primaryDocument", [])
        dates    = filings.get("filingDate", [])

        cutoff = (date.today() - timedelta(days=5)).isoformat()
        target = None
        for i, (form, filed) in enumerate(zip(forms, dates)):
            if form == "8-K" and filed >= cutoff:
                target = i
                break
        if target is None:
            for i, form in enumerate(forms):
                if form in ("10-Q", "10-K"):
                    target = i
                    break
        if target is None:
            return ""

        acc_no = acc_nums[target].replace("-", "")
        url    = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}/{docs[target]}"
        text   = requests.get(url, headers=headers, timeout=20).text
        text   = re.sub(r"<[^>]+>", " ", text)
        text   = re.sub(r"\s{3,}", "\n\n", text)
        return text[:max_chars]
    except Exception as e:
        print(f"   ⚠️  SEC EDGAR error for {ticker}: {e}")
        return ""


# ── Claude analysis ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a senior macro research analyst at a top-tier hedge fund.
You have access to a company's earnings call transcript and SEC filings.

Extract the 5 most important takeaways with emphasis on MACRO implications:
signals about the broader economy, consumer behavior, credit conditions, supply chains,
inflation, labor markets, interest rate sensitivity, geopolitical exposure, and sector-wide trends.

Format your response as clean HTML using this exact structure:

<div class="company-block">
  <h2 class="ticker">{TICKER} — {COMPANY_NAME} | {QUARTER}</h2>
  <ol class="takeaways">
    <li><strong>Takeaway title</strong> — Explanation with macro context. Cite specific numbers. (2-3 sentences)</li>
    [5 total]
  </ol>
  <p class="macro-signal"><em>🌐 Macro Signal:</em> One crisp sentence: the single biggest macro implication.</p>
</div>

Rules:
- Cite actual figures (EPS, revenue, margins, guidance)
- Flag consumer trade-downs, pricing power, hiring trends, capex cuts, demand softening
- Flag geographic shifts (China, Europe, EM) and what they signal
- Be specific — no generic observations"""


def analyze_earnings(ticker: str, name: str, quarter: str,
                     transcript: str, sec_filing: str) -> str:
    content = f"""COMPANY: {name} ({ticker})
QUARTER: {quarter}

=== FACTSET EARNINGS CALL TRANSCRIPT ===
{transcript[:22_000] if transcript else "[Transcript not yet available — analyzing SEC filing only]"}

=== SEC FILING (8-K / 10-Q) ===
{sec_filing[:12_000] if sec_filing else "[Not available]"}
"""
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1200,
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
    <p>S&P 500 · {date} · Macro-Focused Digest · FactSet + Claude</p>
  </div>
  <div class="body">{content}</div>
  <div class="footer">
    Sources: FactSet Events &amp; Transcripts API v2, SEC EDGAR. Analyzed by Claude.
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

    todays = get_todays_earnings()
    print(f"   Found {len(todays)} S&P 500 earnings today")

    if not todays:
        print("   No S&P 500 earnings today — skipping email.")
        return

    analyses = []
    for company in todays:
        ticker   = company["symbol"]
        name     = company["name"]
        quarter  = company.get("quarter") or f"Q{((date.today().month-1)//3)+1} {date.today().year}"
        report_id = company.get("reportId", "")

        print(f"\n   Processing {ticker} ({name})...")

        # Get transcript — try reportId from calendar first, then search
        transcript = ""
        if report_id:
            transcript = get_transcript_text(report_id)
        if not transcript:
            found_id = get_transcript_report_id(ticker)
            if found_id:
                transcript = get_transcript_text(found_id)

        if transcript:
            print(f"   ✅ Got transcript ({len(transcript)} chars)")
        else:
            print(f"   ⚠️  No transcript yet — using SEC filing only")

        sec_filing = get_sec_press_release(ticker)

        if not transcript and not sec_filing:
            print(f"   ⚠️  No data for {ticker} — skipping.")
            continue

        analysis = analyze_earnings(ticker, name, quarter, transcript, sec_filing)
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
    print(f"\n✅ Done — {len(analyses)} companies analyzed.")

if __name__ == "__main__":
    main()
