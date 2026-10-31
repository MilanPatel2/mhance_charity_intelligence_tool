from datetime import date

import pandas as pd
import pytest

import analysis as A

TODAY = date(2026, 10, 31)
BENCH = {"£100k–£500k": {"income": 0.10, "expenditure": 0.08, "n": 100},
         "£10k–£100k": {"income": 0.09, "expenditure": 0.09, "n": 100}}


def hist(*incomes, exp=None, start=2022):
    exp = exp or incomes
    return [{"period_end": f"{start + i}-03-31", "income": inc, "expenditure": e}
            for i, (inc, e) in enumerate(zip(incomes, exp))]


def test_size_bands():
    assert A.size_band(5_000) is None
    assert A.size_band(10_000) == "£10k–£100k"
    assert A.size_band(4_999_999) == "£1m–£5m"
    assert A.size_band(5_000_000) == "£5m–£10m"
    assert A.size_band(2e8) == "Over £100m"


def test_trend_is_relative_to_peers():
    # +12% over 3 yrs vs peer median +10% -> within 5 points -> In line
    s = A.summarise(hist(200e3, 205e3, 224e3), BENCH, today=TODAY)
    assert s["status"] == A.OK and s["size_band"] == "£100k–£500k"
    assert s["income_trend"] == A.INLINE
    # +30% -> 20 points above peers
    assert A.summarise(hist(200e3, 230e3, 260e3), BENCH, today=TODAY)["income_trend"] == A.ABOVE
    # +2% -> 8 points below peers, even though income went up in cash terms
    assert A.summarise(hist(200e3, 202e3, 204e3), BENCH, today=TODAY)["income_trend"] == A.BELOW


def test_under_three_years_marked_separately():
    s = A.summarise(hist(150e3, 300e3), BENCH, today=TODAY)
    assert s["status"] == A.NEW and s["income_trend"] == A.NEW and s["hot"] is False


def test_tiny_base_marked_separately():
    s = A.summarise(hist(0, 50e3, 60e3), BENCH, today=TODAY)
    assert s["status"] == A.SMALL and s["hot"] is False


def test_sickle_cell_filing_error_is_check_data():
    # real figures from the register (charity 1162402): £86k -> £88.9m
    h = hist(36_699, 55_863, 136_809, 86_341, 88_933_000,
             exp=[55_079, 64_099, 68_677, 98_446, 125_141_000], start=2021)
    s = A.summarise(h, BENCH, today=TODAY)
    assert s["status"] == A.CHECK
    assert s["income_trend"] == A.CHECK and s["hot"] is False and s["spike"] is False


def test_hot_and_spike():
    s = A.summarise(hist(100e3, 105e3, 120e3), BENCH, today=TODAY)
    assert s["hot"] is True and s["spike"] is False
    s = A.summarise(hist(50e3, 60e3, 200e3), BENCH, today=TODAY)
    assert s["hot"] is True and s["spike"] is True


def test_uses_last_three_returns_and_yoy_looks_back():
    s = A.summarise(hist(10e3, 100e3, 100e3, 100e3), BENCH, today=TODAY)
    assert len(s["years"]) == 3 and s["income_change"] == 0
    assert s["years"][0]["income_yoy"] == pytest.approx(9.0)


def test_stale_flag():
    assert A.summarise(hist(1e5, 1e5, 1e5), today=TODAY)["stale"] is True
    assert A.summarise(hist(1e5, 1e5, 1e5), today=date(2025, 1, 1))["stale"] is False


def test_vectorised_matches_single():
    cases = {1: hist(200e3, 205e3, 224e3), 2: hist(200e3, 230e3, 260e3), 3: hist(150e3, 300e3),
             4: hist(0, 50e3, 60e3), 5: hist(36_699, 55_863, 136_809, 86_341, 88_933_000, start=2021),
             6: hist(50e3, 60e3, 200e3), 7: hist(10e3, 100e3, 100e3, 100e3), 8: hist(200e3, 202e3, 204e3)}
    rows = [{"org_number": org, **r} for org, h in cases.items() for r in h]
    t = A.apply_trends(A.base_table(pd.DataFrame(rows), today=TODAY), BENCH).set_index("org_number")
    for org, h in cases.items():
        s = A.summarise(h, BENCH, today=TODAY)
        assert t.loc[org, "status"] == s["status"], org
        assert t.loc[org, "income_trend"] == s["income_trend"], org
        assert t.loc[org, "expenditure_trend"] == s["expenditure_trend"], org
        assert bool(t.loc[org, "hot"]) == s["hot"], org
        assert bool(t.loc[org, "spike"]) == s["spike"], org


def test_benchmarks_only_use_ok_up_to_date_charities():
    rows = []
    for org, h in {1: hist(100e3, 110e3, 120e3, start=2023), 2: hist(100e3, 100e3, 140e3, start=2023),
                   3: hist(100e3, 100e3, 900e3, start=2020), 4: hist(1e5, 2e5, start=2024)}.items():
        rows += [{"org_number": org, **r} for r in h]
    b = A.benchmarks(A.base_table(pd.DataFrame(rows), today=TODAY))
    assert b["£100k–£500k"]["n"] == 2  # stale (3) and under-3-years (4) excluded
    assert b["£100k–£500k"]["income"] == pytest.approx(0.3)


def test_money():
    assert A.money(339_366_903) == "£339.4m"
    assert A.money(45_200) == "£45k"
    assert A.money(None) == "–"
