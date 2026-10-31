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

st.set_page_config(page_title="Charity Growth Finder · mhance", page_icon=":material/trending_up:", layout="wide")

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
def prospect_table(band: float, hot: float, small: float) -> pd.DataFrame:
    base, bench = market()
    return get_snapshot().charities.merge(A.apply_trends(base, bench, band, hot, small), on="org_number", how="left")


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
    st.session_state["_toast"] = f"Added {n} to your prospects. Find {'them' if n != 1 else 'it'} in My prospects." if n else "Already in your prospects"


if st.session_state.get("_toast"):
    st.toast(st.session_state.pop("_toast"), icon=":material/star:")

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
            "access key (see *API key* in the README). **Find new prospects** still works in the meantime."
        )
    else:
        st.error(f"Can't get data from the Charity Commission right now. {API_PROBLEM} **Find new prospects** still works.")
    return False


PEER_WORDS = {A.ABOVE: "ahead of", A.INLINE: "in line with", A.BELOW: "behind"}
PEER_SHORT = {A.ABOVE: "ahead of", A.INLINE: "in line with", A.BELOW: "behind"}


def small_threshold() -> float:
    """'Small charity' = income under the minimum income chosen on Find new prospects (default £100k)."""
    return float(st.session_state.get("min_income") or A.SMALL_CHARITY)


# Rule settings: changed on the Settings page, read everywhere.
band = st.session_state.get("band_pct", int(A.FLAT_BAND * 100)) / 100
hot = st.session_state.get("hot_pct", int(A.HOT_THRESHOLD * 100)) / 100


def page_settings() -> None:
    st.markdown("### Settings")
    if not KEY:
        st.warning("Live look-ups are off (no Charity Commission key set up).")
    elif API_PROBLEM:
        st.error(f"Can't reach the Charity Commission: {API_PROBLEM}")
    else:
        st.success("Connected to live Charity Commission data.", icon=":material/check_circle:")
    st.caption(f"Prospect list last updated **{LIST_DATE}** from the Charity Commission's daily download.")

    st.markdown("#### Rules")
    st.slider("A change counts as up/down above (±%)", 0, 20, int(A.FLAT_BAND * 100), key="band_pct", persist_state="session")
    st.slider("Hot prospect: income up more than (%) on the year before", 0, 50, int(A.HOT_THRESHOLD * 100), key="hot_pct", persist_state="session")
    st.caption(f"Small charity: income under **{A.money(small_threshold())}**. Change it with *Minimum income* on *Find new prospects*.")

    st.markdown("#### What the figures and labels mean")
    st.markdown(
        "- **Total income**: everything the charity received in its financial year (donations, grants, contracts, "
        "trading, investments). It's the charity equivalent of revenue.\n"
        "- **Total expenditure**: everything it spent in the same year.\n"
        "- **Net surplus / deficit** = total income − total expenditure. Income and expenditure are never added together.\n"
        "- **Up / Flat / Down**: compares the oldest and newest of the last 3 yearly accounts. "
        f"A change of more than {band:.0%} counts as up or down.\n"
        "- **Similar charities**: charities that were the same size 3 years ago.\n"
        f"- **Hot prospect**: income up more than {hot:.0%} on the year before.\n"
        "- **High percentage growth from a small base**: the growth started from income under the small-charity "
        "threshold (the minimum income set on *Find new prospects*, or £100k if none). It's shown, but doesn't raise priority on its own.\n"
        "- **Priority**: High = hot *and* growing faster than similar charities · Medium = one of the two · "
        "Low = neither, a small base, not enough history, or overdue accounts · Check first = the figures "
        "look like a typo in the official records.\n"
        "- **Missing figures** are shown as –. Nothing is estimated or filled in."
    )


def summary_of(rec: dict) -> dict:
    return A.summarise(rec["financials"], BENCH, band=band, hot=hot, small=small_threshold())


# ---------- single charity ----------
def register_url(reg) -> str:
    return f"https://register-of-charities.charitycommission.gov.uk/en/charity-search/-/charity-details/{int(reg)}"


def companies_house_url(company_no) -> str | None:
    c = str(company_no or "").strip().upper()
    if not c or c in ("NONE", "NAN"):
        return None
    return f"https://find-and-update.company-information.service.gov.uk/company/{c.zfill(8) if c.isdigit() else c}"


def save_button(container, reg: int, name: str, key: str, label: str = "Add to prospects", width="stretch") -> None:
    """The one 'next step' action, worded the same everywhere."""
    if in_outreach(reg):
        container.button(
            "In your prospects",
            icon=":material/check:",
            disabled=True,
            width=width,
            key=f"{key}_saved",
            help="Open My prospects for the outreach plan and draft email.",
        )
    else:
        container.button(label, icon=":material/star:", type="primary", width=width, key=key, on_click=_add_cb, args=([(reg, name)],))


