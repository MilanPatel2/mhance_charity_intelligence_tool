# Walkthrough outline (10–15 minutes)

Before recording: run `streamlit run app.py`, open **My prospects** and fill in *Settings* at the bottom (your name, role and Calendly link). Remove any test prospects so the list starts clean.

## 1. The business problem (1 min)
mhance sells Microsoft Dynamics 365 to UK charities. Sales currently checks charities one by one on the Charity Commission site to work out who is growing, then writes outreach from scratch. That's slow, inconsistent, and the research and the outreach are disconnected. This tool makes it one flow: **search → understand → save → outreach plan → copy/export.**

## 2. A real search, start to finish (2 min)
- **Look up a charity** (the main page) → type `nacro` and press Enter → the summary appears straight away (best match; "pick another" list above it). Clear the search box to show it under *Recent searches*.
- Point out that everything the brief asks for is on one screen: name and number, total income and expenditure for 3 years with labelled trends, net surplus / deficit, why it's worth contacting, trustees, and **Add to prospects**. Then scroll to *More detail* for the chart, peer comparison and the Charity Commission / Companies House links.
- Then type a number, `202918` (Oxfam), to show search by registration number.

## 3. Financial trends and prospect reasoning (2–3 min)
- Nacro: **Total income £90.3m, +31.6% (+£21.7m) over 3 years, Income trend: Up**; expenditure the same way; **£139k deficit** (total income − total expenditure). Total income is the charity equivalent of revenue; income and expenditure are never added together.
- Explain the two layers: **up/flat/down** is the brief's indicator (±5% over 3 returns); **vs peers** adds context, because the typical charity grew ~9%, mostly inflation, so most read as "Up".
- **High priority**, with the reasons always visible: hot (+17.3% last year, the brief's 10% rule) **and** ahead of peers.
- Small charities: search `300765` (Pollyfield Community Association). Income +383%, but only **+£77k**: labelled *high percentage growth from a small base*, Low priority. Then on **Find new prospects**, show the size switch and the "Not shown: …" line, so nothing is hidden silently.
- Data you can trust: search `1162402` (Sickle Cell Care Manchester), which shows **Check first**. Its income jumps £86k → £88.9m in the Commission's own data, almost certainly a typo. Without the guard it was the top "hot prospect". Then `1207593` shows **◌ Under 3 yrs data**: labelled, not guessed.

## 4. Adding to outreach (1 min)
- Press **Add to prospects**; the button turns to *In your prospects* and the *My prospects* count goes up (duplicates are impossible).
- **Find new prospects:** filter **Area = Ealing**, **Priority = High**. Press **Add** on two charities (or **Add all on this page**). This is building a call list in seconds.

## 5. Hook, email and timing plan (2–3 min)
- **My prospects:** *Your next actions*, ordered overdue → due today → inside the estimated window → later. Replied or stopped prospects sit under *No action needed*. The first actionable prospect opens by itself.
- **The brief (five seconds):** *Why this account* (Nacro's growth, inside the £1m–£100m fit range), *Why now* ("Possible budget-planning window is open now", labelled an estimate, not confirmed intent), *Who* (aim for the Finance Director; published inbox and phone; the chair is a trustee, not a confirmed buyer), *Next* ("Send the first email", with **Done / Snooze a week / Not relevant**). The source line underneath separates reported, calculated and estimated.
- Open **View or edit the current email**: "Dear Anna" because the published inbox is anna.barker@. Facts from the filings, "can/may" for what they might mean, your Calendly link. Show **Open in my email app** and the copy box.
- Open a prospect whose window is months away (e.g. a 31 August year end): the action is **Research the Finance Director**, and the first email is planned for when the window opens. Mention the *early relationship-building* switch.
- Press **Done**: the follow-up becomes the current action. Point out the collapsed sections: why we prioritised it, later steps, activity and notes, more actions (download, regenerate, remove), and Settings at the bottom.

## 6. Technical and design choices (1–2 min)
- Streamlit for speed and a real UI for non-technical users.
- Live API for named charities, the free daily bulk extract only for register-wide filtering and peer benchmarks; no silent fallback.
- Rules, not an LLM, for outreach: every sentence traces to data, it's deterministic, and it's tested.
- Clean split: `data_sources` (API + normalisation), `analysis` (financial rules), `outreach` (plan), `prospects` (storage), `app` (UI only). 43 tests; ruff lint and format.

## 7. Trade-offs and rejected approaches (1 min)
- Absolute-only trends (inflation makes everything "Up") vs peers-only (drops the brief's indicator): kept both.
- A 0–100 AI score: rejected as false precision; explainable tiers instead.
- Scraping staff emails: rejected on GDPR/PECR grounds; LinkedIn search links instead.
- A database: unnecessary for a single-user prototype; JSON file now, Dynamics 365 in production.

## 8. Current limitations (1 min)
- The bulk file sometimes has fewer years than the API, so the prospect list can say "Under 3 yrs" where the live page shows a full trend.
- Saved prospects are single-user, in a local file.
- No staff contacts from the register.
- Budget timing is an estimate.
- England and Wales only.

## 9. Production readiness (1 min)
Write prospects and steps into **Dynamics 365** as leads and activities; Entra ID login; scheduled snapshot refresh; shared cache with retries; secrets in Key Vault; adoption metrics (prospects saved → meetings booked).

## 10. With more time (30 s)
An optional AI polishing layer on top of the rules (facts locked to the data), income-by-source filters across the whole register, and weekly "newly hot in your patch" alerts.
