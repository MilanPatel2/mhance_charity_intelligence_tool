"""mhance Charity Growth Finder.

Run:  streamlit run app.py
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

import pandas as pd
import streamlit as st

import analysis as A
import outreach as O
from data_sources import APIError, LiveAPI, NotFound, Snapshot
from prospects import OUTCOMES, ProspectStore

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
OUTREACH_FILE = Path(__file__).parent / "outreach.json"  # saved prospects + your details, kept between sessions


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


@st.cache_data(show_spinner="Preparing the prospect list (first load only)…")
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


# ---------- saved prospects (prospects.py -> outreach.json) ----------
if "store" not in st.session_state:
    st.session_state.store = ProspectStore(OUTREACH_FILE)
STORE: ProspectStore = st.session_state.store


def in_outreach(reg) -> bool:
    return reg in STORE


def _add_cb(items):
    # No st.toast here: callbacks can run inside the charity pop-up, where showing elements
    # crashes Streamlit's front end. Queue the message and show it on the next full run.
    n = STORE.add(items, O.working_day(date.today()))
    st.session_state["_toast"] = (
        f"Saved {n} prospect{'s' if n != 1 else ''}. Find {'them' if n != 1 else 'it'} in ⭐ My prospects." if n else "Already saved as a prospect"
    )


if st.session_state.get("_toast"):
    st.toast(st.session_state.pop("_toast"), icon="⭐")

SNAP = get_snapshot()
KEY = api_key()
API, API_PROBLEM = get_api(KEY) if KEY else (None, None)
_, BENCH = market()
_d = pd.Timestamp(SNAP.extract_date) if SNAP.extract_date else None
LIST_DATE = f"{_d.day} {_d:%B %Y}" if _d is not None else "unknown"


def need_api() -> bool:
    """Single-charity features use the live Charity Commission data. Explain plainly if it isn't available."""
    if API and not (API_PROBLEM and "401" in API_PROBLEM):
        return True
    if not KEY:
        st.warning(
            "Live charity look-ups aren't switched on yet. Whoever set up this tool needs to add the Charity Commission "
            "access key (see *API key* in the README). **🎯 Find new prospects** still works in the meantime."
        )
    else:
        st.error(f"Can't get data from the Charity Commission right now. {API_PROBLEM} **🎯 Find new prospects** still works.")
    return False


PEER_WORDS = {A.ABOVE: "ahead of", A.INLINE: "in line with", A.BELOW: "behind"}
PEER_SHORT = {A.ABOVE: "▲ ahead of", A.INLINE: "► in line with", A.BELOW: "▼ behind"}


# ---------- sidebar ----------
with st.sidebar:
    st.header("📈 Charity Growth Finder")
    st.caption("For the mhance sales team: find UK charities that are growing, and get in touch at the right time.")
    if not KEY:
        st.warning("Live look-ups are off (no Charity Commission key set up).")
    elif API_PROBLEM:
        st.error(f"Can't reach the Charity Commission: {API_PROBLEM}")
    else:
        st.success("✅ Live data from the Charity Commission")
    st.caption(f"Prospect list last updated **{LIST_DATE}** from the Charity Commission's daily download.")

    with st.expander("ℹ️ What the labels mean"):
        st.markdown(
            "- **▲ Up / ► Flat / ▼ Down**: compares the oldest and newest of the charity's last 3 yearly accounts. "
            "A change of more than 5% counts as up or down.\n"
            "- **Similar charities**: charities that were the same size 3 years ago. Shows whether this one is growing "
            "faster or slower than normal for its size.\n"
            "- **🔥 Hot prospect**: income up more than 10% on the year before.\n"
            "- **Priority** 🟢 High = hot *and* growing faster than similar charities · 🟡 Medium = one of the two · "
            "⚪ Low = neither, or not enough history, or accounts overdue · 🔴 Check first = the figures look like a typo "
            "in the official records.\n"
            "- **⚡ Spike**: income more than doubled in a year, often a one-off such as a legacy.\n"
            "- **Overdue**: the latest accounts are more than 22 months old.\n"
            "- **Financial year**: charities' accounting years end on different dates, so we use their last 3 sets of accounts."
        )
        st.caption("Adjust the rules")
        band = st.slider("A change counts as up/down above (±%)", 0, 20, int(A.FLAT_BAND * 100)) / 100
        hot = st.slider("Hot prospect: income up more than (%) on the year before", 0, 50, int(A.HOT_THRESHOLD * 100)) / 100


# ---------- single charity ----------
def register_url(reg) -> str:
    return f"https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/{int(reg)}"


def companies_house_url(company_no) -> str | None:
    c = str(company_no or "").strip().upper()
    if not c or c in ("NONE", "NAN"):
        return None
    return f"https://find-and-update.company-information.service.gov.uk/company/{c.zfill(8) if c.isdigit() else c}"


