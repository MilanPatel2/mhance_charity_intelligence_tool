"""Outreach plan for a charity: the hook, who to contact, when, and a 4-step sequence.

Rules-based on purpose: every sentence in a message comes from a template filled with
figures from the Charity Commission, so nothing can be invented. A salesperson edits
the draft before it goes out. (A planned next step is Azure OpenAI to generate tailored
outreach, with staff review before use; the facts would still come from here.)

HOOKS (strongest first; the best "email-safe" one opens the first email,
the next one is used in the day-3 follow-up, the top three go in the call script)
  growth      Hot (income +10% YoY) and/or growing faster than similar-sized charities
  contracts   Government contracts are 30%+ of income, or grew 20%+ over 3 returns
  trading     Trading income (shops, cafés, events) grew 25%+ and by £100k+
  leadership  New chair in the last 18 months, or 2+ trustees appointed in the last year
  scale       50+ staff or 200+ volunteers
  costs       Expenditure outgrew income / running a deficit. Phone only: it's too
              sensitive to open a cold email with.
  fallback    Size and sector, when nothing else fires

SEQUENCE (days are working days after day 0, so weekends are skipped and steps never clash)
  Day 0  Email 1: hook + who mhance is + Calendly link. Addressed to whoever the inbox
         belongs to: a named address (anna.barker@) gets "Dear Anna"; a generic one
         (info@) is addressed to the chair, from the trustee list.
  Day 3  Email 2: short follow-up with a second angle + Calendly
  Day 5  Phone call: script, discovery questions, voicemail
  Day 7  LinkedIn: connection note (under LinkedIn's 300-character limit)

SCHEDULING (so dates never contradict the timing estimate)
  Day 0 is the saved start date, unless the estimated planning window hasn't opened yet:
  then day 0 moves to the first working day of the window, and the current action until then
  is "Research the <buyer>" (due two weeks before). The salesperson can choose "early
  relationship-building" to contact sooner; the plan then says so. Once the first email is
  sent, dates are fixed from the day it went, so a later window can't move a live sequence.

ACTION QUEUE (My prospects, deterministic)
  1 overdue  2 due today  3 inside the estimated window  4 later  5 no action needed
  (replied, meeting booked, not interested, not relevant, paused). Within a group: earliest
  due date, then High > Medium > Low > Check first, then name. The first prospect opened is
  the first actionable one that isn't Low priority (else the first actionable one).
"""

from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote, quote_plus

import analysis as A

STEPS = [(0, "email", "First email"), (3, "email", "Follow-up email"), (5, "call", "Phone call"), (7, "linkedin", "LinkedIn connection")]
LINKEDIN_LIMIT = 300

TITLES = {
    "dr": "Dr",
    "doctor": "Dr",
    "professor": "Professor",
    "prof": "Professor",
    "sir": "Sir",
    "dame": "Dame",
    "lord": "Lord",
    "lady": "Lady",
    "baroness": "Baroness",
    "baron": "Baron",
    "rev": "Revd",
    "revd": "Revd",
    "reverend": "Revd",
    "canon": "Canon",
    "mr": "Mr",
    "mrs": "Mrs",
    "ms": "Ms",
    "miss": "Miss",
    "councillor": "Cllr",
    "cllr": "Cllr",
    "the": None,
}
POST_NOMINALS = {
    "cb",
    "cbe",
    "obe",
    "mbe",
    "kbe",
    "dbe",
    "bem",
    "qc",
    "kc",
    "jp",
    "dl",
    "phd",
    "frcp",
    "frcpch",
    "frs",
    "fca",
    "aca",
    "mp",
    "cvo",
    "lvo",
    "rn",
    "ma",
    "msc",
    "bsc",
    "ba",
    "mba",
    "llb",
}
SMALL_WORDS = {"of", "and", "the", "for", "in", "on", "at", "to", "a", "an", "&"}
KEEP_UPPER = {"UK", "NHS", "YMCA", "YWCA", "RSPCA", "NSPCC", "RNLI", "CIO", "UCL", "LGBT", "HIV", "MS"}  # 'CANCER RESEARCH UK' -> 'Cancer Research UK'


