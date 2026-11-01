# Charity Growth Finder (mhance · SilverTree Pioneers Track A)

**What it does:** type a UK charity's name or registration number and, on one screen, see its **total income** and **total expenditure** for the last 3 years, whether each is **▲ Up, ► Flat or ▼ Down**, its **net surplus or deficit**, its key people (chair, trustees and senior-staff counts), and why it may or may not be worth contacting. Add it to your prospects and get an evidence-based **outreach plan**: the hook, a first email with your Calendly link, an estimated best time to approach, and a 4-step follow-up sequence you can copy, open in your email app or download.

**The problem it solves:** mhance's sales team checks charities one at a time on the Charity Commission website to work out who is growing. That's slow, inconsistent and disconnected from the outreach that follows. This tool turns it into one workflow:

> ① Search → ② understand the financial direction and priority → ③ save as a prospect → ④ get the outreach plan → ⑤ copy / export

| Page | What a salesperson does there | Data |
|---|---|---|
| **Look up a charity** (main page) | One search box for a full or partial name or a registration number. Below it are **Recent searches** (the last 5 charities opened in this browser session, newest first, as clickable cards), or **Explore charities** examples on a first visit. The search box is a **dropdown**: as you type it suggests matching charities with £1m+ income (from the saved list; about 9,400 names, kept small so the page stays light). Pick one to open it. **Press Enter to search the live register** for anything you've typed, a name of any size or a registration number. The register only matches exact spelling, punctuation included, so the app also tries a hyphenated version: *make a wish* finds *Make-A-Wish Foundation UK*. Results are ranked exact name, then starts with, then contains (ties go to the larger charity); the best match opens straight away with a "pick another" list. The summary answers the core questions in order, with no tabs or pop-ups: name and number, total income / expenditure for 3 years with labelled trends (% **and** £ change), net surplus / deficit, why it may or may not be worth contacting, key people, and one **Add to prospects** button. Chart, peer comparison, contact details, links and a CSV of every year on record (up to 5, the most the Charity Commission publishes, with the income breakdown where filed) sit below under *More detail*. | Live API |
| **Find new prospects** | Filter all ~172,000 registered charities. **Minimum income** is the first filter (default £100k or more; choose *Any* to include small charities). The page says how many charities each option leaves out. Maximum income is under *More filters*. Then area, sector, priority, trend. Sort by priority, size, £ growth or % growth. **View details** and **Add** on each row; export to CSV. | Daily bulk extract |
| **Check a list** | Paste up to 100 charity numbers (e.g. from a CRM export) and trend-check them all live. | Live API |
| **My prospects** | An action queue, **Your next actions**: overdue first, then due today, then inside the estimated planning window, then later. Replied, stopped or paused prospects are folded into **No action needed**. The selected prospect shows a short brief (**Why this account · Why now · Who · Next**) with one main action and Done / Snooze / Not relevant buttons. The source line separates reported, calculated and estimated information. Drafts, later steps, scoring detail, notes, downloads and settings are one click away in collapsed sections. | Live API |
| **Settings** | Data status, the up/down and hot-prospect rules (adjustable), and what every figure and label means. There is no sidebar. | – |