def trend_metric(col, label: str, s: dict, field: str) -> None:
    """Value = the brief's up / flat / down (±5% over 3 accounts). Underneath = how that compares with similar charities."""
    trend, direction = s[f"{field}_trend"], s[f"{field}_direction"]
    if s["status"] != A.OK or not direction:
        col.metric(label, A.LABELS.get(trend, "–"), help=A.STATUS_HELP.get(s["status"]))
        return
    peer = (s["peer"] or {}).get(field) or 0.0
    col.metric(
        label,
        f"{A.LABELS[direction]} {A.pct(s[f'{field}_change'])}",
        f"{PEER_WORDS[trend]} similar charities ({A.pct(peer)})",
        delta_color="off",
        delta_arrow="off",
        help=f"Compares the oldest and newest of the last 3 yearly accounts; a change of more than ±{band:.0%} counts as up or down. "
        f"Similar charities = the {s['peer']['n']:,} charities with {s['size_band']} income 3 years ago; their typical change was {A.pct(peer)}.",
    )


def save_button(container, reg: int, name: str, key: str, label: str = "⭐ Save as prospect") -> None:
    if in_outreach(reg):
        container.button("✓ Saved as prospect", disabled=True, width="stretch", key=f"{key}_saved")
    else:
        container.button(label, type="primary", width="stretch", key=key, on_click=_add_cb, args=([(reg, name)],))


def render_charity(rec: dict, key_prefix: str = "") -> None:
    s = A.summarise(rec["financials"], BENCH, band=band, hot=hot)
    pr = A.priority(s)
    reg = rec["reg_number"]
    st.subheader(O.nice_name(rec["name"]))
    st.caption(f"Registered charity number **{reg}** · Source: Charity Commission (live), {date.today().day} {date.today():%b %Y}")

    colour = {A.HIGH: "green", A.MEDIUM: "orange", A.LOW: "gray", A.CHECK_FIRST: "red"}[pr["level"]]
    tags = [f":{colour}-badge[{A.PRIORITY_LABELS[pr['level']]} priority]"]
    if s["hot"]:
        tags.append(f":orange-badge[🔥 Hot prospect: income {A.pct(s['income_yoy'])} in the year to {str(s['latest_period_end'])[:7]}]")
    if s["spike"]:
        tags.append(":violet-badge[⚡ Income more than doubled: check if it's a one-off]")
    if s["status"] == A.CHECK:
        tags.append(":red-badge[⚠ Figures look wrong in the official records]")
    elif s["status"] != A.OK:
        tags.append(f":gray-badge[◌ {s['status']}]")
    if s["stale"]:
        tags.append(f":gray-badge[Accounts overdue: latest year ended {s['latest_period_end']}]")
    st.markdown(" ".join(tags))

    b1, b2, b3, _ = st.columns([1.2, 1.2, 1, 1.6])
    save_button(b1, reg, rec["name"], f"{key_prefix}add_{reg}")
    b2.link_button("Charity Commission page ↗", register_url(reg), width="stretch")
    ch = companies_house_url(rec["profile"].get("Company no."))
    if ch:
        b3.link_button("Companies House ↗", ch, width="stretch")
    if in_outreach(reg):
        st.caption("Saved. Open **⭐ My prospects** for the outreach plan and draft email.")

    if not s["years"]:
        st.info("No accounts on record yet. This is usually a newly registered or very small charity.")
    else:
        if s["status"] != A.OK:
            (st.error if s["status"] == A.CHECK else st.info)(A.STATUS_HELP[s["status"]])
        latest = s["years"][-1]
        c1, c2, c3, c4 = st.columns(4)
        yoy = lambda f: f"{A.pct(latest.get(f'{f}_yoy'))} on year before" if latest.get(f"{f}_yoy") is not None and s["status"] != A.CHECK else None
        c1.metric("Income, latest year", A.money(latest["income"]), yoy("income"), help=f"Year ending {latest['period_end']}")
        c2.metric("Expenditure, latest year", A.money(latest["expenditure"]), yoy("expenditure"), delta_color="off")
        trend_metric(c3, "Income over 3 years", s, "income")
        trend_metric(c4, "Expenditure over 3 years", s, "expenditure")
        if s["gaps"]:
            st.warning(
                "A year's accounts are missing: "
                + "; ".join(f"nothing filed between {a} and {b}" for a, b in s["gaps"])
                + ". We show only what's on record; nothing has been filled in."
            )
        with st.expander(f"💡 Why this charity is {pr['level'].lower()} priority"):
            for r in pr["reasons"]:
                st.markdown(f"- {r}")

        left, right = st.columns([3, 2])
        with left:
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "Year ending": str(y["period_end"])[:10],
                            "Income": A.money(y["income"]),
                            "vs year before": A.pct(y.get("income_yoy")),
                            "Expenditure": A.money(y["expenditure"]),
                            "vs year before ": A.pct(y.get("expenditure_yoy")),
                            "Income − expenditure": A.money((y["income"] or 0) - (y["expenditure"] or 0)),
                        }
                        for y in s["years"]
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
            st.caption('Last 3 yearly accounts. "vs year before" compares each year with the previous year\'s accounts.')
        with right:
            chart = pd.DataFrame(s["all_years"]).assign(Year=lambda d: d["period_end"].astype(str).str[:7])
            chart = (chart.set_index("Year")[["income", "expenditure"]] / 1e6).rename(columns=str.title)
            st.bar_chart(chart, stack=False, height=240, color=["#1F5FBF", "#E8A33D"], y_label="£m")
            st.caption("Every year on record (up to 5), £ millions")

    tcol, pcol = st.columns([2, 3])
    tr = sorted(rec["trustees"], key=lambda t: (not t["is_chair"], t["name"] or ""))
    with tcol:
        st.markdown("**Trustees (the charity's board)**")
        if tr:
            st.dataframe(
                pd.DataFrame([{"Name": t["name"], "Role": "Chair" if t["is_chair"] else "Trustee", "Since": t["appointed"] or "–"} for t in tr]),
                hide_index=True,
                width="stretch",
                height=min(38 + 35 * len(tr), 280),
            )
        else:
            st.caption("The Charity Commission doesn't list any trustees for this charity.")
    with pcol:
        st.markdown("**Contact details and profile**")
        for k, v in rec["profile"].items():
            if v not in (None, "", 0) and not (isinstance(v, float) and pd.isna(v)):
                st.markdown(f"**{k}:** {v}")

    peer = s["peer"] or {}
    export = pd.DataFrame(
        [
            {
                "reg_number": reg,
                "name": rec["name"],
                "year_ending": str(y["period_end"])[:10],
                "income": y["income"],
                "income_vs_year_before": y.get("income_yoy"),
                "expenditure": y["expenditure"],
                "expenditure_vs_year_before": y.get("expenditure_yoy"),
                "income_direction_3yr": s["income_direction"],
                "income_change_3yr": s["income_change"],
                "similar_charities_income_change_3yr": peer.get("income"),
                "expenditure_direction_3yr": s["expenditure_direction"],
                "expenditure_change_3yr": s["expenditure_change"],
                "priority": pr["level"],
                "hot_prospect": s["hot"],
                "trustees": "; ".join(t["name"] for t in tr),
                "website": rec["profile"].get("Website"),
            }
            for y in s["years"]
        ]
    )
    st.download_button(
        "⬇ Download these figures (CSV)",
        export.to_csv(index=False),
        f"charity_{reg}.csv",
        "text/csv",
        key=f"{key_prefix}dl_{reg}",
        on_click="ignore",
    )