# ---------- names ----------
def nice_name(name: str) -> str:
    """'THE JIGSAW TRUST' -> 'The Jigsaw Trust'; leaves mixed-case and short acronyms alone."""
    name = (name or "").strip()
    if not name or not name.isupper():
        return name
    words = name.split()
    if len(words) == 1 and len(name) <= 6:  # NSPCC, NACRO, RNLI
        return name
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        if w.strip("().,") in KEEP_UPPER:
            out.append(w)
            continue
        if i and lw in SMALL_WORDS:
            out.append(lw)
            continue
        cap = lambda s: s[: (j := next((k for k, ch in enumerate(s) if ch.isalpha()), 0))] + s[j : j + 1].upper() + s[j + 1 :]  # '(GREAT' -> '(Great'
        out.append("-".join(cap(part) for part in lw.split("-")))  # 'MAKE-A-WISH' -> 'Make-A-Wish'
    return " ".join(out)


def person(name: str) -> dict:
    """Split a trustee name into title / first / last and build a salutation.
    'Professor Sir John Irving Bell' -> Dear Sir John; 'ROHAN STEELE' -> Dear Rohan."""
    raw = [w.strip(",.") for w in (name or "").split() if w.strip(",.")]
    if raw and all(w.isupper() for w in raw if w.isalpha()):
        raw = [w.capitalize() for w in raw]
    titles = []
    while raw and raw[0].lower() in TITLES:
        t = TITLES[raw.pop(0).lower()]
        if t:
            titles.append(t)
    while len(raw) > 1 and raw[-1].lower() in POST_NOMINALS:
        raw.pop()
    first, last = (raw[0], raw[-1]) if raw else ("", "")
    full = " ".join(titles + raw)
    if not raw:
        sal = "Dear Trustees"
    elif titles and titles[-1] in ("Sir", "Dame"):
        sal = f"Dear {titles[-1]} {first}"
    elif titles:
        sal = f"Dear {titles[0]} {last}"
    else:
        sal = f"Dear {first}"
    return {"full": full, "first": first, "last": last, "salutation": sal}


def ppct(v) -> str:
    """Percent for prose: 0.173 -> '17%' (no plus sign, no decimals)."""
    return f"{abs(v):.0%}"


# ---------- dates ----------
def working_day(d: date) -> date:
    """Roll Saturday/Sunday forward to Monday."""
    return d + timedelta(days=(7 - d.weekday()) % 7) if d.weekday() >= 5 else d


def add_working_days(d: date, n: int) -> date:
    """Day 3 = three working days after day 0 (weekends skipped), so steps never land on the same day."""
    d = working_day(d)
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def budget_timing(latest_period_end, today: date, start_months: int = 6, end_months: int = 2) -> dict:
    """ESTIMATED budget-planning window from the charity's financial year end.

    Assumption (configurable): charities plan next year's budget roughly `start_months`
    to `end_months` before their year end. We only know the year end (from their filings),
    not their actual budget cycle, so every output is labelled as an estimate."""
    start_months, end_months = max(start_months, end_months), min(start_months, end_months)
    if not latest_period_end:
        return {"fy_end": None, "now": False, "window": None, "period": "Unknown", "text": "Financial year end unknown, so no timing estimate.", "guidance": ""}
    end = date.fromisoformat(str(latest_period_end)[:10])
    nxt = end
    while nxt <= today:
        nxt = _add_years(nxt, 1)
    start_w, end_w = _add_months(nxt, -start_months), _add_months(nxt, -end_months)
    if start_w > today:  # a window that hasn't started yet may also have one still running from the year before
        prev = _add_years(nxt, -1)
        if _add_months(prev, -start_months) <= today <= _add_months(prev, -end_months):
            start_w, end_w, nxt = _add_months(prev, -start_months), _add_months(prev, -end_months), prev
    now = start_w <= today <= end_w
    fy = f"{nxt.day} {nxt:%B}"
    period = f"now to {end_w:%B %Y}" if now else f"{start_w:%B %Y} to {end_w:%B %Y}"
    if now:
        text = f"Estimate: their financial year ends {fy}, so they may be planning next year's budget now (window {start_w:%b}–{end_w:%b})."
    else:
        text = f"Estimate: their financial year ends {fy}, so budget planning probably runs {start_w:%B} to {end_w:%B}."
    guidance = (
        f"Aim for a first conversation before {end_w:%B %Y}, while next year's spending is likely still being "
        f"decided. Based on a {start_months}-to-{end_months}-month rule, not their confirmed budget cycle."
    )
    return {"fy_end": nxt, "now": now, "window": (start_w, end_w), "period": period, "text": text, "guidance": guidance}


