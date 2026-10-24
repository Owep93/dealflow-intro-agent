# Deal Flow Intro Agent — Bring Your Own Agent

**Built for Deal Flow: NYC's First VC Hackathon @ Betaworks (Sat, Oct 24, 2026)**
Hosted by localhost:nyc and VCLab. Team: Harvey Francois + Giulio Profumo

**Challenge theme: Portfolio ops** — helping funds support their companies at scale.
The event's problem statement says venture capital runs on "spreadsheets, gut
feel and endless inbox triage," and asks for software that helps VCs "support
their founders after the check clears." That is exactly this agent's job: it
lives in the inbox, watches the portfolio, and turns founder support from
reactive triage into proactive, evidenced action, for any VC, in any sector.

## Portfolio intelligence that leads to action

> "Our agent follows every portfolio company, detects emerging needs, and
> activates the fund's network to help, before the founder has to ask."

**Track 3 fit:** turn scattered portfolio data into patterns a fund can act on.
The demo sequence:

1. **Read scattered updates** — a founder email mentions expansion; a company
   announcement confirms the launch.
2. **Identify a need** — distributor selection is an explicit challenge, or a
   possible need to confirm with the founder first.
3. **Find help** — match relevant experience with an evidenced relationship
   in the fund's network.
4. **Prepare action** — present the partner with the reason, the evidence,
   and the introduction draft.
5. **Track resolution** — record whether the founder connected and whether
   the help was useful.

The demo **leads with the portfolio development that needs attention**, then
reveals the introduction as the action the agent recommends.

## The team: Scout, Atlas, Bridge, Echo

Four agents run the workflow, so the founder gets relevant help without
having to know whom to ask, and the fund puts its collective network to
work:

- **Scout** spots the need. It reads the scattered updates and Akta
  signals and detects what is emerging, each need backed by evidence.
- **Atlas** finds who can help. It searches the whole firm's network,
  across every partner, and asks the colleagues when the answer sits in
  someone else's relationships.
- **Bridge** prepares the introduction: the partner action card (reason,
  evidence, evidenced relationship, draft), the consent flow, and the
  intro itself on approval.
- **Echo** checks the result: follows up both sides, records whether the
  founder connected and whether the help was useful, and feeds it back
  as trust and learning.

The demo story is Giulio's: an AI startup selling to insurance companies
posts that it launched a pilot with an insurer; its investor update says
three potential customers are stuck in security and procurement reviews.
Scout names the need ("help turning insurance pilots into paying
customers"), Atlas finds a colleague's contact who has sold AI software
to insurers and navigated these reviews, Bridge prepares the intro,
Echo confirms it landed and helped.

## Sponsors, and how each one is used

| Sponsor | How we use it | Priority |
|---|---|---|
| akta.pro | Company news and enriched portfolio profiles via API/MCP. Expansion, launches, partnerships and hiring become triggers for potential introductions. | Core integration |
| Nicrron × Ninoo | Nicrron for the model calls that extract needs, assess candidate relevance and draft recommendations. Ninoo helps build the application. | Core infrastructure |
| Block Convey / PRISM | Traces the workflow and evaluates whether recommendations are supported by the retrieved evidence (`trace`, `evaluate`). | Quality and demo proof |
| Roundtable | A founder's agent shares a current need with the fund's agent, which returns possible connections (`share`, `receive`). | Optional extension |
| BotMRR | "Bots that do the work": the whole team runs unattended in proactive `watch` mode. | Always on |

Run `python3 agent.py sponsors` for the live status of each integration.

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
   Slack): *"Giulio made an intro for Northwind Robotics — it became a meeting."*
   Everyone stays updated, and the analytics show which partners and
   which connectors actually produce outcomes.

## It works proactively, and it earns its autonomy

**Proactive by default.** The agent does not wait to be asked. On a loop
(`watch`) or a schedule (`run`), each cycle it reads new portfolio updates
dropped in `inbox/`, detects needs, prepares partner action cards, queues
follow-up nudges for idle intros, and writes a partner briefing
(`briefing.md`). Everything it wants to send goes through an **outbox**:
auto-approved only for actions its trust level has earned, otherwise it
waits for a human's one-tap approval. The script is the brain; the VC's own
host agent (their Muse or other assistant) is the hands that execute the
outbox through the connected mailbox, so the script never holds mailbox
passwords.

**The reward mechanism: a Trust Ladder.** The agent earns XP only for
*verified* outcomes: a reply (+3), a meeting (+10), a customer (+25), a
founder confirming a detected need (+5), help marked useful (+15). Dead
intros cost XP and add a strike; three strikes demote it a level. Levels
unlock real access:

| Level | Name | Unlocks |
|---|---|---|
| L0 | Observer | Read signals, detect needs, report only |
| L1 | Drafter (start) | Draft intros and confirmations, propose ranked matches |
| L2 | Coordinator (20 XP, 1 win) | Send follow-up nudges itself, post the firm feed to Slack, hold calendar slots |
| L3 | Connector (60 XP, 3 wins) | Send the double-opt-in first ask on approved needs, auto-enrich contacts |
| L4 | Operator (150 XP, 8 wins) | Manage correspondence end to end, book meetings, update the CRM, brief partners unprompted |

