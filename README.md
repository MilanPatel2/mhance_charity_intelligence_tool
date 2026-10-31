# Charity Growth Finder (mhance · SilverTree Pioneers Track A)

**What it does:** type a UK charity's name or registration number and see its last 3 years of income and expenditure, whether each is **▲ Up, ► Flat or ▼ Down**, how that compares with similar-sized charities, its trustees, and a clear **priority** for sales. Save it as a prospect and get an evidence-based **outreach plan**: the hook, a first email with your Calendly link, an estimated best time to approach, and a 4-step follow-up sequence you can copy, open in your email app or download.

**The problem it solves:** mhance's sales team checks charities one at a time on the Charity Commission website to work out who is growing. That's slow, inconsistent and disconnected from the outreach that follows. This tool turns it into one workflow:

> ① Search → ② understand the financial direction and priority → ③ save as a prospect → ④ get the outreach plan → ⑤ copy / export

| Tab | What a salesperson does there | Data |
|---|---|---|
| 🔎 **Look up a charity** | Search by name (pick from a list of matches, largest first) or registration number. See income and expenditure for the last 3 returns with up/flat/down and the peer comparison, a 5-year chart, priority and why, trustees (chair first), sectors, areas, contact details, links to the Charity Commission and Companies House pages, CSV download, **📬 Add to outreach**. | Live API |
| 🎯 **Find prospects** | Filter all ~172,000 registered charities by area (175 local authorities and regions), sector, income band, priority and trend. Sorted by priority, then size. Tick one row to open it, or several to add them all to outreach. Export to CSV. | Daily bulk extract |
| 📋 **Check a list** | Paste up to 100 charity numbers (e.g. from a CRM export) and trend-check them all live. | Live API |
| 📬 **Outreach** | Saved prospects with priority, best time (estimate), next action and due date. Open one for the full plan: financial summary, priority reasons, evidence, timing, who to contact, notes, and the Day 0 / 3 / 5 / 7 sequence. Copy, open in email, download the plan or export everything to CSV. | Live API |

---

## Run it

```bash
pip install -r requirements.txt
streamlit run app.py              # opens http://localhost:8501
```

**Configuration: one API key.** The Charity Commission API is free, but despite the brief it **does need a key**. Register at <https://api-portal.charitycommission.gov.uk>, subscribe to *Register of Charities API*, then put the key in a file called `api_key.txt` next to `app.py` and restart. `.streamlit/secrets.toml` (`CHARITY_API_KEY = "..."`) or a `CHARITY_API_KEY` environment variable also work, and are what you'd use when deployed. `api_key.txt` is git-ignored. Without a key, the prospect search still works and the other tabs explain what's needed.

**Developer checks**

```bash
pip install -r requirements-dev.txt
python -m pytest            # 39 tests
ruff check . && ruff format --check .
python build_dataset.py --download --src bulk   # refresh the bulk snapshot (~2GB temp download)
```

**Deploy (optional):** push to GitHub, create an app on Streamlit Community Cloud pointing at `app.py`, add `CHARITY_API_KEY` under *Secrets*.

---

## Architecture and data flow

