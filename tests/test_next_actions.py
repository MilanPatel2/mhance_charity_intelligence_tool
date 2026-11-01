"""My prospects: the action queue, default selection, and timing vs due dates."""

from datetime import date

import analysis as A
import outreach as O

TODAY = date(2026, 11, 2)  # a Monday


def rec(year_end="2025-03-31", email="info@test.org", phone="020 7946 0000", income=(2_000_000, 2_300_000, 2_600_000)):
    fin = [{"period_end": f"{2023 + i}{year_end[4:]}", "income": v, "expenditure": v * 0.95} for i, v in enumerate(income)]
    return {
        "reg_number": 1,
        "name": "THE TEST TRUST",
        "financials": fin,
        "profile": {"Email": email, "Phone": phone, "Website": "test.org"},
        "trustees": [{"name": "Jane Smith", "is_chair": True, "appointed": "2020-01-01"}],
    }


def plan_for(r, start=TODAY, early=False, started=False, today=TODAY):
    s = A.summarise(r["financials"], today=today)
    return O.build_plan(r, s, {"name": "M"}, start, today, early=early, started=started)


def item(**kw):
    return {"outcome": "Active", "done": {}, "snooze_until": None, **kw}


# ---------- timing vs due dates ----------
def test_window_open_first_email_is_due_now():
    p = plan_for(rec("2025-03-31"))  # year ends 31 Mar: estimated window Oct 2026 - Jan 2027, open
    assert p["timing"]["now"] and not p["schedule"]["waiting"]
    a = O.next_action(item(), p)
    assert a["label"] == "Send the first email" and a["due"] == TODAY


def test_window_months_away_never_asks_for_an_email_now():
    p = plan_for(rec("2025-08-31"))  # year ends 31 Aug: window Feb - Jun 2027
    assert not p["timing"]["now"] and p["timing"]["window"][0] == date(2027, 2, 28)
    assert p["steps"][0]["date"] == date(2027, 3, 1)  # first email inside the window (28 Feb is a Sunday)
    a = O.next_action(item(), p)
    assert a["label"] == "Research the Finance Director" and a["day"] == O.PREP
    assert a["due"] < p["steps"][0]["date"] and "estimated planning window" in a["note"]
    # once the research is done, the email is due when the window opens, not before
    a2 = O.next_action(item(done={O.PREP: True}), p)
    assert a2["label"] == "Send the first email" and a2["due"] >= p["timing"]["window"][0]


def test_early_relationship_building_is_labelled():
    p = plan_for(rec("2025-08-31"), early=True)
    a = O.next_action(item(early=True), p)
    assert a["due"] == TODAY and a["note"].startswith("Early relationship-building")
    assert "early relationship-building" in O.why_now(p)[0]


def test_a_started_sequence_is_not_moved_by_the_window():
    p = plan_for(rec("2025-08-31"), started=True)
    assert p["steps"][0]["date"] == TODAY and not p["schedule"]["waiting"]
    a = O.next_action(item(done={"0": True}), p)
    assert a["label"] == "Send the follow-up email" and a["due"] == O.add_working_days(TODAY, 3)


def test_timing_is_always_called_an_estimate():
    head, caveat = O.why_now(plan_for(rec("2025-08-31")))
    assert "Possible" in head and "not confirmed buying intent" in caveat


# ---------- queue ----------
def row(reg, priority, due=None, outcome="Active", in_window=False):
    return {"reg": reg, "name": reg, "priority": priority, "in_window": in_window, "action": {"due": due, "actionable": outcome == "Active"}}


def test_queue_order_and_no_action_group():
    rows = O.order_queue(
        [
            row("replied", A.HIGH, outcome="Replied"),
            row("later", A.HIGH, date(2027, 3, 1)),
            row("window", A.MEDIUM, date(2026, 11, 5), in_window=True),
            row("today", A.LOW, TODAY),
            row("overdue", A.MEDIUM, date(2026, 10, 28)),
            row("missing", A.MEDIUM, None),
        ],
        TODAY,
    )
    assert [r["reg"] for r in rows] == ["overdue", "today", "window", "later", "missing", "replied"]
    assert rows[-1]["group"] == O.NO_ACTION


def test_same_group_sorts_by_due_then_priority_then_name():
    d = date(2026, 12, 1)
    rows = O.order_queue([row("b", A.LOW, d), row("c", A.HIGH, d), row("a", A.HIGH, d), row("z", A.LOW, date(2026, 11, 20))], TODAY)
    assert [r["reg"] for r in rows] == ["z", "a", "c", "b"]


def test_default_selection_skips_low_and_stopped_records():
    rows = O.order_queue([row("low", A.LOW, TODAY), row("med", A.MEDIUM, date(2027, 1, 5)), row("replied", A.HIGH, outcome="Replied")], TODAY)
    assert O.default_selection(rows) == "med"
    only_low = O.order_queue([row("replied", A.HIGH, outcome="Replied"), row("low", A.LOW, date(2027, 1, 5))], TODAY)
    assert O.default_selection(only_low) == "low"
    assert O.default_selection(O.order_queue([row("replied", A.HIGH, outcome="Replied")], TODAY)) is None


def test_not_relevant_and_snooze():
    p = plan_for(rec())
    assert O.next_action(item(outcome="Not relevant"), p)["actionable"] is False
    a = O.next_action(item(snooze_until="2026-11-09"), p)
    assert a["due"] == date(2026, 11, 9) and a["snoozed"]


def test_finished_sequence_asks_for_an_outcome():
    p = plan_for(rec())
    a = O.next_action(item(done={str(d): True for d, _, _ in O.STEPS}), p)
    assert a["actionable"] and a["due"] and "set the outcome" in a["label"]


# ---------- missing data ----------
def test_missing_year_end_and_contacts():
    r = rec(email=None, phone=None)
    r["financials"] = []
    p = plan_for(r)
    assert p["timing"]["window"] is None and p["steps"][0]["date"] == TODAY
    head, _ = O.why_now(p)
    assert "isn't known" in head
    assert O.provenance(A.summarise([], today=TODAY))[0].startswith("Charity Commission · no accounts on record")
    assert O.account_reasons(p)  # still says something, never crashes
    assert p["contact"]["buyer"] == "Chief Executive"  # no income on record: treated as a small charity


def test_reasons_are_short_and_cite_fit():
    p = plan_for(rec())
    rs = O.account_reasons(p)
    assert 1 <= len(rs) <= 2 and any("£1m–£100m" in r for r in rs)