def _add_years(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:  # 29 Feb
        return d.replace(year=d.year + n, day=28)


def _add_months(d: date, n: int) -> date:
    m = d.month - 1 + n
    y, m = d.year + m // 12, m % 12 + 1
    day = min(d.day, [31, 29 if y % 4 == 0 and (y % 100 or y % 400 == 0) else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1])
    return date(y, m, day)


# ---------- hooks ----------
def _mid_sentence(fact: str, name: str) -> str:
    """Lower-case the first letter so a fact can follow 'I noticed' / 'I also noticed',
    unless it starts with the charity's name or a number."""
    if not fact or fact.startswith(name) or fact[0].isdigit():
        return fact
    return fact[0].lower() + fact[1:]


def _share(part, total):
    return part / total if part is not None and total else None


def find_hooks(rec: dict, s: dict, today: date) -> list[dict]:
    """Return hooks, strongest first. Each: key, title, line (opening sentence), why, question, email_safe, score."""
    name = nice_name(rec["name"])
    years = s["years"]
    latest = years[-1] if years else {}
    hooks = []

    if s["status"] == A.OK and (s["hot"] or s["income_trend"] == A.ABOVE):
        peer = (s["peer"] or {}).get("income")
        if s["hot"]:
            fact = f"{name}'s income grew {ppct(s['income_yoy'])} last year to {A.money(latest['income'])}"
            if s["income_trend"] == A.ABOVE and peer is not None:
                fact += f", and {ppct(s['income_change'])} over three years, well ahead of the {ppct(peer)} typical for charities of its size"
        else:
            fact = (
                f"{name}'s income has grown {ppct(s['income_change'])} over the last three years, well ahead "
                f"of the {ppct(peer)} typical for charities of its size"
            )
        hooks.append(
            {
                "key": "growth",
                "title": "Strong growth",
                "email_safe": True,
                "score": 90 if s["hot"] and s["income_trend"] == A.ABOVE else 80 if s["hot"] else 70,
                "fact": fact + ".",
                "extra": "Congratulations, that's a real achievement.",
                "why": "Growth like that can mean more supporters, grants and reporting to keep track of, and systems "
                "that suited a smaller organisation may start to feel stretched.",
                "subject": f"{name}'s growth, and the systems behind it",
                "question": "How are your current systems coping with the growth? Where does it hurt most?",
                "short": "your recent growth",
            }
        )

    if len(years) >= 2:
        first = years[0]
        c0, c1 = first.get("govt_contracts"), latest.get("govt_contracts")
        share = _share(c1, latest.get("income"))
        grew = c0 and c1 and c0 > 0 and (c1 / c0 - 1) >= 0.20
        if c1 and c1 > 0 and ((share or 0) >= 0.30 or grew):
            portion = ("almost all" if (share or 0) >= 0.95 else f"around {share:.0%}") if share else None
            if portion and grew:
                fact = f"{portion} of {name}'s income now comes from government contracts, up from {A.money(c0)} to {A.money(c1)} in three years."
            elif portion:
                fact = f"{portion} of {name}'s income now comes from government contracts."
            else:
                fact = f"{name}'s government contract income has grown from {A.money(c0)} to {A.money(c1)} in three years."
            hooks.append(
                {
                    "key": "contracts",
                    "title": "Government contract income",
                    "email_safe": True,
                    "score": 85 if grew and (share or 0) >= 0.30 else 75,
                    "fact": fact,
                    "why": "Contract funding often comes with tighter reporting, outcome tracking and audit requirements, "
                    "which can take up a lot of staff time if it's pulled together by hand.",
                    "subject": f"Contract reporting at {name}",
                    "question": "How do you pull together the reporting for your contracts and funders at the moment?",
                    "short": "your contract-funded work",
                }
            )

        t0, t1 = first.get("trading"), latest.get("trading")
        if t0 and t1 and t0 > 0 and t1 / t0 - 1 >= 0.25 and t1 - t0 >= 100_000:
            hooks.append(
                {
                    "key": "trading",
                    "title": "Trading income growing",
                    "email_safe": True,
                    "score": 60,
                    "fact": f"{name}'s trading income has grown from {A.money(t0)} to {A.money(t1)} in three years.",
                    "why": "Shops, cafés, events and trading arms add stock, sales and finance to track alongside fundraising, "
                    "and organisations can end up with separate systems that don't talk to each other.",
                    "subject": f"{name}'s trading growth",
                    "question": "How do your trading and fundraising figures come together for the finance team?",
                    "short": "your trading growth",
                }
            )

    chair = next((t for t in rec["trustees"] if t["is_chair"]), None)
    recent = [t for t in rec["trustees"] if t["appointed"] and (today - date.fromisoformat(t["appointed"][:10])).days <= 365]
    chair_new = chair and chair["appointed"] and (today - date.fromisoformat(chair["appointed"][:10])).days <= 548
    if chair_new or len(recent) >= 2:
        if chair_new:
            when = date.fromisoformat(chair["appointed"][:10]).strftime("%B %Y")
            fact = f"{name} has had a new chair since {when}."
        else:
            fact = f"{len(recent)} new trustees have joined {name}'s board in the last year."
        hooks.append(
            {
                "key": "leadership",
                "title": "New leadership",
                "email_safe": True,
                "score": 50,
                "fact": fact,
                "why": "New boards sometimes take a fresh look at how the organisation runs and what it needs to grow.",
                "subject": f"A fresh look at {name}'s systems",
                "question": "Is the board looking at any changes to how things run this year?",
                "short": "the changes on your board",
            }
        )

    staff, vols = rec["profile"].get("Employees") or 0, rec["profile"].get("Volunteers") or 0
    if staff >= 50 or vols >= 200:
        parts = [f"{staff:,} staff" if staff else "", f"{vols:,} volunteers" if vols else ""]
        hooks.append(
            {
                "key": "scale",
                "title": "Lots of people to coordinate",
                "email_safe": True,
                "score": 40,
                "fact": f"{name} has {' and '.join(p for p in parts if p)} to coordinate.",
                "why": "Keeping rotas, training, safeguarding checks and impact data in one place can get harder at that scale.",
                "subject": f"Coordinating {name}'s people",
                "question": "How do you manage staff and volunteer records today?",
                "short": "coordinating your staff and volunteers",
            }
        )

    if s["status"] == A.OK and latest.get("income") and latest.get("expenditure"):
        deficit = latest["expenditure"] - latest["income"]
        exp_ahead = (s["expenditure_change"] or 0) - (s["income_change"] or 0) >= 0.10
        if deficit > 0.05 * latest["income"] or exp_ahead:
            hooks.append(
                {
                    "key": "costs",
                    "title": "Costs outpacing income",
                    "email_safe": False,
                    "score": 55,
                    "fact": (
                        f"expenditure ran {A.money(deficit)} ahead of income last year."
                        if deficit > 0
                        else f"costs have grown faster than income ({A.pct(s['expenditure_change'])} vs {A.pct(s['income_change'])})."
                    ),
                    "why": "Clearer visibility of where time and money go may help.",
                    "subject": "",
                    "question": "Where are you hoping to save time or cost this year?",
                    "short": "efficiency",
                }
            )

    sector = (rec["profile"].get("Sectors") or "").split(" | ")[0].lower()
    hooks.append(
        {
            "key": "fallback",
            "title": "Size and sector",
            "email_safe": True,
            "score": 10,
            "fact": "",
            "opener": f"I've been looking at charities like {name}" + (f" working in {sector}" if sector else "") + ".",
            "why": "Charities at a similar stage can find their fundraising, finance and reporting live in separate places.",
            "subject": f"A quick idea for {name}",
            "question": "What do you use for fundraising, finance and reporting today?",
            "short": "how you run things day to day",
        }
    )
    for h in hooks:
        h.setdefault("extra", "")
        h["line"] = h.get("opener") or f"I noticed {_mid_sentence(h['fact'], name)}"
    return sorted(hooks, key=lambda h: -h["score"])


# ---------- contact ----------
GENERIC_INBOXES = {
    "info",
    "admin",
    "office",
    "enquiries",
    "enquiry",
    "hello",
    "contact",
    "accounts",
    "finance",
    "mail",
    "general",
    "reception",
    "secretary",
    "secretariat",
    "team",
    "charity",
    "post",
    "help",
}


def recipient(email: str | None, chair: dict | None) -> dict:
    """Who the email is addressed to, so the greeting matches the inbox it lands in.
    - inbox contains the chair's name           -> the chair
    - inbox looks like a person (anna.barker@)  -> that person, by first name
    - generic inbox (info@, admin@) or none     -> the chair if known, else the trustees"""
    local = (email or "").split("@")[0].lower()
    if chair and local and any(len(n) > 2 and n.lower() in local for n in (chair["first"], chair["last"])):
        return {"salutation": chair["salutation"], "who": f"{chair['full']} (chair)", "first": chair["first"]}
    parts = [p for p in local.replace("_", ".").replace("-", ".").split(".") if p]
    if len(parts) >= 2 and parts[0].isalpha() and len(parts[0]) > 1 and parts[0] not in GENERIC_INBOXES:
        first = parts[0].capitalize()
        return {"salutation": f"Dear {first}", "who": f"{first} {parts[-1].capitalize()} (published contact)", "first": first}
    if chair:
        return {"salutation": chair["salutation"], "who": f"{chair['full']} (chair), via the charity's main inbox", "first": chair["first"]}
    return {"salutation": "Dear Trustees", "who": "The trustees, via the charity's main inbox", "first": ""}


def contact(rec: dict) -> dict:
    p = rec["profile"]
    chair_row = next((t for t in rec["trustees"] if t["is_chair"]), None)
    chair = person(chair_row["name"]) if chair_row else None
    charity = nice_name(rec["name"])
    li = lambda kw: f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(kw)}"
    income = next((y["income"] for y in reversed(rec["financials"]) if y.get("income")), 0) or 0
    to = recipient(p.get("Email"), chair)
    return {
        "charity": charity,
        "chair": chair,
        "to": to,
        "salutation": to["salutation"],
        "email": p.get("Email"),
        "phone": p.get("Phone"),
        "website": p.get("Website"),
        "decision_maker": ("CEO, Finance Director or Head of Operations" if income >= 1e6 else "chair or CEO (smaller charities often decide at board level)"),
        # The single role to aim for first: finance usually owns a Dynamics 365 decision; small charities decide at the top.
        "buyer": "Finance Director" if income >= 1e6 else "Chief Executive",
        "linkedin_chair": li(f"{chair['full']} {charity}") if chair else None,
        "linkedin_ceo": li(f"{charity} chief executive"),
        "linkedin_finance": li(f"{charity} finance director"),
    }