In the demo you watch it happen: one meeting and one "useful" resolution
take the agent from L1 to L2 live. Automation here is *earned*, never
given, and a human always approves the first intro to anyone.

## Connected to every channel an investor actually uses

Investors do not live in one inbox. The agent works across all of it,
through the VC's own connected agent (bring your own agent means the
connections are the VC's, held by their assistant, never by this script):

| Channel | The agent reads | The agent sends |
|---|---|---|
| Email (Gmail / Outlook) | Contacts, founder updates, intro threads | Intro asks, follow-ups |
| LinkedIn | Connections graph, founder posts, job changes | DM intro asks |
| X | Founder posts: launches, raises, hires | DM intro asks, warm replies |
| Instagram / Threads | Founder and operator presence, updates | DM intro asks |
| WhatsApp / Telegram | The real backchannel with founders and operators | One-tap intro asks, nudges |
| Slack | The firm's internal channels | Firm feed, partner alerts |
| Discord | Founder communities | DM intro asks |
| Calendar | Meeting outcomes, the ground truth an intro worked | Holds and bookings (earned levels only) |

Every contact carries their handles and their **best channel**, and every
action card says so: the ask goes out where that person actually answers,
not as another cold email. Founder posts are signals too: a launch post on
LinkedIn or a raise teased on X feeds the same need detection as an email.

## Sponsor integration: Akta.pro, our data layer

[Akta.pro](https://akta.pro) (by Wokelo AI) is a private company data and
signals API built for agents: 20M+ private companies, 70+ data points per
company, entity-resolved news, and alternative signals like job posts,
headcount trends and reviews. We use it for the two things a fund's own
notes cannot do:

1. **Portfolio watchlist signals.** Akta watches every portfolio company
   and streams signals (a hiring spike in distribution roles, a launch, a
   raise) into the agent's need detection. In the demo, an Akta jobs
   signal corroborates Northwind Robotics' distributor need.
2. **Enrichment on every action card.** Each card carries Akta
   firmographics and recent signals for the portfolio company *and* the
   intro target's company, so "why this person, why now" is evidenced
   with live market data, not gut feel.

Two live routes, MCP first: set `AKTA_MCP_URL` to Akta's MCP server and
the agent speaks MCP to it directly (it discovers the company tool from
`tools/list`, nothing is hardcoded), with `AKTA_API_KEY` as the bearer
when the server asks for one. Or set only `AKTA_API_KEY` and it calls the
live REST API. With neither, it reads `data/akta.sample.json`, a cache in
the Akta response shape. Enrichment is never invented: no Akta record,
no enrichment block.
Run `python3 agent.py akta` for status, `python3 agent.py enrich --company "Northwind Robotics"` to test it.

## Run it

```bash
python3 agent.py demo        # full loop with sample data
python3 agent.py signals data/signals.sample.csv   # scattered portfolio updates in
python3 agent.py detect                            # needs out, each with quoted evidence
python3 agent.py action --need need_001            # partner action card + intro draft
python3 agent.py confirm --need need_002           # draft to confirm a possible need
python3 agent.py resolve --need need_001 --connected yes --useful yes
python3 agent.py run         # one proactive cycle: inbox, detection, nudges, briefing
python3 agent.py watch --interval 60   # proactive loop
python3 agent.py agent       # trust profile: level, XP, what is unlocked, what is next
python3 agent.py ingest data/contacts.sample.csv
python3 agent.py match --need "VP Operations at a national retail chain" --company RouteWise --partner Giulio
python3 agent.py draft --intro intro_001
python3 agent.py followups
python3 agent.py record --intro intro_001 --outcome meeting
python3 agent.py analytics   # stats + analytics.html, the simple interface
python3 agent.py agents      # Scout, Atlas, Bridge, Echo
python3 agent.py sponsors    # every sponsor integration and its live status
python3 agent.py trace       # PRISM trace of everything the agents did
python3 agent.py evaluate    # PRISM: is each recommendation supported by the evidence?
python3 agent.py share --need need_001   # Roundtable: share a need agent-to-agent
python3 agent.py receive roundtable_need.json   # receive one the same way
```

No dependencies. Python 3 standard library only. State is one local
`state.json` file on the VC's own machine — contacts never go to a
third-party server.

## Files
- `agent.py` — the whole agent: ingest, match, draft, follow-ups, learning, analytics
- `SKILL.md` — instructions any AI agent (Muse etc.) follows to run this script
- `data/contacts.sample.csv` — sample enriched contact list for the demo
- `data/signals.sample.csv` — sample scattered portfolio updates: a founder
  email, a launch announcement, a call note

## What is stubbed for the hackathon demo
- Live Gmail / LinkedIn / Slack connectors: the ingest format and feed
  hooks are in place; in the demo they run on CSV exports and console
  output instead of live API calls.
- Enrichment: topics come from the export; a production version enriches
  from email history and LinkedIn headlines automatically.
