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

# ── FactSet: Live S&P 500 constituents via Benchmarks API ────────────────────
def get_sp500_tickers_live() -> set[str]:
    """
    Fetch current S&P 500 constituents from FactSet Benchmarks API.
    GET /factset-benchmarks/v1/constituents?ids=SP50
    Returns a set of FactSet fsymIds (e.g. 'F07Q7W-R').
    Falls back to hardcoded SP500 set if API call fails.
    """
    url = "https://api.factset.com/content/factset-benchmarks/v1/constituents"
    params = {"ids": "SP50", "currency": "USD"}
    try:
        resp = requests.get(url, auth=FS_AUTH, params=params, timeout=20)
        resp.raise_for_status()
        data = resp.json().get("data", [])
        if data:
            # fsymId here is the constituent security ID like 'F07Q7W-R'
            ids = {item["fsymId"] for item in data if item.get("fsymId")}
            print(f"   Benchmarks API: {len(ids)} S&P 500 constituents loaded")
            return ids
    except Exception as e:
        print(f"   ⚠️  Benchmarks API error: {e} — using hardcoded list")
    return set()  # Caller falls back to SP500 set


# ── FactSet: Earnings calendar ────────────────────────────────────────────────
def get_todays_earnings() -> list[dict]:
    """
    Fetch today's S&P 500 earnings events from FactSet Calendar Events API.
    POST /calendar/events
    """
    today     = date.today()
    start_str = f"{(today - timedelta(days=1)).isoformat()}T00:00:00Z"
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
    Find the earnings CALL transcript reportId for this ticker.
    Tries two approaches:
    1. Search by eventId (most precise — pins to exact event)
    2. Search by ticker + date range for any Earnings transcript
    Returns the reportId of the best match (preferring CorrectedTranscript > RawTranscript).
    """
    today = date.today()
    start = (today - timedelta(days=2)).isoformat()
    end   = today.isoformat()

    # Approach 1: search by eventId if we have it
    if event_id:
        payload = {
            "data": {"eventIds": [event_id], "eventType": "Earnings"},
            "meta": {"pagination": {"limit": 5, "offset": 0},
                     "sort": ["-storyDateTime"]}
        }
        try:
            resp = requests.post(
                f"{FS_BASE}/transcripts",
                auth=FS_AUTH, headers=HEADERS,
                json=payload, timeout=15
            )
            resp.raise_for_status()
            report_id = _best_report_id(resp.json().get("data", []))
            if report_id:
                print(f"   📋 Found transcript via eventId ({event_id}): reportId={report_id}")
                return report_id
        except Exception as e:
            print(f"   ⚠️  Transcript search by eventId error: {e}")

    # Approach 2: search by ticker + date range
    for event_type in ["Earnings", "Guidance", "SalesRevenue"]:
        payload = {
            "data": {
                "ids":       [f"{ticker}-US"],
                "startDate": start,
                "endDate":   end,
                "eventType": event_type,
                "dateType":  "uploadDateTime",
            },
            "meta": {"pagination": {"limit": 5, "offset": 0},
                     "sort": ["-storyDateTime"]}
        }
        try:
            resp = requests.post(
                f"{FS_BASE}/transcripts",
                auth=FS_AUTH, headers=HEADERS,
                json=payload, timeout=15
            )
            resp.raise_for_status()
            report_id = _best_report_id(resp.json().get("data", []))
            if report_id:
                print(f"   📋 Found transcript via ticker search ({event_type}): reportId={report_id}")
                return report_id
        except Exception as e:
            print(f"   ⚠️  Transcript search error for {ticker} ({event_type}): {e}")

    return ""


def _best_report_id(data: list) -> str:
    """
    From a list of transcript search results, return the reportId of the
    best match — preferring CorrectedTranscript > RawTranscript > NearRealTime.
    """
    priority = {"Corrected": 0, "Raw": 1, "NearRealTime": 2}
    best_id    = ""
    best_score = 99

    for item in data:
        docs = []
        if item.get("transcriptResponseType") == "documentResult":
            docs = [item]
        elif item.get("transcriptResponseType") == "transcriptById":
            docs = item.get("documents", [])

        for doc in docs:
            t_type  = doc.get("transcriptType", "")
            score   = priority.get(t_type, 5)
            r_id    = doc.get("reportId", "")
            if r_id and score < best_score:
                best_score = score
                best_id    = r_id

    return best_id


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
        print(f"   📄 Transcript response: {len(raw)} chars, content-type: {content_type[:50]}, starts: {raw.strip()[:80]!r}")

        def extract_text_from_xml(xml_str: str) -> str:
            """Extract all paragraph text from FactSet transcript XML."""
            try:
                root = ET.fromstring(xml_str)
                parts = []
                for elem in root.iter():
                    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                    if tag == "p":
                        # Collect all text including mixed content
                        full_text = "".join(elem.itertext()).strip()
                        if full_text:
                            parts.append(full_text)
                if parts:
                    return "\n\n".join(parts)
            except ET.ParseError as e:
                print(f"   ⚠️  XML parse error: {e}")
            return ""

        # If XML response — parse directly
        if "xml" in content_type or raw.strip().startswith("<"):
            # Empty collection = transcript not posted yet
            if raw.strip() in ("<TranscriptsCollection/>", "<TranscriptsCollection />"):
                print(f"   ⏳ Transcript not yet available for reportId={report_id}")
                return ""
            text = extract_text_from_xml(raw)
            if text and len(text) > 50:
                return text[:max_chars]
            # Fallback: brute-force strip tags
            text = re.sub(r"<[^>]+>", " ", raw)
            text = re.sub(r"\s{3,}", "\n\n", text).strip()
            if len(text) > 50:
                return text[:max_chars]
            return ""

        # If JSON — response contains a URL to the actual transcript
        try:
            json_data = resp.json()
            items = json_data.get("data", [])
            print(f"   📄 JSON response with {len(items)} items")
            for item in items:
                url = item.get("transcriptsUrl", "")
                if url:
                    print(f"   📄 Fetching transcript URL...")
                    txt_resp = requests.get(url, timeout=30)
                    inner_ct = txt_resp.headers.get("Content-Type", "")
                    inner_raw = txt_resp.text
                    print(f"   📄 Inner response: {len(inner_raw)} chars, ct: {inner_ct[:50]}")
                    if "xml" in inner_ct or inner_raw.strip().startswith("<"):
                        text = extract_text_from_xml(inner_raw)
                        if text and len(text) > 50:
                            return text[:max_chars]
                        # Brute force
                        text = re.sub(r"<[^>]+>", " ", inner_raw)
                        text = re.sub(r"\s{3,}", "\n\n", text).strip()
                        if len(text) > 50:
                            return text[:max_chars]
                    elif len(inner_raw.strip()) > 50:
                        return inner_raw[:max_chars]
        except Exception as e:
            print(f"   ⚠️  JSON transcript fetch error: {e}")

        # Last resort: strip tags from raw response
        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"\s{3,}", "\n\n", text)
        return text[:max_chars]

    except Exception as e:
        print(f"   ⚠️  Transcript download error (reportId={report_id}): {e}")
        return ""


def _get_readable_filing_doc(cik: str, acc_no: str, headers: dict) -> str:
    """
    Given an accession number, find the best human-readable document
    (HTML/HTM) from the filing index, skipping XBRL files.
    Returns extracted plain text or empty string.
    """
    index_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}/{acc_no}-index.htm"
    try:
        idx = requests.get(index_url, headers=headers, timeout=15).text
    except Exception:
        return ""

    # Find all document links in the index
    doc_links = re.findall(r'href="(/Archives/edgar/data/[^"]+\.(htm|html))"', idx, re.IGNORECASE)

    for path, _ in doc_links:
        # Skip XBRL viewer, R files, and inline XBRL
        if any(x in path.lower() for x in ["viewer", "/r/", "xbrl", "ix?doc", "FilingSummary"]):
            continue
        url = f"https://www.sec.gov{path}"
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            text = resp.text
            # Skip if it looks like XBRL (contains ix: namespace tags)
            if "ix:nonNumeric" in text or "ix:nonFraction" in text or "<xbrl" in text.lower():
                continue
            # Strip HTML and clean up
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"&[a-z]+;", " ", text)
            text = re.sub(r"\s{3,}", "\n\n", text)
            text = text.strip()
            if len(text) > 500:
                return text
        except Exception:
            continue
    return ""


def get_sec_press_release(ticker: str, max_chars: int = 20_000) -> str:
    """
    Pull the most recent 8-K earnings press release from SEC EDGAR.
    Falls back to 10-Q/10-K if no fresh 8-K found.
    Skips XBRL files and finds the human-readable HTML version.
    """
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

        subs    = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers=headers, timeout=15
        ).json()
        filings = subs.get("filings", {}).get("recent", {})
        forms   = filings.get("form", [])
        acc_nums = filings.get("accessionNumber", [])
        docs    = filings.get("primaryDocument", [])
        dates   = filings.get("filingDate", [])

        # Try fresh 8-K first (last 5 days)
        cutoff = (date.today() - timedelta(days=5)).isoformat()
        targets = []
        for i, (form, filed) in enumerate(zip(forms, dates)):
            if form == "8-K" and filed >= cutoff:
                targets.append(i)
                break

        # Fall back to most recent 10-Q or 10-K
        if not targets:
            for i, form in enumerate(forms):
                if form in ("10-Q", "10-K"):
                    targets.append(i)
                    break

        for target in targets:
            acc_no = acc_nums[target].replace("-", "")
            primary_doc = docs[target]

            # Skip if primary doc is XBRL
            if primary_doc.lower().endswith((".xml", ".xsd")):
                text = _get_readable_filing_doc(cik, acc_no, headers)
                if text:
                    return text[:max_chars]
                continue

            url  = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}/{primary_doc}"
            resp = requests.get(url, headers=headers, timeout=20)
            raw  = resp.text

            # If it looks like XBRL, find the readable version instead
            if ("ix:nonNumeric" in raw or "ix:nonFraction" in raw or
                    raw.strip().startswith("<?xml") or "<xbrl" in raw.lower()):
                text = _get_readable_filing_doc(cik, acc_no, headers)
                if text:
                    return text[:max_chars]
                continue

            text = re.sub(r"<[^>]+>", " ", raw)
            text = re.sub(r"&[a-z]+;", " ", text)
            text = re.sub(r"\s{3,}", "\n\n", text)
            text = text.strip()
            if len(text) > 500:
                return text[:max_chars]

        return ""
    except Exception as e:
        print(f"   ⚠️  SEC EDGAR error for {ticker}: {e}")
        return ""


# ── Claude analysis ───────────────────────────────────────────────────────────
SYSTEM_PROMPT = """You are a senior macro research analyst at a top-tier hedge fund.
You have access to a company's earnings call transcript and SEC filings.