# ---------- sequence ----------
def schedule(start: date, timing: dict, early: bool = False, started: bool = False) -> dict:
    """When the sequence's day 0 (first email) falls. See SCHEDULING in the module docstring."""
    start = working_day(start)
    w = timing.get("window")
    upcoming = bool(w) and not timing.get("now")
    if started or not upcoming or early or working_day(w[0]) <= start:
        first = start
    else:
        first = working_day(w[0])
    waiting = first > start
    return {
        "first": first,
        "waiting": waiting,  # first email held back until the estimated window opens
        "prep_due": max(start, working_day(first - timedelta(days=14))) if waiting else None,
        "early": bool(early and upcoming and not started and working_day(w[0]) > start),  # contacting before the window, on purpose
    }


def build_plan(rec: dict, s: dict, settings: dict, start: date, today: date | None = None, early: bool = False, started: bool = False) -> dict:
    today = today or date.today()
    hooks = find_hooks(rec, s, today)
    safe = [h for h in hooks if h["email_safe"]]
    h1 = safe[0]
    h2 = next((h for h in safe[1:] if h["key"] != "fallback"), None)
    c = contact(rec)
    timing = budget_timing(s.get("latest_period_end"), today, int(settings.get("budget_start_months", 6)), int(settings.get("budget_end_months", 2)))
    me = settings.get("name") or "[Your name]"
    role = settings.get("role") or "[Your role]"
    cal = settings.get("calendly") or "[your Calendly link]"
    sig = f"{me}\n{role}, mhance"
    sched = schedule(start, timing, early, started)
    dates = {d: add_working_days(sched["first"], d) for d, _, _ in STEPS}

    email1 = (
        f"{c['salutation']},\n\n"
        f"{' '.join(x for x in (h1['line'], h1['extra'], h1['why']) if x)}\n\n"
        f"I'm {me} at mhance. We work only with UK charities and nonprofits, helping them run fundraising, "
        f"grants, volunteers and finance on Microsoft Dynamics 365, so their systems keep up with the mission "
        f"instead of holding it back.\n\n"
        f"Would a 20-minute call be useful to compare notes? You can pick a time that suits you here: {cal}\n\n"
        f"Kind regards,\n{sig}"
    )
    second = f"I also noticed {_mid_sentence(h2['fact'], c['charity'])} {h2['why']}" if h2 else h1["why"]
    email2 = (
        f"{c['salutation']},\n\n"
        f"Just following up on my note from {dates[0]:%A}. {second}\n\n"
        f"I'd be happy to share what we've seen work for charities of a similar size, with no obligation. "
        f"If a short call would help, here's my calendar: {cal}\n\n"
        f"Best wishes,\n{sig}"
    )
    ask_for = c["chair"]["full"] + " (chair)" if c["chair"] else "whoever looks after systems or finance"
    qs = [h["question"] for h in hooks[:3]]
    call = (
        f"Call: {c['phone'] or 'no phone listed, check the website'}\n"
        f"Ask for: the {c['decision_maker']}, or {ask_for}\n\n"
        f'Opener: "Hi, it\'s {me} from mhance. I sent a couple of emails about {h1["short"]}. Have I caught you at an OK time?"\n\n'
        f"Why you're calling: {h1['line']}\n\n"
        f"Questions to ask:\n" + "\n".join(f"  • {q}" for q in qs) + "\n\n"
        f"Timing: {timing['text']}\n\n"
        f"Goal: book a 20-minute call. Offer to send the Calendly link: {cal}\n"
        f"If 'not now': \"When do you usually start planning next year's budget?\" and diary a follow-up for then.\n\n"
        f"Voicemail: \"Hi, it's {me} from mhance. I emailed about {h1['short']} at {c['charity']}. "
        f"I'll drop you a line on LinkedIn too, or you can book a time from the link in my email. Thanks!\""
    )
    li_first = c["chair"]["first"] if c["chair"] else ""
    hi = f"Hi {li_first}, " if li_first else "Hi, "
    note = hi + (
        f"I'm {me} at mhance. We help UK charities run fundraising and finance on Microsoft Dynamics 365. "
        f"I've been following {c['charity']}'s work and {h1['short']}, and would love to connect."
    )
    if len(note) > LINKEDIN_LIMIT:
        note = hi + f"I'm {me} at mhance. We help UK charities with Microsoft Dynamics 365. Would love to connect."
    steps = [
        {"day": 0, "date": dates[0], "channel": "email", "title": "First email", "to": c["email"], "subject": h1["subject"], "body": email1},
        {"day": 3, "date": dates[3], "channel": "email", "title": "Follow-up email", "to": c["email"], "subject": f"Re: {h1['subject']}", "body": email2},
        {"day": 5, "date": dates[5], "channel": "call", "title": "Phone call", "to": c["phone"], "subject": "", "body": call},
        {
            "day": 7,
            "date": dates[7],
            "channel": "linkedin",
            "title": "LinkedIn connection",
            "to": c["chair"]["full"] if c["chair"] else "",
            "subject": "",
            "body": note,
        },
    ]
    return {
        "hooks": hooks,
        "primary": h1,
        "secondary": h2,
        "contact": c,
        "timing": timing,
        "schedule": sched,
        "steps": steps,
        "summary": financial_summary(s),
        "priority": A.priority(s),
    }


