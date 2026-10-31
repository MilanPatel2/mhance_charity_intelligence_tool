# Charity Growth Finder (mhance, Track A)

A tool for mhance's sales team to see which UK charities are growing or shrinking, so they can decide who to call first.

| Tab | What it's for | Data |
|---|---|---|
| **🔎 Look up a charity** | Type a name or registration number and pick from the list of matches. You get 3 years of income and expenditure, a trend for each compared with similar-sized charities, year-on-year changes, a 5-year chart, trustees (chair first), sectors, areas, contact details, links to the charity's Charity Commission and Companies House pages, and a CSV download. | Live API |
| **🎯 Find prospects** | Filter all ~172,000 registered charities by area (175 local authorities plus regions), sector and income, then sort and export a call list. Click any row to open that charity's full page. | Bulk extract |
| **📋 Check a list** | Paste up to 100 charity numbers from a CRM export and trend-check them all at once. | Live API |
| **📬 Outreach** | Your call list. Tick charities in any table (or press *Add to outreach* on a charity's page) and each one gets a ready-to-edit 4-step sequence built from its own figures: **Day 0** first email with a data-driven hook and your Calendly link, **Day 3** follow-up email with a second angle, **Day 5** phone call script, **Day 7** LinkedIn connection note. Track done/outcome, open drafts in your email app, export everything to CSV. | Live API |

### Labels used everywhere

| Label | Meaning |
|---|---|
| ▲ Above peers / ► In line / ▼ Below peers | Income (or expenditure) change over the last 3 annual returns, compared with the median for charities of the same size (its **peer group**, shown on every charity page). Within ±5% of the peer median = In line; e.g. if peers grew +8%, more than +13% is Above and less than +3% is Below. |
| ◌ Under 3 yrs data | Fewer than 3 annual returns on record, so it's too early to call a trend. |
| ◌ Base under £10k | Income 3 years ago was under £10k, so % changes are meaningless. |
| ⚠ Check data | Income or expenditure changed more than 50× between two returns, almost always a filing error. |
| 🔥 Hot prospect | Latest year's income up more than 10% on the year before. |
| ⚡ Spike | Income more than doubled in a year. Often a one-off (legacy, merger, appeal). |
| Stale | Latest return ended more than 22 months ago (late or missing filing). |

---

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py
```

**API key.** The Charity Commission API is free, but despite what the brief says it does need a key. Register at <https://api-portal.charitycommission.gov.uk> and subscribe to *Register of Charities API*. Create a file called `api_key.txt` next to `app.py` containing just the key, then restart the app. (`.streamlit/secrets.toml` or a `CHARITY_API_KEY` environment variable also work; that's what you'd use when deployed.) `api_key.txt` is git-ignored so the key never ends up on GitHub.

Without a key, prospect search still works. The lookup, list and outreach tabs tell you to add one.

**Refresh the bulk snapshot** (a few minutes, ~2GB temporary download):

```bash
python build_dataset.py --download --src bulk
```

**Tests:** `python -m pytest` (22 tests covering the trend rules and edge cases (including a real filing error from the register), API response parsing, and the outreach rules: hooks, greetings, dates and timing).

**Deploy:** push to GitHub, create an app on [Streamlit Community Cloud](https://share.streamlit.io) pointing at `app.py`, and add `CHARITY_API_KEY = "your-key"` under *Secrets*.

---

## Decisions and why

**1. Live API for named charities, bulk data only where the API can't help.** Anything about a charity you name (search, lookup, list check) goes to the live API, with no local-data fallback. If the API fails, the app says so rather than quietly showing day-old figures. The API can't answer "education charities in Ealing with £1m–£5m income" or "what's normal growth for a £5m charity?", so for those two jobs only, `build_dataset.py` turns the Commission's free daily bulk download into two small parquet files (~18MB). Every screen shows which source it's using and the extract date.

**2. Trends are relative to similar-sized charities, not absolute.** The brief asks whether income is going up, flat or down. But almost every charity's income has risen in cash terms recently: the median charity grew ~9% over 3 years, largely inflation. Under an absolute rule, about two-thirds of £1m+ charities read as "Up", which doesn't help anyone prioritise. So each charity is compared with peers:
- **Peers** are charities in the same size band, using income at the *start* of the 3-year window. Using latest income would bias it, because charities that grew move up into a bigger band.
- **Bands:** £10k–£100k, £100k–£500k, £500k–£1m, £1m–£5m, £5m–£10m, £10m–£25m, £25m–£100m, £100m+. These are narrow enough that a £1m charity isn't compared with a £50m one, but every band still has 100+ peers (the smallest, £100m+, has 111). The sales-relevant bands between £1m and £100m are split finer than the standard NCVO bands.
- **Peer baseline** is the median 3-year change for up-to-date peers with a reliable trend. It's shown next to every trend and in a "Market benchmarks" table, so the sales team can see what the charity is being compared against.

For example, Cancer Research UK's income grew +2.2% over 3 years, but its peer group (111 charities over £100m) grew +7.4% at the median, so it's ▼ Below peers.

**3. Only trust a trend when the data supports one.** Three things get a separate label instead of an arrow:
- *Fewer than 3 returns* (new charities).
- *A tiny starting base* (under £10k).
- *Impossible jumps.* Sickle Cell Care Manchester (1162402) is a real example. Its income goes £137k → £86k → **£88.9m**, and expenditure £98k → £125m. The live API returns those exact figures, so it's an error in the Commission's own record, almost certainly £88,933 entered as £88.9m. Without a guard it topped the prospect list as a "+102,902%" hot prospect. Anything changing more than 50× in a year is now flagged "⚠ Check data" and kept out of trends, hot flags and the peer benchmarks. About 1,100 charities on the register trip it, and around 500 jumps across all years exceed 50×.

**4. Hot prospect stays as the brief defines it** (latest YoY income +10%), applied only where the data's reliable. It answers a different question from the trend ("did they just have a big year?" rather than "are they outgrowing their peers over 3 years?"), so a charity can be 🔥 Hot but ► In line. The threshold is a slider because ~40% of £1m+ charities clear 10%.

**5. One word for one thing.** The Charity Commission and the brief say "expenditure", so the tool says "expenditure" everywhere: UI, CSVs and code.

**6. Default filter of £1m–£100m income.** This assumes the sales team cares about charities large enough to buy and run Dynamics 365 but not so large they run enterprise tenders. It's one click to change.

**7. Caching.** API responses are cached on disk for 24 hours (requests-cache + SQLite). Accounts change at most once a year, so a day is safe, repeat lookups are instant, and the "check a list" tab doesn't hammer the API. "Not found" responses are cached too.

**8. Outreach is rules-based, not AI.** Every sentence in a draft is a template filled with Charity Commission figures, so it can't invent facts about a charity, and every claim traces back to the data. The salesperson edits and sends; nothing is sent automatically.
- **The hook** is picked from the strongest signal in the data: strong growth (hot and/or above peers), government contract income (30%+ of income or growing fast; contracts mean heavy reporting), trading income growth (shops and cafés mean stock and sales to track), new chair or trustees (new boards review how things run), or lots of staff and volunteers. "Costs outpacing income" is used in the call script only, because it's too sensitive to open a cold email with. Email 1 uses the strongest hook and the day-3 follow-up uses the second, so the follow-up adds something rather than just "bumping".
- **The greeting matches the inbox.** A named address (anna.barker@) gets "Dear Anna"; a generic one (info@, admin@) is addressed to the chair from the trustee list; with no chair, "Dear Trustees".
- **Timing.** Charities plan next year's budget in the ~6 to 2 months before their year end, which we know from their filings, so each plan says whether now is a good time.
- **Dates are working days** (day 3 = three working days after day 0), so nothing lands on a weekend and steps never clash.
- **Contact details: published only.** The register gives the charity's published email and phone and the trustees' names, but not staff. Rather than scraping personal emails (a GDPR / PECR problem), the tool links to LinkedIn searches for the chief executive, finance director and chair, who are the likely buyers.
- The call list and your details are saved to `outreach.json` next to the app (git-ignored). On a hosted deployment that file isn't permanent; in production this would live in Dynamics 365 itself.

**9. Streamlit.** It's the fastest way to give a non-technical user a real UI with tables, charts and downloads, and it deploys free with a shareable link. I considered a CLI (nobody in sales uses a terminal) and React (better long-term, too slow for 24 hours).

## What I'd do next

- **Push straight into Dynamics 365.** mhance sells Dynamics, so hot prospects and their outreach sequences should become leads, activities and tasks in their CRM via the Dataverse Web API or Power Automate, not CSVs and a JSON file.
- **AI polish on top of the rules.** Have an LLM rewrite each draft in the salesperson's voice, while the facts still come only from the rules (pass it the figures, forbid anything else).
- **Use the outreach signals in the prospect list too.** Income by source (government contracts, trading) and staff numbers already drive the outreach hooks; adding them to the bulk snapshot would let sales filter the whole register on them (e.g. "contract-funded charities in London").
- **Alerts.** A weekly email of charities that newly turned hot or moved above peers in the team's patch.
- **Production hardening.** Schedule the snapshot refresh (a weekly GitHub Action is included in `.github/workflows/` but hasn't been run yet), add API retry/backoff, and use a shared cache if more than a handful of people use it.

## Files

```
app.py              Streamlit UI (4 tabs)
analysis.py         Status / peer-relative trend / hot / spike / stale rules (pure functions, tested)
outreach.py         Hooks, greeting, timing and the 4-step outreach sequence (pure functions, tested)
data_sources.py     LiveAPI (cached) for named charities; Snapshot for register-wide data
build_dataset.py    Bulk extract -> data/*.parquet
data/               Snapshot: charities + 5-yr financials
tests/              pytest
```

Data © Charity Commission for England and Wales, used under the Open Government Licence v3.0.
