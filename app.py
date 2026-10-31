"""mhance Charity Growth Finder.

Run:  streamlit run app.py
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import analysis as A
import outreach as O
from data_sources import APIError, LiveAPI, NotFound, Snapshot

st.set_page_config(page_title="Charity Growth Finder · mhance", page_icon="📈", layout="wide")

INCOME_FILTER = {  # filter on LATEST income (what they're worth to sales today)
    "Under £100k": (0, 1e5),
    "£100k–£500k": (1e5, 5e5),
    "£500k–£1m": (5e5, 1e6),
    "£1m–£5m": (1e6, 5e6),
    "£5m–£10m": (5e6, 1e7),
    "£10m–£25m": (1e7, 2.5e7),
    "£25m–£100m": (2.5e7, 1e8),
    "Over £100m": (1e8, float("inf")),
}
DEFAULT_BANDS = ["£1m–£5m", "£5m–£10m", "£10m–£25m", "£25m–£100m"]
KEY_FILE = Path(__file__).parent / "api_key.txt"
PLACEHOLDER = "paste-your-key-here"
MAX_LIST = 100
OUTREACH_FILE = Path(__file__).parent / "outreach.json"  # call list + your details, kept between sessions
OUTCOMES = ["Active", "Replied", "Meeting booked", "Not interested", "Paused"]


# ---------- data ----------
def api_key() -> str | None:
    """Key lookup order: api_key.txt -> Streamlit secrets (for deployment) -> env var."""
    if KEY_FILE.exists():
        k = KEY_FILE.read_text(encoding="utf-8-sig").strip().strip('"').strip("'")
        if k and k != PLACEHOLDER:
            return k
    try:
        k = st.secrets.get("CHARITY_API_KEY")
    except Exception:  # no secrets file
        k = None
    return k or os.getenv("CHARITY_API_KEY")


@st.cache_resource
def get_snapshot() -> Snapshot:
    return Snapshot()


@st.cache_resource
def get_api(key: str) -> tuple[LiveAPI, str | None]:
    api = LiveAPI(key)
    return api, api.check_key()


@st.cache_data(show_spinner="Working out market benchmarks across the register…")
def market() -> tuple[pd.DataFrame, dict]:
    base = A.base_table(get_snapshot().financials)
    return base, A.benchmarks(base)


@st.cache_data(show_spinner=False)
def prospect_table(band: float, hot: float) -> pd.DataFrame:
    base, bench = market()
    return get_snapshot().charities.merge(A.apply_trends(base, bench, band, hot), on="org_number", how="left")


@st.cache_data
def area_options() -> list[str]:
    c = get_snapshot().charities
    vals = pd.concat([c["local_authorities"].str.split(r" \| ").explode(), c["regions"].str.split(r" \| ").explode()])
    return sorted({x for x in vals.dropna() if x})


@st.cache_data
def sector_options() -> list[str]:
    s = get_snapshot().charities["sectors"].str.split(r" \| ").explode().dropna()
    return sorted({x for x in s if x})


# ---------- outreach call list (saved to outreach.json) ----------
def load_store() -> dict:
    try:
        data = json.loads(OUTREACH_FILE.read_text())
    except Exception:
        data = {}
    data.setdefault("settings", {"name": "", "role": "", "calendly": ""})
    data.setdefault("list", {})
    return data


def save_store() -> None:
    try:
        OUTREACH_FILE.write_text(json.dumps(st.session_state.store, indent=2, default=str))
    except OSError:
        pass  # read-only host: the list still works for this session


if "store" not in st.session_state:
    st.session_state.store = load_store()
STORE = st.session_state.store


def in_outreach(reg) -> bool:
    return str(int(reg)) in STORE["list"]


def add_to_outreach(items: list[tuple[int, str]]) -> int:
    added = 0
    for reg, name in items:
        if not in_outreach(reg):
            STORE["list"][str(int(reg))] = {"name": name, "added": date.today().isoformat(),
                                            "start": O.working_day(date.today()).isoformat(),
                                            "done": {}, "outcome": "Active", "notes": ""}
            added += 1
    save_store()
    return added


def _add_cb(items):
    # No st.toast here: callbacks can run inside the charity pop-up, where showing elements
    # crashes Streamlit's front end. Queue the message and show it on the next full run.
    n = add_to_outreach(items)
    st.session_state["_toast"] = f"Added {n} to your outreach list" if n else "Already in your outreach list"


if st.session_state.get("_toast"):
    st.toast(st.session_state.pop("_toast"), icon="📬")

SNAP = get_snapshot()
KEY = api_key()
API, API_PROBLEM = get_api(KEY) if KEY else (None, None)
_, BENCH = market()


def need_api() -> bool:
    """Single-charity features use the live API only. Explain clearly if it isn't available."""
    if API and not (API_PROBLEM and "401" in API_PROBLEM):
        return True
    if not KEY:
        st.warning("This tab uses the live Charity Commission API. Paste your API key into `api_key.txt` and restart the app.")
    else:
        st.error(f"Live API unavailable: {API_PROBLEM}")
    return False


