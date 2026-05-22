"""
PMI Backfill Script — Run locally
Scores all S&P 500 companies that reported this earnings season.
PMI scoring only — no emails, no full analysis bullets.
Saves to pmi_scores.json in the current directory.

Usage:
  cd ~/Downloads/earnings-monitor-factset
  pip install anthropic requests
  export ANTHROPIC_API_KEY="..."
  export FACTSET_USERNAME="..."
  export FACTSET_API_KEY="..."
  python src/backfill_pmi.py
"""

import os, re, json, time, requests, anthropic
import xml.etree.ElementTree as ET
from datetime import date, timedelta

# ── Config ────────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
FACTSET_USERNAME  = os.environ["FACTSET_USERNAME"]
FACTSET_API_KEY   = os.environ["FACTSET_API_KEY"]

client   = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
FS_AUTH  = (FACTSET_USERNAME, FACTSET_API_KEY)
FS_BASE  = "https://api.factset.com/content/events/v2"
HEADERS  = {"Content-Type": "application/json", "Accept": "application/json"}

PMI_FILE     = "pmi_scores.json"
SEASON_START = "2026-04-14"
SEASON_END   = date.today().isoformat()
SEASON_LABEL = "Q1 2026"

# ── S&P 500 tickers ───────────────────────────────────────────────────────────
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

# ── FactSet: Get all earnings events for the season ───────────────────────────
def get_season_earnings() -> list[dict]:
    """Fetch all S&P 500 earnings events for the full season in batches."""
    print(f"\n📅 Fetching earnings calendar: {SEASON_START} → {SEASON_END}")
    symbols  = [f"{t}-US" for t in SP500]
    results  = []
    seen     = set()

    for i in range(0, len(symbols), 100):
        chunk = symbols[i:i+100]
        payload = {
            "data": {
                "dateTime": {
                    "start": f"{SEASON_START}T00:00:00Z",
                    "end":   f"{SEASON_END}T23:59:59Z"
                },
                "universe":   {"symbols": chunk, "type": "Tickers"},
                "eventTypes": ["Earnings", "ConfirmedEarningsRelease"]
            }
        }
        try:
            resp = requests.post(
                f"{FS_BASE}/calendar/events",
                auth=FS_AUTH, headers=HEADERS,
                json=payload, timeout=30
            )
            resp.raise_for_status()
            for item in resp.json().get("data", []):
                ticker = item.get("identifier", "").replace("-US", "")
                if ticker in SP500 and ticker not in seen:
                    seen.add(ticker)
                    results.append({
                        "symbol":   ticker,
                        "name":     item.get("entityName", ticker),
                        "eventId":  item.get("eventId", ""),
                        "reportId": item.get("reportId", ""),
                        "quarter":  f"Q{item.get('fiscalPeriod','')} {item.get('fiscalYear','')}".strip(),
                        "date":     item.get("eventDateTime", "")[:10],
                    })
        except Exception as e:
            print(f"  ⚠️  Calendar batch {i//100+1} error: {e}")
        time.sleep(0.3)

    print(f"   Found {len(results)} S&P 500 reporters this season")
    return sorted(results, key=lambda x: x["date"])


