"""
Transcript Search Script
Searches full FactSet transcripts for specific keywords across all scored companies.
Usage:
  python3 src/search_transcripts.py --query "tax rebate" "tax refund" "irs refund"
  python3 src/search_transcripts.py --query "tariff refund" "tariff rebate"
"""

import os, re, json, time, requests, argparse
import xml.etree.ElementTree as ET
from datetime import date, timedelta

FACTSET_USERNAME = os.environ["FACTSET_USERNAME"]
FACTSET_API_KEY  = os.environ["FACTSET_API_KEY"]

FS_AUTH  = (FACTSET_USERNAME, FACTSET_API_KEY)
FS_BASE  = "https://api.factset.com/content/events/v2"
HEADERS  = {"Content-Type": "application/json", "Accept": "application/json"}
PMI_FILE = "pmi_scores.json"

SEASON_START = "2026-04-14"
CONTEXT_CHARS = 300  # characters of context around each match


def load_scored_companies() -> list[dict]:
    with open(PMI_FILE) as f:
        data = json.load(f)
    return data.get("scores", [])


def get_transcript_by_ticker(ticker: str) -> str:
    """Search FactSet for most recent earnings transcript for this ticker."""
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
    try:
        resp = requests.post(
            f"{FS_BASE}/transcripts",
            auth=FS_AUTH, headers=HEADERS,
            json=payload, timeout=15
        )
        resp.raise_for_status()
        data = resp.json().get("data", [])

        # Find best reportId (prefer Corrected > Raw)
        priority = {"Corrected": 0, "Raw": 1, "NearRealTime": 2}
        best_id, best_score = "", 99
        for item in data:
            docs = []
            if item.get("transcriptResponseType") == "documentResult":
                docs = [item]
            elif item.get("transcriptResponseType") == "transcriptById":
                docs = item.get("documents", [])
            for doc in docs:
                t_type = doc.get("transcriptType", "")
                score  = priority.get(t_type, 5)
                rid    = doc.get("reportId", "")
                if rid and score < best_score:
                    best_score = score
                    best_id    = rid

        if not best_id:
            return ""

        # Fetch transcript content
        resp2 = requests.get(
            f"{FS_BASE}/transcripts/response-type",
            auth=FS_AUTH,
            params={"reportIds": best_id, "format": "ContentXML"},
            timeout=30
        )
        resp2.raise_for_status()
        raw = resp2.text

        if "<TranscriptsCollection/>" in raw or len(raw) < 100:
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
                return "\n\n".join(parts)
        except ET.ParseError:
            pass

        # Fallback: strip tags
        text = re.sub(r"<[^>]+>", " ", raw)
        return re.sub(r"\s{3,}", "\n\n", text).strip()

    except Exception:
        return ""


def search_transcript(text: str, queries: list[str]) -> list[dict]:
    """Find all occurrences of query terms in transcript, return with context."""
    text_lower = text.lower()
    matches = []
    for query in queries:
        q_lower = query.lower()
        start = 0
        while True:
            idx = text_lower.find(q_lower, start)
            if idx == -1:
                break
            # Get surrounding context
            ctx_start = max(0, idx - CONTEXT_CHARS)
            ctx_end   = min(len(text), idx + len(query) + CONTEXT_CHARS)
            context   = text[ctx_start:ctx_end].strip()
            # Clean up context
            context = re.sub(r"\s{2,}", " ", context)
            matches.append({
                "query":   query,
                "context": context,
                "pos":     idx,
            })
            start = idx + 1
    return matches


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--query", nargs="+", required=True,
                        help="Search terms e.g. 'tax rebate' 'tax refund'")
    parser.add_argument("--limit", type=int, default=None,
                        help="Limit to first N companies (for testing)")
    args = parser.parse_args()

    queries = args.query
    print(f"\n🔍 Searching transcripts for: {queries}")
    print(f"   Loading scored companies from {PMI_FILE}...")

    companies = load_scored_companies()
    if args.limit:
        companies = companies[:args.limit]

    print(f"   Searching {len(companies)} companies...\n")

    results = []
    not_found = []

    for i, company in enumerate(companies, 1):
        ticker = company["ticker"]
        name   = company["name"]
        score  = company.get("composite", 0)

        print(f"[{i:3}/{len(companies)}] {ticker:6}", end=" ", flush=True)

        transcript = get_transcript_by_ticker(ticker)

        if not transcript:
            print("⚠️  no transcript")
            not_found.append(ticker)
            time.sleep(0.3)
            continue

        matches = search_transcript(transcript, queries)

        if matches:
            print(f"✅ {len(matches)} match(es) found!")
            results.append({
                "ticker":  ticker,
                "name":    name,
                "score":   score,
                "sector":  company.get("sector", ""),
                "matches": matches,
            })
        else:
            print("—")

        time.sleep(0.3)

    # Print results
    print(f"\n{'='*70}")
    print(f"SEARCH RESULTS: '{' | '.join(queries)}'")
    print(f"{'='*70}")
    print(f"Companies searched: {len(companies)}")
    print(f"Transcripts found:  {len(companies) - len(not_found)}")
    print(f"Matches found:      {len(results)} companies\n")

    if not results:
        print("No companies mentioned these terms in their earnings transcripts.")
    else:
        for r in sorted(results, key=lambda x: -x["score"]):
            print(f"\n{r['ticker']} — {r['name']} | PMI {r['score']:.0f} | {r['sector']}")
            print("-" * 60)
            for m in r["matches"][:3]:  # Show max 3 matches per company
                print(f'  [{m["query"]}]')
                print(f'  "...{m["context"]}..."')
                print()

    if not_found:
        print(f"\nNo transcript available for: {', '.join(not_found)}")

    print(f"{'='*70}")


if __name__ == "__main__":
    main()