# ---------- sidebar ----------
with st.sidebar:
    st.header("📈 Charity Growth Finder")
    st.caption("For mhance sales: spot UK charities that are growing (or shrinking) before you call.")
    if not KEY:
        st.warning("No API key: lookups are off. Paste your key into `api_key.txt` and restart.")
    elif API_PROBLEM:
        st.error(f"Live API problem: {API_PROBLEM}")
    else:
        st.success("Lookups: **live** Charity Commission API (cached 24h)")
    st.caption(f"Prospect search and market benchmarks: Commission bulk data, extract dated **{SNAP.extract_date}**")

    with st.expander("Rules & settings"):
        band = st.slider("'In line' band (± % around the peer median)", 0, 20, int(A.FLAT_BAND * 100)) / 100
        hot = st.slider("Hot prospect: income up more than (%) YoY", 0, 50, int(A.HOT_THRESHOLD * 100)) / 100
        st.markdown(
            f"- **Trend** compares a charity's income change over its last 3 annual returns with the **median for "
            f"charities of the same size** (its peer group = income 3 years ago). E.g. peers grew +8%: a charity that grew "
            f"more than +{8 + band * 100:.0f}% is ▲ Above peers, less than +{8 - band * 100:.0f}% is ▼ Below peers, "
            f"anything in between is ► In line (±{band:.0%}). Expenditure works the same way.\n"
            f"- **◌ Under 3 yrs data** / **◌ Base under £10k**: not enough history or too small a base to call a trend.\n"
            f"- **⚠ Check data**: income or expenditure changed more than {A.SUSPECT_RATIO}× in a year, usually a filing error.\n"
            f"- **🔥 Hot** = latest income up more than {hot:.0%} on the year before.\n"
            f"- **⚡ Spike** = income more than doubled in a year. Often a one-off, so check before calling.\n"
            f"- **Stale** = latest return ended over {A.STALE_MONTHS} months ago."
        )


# ---------- single-charity view ----------
def register_url(reg) -> str:
    return f"https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/{int(reg)}"


def companies_house_url(company_no) -> str | None:
    c = str(company_no or "").strip().upper()
    if not c or c in ("NONE", "NAN"):
        return None
    return f"https://find-and-update.company-information.service.gov.uk/company/{c.zfill(8) if c.isdigit() else c}"


def trend_metric(col, label: str, s: dict, field: str) -> None:
    trend = s[f"{field}_trend"]
    if s["status"] != A.OK or trend not in (A.ABOVE, A.INLINE, A.BELOW):
        col.metric(label, A.LABELS.get(trend, "–"))
        return
    peer = (s["peer"] or {}).get(field) or 0.0
    col.metric(label, A.LABELS[trend], f"{A.pct(s[f'{field}_change'])} vs {A.pct(peer)} for peers", delta_color="off",
               help=f"{field.title()} changed {A.pct(s[f'{field}_change'])} over its last 3 returns. "
                    f"Charities in its peer group ({s['size_band']} income 3 years ago) changed {A.pct(peer)} at the median.")