def year_label(period_end) -> str:
    d = pd.Timestamp(period_end)
    return f"{d:%b %Y}"


DIRECTION_BADGE = {  # (icon, colour) for income; expenditure uses neutral colours (spending more isn't good or bad)
    "income": {A.UP: (":material/trending_up:", "green"), A.FLAT: (":material/trending_flat:", "gray"), A.DOWN: (":material/trending_down:", "red")},
    "expenditure": {A.UP: (":material/trending_up:", "blue"), A.FLAT: (":material/trending_flat:", "gray"), A.DOWN: (":material/trending_down:", "blue")},
}
NO_TREND = {
    A.NEW: "not enough years on record to tell",
    A.SMALL: "income too small to measure a trend",
    A.CHECK: "figures look wrong, check first",
}


def money_card(s: dict, field: str, title: str, help_text: str) -> None:
    """One headline figure: latest year, the 3-year change in % and £, and a clearly labelled trend."""
    years = s["years"]
    latest = years[-1] if years else {}
    change, change_abs = s.get(f"{field}_change"), s.get(f"{field}_change_abs")
    with st.container(border=True):
        st.metric(
            f"{title}, latest year",
            A.money(latest.get(field)),
            A.pct_abs(change, change_abs) if change is not None else None,
            delta_color="normal" if field == "income" and s.get("income_direction") in (A.UP, A.DOWN) else "off",
            delta_description=f"over {len(years)} years" if change is not None else None,
            help=help_text,
        )
        d = s.get(f"{field}_direction")
        name = "Income" if field == "income" else "Expenditure"
        if d:
            icon, colour = DIRECTION_BADGE[field][d]
            st.badge(f"{name} trend: {d}", icon=icon, color=colour)
        else:
            st.badge(f"{name} trend: {NO_TREND.get(s['status'], 'not available')}", icon=":material/help:", color="gray")


def net_card(s: dict) -> None:
    latest = s["years"][-1] if s["years"] else {}
    net = latest.get("net")
    with st.container(border=True):
        st.metric(
            "Net surplus / deficit, latest year",
            A.net_label(net),
            help="Total income minus total expenditure for the same year. A deficit means it spent more than it received.",
        )
        if net is None:
            st.badge("Expenditure not reported", icon=":material/help:", color="gray")
        elif net >= 0:
            st.badge(
                f"Surplus: {A.pct(net / latest['income']).lstrip('+')} of income" if latest["income"] else "Surplus",
                icon=":material/add_circle:",
                color="green",
            )
        else:
            st.badge(
                f"Deficit: {A.pct(-net / latest['income']).lstrip('+')} of income" if latest["income"] else "Deficit",
                icon=":material/remove_circle:",
                color="red",
            )


def verdict(s: dict, pr: dict) -> None:
    """Why this charity may or may not be a useful prospect, always visible."""
    level = pr["level"]
    heading = {
        A.HIGH: "Worth contacting: high priority",
        A.MEDIUM: "Possibly worth contacting: medium priority",
        A.LOW: "Probably not a priority right now",
        A.CHECK_FIRST: "Check the figures before contacting",
    }[level]
    box = {A.HIGH: st.success, A.MEDIUM: st.info, A.LOW: st.warning, A.CHECK_FIRST: st.error}[level]
    icon = {A.HIGH: ":material/thumb_up:", A.MEDIUM: ":material/lightbulb:", A.LOW: ":material/schedule:", A.CHECK_FIRST: ":material/report:"}[level]
    lines = [f"**{A.PRIORITY_LABELS[level]} · {heading}**"] + [f"- {r}" for r in pr["reasons"]]
    tags = []  # hot-prospect and small-base wording already come from priority()
    if s["spike"]:
        tags.append("Income more than doubled in a year. Check whether it's a one-off such as a legacy.")
    if s["gaps"]:
        tags.append("A year's accounts are missing: " + "; ".join(f"nothing filed between {a} and {b}" for a, b in s["gaps"]) + ". Nothing has been filled in.")
    lines += [f"- {t}" for t in tags]
    box("\n".join(lines), icon=icon)


def trustees_block(rec: dict) -> None:
    tr = sorted(rec["trustees"], key=lambda t: (not t["is_chair"], t["name"] or ""))
    st.markdown("**Trustees (the charity's board)**")
    if not tr:
        st.caption("The Charity Commission doesn't list any trustees for this charity.")
        return
    chairs = [O.nice_name(t["name"]) for t in tr if t["is_chair"]]
    others = [O.nice_name(t["name"]) for t in tr if not t["is_chair"]]
    shown, more = others[:10], len(others) - 10
    text = (f"**Chair:** {', '.join(chairs)}  \n" if chairs else "") + (
        f"**Trustees:** {', '.join(shown)}" + (f", and {more} more (see below)" if more > 0 else "") if others else ""
    )
    st.markdown(text)
    st.caption(
        f"{len(tr)} trustee{'s' if len(tr) != 1 else ''} on the register. Trustees are the board, not staff: "
        "the buyer is usually the chief executive or finance director."
    )