Format your response as clean HTML using this exact structure:

<div class="company-block">
  <h2 class="ticker">{TICKER} — {COMPANY_NAME} | {QUARTER} | {MARKET CAP if provided}</h2>
  <p class="company-desc"><em>{One sentence: what the company does, its primary business, and rough revenue scale. E.g. "Deere & Co. manufactures agricultural and construction equipment, generating ~$55B in annual revenue primarily from equipment sales and financing."}</em></p>
  <ol class="takeaways">
    <li><strong>Takeaway title</strong> — Macro-focused explanation. Cite specific numbers. (2-3 sentences)</li>
    <li><strong>Takeaway title</strong> — Macro-focused explanation. Cite specific numbers. (2-3 sentences)</li>
    <li><strong>Takeaway title</strong> — Macro-focused explanation. Cite specific numbers. (2-3 sentences)</li>
    <li><strong>Takeaway title</strong> — Macro-focused explanation. Cite specific numbers. (2-3 sentences)</li>
    <li class="ai-bullet"><strong>🤖 AI Impact</strong> — Did the company mention AI driving revenue, margin improvement, cost savings, or productivity gains? Quote specific claims and figures if mentioned. If AI was not meaningfully discussed, say so explicitly: "AI not a material topic this quarter."</li>
  </ol>
  <p class="macro-signal"><em>🌐 Macro Signal:</em> One crisp sentence: the single biggest macro implication from this report.</p>