def render_charity(rec: dict, key_prefix: str = "") -> None:
    s = A.summarise(rec["financials"], BENCH, band=band, hot=hot)
    st.subheader(f"{rec['name']}  ·  #{rec['reg_number']}")
    tags = []
    if s["hot"]:
        tags.append(f":orange-badge[🔥 Hot prospect: income {A.pct(s['income_yoy'])} YoY]")
    if s["spike"]:
        tags.append(":violet-badge[⚡ Spike: income more than doubled, check if it's a one-off]")
    if s["status"] == A.CHECK:
        tags.append(":red-badge[⚠ Check data: possible filing error]")
    elif s["status"] != A.OK:
        tags.append(f":gray-badge[◌ {s['status']}]")
    if s["stale"]:
        tags.append(f":gray-badge[Stale: latest return ended {s['latest_period_end']}]")
    if s["status"] == A.OK and s["size_band"]:
        n = (s["peer"] or {}).get("n")
        tags.append(f":green-badge[Peer group: {s['size_band']} income 3 yrs ago" + (f" ({n:,} charities)]" if n else "]"))
    tags.append(f":blue-badge[Source: {rec['source']}]")
    st.markdown(" ".join(tags))
    b1, b2, b3, _ = st.columns([1, 1, 1, 2])
    b1.link_button("Charity Commission register ↗", register_url(rec["reg_number"]), width="stretch")
    ch = companies_house_url(rec["profile"].get("Company no."))
    if ch:
        b2.link_button("Companies House ↗", ch, width="stretch")
    if in_outreach(rec["reg_number"]):
        b3.button("✓ In outreach list", disabled=True, width="stretch", key=f"{key_prefix}in_{rec['reg_number']}")
    else:
        b3.button("📬 Add to outreach", type="primary", width="stretch", key=f"{key_prefix}add_{rec['reg_number']}",
                  on_click=_add_cb, args=([(rec["reg_number"], rec["name"])],))

    if not s["years"]:
        st.info("No financial returns on record. Usually a newly registered or very small charity.")
    else:
        if s["status"] != A.OK:
            (st.error if s["status"] == A.CHECK else st.info)(A.STATUS_HELP[s["status"]])
        latest = s["years"][-1]
        c1, c2, c3, c4 = st.columns(4)
        yoy = lambda f: (A.pct(latest.get(f"{f}_yoy"))
                         if latest.get(f"{f}_yoy") is not None and s["status"] != A.CHECK else None)
        c1.metric("Latest income", A.money(latest["income"]), yoy("income"))
        c2.metric("Latest expenditure", A.money(latest["expenditure"]), yoy("expenditure"), delta_color="off")
        trend_metric(c3, "Income trend (3 yrs)", s, "income")
        trend_metric(c4, "Expenditure trend (3 yrs)", s, "expenditure")
        if s["status"] == A.OK and s["peer"]:
            st.caption(f"Over its last 3 returns: income **{A.pct(s['income_change'])}**, expenditure **{A.pct(s['expenditure_change'])}**. "
                       f"Compared with **{s['peer']['n']:,} charities** that had **{s['size_band']}** income three years ago, "
                       f"whose median change was income {A.pct(s['peer']['income'])}, expenditure {A.pct(s['peer']['expenditure'])}.")

        left, right = st.columns([3, 2])
        with left:
            st.dataframe(pd.DataFrame([{
                "Year ending": str(y["period_end"])[:10],
                "Income": A.money(y["income"]),
                "Income YoY": A.pct(y.get("income_yoy")),
                "Expenditure": A.money(y["expenditure"]),
                "Expenditure YoY": A.pct(y.get("expenditure_yoy")),
                "Surplus / (deficit)": A.money((y["income"] or 0) - (y["expenditure"] or 0)),
            } for y in s["years"]]), hide_index=True, width="stretch")
        with right:
            chart = pd.DataFrame(s["all_years"]).assign(Year=lambda d: d["period_end"].astype(str).str[:7])
            chart = (chart.set_index("Year")[["income", "expenditure"]] / 1e6).rename(columns=str.title)
            st.bar_chart(chart, stack=False, height=260, color=["#2E6FD8", "#E8A33D"], y_label="£m")
            st.caption("All returns on record (up to 5 years), £m")

    tcol, pcol = st.columns([2, 3])
    tr = sorted(rec["trustees"], key=lambda t: (not t["is_chair"], t["name"] or ""))
    with tcol:
        st.markdown("**Trustees**")
        if tr:
            st.dataframe(pd.DataFrame([{"Name": t["name"], "Role": "Chair" if t["is_chair"] else "Trustee",
                                        "Appointed": t["appointed"] or "–"} for t in tr]),
                         hide_index=True, width="stretch", height=min(38 + 35 * len(tr), 300))
        else:
            st.caption("No trustees listed.")
    with pcol:
        st.markdown("**Profile**")
        for k, v in rec["profile"].items():
            if v not in (None, "", 0) and not (isinstance(v, float) and pd.isna(v)):
                st.markdown(f"**{k}:** {v}")

    peer = s["peer"] or {}
    export = pd.DataFrame([{
        "reg_number": rec["reg_number"], "name": rec["name"], "year_ending": str(y["period_end"])[:10],
        "income": y["income"], "income_yoy": y.get("income_yoy"), "expenditure": y["expenditure"],
        "expenditure_yoy": y.get("expenditure_yoy"), "status": s["status"], "size_band": s["size_band"],
        "income_change_3yr": s["income_change"], "peer_income_median_3yr": peer.get("income"),
        "income_trend_vs_peers": s["income_trend"], "expenditure_change_3yr": s["expenditure_change"],
        "peer_expenditure_median_3yr": peer.get("expenditure"), "expenditure_trend_vs_peers": s["expenditure_trend"],
        "hot_prospect": s["hot"], "spike": s["spike"],
        "trustees": "; ".join(t["name"] for t in tr), "website": rec["profile"].get("Website"),
    } for y in s["years"]])
    st.download_button("⬇ Download as CSV", export.to_csv(index=False), f"charity_{rec['reg_number']}.csv",
                       "text/csv", key=f"{key_prefix}dl_{rec['reg_number']}", on_click="ignore")


def show_lookup(reg: int, key_prefix: str) -> None:
    try:
        with st.spinner("Fetching from the Charity Commission…"):
            rec = API.lookup(reg)
        render_charity(rec, key_prefix)
    except NotFound as e:
        st.warning(str(e))
    except APIError as e:
        st.error(str(e))


