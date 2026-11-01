"""Look up a charity: search ranking and this session's recent searches."""

from data_sources import rank_search_hits
from prospects import add_recent


def hits(*names):
    return [{"reg_number": i + 1, "name": n} for i, n in enumerate(names)]


def test_exact_then_starts_with_then_contains():
    h = hits("FRIENDS OF OXFAM BOOKSHOP", "OXFAM TRADING", "THE OXFAM", "OXFORD CHARITY")
    ranked = [x["name"] for x in rank_search_hits(h, "oxfam", {2: 50_000_000})]
    assert ranked == ["THE OXFAM", "OXFAM TRADING", "FRIENDS OF OXFAM BOOKSHOP", "OXFORD CHARITY"]


def test_ties_go_to_the_larger_charity_and_partial_names_work():
    h = hits("CANCER RESEARCH WALES", "CANCER RESEARCH UK", "CANCER RESEARCH HULL")
    ranked = [x["name"] for x in rank_search_hits(h, "cancer res", {2: 700_000_000, 1: 5_000_000})]
    assert ranked == ["CANCER RESEARCH UK", "CANCER RESEARCH WALES", "CANCER RESEARCH HULL"]
    assert rank_search_hits([], "x") == []


def test_punctuation_and_case_are_ignored():
    h = hits("ST. JOHN AMBULANCE", "ST JOHN'S CHURCH")
    assert rank_search_hits(h, "st john ambulance")[0]["name"] == "ST. JOHN AMBULANCE"


def test_recent_newest_first_no_duplicates_limited():
    r = []
    for reg in (1, 2, 3):
        r = add_recent(r, {"reg": reg, "name": str(reg)})
    assert [x["reg"] for x in r] == [3, 2, 1]
    r = add_recent(r, {"reg": "1", "name": "1"})  # reopened (as text): moves to the front, no duplicate
    assert [x["reg"] for x in r] == [1, 3, 2]
    for reg in range(10, 20):
        r = add_recent(r, {"reg": reg, "name": str(reg)})
    assert len(r) == 5 and r[0]["reg"] == 19


# ---------- type-ahead suggestions ----------
import pandas as pd  # noqa: E402

from data_sources import name_index, search_variants, suggest  # noqa: E402

INDEX = name_index(
    pd.DataFrame(
        {
            "reg_number": [295672, 202918, 1083581, 1089464, 1167290, 226171, 226121, 205846],
            "name": [
                "MAKE-A-WISH FOUNDATION UK",
                "OXFAM",
                "THE COX FAMILY CHRISTIAN TRUST",
                "CANCER RESEARCH UK",
                "CANCER RESEARCH WALES",
                "NACRO",
                "PROSPER WAKEFIELD DISTRICT LTD",
                "THE NATIONAL TRUST FOR PLACES OF HISTORIC INTEREST",
            ],
            "latest_income": [20e6, 339e6, 1e5, 734e6, 5e6, 90e6, 2e6, 766e6],
        }
    )
)


def names(q):
    return [x["name"] for x in suggest(INDEX, q)]


def test_punctuation_and_spaces_dont_matter():
    for q in ("make a wish", "make-a-wish", "Make A Wish", "makeawish", "make a"):
        assert names(q)[0] == "MAKE-A-WISH FOUNDATION UK", q


def test_suggestions_rank_and_stay_tight():
    assert names("oxfam") == ["OXFAM"]  # not "cOX FAMily"
    assert names("cancer res") == ["CANCER RESEARCH UK", "CANCER RESEARCH WALES"]  # larger first
    assert names("national trust")[0].startswith("THE NATIONAL TRUST")  # leading "the" ignored
    assert names("x") == [] and names("") == []


def test_numbers_match_from_the_start():
    assert [x["reg"] for x in suggest(INDEX, "2261")] == [226171, 226121]
    assert [x["reg"] for x in suggest(INDEX, "226171")] == [226171]
    assert suggest(INDEX, "9999") == []


def test_live_register_spellings():
    assert search_variants("make a wish") == ["make a wish", "make-a-wish"]
    assert search_variants("  st. john's  ")[0] == "st. john's"