</div>

Rules for the first 4 bullets:
- Focus on macro implications: consumer behavior, credit conditions, supply chains, inflation, labor markets, interest rate sensitivity, geopolitical exposure, sector-wide trends
- Cite actual figures (EPS, revenue, margins, guidance ranges)
- Flag consumer trade-downs, pricing power, hiring trends, capex cuts, demand softening
- Flag geographic shifts (China, Europe, EM) and what they signal
- Be specific — no generic observations

Rules for bullet 5 (AI Impact):
- Look for: AI-driven revenue growth, AI cost savings, margin improvement from AI, headcount reduction via AI, AI product launches, AI capex spend, competitive AI positioning
- Quote specific numbers if given (e.g. "AI features drove $X in incremental revenue", "reduced costs by X% using AI")
- Note whether AI discussion was substantive or just buzzword-level
- Always include this bullet even if AI was not mentioned"""


def get_market_cap(ticker: str) -> str:
    """
    Fetch market cap from FactSet Global Prices market-value endpoint.
    Falls back to SEC EDGAR company facts if FactSet not available.
    Returns a formatted string like '$3.2T' or '$45B'.
    """
    # Try FactSet market-value endpoint
    try:
        url = "https://api.factset.com/content/factset-global-prices/v1/market-value"
        params = {"ids": f"{ticker}-US", "currency": "USD"}
        resp = requests.get(url, auth=FS_AUTH, params=params, timeout=10)
        if resp.status_code == 200:
            data = resp.json().get("data", [])
            if data and data[0].get("marketValue"):
                mv_millions = data[0]["marketValue"]
                return _format_market_cap(mv_millions * 1_000_000)
    except Exception:
        pass

    # Fall back to SEC EDGAR company facts (shares * price approximation)
    try:
        headers = {"User-Agent": "EarningsMonitor mikekantro@gmail.com"}
        tickers_data = requests.get(
            "https://www.sec.gov/files/company_tickers.json",
            headers=headers, timeout=10
        ).json()
        cik = None
        for entry in tickers_data.values():
            if entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry["cik_str"]).zfill(10)
                break
        if cik:
            facts = requests.get(
                f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
                headers=headers, timeout=15
            ).json()
            # Try to get shares outstanding
            shares_facts = (facts.get("facts", {})
                           .get("us-gaap", {})
                           .get("CommonStockSharesOutstanding", {})
                           .get("units", {})
                           .get("shares", []))
            if shares_facts:
                latest = sorted(shares_facts, key=lambda x: x.get("end", ""))[-1]
                shares = latest.get("val", 0)
                if shares > 0:
                    return f"~{_format_market_cap(shares)}  shares outstanding"
    except Exception:
        pass

    return ""


def _format_market_cap(value: float) -> str:
    """Format a number into T/B/M string."""
    if value >= 1_000_000_000_000:
        return f"${value/1_000_000_000_000:.1f}T"
    elif value >= 1_000_000_000:
        return f"${value/1_000_000_000:.1f}B"
    elif value >= 1_000_000:
        return f"${value/1_000_000:.1f}M"
    return f"${value:,.0f}"


def analyze_earnings(ticker: str, name: str, quarter: str,
                     transcript: str, sec_filing: str,
                     market_cap: str = "") -> str:
    mktcap_str = f"MARKET CAP: {market_cap}\n" if market_cap else ""
    content = f"""COMPANY: {name} ({ticker})
