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
