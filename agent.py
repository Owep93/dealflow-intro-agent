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
  python3 agent.py match --need "VP Operations at a national retail chain"
  python3 agent.py draft  --intro intro_001   # print a double-opt-in draft
  python3 agent.py followups                   # who needs a nudge today
  python3 agent.py record --intro intro_001 --outcome meeting
  python3 agent.py analytics                   # print stats + write analytics.html
  python3 agent.py feed                        # firm activity feed (Slack-ready)
  python3 agent.py run                         # ONE proactive cycle (see below)
  python3 agent.py watch --interval 60         # proactive loop, every N minutes
  python3 agent.py agent                       # trust profile: level, XP, unlocks

Proactive mode:
  The agent does not wait to be asked. Each cycle it reads new portfolio
  updates from inbox/, detects needs, prepares action cards, queues
  follow-up nudges, and writes briefing.md. Sends go through the outbox:
  auto-approved only at a trust level that has EARNED that action;
  everything else waits for a human. The host agent (the VC's own Muse
  or other assistant) executes the outbox through its connected mailbox,
  which is why this script never holds mailbox passwords.

Reward mechanism (Trust Ladder):
  Verified outcomes pay XP: reply +3, meeting +10, customer +25, founder
  connected +5, help marked useful +15, confirmed need +5. Dead intros
  cost XP and add strikes; 3 strikes demote a level. Levels unlock real
  access: L1 Drafter (drafts only), L2 Coordinator (sends follow-up
  nudges itself, posts to Slack), L3 Connector (sends double-opt-in
  first asks on approved needs), L4 Operator (books meetings, updates
  the CRM, briefs partners unprompted). Automation is earned, never given.

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
INBOX = Path(__file__).with_name("inbox")        # drop signal CSVs here
SCRATCH_THRESHOLD = 3          # failed intros before a contact is scratched
FOLLOWUP_EVERY_DAYS = 3        # nudge cadence while an intro is open
WEEKLY_ROLLUP_DAYS = 7

# --------------------------------------------------------------------------
# The reward mechanism: a TRUST LADDER (earned autonomy, not blind autonomy)
#
# The agent earns XP for VERIFIED good outcomes only: a reply, a meeting,
# a customer, a founder confirming a detected need, help marked useful.
# Bad outcomes cost XP and add a strike. At XP + verified-win thresholds
# the agent LEVELS UP and unlocks more access and more autonomy. Three
# strikes demote it a level: trust is earned slowly and lost fast.
# Every autonomous action is logged; everything above the agent's level
# is routed to a human. A human always approves the FIRST intro to anyone.
# --------------------------------------------------------------------------

REWARDS = {"replied": 3, "meeting": 10, "customer": 25,
           "connected": 5, "useful": 15, "confirmed_need": 5}
PENALTIES = {"passed": -2, "no_response": -2, "not_useful": -5, "wrong_need": -5}

LEVELS = [
    {"level": 0, "name": "Observer", "xp": 0, "wins": 0,
     "unlocks": ["read signals", "detect needs", "report only"]},
    {"level": 1, "name": "Drafter", "xp": 0, "wins": 0,
     "unlocks": ["draft intros and founder confirmations", "propose ranked matches"]},
    {"level": 2, "name": "Coordinator", "xp": 20, "wins": 1,
     "unlocks": ["send follow-up nudges on approved intros without asking each time",
                 "post the firm feed to Slack", "hold calendar slots for meetings"]},
    {"level": 3, "name": "Connector", "xp": 60, "wins": 3,
     "unlocks": ["send the double-opt-in first ask for high-scoring matches on approved needs",
                 "enrich contacts from email history automatically"]},
    {"level": 4, "name": "Operator", "xp": 150, "wins": 8,
     "unlocks": ["manage correspondence end to end", "book meetings",
                 "update the CRM", "send the weekly partner briefing unprompted"]},
]
START_LEVEL = 1   # a new agent starts as a Drafter: useful, but supervised

def default_agent() -> dict:
    return {"xp": 0, "level": START_LEVEL, "strikes": 0, "wins": 0,
            "autonomous_actions": 0, "routed_to_human": 0, "history": []}

def agent_profile(state: dict) -> dict:
    state.setdefault("agent", default_agent())
    for k, v in default_agent().items():
        state["agent"].setdefault(k, v)
    return state["agent"]