def show_lookup(reg: int, key_prefix: str) -> None:
    try:
        with st.spinner("Getting the latest figures from the Charity Commission…"):
            rec = API.lookup(reg)
        render_charity(rec, key_prefix)
    except NotFound:
        st.warning(f"No registered charity has the number {reg}. Check the number, or search by name instead.")
    except APIError as e:
        st.error(f"{e} Your search hasn't been lost: press Enter in the search box to try again.")


# on_dismiss="rerun": closing the pop-up refreshes the page, so a prospect saved inside it
# shows up straight away in ⭐ My prospects (it used to look as if saving hadn't worked).
@st.dialog("Charity details", width="large", on_dismiss="rerun")
def charity_dialog(reg: int) -> None:
    show_lookup(reg, "d_")


def result_list(rows: list[dict], key: str, page_size: int = 15, allow_save: bool = True) -> list[dict]:
    """Charities as a simple list: name and key facts, with a 'View details' button and a 'Save' button.
    rows: [{"reg": int, "name": str, "line": str}]. Returns the rows shown on the current page."""
    if not rows:
        return []
    pages = max(1, -(-len(rows) // page_size))
    page = min(st.session_state.get(f"{key}_page", 1), pages)
    shown = rows[(page - 1) * page_size : page * page_size]
    for r in shown:
        with st.container(border=True):
            c1, c2, c3 = st.columns([6, 1.4, 1.6], vertical_alignment="center")
            c1.markdown(f"**{O.nice_name(r['name'])}** · #{r['reg']}  \n:gray[{r['line']}]")
            if c2.button("View details", key=f"{key}_view_{r['reg']}", width="stretch"):
                charity_dialog(int(r["reg"]))
            if allow_save:
                save_button(c3, int(r["reg"]), r["name"], f"{key}_save_{r['reg']}", label="⭐ Save")
    if pages > 1:
        p1, p2, p3 = st.columns([1, 2, 1], vertical_alignment="center")
        if p1.button("◀ Previous", key=f"{key}_prev", disabled=page <= 1, width="stretch"):
            st.session_state[f"{key}_page"] = page - 1
            st.rerun()
        p2.markdown(f"<div style='text-align:center'>Page {page} of {pages} · {len(rows):,} charities</div>", unsafe_allow_html=True)
        if p3.button("Next ▶", key=f"{key}_next", disabled=page >= pages, width="stretch"):
            st.session_state[f"{key}_page"] = page + 1
            st.rerun()
    return shown


def save_all_button(rows: list[dict], key: str, what: str = "on this page") -> None:
    new = [(int(r["reg"]), r["name"]) for r in rows if not in_outreach(r["reg"])]
    st.button(
        f"⭐ Save all {len(new)} {what} as prospects" if new else f"✓ All {what} saved",
        disabled=not new,
        key=key,
        on_click=_add_cb,
        args=(new,),
    )


def _set_query(text: str) -> None:
    st.session_state["q"] = text


# ---------- first screen ----------
st.markdown("### See which charities are growing, and get a ready-to-send outreach plan")
st.caption(
    "**1** Find a charity  →  **2** See if its income is going up, flat or down  →  **3** ⭐ Save it as a prospect  →  "
    "**4** Open **⭐ My prospects** for a ready-to-edit email and the best time to get in touch."
)

tab1, tab2, tab3, tab4 = st.tabs(["🔎 Find a charity", "🎯 Find new prospects", "📋 Check a list of charities", "⭐ My prospects"])

with tab1:
    if need_api():
        q = st.text_input("Charity name or registration number", placeholder="e.g. Oxfam, or 202918", key="q").strip()
        if not q:
            st.caption("Not sure where to start? Try one:")
            e1, e2, e3, _ = st.columns([1, 1, 1.4, 3])
            e1.button("Nacro", on_click=_set_query, args=("nacro",), width="stretch")
            e2.button("Oxfam", on_click=_set_query, args=("202918",), width="stretch")
            e3.button("Cancer Research UK", on_click=_set_query, args=("1089464",), width="stretch")
        elif q.isdigit():
            show_lookup(int(q), "l_")
        else:
            try:
                with st.spinner("Searching the Charity Commission register…"):
                    hits = API.search(q)
                    inc = API.latest_incomes([h["reg_number"] for h in hits[:60]]) if hits else {}
            except APIError as e:
                st.error(f"{e} Press Enter in the search box to try again.")
                hits = None
            if hits:
                hits = sorted(hits, key=lambda h: -(inc.get(h["reg_number"]) or 0))
                st.caption(f"**{len(hits)}** registered {'charity matches' if len(hits) == 1 else 'charities match'} “{q}”, largest first.")
                rows = [
                    {
                        "reg": h["reg_number"],
                        "name": h["name"],
                        "line": f"Latest income {A.money(inc.get(h['reg_number']))}"
                        + (f" · registered {h['registered_on'][:4]}" if h["registered_on"] else ""),
                    }
                    for h in hits
                ]
                result_list(rows, f"search_{q.lower()}")
            elif hits is not None:
                st.warning(f"No registered charities match “{q}”. Try fewer words (e.g. *cancer research*) or the registration number.")

with tab2:
    st.caption(f"Filter all ~172,000 registered charities to build a call list. List last updated {LIST_DATE}.")
    df = prospect_table(band, hot)
    f1, f2, f3 = st.columns(3)
    areas = f1.multiselect("Area they work in", area_options(), placeholder="Anywhere")
    sectors = f2.multiselect("Type of work", sector_options(), placeholder="Any")
    bands = f3.multiselect("Income now", list(INCOME_FILTER), default=DEFAULT_BANDS)
    g1, g2, g3 = st.columns(3)
    prio_f = g1.multiselect("Priority", [A.HIGH, A.MEDIUM, A.LOW, A.CHECK_FIRST], format_func=A.PRIORITY_LABELS.get, placeholder="Any")
    sort_by = g2.selectbox("Sort by", ["Highest priority first", "Largest income first", "Fastest growth over 3 years"])
    name_f = g3.text_input("Name contains", placeholder="optional")
    with st.expander("More filters"):
        h1, h2 = st.columns(2)
        trend_f = h1.selectbox(
            "Income growth compared with similar charities",
            ["Any", A.ABOVE, A.INLINE, A.BELOW],
            format_func=lambda x: {"Any": "Any", A.ABOVE: "▲ Growing faster", A.INLINE: "► About the same", A.BELOW: "▼ Growing slower"}[x],
        )
        with h2:
            hot_only = st.checkbox("🔥 Hot prospects only (income up more than 10% last year)")
            hide_spikes = st.checkbox("Hide ⚡ one-off jumps (income more than doubled)")
            hide_stale = st.checkbox("Hide charities with overdue accounts", value=True)
            hide_unreliable = st.checkbox("Hide charities without enough history for a trend")

    m = pd.Series(True, index=df.index)
    if areas:
        pat = "|".join(rf"(?:^|\| ){re.escape(a)}(?: \||$)" for a in areas)
        m &= df["local_authorities"].str.contains(pat, regex=True) | df["regions"].str.contains(pat, regex=True)
    if sectors:
        m &= df["sectors"].str.contains("|".join(re.escape(s) for s in sectors), regex=True)
    if bands:
        inc = df["latest_income"].fillna(-1)
        m &= pd.concat([(inc >= lo) & (inc < hi) for lo, hi in (INCOME_FILTER[b] for b in bands)], axis=1).any(axis=1)
    if prio_f:
        m &= df["priority"].isin(prio_f)
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

    rank = {A.HIGH: 3, A.MEDIUM: 2, A.LOW: 1, A.CHECK_FIRST: 0}
    res = df[m].assign(_rank=df["priority"].map(rank).fillna(0), _hot=df["hot"].fillna(False).astype(bool))
    sort_cols = {
        "Highest priority first": (["_rank", "latest_income"], False),
        "Largest income first": (["latest_income"], False),
        "Fastest growth over 3 years": (["income_change"], False),
    }[sort_by]
    res = res.sort_values(sort_cols[0], ascending=sort_cols[1], na_position="last")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Charities found", f"{len(res):,}")
    k2.metric("🟢 High priority", f"{int((res['priority'] == A.HIGH).sum()):,}")
    k3.metric("🔥 Hot prospects", f"{int(res['_hot'].sum()):,}")
    k4.metric("▲ Growing faster than similar", f"{int((res['income_trend'] == A.ABOVE).sum()):,}")

    def prospect_line(r) -> str:
        bits = [f"{A.money(r.latest_income)} income"]
        if isinstance(r.income_direction, str):
            bits.append(f"income {A.LABELS[r.income_direction].split(' ')[1].lower()} {A.pct(r.income_change)} over 3 years")
            if isinstance(r.income_trend, str) and r.income_trend in PEER_SHORT:
                bits.append(f"{PEER_SHORT[r.income_trend]} similar charities")
        elif isinstance(r.status, str):
            bits.append(A.LABELS.get(r.status, r.status))
        bits.append(f"{A.PRIORITY_LABELS.get(r.priority, '')} priority")
        if pd.notna(r.hot) and bool(r.hot):
            bits.append("🔥 hot")
        if pd.notna(r.spike) and bool(r.spike):
            bits.append("⚡ check one-off")
        if r.web:
            bits.append(str(r.web).replace("https://", "").replace("http://", "").strip("/"))
        return " · ".join(bits)

    if res.empty:
        st.info("No charities match these filters. Try removing a filter or widening the income range.")
    else:
        page_rows = [{"reg": int(r.reg_number), "name": r.name, "line": prospect_line(r)} for r in res.head(600).itertuples()]
        if st.session_state.get("_pf") != (tuple(areas), tuple(sectors), tuple(bands), tuple(prio_f), sort_by, name_f, trend_f):
            st.session_state["_pf"] = (tuple(areas), tuple(sectors), tuple(bands), tuple(prio_f), sort_by, name_f, trend_f)
            st.session_state["prospects_page"] = 1  # new filters: back to page 1
        shown = result_list(page_rows, "prospects")
        save_all_button(shown, "save_page")
        if len(res) > 600:
            st.caption(f"Showing the top 600 of {len(res):,} in the list. The spreadsheet download has all of them.")

    out = res[
        [
            "reg_number", "name", "priority", "latest_income", "latest_period_end", "status", "size_band",
            "income_y1", "income_y2", "income_y3", "income_yoy", "income_change", "income_direction", "peer_income_median", "income_trend",
            "expenditure_y1", "expenditure_y2", "expenditure_y3", "expenditure_change", "expenditure_direction",
            "peer_expenditure_median", "expenditure_trend", "hot", "spike", "stale", "sectors", "local_authorities", "regions",
            "postcode", "web", "email", "phone",
        ]
    ]  # fmt: skip
    st.download_button(f"⬇ Download all {len(res):,} as a spreadsheet (CSV)", out.to_csv(index=False), "charity_prospects.csv", "text/csv")

    with st.expander("📊 What's normal growth for each size of charity?"):
        st.caption(
            "Typical change over the last 3 years for charities with up-to-date accounts, grouped by their income 3 years ago. "
            "Each charity is compared with its own group."
        )
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Income 3 years ago": lbl,
                        "Charities in group": BENCH[lbl]["n"],
                        "Typical income change": A.pct(BENCH[lbl]["income"]),
                        "Typical expenditure change": A.pct(BENCH[lbl]["expenditure"]),
                    }
                    for _, _, lbl in A.SIZE_BANDS
                    if lbl in BENCH
                ]
            ),
            hide_index=True,
            width="stretch",
        )