def chart_scale(values) -> tuple[float, str]:
    """Pick £ / £k / £m so a small charity's chart isn't a row of 0.0s."""
    top = max((abs(v) for v in values if v is not None and not pd.isna(v)), default=0)
    return (1e6, "£ millions") if top >= 1e6 else (1e3, "£ thousands") if top >= 1e3 else (1, "£")


def render_charity(rec: dict, key_prefix: str = "") -> None:
    s = summary_of(rec)
    pr = A.priority(s)
    reg = rec["reg_number"]
    years = s["years"]

    # 1-2. Which charity, and the one next step
    with st.container(horizontal=True, vertical_alignment="center"):
        with st.container():
            st.subheader(O.nice_name(rec["name"]), anchor=False)
            st.markdown(
                f"Registered charity number **{reg}**"
                + (f" · Latest accounts: year ending **{pd.Timestamp(s['latest_period_end']):%d %b %Y}**" if s["latest_period_end"] else "")
                + (" · :orange[accounts overdue]" if s["stale"] else "")
            )
        save_button(st, reg, rec["name"], f"{key_prefix}add_{reg}", width=200)

    if not years:
        st.info("No accounts on record yet, so there are no income or expenditure figures. This is usually a newly registered or very small charity.")
        trustees_block(rec)
        return

    # 3-7. Income, expenditure, surplus / deficit
    c1, c2, c3 = st.columns(3)
    with c1:
        money_card(
            s,
            "income",
            "Total income",
            "The charity equivalent of revenue: everything it received in the year (donations, grants, contracts, trading, investments).",
        )
    with c2:
        money_card(s, "expenditure", "Total expenditure", "Everything the charity spent in the same year.")
    with c3:
        net_card(s)

    st.table(
        pd.DataFrame(
            [
                {
                    "Year ending": year_label(y["period_end"]),
                    "Total income": A.money(y["income"]),
                    "Total expenditure": A.money(y.get("expenditure")),
                    "Net surplus / deficit": A.net_label(y.get("net")),
                }
                for y in years
            ]
        ),
        hide_index=True,
        alt=f"Total income, total expenditure and net surplus or deficit for the last {len(years)} years",
    )
    st.caption(
        f"Last {len(years)} yearly accounts, oldest first. Trend = change from the oldest to the newest year: "
        f"more than ±{band:.0%} is up or down, otherwise flat. Net surplus / deficit = total income − total expenditure. "
        "Missing figures show as –."
    )

    # 9. Why it may or may not be worth contacting
    verdict(s, pr)

    # 8. Key people
    trustees_block(rec)

    # ---------- secondary detail, below the summary ----------
    st.divider()
    st.markdown("##### More detail")
    left, right = st.columns([3, 2])
    with left:
        chart = pd.DataFrame(s["all_years"])
        div, unit = chart_scale(list(chart["income"]) + list(chart["expenditure"]))
        chart = chart.assign(Year=chart["period_end"].map(year_label)).set_index("Year")[["income", "expenditure"]] / div
        st.bar_chart(
            chart.rename(columns={"income": "Total income", "expenditure": "Total expenditure"}),
            stack=False,
            sort=False,
            height=240,
            color=["#1F5FBF", "#E8A33D"],
            y_label=unit,
            alt="Bar chart of total income and total expenditure for every year on record",
        )
        st.caption(f"Every year on record (up to 5), in {unit}. Bars start at zero.")
    with right:
        peer = s["peer"] or {}
        if s["status"] == A.OK and peer:
            st.markdown("**Compared with similar-sized charities**")
            for f, nm in (("income", "Income"), ("expenditure", "Expenditure")):
                if s[f"{f}_change"] is not None and peer.get(f) is not None:
                    st.markdown(f"- {nm} {A.pct(s[f'{f}_change'])}: {PEER_WORDS[s[f'{f}_trend']]} similar charities ({A.pct(peer[f])})")
            st.caption(f"Similar = the {peer['n']:,} charities with {s['size_band']} income 3 years ago.")
        elif s["status"] != A.OK:
            (st.error if s["status"] == A.CHECK else st.info)(A.STATUS_HELP[s["status"]])
        b1, b2 = st.columns(2)
        b1.link_button("Charity Commission page", register_url(reg), icon=":material/open_in_new:", width="stretch")
        ch = companies_house_url(rec["profile"].get("Company no."))
        if ch:
            b2.link_button("Companies House", ch, icon=":material/open_in_new:", width="stretch")

    with st.expander("Contact details and profile"):
        for k, v in rec["profile"].items():
            if v not in (None, "", 0) and not (isinstance(v, float) and pd.isna(v)):
                st.markdown(f"**{k}:** {v}")
    tr = sorted(rec["trustees"], key=lambda t: (not t["is_chair"], t["name"] or ""))
    if tr:
        with st.expander(f"All {len(tr)} trustees with start dates"):
            st.dataframe(
                pd.DataFrame([{"Name": t["name"], "Role": "Chair" if t["is_chair"] else "Trustee", "Since": t["appointed"] or "–"} for t in tr]),
                hide_index=True,
                width="stretch",
            )

    peer = s["peer"] or {}
    export = pd.DataFrame(
        [
            {
                "reg_number": reg,
                "name": rec["name"],
                "year_ending": str(y["period_end"])[:10],
                "total_income": y["income"],
                "income_vs_year_before": y.get("income_yoy"),
                "total_expenditure": y.get("expenditure"),
                "expenditure_vs_year_before": y.get("expenditure_yoy"),
                "net_surplus_or_deficit": y.get("net"),
                "income_direction_3yr": s["income_direction"],
                "income_change_3yr_pct": s["income_change"],
                "income_change_3yr_gbp": s["income_change_abs"],
                "similar_charities_income_change_3yr": peer.get("income"),
                "expenditure_direction_3yr": s["expenditure_direction"],
                "expenditure_change_3yr_pct": s["expenditure_change"],
                "expenditure_change_3yr_gbp": s["expenditure_change_abs"],
                "priority": pr["level"],
                "hot_prospect": s["hot"],
                "small_base": s["small_base"],
                "trustees": "; ".join(t["name"] for t in tr),
                "website": rec["profile"].get("Website"),
            }
            for y in years
        ]
    )
    st.download_button(
        "Download these figures (CSV)",
        export.to_csv(index=False),
        f"charity_{reg}.csv",
        "text/csv",
        icon=":material/download:",
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
# shows up straight away in My prospects (it used to look as if saving hadn't worked).
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
                save_button(c3, int(r["reg"]), r["name"], f"{key}_save_{r['reg']}", label="Add")
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
        f"Add all {len(new)} {what} to prospects" if new else f"All {what} are in your prospects",
        icon=":material/star:",
        disabled=not new,
        key=key,
        on_click=_add_cb,
        args=(new,),
    )


