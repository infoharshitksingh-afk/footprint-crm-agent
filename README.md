# CRM Cleanup Agent

An agent that cleans a sales CRM the way a careful RevOps owner would: it finds what's broken, proposes a fix for each problem with a reason and a confidence score, and changes nothing until a human approves.

Built as an independent work sample for Footprint. Not affiliated with or endorsed by Footprint. The demo data is synthetic; every company and person in it is fictional.

## Why it works this way

Footprint's own rule for Percy is that agents propose and humans approve, and that every decision carries provenance. A CRM cleanup tool should follow the same rule. So:

- **Nothing writes back on its own.** The agent produces proposals. A person approves or rejects each one. Only approved changes are applied, and to copies of the export, never the originals.
- **Every change is explainable.** Each proposal says what it found, why, whether a rule or Claude made the call, and how confident it is. The change log records old value, new value and who approved it.
- **Ranked by money, not by count.** "412 issues" is noise. A duplicate on an account carrying a $480K deal outranks fifty typos on dead leads. The headline number is the share of open pipeline you can trust today.
- **It doesn't care which CRM you use.** Every CRM exports CSV. The agent maps your headers onto one standard schema once, saves the mapping, and everything downstream runs on that.
- **Your data stays on your machine.** It runs locally. With an API key, Claude sees only what it needs for a judgment (company names, domains, job titles, deal notes), never emails or amounts.

## What it checks

| Area | Rules catch | Claude decides |
|---|---|---|
| Accounts | Duplicates by domain or normalized name (FCU, Natl, Inc, LLC), messy domains, missing domains (inferred from contact emails), industry and country picklists | Look-alike accounts: same company or not? ("Granite Trust" vs "Granite Trust Bancorp" yes, "Meridian Community Bank" vs "Meridian Credit Union" no). Industry when the label is blank or vague |
| Contacts | Duplicate emails, invalid or mistyped emails, contacts not linked to an account (matched by email domain), buyer persona from title | Persona for titles no rule covers ("Head of Trust & Safety", "MLRO") |
| Deals | Non-standard stages, deals not rolling up to an account, missing amount or close date, close date already passed, no activity in 30+ days, no next step, missing source | What the notes really say: deals mis-staged ("legal sent MSA redlines" on a Discovery deal), deals at risk ("champion left"), and where the deal came from (an event mentioned only in the notes) |

Without an API key everything still runs. The judgment calls become flags for a human instead of proposed fixes.

## Run it on your CRM

1. **Export** accounts/companies, contacts and deals/opportunities from your CRM as CSV. Any CRM works.
2. **Drop the files into `input/`.** Names like `companies.csv`, `contacts.csv`, `deals.csv` help, but the agent can tell them apart by their headers.
3. **Install and run:**

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...     # optional, your own key
python run.py scan
```

4. **Confirm the field mapping.** It prints how it read your headers and saves `output/mapping.json`. Edit that file if anything's wrong and run `scan` again. You only do this once.
5. **Review.** `output/review.html` opens in your browser: the pipeline trust score, what's broken, and the review queue. Approve or reject each proposal (there's a one-click approve for high-confidence rule fixes), then download `decisions.json` into `output/`.
6. **Apply:**

```bash
python run.py apply
```

You get, in `output/clean/`:

- cleaned copies of your files with your original columns, ready to re-import
- `merge_plan.csv`: which record survives each merge (run merges natively in the CRM so activity history follows)
- `removed_duplicates_*.csv`: the merged-away rows, untouched
- `change_log.csv`: every change, why, who proposed it, who approved it
- `owner_tasks.csv`: problems only a rep can fix (missing amounts, stale deals), routed to each record's owner

## Try the demo

```bash
python run.py demo            # rules only, no key needed
ANTHROPIC_API_KEY=... python run.py demo   # with Claude
```

It runs on `demo/data`: a messy synthetic CRM for a compliance-software company selling to banks, credit unions and fintechs, with planted duplicates, look-alikes, orphaned deals, stale pipeline and attribution buried in notes. Regenerate it with `python demo/generate_demo.py`.

## Tuning it to your team

Everything opinionated lives in `crm_agent/schema.py`: pipeline stages and their aliases, industry picklist, buyer personas and their title keywords, event names to look for in notes, the stale-deal threshold. Change those and the agent follows.

Set `CRM_AGENT_MODEL` to use a different Claude model. `--no-llm` forces rules only even when a key is set.

## Layout

```
run.py                     CLI: scan, apply, demo
crm_agent/ingest.py        read exports, map headers to the standard schema
crm_agent/detect.py        rules + Claude judgments -> proposals
crm_agent/judge.py         Claude calls (structured tool output, batched, fail-safe)
crm_agent/prioritize.py    rank by open pipeline touched, pipeline trust score
crm_agent/report.py        review page
crm_agent/apply.py         apply approved decisions, write cleaned files and logs
crm_agent/schema.py        your picklists and rules
demo/                      synthetic CRM generator and data
tests/test_pipeline.py     end-to-end test with a fake Claude client (no network)
```

## What comes next

This is the cleanup. The standing version would run weekly against the CRM's API, catch new mess as it lands, and feed the numbers the role cares about: event-attributed pipeline, CAC against LTV, deal-cycle movement after events. Those numbers are only as good as the CRM underneath them, which is why this comes first.

## License

MIT. See `LICENSE`.