# ── FactSet: Fetch transcript ─────────────────────────────────────────────────
def get_transcript(ticker: str, report_id: str, event_id: str) -> str:
    """Fetch transcript — try reportId first, then search by eventId/ticker."""

    def fetch_by_report_id(rid: str) -> str:
        if not rid:
            return ""
        try:
            resp = requests.get(
                f"{FS_BASE}/transcripts/response-type",
                auth=FS_AUTH,
                params={"reportIds": rid, "format": "ContentXML"},
                timeout=30
            )
            resp.raise_for_status()
            raw = resp.text
            if "<TranscriptsCollection/>" in raw or len(raw) < 50:
                return ""
            # Parse XML
            try:
                root = ET.fromstring(raw)
                parts = []
                for elem in root.iter():
                    tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
                    if tag == "p":
                        txt = "".join(elem.itertext()).strip()
                        if txt:
                            parts.append(txt)
                if parts:
                    return "\n\n".join(parts)[:25_000]
            except ET.ParseError:
                pass
            text = re.sub(r"<[^>]+>", " ", raw)
            return re.sub(r"\s{3,}", "\n\n", text).strip()[:25_000]
        except Exception:
            return ""

    # Try direct reportId
    text = fetch_by_report_id(report_id)
    if text:
        return text

    # Search by eventId
    if event_id:
        try:
            payload = {
                "data": {"eventIds": [event_id], "eventType": "Earnings"},
                "meta": {"pagination": {"limit": 3, "offset": 0}}
            }
            resp = requests.post(
                f"{FS_BASE}/transcripts",
                auth=FS_AUTH, headers=HEADERS,
                json=payload, timeout=15
            )
            resp.raise_for_status()
            for item in resp.json().get("data", []):
                rid = ""
                if item.get("transcriptResponseType") == "documentResult":
                    rid = item.get("reportId", "")
                elif item.get("transcriptResponseType") == "transcriptById":
                    docs = item.get("documents", [])
                    if docs:
                        rid = docs[0].get("reportId", "")
                if rid:
                    text = fetch_by_report_id(rid)
                    if text:
                        return text
        except Exception:
            pass

    # Search by ticker + date range
    try:
        today = date.today().isoformat()
        payload = {
            "data": {
                "ids":       [f"{ticker}-US"],
                "startDate": SEASON_START,
                "endDate":   today,
                "eventType": "Earnings",
                "dateType":  "uploadDateTime",
            },
            "meta": {"pagination": {"limit": 3, "offset": 0},
                     "sort": ["-storyDateTime"]}
        }
        resp = requests.post(
            f"{FS_BASE}/transcripts",
            auth=FS_AUTH, headers=HEADERS,
            json=payload, timeout=15
        )
        resp.raise_for_status()
        for item in resp.json().get("data", []):
            rid = ""
            if item.get("transcriptResponseType") == "documentResult":
                rid = item.get("reportId", "")
            elif item.get("transcriptResponseType") == "transcriptById":
                docs = item.get("documents", [])
                if docs:
                    rid = docs[0].get("reportId", "")
            if rid:
                text = fetch_by_report_id(rid)
                if text:
                    return text
    except Exception:
        pass

    return ""


# ── SEC EDGAR: 8-K fallback ───────────────────────────────────────────────────
def get_sec_filing(ticker: str, report_date: str, max_chars: int = 15_000) -> str:
    """Pull recent 8-K from SEC EDGAR as transcript fallback."""
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

        # Find 8-K near the report date
        cutoff_start = (date.fromisoformat(report_date) - timedelta(days=2)).isoformat() if report_date else SEASON_START
        cutoff_end   = (date.fromisoformat(report_date) + timedelta(days=2)).isoformat() if report_date else date.today().isoformat()

        target = None
        for i, (form, filed) in enumerate(zip(forms, dates)):
            if form == "8-K" and cutoff_start <= filed <= cutoff_end:
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
        primary = docs[target]

        if primary.lower().endswith((".xml", ".xsd")):
            return ""

        url  = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}/{primary}"
        resp = requests.get(url, headers=headers, timeout=20)
        raw  = resp.text

        if "ix:nonNumeric" in raw or raw.strip().startswith("<?xml"):
            return ""

        text = re.sub(r"<[^>]+>", " ", raw)
        text = re.sub(r"&[a-z]+;", " ", text)
        text = re.sub(r"\s{3,}", "\n\n", text).strip()
        return text[:max_chars]
    except Exception:
        return ""


# ── PMI Scoring ───────────────────────────────────────────────────────────────
PMI_PROMPT = """You are a macro economist scoring an earnings report for a PMI-style indicator.

Score this company across 6 macro sub-indices, each from 0 to 100.
50 = neutral, >50 = expansionary, <50 = contractionary.

1. NEW_ORDERS: Forward guidance, bookings, backlog, demand pipeline
2. OUTPUT: Revenue vs expectations, volume growth vs prior year
3. EMPLOYMENT: Hiring trends, headcount, wage/labor cost commentary
4. PRICES: Pricing power, margin direction, input cost pass-through
5. SUPPLY_CHAINS: Inventory, lead times, supplier commentary
6. DEMAND_BREADTH: Geographic signals — US, China, Europe, EM

Respond ONLY with valid JSON, no preamble or markdown:
{
  "new_orders": 0-100,
  "output": 0-100,
  "employment": 0-100,
  "prices": 0-100,
  "supply_chains": 0-100,
  "demand_breadth": 0-100,
  "composite": 0-100,
  "sector": "one of: Technology, Financials, Consumer Discretionary, Consumer Staples, Industrials, Healthcare, Energy, Materials, Utilities, Real Estate, Communication Services",
  "confidence": 1-3,
  "key_signal": "one sentence: the single most important macro signal from this report"
}

COMPOSITE = weighted average: new_orders×0.30 + output×0.25 + employment×0.15 + prices×0.15 + supply_chains×0.10 + demand_breadth×0.05"""