def _set_query(text: str) -> None:
    st.session_state["q"] = text


# ---------- page 1: look up a charity (the main page) ----------
def page_lookup() -> None:
    st.markdown("### Look up a charity")
    if not need_api():
        return
    q = st.text_input(
        "Charity name or registration number",
        placeholder="e.g. Oxfam, or 202918",
        key="q",
        persist_state="session",
        icon=":material/search:",
    ).strip()
    if not q:
        st.caption("Type a name or number and press Enter. Not sure where to start? Try one:")
        with st.container(horizontal=True):
            st.button("Nacro", on_click=_set_query, args=("nacro",))
            st.button("Oxfam", on_click=_set_query, args=("202918",))
            st.button("Cancer Research UK", on_click=_set_query, args=("1089464",))
        st.caption(
            "You'll see total income and expenditure for the last 3 years, whether each is going up, flat or down, "
            "the surplus or deficit, the trustees, and whether the charity looks worth contacting."
        )
        return
    if q.isdigit():
        show_lookup(int(q), "l_")
        return
    try:
        with st.spinner("Searching the Charity Commission register…"):
            hits = API.search(q)
            inc = API.latest_incomes([h["reg_number"] for h in hits[:60]]) if hits else {}
    except APIError as e:
        st.error(f"{e} Press Enter in the search box to try again.")
        return
    if not hits:
        st.warning(f"No registered charities match “{q}”. Try fewer words (e.g. *cancer research*) or the registration number.")
        return
    hits = sorted(hits, key=lambda h: -(inc.get(h["reg_number"]) or 0))
    if len(hits) > 1:
        # Show the largest match straight away (usually the one people mean); the others are one click away.
        regs = [h["reg_number"] for h in hits]
        names = {h["reg_number"]: f"{O.nice_name(h['name'])} · #{h['reg_number']} · income {A.money(inc.get(h['reg_number']))}" for h in hits}
        reg = st.selectbox(
            f"{len(hits)} charities match “{q}”. Showing the largest. Not the right one? Pick another:",
            regs,
            format_func=names.get,
            key=f"pick_{q.lower()}",
        )
    else:
        reg = hits[0]["reg_number"]
    show_lookup(int(reg), "l_")


