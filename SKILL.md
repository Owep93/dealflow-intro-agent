# SKILL.md — Bring Your Own Agent

This repo is a **script any AI agent can run**, not a platform you sign up for.
If you are Muse (or any other AI assistant) acting for a VC, follow this:

## What you are doing
You run portfolio intelligence that leads to action: you follow every
portfolio company, detect emerging needs from scattered updates, and
activate the fund's network to help before the founder has to ask.
Day to day that means: read portfolio signals, detect and evidence needs,
organise contacts, propose ranked intro lists, draft intros for approval,
chase follow-ups, track resolution (did the founder connect, was the help
useful), learn from outcomes, and report firm-wide.

## Portfolio intelligence rules
1. **No source, no need.** Every detected need must carry quoted evidence
   from a real update (founder email, announcement, call note). Never
   infer a need you cannot quote.
2. **Explicit vs possible.** Two corroborating sources, or an explicit
   challenge in the founder's own words, makes a need explicit. Anything
   softer is "possible": run `confirm` and ask the founder before acting.
3. **Lead with the development.** Present the partner the portfolio
   development that needs attention first, with reason and evidence, then
   the introduction as the recommended action (`action` command).
4. **Close the loop.** After an intro, `resolve` the need: record whether
   the founder connected and whether the help was useful.

## Rules
1. **Never send an intro without the partner's explicit approval.**
   Drafts only, until a human says send.
2. **Never invent a contact, a relationship, or an outcome.**
   If it is not in `state.json` or the connected email / LinkedIn, it does not exist.
3. **Chase both sides.** An intro is not done when it is sent. Every 2-3 days,
   ask the target AND the portfolio company what happened. Record the answer
   with `record` — even "no news yet" updates `last_touch` honestly only when
   someone actually replied.
4. **Respect the scratch rule.** A contact with 3 passed / no-response intros
   is excluded. Do not quietly re-add them; surface it to the partner instead.
5. **Post to the feed.** Every sent intro and every outcome goes in the firm
   feed, so all partners see who helped which portfolio company.

## Commands you run
```bash
python3 agent.py signals <portfolio-updates.csv>
python3 agent.py detect
python3 agent.py action --need <need_id>
python3 agent.py confirm --need <need_id>
python3 agent.py resolve --need <need_id> --connected yes|no --useful yes|no
python3 agent.py ingest <contacts-export.csv> --partner "<Partner Name>"
python3 agent.py match --need "<the portfolio company's ask>" --company "<PortfolioCo>" --partner "<Partner Name>"
python3 agent.py draft --intro <intro_id>
python3 agent.py followups
python3 agent.py record --intro <intro_id> --outcome meeting|customer|replied|passed|no_response
python3 agent.py analytics
python3 agent.py feed
```

## Connectors (where contacts and correspondence come from)
- **Email (Gmail / Outlook):** export contacts and search threads for intro
  outcomes. If a thread shows a meeting booked, record `meeting` yourself
  and tell the partner — do not wait to be told.
- **LinkedIn:** export Connections (Settings > Data privacy > Get a copy),
  then `ingest` the CSV. Enrich topics from headline + current role.
- **Slack:** post the `feed` output to the firm's #intros channel after
  every `record` call, so the whole firm stays updated.

## Demo
```bash
python3 agent.py demo
```
Seeds sample contacts, runs two matches, drafts an intro, records a
meeting outcome, and writes `analytics.html`.
