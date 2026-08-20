#!/usr/bin/env python3
"""
fix_pmi_ordering.py
-------------------
Moves add_pmi_scores() BEFORE send_email() in main(), so an email failure can
never lose PMI data again. This is the exact bug that destroyed the Jul 17 and
Jul 31 scores (83 companies including AAPL/MSFT/META/AMZN): both runs crashed
at SMTP, and the PMI save that lived after it never executed.

The PMI *summary email* still goes out after the main email, unchanged — only
the data save moves.

Run from repo root:
    cd ~/Downloads/earnings-monitor
    python3 fix_pmi_ordering.py
Undo:  cp src/earnings_monitor.py.bak2 src/earnings_monitor.py
"""
import ast, shutil, sys, os

PATH = "src/earnings_monitor.py"
if not os.path.exists(PATH):
    sys.exit("run from ~/Downloads/earnings-monitor")
src = open(PATH).read()

if "pmi_data = add_pmi_scores(pmi_scores_today)\n\n    send_email" in src.replace("  #","#"):
    sys.exit("already patched")

# Step 1: strip the save out of the tail block
old_tail = """    if pmi_scores_today:
        pmi_data = add_pmi_scores(pmi_scores_today)
        maybe_send_pmi_email(pmi_data)"""
new_tail = """    if pmi_data:
        maybe_send_pmi_email(pmi_data)"""

# Step 2: add the save next to the AI Watch save, before send_email
old_head = """    add_ai_highlights(ai_hits)   # save panel FIRST — email failure must not lose data
    send_email(subject, full_html)"""
new_head = """    # Save ALL data FIRST — email failure must never lose data
    add_ai_highlights(ai_hits)
    pmi_data = add_pmi_scores(pmi_scores_today) if pmi_scores_today else None

    send_email(subject, full_html)"""

ok = True
for name, old in [("tail block", old_tail), ("head block", old_head)]:
    n = src.count(old)
    print(f"  {'OK  ' if n==1 else 'MISS'} {name} (found {n}x)")
    if n != 1: ok = False
if not ok:
    sys.exit("anchors didn't match — nothing written; paste this output to me")

src = src.replace(old_tail, new_tail, 1).replace(old_head, new_head, 1)
try:
    ast.parse(src)
except SyntaxError as e:
    sys.exit(f"result invalid ({e}) — nothing written")

shutil.copy(PATH, PATH + ".bak2")
open(PATH, "w").write(src)
print("\npatched: PMI now saves before email. Backup at src/earnings_monitor.py.bak2")