with tab3:
    st.caption(f"Paste up to {MAX_LIST} registration numbers (e.g. from a spreadsheet or CRM) to check them all at once, with live figures.")
    if need_api():
        txt = st.text_area("Registration numbers", placeholder="202918, 1089464\n220949", height=110)
        nums = list(dict.fromkeys(int(n) for n in re.findall(r"\d{6,8}", txt)))[:MAX_LIST]
        if txt.strip() and not nums:
            st.warning("No registration numbers found. They're 6 to 8 digits long, e.g. 202918.")
        if nums:
            rows, missing, errors, export_rows = [], [], [], []
            bar = st.progress(0.0, text="Checking…")
            for i, n in enumerate(nums):
                try:
                    rec = API.lookup(n)
                    s = A.summarise(rec["financials"], BENCH, band=band, hot=hot)
                    pr = A.priority(s)
                    latest = s["years"][-1] if s["years"] else {}
                    bits = [f"{A.money(latest.get('income'))} income"]
                    if s["income_direction"]:
                        bits.append(f"income {s['income_direction'].lower()} {A.pct(s['income_change'])} over 3 years")
                        bits.append(f"{PEER_SHORT[s['income_trend']]} similar charities")
                    else:
                        bits.append(A.LABELS.get(s["status"], s["status"]))
                    bits.append(f"{A.PRIORITY_LABELS[pr['level']]} priority" + (" · 🔥 hot" if s["hot"] else ""))
                    rows.append({"reg": n, "name": rec["name"], "line": " · ".join(bits)})
                    export_rows.append(
                        {
                            "reg_number": n, "name": rec["name"], "priority": pr["level"], "latest_income": latest.get("income"),
                            "income_direction_3yr": s["income_direction"], "income_change_3yr": s["income_change"],
                            "income_vs_similar": s["income_trend"], "expenditure_direction_3yr": s["expenditure_direction"],
                            "hot_prospect": s["hot"], "year_ending": str(s["latest_period_end"] or "")[:10],
                            "website": rec["profile"].get("Website"),
                        }
                    )  # fmt: skip
                except NotFound:
                    missing.append(n)
                except APIError as e:
                    errors.append(f"{n}: {e}")
                bar.progress((i + 1) / len(nums), text=f"Checked {i + 1} of {len(nums)}")
            bar.empty()
            if rows:
                result_list(rows, "listcheck", page_size=20)
                save_all_button(rows, "save_list", what="in this list")
                st.download_button("⬇ Download as a spreadsheet (CSV)", pd.DataFrame(export_rows).to_csv(index=False), "charity_list_check.csv", "text/csv")
            if missing:
                st.warning(f"Not found on the register (check the numbers): {', '.join(map(str, missing))}")
            for e in errors:
                st.error(e)


