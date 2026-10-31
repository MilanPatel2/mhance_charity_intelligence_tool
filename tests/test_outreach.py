from datetime import date

import analysis as A
import outreach as O

TODAY = date(2026, 10, 31)  # a Saturday
BENCH = {"£25m–£100m": {"income": 0.095, "expenditure": 0.127, "n": 463}, "£1m–£5m": {"income": 0.099, "expenditure": 0.127, "n": 5596}}
SETTINGS = {"name": "Milan Patel", "role": "Business Development", "calendly": "https://calendly.com/milan/20min"}


def nacro_like():
    # shaped like the real API response for Nacro (226171)
    fin = [
        {"period_end": "2023-03-31", "income": 68_659_000, "expenditure": 70_000_000, "govt_contracts": 50_199_000, "trading": 0},
        {"period_end": "2024-03-31", "income": 77_032_000, "expenditure": 76_000_000, "govt_contracts": 56_763_000, "trading": 0},
        {"period_end": "2025-03-31", "income": 90_328_000, "expenditure": 88_000_000, "govt_contracts": 90_328_000, "trading": 0},
    ]
    return {
        "reg_number": 226171,
        "name": "NACRO",
        "financials": fin,
        "profile": {
            "Email": "anna.barker@nacro.org.uk",
            "Phone": "0300 123 1889",
            "Website": "www.nacro.org.uk",
            "Employees": 873,
            "Volunteers": 97,
            "Sectors": "Education/training | Accommodation/housing",
        },
        "trustees": [
            {"name": "NICHOLAS LIONEL HARDWICK", "is_chair": True, "appointed": "2022-07-20"},
            {"name": "Joanne Harper", "is_chair": False, "appointed": "2025-08-01"},
        ],
    }


def test_names():
    assert O.nice_name("THE JIGSAW TRUST") == "The Jigsaw Trust"
    assert O.nice_name("NACRO") == "NACRO"
    assert O.nice_name("THE CHURCH OF JESUS CHRIST (GREAT BRITAIN)") == "The Church of Jesus Christ (Great Britain)"
    assert O.nice_name("THE SOCIETY OF ST COLUMBAN FOR FOREIGN MISSIONS") == "The Society of St Columban for Foreign Missions"
    assert O.person("NICHOLAS LIONEL HARDWICK")["salutation"] == "Dear Nicholas"
    assert O.person("Professor Sir John Irving Bell")["salutation"] == "Dear Sir John"
    assert O.person("Dr Glenn Wells")["salutation"] == "Dear Dr Wells"
    assert O.person("Ciaran Martin CB")["salutation"] == "Dear Ciaran"
    assert O.person("")["salutation"] == "Dear Trustees"


def test_working_day_and_sequence_dates():
    assert O.working_day(date(2026, 10, 31)) == date(2026, 11, 2)  # Sat -> Mon
    plan = O.build_plan(nacro_like(), A.summarise(nacro_like()["financials"], BENCH, today=TODAY), SETTINGS, TODAY, TODAY)
    days = [(s["day"], s["date"]) for s in plan["steps"]]
    assert days == [(0, date(2026, 11, 2)), (3, date(2026, 11, 5)), (5, date(2026, 11, 9)), (7, date(2026, 11, 11))]
    assert all(s["date"].weekday() < 5 for s in plan["steps"])


def test_nacro_hooks_and_email():
    rec = nacro_like()
    s = A.summarise(rec["financials"], BENCH, today=TODAY)
    plan = O.build_plan(rec, s, SETTINGS, TODAY, TODAY)
    keys = [h["key"] for h in plan["hooks"]]
    assert keys[0] == "growth"  # hot (+17%) and above peers (+32% vs +9.5%)
    assert "contracts" in keys and "scale" in keys
    assert plan["secondary"]["key"] == "contracts"
    e1 = plan["steps"][0]
    assert e1["to"] == "anna.barker@nacro.org.uk"
    assert e1["body"].startswith("Dear Anna,")  # named inbox -> greet the person who owns it
    assert "https://calendly.com/milan/20min" in e1["body"]
    assert "grew 17% last year to £90.3m, and 32% over three years" in e1["body"]
    e2 = plan["steps"][1]["body"]
    assert "I also noticed almost all of NACRO's income now comes from government contracts" in e2
    assert "noticed i " not in e2.lower().replace("noticed in", "")
    assert plan["steps"][1]["subject"].startswith("Re: ")
    assert "0300 123 1889" in plan["steps"][2]["body"]
    assert len(plan["steps"][3]["body"]) <= O.LINKEDIN_LIMIT


def test_costs_hook_never_opens_an_email():
    rec = nacro_like()
    rec["financials"] = [dict(f, expenditure=f["income"] * 1.3, govt_contracts=None) for f in rec["financials"]]
    rec["profile"]["Employees"] = 0
    rec["profile"]["Email"] = "info@example.org"
    rec["trustees"] = []
    s = A.summarise(rec["financials"], BENCH, today=TODAY)
    plan = O.build_plan(rec, s, SETTINGS, TODAY, TODAY)
    assert "costs" in [h["key"] for h in plan["hooks"]]
    assert plan["primary"]["key"] != "costs"
    assert "Dear Trustees" in plan["steps"][0]["body"]


def test_fallback_when_nothing_fires():
    rec = nacro_like()
    rec["financials"] = [{"period_end": f"{2023 + i}-03-31", "income": 2e6, "expenditure": 1.9e6} for i in range(3)]
    rec["profile"].update(Employees=10, Volunteers=5)
    rec["trustees"] = [{"name": "Jane Smith", "is_chair": True, "appointed": "2015-01-01"}]
    plan = O.build_plan(rec, A.summarise(rec["financials"], BENCH, today=TODAY), SETTINGS, TODAY, TODAY)
    assert plan["primary"]["key"] == "fallback"
    assert "education/training" in plan["steps"][0]["body"]


def test_budget_timing():
    t = O.budget_timing("2025-03-31", TODAY)  # year ends 31 March, window Oct-Jan
    assert t["fy_end"] == date(2027, 3, 31) and t["now"] is True
    t = O.budget_timing("2025-09-30", TODAY)  # window Mar-Jul
    assert t["now"] is False and "March" in t["text"]


def test_mailto_encodes():
    m = O.mailto("a@b.org", "Hi & bye", "Line 1\nLine 2")
    assert m.startswith("mailto:a%40b.org?subject=Hi%20%26%20bye&body=Line%201%0ALine%202")


def test_recipient_matches_inbox():
    chair = O.person("Jane Smith")
    assert O.recipient("jane.smith@x.org", chair)["salutation"] == "Dear Jane"
    assert O.recipient("smithj@x.org", chair)["salutation"] == "Dear Jane"  # chair's own inbox
    assert O.recipient("anna.barker@x.org", chair)["salutation"] == "Dear Anna"  # someone else's
    assert O.recipient("info@x.org", chair)["salutation"] == "Dear Jane"  # generic -> chair
    assert O.recipient("accounts@x.org", None)["salutation"] == "Dear Trustees"
    assert O.recipient(None, None)["salutation"] == "Dear Trustees"