# ---------- page 2: find new prospects (many charities at once) ----------
MIN_OPTIONS = [0, 10_000, 25_000, 50_000, 100_000, 250_000, 500_000, 1_000_000]
MAX_OPTIONS = [None, 1_000_000, 5_000_000, 10_000_000, 25_000_000, 100_000_000]


def page_prospects() -> None:
    st.markdown("### Find new prospects")
    st.caption(f"Filter all ~172,000 registered charities to build a call list. List last updated {LIST_DATE}.")

    f0, f1, f2, f3 = st.columns(4)
    min_inc = f0.selectbox(
        "Minimum income",
        MIN_OPTIONS,
        index=MIN_OPTIONS.index(A.SMALL_CHARITY),
        format_func=lambda v: "Any (include small charities)" if not v else f"{A.money(v)} or more",
        key="min_income",
        persist_state="session",
        help="Total income in the latest year. Charities below this are left out, and growth from below it is labelled "
        "'high percentage growth from a small base'.",
    )
    small = float(min_inc or A.SMALL_CHARITY)
    exclude_small = bool(min_inc)
    df = prospect_table(band, hot, small)
    areas = f1.multiselect("Area they work in", area_options(), placeholder="Anywhere", key="areas", persist_state="session")
    sectors = f2.multiselect("Type of work", sector_options(), placeholder="Any", key="sectors", persist_state="session")
    prio_f = f3.multiselect(
        "Priority", [A.HIGH, A.MEDIUM, A.LOW, A.CHECK_FIRST], format_func=A.PRIORITY_LABELS.get, placeholder="Any", key="prio_f", persist_state="session"
    )
    g1, g2 = st.columns(2)
    sort_by = g1.selectbox(
        "Sort by",
        ["Highest priority first", "Largest income first", "Biggest £ income growth over 3 years", "Fastest % income growth over 3 years"],
        key="sort_by",
        persist_state="session",
    )
    name_f = g2.text_input("Name contains", placeholder="optional", key="name_f", persist_state="session")
    with st.expander("More filters"):
        h1, h2 = st.columns(2)
        trend_f = h1.selectbox(
            "Income growth compared with similar charities",
            ["Any", A.ABOVE, A.INLINE, A.BELOW],
            format_func=lambda x: {"Any": "Any", A.ABOVE: "Growing faster", A.INLINE: "About the same", A.BELOW: "Growing slower"}[x],
            key="trend_f",
            persist_state="session",
        )
        max_inc = h1.selectbox(
            "Maximum income",
            MAX_OPTIONS,
            format_func=lambda v: "No maximum" if v is None else f"Up to {A.money(v)}",
            key="max_income",
            persist_state="session",
        )
        with h2:
            hot_only = st.checkbox("Hot prospects only (income up more than 10% last year, not from a small base)", key="hot_only", persist_state="session")
            hide_spikes = st.checkbox("Leave out one-off jumps (income more than doubled)", key="hide_spikes", persist_state="session")
            hide_stale = st.checkbox("Leave out charities with overdue accounts", value=True, key="hide_stale", persist_state="session")
            hide_unreliable = st.checkbox("Leave out charities without enough history for a trend", key="hide_unreliable", persist_state="session")

    # Everything except the "leave out" filters, so we can say exactly how many each one hides.
    m = pd.Series(True, index=df.index)
    if areas:
        pat = "|".join(rf"(?:^|\| ){re.escape(a)}(?: \||$)" for a in areas)
        m &= df["local_authorities"].str.contains(pat, regex=True) | df["regions"].str.contains(pat, regex=True)
    if sectors:
        m &= df["sectors"].str.contains("|".join(re.escape(s) for s in sectors), regex=True)
    if max_inc is not None:
        m &= ~(df["latest_income"] >= max_inc)
    if prio_f:
        m &= df["priority"].isin(prio_f)
    if trend_f != "Any":
        m &= df["income_trend"] == trend_f
    if hot_only:
        m &= df["hot"].fillna(False).astype(bool) & ~df["small_base"].fillna(False).astype(bool)
    if name_f:
        m &= df["name"].str.contains(name_f, case=False, regex=False)

    hidden = []
    no_accounts = m & df["latest_income"].isna()
    if exclude_small:
        is_small = m & (df["latest_income"] < small)
        hidden.append((int(is_small.sum()), f"with income under {A.money(small)}"))
        hidden.append((int(no_accounts.sum()), "with no accounts on record"))
        m &= ~is_small & ~no_accounts
    for on, col, words in (
        (hide_spikes, df["spike"].fillna(False).astype(bool), "with a one-off jump (More filters)"),
        (hide_stale, df["stale"].fillna(True).astype(bool), "with overdue accounts (More filters)"),
        (hide_unreliable, df["status"] != A.OK, "without enough history (More filters)"),
    ):
        if on:
            hidden.append((int((m & col).sum()), words))
            m &= ~col

    rank = {A.HIGH: 3, A.MEDIUM: 2, A.LOW: 1, A.CHECK_FIRST: 0}
    res = df[m].assign(_rank=df["priority"].map(rank).fillna(0), _hot=df["hot"].fillna(False).astype(bool) & ~df["small_base"].fillna(False).astype(bool))
    sort_cols = {
        "Highest priority first": ["_rank", "latest_income"],
        "Largest income first": ["latest_income"],
        "Biggest £ income growth over 3 years": ["income_change_abs"],
        "Fastest % income growth over 3 years": ["income_change"],
    }[sort_by]
    res = res.sort_values(sort_cols, ascending=False, na_position="last")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Charities found", f"{len(res):,}")
    k2.metric("High priority", f"{int((res['priority'] == A.HIGH).sum()):,}")
    k3.metric(
        "Hot prospects", f"{int(res['_hot'].sum()):,}", help="Income up more than the hot-prospect line last year, not counting growth from a small base."
    )
    k4.metric(
        "Small-base growth",
        f"{int(res['small_base_growth'].fillna(False).astype(bool).sum()):,}",
        help="High percentage growth from a small base. Shown but not prioritised.",
    )
    hidden = [(n, w) for n, w in hidden if n]
    if hidden:
        st.caption("**Not shown:** " + " · ".join(f"{n:,} {w}" for n, w in hidden) + ". Change the matching option to include them.")
    else:
        st.caption("Nothing is being left out by the income or 'leave out' options.")
    if sort_by.startswith("Fastest %") and not exclude_small:
        st.warning(
            "Sorting by % growth with small charities included puts tiny charities first. Their % changes come from a small base.", icon=":material/warning:"
        )

    def prospect_line(r) -> str:
        bits = [f"Income {A.money(r.latest_income)}"]
        if isinstance(r.income_direction, str):
            bits.append(f"{A.LABELS[r.income_direction]} {A.pct_abs(r.income_change, r.income_change_abs)} over 3 years")
            if isinstance(r.income_trend, str) and r.income_trend in PEER_SHORT:
                bits.append(f"{PEER_SHORT[r.income_trend]} similar charities")
        elif isinstance(r.status, str):
            bits.append(A.LABELS.get(r.status, r.status))
        if pd.notna(r.net_latest):
            bits.append(A.net_label(r.net_latest))
        bits.append(f"{A.PRIORITY_LABELS.get(r.priority, '')} priority")
        if pd.notna(r.small_base_growth) and bool(r.small_base_growth):
            bits.append("high % growth from a small base")
        elif pd.notna(r.hot) and bool(r.hot):
            bits.append("hot prospect")
        if pd.notna(r.spike) and bool(r.spike):
            bits.append("check for a one-off")
        return " · ".join(bits)

    if res.empty:
        st.info("No charities match these filters. Try removing a filter, or include small charities.")
    else:
        page_rows = [{"reg": int(r.reg_number), "name": r.name, "line": prospect_line(r)} for r in res.head(600).itertuples()]
        sig = (tuple(areas), tuple(sectors), tuple(prio_f), sort_by, name_f, trend_f, exclude_small, small, max_inc)
        if st.session_state.get("_pf") != sig:
            st.session_state["_pf"] = sig
            st.session_state["prospects_page"] = 1  # new filters: back to page 1
        shown = result_list(page_rows, "prospects")
        save_all_button(shown, "save_page")
        if len(res) > 600:
            st.caption(f"Showing the top 600 of {len(res):,}. The spreadsheet download has all of them.")

    out = res[
        [
            "reg_number", "name", "priority", "latest_income", "latest_period_end", "status", "size_band",
            "income_y1", "income_y2", "income_y3", "income_yoy", "income_change", "income_change_abs", "income_direction",
            "peer_income_median", "income_trend", "expenditure_y1", "expenditure_y2", "expenditure_y3", "expenditure_change",
            "expenditure_change_abs", "expenditure_direction", "peer_expenditure_median", "expenditure_trend", "net_latest",
            "hot", "small_base", "small_base_growth", "spike", "stale", "sectors", "local_authorities", "regions",
            "postcode", "web", "email", "phone",
        ]
    ].rename(columns={"latest_income": "latest_total_income", "net_latest": "latest_net_surplus_or_deficit"})  # fmt: skip
    st.download_button(
        f"Download all {len(res):,} as a spreadsheet (CSV)", out.to_csv(index=False), "charity_prospects.csv", "text/csv", icon=":material/download:"
    )

    with st.expander("What's normal growth for each size of charity?"):
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


