import json
from datetime import date

import pandas as pd
import pytest

import analysis as A
import outreach as O
from prospects import ProspectStore

TODAY = date(2026, 10, 31)
BENCH = {"£1m–£5m": {"income": 0.10, "expenditure": 0.12, "n": 5000}}


def hist(*incomes, exp=None, ends=None):
    exp = exp or incomes
    ends = ends or [f"{2023 + i}-03-31" for i in range(len(incomes))]  # latest 2025: up to date
    return [{"period_end": e, "income": i, "expenditure": x} for e, i, x in zip(ends, incomes, exp, strict=True)]


# ---------- direction (the brief's up / flat / down) ----------
def test_direction_up_flat_down():
    assert A.summarise(hist(2e6, 2.1e6, 2.3e6), BENCH, today=TODAY)["income_direction"] == A.UP  # +15%
    assert A.summarise(hist(2e6, 2.0e6, 2.06e6), BENCH, today=TODAY)["income_direction"] == A.FLAT  # +3%
    assert A.summarise(hist(2e6, 1.9e6, 1.8e6), BENCH, today=TODAY)["income_direction"] == A.DOWN  # -10%
    assert A.summarise(hist(2e6, 2.1e6), BENCH, today=TODAY)["income_direction"] is None  # <3 returns


def test_up_in_cash_terms_can_still_be_below_peers():
    s = A.summarise(hist(2e6, 2.05e6, 2.12e6), BENCH, today=TODAY)  # +6% vs peers +10%
    assert s["income_direction"] == A.UP and s["income_trend"] == A.INLINE
    s = A.summarise(hist(2e6, 2.0e6, 2.0e6), BENCH, today=TODAY)
    assert s["income_direction"] == A.FLAT and s["income_trend"] == A.BELOW


# ---------- ordering and missing years ----------
def test_unsorted_input_is_ordered_chronologically():
    s = A.summarise(list(reversed(hist(2e6, 2.2e6, 2.42e6))), BENCH, today=TODAY)
    assert [y["period_end"] for y in s["years"]] == ["2023-03-31", "2024-03-31", "2025-03-31"]
    assert s["income_yoy"] == pytest.approx(0.10)


def test_missing_reporting_year_is_flagged_not_filled():
    s = A.summarise(hist(2e6, 2.1e6, 2.3e6, ends=["2022-03-31", "2024-03-31", "2025-03-31"]), BENCH, today=TODAY)
    assert s["gaps"] == [("2022-03-31", "2024-03-31")]
    assert len(s["years"]) == 3  # nothing invented
    assert any("missing" in r for r in A.priority(s)["reasons"])


# ---------- priority ----------
def test_priority_levels_and_reasons():
    hot_above = A.summarise(hist(2e6, 2.2e6, 2.6e6), BENCH, today=TODAY)  # +18% YoY, +30% vs peers 10%
    p = A.priority(hot_above)
    assert p["level"] == A.HIGH and any("hot-prospect rule" in r for r in p["reasons"]) and any("ahead of" in r for r in p["reasons"])
    hot_only = A.summarise(hist(2e6, 1.9e6, 2.15e6), BENCH, today=TODAY)  # +13% YoY, +7.5% over 3 yrs (in line)
    assert A.priority(hot_only)["level"] == A.MEDIUM
    flat = A.summarise(hist(2e6, 2e6, 2e6), BENCH, today=TODAY)
    assert A.priority(flat)["level"] == A.LOW
    check = A.summarise(hist(80e3, 86e3, 88e6), BENCH, today=TODAY)
    assert A.priority(check)["level"] == A.CHECK_FIRST
    stale = A.summarise(hist(2e6, 2.2e6, 2.6e6), BENCH, today=date(2027, 6, 1))
    assert A.priority(stale)["level"] == A.LOW and "overdue" in A.priority(stale)["reasons"][0]