def financial_summary(s: dict) -> str:
    """One plain-English sentence on financial direction, built only from the figures."""
    if not s["years"]:
        return "No financial returns on record."
    latest = s["years"][-1]
    if s["status"] != A.OK:
        why = A.STATUS_HELP[s["status"]]
        return f"Latest income {A.money(latest['income'])} (year ending {str(latest['period_end'])[:10]}). No trend shown: {why[0].lower() + why[1:]}"
    peer = (s["peer"] or {}).get("income")
    word = lambda d: {A.UP: "up", A.DOWN: "down", A.FLAT: "flat"}[d]
    text = (
        f"Income {A.money(latest['income'])} in the year ending {str(latest['period_end'])[:10]}, "
        f"{word(s['income_direction'])} {A.pct(s['income_change'])} over 3 returns"
    )
    if peer is not None:
        cmp = {A.ABOVE: "faster than", A.INLINE: "in line with", A.BELOW: "slower than"}[s["income_trend"]]
        text += f", {cmp} similar-sized charities ({A.pct(peer)})"
    text += f". Expenditure {A.money(latest['expenditure'])}"
    if s["expenditure_direction"]:
        text += f", {word(s['expenditure_direction'])} {A.pct(s['expenditure_change'])}"
    return text + "."


STEP_ACTIONS = {0: "Send the first email", 3: "Send the follow-up email", 5: "Make the follow-up call", 7: "Connect on LinkedIn"}
PREP = "prep"  # key in item["done"] for the research step