---

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py              # opens http://localhost:8501
```

**Configuration: one API key.** The Charity Commission API is free, but despite the brief it **does need a key**. Register at <https://api-portal.charitycommission.gov.uk>, subscribe to *Register of Charities API*, then put the key in a file called `api_key.txt` next to `app.py` and restart. `.streamlit/secrets.toml` (`CHARITY_API_KEY = "..."`) or a `CHARITY_API_KEY` environment variable also work, and are what you'd use when deployed. `api_key.txt` is git-ignored. Without a key, the prospect search still works and the other pages explain what's needed.

**Developer checks**

```bash
pip install -r requirements-dev.txt
python -m pytest            # 63 tests
ruff check . && ruff format --check .
python build_dataset.py --download --src bulk   # refresh the bulk snapshot (~2GB temp download)
```

**Weekly data refresh.** `.github/workflows/refresh-data.yml` runs every Monday at 04:17 UTC (or on demand: *Actions → Refresh charity snapshot → Run workflow*). It downloads the Commission's latest bulk extract, rebuilds `data/*.parquet`, and commits them if anything changed. Streamlit Cloud redeploys on that push, and the app reloads the new files without a restart: cached data is keyed on the files' modification time and size (`Snapshot.version()`). The bot's commits land on `main`, so run `git pull` before pushing local work.

**Deploy (public):** push to GitHub, create an app on Streamlit Community Cloud pointing at `app.py`, and add `CHARITY_API_KEY` under *Secrets*. Requirements:
- Python 3.10+ and `requirements.txt` (Streamlit **1.65+**; the app uses top navigation, badges and widget state that survives page switches).
- `data/charities.parquet` and `data/financials.parquet` must be in the repo (or rebuilt with `build_dataset.py`) for *Find new prospects* and the example cards on the lookup page.
- **Saved prospects are a local JSON file.** On Streamlit Cloud every visitor shares the same list and it resets when the app restarts. That's fine for a demo; production would store prospects in Dynamics 365. Set `CHARITY_OUTREACH_FILE` to use a different file (e.g. a test list).
- After a push that changes `analysis.py` or `outreach.py` but not `app.py`, use *Manage app → Reboot* if you see an error about a missing name: Streamlit Cloud can keep the old module loaded.

---

## Architecture and data flow

```
                    ┌──────────────── app.py (Streamlit UI: 5 pages) ───────────────┐
 search / lookup /  │                                                                │
 list / outreach ──►│ data_sources.LiveAPI ──► Charity Commission Register API       │
                    │   (requests-cache, 24h, SQLite)   search, details, financial   │
                    │                                   history, overview, trustees  │
                    │         │ normalised record {financials, trustees, profile}    │
                    │         ▼                                                      │
                    │ analysis.summarise ──► status, up/flat/down, vs peers, hot,    │
                    │                        gaps, priority (+ reasons)              │
                    │         │                                                      │
                    │         ▼                                                      │
                    │ outreach.build_plan ──► hooks, evidence, recipient, timing,    │
                    │                         Day 0/3/5/7 drafts, plan export        │
                    │         │                                                      │
                    │ prospects.ProspectStore ──► outreach.json (saved prospects)    │
                    │                                                                │
 prospect filter ──►│ data_sources.Snapshot ──► data/*.parquet (built by             │
 + benchmarks       │   analysis.base_table/benchmarks   build_dataset.py from the   │
                    │                                    free daily bulk extract)    │
                    └────────────────────────────────────────────────────────────────┘
```

| File | Responsibility |
|---|---|
| `app.py` | UI only: layout, widgets, wiring. No financial rules live here. |
| `data_sources.py` | **All** Charity Commission access. One `LiveAPI` client (key header, caching, error handling, response normalisation, duplicate-trustee removal, malformed-row skipping) and a data-only `Snapshot`. |
| `analysis.py` | Deterministic financial rules: ordering, % change, status, up/flat/down, peer comparison, hot, spike, stale, missing-year gaps, priority. Pure functions plus a vectorised twin for the whole register (tested to give identical answers). |
| `outreach.py` | Hooks, evidence, recipient/greeting, estimated timing, the 4-step sequence, financial summary, next action, Markdown plan export. Pure functions. |
| `prospects.py` | Saved prospects and settings in `outreach.json`: dedupe by registration number, persistence, tolerant of a missing or corrupt file. |
| `build_dataset.py` | Streams the 2GB bulk extract into two small parquet files (~18MB). |

### Charity Commission API integration

`https://api.charitycommission.gov.uk/register/api` with header `Ocp-Apim-Subscription-Key`. Endpoints used: `searchCharityName`, `charitydetailsmulti` (to sort search results by size), `allcharitydetailsV2` (profile, contact, sectors, areas), `charityfinancialhistory` (5 years of income/expenditure plus income by source), `charityoverview` (staff, volunteers, activities) and `charitytrusteeinformationv2` (trustees, chair, appointment dates).

- **Caching:** 24h on disk. Accounts change at most yearly; repeat searches are instant. "Not found" responses are cached too.
- **Failures:** bad key (401), rate limit (429), network errors and non-JSON bodies all become a plain-English message. Malformed rows (missing numbers, non-numeric income, unknown shapes) are skipped, never guessed. A bad key is detected once at start-up and explained on the page (and under Settings).
- **No silent fallback:** named-charity lookups never quietly switch to older bulk data. If the API fails, the user is told.
- **Why the bulk extract as well?** The API can't answer "education charities in Ealing with £1m–£5m income" or "what's normal growth for a £5m charity?". The free daily bulk extract can, so it's used for exactly those two jobs and shows its extract date.

---

## Definition of financial trends

All thresholds are constants at the top of `analysis.py`.

1. **Window:** the charity's **last 3 annual returns**, sorted by financial year end. Financial years end on all sorts of dates, so "3 years" means 3 returns, not 3 calendar years.
2. **Up / Flat / Down (the brief's indicator):** total % change from the oldest to the latest of those 3 returns. **More than +5% = Up, less than −5% = Down, otherwise Flat.** The same rule applies to income and expenditure. The ±5% band stops a 1% wobble being sold as growth. It's adjustable under Settings.
3. **vs peers (context):** the same change compared with the **median for charities of the same size**. Size is based on income at the *start* of the window, because using latest income would push growers into bigger bands. Bands: £10k–£100k, £100k–£500k, £500k–£1m, £1m–£5m, £5m–£10m, £10m–£25m, £25m–£100m, £100m+. Every band has at least 111 up-to-date peers. Within ±5% of the median = ► In line. *Why both?* The typical charity grew ~9% over 3 years, largely inflation, so about two-thirds of £1m+ charities read as "Up". Up/flat/down answers the brief; vs peers answers "is this one actually outperforming?".
4. **When no trend is shown (labelled, never guessed):** **Under 3 yrs data** (fewer than 3 returns); **Base under £10k** (% change off a tiny base is meaningless); **⚠ Check data** (income or expenditure changed more than 50× between two returns, almost always a filing error).
5. **Missing years:** if two consecutive returns are more than 15 months apart, the page warns that a reporting year is missing. Nothing is filled in.
6. **YoY** for each row is against the previous return on record, even if that return is outside the 3-year window.
7. **Money terms.** Charities don't report "revenue". **Total income** is the charity equivalent, and the app calls it that. **Net surplus / deficit = total income − total expenditure** for the same year. Income and expenditure are never added together. A missing figure stays missing (–); nothing is estimated.
8. **Every % comes with its £.** e.g. "+31.6% (+£21.7m) over 3 years", so a big percentage on a small number is obvious at a glance. Charts switch between £, £k and £m so small charities aren't drawn as a row of 0.0s, and bars start at zero.

### Small charities

Very small charities produce huge percentage swings: +383% for a community association whose income went from £20k to £98k. To stop these crowding out real prospects:

- **Small charity = income under £100k** by default. It follows the *Minimum income* filter on *Find new prospects* and is used everywhere.
- Growth measured from income under that line is labelled **"High percentage growth from a small base"**. It is shown, but it **doesn't raise priority**: a charity can't become Medium or High on percentage growth alone if it started small. The brief's hot rule (+10% on the year before) still applies to everyone, but small-base cases are worded as "above the hot-prospect line, but from a small base".
- *Find new prospects* leaves small charities out by default, using the visible *Minimum income* filter. It always states how many charities each option hides (e.g. "Not shown: 119,286 with income under £100k · 8,860 with no accounts on record · 834 with overdue accounts"). Nothing is hidden silently.
- Sorting by % growth with small charities included shows a warning. A **£ growth** sort is offered as the fairer alternative.

**Real example:** Sickle Cell Care Manchester (1162402) shows income £137k → £86k → **£88.9m**. The live API returns exactly that, so it's an error in the Commission's own record (almost certainly £88,933 typed as £88.9m). Without the guard it topped the prospect list as a "+102,902%" hot prospect; now it's 🔴 *Check first*.

## Prospect prioritisation rules

No opaque score. The first rule that matches wins, and the page lists the reasons in plain English.

| Priority | Rule |
|---|---|
| Check first | Figures look like a filing error (Check data) |
| Low | Not enough history, tiny base, or latest accounts more than 22 months old (stale) |
| High | **Hot** (income up more than 10% on the previous year, the brief's rule) **and** income growing faster than peers, neither from a small base |
| Medium | Hot **or** growing faster than peers, not from a small base |
| Low | Neither, or growth only from a small base |

The reasons also state whether latest income falls in the £1m–£100m range assumed to suit Dynamics 365 (an assumption, shown as such; it doesn't change the level). A ⚡ **Spike** (income more than doubled) is flagged so a human checks whether it's a one-off.

## Outreach plan and timing assumptions

- **Evidence and hook.** Hooks fire only from figures in the filings: strong growth; government contracts as 30%+ of income or up 20%+; trading income up 25% and £100k+; a new chair (18 months) or 2+ new trustees (12 months); 50+ staff or 200+ volunteers. "Costs outpacing income" is used in the call script only, as it's too sensitive for a cold email. The strongest hook opens email 1 and the second strongest opens the day-3 follow-up. With no signal, a neutral size/sector opener is used and labelled as such.
- **Careful wording.** Emails say what the data shows, then use "can", "may" or "often" for what that might mean. They never claim problems, technology, budgets, buying intent or named staff that the data doesn't contain. A test bans phrases like "usually means" and "your systems are".
- **Recipient.** A named published address (anna.barker@) gets "Dear Anna"; a generic one (info@) is addressed to the chair from the trustee list; otherwise "Dear Trustees". The register lists trustees, not staff, so the plan links to LinkedIn *searches* for the CEO, finance director and chair rather than scraping personal details (GDPR/PECR).
- **Timing is an estimate.** Charities usually plan next year's budget a few months before their year end. We know the year end from filings, not the actual budget cycle, so the plan says **"Estimate"** and shows the rule: by default the window is **6 to 2 months before year end**, configurable under *Settings* on My prospects. The brief calls it a **"possible" planning window** and says it is a hypothesis, not confirmed buying intent.
- **Sequence.** Day 0 email (hook + mhance + Calendly) → Day 3 follow-up (second angle) → Day 5 call script (questions, voicemail) → Day 7 LinkedIn note (≤300 chars). Days are **working days**. Outcome (Active, Replied, Meeting booked, Not interested, Not relevant, Paused) stops the sequence.
- **Dates never contradict the timing estimate.** If the estimated window hasn't opened, the first email is planned for the first working day of the window. Until then the current action is **"Research the Finance Director"** (or Chief Executive for charities under £1m), due two weeks before. To contact sooner, switch on *early relationship-building* (under *Activity and notes*); the action is then labelled as early relationship-building, not a sales approach. Once the first email is marked done, the later steps are dated from that day, so a live sequence never jumps to next year's window.
- **Action queue (deterministic, tested).** Groups: 1 overdue, 2 due today, 3 inside the estimated window, 4 later, 5 no action needed. Within a group: earliest due date, then High > Medium > Low > Check first, then name. The prospect opened by default is the first actionable one that isn't Low priority (otherwise the first actionable one); a replied or stopped record never opens automatically. **Snooze** pushes the current action back one working week; **Not relevant** moves the prospect to *No action needed* and opens the next one.
- **Likely buyer.** The brief names one role to aim for: Finance Director (income £1m+) or Chief Executive (smaller charities). Contact routes shown are only those published on the register. The chair is named as a trustee, never as a confirmed buyer.
- **Copy and export.** Each draft can be edited, opened in your email app, or copied from a copy box. "Download this plan" gives a Markdown file with everything; "Download every prospect's sequence" gives a CSV for mail merge or CRM import.

---

## Usability decisions (tested as a first-time salesperson)

- **One screen answers the brief.** The main page is the charity look-up. Name, number, total income and expenditure for 3 years with labelled trends, surplus / deficit, the reason to contact (or not), trustees and **Add to prospects** are all on the page, with no tabs, pop-ups or sections to expand. Typing a name or number and pressing Enter is enough: **0 clicks** (or pick from the dropdown). Detail lives below under *More detail*, and other features are separate, clearly named pages.
- **Dropdown plus live search.** The search box suggests £1m+ charities as you type (Streamlit's built-in dropdown; its matching is simple, so punctuation must roughly match). Pressing Enter always searches the live register, retrying with hyphens because the register needs exact punctuation (*make a wish* found nothing before). A fuller type-ahead over all 172,000 names was tried and dropped in favour of this simpler, native control.
- **Settings survive page switches** (search box, filters, small-charity threshold), so moving between pages never loses your place.

- **Buttons, not tick boxes.** Search results, prospect lists and saved prospects are lists with **View details**, **Add** and **Open** buttons. The first version needed a tick box to open a charity, which users found unintuitive.
- **Saving always shows up straight away.** Closing the charity pop-up refreshes the page (`on_dismiss="rerun"`). Previously a prospect saved inside the pop-up only appeared after some other click, so saving looked like it "only worked sometimes".
- **Plain language.** "Look up a charity", "Add to prospects", "My prospects", "similar charities", "vs year before", "Suggested time to get in touch". No API, cache or YoY jargon in the interface.
- **Facts vs estimates vs drafts are marked.** Headings say which is which: "(from the accounts)", "(estimate)", "Drafts for you to edit".
- **First screen is never empty.** A search box, then **Recent searches** as clickable cards (name, number, latest income, priority). They're kept in Streamlit session state: private to each browser session, never shared with other users, cleared on refresh. A first visit shows a few **Explore charities** examples instead, with figures from the data.
- **Light theme by default** (`.streamlit/config.toml`), whatever the viewer's system setting.

## Key decisions and alternatives considered

| Decision | Why | Alternatives considered |
|---|---|---|
| Streamlit | Real UI for non-technical users in hours; tables, charts, downloads; free hosting with a shareable link. | CLI (salespeople won't use a terminal); React/Next.js (better long-term, too slow for 24h). |
| Live API for named charities + bulk extract for register-wide jobs | Each source does what it's good at; no silent fallback. | API-only (can't filter by area/sector/income; 172k calls); bulk-only (up to a day old; brief asks for the API). |
| Up/flat/down **and** vs peers | Meets the brief literally and adds the context that makes it useful. | Absolute only (inflation makes most charities "Up"); peers only (drops the brief's indicator). |
| Rules-based outreach, not an LLM | Every sentence traces to data; can't invent facts; deterministic and testable; no API costs or keys. | LLM drafting (nicer prose, but hallucination risk with real names and figures). Kept as a future layer on top of the rules. |
| Explainable priority tiers | A salesperson can repeat the reason to a manager. | Weighted 0–100 score (false precision, hard to explain). |
| JSON file for saved prospects | Zero setup, inspectable, enough for one user. | SQLite/Postgres (overkill for a prototype); Dynamics 365 (the right production home). |
| 24h request cache (SQLite) | Accounts change yearly; instant repeats; polite to the API. | No cache; in-memory only (lost on restart). |

## Known limitations

- **Bulk extract vs API history:** for some charities the bulk annual-return file holds fewer years than the API's financial history (e.g. St Francis' Children's Society: 2 vs 5). The prospect list (bulk) can therefore say "Under 3 yrs data" where the live lookup shows a full trend. The live lookup is authoritative.
- **Peer benchmarks** come from the bulk snapshot, which is up to a week old: it's refreshed weekly (see *Weekly data refresh*), not live.
- **Saved prospects** live in one local JSON file: single user, not shared, and reset on hosts with temporary disks such as Streamlit Cloud. Edits to a draft last for the session; the plan regenerates from data.
- **No staff names:** the register names trustees and gives published contact details, but never names staff. *Key people* therefore shows the chair and trustees (with start dates and the other charities each also sits on), plus a staff line from the annual return: employees, how many are paid over £60k and the highest pay band, and volunteers. The chief executive and finance director have to be found on the charity's website or LinkedIn.
- **Budget timing** is a rule-of-thumb estimate, labelled as such.
- **England & Wales only:** Scottish (OSCR) and Northern Irish charities aren't on this register.
- The **£1m–£100m target range** for Dynamics 365 is an assumption, not mhance data.

## What I'd change for production

1. **Write to Dynamics 365 instead of a file:** prospects become leads/accounts, sequence steps become activities and tasks (Dataverse Web API or Power Automate). That also solves multi-user, history and reporting.
2. **Scheduled refresh** of the bulk snapshot and benchmarks, plus monitoring of API errors and rate limits.
3. **Shared cache** (Redis/Azure Cache), retry with back-off, and a service key held in Azure Key Vault.
4. **Authentication** (Entra ID) so only mhance staff can use it.
5. **Measure adoption:** prospects saved, emails opened from the tool, meetings booked per sequence.

## Intentionally left out

- AI-written emails (hallucination risk; a polishing layer could sit on top of the rules later).
- Sending email or LinkedIn messages from the tool (keeps a human in the loop; avoids spam and compliance risk).
- Scraping staff names or personal emails.
- Scottish and Northern Irish registers.
- Accounts and login.

## Files

```
app.py               Streamlit UI (5 pages)
analysis.py          Financial rules: ordering, % change, status, up/flat/down, vs peers, hot, gaps, priority
outreach.py          Hooks, evidence, recipient, estimated timing, scheduling, action queue, sequence, plan export
prospects.py         Saved prospects + settings (outreach.json), dedupe, persistence
data_sources.py      Charity Commission API client (cached, normalised) + bulk Snapshot
build_dataset.py     Bulk extract -> data/*.parquet
tests/               63 pytest tests
WALKTHROUGH.md       10–15 minute demo outline
pyproject.toml       ruff + pytest config
```

Data © Charity Commission for England and Wales, used under the Open Government Licence v3.0.
