# Deal Flow Intro Agent — Bring Your Own Agent

**Built for Deal Flow: NYC's First VC Hackathon @ Betaworks (Sat, Oct 24, 2026)**
Team: Harvey Francois + Giulio Profumo

## The problem

VCs have the contacts. What they do not have is the time.

Every week a portfolio company asks: *"Can you intro us to a VP Operations,
a buyer, a facilities head?"* The partner then has to remember who they know,
build the list by hand, write the intro, chase both sides, and figure out
whether anything came of it. Most of the time it gets lost in the shuffle,
and the VC is the one expected to be proactive and suggest who to contact.

## The solution — very simple, on purpose

A script that runs on the VC's **own** AI agent (their Muse, or any other
assistant they already use). No new platform to learn. *Bring your own agent.*

1. **Connect** — the VC connects email or LinkedIn once. The agent pulls
   every contact and organises them with enriched data: company, role,
   topics, relationship strength, which partner knows them.
2. **Match** — a portfolio company states its ask in plain words. The agent
   returns a ranked, ready-to-send intro list, so the partner only approves.
3. **Draft + send** — double-opt-in intro drafts. Nothing sends without
   the partner's approval.
4. **Follow up automatically** — the agent manages the correspondence.
   Every 2-3 days it nudges the intro target *and* the portfolio company,
   with a weekly rollup, so it learns whether the intro worked even when
   the portfolio company forgets to report back.
5. **Learn** — outcomes feed back in. A contact who produced a meeting gets
   boosted for similar asks, so new intros to new startups are already
   optimised. A contact whose intros went nowhere 2-3 times gets
   **scratched** from future lists.
6. **Firm network effect** — multiple partners at the firm can be invited
   in. Every intro and outcome posts to one firm feed (or drops into
   Slack): *"Giulio made an intro for Soventify — it became a meeting."*
   Everyone stays updated, and the analytics show which partners and
   which connectors actually produce outcomes.

## Run it

```bash
python3 agent.py demo        # full loop with sample data
python3 agent.py ingest data/contacts.sample.csv
python3 agent.py match --need "VP Operations at a data center operator" --company Soventify --partner Giulio
python3 agent.py draft --intro intro_001
python3 agent.py followups
python3 agent.py record --intro intro_001 --outcome meeting
python3 agent.py analytics   # stats + analytics.html, the simple interface
```

No dependencies. Python 3 standard library only. State is one local
`state.json` file on the VC's own machine — contacts never go to a
third-party server.

## Files
- `agent.py` — the whole agent: ingest, match, draft, follow-ups, learning, analytics
- `SKILL.md` — instructions any AI agent (Muse etc.) follows to run this script
- `data/contacts.sample.csv` — sample enriched contact list for the demo

## What is stubbed for the hackathon demo
- Live Gmail / LinkedIn / Slack connectors: the ingest format and feed
  hooks are in place; in the demo they run on CSV exports and console
  output instead of live API calls.
- Enrichment: topics come from the export; a production version enriches
  from email history and LinkedIn headlines automatically.