def fmt_day(d: date) -> str:
    return f"{d:%a} {d.day} {d:%b}"


def next_action(item: dict, plan: dict) -> dict:
    """The one current action for a saved prospect.
    Returns {label, due, day, channel, actionable, note, snoozed}. day is a step day, PREP, or None."""
    out = item.get("outcome", "Active")
    act = {"label": "", "due": None, "day": None, "channel": None, "actionable": True, "note": "", "snoozed": False}
    if out != "Active":
        return {**act, "label": f"No action needed: {out.lower()}", "actionable": False}
    done, sched = item.get("done", {}), plan["schedule"]
    nxt = next((x for x in plan["steps"] if not done.get(str(x["day"]))), None)
    if nxt is None:
        act |= {"label": "No reply yet: set the outcome or plan a later follow-up", "due": add_working_days(plan["steps"][-1]["date"], 5)}
    elif nxt["day"] == 0 and sched["waiting"] and not done.get(PREP):
        act |= {
            "label": f"Research the {plan['contact']['buyer']}",
            "due": sched["prep_due"],
            "day": PREP,
            "channel": "research",
            "note": f"First email planned for {fmt_day(sched['first'])} {sched['first'].year}, when the estimated planning window opens.",
        }
    else:
        act |= {"label": STEP_ACTIONS[nxt["day"]], "due": nxt["date"], "day": nxt["day"], "channel": nxt["channel"]}
        if nxt["day"] == 0 and sched["early"]:
            act["note"] = (
                f"Early relationship-building: this is before the estimated planning window "
                f"({plan['timing']['window'][0]:%B %Y}), so aim to start a conversation, not to sell."
            )
    snooze = item.get("snooze_until")
    if snooze and act["due"] and date.fromisoformat(str(snooze)[:10]) > act["due"]:
        act["due"], act["snoozed"] = date.fromisoformat(str(snooze)[:10]), True
    return act