@st.dialog("Charity details", width="large")
def charity_dialog(reg: int) -> None:
    show_lookup(reg, "d_")


def open_selected(event, numbers: list, names: list, state_key: str, can_add: bool = True) -> None:
    """Row ticks under a table.
    - Tick one row: that charity's page opens (once per tick, so changing a filter
      afterwards doesn't keep popping it up; the Open button re-opens it).
    - Tick several: nothing pops up; add them all to the outreach list in one go."""
    rows = event.selection.rows if event and event.selection else []
    if not rows:
        st.session_state[state_key] = None
        st.caption("👆 Tick a row to open that charity" + (", or tick several and add them to your outreach list." if can_add else "."))
        return
    picked = [(int(numbers[r]), names[r]) for r in rows]
    reg, name = picked[-1]
    c1, c2, _ = st.columns([1.2, 1.2, 2])
    if can_add:
        new = [p for p in picked if not in_outreach(p[0])]
        c1.button(f"📬 Add {len(new)} to outreach" if new else "✓ All in outreach list", disabled=not new,
                  type="primary", width="stretch", key=f"add_{state_key}", on_click=_add_cb, args=(new,))
    if c2.button(f"🔎 Open {O.nice_name(name)[:28]}", width="stretch", key=f"open_{state_key}"):
        charity_dialog(reg)
    elif len(picked) == 1 and st.session_state.get(state_key) != reg:
        st.session_state[state_key] = reg
        charity_dialog(reg)
    elif len(picked) > 1:
        st.session_state[state_key] = "multi"


def flags(df: pd.DataFrame) -> pd.Series:
    f = lambda col, sym: df[col].fillna(False).astype(bool).map({True: sym, False: ""})
    return f("hot", "🔥") + f("spike", "⚡") + (df["status"] == A.CHECK).map({True: "⚠", False: ""})


# ---------- tabs ----------
tab1, tab2, tab3, tab4 = st.tabs(["🔎 Look up a charity", "🎯 Find prospects", "📋 Check a list", "📬 Outreach"])

with tab1:
    if need_api():
        q = st.text_input("Charity name or registration number", placeholder="e.g. Oxfam, or 202918").strip()
        if q.isdigit():
            show_lookup(int(q), "l_")
        elif q:
            try:
                with st.spinner("Searching…"):
                    hits = API.search(q)
                    inc = API.latest_incomes([h["reg_number"] for h in hits[:60]]) if hits else {}
            except APIError as e:
                st.error(str(e))
                hits = []
            if hits:
                hits = sorted(hits, key=lambda h: -(inc.get(h["reg_number"]) or 0))
                st.caption(f"{len(hits)} registered match(es), largest first. Click a row to open the charity.")
                results = pd.DataFrame({
                    "Charity": [h["name"] for h in hits],
                    "Number": [h["reg_number"] for h in hits],
                    "Latest income £m": [(inc.get(h["reg_number"]) or float("nan")) / 1e6 for h in hits],
                    "Registered": [h["registered_on"] for h in hits],
                    "Register": [register_url(h["reg_number"]) for h in hits],
                })
                ev = st.dataframe(
                    results, hide_index=True, width="stretch", on_select="rerun",
                    selection_mode="single-row", key=f"search_{q.lower()}",
                    height=min(38 + 35 * len(results), 420),
                    column_config={
                        "Number": st.column_config.NumberColumn(format="%d"),
                        "Latest income £m": st.column_config.NumberColumn(format="£%.2fm"),
                        "Register": st.column_config.LinkColumn(display_text="View on register ↗"),
                    })
                open_selected(ev, results["Number"].tolist(), results["Charity"].tolist(), "search_open", can_add=False)
            elif q:
                st.warning(f"No registered charities match “{q}”. Try a shorter name or the registration number.")