QUARTER: {quarter}
{mktcap_str}
=== FACTSET EARNINGS CALL TRANSCRIPT ===
{transcript[:22_000] if transcript else "[Transcript not yet available — analyzing SEC filing only]"}

=== SEC FILING (8-K / 10-Q) ===
{sec_filing[:12_000] if sec_filing else "[Not available]"}
"""
    msg = client.messages.create(
        model="claude-sonnet-4-6",
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
  .company-block h2.ticker {{ margin: 0 0 4px; font-size: 17px; color: #1a1a2e; }}
  .company-desc {{ margin: 0 0 12px; font-size: 13px; color: #666; font-style: italic; }}
  .takeaways {{ margin: 0; padding-left: 20px; }}
  .takeaways li {{ margin-bottom: 10px; font-size: 14px; line-height: 1.6; }}
  .takeaways li.ai-bullet {{ background: #f0f4ff; border-left: 3px solid #4a6fa5; padding: 8px 12px; margin-left: -12px; border-radius: 0 4px 4px 0; list-style: none; }}
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

    # Try to get live S&P 500 list from Benchmarks API (logged but not blocking)
    get_sp500_tickers_live()

    todays = get_todays_earnings()
    print(f"   Found {len(todays)} S&P 500 earnings today")

    if not todays:
        print("   No S&P 500 earnings today — skipping email.")
        return

    analyses = []
    for company in todays:
        ticker    = company["symbol"]
        name      = company["name"]
        quarter   = company.get("quarter") or f"Q{((date.today().month-1)//3)+1} {date.today().year}"
        report_id = company.get("reportId", "")
        event_id  = company.get("eventId", "")

        print(f"\n   Processing {ticker} ({name})...")

        # Get transcript — try reportId from calendar first, then search by eventId/ticker
        transcript = ""
        if report_id:
            transcript = get_transcript_text(report_id)
        if not transcript:
            found_id = get_transcript_report_id(ticker, event_id)
            if found_id:
                transcript = get_transcript_text(found_id)

        if transcript:
            print(f"   ✅ Got transcript ({len(transcript)} chars)")
        else:
            print(f"   ⚠️  No transcript yet — using SEC filing only")

        sec_filing  = get_sec_press_release(ticker)
        market_cap  = get_market_cap(ticker)
        if market_cap:
            print(f"   💰 Market cap: {market_cap}")

        if not transcript and not sec_filing:
            print(f"   ⚠️  No data for {ticker} — skipping.")
            continue

        analysis = analyze_earnings(ticker, name, quarter, transcript, sec_filing, market_cap)

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