# ---------- page 3: check a list ----------
def page_list() -> None:
    st.markdown("### Check a list of charities")
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
                    s = summary_of(rec)
                    pr = A.priority(s)
                    latest = s["years"][-1] if s["years"] else {}
                    bits = [f"Income {A.money(latest.get('income'))}"]
                    if s["income_direction"]:
                        bits.append(f"{A.LABELS[s['income_direction']]} {A.pct_abs(s['income_change'], s['income_change_abs'])} over 3 years")
                        bits.append(f"{PEER_SHORT[s['income_trend']]} similar charities")
                    else:
                        bits.append(A.LABELS.get(s["status"], s["status"]))
                    if latest.get("net") is not None:
                        bits.append(A.net_label(latest["net"]))
                    tag = " · high % growth from a small base" if s["small_base_growth"] else " · hot prospect" if s["hot"] else ""
                    bits.append(f"{A.PRIORITY_LABELS[pr['level']]} priority" + tag)
                    rows.append({"reg": n, "name": rec["name"], "line": " · ".join(bits)})
                    export_rows.append(
                        {
                            "reg_number": n, "name": rec["name"], "priority": pr["level"], "latest_total_income": latest.get("income"),
                            "latest_total_expenditure": latest.get("expenditure"), "latest_net_surplus_or_deficit": latest.get("net"),
                            "income_direction_3yr": s["income_direction"], "income_change_3yr_pct": s["income_change"],
                            "income_change_3yr_gbp": s["income_change_abs"], "small_base": s["small_base"],
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
                st.download_button(
                    "Download as a spreadsheet (CSV)",
                    pd.DataFrame(export_rows).to_csv(index=False),
                    "charity_list_check.csv",
                    "text/csv",
                    icon=":material/download:",
                )
            if missing:
                st.warning(f"Not found on the register (check the numbers): {', '.join(map(str, missing))}")
            for e in errors:
                st.error(e)


# ---------- outreach ----------
CHANNEL_ICON = {"email": ":material/mail:", "call": ":material/call:", "linkedin": ":material/work:"}


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


# ---------- page 4: my prospects ----------
def page_my() -> None:
    st.markdown("### My prospects")
    st.caption(
        "Each saved charity gets an outreach plan: why it may be worth contacting, when to get in touch, and drafts for "
        "4 steps (first email with your Calendly link, follow-up email, phone call, LinkedIn). Nothing is sent for you."
    )
    if need_api():
        cfg = STORE.settings
        with st.expander(
            "Your name and Calendly link (used to sign every email)", icon=":material/edit:", expanded=not (cfg.get("name") and cfg.get("calendly"))
        ):
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
                "Timing is an **estimate**: we know when each charity's financial year ends (from its accounts), not when it "
                "actually sets its budget. Change the months above if you know better."
            )

        if not len(STORE):
            st.info(
                "**No prospects yet.** Look up a charity or use **Find new prospects**, then press **Add to prospects**. Its outreach plan will appear here."
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
                    s = summary_of(rec)
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
            m4.metric("Meetings booked", int((table["Outcome"] == "Meeting booked").sum()))

            # One row per prospect with an "Open plan" button (no tick boxes).
            if st.session_state.get("plan_reg") not in set(table["reg"]):
                st.session_state["plan_reg"] = table.iloc[0]["reg"]
            for row in table.to_dict("records"):
                current = row["reg"] == st.session_state["plan_reg"]
                due = row.get("Due") if isinstance(row.get("Due"), date) else None
                with st.container(border=True):
                    c1, c2 = st.columns([6, 1.4], vertical_alignment="center")
                    when = (f" · due {fmt_day(due)}" + (" · :orange[overdue]" if due < today else "")) if due else ""
                    c1.markdown(
                        f"{row.get('Priority') or ''} **{row['Charity']}** · {row.get('Why') or ''}  \n"
                        f":gray[Next: {row.get('Next action') or '–'}{when} · Outcome: {row['Outcome']} · "
                        f"Best time (estimate): {row.get('Best time (estimate)') or '–'}]"
                    )
                    if c2.button("Showing below" if current else "Open plan", key=f"open_{row['reg']}", disabled=current, width="stretch"):
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
            st.download_button(
                "Download all plans as a spreadsheet (CSV)",
                pd.DataFrame(export).to_csv(index=False),
                "outreach_sequences.csv",
                "text/csv",
                icon=":material/download:",
            )

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
                h4.button("Remove", icon=":material/delete:", key=f"rm_{reg}", on_click=_remove, args=(reg,), width="stretch")

                act, due = O.next_action(item, plan)
                st.markdown(f"**Next action:** {act}" + (f" · due **{fmt_day(due)}**" if due else "") + (" · :orange[overdue]" if due and due < today else ""))
                if item["outcome"] != "Active":
                    st.info(f"Sequence stopped: **{item['outcome']}**. Set the outcome back to Active to carry on.")

                p1, p2 = st.columns([1.1, 1])
                with p1:
                    st.markdown(f"**Why this charity may be worth contacting:** {A.PRIORITY_LABELS[pr['level']]} priority")
                    for r in pr["reasons"]:
                        st.markdown(f"- {r}")
                    st.markdown("**Financial direction** (from the accounts)")
                    st.write(plan["summary"])
                with p2:
                    st.markdown("**Facts the email opens with** (from the accounts)")
                    for hk in plan["hooks"]:
                        if hk["key"] == "fallback":
                            continue
                        used = "email 1" if hk is plan["primary"] else "email 2" if hk is plan["secondary"] else "call only" if not hk["email_safe"] else "call"
                        st.markdown(f"- **{hk['title']}** ({used}): {hk['fact']}")
                    if plan["primary"]["key"] == "fallback":
                        st.caption("No strong signal in the filings, so the email uses a general opener about size and sector.")
                    st.markdown("**Suggested time to get in touch** (estimate)")
                    (st.success if tm["now"] else st.info)(f"{tm['text']}  \n**Recommended outreach period:** {tm['period']}.  \n{tm['guidance']}")

                k1, k2 = st.columns(2)
                with k1:
                    st.markdown("**Who to contact**")
                    st.markdown(f"Email to: **{c['to']['who']}**")
                    links = []
                    if c["email"]:
                        links.append(f"Email: [{c['email']}](mailto:{c['email']})")
                    if c["phone"]:
                        links.append(f"Phone: [{c['phone']}](tel:{c['phone'].replace(' ', '')})")
                    if c["website"]:
                        site = c["website"] if c["website"].startswith("http") else f"https://{c['website']}"
                        links.append(f"Website: [{c['website']}]({site})")
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
                tcol1.markdown("**Drafts for you to edit**: tick each step when done")
                tcol2.download_button(
                    "Download this plan",
                    O.plan_markdown(rec, s, plan, item),
                    f"outreach_plan_{reg}.md",
                    "text/markdown",
                    icon=":material/download:",
                    width="stretch",
                    on_click="ignore",
                )
                tcol3.button(
                    "Regenerate drafts",
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
                    label = f"{':material/check_circle:' if done else CHANNEL_ICON[stp['channel']]}  Day {d} · {fmt_day(stp['date'])} · {stp['title']}" + (
                        " · :orange[overdue]" if late else ""
                    )
                    with st.expander(label, expanded=not done and item["outcome"] == "Active" and d == first_open):
                        st.checkbox("Done", value=done, key=f"done_{reg}_{d}", on_change=_set_done, args=(reg, d, f"done_{reg}_{d}"))
                        if stp["channel"] == "email":
                            to = st.text_input("To", stp["to"] or "", key=f"txt_{reg}_{d}_to")
                            subj = st.text_input("Subject", stp["subject"], key=f"txt_{reg}_{d}_subj")
                            body = st.text_area("Message (edit freely)", stp["body"], key=f"txt_{reg}_{d}_body", height=330)
                            b1, _ = st.columns([1, 3])
                            b1.link_button("Open in my email app", O.mailto(to, subj, body), icon=":material/mail:", width="stretch")
                            st.caption("Or copy it: hover the box below and click the copy icon.")
                            st.code(f"Subject: {subj}\n\n{body}", language=None, wrap_lines=True)
                        elif stp["channel"] == "call":
                            notes = st.text_area("Call script (edit freely)", stp["body"], key=f"txt_{reg}_{d}_body", height=380)
                            if c["phone"]:
                                st.link_button(f"Call {c['phone']}", f"tel:{c['phone'].replace(' ', '')}", icon=":material/call:")
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


# ---------- pages ----------
# The look-up page is the default: it answers the core questions for one charity on one screen.
# Everything else is a clearly labelled secondary page.
nav = st.navigation(
    [
        st.Page(page_lookup, title="Look up a charity", icon=":material/search:", url_path="lookup", default=True),
        st.Page(page_prospects, title="Find new prospects", icon=":material/travel_explore:", url_path="find"),
        st.Page(page_list, title="Check a list", icon=":material/checklist:", url_path="list"),
        st.Page(page_my, title=f"My prospects ({len(STORE)})", icon=":material/star:", url_path="my-prospects"),
        st.Page(page_settings, title="Settings", icon=":material/settings:", url_path="settings"),
    ],
    position="top",
)
nav.run()