with tab2:
    st.caption(f"Filter the whole register to build a call list (bulk data, {SNAP.extract_date}). "
               "Pick a row to load full live details.")
    df = prospect_table(band, hot)
    f1, f2, f3 = st.columns(3)
    areas = f1.multiselect("Area (local authority or region)", area_options(), placeholder="Anywhere")
    sectors = f2.multiselect("Sector", sector_options(), placeholder="Any sector")
    bands = f3.multiselect("Latest income", list(INCOME_FILTER), default=DEFAULT_BANDS)
    g1, g2, g3, g4 = st.columns([1.3, 1, 1, 1.7])
    trend_f = g1.selectbox("Income trend", ["Any", A.ABOVE, A.INLINE, A.BELOW, A.NEW, A.CHECK],
                           format_func=lambda x: A.LABELS.get(x, x))
    with g2:
        hot_only = st.checkbox("🔥 Hot prospects only")
        hide_spikes = st.checkbox("Hide ⚡ spikes")
    with g3:
        hide_stale = st.checkbox("Hide stale filers", value=True)
        hide_unreliable = st.checkbox("Hide ⚠ / ◌ (no reliable trend)")
    name_f = g4.text_input("Name contains", placeholder="optional")

    m = pd.Series(True, index=df.index)
    if areas:
        pat = "|".join(rf"(?:^|\| ){re.escape(a)}(?: \||$)" for a in areas)
        m &= df["local_authorities"].str.contains(pat, regex=True) | df["regions"].str.contains(pat, regex=True)
    if sectors:
        m &= df["sectors"].str.contains("|".join(re.escape(s) for s in sectors), regex=True)
    if bands:
        inc = df["latest_income"].fillna(-1)
        m &= pd.concat([(inc >= lo) & (inc < hi) for lo, hi in (INCOME_FILTER[b] for b in bands)], axis=1).any(axis=1)
    if trend_f != "Any":
        m &= df["income_trend"] == trend_f
    if hot_only:
        m &= df["hot"].fillna(False).astype(bool)
    if hide_spikes:
        m &= ~df["spike"].fillna(False).astype(bool)
    if hide_stale:
        m &= ~df["stale"].fillna(True).astype(bool)
    if hide_unreliable:
        m &= df["status"] == A.OK
    if name_f:
        m &= df["name"].str.contains(name_f, case=False, regex=False)

    # Hot first, then biggest (better Dynamics fit). Unreliable trends sink to the bottom.
    res = df[m].assign(_ok=df["status"] == A.OK, _hot=df["hot"].fillna(False).astype(bool)) \
               .sort_values(["_ok", "_hot", "latest_income"], ascending=False, na_position="last")
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Charities", f"{len(res):,}")
    k2.metric("🔥 Hot", f"{int(res['_hot'].sum()):,}")
    k3.metric("▲ Above peers", f"{int((res['income_trend'] == A.ABOVE).sum()):,}")
    k4.metric("▼ Below peers", f"{int((res['income_trend'] == A.BELOW).sum()):,}")
    k5.metric("⚠ / ◌ No reliable trend", f"{int((~res['_ok']).sum()):,}")

    show = pd.DataFrame({
        "Flags": flags(res),
        "Charity": res["name"],
        "Number": res["reg_number"],
        "Latest income £m": res["latest_income"] / 1e6,
        "Income YoY %": res["income_yoy"].where(res["status"] != A.CHECK) * 100,
        "Income 3-yr %": res["income_change"] * 100,
        "Peer median 3-yr %": res["peer_income_median"] * 100,
        "Income trend": res["income_trend"].map(A.LABELS),
        "Expenditure trend": res["expenditure_trend"].map(A.LABELS),
        "Peer group (income 3 yrs ago)": res["size_band"],
        "Year ending": res["latest_period_end"],
        "Sectors": res["sectors"],
        "Website": res["web"],
        "Register": res["reg_number"].map(register_url),
    })
    MAX = 2000
    ev = st.dataframe(
        show.head(MAX), hide_index=True, width="stretch", height=420,
        on_select="rerun", selection_mode="multi-row", key="prospects",
        column_config={
            "Number": st.column_config.NumberColumn(format="%d"),
            "Latest income £m": st.column_config.NumberColumn(format="£%.2fm"),
            "Income YoY %": st.column_config.NumberColumn(format="%+.1f%%"),
            "Income 3-yr %": st.column_config.NumberColumn(format="%+.1f%%"),
            "Peer median 3-yr %": st.column_config.NumberColumn(format="%+.1f%%"),
            "Website": st.column_config.LinkColumn(display_text=r"https?://(?:www\.)?([^/]+).*"),
            "Register": st.column_config.LinkColumn(display_text="View ↗"),
        },
    )
    if need_api():
        top = show.head(MAX)
        open_selected(ev, top["Number"].tolist(), top["Charity"].tolist(), "prospect_open")
    if len(res) > MAX:
        st.caption(f"Showing the top {MAX:,} of {len(res):,}. The CSV has all of them.")
    out = res[["reg_number", "name", "latest_income", "latest_period_end", "status", "size_band",
               "income_y1", "income_y2", "income_y3", "income_yoy", "income_change", "peer_income_median", "income_trend",
               "expenditure_y1", "expenditure_y2", "expenditure_y3", "expenditure_change", "peer_expenditure_median",
               "expenditure_trend", "hot", "spike", "stale", "sectors", "local_authorities", "regions",
               "postcode", "web", "email", "phone"]]
    st.download_button(f"⬇ Download {len(res):,} charities as CSV", out.to_csv(index=False), "charity_prospects.csv", "text/csv")

    with st.expander("📊 Market benchmarks: what 'in line with peers' means"):
        st.caption("Median 3-year change for up-to-date charities with a reliable trend, grouped by income three years ago. "
                   "Each charity's trend is measured against its own row.")
        st.dataframe(pd.DataFrame([{"Peer group (income 3 yrs ago)": lbl, "Charities": BENCH[lbl]["n"],
                                    "Median income change": A.pct(BENCH[lbl]["income"]),
                                    "Median expenditure change": A.pct(BENCH[lbl]["expenditure"])}
                                   for _, _, lbl in A.SIZE_BANDS if lbl in BENCH]),
                     hide_index=True, width="stretch")