def test_vectorised_priority_and_direction_match_single():
    cases = {
        1: hist(2e6, 2.2e6, 2.6e6),
        2: hist(2e6, 1.9e6, 2.15e6),
        3: hist(2e6, 2e6, 2e6),
        4: hist(80e3, 86e3, 88e6),
        5: hist(2e6, 2.1e6),
        6: hist(2e6, 1.9e6, 1.8e6),
    }
    rows = [{"org_number": k, **r} for k, h in cases.items() for r in h]
    t = A.apply_trends(A.base_table(pd.DataFrame(rows), today=TODAY), BENCH).set_index("org_number")
    for k, h in cases.items():
        s = A.summarise(h, BENCH, today=TODAY)
        assert t.loc[k, "priority"] == A.priority(s)["level"], k
        assert t.loc[k, "income_direction"] == s["income_direction"], k


# ---------- saved prospects ----------
def test_store_dedupes_and_persists(tmp_path):
    f = tmp_path / "outreach.json"
    st = ProspectStore(f)
    assert st.add([(226171, "NACRO"), (226171, "NACRO"), (202918, "OXFAM")], TODAY) == 2
    assert st.add([(226171, "NACRO")], TODAY) == 0  # already saved
    assert len(st) == 2 and 226171 in st and "226171" in st.items
    st.set_done(226171, 0, True)
    st.update(226171, outcome="Replied", notes="Spoke to Anna", start=date(2026, 11, 9))
    again = ProspectStore(f)  # simulates reloading the app
    assert again.items["226171"]["outcome"] == "Replied"
    assert again.items["226171"]["done"] == {"0": True}
    assert again.items["226171"]["start"] == "2026-11-09"
    again.remove(202918)
    assert 202918 not in ProspectStore(f)


def test_store_reads_existing_format_and_survives_corrupt_file(tmp_path):
    f = tmp_path / "outreach.json"
    f.write_text(
        json.dumps(
            {
                "settings": {"name": "Milan Patel", "calendly": ""},
                "list": {"1099776": {"name": "MALARIA CONSORTIUM", "added": "2026-10-31", "start": "2026-11-02", "done": {}, "outcome": "Active", "notes": ""}},
            }
        )
    )
    st = ProspectStore(f)
    assert st.settings["name"] == "Milan Patel" and st.settings["budget_start_months"] == 6  # defaults filled in
    assert 1099776 in st
    f.write_text("{not json")
    assert len(ProspectStore(f)) == 0


# ---------- timing ----------
def test_timing_is_labelled_estimate_and_configurable():
    t = O.budget_timing("2025-03-31", TODAY)  # default 6-2 months: Oct-Jan
    assert t["now"] and t["text"].startswith("Estimate") and "not their confirmed budget cycle" in t["guidance"]
    t = O.budget_timing("2025-03-31", TODAY, start_months=4, end_months=1)  # Nov-Feb: not yet
    assert not t["now"] and t["window"] == (date(2026, 11, 30), date(2027, 2, 28))
    assert O.budget_timing(None, TODAY)["period"] == "Unknown"


# ---------- wording and export ----------
def _rec():
    return {
        "reg_number": 1,
        "name": "THE TEST TRUST",
        "financials": hist(2e6, 2.2e6, 2.6e6),
        "profile": {"Email": "info@test.org", "Phone": "0123", "Website": "test.org", "Employees": 0, "Volunteers": 0, "Sectors": ""},
        "trustees": [{"name": "Jane Smith", "is_chair": True, "appointed": "2010-01-01"}],
    }


def test_email_uses_careful_wording_and_no_invented_claims():
    rec = _rec()
    s = A.summarise(rec["financials"], BENCH, today=TODAY)
    body = O.build_plan(rec, s, {"name": "M", "role": "R", "calendly": "c"}, TODAY, TODAY)["steps"][0]["body"]
    assert "can mean" in body and "may start" in body
    for banned in ("usually means", "start to creak", "you need", "your systems are"):
        assert banned not in body


