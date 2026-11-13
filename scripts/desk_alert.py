#!/usr/bin/env python3
"""Desk alert: one email per day with what's NEW since the last alert.

New PMI scores (with biggest movers vs their own Q2), new tariff-refund
disclosures, new build-out claimants, new first-time AI claimants.
Watermark state lives in alerts_state.json (committed by the refresh),
so each item is alerted exactly once. Sends nothing if nothing is new.

Env: GMAIL_USER, GMAIL_APP_PASS, DESK_ALERT_TO (comma list; defaults to
GMAIL_USER), SITE_URL (link target), SKIP_EMAIL=1 to dry-run.
"""
import json, os, smtplib, datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "alerts_state.json")
SEASON_START = "2026-10-01"
SITE = os.environ.get("SITE_URL", "https://whatsnextformarkets.com/research/")

def load(p):
    with open(os.path.join(ROOT, p)) as f:
        return json.load(f)

def main():
    try:
        state = json.load(open(STATE))
    except Exception:
        state = {"pmi": {}, "refund": [], "buildout": [], "ai": []}

    today = datetime.date.today().isoformat()

    # ---- PMI: newly scored companies ----
    cur = {}
    for r in load("pmi_scores.json")["scores"]:
        t = r["ticker"]
        if t not in cur or r.get("date", "") > cur[t].get("date", ""):
            cur[t] = r
    prev = {r["ticker"]: r for r in load("pmi_scores_q2_2026.json")["scores"]}
    new_scores = [r for t, r in cur.items() if t not in state["pmi"]]
    movers = []
    for r in new_scores:
        p = prev.get(r["ticker"])
        if p and p.get("composite") is not None:
            movers.append((r["composite"] - p["composite"], r))
    movers.sort(key=lambda x: x[0])
    dn5, up5 = movers[:4], movers[-4:][::-1]

    def newer(path, seen, datekey="event_date"):
        try:
            rows = load(path)["highlights"]
        except Exception:
            return []
        out = []
        for h in rows:
            d = h.get(datekey) or ""
            if d >= SEASON_START and h["ticker"] not in seen:
                out.append(h)
        # newest first, one per ticker
        out.sort(key=lambda h: h.get(datekey) or "", reverse=True)
        uniq, seen2 = [], set()
        for h in out:
            if h["ticker"] not in seen2:
                uniq.append(h); seen2.add(h["ticker"])
        return uniq

    new_rf = newer("refund_highlights.json", set(state["refund"]))
    new_bo = newer("buildout_highlights.json", set(state["buildout"]))
    new_ai = newer("ai_highlights_q2.json", set(state["ai"]))

    n_items = len(new_scores) + len(new_rf) + len(new_bo) + len(new_ai)
    if n_items == 0:
        print("desk alert: nothing new; no email")
        return

    def esc(x):
        return str(x or "").replace("&", "&amp;").replace("<", "&lt;")

    H = []
    H.append(f'<div style="font-family:Inter,Helvetica,Arial,sans-serif;color:#0A0A0A;max-width:680px">')
    H.append(f'<p style="font-size:11px;letter-spacing:.12em;text-transform:uppercase;color:#666">Piper Sandler &middot; Portfolio Strategy &middot; Earnings Intelligence desk alert</p>')
    H.append(f'<h2 style="font-weight:300;margin:4px 0 14px">{len(new_scores)} newly scored &middot; {len(new_rf)} refund disclosures &middot; {len(new_bo)} build-out claimants &middot; {len(new_ai)} new AI claimants</h2>')

    if movers:
        H.append('<h3 style="font-size:15px;margin:18px 0 6px">Biggest new movers (vs own Q2)</h3>')
        for d, r in up5 + dn5:
            c = "#1E5162" if d > 0 else "#C24F1F"
            H.append(f'<p style="font-size:13px;margin:5px 0"><b>{esc(r["ticker"])}</b> '
                     f'<span style="color:{c};font-weight:600">{d:+.0f}</span> &middot; '
                     f'{esc((r.get("key_signal") or "")[:180])}</p>')

    def section(title, rows, fmt):
        if not rows: return
        H.append(f'<h3 style="font-size:15px;margin:18px 0 6px">{title}</h3>')
        for h in rows[:8]:
            H.append(f'<p style="font-size:13px;margin:5px 0">{fmt(h)}</p>')
        if len(rows) > 8:
            H.append(f'<p style="font-size:12px;color:#666">&hellip;and {len(rows)-8} more on the dashboard.</p>')

    section("New tariff-refund disclosures", new_rf,
            lambda h: f'<b>{esc(h["ticker"])}</b> &middot; {esc(h.get("amount") or "amount n/a")} &middot; {esc(h.get("disposition") or "")} &middot; {esc((h.get("quote_receiving") or h.get("headline") or "")[:150])}')
    section("New build-out claimants", new_bo,
            lambda h: f'<b>{esc(h["ticker"])}</b> &middot; {esc((h.get("channel") or "").replace("_"," "))} &middot; {esc((h.get("metric") if h.get("metric") not in (None,"None") else h.get("headline") or "")[:150])}')
    section("New AI-use claimants", new_ai,
            lambda h: f'<b>{esc(h["ticker"])}</b> &middot; {esc(h.get("category") or "")} &middot; {esc((h.get("quote") or "")[:150])}')

    H.append(f'<p style="font-size:12.5px;color:#666;margin-top:18px">Full detail: <a href="{SITE}" style="color:#1E5162">the live dashboard</a>. Verbatim, transcript-verified quotes throughout. Internal desk color; not investment advice.</p></div>')

    subject = (f"Earnings Intel — {datetime.date.today():%b %d}: "
               f"{len(new_scores)} scored, {len(new_rf)} refunds, {len(new_bo)} build-out, {len(new_ai)} AI")

    if os.environ.get("SKIP_EMAIL"):
        print("SKIP_EMAIL set — dry run:", subject)
    else:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = os.environ["GMAIL_USER"]
        msg["To"] = os.environ.get("DESK_ALERT_TO") or os.environ["GMAIL_USER"]
        msg.attach(MIMEText("".join(H), "html"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
            s.login(os.environ["GMAIL_USER"], os.environ["GMAIL_APP_PASS"])
            s.send_message(msg)
        print("desk alert sent:", subject)

    # ---- watermark AFTER a successful send (or dry run) ----
    for t, r in cur.items():
        state["pmi"].setdefault(t, r.get("date", today))
    state["refund"] = sorted(set(state["refund"]) | {h["ticker"] for h in new_rf})
    state["buildout"] = sorted(set(state["buildout"]) | {h["ticker"] for h in new_bo})
    state["ai"] = sorted(set(state["ai"]) | {h["ticker"] for h in new_ai})
    state["last_run"] = today
    json.dump(state, open(STATE, "w"), indent=1)
    print(f"state: {len(state['pmi'])} pmi / {len(state['refund'])} rf / {len(state['buildout'])} bo / {len(state['ai'])} ai")

if __name__ == "__main__":
    main()