with tab3:
    st.caption(f"Paste up to {MAX_LIST} charity numbers from a CRM export or spreadsheet (any separator). "
               "Each one is checked live against the Charity Commission API.")
    if need_api():
        txt = st.text_area("Charity numbers", placeholder="202918, 1089464\n220949", height=120)
        nums = list(dict.fromkeys(int(n) for n in re.findall(r"\d{6,8}", txt)))[:MAX_LIST]
        if nums:
            rows, missing, errors = [], [], []
            bar = st.progress(0.0, text="Checking…")
            for i, n in enumerate(nums):
                try:
                    rec = API.lookup(n)
                    s = A.summarise(rec["financials"], BENCH, band=band, hot=hot)
                    latest = s["years"][-1] if s["years"] else {}
                    rows.append({"status": s["status"], "hot": s["hot"], "spike": s["spike"], "name": rec["name"],
                                 "reg_number": n, "latest_income": latest.get("income"),
                                 "latest_expenditure": latest.get("expenditure"), "income_yoy": s["income_yoy"],
                                 "income_change_3yr": s["income_change"], "peer_income_median_3yr": (s["peer"] or {}).get("income"),
                                 "income_trend": s["income_trend"], "expenditure_trend": s["expenditure_trend"],
                                 "size_band": s["size_band"], "year_ending": str(s["latest_period_end"] or "")[:10],
                                 "website": rec["profile"].get("Website")})
                except NotFound:
                    missing.append(n)
                except APIError as e:
                    errors.append(f"{n}: {e}")
                bar.progress((i + 1) / len(nums), text=f"Checked {i + 1} of {len(nums)}")
            bar.empty()
            found = pd.DataFrame(rows)
            if not found.empty:
                ev3 = st.dataframe(pd.DataFrame({
                    "Flags": flags(found), "Charity": found["name"], "Number": found["reg_number"],
                    "Latest income": found["latest_income"].map(A.money),
                    "Income YoY": found["income_yoy"].where(found["status"] != A.CHECK).map(A.pct),
                    "Income 3-yr": found["income_change_3yr"].map(A.pct),
                    "Peer median": found["peer_income_median_3yr"].map(A.pct),
                    "Income trend": found["income_trend"].map(A.LABELS),
                    "Expenditure trend": found["expenditure_trend"].map(A.LABELS),
                    "Peer group": found["size_band"],
                    "Year ending": found["year_ending"],
                    "Register": found["reg_number"].map(register_url),
                }), hide_index=True, width="stretch", on_select="rerun", selection_mode="multi-row",
                    key="list_table",
                    column_config={"Number": st.column_config.NumberColumn(format="%d"),
                                   "Register": st.column_config.LinkColumn(display_text="View ↗")})
                open_selected(ev3, found["reg_number"].tolist(), found["name"].tolist(), "list_open")
                st.download_button("⬇ Download as CSV", found.to_csv(index=False), "charity_list_check.csv", "text/csv")
            if missing:
                st.warning(f"Not found on the register: {', '.join(map(str, missing))}")
            for e in errors:
                st.error(e)

# ---------- outreach ----------
CHANNEL_ICON = {"email": "✉️", "call": "📞", "linkedin": "💼"}


@st.cache_data(ttl=3600, show_spinner=False)
def cached_lookup(reg: int) -> dict:
    return API.lookup(reg)


def _save_settings():
    for k in ("name", "role", "calendly"):
        STORE["settings"][k] = st.session_state.get(f"set_{k}", "").strip()
    save_store()


def _set_item(reg: str, field: str, widget_key: str):
    STORE["list"][reg][field] = st.session_state[widget_key]
    if field == "start":
        STORE["list"][reg][field] = st.session_state[widget_key].isoformat()
    save_store()


def _set_done(reg: str, day: int, widget_key: str):
    STORE["list"][reg]["done"][str(day)] = st.session_state[widget_key]
    save_store()


def _remove(reg: str):
    STORE["list"].pop(reg, None)
    save_store()
    st.session_state.pop("out_table", None)


def _reset_text(reg: str):
    for k in [k for k in st.session_state.keys() if k.startswith(f"txt_{reg}_")]:
        del st.session_state[k]


def next_step(item: dict, plan: dict) -> tuple[str, date | None]:
    if item["outcome"] != "Active":
        return item["outcome"], None
    for stp in plan["steps"]:
        if not item["done"].get(str(stp["day"])):
            return f"{CHANNEL_ICON[stp['channel']]} {stp['title']}", stp["date"]
    return "Sequence complete", None