```
                    ┌──────────────── app.py (Streamlit UI: 4 tabs) ────────────────┐
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
- **Failures:** bad key (401), rate limit (429), network errors and non-JSON bodies all become a plain-English message. Malformed rows (missing numbers, non-numeric income, unknown shapes) are skipped, never guessed. A bad key is detected once at start-up and shown in the sidebar.
- **No silent fallback:** named-charity lookups never quietly switch to older bulk data. If the API fails, the user is told.
- **Why the bulk extract as well?** The API can't answer "education charities in Ealing with £1m–£5m income" or "what's normal growth for a £5m charity?". The free daily bulk extract can, so it's used for exactly those two jobs and shows its extract date.

---

## Definition of financial trends

All thresholds are constants at the top of `analysis.py`.

1. **Window:** the charity's **last 3 annual returns**, sorted by financial year end. Financial years end on all sorts of dates, so "3 years" means 3 returns, not 3 calendar years.
2. **Up / Flat / Down (the brief's indicator):** total % change from the oldest to the latest of those 3 returns. **More than +5% = ▲ Up, less than −5% = ▼ Down, otherwise ► Flat.** The same rule applies to income and expenditure. The ±5% band stops a 1% wobble being sold as growth. It's adjustable in the sidebar.
3. **vs peers (context):** the same change compared with the **median for charities of the same size**. Size is based on income at the *start* of the window, because using latest income would push growers into bigger bands. Bands: £10k–£100k, £100k–£500k, £500k–£1m, £1m–£5m, £5m–£10m, £10m–£25m, £25m–£100m, £100m+. Every band has at least 111 up-to-date peers. Within ±5% of the median = ► In line. *Why both?* The typical charity grew ~9% over 3 years, largely inflation, so about two-thirds of £1m+ charities read as "Up". Up/flat/down answers the brief; vs peers answers "is this one actually outperforming?".
4. **When no trend is shown (labelled, never guessed):** **◌ Under 3 yrs data** (fewer than 3 returns); **◌ Base under £10k** (% change off a tiny base is meaningless); **⚠ Check data** (income or expenditure changed more than 50× between two returns, almost always a filing error).
5. **Missing years:** if two consecutive returns are more than 15 months apart, the page warns that a reporting year is missing. Nothing is filled in.
6. **YoY** for each row is against the previous return on record, even if that return is outside the 3-year window.

**Real example:** Sickle Cell Care Manchester (1162402) shows income £137k → £86k → **£88.9m**. The live API returns exactly that, so it's an error in the Commission's own record (almost certainly £88,933 typed as £88.9m). Without the guard it topped the prospect list as a "+102,902%" hot prospect; now it's 🔴 *Check first*.

## Prospect prioritisation rules

No opaque score. The first rule that matches wins, and the page lists the reasons in plain English.

| Priority | Rule |
|---|---|
| 🔴 Check first | Figures look like a filing error (⚠ Check data) |
| ⚪ Low | Not enough history, tiny base, or latest accounts more than 22 months old (stale) |
| 🟢 High | 🔥 **Hot** (income up more than 10% on the previous year, the brief's rule) **and** income growing faster than peers |
| 🟡 Medium | Hot **or** growing faster than peers |
| ⚪ Low | Neither |

The reasons also state whether latest income falls in the £1m–£100m range assumed to suit Dynamics 365 (an assumption, shown as such; it doesn't change the level). A ⚡ **Spike** (income more than doubled) is flagged so a human checks whether it's a one-off.

## Outreach plan and timing assumptions

- **Evidence and hook.** Hooks fire only from figures in the filings: strong growth; government contracts as 30%+ of income or up 20%+; trading income up 25% and £100k+; a new chair (18 months) or 2+ new trustees (12 months); 50+ staff or 200+ volunteers. "Costs outpacing income" is used in the call script only, as it's too sensitive for a cold email. The strongest hook opens email 1 and the second strongest opens the day-3 follow-up. With no signal, a neutral size/sector opener is used and labelled as such.
- **Careful wording.** Emails say what the data shows, then use "can", "may" or "often" for what that might mean. They never claim problems, technology, budgets, buying intent or named staff that the data doesn't contain. A test bans phrases like "usually means" and "your systems are".
- **Recipient.** A named published address (anna.barker@) gets "Dear Anna"; a generic one (info@) is addressed to the chair from the trustee list; otherwise "Dear Trustees". The register lists trustees, not staff, so the plan links to LinkedIn *searches* for the CEO, finance director and chair rather than scraping personal details (GDPR/PECR).
- **Timing is an estimate.** Charities usually plan next year's budget a few months before their year end. We know the year end from filings, not the actual budget cycle, so the plan says **"Estimate"** and shows the rule: by default the window is **6 to 2 months before year end**, configurable in *Your details and timing rule*. Output: whether now is inside the window, the recommended outreach period, and guidance to have a first conversation before the window closes.
- **Sequence.** Day 0 email (hook + mhance + Calendly) → Day 3 follow-up (second angle) → Day 5 call script (questions, voicemail) → Day 7 LinkedIn note (≤300 chars). Days are **working days**. Each step has a Done tick box; Outcome (Active, Replied, Meeting booked, Not interested, Paused) stops the sequence; Next action and due date update automatically.
- **Copy and export.** Each draft can be edited, opened in your email app, or copied from a copy box. "Download this plan" gives a Markdown file with everything; "Download every prospect's sequence" gives a CSV for mail merge or CRM import.

---

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
- **Peer benchmarks** come from the bulk snapshot (refreshed by re-running `build_dataset.py`; a weekly GitHub Action is included but hasn't been run).
- **Saved prospects** live in one local JSON file: single user, not shared, and reset on hosts with temporary disks such as Streamlit Cloud. Edits to a draft last for the session; the plan regenerates from data.
- **No staff contact data:** the register gives trustees and published contact details only.
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
app.py               Streamlit UI (4 tabs)
analysis.py          Financial rules: ordering, % change, status, up/flat/down, vs peers, hot, gaps, priority
outreach.py          Hooks, evidence, recipient, estimated timing, sequence, plan export
prospects.py         Saved prospects + settings (outreach.json), dedupe, persistence
data_sources.py      Charity Commission API client (cached, normalised) + bulk Snapshot
build_dataset.py     Bulk extract -> data/*.parquet
tests/               39 pytest tests
WALKTHROUGH.md       10–15 minute demo outline
pyproject.toml       ruff + pytest config
```

Data © Charity Commission for England and Wales, used under the Open Government Licence v3.0.