def recompute_level(state: dict) -> None:
    p = agent_profile(state)
    earned = START_LEVEL
    for lv in LEVELS:
        if p["xp"] >= lv["xp"] and p["wins"] >= lv["wins"]:
            earned = max(earned, lv["level"])
    if p["strikes"] >= 3:                      # three strikes: demotion
        earned = max(0, earned - 1)
        p["strikes"] = 0
        print("  [trust] 3 strikes: agent DEMOTED a level. Trust is lost fast.")
    if earned > p["level"]:
        p["level"] = earned
        new = LEVELS[earned]
        print(f"  [trust] LEVEL UP -> L{earned} {new['name']}. Unlocked: "
              + "; ".join(new["unlocks"]))
    elif earned < p["level"]:
        p["level"] = earned

def award(state: dict, event: str) -> None:
    """Apply a reward or penalty from a VERIFIED outcome, then re-level."""
    p = agent_profile(state)
    pts = REWARDS.get(event, PENALTIES.get(event, 0))
    if pts == 0:
        return
    p["xp"] = max(0, p["xp"] + pts)
    if event in ("meeting", "customer"):
        p["wins"] += 1
    if pts > 0:
        p["strikes"] = max(0, p["strikes"] - 1)   # good work clears strikes
    else:
        p["strikes"] += 1
    p["history"].append({"date": date.today().isoformat(), "event": event, "points": pts})
    sign = "+" if pts > 0 else ""
    print(f"  [trust] {event}: {sign}{pts} XP (total {p['xp']}, level {p['level']})")
    recompute_level(state)

def can(state: dict, min_level: int) -> bool:
    return agent_profile(state)["level"] >= min_level

def queue_outbox(state: dict, kind: str, text: str, min_level: int) -> dict:
    """Everything the agent wants to send goes through the outbox.
    At or above its trust level for that action it is auto-approved;
    below it, the item is routed to a human. Nothing is ever silently sent."""
    p = agent_profile(state)
    auto = can(state, min_level)
    item = {"date": date.today().isoformat(), "kind": kind, "text": text,
            "status": "auto_approved" if auto else "awaiting_human_approval",
            "agent_level": p["level"]}
    state.setdefault("outbox", []).append(item)
    if auto:
        p["autonomous_actions"] += 1
    else:
        p["routed_to_human"] += 1
    return item

def show_agent() -> None:
    state = load()
    p = agent_profile(state)
    lv = LEVELS[p["level"]]
    nxt = LEVELS[p["level"] + 1] if p["level"] + 1 < len(LEVELS) else None
    print(f"Agent trust: L{p['level']} {lv['name']} | XP {p['xp']} | wins {p['wins']} | strikes {p['strikes']}")
    print(f"Unlocked now: {'; '.join(lv['unlocks'])}")
    if nxt:
        print(f"Next: L{nxt['level']} {nxt['name']} at {nxt['xp']} XP and {nxt['wins']} wins. "
              f"Unlocks: {'; '.join(nxt['unlocks'])}")
    print(f"Earned-automation row: {p['autonomous_actions']} actions taken autonomously, "
          f"{p['routed_to_human']} routed to a human, every one logged.")

# --------------------------------------------------------------------------
# Data model
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Connector map: every channel an investor actually lives on.
# The host agent (the VC's own Muse / assistant) holds each connection;
# this script consumes what they export and queues sends back per channel.
# --------------------------------------------------------------------------

CONNECTORS = {
    "email":     {"gives": "contacts, founder updates, intro threads",
                  "reach": "intro asks, follow-ups", "connect": "Gmail / Outlook via host agent"},
    "linkedin":  {"gives": "connections graph, founder posts, job changes",
                  "reach": "connection requests, InMail / DM intro asks", "connect": "Connections export or host agent"},
    "x":         {"gives": "founder posts (launches, raises, hires), warm replies",
                  "reach": "DM intro asks, public warm-up engagement", "connect": "X account via host agent"},
    "instagram": {"gives": "founder / operator presence, story updates",
                  "reach": "DM intro asks", "connect": "Instagram via host agent"},
    "threads":   {"gives": "founder posts and conversations",
                  "reach": "DM intro asks", "connect": "Threads via host agent"},
    "whatsapp":  {"gives": "the real backchannel: founder and operator chats",
                  "reach": "one-tap intro asks, nudges", "connect": "WhatsApp via host agent"},
    "telegram":  {"gives": "founder and community chats",
                  "reach": "DM intro asks", "connect": "Telegram via host agent"},
    "slack":     {"gives": "fund's internal channels, portfolio community",
                  "reach": "firm feed, partner alerts", "connect": "Slack workspace webhook / app"},
    "discord":   {"gives": "founder communities, hackathon and DAO rooms",
                  "reach": "DM intro asks, community posts", "connect": "Discord via host agent"},
    "calendar":  {"gives": "meeting outcomes (the ground truth an intro worked)",
                  "reach": "meeting holds and bookings (L2+ / L4)", "connect": "Google Calendar via host agent"},
}