def test_plan_export_contains_everything():
    rec = _rec()
    s = A.summarise(rec["financials"], BENCH, today=TODAY)
    plan = O.build_plan(rec, s, {"name": "M", "role": "R", "calendly": "https://cal"}, TODAY, TODAY)
    md = O.plan_markdown(rec, s, plan, {"outcome": "Active", "done": {}, "notes": "call back"})
    for part in (
        "# Outreach plan: The Test Trust (#1)",
        "## Priority: High",
        "## Timing (estimate)",
        "Recommended outreach period",
        "Day 0",
        "Day 7",
        "call back",
        "Next action: Send the first email",
    ):
        assert part in md, part
    assert "Income £2.6m" in plan["summary"] and "up +30.0%" in plan["summary"]


# ---------- money terms and small charities ----------
def test_net_is_income_minus_expenditure_and_never_invented():
    h = hist(2e6, 2.1e6, 2.3e6, exp=[1.9e6, 2.2e6, 2.0e6])
    s = A.summarise(h, BENCH, today=TODAY)
    assert [y["net"] for y in s["years"]] == [pytest.approx(1e5), pytest.approx(-1e5), pytest.approx(3e5)]
    h[1]["expenditure"] = None  # missing figure stays missing
    assert A.summarise(h, BENCH, today=TODAY)["years"][1]["net"] is None
    assert A.net_label(3e5) == "£300k surplus" and A.net_label(-1e5) == "£100k deficit" and A.net_label(None) == "–"


def test_every_percentage_comes_with_its_pound_change():
    s = A.summarise(hist(2e6, 2.2e6, 2.6e6), BENCH, today=TODAY)
    assert s["income_change_abs"] == pytest.approx(6e5) and s["income_yoy_abs"] == pytest.approx(4e5)
    assert A.pct_abs(s["income_change"], s["income_change_abs"]) == "+30.0% (+£600k)"
    assert any("(+£400k)" in r for r in A.priority(s)["reasons"])


def test_small_base_growth_is_labelled_and_not_rewarded():
    s = A.summarise(hist(40e3, 45e3, 90e3), BENCH, today=TODAY)  # +100% YoY, but only +£45k
    assert s["hot"] and s["small_base"] and s["small_base_growth"]  # brief's hot rule still applies
    p = A.priority(s)
    assert p["level"] == A.LOW and any("High percentage growth from a small base" in r for r in p["reasons"])
    # same growth on a larger charity is rewarded
    big = A.summarise(hist(4e6, 4.5e6, 9e6), {"£1m–£5m": BENCH["£1m–£5m"]}, today=TODAY)
    assert not big["small_base"] and A.priority(big)["level"] == A.HIGH
    # threshold is configurable
    assert not A.summarise(hist(40e3, 45e3, 90e3), BENCH, today=TODAY, small=20e3)["small_base"]


def test_vectorised_small_base_matches_single():
    cases = {1: hist(40e3, 45e3, 90e3), 2: hist(2e6, 2.2e6, 2.6e6), 3: hist(150e3, 90e3, 140e3)}
    rows = [{"org_number": k, **r} for k, h in cases.items() for r in h]
    for small in (A.SMALL_CHARITY, 50e3):
        t = A.apply_trends(A.base_table(pd.DataFrame(rows), today=TODAY), BENCH, small=small).set_index("org_number")
        for k, h in cases.items():
            s = A.summarise(h, BENCH, today=TODAY, small=small)
            assert bool(t.loc[k, "small_base"]) == s["small_base"], (k, small)
            assert bool(t.loc[k, "small_base_growth"]) == s["small_base_growth"], (k, small)
            assert t.loc[k, "priority"] == A.priority(s)["level"], (k, small)
            assert t.loc[k, "income_change_abs"] == pytest.approx(s["income_change_abs"]), k