with tab4:
    st.caption("Your call list. Each charity gets a 4-step sequence built from its own figures: "
               "first email with your Calendly link, day-3 follow-up, day-5 phone call, day-7 LinkedIn. "
               "Everything is a draft for you to edit; nothing is sent automatically.")
    if need_api():
        cfg = STORE["settings"]
        with st.expander("✍️ Your details (used in every message)", expanded=not (cfg.get("name") and cfg.get("calendly"))):
            s1, s2, s3 = st.columns(3)
            s1.text_input("Your name", cfg.get("name", ""), key="set_name", on_change=_save_settings)
            s2.text_input("Your role", cfg.get("role", ""), key="set_role", on_change=_save_settings,
                          placeholder="e.g. Business Development Manager")
            s3.text_input("Calendly link", cfg.get("calendly", ""), key="set_calendly", on_change=_save_settings,
                          placeholder="https://calendly.com/your-name/20min")

        if not STORE["list"]:
            st.info("Your outreach list is empty. In **Find prospects** or **Check a list**, tick charities and press "
                    "**📬 Add to outreach**, or open any charity and press **📬 Add to outreach**.")
        else:
            today = date.today()
            plans, rows = {}, []
            with st.spinner("Building outreach plans from live Charity Commission data…"):
                for reg, item in STORE["list"].items():
                    try:
                        rec = cached_lookup(int(reg))
                    except (APIError, NotFound) as e:
                        rows.append({"reg": reg, "Charity": item["name"], "Hook": f"Couldn't load: {e}"})
                        continue
                    s = A.summarise(rec["financials"], BENCH, band=band, hot=hot)
                    plan = O.build_plan(rec, s, cfg, date.fromisoformat(item["start"]), today)
                    plans[reg] = (rec, s, plan)
                    step, due = next_step(item, plan)
                    rows.append({
                        "reg": reg,
                        "Flags": ("🔥" if s["hot"] else "") + ("⚡" if s["spike"] else "") + ("⚠" if s["status"] == A.CHECK else ""),
                        "Charity": plan["contact"]["charity"],
                        "Hook": plan["primary"]["title"],
                        "Email to": plan["contact"]["to"]["who"],
                        "Email": plan["contact"]["email"] or "–",
                        "Phone": plan["contact"]["phone"] or "–",
                        "Next step": step,
                        "Due": due,
                        "Overdue": bool(due and due < today),
                        "Outcome": item["outcome"],
                    })
            table = pd.DataFrame(rows)
            for col in ("Outcome", "Due", "Flags", "Email to", "Email", "Phone", "Next step"):
                if col not in table:
                    table[col] = None
            table["Outcome"] = table["Outcome"].fillna("Active")
            active = table[table["Outcome"] == "Active"]
            fmt_day = lambda d: f"{d:%a} {d.day} {d:%b}"
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("In outreach list", len(table))
            m2.metric("Active sequences", len(active))
            m3.metric("Due today or overdue", sum(isinstance(d, date) and d <= today for d in active["Due"]))
            m4.metric("📅 Meetings booked", int((table["Outcome"] == "Meeting booked").sum()))

            show_cols = ["Flags", "Charity", "Hook", "Email to", "Email", "Phone", "Next step", "Due", "Outcome"]
            due_txt = table["Due"].map(lambda d: (fmt_day(d) + (" ⚠ overdue" if d < today else "")) if isinstance(d, date) else "–")
            ev = st.dataframe(table[show_cols].assign(Due=due_txt),
                              hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row",
                              key="out_table", height=min(38 + 35 * len(table), 380))
            sel = ev.selection.rows if ev and ev.selection else []
            reg = table.iloc[sel[0]]["reg"] if sel else table.iloc[0]["reg"]
            if not sel:
                st.caption("👆 Click a row to work on that charity. Showing the first one.")

            # export every step for every charity (for mail merge / CRM import)
            export = [{"reg_number": r, "charity": p[2]["contact"]["charity"], "outcome": STORE["list"][r]["outcome"],
                       "day": stp["day"], "date": stp["date"], "channel": stp["channel"], "to": stp["to"],
                       "subject": stp["subject"], "message": stp["body"],
                       "done": STORE["list"][r]["done"].get(str(stp["day"]), False)}
                      for r, p in plans.items() for stp in p[2]["steps"]]
            st.download_button("⬇ Download all sequences as CSV", pd.DataFrame(export).to_csv(index=False),
                               "outreach_sequences.csv", "text/csv")

            if reg in plans:
                rec, s, plan = plans[reg]
                item = STORE["list"][reg]
                c = plan["contact"]
                st.divider()
                h1, h2, h3, h4 = st.columns([3, 1.3, 1.3, 1])
                h1.subheader(f"{c['charity']}  ·  #{reg}")
                h2.selectbox("Outcome", OUTCOMES, index=OUTCOMES.index(item["outcome"]), key=f"out_{reg}",
                             on_change=_set_item, args=(reg, "outcome", f"out_{reg}"))
                h3.date_input("Sequence starts", date.fromisoformat(item["start"]), key=f"start_{reg}",
                              on_change=_set_item, args=(reg, "start", f"start_{reg}"), format="DD/MM/YYYY")
                h4.write("")
                h4.button("🗑 Remove", key=f"rm_{reg}", on_click=_remove, args=(reg,), width="stretch")
                if item["outcome"] != "Active":
                    st.info(f"Sequence stopped: **{item['outcome']}**. Set the outcome back to Active to carry on.")

                k1, k2, k3 = st.columns(3)
                with k1:
                    st.markdown("**Who to contact**")
                    st.markdown(f"Email to: **{c['to']['who']}**")
                    if c["email"]:
                        st.markdown(f"✉️ [{c['email']}](mailto:{c['email']})")
                    if c["phone"]:
                        st.markdown(f"📞 [{c['phone']}](tel:{c['phone'].replace(' ', '')})")
                    if c["website"]:
                        site = c["website"] if c["website"].startswith("http") else f"https://{c['website']}"
                        st.markdown(f"🌐 [{c['website']}]({site})")
                    if c["chair"]:
                        st.caption(f"Chair: {c['chair']['full']}")
                with k2:
                    st.markdown("**Find the decision-maker**")
                    st.caption(f"The register lists trustees, not staff. The buyer is usually the {c['decision_maker']}.")
                    st.link_button("LinkedIn: chief executive ↗", c["linkedin_ceo"], width="stretch")
                    st.link_button("LinkedIn: finance director ↗", c["linkedin_finance"], width="stretch")
                    if c["linkedin_chair"]:
                        st.link_button("LinkedIn: the chair ↗", c["linkedin_chair"], width="stretch")
                with k3:
                    st.markdown("**Why and when**")
                    for i, hk in enumerate(plan["hooks"]):
                        if hk["key"] == "fallback" and i:
                            continue
                        used = ("✉️ Email 1" if hk is plan["primary"] else "✉️ Email 2" if hk is plan["secondary"]
                                else "📞 Call only" if not hk["email_safe"] else "📞 Call")
                        st.markdown(f"- **{hk['title']}** · {used}")
                    (st.success if plan["timing"]["now"] else st.info)(plan["timing"]["text"])

                tcol1, tcol2 = st.columns([4, 1])
                tcol1.markdown("**Sequence**")
                tcol2.button("↺ Regenerate drafts", key=f"regen_{reg}", on_click=_reset_text, args=(reg,),
                             help="Throw away your edits and rebuild the messages (e.g. after changing your details).",
                             width="stretch")
                if not (cfg.get("name") and cfg.get("calendly")):
                    st.warning("Add your name and Calendly link in **Your details** above so the drafts are ready to send.")
                for stp in plan["steps"]:
                    d = stp["day"]
                    done = item["done"].get(str(d), False)
                    late = (not done) and stp["date"] < today and item["outcome"] == "Active"
                    label = (f"{'✅' if done else CHANNEL_ICON[stp['channel']]}  Day {d} · {fmt_day(stp['date'])} · {stp['title']}"
                             + ("  ⚠ overdue" if late else ""))
                    with st.expander(label, expanded=not done and item["outcome"] == "Active" and d == next(
                            (x["day"] for x in plan["steps"] if not item["done"].get(str(x["day"]))), -1)):
                        st.checkbox("Done", value=done, key=f"done_{reg}_{d}", on_change=_set_done, args=(reg, d, f"done_{reg}_{d}"))
                        if stp["channel"] == "email":
                            to = st.text_input("To", stp["to"] or "", key=f"txt_{reg}_{d}_to")
                            subj = st.text_input("Subject", stp["subject"], key=f"txt_{reg}_{d}_subj")
                            body = st.text_area("Message", stp["body"], key=f"txt_{reg}_{d}_body", height=330)
                            st.link_button("✉️ Open in my email app", O.mailto(to, subj, body))
                        elif stp["channel"] == "call":
                            st.text_area("Call script (add your notes)", stp["body"], key=f"txt_{reg}_{d}_body", height=380)
                            if c["phone"]:
                                st.link_button(f"📞 Call {c['phone']}", f"tel:{c['phone'].replace(' ', '')}")
                        else:
                            note = st.text_area("Connection note", stp["body"], key=f"txt_{reg}_{d}_body", height=110)
                            n = len(note)
                            (st.caption if n <= O.LINKEDIN_LIMIT else st.error)(f"{n}/{O.LINKEDIN_LIMIT} characters (LinkedIn's limit for a connection note)")
                            l1, l2 = st.columns(2)
                            if c["linkedin_chair"]:
                                l1.link_button(f"Find {c['chair']['full']} on LinkedIn ↗", c["linkedin_chair"], width="stretch")
                            l2.link_button("Find their chief executive ↗", c["linkedin_ceo"], width="stretch")
