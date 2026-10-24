#!/usr/bin/env python3
"""
Deal Flow Intro Agent — Bring Your Own Agent (BYOA)

Problem (from VCs themselves):
  VCs sit on thousands of contacts and get asked every week to make
  customer / partner / hire intros for portfolio companies. They do not
  have time to build the list, pick the right people, chase replies, or
  track what worked. Intros get lost in the shuffle.

Positioning — portfolio intelligence that leads to action:
  "Our agent follows every portfolio company, detects emerging needs,
  and activates the fund's network to help, before the founder has to ask."
  (Track 3: turn scattered portfolio data into patterns a fund can act on.)

What this agent does:
  0. DETECT   Reads scattered portfolio updates (founder emails, company
              announcements, call notes) and detects emerging needs, each
              backed by quoted evidence. An explicit challenge becomes a
              need; a possible need is flagged to confirm with the founder.
              The demo LEADS with the portfolio development that needs
              attention; the introduction is the action it recommends.
  1. INGEST   Connects email / LinkedIn exports, pulls every contact,
              enriches and organises them (company, role, topics,
              relationship strength, last touch).
  2. MATCH    Given a portfolio company's ask, ranks the best intro
              targets. It learns: a contact whose intro led to a meeting
              or a deal gets boosted for similar asks; a contact who
              ignored / failed 2-3 intros gets scratched from future lists.
  3. DRAFT    Writes a double-opt-in intro draft for the partner to approve.
              Nothing is ever sent without a human approval.
  4. FOLLOW UP  Manages the correspondence. Every 2-3 days it nudges BOTH
              sides (the intro target and the portfolio company), and once
              a week it rolls up open intros. This solves the core tracking
              problem: the agent finds out whether an intro worked even
              when the portfolio company forgets to report back.
  5. REPORT   Firm-wide feed + analytics. Every partner sees "X made an
              intro for Y", per-partner activity, reply / meeting rates,
              and which connectors actually produce outcomes. The same
              feed can be dropped into Slack.

BYOA design:
  This is a plain script, not a platform. Any AI agent a VC already has
  (Muse, or any other assistant) can run it — see SKILL.md. State lives
  in one local JSON file. No contacts ever leave the VC's own machine
  unless the VC's own agent sends the approved emails.

Usage:
  python3 agent.py demo                      # seed demo data + full run
  python3 agent.py signals signals.csv       # import portfolio updates
  python3 agent.py detect                      # detect needs from signals
  python3 agent.py action --need need_001     # partner action card: reason,
                                               # evidence, matched help, draft
  python3 agent.py confirm --need need_001    # draft to confirm a possible
                                               # need with the founder
  python3 agent.py resolve --need need_001 --connected yes --useful yes
  python3 agent.py ingest contacts.csv       # import a CSV / LinkedIn export
  python3 agent.py match --need "VP Operations at a data center operator"
  python3 agent.py draft  --intro intro_001   # print a double-opt-in draft
  python3 agent.py followups                   # who needs a nudge today
  python3 agent.py record --intro intro_001 --outcome meeting
  python3 agent.py analytics                   # print stats + write analytics.html
  python3 agent.py feed                        # firm activity feed (Slack-ready)

Outcomes: replied | meeting | customer | passed | no_response
Scratch rule: 3 x (passed | no_response) on a contact -> scratched.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import date, timedelta
from pathlib import Path

STORE = Path(__file__).with_name("state.json")
SCRATCH_THRESHOLD = 3          # failed intros before a contact is scratched
FOLLOWUP_EVERY_DAYS = 3        # nudge cadence while an intro is open
WEEKLY_ROLLUP_DAYS = 7

# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

@dataclass
class Contact:
    id: str
    name: str
    email: str = ""
    company: str = ""
    role: str = ""
    topics: list = field(default_factory=list)   # e.g. ["data centers", "ops"]
    strength: int = 3                            # 1 weak .. 5 close
    source: str = ""                             # email | linkedin | manual
    owner_partner: str = ""                      # which partner knows them
    wins: int = 0                                # intros that produced an outcome
    fails: int = 0                               # intros passed / no response
    scratched: bool = False

@dataclass
class Signal:
    id: str
    company: str                     # portfolio company
    source: str                      # founder_email | announcement | call_note | news
    date: str = ""
    text: str = ""

@dataclass
class Need:
    id: str
    company: str                     # portfolio company
    need: str                        # detected need, in plain words
    certainty: str = "possible"      # explicit | possible (confirm with founder)
    evidence: list = field(default_factory=list)  # [{source, date, quote}]
    sources_count: int = 1           # corroborating sources raise confidence
    status: str = "detected"         # detected|confirmed|actioned|resolved
    connected: str = ""              # did the founder connect? yes | no
    useful: str = ""                 # was the help useful? yes | no

@dataclass
class Intro:
    id: str
    need: str                    # the portfolio company's ask, in plain words
    portfolio_company: str
    contact_id: str
    partner: str                 # partner who owns / approved the intro
    status: str = "proposed"     # proposed|approved|sent|replied|meeting|customer|passed|no_response
    created: str = ""
    last_touch: str = ""
    followups_sent: int = 0

# --------------------------------------------------------------------------
# Store
# --------------------------------------------------------------------------

def load() -> dict:
    if STORE.exists():
        state = json.loads(STORE.read_text())
        for key in ("contacts", "intros", "feed", "signals", "needs"):
            state.setdefault(key, [])
        return state
    return {"contacts": [], "intros": [], "feed": [], "signals": [], "needs": []}

def save(state: dict) -> None:
    STORE.write_text(json.dumps(state, indent=2))

def post_feed(state: dict, text: str) -> None:
    """Firm-wide visibility: every intro action lands in one feed.
    Point `post_feed` at a Slack webhook to drop this straight into Slack."""
    state["feed"].append({"date": date.today().isoformat(), "text": text})
    print(f"  [feed] {text}")

# --------------------------------------------------------------------------
# 0. Portfolio intelligence — scattered updates in, evidenced needs out
# --------------------------------------------------------------------------

# keyword signal -> the need it points to. Extend freely; the agent's job is
# pattern -> need -> action, not keyword bingo: every need carries its quotes.
NEED_PATTERNS = [
    (("distributor", "distribution"), "Select a distributor for the new regional launch"),
    (("expanding into", "expansion", "new market", "launch"), "Support the regional expansion (customers, partners, distribution)"),
    (("churn",), "Customer success help for churn"),
    (("raising", "bridge round", "fundrais"), "Introductions to investors for the current raise"),
    (("hiring", "head of", "recruiting"), "Hiring help: candidates and backchannel references"),
    (("enterprise customer", "first enterprise", "big logo"), "Enterprise customer introductions"),
]

EXPLICIT_MARKERS = ("challenge", "struggling", "looking for", "need help",
                    "biggest problem", "hard part", "stuck on")

def ingest_signals(path: str) -> None:
    """Import scattered portfolio updates from a CSV export.
    Columns: company,source,date,text
    Live version: the VC's own agent reads founder emails, portfolio
    announcements and call notes from the connected mailbox and writes
    the same rows. The agent never invents a signal: no source, no need."""
    state = load()
    added = 0
    with open(path, newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            state["signals"].append(asdict(Signal(
                id=f"sig_{len(state['signals']) + 1:03d}",
                company=row.get("company", "").strip(),
                source=row.get("source", "note").strip(),
                date=row.get("date", "").strip(),
                text=row.get("text", "").strip(),
            )))
            added += 1
    save(state)
    print(f"Ingested {added} portfolio signals. Total: {len(state['signals'])}")

def detect() -> list:
    """Group signals by portfolio company and turn patterns into needs.
    2+ corroborating sources, or an explicit challenge marker in the text,
    makes a need 'explicit'. A single soft signal stays 'possible' and must
    be confirmed with the founder before anyone acts on it."""
    state = load()
    by_company = {}
    for s in state["signals"]:
        by_company.setdefault(s["company"], []).append(s)
    found = []
    for company, signals in by_company.items():
        matched = {}
        for s in signals:
            low = s["text"].lower()
            for keys, need_text in NEED_PATTERNS:
                if any(k in low for k in keys):
                    matched.setdefault(need_text, []).append(s)
        # The broad expansion pattern is context, not a separate need, when a
        # specific need (e.g. distributor selection) comes from the same signals.
        if len(matched) > 1:
            generic = "Support the regional expansion (customers, partners, distribution)"
            if generic in matched:
                shared = {id(s) for s in matched[generic]}
                if any(shared & {id(s) for k, v in matched.items() if k != generic for s in v}):
                    del matched[generic]
        for need_text, sigs in matched.items():
            if any(n["company"] == company and n["need"] == need_text for n in state["needs"]):
                continue
            explicit = len({s["source"] for s in sigs}) >= 2 or any(
                m in s["text"].lower() for s in sigs for m in EXPLICIT_MARKERS)
            need = Need(
                id=f"need_{len(state['needs']) + 1:03d}",
                company=company, need=need_text,
                certainty="explicit" if explicit else "possible",
                evidence=[{"source": s["source"], "date": s["date"], "quote": s["text"]} for s in sigs],
                sources_count=len({s["source"] for s in sigs}),
            )
            found.append(need)
            state["needs"].append(asdict(need))
            print(f"\n[{need.certainty.upper()}] {company}: {need_text} "
                  f"({need.sources_count} source(s))")
            for e in need.evidence:
                print(f"   evidence ({e['source']}, {e['date']}): \"{e['quote']}\"")
    save(state)
    if not found:
        print("No new needs detected.")
    return found

def action(need_id: str) -> None:
    """The partner action card: lead with the portfolio development that
    needs attention, then reveal the introduction as the recommended action,
    with the reason, the evidence, and the evidenced relationship."""
    state = load()
    need = next((n for n in state["needs"] if n["id"] == need_id), None)
    if not need:
        sys.exit(f"No need {need_id}")
    print(f"\n=== ACTION FOR PARTNER — {need['company']} ===")
    print(f"Development needing attention: {need['need']} [{need['certainty']}]")
    print("Why now (evidence):")
    for e in need["evidence"]:
        print(f"  - ({e['source']}, {e['date']}) \"{e['quote']}\"")
    if need["certainty"] == "possible":
        print("\nThis is a POSSIBLE need. Confirm with the founder first:")
        print(confirm_text(need))
        return
    words = {w.strip(".,").lower() for w in need["need"].split() if len(w) > 2}
    ranked = sorted(state["contacts"], key=lambda c: score(c, words), reverse=True)
    best = next((c for c in ranked if score(c, words) > 0 and not c["scratched"]), None)
    if not best:
        print("\nNo evidenced match in the fund's network yet.")
        return
    print(f"\nRecommended action: introduction to {best['name']}, {best['role']}, {best['company']}")
    print(f"Evidenced relationship: strength {best['strength']}/5, source {best['source']}, "
          f"known by {best['owner_partner'] or 'the fund'}, past intro wins {best['wins']}")
    iid = f"intro_{len(state['intros']) + 1:03d}"
    state["intros"].append(asdict(Intro(
        id=iid, need=need["need"], portfolio_company=need["company"],
        contact_id=best["id"], partner=best["owner_partner"],
        created=date.today().isoformat(), last_touch=date.today().isoformat())))
    need["status"] = "actioned"
    save(state)
    print("\nIntroduction draft:")
    draft(iid)

def confirm_text(need: dict) -> str:
    quotes = " ".join(f'"{e["quote"]}"' for e in need["evidence"])
    return (f"Hi team, quick check-in. From your recent updates ({quotes}) "
            f"it looks like this may be coming up: {need['need']}. "
            f"Is that a real priority right now? If yes, I may know exactly the right person.")

def confirm(need_id: str) -> None:
    state = load()
    need = next((n for n in state["needs"] if n["id"] == need_id), None)
    if not need:
        sys.exit(f"No need {need_id}")
    print(confirm_text(need))

def resolve(need_id: str, connected: str, useful: str) -> None:
    """Track resolution: did the founder connect, and was the help useful?
    Useful help reinforces the pattern, so the next similar need is
    actioned faster and matched better."""
    state = load()
    need = next((n for n in state["needs"] if n["id"] == need_id), None)
    if not need:
        sys.exit(f"No need {need_id}")
    need["status"] = "resolved"
    need["connected"] = connected
    need["useful"] = useful
    post_feed(state, f"{need['company']}: need '{need['need']}' resolved. "
                     f"Founder connected: {connected}. Help useful: {useful}.")
    save(state)
    print(f"Resolved {need_id}: connected={connected}, useful={useful}")

# --------------------------------------------------------------------------
# 1. Ingest — email / LinkedIn / CSV
# --------------------------------------------------------------------------

def ingest_csv(path: str, partner: str = "") -> None:
    """Import contacts from a CSV export (LinkedIn Connections export,
    Gmail contacts export, or the sample format in data/contacts.sample.csv).

    Live connectors plug in here: an agent with Gmail / LinkedIn access
    exports the same columns and calls this same function.
    Columns: name,email,company,role,topics(| separated),strength,source
    """
    state = load()
    known = {c["email"] or c["name"] for c in state["contacts"]}
    added = 0
    with open(path, newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=1):
            key = row.get("email") or row.get("name", "")
            if not key or key in known:
                continue
            state["contacts"].append(asdict(Contact(
                id=f"c{i:03d}_{row.get('name','').split()[0].lower()}",
                name=row.get("name", "").strip(),
                email=row.get("email", "").strip(),
                company=row.get("company", "").strip(),
                role=row.get("role", "").strip(),
                topics=[t.strip().lower() for t in row.get("topics", "").split("|") if t.strip()],
                strength=int(row.get("strength") or 3),
                source=row.get("source", "csv").strip(),
                owner_partner=partner or row.get("owner_partner", ""),
            )))
            known.add(key)
            added += 1
    save(state)
    print(f"Ingested {added} new contacts. Total: {len(state['contacts'])}")

# --------------------------------------------------------------------------
# 2. Match — ranked, learning from outcomes
# --------------------------------------------------------------------------

def score(contact: dict, need_words: set) -> float:
    if contact["scratched"]:
        return -1.0
    def _hits(word: str, topic: str) -> bool:
        if word in topic or topic in word:
            return True
        return len(word) > 5 and len(topic) > 5 and word[:6] == topic[:6]  # stem match
    topic_hits = sum(1 for t in contact["topics"] if any(_hits(w, t) for w in need_words))
    text = f"{contact['company']} {contact['role']}".lower()
    text_hits = sum(1 for w in need_words if len(w) > 3 and w in text)
    base = (topic_hits * 3.0) + (text_hits * 1.5) + (contact["strength"] * 0.8)
    learned = (contact["wins"] * 2.0) - (contact["fails"] * 1.2)  # upgrade / eliminate
    return round(base + learned, 2)

def match(need: str, portfolio_company: str = "PortfolioCo", partner: str = "", top: int = 5) -> list:
    state = load()
    words = {w.strip(".,").lower() for w in need.split() if len(w) > 2}
    ranked = sorted(state["contacts"], key=lambda c: score(c, words), reverse=True)
    picks = [c for c in ranked if score(c, words) > 0][:top]
    print(f"\nTop intro targets for: \"{need}\" ({portfolio_company})")
    for c in picks:
        tag = " [SCRATCHED - excluded]" if c["scratched"] else ""
        print(f"  {score(c, words):>5}  {c['name']} — {c['role']}, {c['company']} "
              f"(strength {c['strength']}, wins {c['wins']}, fails {c['fails']}){tag}")
        if not c["scratched"]:
            iid = f"intro_{len(state['intros']) + 1:03d}"
            state["intros"].append(asdict(Intro(
                id=iid, need=need, portfolio_company=portfolio_company,
                contact_id=c["id"], partner=partner or c["owner_partner"],
                created=date.today().isoformat(), last_touch=date.today().isoformat(),
            )))
    save(state)
    return picks

# --------------------------------------------------------------------------
# 3. Draft — double opt-in, human approves before anything sends
# --------------------------------------------------------------------------

def draft(intro_id: str) -> str:
    state = load()
    intro = next((i for i in state["intros"] if i["id"] == intro_id), None)
    if not intro:
        sys.exit(f"No intro {intro_id}")
    c = next(x for x in state["contacts"] if x["id"] == intro["contact_id"])
    first = c["name"].split()[0]
    text = (
        f"Subject: Quick intro request — {intro['portfolio_company']}\n\n"
        f"Hi {first},\n\n"
        f"Hoping you're open to a short intro to the team at {intro['portfolio_company']}. "
        f"They're looking for exactly this: {intro['need']}.\n"
        f"Given your work at {c['company']}, I thought of you first. "
        f"Happy to send a two-line blurb first if you'd rather see it before I connect you both.\n\n"
        f"Thanks,\n{intro['partner'] or 'Your partner at the fund'}\n\n"
        f"[AGENT NOTE: draft only. Sent only after {intro['partner'] or 'the partner'} approves.]"
    )
    print(text)
    return text

# --------------------------------------------------------------------------
# 4. Follow-ups — the agent chases, so nothing is lost in the shuffle
# --------------------------------------------------------------------------

def followups() -> list:
    state = load()
    today = date.today()
    due = []
    for intro in state["intros"]:
        if intro["status"] in ("customer", "passed"):
            continue
        last = date.fromisoformat(intro["last_touch"] or intro["created"])
        idle = (today - last).days
        if idle >= FOLLOWUP_EVERY_DAYS:
            c = next((x for x in state["contacts"] if x["id"] == intro["contact_id"]), {})
            audience = "both sides" if idle >= WEEKLY_ROLLUP_DAYS else "intro target + portfolio company"
            msg = (f"NUDGE {intro['id']}: {intro['portfolio_company']} <-> {c.get('name','?')} "
                   f"idle {idle}d (status {intro['status']}) -> follow up with {audience}. "
                   f"Ask explicitly: did this turn into a meeting / next step?")
            print(msg)
            due.append(msg)
    if not due:
        print("No follow-ups due today.")
    return due

def record(intro_id: str, outcome: str) -> None:
    """Record an outcome and LEARN from it.
    meeting/customer -> contact wins +1 (boosted for similar future asks)
    passed/no_response -> fails +1; at the threshold the contact is scratched."""
    state = load()
    intro = next((i for i in state["intros"] if i["id"] == intro_id), None)
    if not intro:
        sys.exit(f"No intro {intro_id}")
    intro["status"] = outcome
    intro["last_touch"] = date.today().isoformat()
    c = next(x for x in state["contacts"] if x["id"] == intro["contact_id"])
    if outcome in ("replied", "meeting", "customer"):
        c["wins"] += 1
        post_feed(state, f"{intro['partner'] or 'A partner'}'s intro worked: "
                         f"{c['name']} ({c['company']}) -> {outcome} for {intro['portfolio_company']}")
    elif outcome in ("passed", "no_response"):
        c["fails"] += 1
        if c["fails"] >= SCRATCH_THRESHOLD and not c["scratched"]:
            c["scratched"] = True
            post_feed(state, f"{c['name']} scratched after {c['fails']} intros went nowhere. "
                             f"Excluded from future lists.")
    save(state)
    print(f"Recorded: {intro_id} -> {outcome}. {c['name']}: wins {c['wins']}, fails {c['fails']}, scratched {c['scratched']}")

# --------------------------------------------------------------------------
# 5. Analytics + firm feed — the simple interface
# --------------------------------------------------------------------------

def analytics(write_html: bool = True) -> dict:
    state = load()
    intros = state["intros"]
    by_status = {}
    for i in intros:
        by_status[i["status"]] = by_status.get(i["status"], 0) + 1
    by_partner = {}
    for i in intros:
        by_partner[i["partner"] or "unassigned"] = by_partner.get(i["partner"] or "unassigned", 0) + 1
    sent = sum(v for k, v in by_status.items() if k not in ("proposed",))
    stats = {
        "signals_read": len(state.get("signals", [])),
        "needs_detected": len(state.get("needs", [])),
        "needs_resolved": sum(1 for n in state.get("needs", []) if n["status"] == "resolved"),
        "needs_useful": sum(1 for n in state.get("needs", []) if n.get("useful") == "yes"),
        "contacts": len(state["contacts"]),
        "scratched_contacts": sum(1 for c in state["contacts"] if c["scratched"]),
        "intros_total": len(intros),
        "by_status": by_status,
        "by_partner": by_partner,
        "meetings": by_status.get("meeting", 0) + by_status.get("customer", 0),
        "top_connectors": sorted(
            [{"name": c["name"], "company": c["company"], "wins": c["wins"]} for c in state["contacts"]],
            key=lambda x: -x["wins"])[:5],
    }
    print(json.dumps(stats, indent=2))
    if write_html:
        rows = "".join(
            f"<tr><td>{html.escape(i['id'])}</td><td>{html.escape(i['portfolio_company'])}</td>"
            f"<td>{html.escape(i['contact_id'])}</td><td>{html.escape(i['status'])}</td>"
            f"<td>{html.escape(i['partner'])}</td></tr>" for i in intros)
        feed = "".join(f"<li>{html.escape(e['date'])} — {html.escape(e['text'])}</li>" for e in state["feed"])
        Path("analytics.html").write_text(
            f"<h1>Deal Flow — Intro Analytics</h1><pre>{html.escape(json.dumps(stats, indent=2))}</pre>"
            f"<h2>Open &amp; past intros</h2><table border=1 cellspacing=0 cellpadding=6>{rows}</table>"
            f"<h2>Firm feed</h2><ul>{feed}</ul>")
        print("Wrote analytics.html")
    return stats

def feed() -> None:
    state = load()
    for e in state["feed"]:
        print(f"{e['date']}  {e['text']}")
    if not state["feed"]:
        print("Feed is empty. Record an intro outcome to post the first update.")

# --------------------------------------------------------------------------
# Demo seed — runs the whole loop end to end with sample data
# --------------------------------------------------------------------------

def demo() -> None:
    STORE.unlink(missing_ok=True)
    print("=== 1. PORTFOLIO INTELLIGENCE: scattered updates -> detected needs ===")
    ingest_signals(str(Path(__file__).with_name("data") / "signals.sample.csv"))
    detect()
    ingest_csv(str(Path(__file__).with_name("data") / "contacts.sample.csv"))
    print("\n=== 2. PARTNER ACTION CARD (demo leads with the development, "
          "then reveals the intro) ===")
    needs = load()["needs"]
    explicit = next((n for n in needs if n["certainty"] == "explicit"), None)
    if explicit:
        action(explicit["id"])
    print("\n=== 3. THE ORIGINAL ASK FLOW: a portfolio company asks directly ===")
    before = len(load()["intros"])
    match("Intro to a VP Operations at a data center operator about cutting energy cost",
          portfolio_company="Soventify", partner="Giulio")
    match("Intro to a head of facilities at a hospital group about uptime",
          portfolio_company="Soventify", partner="Giulio")
    if len(load()["intros"]) > before:
        top_pick = load()["intros"][before]  # top-ranked intro of the ask flow
        draft(top_pick["id"])
        record(top_pick["id"], "meeting")
    print("\n=== 4. TRACK RESOLUTION: did the founder connect, was it useful? ===")
    if explicit:
        resolve(explicit["id"], "yes", "yes")
    print("\n--- Follow-ups due (simulated: none idle yet) ---")
    followups()
    print("\n--- Analytics ---")
    analytics()

# --------------------------------------------------------------------------

def main() -> None:
    p = argparse.ArgumentParser(description="Deal Flow Intro Agent (BYOA)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("demo")
    sg = sub.add_parser("signals"); sg.add_argument("csv")
    sub.add_parser("detect")
    ac = sub.add_parser("action"); ac.add_argument("--need", required=True)
    cf = sub.add_parser("confirm"); cf.add_argument("--need", required=True)
    rs = sub.add_parser("resolve"); rs.add_argument("--need", required=True)
    rs.add_argument("--connected", required=True); rs.add_argument("--useful", required=True)
    ing = sub.add_parser("ingest"); ing.add_argument("csv"); ing.add_argument("--partner", default="")
    m = sub.add_parser("match"); m.add_argument("--need", required=True)
    m.add_argument("--company", default="PortfolioCo"); m.add_argument("--partner", default="")
    d = sub.add_parser("draft"); d.add_argument("--intro", required=True)
    sub.add_parser("followups")
    r = sub.add_parser("record"); r.add_argument("--intro", required=True); r.add_argument("--outcome", required=True)
    sub.add_parser("analytics")
    sub.add_parser("feed")
    a = p.parse_args()
    if a.cmd == "demo": demo()
    elif a.cmd == "signals": ingest_signals(a.csv)
    elif a.cmd == "detect": detect()
    elif a.cmd == "action": action(a.need)
    elif a.cmd == "confirm": confirm(a.need)
    elif a.cmd == "resolve": resolve(a.need, a.connected, a.useful)
    elif a.cmd == "ingest": ingest_csv(a.csv, a.partner)
    elif a.cmd == "match": match(a.need, a.company, a.partner)
    elif a.cmd == "draft": draft(a.intro)
    elif a.cmd == "followups": followups()
    elif a.cmd == "record": record(a.intro, a.outcome)
    elif a.cmd == "analytics": analytics()
    elif a.cmd == "feed": feed()

if __name__ == "__main__":
    main()