# ---------- the action queue on My prospects ----------
OVERDUE, DUE_TODAY, IN_WINDOW, LATER, NO_ACTION = range(5)
GROUP_LABELS = {OVERDUE: "Overdue", DUE_TODAY: "Due today", IN_WINDOW: "Planning window open", LATER: "Later", NO_ACTION: "No action needed"}
PRIORITY_RANK = {A.HIGH: 0, A.MEDIUM: 1, A.LOW: 2, A.CHECK_FIRST: 3}


def queue_group(action: dict, in_window: bool, today: date) -> int:
    if not action.get("actionable", True):
        return NO_ACTION
    due = action.get("due")
    if due and due < today:
        return OVERDUE
    if due == today:
        return DUE_TODAY
    return IN_WINDOW if in_window else LATER


def order_queue(rows: list[dict], today: date) -> list[dict]:
    """rows: [{reg, name, priority, action, in_window}]. Adds "group" and returns them in queue order."""
    for r in rows:
        r["group"] = queue_group(r["action"], r.get("in_window", False), today)
    return sorted(rows, key=lambda r: (r["group"], r["action"].get("due") or date.max, PRIORITY_RANK.get(r.get("priority"), 4), r.get("name") or ""))


def default_selection(rows: list[dict]):
    """The prospect to open first: the first actionable one that isn't Low priority, else the first actionable one.
    None if nothing needs action (a replied or stopped record is never opened automatically)."""
    actionable = [r for r in rows if r["group"] != NO_ACTION]
    pick = next((r for r in actionable if r.get("priority") not in (A.LOW, A.CHECK_FIRST)), actionable[0] if actionable else None)
    return pick["reg"] if pick else None