# ---------- outreach ----------
CHANNEL_ICON = {"email": "✉️", "call": "📞", "linkedin": "💼"}


@st.cache_data(ttl=3600, show_spinner=False)
def cached_lookup(reg: int) -> dict:
    return API.lookup(reg)


def _save_settings():
    STORE.update_settings(
        **{k: str(st.session_state.get(f"set_{k}", "")).strip() for k in ("name", "role", "calendly")},
        budget_start_months=int(st.session_state.get("set_bstart", 6)),
        budget_end_months=int(st.session_state.get("set_bend", 2)),
    )


def _widget_to_store(reg: str, field: str, widget_key: str):
    STORE.update(reg, **{field: st.session_state[widget_key]})


def _set_done(reg: str, day: int, widget_key: str):
    STORE.set_done(reg, day, st.session_state[widget_key])


def _remove(reg: str):
    STORE.remove(reg)
    st.session_state.pop("out_table", None)
    st.session_state["_toast"] = "Removed from your prospect list"


def _reset_text(reg: str):
    for k in [k for k in st.session_state if k.startswith(f"txt_{reg}_")]:
        del st.session_state[k]


with tab4:
    st.caption(
        "Each saved charity gets an outreach plan: why it may be worth contacting, when to get in touch, and drafts for "
        "4 steps (first email with your Calendly link, follow-up email, phone call, LinkedIn). Nothing is sent for you. "
        "Key: 📊 = from the charity's accounts · 🕒 = our estimate · ✍️ = a draft for you to edit."
    )
    if need_api():
        cfg = STORE.settings
        with st.expander("✍️ Your name and Calendly link (used to sign every email)", expanded=not (cfg.get("name") and cfg.get("calendly"))):
            s1, s2, s3 = st.columns(3)
            s1.text_input("Your name", cfg.get("name", ""), key="set_name", on_change=_save_settings)
            s2.text_input("Your role", cfg.get("role", ""), key="set_role", on_change=_save_settings, placeholder="e.g. Business Development Manager")
            s3.text_input(
                "Calendly link", cfg.get("calendly", ""), key="set_calendly", on_change=_save_settings, placeholder="https://calendly.com/your-name/20min"
            )
            t1, t2 = st.columns(2)
            t1.number_input(
                "Budget planning starts (months before year end)", 1, 12, int(cfg["budget_start_months"]), key="set_bstart", on_change=_save_settings
            )
            t2.number_input("Budget planning ends (months before year end)", 0, 11, int(cfg["budget_end_months"]), key="set_bend", on_change=_save_settings)
            st.caption(
                "🕒 Timing is an **estimate**: we know when each charity's financial year ends (from its accounts), not when it "
                "actually sets its budget. Change the months above if you know better."
            )

        if not len(STORE):
            st.info(
                "**No prospects saved yet.** Find a charity in **🔎 Find a charity** or **🎯 Find new prospects** and press "
                "**⭐ Save**. Its outreach plan will appear here."
            )
        else:
            today = date.today()
            plans, rows = {}, []
            with st.spinner("Building plans from the latest Charity Commission figures…"):
                for reg, item in STORE.items.items():
                    try:
                        rec = cached_lookup(int(reg))
                    except (APIError, NotFound) as e:
                        rows.append({"reg": reg, "Charity": item["name"], "Why": f"Couldn't load: {e}", "Outcome": item["outcome"]})
                        continue
                    s = A.summarise(rec["financials"], BENCH, band=band, hot=hot)
                    plan = O.build_plan(rec, s, cfg, date.fromisoformat(item["start"]), today)
                    plans[reg] = (rec, s, plan)
                    act, due = O.next_action(item, plan)
                    rows.append(
                        {
                            "reg": reg,
                            "Priority": A.PRIORITY_LABELS[plan["priority"]["level"]],
                            "Charity": plan["contact"]["charity"],
                            "Why": plan["primary"]["title"],
                            "Best time (estimate)": ("Now" if plan["timing"]["now"] else plan["timing"]["period"]),
                            "Next action": act,
                            "Due": due,
                            "Outcome": item["outcome"],
                        }
                    )
            table = pd.DataFrame(rows)
            for col in ("Priority", "Best time (estimate)", "Next action", "Due", "Outcome"):
                if col not in table:
                    table[col] = None
            table["Outcome"] = table["Outcome"].fillna("Active")
            active = table[table["Outcome"] == "Active"]
            fmt_day = lambda d: f"{d:%a} {d.day} {d:%b}"
            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Saved prospects", len(table))
            m2.metric("Active sequences", len(active))
            m3.metric("Due today or overdue", sum(isinstance(d, date) and d <= today for d in active["Due"]))
            m4.metric("📅 Meetings booked", int((table["Outcome"] == "Meeting booked").sum()))

            # One row per prospect with an "Open plan" button (no tick boxes).
            if st.session_state.get("plan_reg") not in set(table["reg"]):
                st.session_state["plan_reg"] = table.iloc[0]["reg"]
            for row in table.to_dict("records"):
                current = row["reg"] == st.session_state["plan_reg"]
                due = row.get("Due") if isinstance(row.get("Due"), date) else None
                with st.container(border=True):
                    c1, c2 = st.columns([6, 1.4], vertical_alignment="center")
                    when = (f" · due {fmt_day(due)}" + (" ⚠ overdue" if due < today else "")) if due else ""
                    c1.markdown(
                        f"{row.get('Priority') or ''} **{row['Charity']}** · {row.get('Why') or ''}  \n"
                        f":gray[Next: {row.get('Next action') or '–'}{when} · Outcome: {row['Outcome']} · "
                        f"Best time (estimate): {row.get('Best time (estimate)') or '–'}]"
                    )
                    if c2.button("✓ Showing below" if current else "Open plan", key=f"open_{row['reg']}", disabled=current, width="stretch"):
                        st.session_state["plan_reg"] = row["reg"]
                        st.rerun()
            reg = st.session_state["plan_reg"]

            export = [
                {
                    "reg_number": r,
                    "charity": p[2]["contact"]["charity"],
                    "priority": p[2]["priority"]["level"],
                    "outcome": STORE.items[r]["outcome"],
                    "day": stp["day"],
                    "date": stp["date"],
                    "channel": stp["channel"],
                    "to": stp["to"],
                    "subject": stp["subject"],
                    "message": stp["body"],
                    "done": STORE.items[r]["done"].get(str(stp["day"]), False),
                }
                for r, p in plans.items()
                for stp in p[2]["steps"]
            ]
            st.download_button("⬇ Download all plans as a spreadsheet (CSV)", pd.DataFrame(export).to_csv(index=False), "outreach_sequences.csv", "text/csv")

            if reg in plans:
                rec, s, plan = plans[reg]
                item = STORE.items[reg]
                c, pr, tm = plan["contact"], plan["priority"], plan["timing"]
                st.divider()
                h1, h2, h3, h4 = st.columns([3, 1.3, 1.3, 1])
                h1.subheader(f"{c['charity']}  ·  #{reg}")
                h2.selectbox(
                    "Outcome",
                    OUTCOMES,
                    index=OUTCOMES.index(item["outcome"]),
                    key=f"out_{reg}",
                    on_change=_widget_to_store,
                    args=(reg, "outcome", f"out_{reg}"),
                )
                h3.date_input(
                    "Sequence starts",
                    date.fromisoformat(item["start"]),
                    key=f"start_{reg}",
                    on_change=_widget_to_store,
                    args=(reg, "start", f"start_{reg}"),
                    format="DD/MM/YYYY",
                )
                h4.write("")
                h4.button("🗑 Remove", key=f"rm_{reg}", on_click=_remove, args=(reg,), width="stretch")

                act, due = O.next_action(item, plan)
                st.markdown(f"**Next action:** {act}" + (f" · due **{fmt_day(due)}**" if due else "") + (" ⚠ overdue" if due and due < today else ""))
                if item["outcome"] != "Active":
                    st.info(f"Sequence stopped: **{item['outcome']}**. Set the outcome back to Active to carry on.")

                p1, p2 = st.columns([1.1, 1])
                with p1:
                    st.markdown(f"**💡 Why this charity may be worth contacting:** {A.PRIORITY_LABELS[pr['level']]} priority")
                    for r in pr["reasons"]:
                        st.markdown(f"- {r}")
                    st.markdown("**📊 Financial direction** (from the accounts)")
                    st.write(plan["summary"])
                with p2:
                    st.markdown("**📊 Facts the email opens with** (from the accounts)")
                    for hk in plan["hooks"]:
                        if hk["key"] == "fallback":
                            continue
                        used = (
                            "✉️ email 1"
                            if hk is plan["primary"]
                            else "✉️ email 2"
                            if hk is plan["secondary"]
                            else "📞 call only"
                            if not hk["email_safe"]
                            else "📞 call"
                        )
                        st.markdown(f"- **{hk['title']}** ({used}): {hk['fact']}")
                    if plan["primary"]["key"] == "fallback":
                        st.caption("No strong signal in the filings, so the email uses a general opener about size and sector.")
                    st.markdown("**🕒 Suggested time to get in touch** (estimate)")
                    (st.success if tm["now"] else st.info)(f"{tm['text']}  \n**Recommended outreach period:** {tm['period']}.  \n{tm['guidance']}")

                k1, k2 = st.columns(2)
                with k1:
                    st.markdown("**Who to contact**")
                    st.markdown(f"Email to: **{c['to']['who']}**")
                    links = []
                    if c["email"]:
                        links.append(f"✉️ [{c['email']}](mailto:{c['email']})")
                    if c["phone"]:
                        links.append(f"📞 [{c['phone']}](tel:{c['phone'].replace(' ', '')})")
                    if c["website"]:
                        site = c["website"] if c["website"].startswith("http") else f"https://{c['website']}"
                        links.append(f"🌐 [{c['website']}]({site})")
                    st.markdown("  \n".join(links) or "No contact details published.")
                with k2:
                    st.markdown("**Find the decision-maker**")
                    st.caption(f"The register lists trustees, not staff. The buyer is usually the {c['decision_maker']}.")
                    l1, l2, l3 = st.columns(3)
                    l1.link_button("CEO ↗", c["linkedin_ceo"], width="stretch", help="LinkedIn search")
                    l2.link_button("Finance ↗", c["linkedin_finance"], width="stretch", help="LinkedIn search")
                    if c["linkedin_chair"]:
                        l3.link_button("Chair ↗", c["linkedin_chair"], width="stretch", help="LinkedIn search")

                st.text_area(
                    "Notes (saved)",
                    item.get("notes", ""),
                    key=f"notes_{reg}",
                    height=80,
                    placeholder="e.g. Spoke to reception, CEO is Sarah Jones, call back Thursday",
                    on_change=_widget_to_store,
                    args=(reg, "notes", f"notes_{reg}"),
                )

                tcol1, tcol2, tcol3 = st.columns([3, 1.2, 1.2])
                tcol1.markdown("**✍️ Drafts for you to edit**: tick each step when done")
                tcol2.download_button(
                    "⬇ Download this plan", O.plan_markdown(rec, s, plan, item), f"outreach_plan_{reg}.md", "text/markdown", width="stretch", on_click="ignore"
                )
                tcol3.button(
                    "↺ Regenerate drafts",
                    key=f"regen_{reg}",
                    on_click=_reset_text,
                    args=(reg,),
                    help="Throw away your edits and rebuild the messages (e.g. after changing your details).",
                    width="stretch",
                )
                if not (cfg.get("name") and cfg.get("calendly")):
                    st.warning("Add your name and Calendly link in **Your name and Calendly link** above so the drafts are ready to send.")
                first_open = next((x["day"] for x in plan["steps"] if not item["done"].get(str(x["day"]))), -1)
                for stp in plan["steps"]:
                    d = stp["day"]
                    done = item["done"].get(str(d), False)
                    late = (not done) and stp["date"] < today and item["outcome"] == "Active"
                    label = f"{'✅' if done else CHANNEL_ICON[stp['channel']]}  Day {d} · {fmt_day(stp['date'])} · {stp['title']}" + (
                        "  ⚠ overdue" if late else ""
                    )
                    with st.expander(label, expanded=not done and item["outcome"] == "Active" and d == first_open):
                        st.checkbox("Done", value=done, key=f"done_{reg}_{d}", on_change=_set_done, args=(reg, d, f"done_{reg}_{d}"))
                        if stp["channel"] == "email":
                            to = st.text_input("To", stp["to"] or "", key=f"txt_{reg}_{d}_to")
                            subj = st.text_input("Subject", stp["subject"], key=f"txt_{reg}_{d}_subj")
                            body = st.text_area("Message (edit freely)", stp["body"], key=f"txt_{reg}_{d}_body", height=330)
                            b1, _ = st.columns([1, 3])
                            b1.link_button("✉️ Open in my email app", O.mailto(to, subj, body), width="stretch")
                            st.caption("Or copy it: hover the box below and click the copy icon.")
                            st.code(f"Subject: {subj}\n\n{body}", language=None, wrap_lines=True)
                        elif stp["channel"] == "call":
                            notes = st.text_area("Call script (edit freely)", stp["body"], key=f"txt_{reg}_{d}_body", height=380)
                            if c["phone"]:
                                st.link_button(f"📞 Call {c['phone']}", f"tel:{c['phone'].replace(' ', '')}")
                            st.code(notes, language=None, wrap_lines=True)
                        else:
                            note = st.text_area("Connection note (edit freely)", stp["body"], key=f"txt_{reg}_{d}_body", height=110)
                            n = len(note)
                            (st.caption if n <= O.LINKEDIN_LIMIT else st.error)(f"{n}/{O.LINKEDIN_LIMIT} characters (LinkedIn's limit for a connection note)")
                            st.code(note, language=None, wrap_lines=True)
                            l1, l2 = st.columns(2)
                            if c["linkedin_chair"]:
                                l1.link_button(f"Find {c['chair']['full']} on LinkedIn ↗", c["linkedin_chair"], width="stretch")
                            l2.link_button("Find their chief executive ↗", c["linkedin_ceo"], width="stretch")
