#!/usr/bin/env python3
"""
apply_ai_watch.py
-----------------
Applies the 4 AI Watch edits to src/earnings_monitor.py automatically.
Safe: backs up first, refuses to write unless every anchor matched AND the
result still parses as valid Python.

Run from the repo root:
    cd ~/Downloads/earnings-monitor
    python3 apply_ai_watch.py

To undo:
    cp src/earnings_monitor.py.bak src/earnings_monitor.py
"""
import ast, shutil, sys, os

PATH = "src/earnings_monitor.py"
if not os.path.exists(PATH):
    sys.exit(f"Can't find {PATH} — run this from ~/Downloads/earnings-monitor")

src = open(PATH).read()
orig = src

if "ai_watch_block" in src:
    sys.exit("Already patched — nothing to do.")

edits = []

# ---- 1. imports -----------------------------------------------------------
edits.append((
    "imports",
    "from email.mime.text import MIMEText",
    "from email.mime.text import MIMEText\n"
    "from ai_highlight import get_ai_highlight\n"
    "from ai_watch_digest import ai_watch_block, add_ai_highlights",
))

# ---- 2. accumulator -------------------------------------------------------
edits.append((
    "ai_hits accumulator",
    "    analyses         = []\n    pmi_scores_today = []",
    "    analyses         = []\n    pmi_scores_today = []\n    ai_hits          = []",
))

# ---- 3a. fetch full transcript, keep 30k slice for existing calls ---------
edits.append((
    "full-length transcript fetch",
    '        transcript = ""\n'
    "        if report_id:\n"
    "            transcript = get_transcript_text(report_id)\n"
    "        if not transcript:\n"
    "            found_id = get_transcript_report_id(ticker, event_id)\n"
    "            if found_id:\n"
    "                transcript = get_transcript_text(found_id)",

    '        transcript_full = ""\n'
    "        if report_id:\n"
    "            transcript_full = get_transcript_text(report_id, max_chars=300_000)\n"
    "        if not transcript_full:\n"
    "            found_id = get_transcript_report_id(ticker, event_id)\n"
    "            if found_id:\n"
    "                transcript_full = get_transcript_text(found_id, max_chars=300_000)\n"
    "\n"
    "        # AI Watch needs the whole call (the Q&A is where the AI story lives);\n"
    "        # analyze/score keep the original 30k slice so PMI stays comparable.\n"
    "        transcript = transcript_full[:30_000]",
))

# ---- 3b. the AI Watch call ------------------------------------------------
edits.append((
    "get_ai_highlight call",
    "        pmi_score = score_earnings(ticker, name, analysis, transcript, sec_filing)\n"
    "        if pmi_score:\n"
    "            pmi_scores_today.append(pmi_score)",

    "        pmi_score = score_earnings(ticker, name, analysis, transcript, sec_filing)\n"
    "        if pmi_score:\n"
    "            pmi_scores_today.append(pmi_score)\n"
    "\n"
    "        # AI Watch — grounded, verbatim-verified AI-use snippet (or nothing)\n"
    "        if transcript_full:\n"
    "            hit = get_ai_highlight(ticker, name, transcript_full)\n"
    "            if hit:\n"
    '                hit["event_date"] = date.today().isoformat()\n'
    "                ai_hits.append(hit)\n"
    "                print(f\"   AI Watch: {hit['category']} - {hit['headline'][:60]}\")",
))

# ---- 4a. email assembly ---------------------------------------------------
edits.append((
    "email block",
    "    full_html = EMAIL_TEMPLATE.format(\n"
    '        date=date.today().strftime("%B %d, %Y"),\n'
    '        content="\\n".join(analyses) + pmi_snapshot\n'
    "    )",

    "    ai_html = ai_watch_block(ai_hits, len(analyses))\n"
    "\n"
    "    full_html = EMAIL_TEMPLATE.format(\n"
    '        date=date.today().strftime("%B %d, %Y"),\n'
    '        content="\\n".join(analyses) + ai_html + pmi_snapshot\n'
    "    )",
))

# ---- 4b. persist the panel ------------------------------------------------
edits.append((
    "add_ai_highlights call",
    "    send_email(subject, full_html)",
    "    send_email(subject, full_html)\n"
    "    add_ai_highlights(ai_hits)   # cumulative panel -> ai_highlights.json",
))

# ---- apply ----------------------------------------------------------------
failed = []
for name, old, new in edits:
    n = src.count(old)
    if n != 1:
        failed.append((name, n))
        print(f"  MISS  {name}  (found {n}x, need exactly 1)")
        continue
    src = src.replace(old, new, 1)
    print(f"  OK    {name}")

if failed:
    print("\nSome anchors didn't match — your file differs from what I expected.")
    print("Nothing was written. Paste this output to me and I'll adjust:")
    for name, n in failed:
        print(f"   - {name}: matched {n} times")
    sys.exit(1)

try:
    ast.parse(src)
except SyntaxError as e:
    sys.exit(f"\nPatched file would be invalid Python ({e}) — nothing written.")

shutil.copy(PATH, PATH + ".bak")
open(PATH, "w").write(src)
print(f"\nAll 6 edits applied. Backup at {PATH}.bak")
print("Result parses as valid Python.")
print("\nNext:  python3 src/earnings_monitor.py")