# ---------- the GTM brief ----------
def account_reasons(plan: dict) -> list[str]:
    """One or two plain reasons this charity is (or isn't) a good account, strongest first."""
    pr = plan["priority"]
    if pr["level"] == A.CHECK_FIRST or plan["primary"]["key"] == "fallback":
        first = pr["reasons"][0]
    else:
        first = plan["primary"]["fact"]
    second = next((r for r in pr["reasons"] if r.startswith(("High percentage growth", "Small charity"))), None) or next(
        (r for r in pr["reasons"] if r.startswith("Latest income")), None
    )
    return [first] + ([second] if second and second != first else [])


def why_now(plan: dict) -> tuple[str, str]:
    """(headline, caveat). Timing is an estimate from the financial year end, never confirmed intent."""
    t, sched = plan["timing"], plan["schedule"]
    if not t.get("window"):
        return "No timing estimate: the financial year end isn't known.", "Contact when it suits you."
    start, end = t["window"]
    caveat = f"Estimated from their financial year end ({t['fy_end']:%d %B}). A hypothesis, not confirmed buying intent."
    if t["now"]:
        return f"Possible budget-planning window is open now, until {end:%B %Y}.", caveat
    head = f"Possible budget-planning window opens {start:%B %Y} (to {end:%B %Y})."
    if sched["early"]:
        head += " You chose early relationship-building, so contact starts before it."
    return head, caveat


def provenance(s: dict) -> tuple[str, str]:
    """(facts line, estimates line) shown under the brief."""
    end = s.get("latest_period_end")
    facts = "Charity Commission · " + (f"accounts to {date.fromisoformat(str(end)[:10]):%d %B %Y}" if end else "no accounts on record")
    facts += " · income and expenditure reported; changes and priority calculated"
    return facts, "Planning window and contact timing · estimated from the financial year end · drafts are for you to edit"


def plan_markdown(rec: dict, s: dict, plan: dict, item: dict | None = None) -> str:
    """The whole outreach plan as plain text/Markdown, for copying into a CRM or sharing."""
    c, pr, t = plan["contact"], plan["priority"], plan["timing"]
    lines = [f"# Outreach plan: {c['charity']} (#{rec['reg_number']})", ""]
    if item:
        act = next_action(item, plan)
        lines += [f"Status: {item.get('outcome', 'Active')}  ·  Next action: {act['label']}" + (f" on {act['due']:%a %d %b %Y}" if act["due"] else ""), ""]
        if act["note"]:
            lines += [act["note"], ""]
    lines += [
        "## Financial direction",
        plan["summary"],
        "",
        f"## Priority: {pr['level']}",
        *[f"- {r}" for r in pr["reasons"]],
        "",
        "## Evidence used for the hook (Charity Commission filings)",
        *[f"- {h['title']}: {h['fact'] or h['line']}" for h in plan["hooks"] if h["key"] != "fallback"],
        "",
        "## Timing (estimate)",
        t["text"],
        t["guidance"],
        f"Recommended outreach period: {t['period']}",
        "",
        "## Who to contact",
        f"- Email to: {c['to']['who']} <{c['email'] or 'no email listed'}>",
        f"- Phone: {c['phone'] or 'not listed'}",
        f"- Website: {c['website'] or 'not listed'}",
        f"- Likely decision-maker: {c['decision_maker']}",
        "",
    ]
    for stp in plan["steps"]:
        lines += [f"## Day {stp['day']} ({stp['date']:%a %d %b}): {stp['title']}"]
        if stp["subject"]:
            lines += [f"Subject: {stp['subject']}"]
        lines += ["", stp["body"], ""]
    if item and item.get("notes"):
        lines += ["## Notes", item["notes"], ""]
    lines += [f"Source: Charity Commission Register of Charities, retrieved {date.today():%d %b %Y}."]
    return "\n".join(lines)


def mailto(to: str | None, subject: str, body: str) -> str:
    return f"mailto:{quote(to or '')}?subject={quote(subject)}&body={quote(body)}"
