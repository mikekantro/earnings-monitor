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


# ── Stock price reaction ──────────────────────────────────────────────────────
def get_price_reaction(ticker: str) -> dict:
    """
    Fetch the stock's true earnings reaction using Yahoo Finance quote endpoint.
    Uses post-market price if available (evening run after earnings),
    otherwise pre-market price (morning run after after-hours earnings).
    Compares against the regular session close to show the real reaction.
    """
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
        params = {"interval": "1d", "range": "2d"}
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        resp.raise_for_status()
        data   = resp.json()
        result = data["chart"]["result"][0]
        meta   = result.get("meta", {})
        closes = result["indicators"]["quote"][0].get("close", [])

        # Get today's actual regular session closing price from chart data
        # (more reliable than meta.regularMarketPrice which can lag)
        valid_closes = [c for c in closes if c is not None]
        todays_close = valid_closes[-1] if valid_closes else None
        prev_close   = valid_closes[-2] if len(valid_closes) >= 2 else None

        post_price   = meta.get("postMarketPrice")
        pre_price    = meta.get("preMarketPrice")
        prev_meta    = meta.get("chartPreviousClose") or meta.get("previousClose")

        # Determine the most relevant reaction price and correct base
        # Post-market (PM reporters): reaction=post_price, base=TODAY's actual close
        # Pre-market (AM reporters):  reaction=pre_price,  base=YESTERDAY's close
        # Regular session fallback:   reaction=today's close, base=yesterday's close
        reaction_price = None
        base           = None
        session_label  = ""

        if post_price and todays_close and post_price != todays_close:
            # Company reported after close — base is today's close
            reaction_price = post_price
            base           = todays_close
            session_label  = "after-hours"
        elif pre_price and (prev_close or prev_meta) and pre_price != (prev_close or prev_meta):
            # Company reported pre-market or prior evening — base is yesterday's close
            reaction_price = pre_price
            base           = prev_close or prev_meta
            session_label  = "pre-market"
        elif todays_close and (prev_close or prev_meta):
            # Regular session — day over day
            reaction_price = todays_close
            base           = prev_close or prev_meta
            session_label  = "regular session"

        if not reaction_price or not base:
            return {}

        pct_change = ((reaction_price - base) / base) * 100
        direction  = "▲" if pct_change >= 0 else "▼"
        color      = "#1a7a3a" if pct_change >= 0 else "#b91c1c"

        label = (
            f"{direction} {abs(pct_change):.1f}% {session_label} "
            f"(close ${base:.2f} → ${reaction_price:.2f})"
        )
        print(f"   📈 {ticker}: reg close=${base:.2f}, {session_label}=${reaction_price:.2f}, change={pct_change:.1f}%")

        return {
            "prev_close":     round(base, 2),
            "latest_close":   round(reaction_price, 2),
            "pct_change":     round(pct_change, 2),
            "direction":      direction,
            "color":          color,
            "label":          label,
            "session":        session_label,
        }
    except Exception as e:
        print(f"   ⚠️  Price data error for {ticker}: {e}")
        return {}



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
                     transcript: str, sec_filing: str,
                     price_reaction: dict) -> str:
    price_str = ""
    if price_reaction:
        price_str = (
            f"STOCK REACTION: {price_reaction['label']} "
            f"(prev close ${price_reaction['prev_close']} → "
            f"${price_reaction['latest_close']})\n\n"
        )

    content = f"""COMPANY: {name} ({ticker})
QUARTER: {quarter}

{price_str}=== FACTSET EARNINGS CALL TRANSCRIPT ===
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
  .company-block h2.ticker {{ margin: 0 0 4px; font-size: 17px; color: #1a1a2e; }}
  .price-badge {{ display: inline-block; font-size: 13px; font-weight: bold; padding: 3px 10px; border-radius: 12px; margin-bottom: 10px; color: white; }}
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

        sec_filing     = get_sec_press_release(ticker)
        price_reaction = get_price_reaction(ticker)

        if price_reaction:
            print(f"   📈 Price reaction: {price_reaction['label']}")
        else:
            print(f"   ⚠️  No price data for {ticker}")

        if not transcript and not sec_filing:
            print(f"   ⚠️  No data for {ticker} — skipping.")
            continue

        analysis = analyze_earnings(ticker, name, quarter, transcript, sec_filing, price_reaction)

        # Inject price badge directly after the <h2> tag
        if price_reaction:
            badge = (
                f'<span class="price-badge" style="background:{price_reaction["color"]}">'
                f'{price_reaction["label"]}</span>'
            )
            analysis = analysis.replace(
                '</h2>', f'</h2>\n  {badge}', 1
            )

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