def score_company(ticker: str, name: str, transcript: str, sec_filing: str) -> dict:
    """Score one company's earnings for PMI."""
    content = f"""COMPANY: {name} ({ticker})

TRANSCRIPT:
{transcript[:18_000] if transcript else "[Not available]"}

SEC FILING:
{sec_filing[:6_000] if sec_filing else "[Not available]"}
"""
    try:
        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            system=PMI_PROMPT,
            messages=[{"role": "user", "content": content}]
        )
        raw = re.sub(r"```json|```", "", msg.content[0].text).strip()
        scores = json.loads(raw)
        scores["ticker"] = ticker
        scores["name"]   = name
        scores["date"]   = date.today().isoformat()
        scores["season"] = SEASON_LABEL
        return scores
    except Exception as e:
        print(f"  ⚠️  Scoring error for {ticker}: {e}")
        return {}


# ── PMI Storage ───────────────────────────────────────────────────────────────
def load_scores() -> dict:
    try:
        if os.path.exists(PMI_FILE):
            with open(PMI_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {"season": SEASON_LABEL, "scores": []}


def save_scores(data: dict):
    with open(PMI_FILE, "w") as f:
        json.dump(data, f, indent=2)


def print_summary(data: dict):
    scores = data.get("scores", [])
    if not scores:
        return
    composites = [s["composite"] for s in scores if "composite" in s]
    avg = sum(composites) / len(composites)
    breadth = sum(1 for c in composites if c > 50) / len(composites) * 100
    print(f"\n{'='*60}")
    print(f"EARNINGS PMI — {SEASON_LABEL}")
    print(f"{'='*60}")
    print(f"Composite:  {avg:.1f}")
    print(f"Breadth:    {breadth:.0f}% above 50")
    print(f"Companies:  {len(scores)}")
    print(f"\nTop 5:")
    for s in sorted(scores, key=lambda x: x.get("composite",0), reverse=True)[:5]:
        print(f"  {s['ticker']:6} {s.get('composite',0):.0f}  {s.get('key_signal','')[:70]}")
    print(f"\nBottom 5:")
    for s in sorted(scores, key=lambda x: x.get("composite",0))[:5]:
        print(f"  {s['ticker']:6} {s.get('composite',0):.0f}  {s.get('key_signal','')[:70]}")
    print(f"{'='*60}\n")


# ── Main ──────────────────────────────────────────────────────────────────────
SKIP_FILE = "pmi_skipped.json"

# Companies that never have transcripts — use SEC filing only
SEC_ONLY = {"BRK.B", "BRK.A", "NVR"}


def load_skipped() -> list[dict]:
    """Load previously skipped companies for retry."""
    try:
        if os.path.exists(SKIP_FILE):
            with open(SKIP_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return []


def save_skipped(skipped_list: list[dict]):
    with open(SKIP_FILE, "w") as f:
        json.dump(skipped_list, f, indent=2)


def get_brk_filing(max_chars: int = 20_000) -> str:
    """
    Berkshire Hathaway doesn't do earnings calls.
    Pull their most recent 10-K from SEC EDGAR directly.
    """
    headers = {"User-Agent": "EarningsMonitor mikekantro@gmail.com"}
    try:
        # BRK.B CIK is 0001067983
        cik = "0001067983"
        subs = requests.get(
            f"https://data.sec.gov/submissions/CIK{cik}.json",
            headers=headers, timeout=15
        ).json()
        filings  = subs.get("filings", {}).get("recent", {})
        forms    = filings.get("form", [])
        acc_nums = filings.get("accessionNumber", [])
        docs     = filings.get("primaryDocument", [])

        target = next((i for i, f in enumerate(forms) if f == "10-K"), None)
        if target is None:
            return ""

        acc_no = acc_nums[target].replace("-", "")
        primary = docs[target]

        # Get the filing index to find the readable HTML version
        idx_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no}/{acc_no}-index.htm"
        idx = requests.get(idx_url, headers=headers, timeout=15).text
        doc_links = re.findall(r'href="(/Archives/edgar/data/[^"]+\.htm)"', idx, re.IGNORECASE)

        for path in doc_links:
            if any(x in path.lower() for x in ["viewer", "xbrl", "FilingSummary", "R/"]):
                continue
            url  = f"https://www.sec.gov{path}"
            resp = requests.get(url, headers=headers, timeout=20)
            raw  = resp.text
            if "ix:nonNumeric" in raw or raw.strip().startswith("<?xml"):
                continue
            text = re.sub(r"<[^>]+>", " ", raw)
            text = re.sub(r"&[a-z]+;", " ", text)
            text = re.sub(r"\s{3,}", "\n\n", text).strip()
            if len(text) > 1000:
                return text[:max_chars]
    except Exception as e:
        print(f"  ⚠️  BRK.B filing error: {e}")
    return ""


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--retry", action="store_true",
                        help="Retry previously skipped companies")
    parser.add_argument("--ticker", type=str, default=None,
                        help="Score a single specific ticker")
    args = parser.parse_args()

    print(f"\n🚀 PMI Backfill — {SEASON_LABEL}")
    print(f"   Season: {SEASON_START} → {SEASON_END}")

    data          = load_scores()
    already_scored = {s["ticker"] for s in data.get("scores", [])}
    print(f"   Already scored: {len(already_scored)} companies")

    # Single ticker mode
    if args.ticker:
        ticker = args.ticker.upper()
        print(f"\n   Single ticker mode: {ticker}")
        companies = get_season_earnings()
        match = next((c for c in companies if c["symbol"] == ticker), None)
        if not match:
            match = {"symbol": ticker, "name": ticker, "eventId": "", "reportId": "", "date": ""}
        to_process = [match]

    # Retry skipped companies
    elif args.retry:
        skipped_list = load_skipped()
        already_scored_this_run = already_scored.copy()
        to_process = [s for s in skipped_list
                      if s["symbol"] not in already_scored_this_run]
        print(f"   Retry mode: {len(to_process)} previously skipped companies\n")

    # Normal mode — new companies only
    else:
        companies  = get_season_earnings()
        to_process = [c for c in companies if c["symbol"] not in already_scored]
        print(f"   To process: {len(to_process)} companies\n")

    scored       = 0
    skipped      = 0
    skipped_list = load_skipped() if not args.retry else []
    skipped_tickers = {s["symbol"] for s in skipped_list}

    for i, company in enumerate(to_process, 1):
        ticker    = company["symbol"]
        name      = company["name"]
        event_id  = company.get("eventId", "")
        report_id = company.get("reportId", "")
        rep_date  = company.get("date", "")

        print(f"[{i:3}/{len(to_process)}] {ticker:6} ({name[:30]})", end=" ", flush=True)

        # Special handling for no-transcript companies
        if ticker in SEC_ONLY:
            print(f"[SEC only]", end=" ", flush=True)
            if ticker == "BRK.B":
                sec_filing = get_brk_filing()
            else:
                sec_filing = get_sec_filing(ticker, rep_date)
            transcript = ""
        else:
            transcript = get_transcript(ticker, report_id, event_id)
            if not transcript:
                sec_filing = get_sec_filing(ticker, rep_date)
            else:
                sec_filing = ""

        if not transcript and not sec_filing:
            print("⚠️  no data — skip")
            skipped += 1
            # Track for retry
            if ticker not in skipped_tickers:
                skipped_list.append(company)
                skipped_tickers.add(ticker)
            continue

        source = "transcript" if transcript else "SEC filing"
        print(f"[{source}]", end=" ", flush=True)

        score = score_company(ticker, name, transcript, sec_filing)
        if score:
            # Remove from skipped list if it was there
            skipped_list = [s for s in skipped_list if s["symbol"] != ticker]
            data["scores"].append(score)
            data["season"] = SEASON_LABEL
            scored += 1
            print(f"✅ {score.get('composite', '?'):.0f}")
        else:
            print("⚠️  scoring failed")
            skipped += 1

        if scored % 10 == 0:
            save_scores(data)
            save_skipped(skipped_list)
            print(f"   💾 Progress saved ({scored} scored so far)")

        time.sleep(0.5)

    save_scores(data)
    save_skipped(skipped_list)
    print(f"\n✅ Done — {scored} scored, {skipped} skipped")
    if skipped > 0:
        print(f"   Run with --retry to attempt skipped companies again")
    print_summary(data)
    print_summary(data)


if __name__ == "__main__":
    main()