def connectors() -> None:
    print("Channels this agent works across (connected through your own agent):")
    for name, c in CONNECTORS.items():
        print(f"  {name:<10} reads: {c['gives']}\n  {'':<10} sends: {c['reach']}  [{c['connect']}]")

@dataclass
class Contact:
    id: str
    name: str
    email: str = ""
    company: str = ""
    role: str = ""
    topics: list = field(default_factory=list)   # e.g. ["retail", "ops"]
    strength: int = 3                            # 1 weak .. 5 close
    source: str = ""                             # email | linkedin | manual
    owner_partner: str = ""                      # which partner knows them
    socials: list = field(default_factory=list)  # e.g. ["x:@dana", "linkedin:dana-whitfield"]
    channel: str = ""                            # best way to reach them: whatsapp | x | email ...
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
        for key in ("contacts", "intros", "feed", "signals", "needs", "outbox"):
            state.setdefault(key, [])
        agent_profile(state)
        return state
    return {"contacts": [], "intros": [], "feed": [], "signals": [], "needs": [],
            "outbox": [], "agent": default_agent()}

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
    reach = best.get("channel") or (best.get("socials") or ["email"])[0].split(":")[0]
    handles = ", ".join(best.get("socials") or []) or "email on file"
    print(f"Best reached via: {reach} ({handles}) — the ask goes out on that channel, not a cold email")
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
    if connected == "yes":
        award(state, "connected")
    award(state, "useful" if useful == "yes" else "not_useful")
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
                socials=[s.strip() for s in (row.get("socials") or "").split("|") if s.strip()],
                channel=(row.get("channel") or "").strip(),
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
        award(state, outcome)   # verified good outcome: the agent earns trust
        post_feed(state, f"{intro['partner'] or 'A partner'}'s intro worked: "
                         f"{c['name']} ({c['company']}) -> {outcome} for {intro['portfolio_company']}")
    elif outcome in ("passed", "no_response"):
        award(state, outcome)   # dead intro: small penalty + a strike
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
    _p = agent_profile(state)
    stats = {
        "agent_trust": {"level": _p["level"], "name": LEVELS[_p["level"]]["name"],
                        "xp": _p["xp"], "wins": _p["wins"], "strikes": _p["strikes"],
                        "autonomous_actions": _p["autonomous_actions"],
                        "routed_to_human": _p["routed_to_human"]},
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
# 6. Proactive mode — the agent works without being asked
# --------------------------------------------------------------------------

def run_cycle() -> None:
    """One proactive pass. Run it on a loop (`watch`) or on a schedule
    (cron / the host agent's scheduler). In one pass the agent:
      1. reads any new portfolio updates dropped in inbox/ (CSV exports
         from the VC's own mailbox, written by whatever agent hosts this)
      2. detects new needs and prepares partner action cards for the
         explicit ones; possible needs get a founder-confirmation draft
      3. queues follow-up nudges for idle intros — sent autonomously only
         if the agent's trust level has EARNED that (L2+); otherwise the
         nudge waits in the outbox for a human's one-tap approval
      4. writes briefing.md: what needs attention, what it did, what is
         waiting on a human, and its earned-automation row
    The agent never waits to be asked, and never exceeds its level."""
    print(f"--- Proactive cycle {date.today().isoformat()} ---")
    state = load()
    p = agent_profile(state)
    print(f"Agent: L{p['level']} {LEVELS[p['level']]['name']}, XP {p['xp']}")
    if INBOX.exists():
        done_dir = INBOX / "processed"
        for csv_file in sorted(INBOX.glob("*.csv")):
            ingest_signals(str(csv_file))
            done_dir.mkdir(exist_ok=True)
            csv_file.rename(done_dir / csv_file.name)
            print(f"  processed inbox file {csv_file.name}")
    detect()
    state = load()
    for need in state["needs"]:
        if need["status"] != "detected":
            continue
        if need["certainty"] == "explicit":
            action(need["id"])   # prepares match + draft, marks actioned
            state = load()
            last = state["intros"][-1] if state["intros"] else None
            if last:
                queue_outbox(state, "intro_draft",
                             f"Intro draft for {need['company']} ({need['need']}) ready: {last['id']}",
                             min_level=1)
                save(state)
        else:
            queue_outbox(state, "founder_confirmation",
                         confirm_text(need), min_level=1)
            need["status"] = "confirmation_queued"
            save(state)
    # follow-ups for idle intros
    state = load()
    today = date.today()
    nudges = 0
    for intro in state["intros"]:
        if intro["status"] in ("customer", "passed"):
            continue
        last = date.fromisoformat(intro["last_touch"] or intro["created"])
        if (today - last).days >= FOLLOWUP_EVERY_DAYS:
            item = queue_outbox(state, "followup_nudge",
                                f"Nudge both sides on {intro['id']} "
                                f"({intro['portfolio_company']}, idle {(today - last).days}d)",
                                min_level=2)   # autonomy must be earned
            nudges += 1
            print(f"  follow-up nudge queued for {intro['id']}: {item['status']}")
    save(state)
    # briefing
    state = load()
    p = agent_profile(state)
    open_needs = [n for n in state["needs"] if n["status"] in ("detected", "actioned", "confirmation_queued")]
    waiting = [o for o in state["outbox"] if o["status"] == "awaiting_human_approval"]
    lines = [f"# Partner briefing — {date.today().isoformat()}", "",
             f"Agent trust: L{p['level']} {LEVELS[p['level']]['name']} (XP {p['xp']}, wins {p['wins']})",
             f"Earned-automation row: {p['autonomous_actions']} actions taken autonomously, "
             f"{p['routed_to_human']} routed to a human, every one logged.", "",
             "## Portfolio developments needing attention"]
    lines += [f"- {n['company']}: {n['need']} [{n['certainty']}, {n['status']}]" for n in open_needs] or ["- none"]
    lines += ["", "## Waiting on a human"]
    lines += [f"- [{o['kind']}] {o['text']}" for o in waiting] or ["- nothing"]
    Path("briefing.md").write_text("\n".join(lines) + "\n")
    print(f"Briefing written to briefing.md ({len(open_needs)} open needs, "
          f"{nudges} nudges queued, {len(waiting)} items waiting on a human)")

def watch(interval_minutes: int = 60) -> None:
    import time
    print(f"Watching. Proactive cycle every {interval_minutes} min. Ctrl-C to stop.")
    while True:
        run_cycle()
        time.sleep(interval_minutes * 60)

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
    match("Intro to a VP Operations at a national retail chain about a delivery partnership pilot",
          portfolio_company="RouteWise", partner="Giulio")
    match("Intro to a VP Supply Chain at a national retailer about reducing delivery churn",
          portfolio_company="BrightCart", partner="Giulio")
    if len(load()["intros"]) > before:
        top_pick = load()["intros"][before]  # top-ranked intro of the ask flow
        draft(top_pick["id"])
        record(top_pick["id"], "meeting")
    print("\n=== 4. TRACK RESOLUTION: did the founder connect, was it useful? ===")
    if explicit:
        resolve(explicit["id"], "yes", "yes")
    print("\n--- Follow-ups due (simulated: none idle yet) ---")
    followups()
    print("\n=== 5. THE REWARD: verified outcomes earned the agent more trust ===")
    show_agent()
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
    sub.add_parser("run")        # one proactive cycle
    w = sub.add_parser("watch"); w.add_argument("--interval", type=int, default=60)
    sub.add_parser("agent")      # trust profile: level, XP, unlocks
    sub.add_parser("connectors") # every channel the agent works across
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
    elif a.cmd == "run": run_cycle()
    elif a.cmd == "watch": watch(a.interval)
    elif a.cmd == "agent": show_agent()
    elif a.cmd == "connectors": connectors()

if __name__ == "__main__":
    main()
