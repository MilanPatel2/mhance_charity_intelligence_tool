"""Outreach plan for a charity: the hook, who to contact, when, and a 4-step sequence.

Rules-based on purpose: every sentence in a message comes from a template filled with
figures from the Charity Commission, so nothing can be invented. A salesperson edits
the draft before it goes out. (An LLM could polish the wording later; the facts would
still come from here.)

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
"""
from __future__ import annotations

from datetime import date, timedelta
from urllib.parse import quote, quote_plus

import analysis as A

STEPS = [(0, "email", "First email"), (3, "email", "Follow-up email"), (5, "call", "Phone call"), (7, "linkedin", "LinkedIn connection")]
LINKEDIN_LIMIT = 300

TITLES = {"dr": "Dr", "doctor": "Dr", "professor": "Professor", "prof": "Professor", "sir": "Sir", "dame": "Dame",
          "lord": "Lord", "lady": "Lady", "baroness": "Baroness", "baron": "Baron", "rev": "Revd", "revd": "Revd",
          "reverend": "Revd", "canon": "Canon", "mr": "Mr", "mrs": "Mrs", "ms": "Ms", "miss": "Miss", "councillor": "Cllr",
          "cllr": "Cllr", "the": None}
POST_NOMINALS = {"cb", "cbe", "obe", "mbe", "kbe", "dbe", "bem", "qc", "kc", "jp", "dl", "phd", "frcp", "frcpch",
                 "frs", "fca", "aca", "mp", "cvo", "lvo", "rn", "ma", "msc", "bsc", "ba", "mba", "llb"}
SMALL_WORDS = {"of", "and", "the", "for", "in", "on", "at", "to", "a", "an", "&"}


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
        if i and lw in SMALL_WORDS:
            out.append(lw)
            continue
        j = next((k for k, ch in enumerate(lw) if ch.isalpha()), 0)  # '(GREAT' -> '(Great'
        out.append(lw[:j] + lw[j:j + 1].upper() + lw[j + 1:])
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


def budget_timing(latest_period_end, today: date) -> dict:
    """Charities usually plan next year's budget in the ~6 to 2 months before year end."""
    if not latest_period_end:
        return {"fy_end": None, "now": False, "text": "Financial year end unknown."}
    end = date.fromisoformat(str(latest_period_end)[:10])
    nxt = end
    while nxt <= today:
        nxt = _add_years(nxt, 1)
    start_w, end_w = _add_months(nxt, -6), _add_months(nxt, -2)
    if start_w > today:  # a window that hasn't started yet may also have one still running from the year before
        prev = _add_years(nxt, -1)
        if _add_months(prev, -6) <= today <= _add_months(prev, -2):
            start_w, end_w, nxt = _add_months(prev, -6), _add_months(prev, -2), prev
    now = start_w <= today <= end_w
    fy = f"{nxt.day} {nxt:%B}"
    if now:
        text = f"Good timing: their year ends {fy}, so they're likely planning next year's budget now."
    else:
        text = f"Year ends {fy}. Budget planning is usually {start_w:%B} to {end_w:%B}, so that's the best window."
    return {"fy_end": nxt, "now": now, "window": (start_w, end_w), "text": text}


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
                fact += (f", and {ppct(s['income_change'])} over three years, well ahead of the "
                         f"{ppct(peer)} typical for charities of its size")
        else:
            fact = (f"{name}'s income has grown {ppct(s['income_change'])} over the last three years, well ahead "
                    f"of the {ppct(peer)} typical for charities of its size")
        hooks.append({
            "key": "growth", "title": "Strong growth", "email_safe": True,
            "score": 90 if s["hot"] and s["income_trend"] == A.ABOVE else 80 if s["hot"] else 70,
            "fact": fact + ".", "extra": "Congratulations, that's a real achievement.",
            "why": "Growth like that usually means more supporters, grants and reporting to keep track of, and the "
                   "spreadsheets and older systems that worked at a smaller size start to creak.",
            "subject": f"{name}'s growth, and the systems behind it",
            "question": "How are your current systems coping with the growth? Where does it hurt most?",
            "short": "your recent growth",
        })

    if len(years) >= 2:
        first = years[0]
        c0, c1 = first.get("govt_contracts"), latest.get("govt_contracts")
        share = _share(c1, latest.get("income"))
        grew = c0 and c1 and c0 > 0 and (c1 / c0 - 1) >= 0.20
        if c1 and c1 > 0 and ((share or 0) >= 0.30 or grew):
            portion = ("almost all" if (share or 0) >= 0.95 else f"around {share:.0%}") if share else None
            if portion and grew:
                fact = (f"{portion} of {name}'s income now comes from government contracts, "
                        f"up from {A.money(c0)} to {A.money(c1)} in three years.")
            elif portion:
                fact = f"{portion} of {name}'s income now comes from government contracts."
            else:
                fact = f"{name}'s government contract income has grown from {A.money(c0)} to {A.money(c1)} in three years."
            hooks.append({
                "key": "contracts", "title": "Government contract income", "email_safe": True,
                "score": 85 if grew and (share or 0) >= 0.30 else 75,
                "fact": fact,
                "why": "Contract funding brings tighter reporting, outcome tracking and audit requirements, and "
                       "pulling that together by hand eats staff time.",
                "subject": f"Contract reporting at {name}",
                "question": "How do you pull together the reporting for your contracts and funders at the moment?",
                "short": "your contract-funded work",
            })

        t0, t1 = first.get("trading"), latest.get("trading")
        if t0 and t1 and t0 > 0 and t1 / t0 - 1 >= 0.25 and t1 - t0 >= 100_000:
            hooks.append({
                "key": "trading", "title": "Trading income growing", "email_safe": True, "score": 60,
                "fact": f"{name}'s trading income has grown from {A.money(t0)} to {A.money(t1)} in three years.",
                "why": "Shops, cafés, events and trading arms add stock, sales and finance to track alongside fundraising, "
                       "and it's easy to end up with separate systems that don't talk to each other.",
                "subject": f"{name}'s trading growth",
                "question": "How do your trading and fundraising figures come together for the finance team?",
                "short": "your trading growth",
            })

    chair = next((t for t in rec["trustees"] if t["is_chair"]), None)
    recent = [t for t in rec["trustees"] if t["appointed"] and (today - date.fromisoformat(t["appointed"][:10])).days <= 365]
    chair_new = chair and chair["appointed"] and (today - date.fromisoformat(chair["appointed"][:10])).days <= 548
    if chair_new or len(recent) >= 2:
        if chair_new:
            when = date.fromisoformat(chair["appointed"][:10]).strftime("%B %Y")
            fact = f"{name} has had a new chair since {when}."
        else:
            fact = f"{len(recent)} new trustees have joined {name}'s board in the last year."
        hooks.append({
            "key": "leadership", "title": "New leadership", "email_safe": True, "score": 50,
            "fact": fact, "why": "New boards often take a fresh look at how the organisation runs and what it needs to grow.",
            "subject": f"A fresh look at {name}'s systems",
            "question": "Is the board looking at any changes to how things run this year?",
            "short": "the changes on your board",
        })

    staff, vols = rec["profile"].get("Employees") or 0, rec["profile"].get("Volunteers") or 0
    if staff >= 50 or vols >= 200:
        parts = [f"{staff:,} staff" if staff else "", f"{vols:,} volunteers" if vols else ""]
        hooks.append({
            "key": "scale", "title": "Lots of people to coordinate", "email_safe": True, "score": 40,
            "fact": f"{name} has {' and '.join(p for p in parts if p)} to coordinate.",
            "why": "Keeping rotas, training, safeguarding checks and impact data in one place gets hard at that scale.",
            "subject": f"Coordinating {name}'s people",
            "question": "How do you manage staff and volunteer records today?",
            "short": "coordinating your staff and volunteers",
        })

    if s["status"] == A.OK and latest.get("income") and latest.get("expenditure"):
        deficit = latest["expenditure"] - latest["income"]
        exp_ahead = (s["expenditure_change"] or 0) - (s["income_change"] or 0) >= 0.10
        if deficit > 0.05 * latest["income"] or exp_ahead:
            hooks.append({
                "key": "costs", "title": "Costs outpacing income", "email_safe": False, "score": 55,
                "fact": (f"expenditure ran {A.money(deficit)} ahead of income last year." if deficit > 0
                         else f"costs have grown faster than income ({A.pct(s['expenditure_change'])} vs {A.pct(s['income_change'])})."),
                "why": "Better visibility of where time and money go is usually the quickest win.",
                "subject": "", "question": "Where are you hoping to save time or cost this year?",
                "short": "efficiency",
            })

    band = s.get("size_band") or A.size_band(years[0]["income"] if years else None)
    sector = (rec["profile"].get("Sectors") or "").split(" | ")[0].lower()
    hooks.append({
        "key": "fallback", "title": "Size and sector", "email_safe": True, "score": 10,
        "fact": "", "opener": f"I've been looking at charities like {name}" + (f" working in {sector}" if sector else "") + ".",
        "why": "Charities at your stage often find their fundraising, finance and reporting live in separate places.",
        "subject": f"A quick idea for {name}",
        "question": "What do you use for fundraising, finance and reporting today?",
        "short": "how you run things day to day",
    })
    for h in hooks:
        h.setdefault("extra", "")
        h["line"] = h.get("opener") or f"I noticed {_mid_sentence(h['fact'], name)}"
    return sorted(hooks, key=lambda h: -h["score"])


# ---------- contact ----------
GENERIC_INBOXES = {"info", "admin", "office", "enquiries", "enquiry", "hello", "contact", "accounts", "finance",
                   "mail", "general", "reception", "secretary", "secretariat", "team", "charity", "post", "help"}


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
        "decision_maker": ("CEO, Finance Director or Head of Operations" if income >= 1e6
                           else "chair or CEO (smaller charities often decide at board level)"),
        "linkedin_chair": li(f"{chair['full']} {charity}") if chair else None,
        "linkedin_ceo": li(f"{charity} chief executive"),
        "linkedin_finance": li(f"{charity} finance director"),
    }


# ---------- sequence ----------
def build_plan(rec: dict, s: dict, settings: dict, start: date, today: date | None = None) -> dict:
    today = today or date.today()
    hooks = find_hooks(rec, s, today)
    safe = [h for h in hooks if h["email_safe"]]
    h1 = safe[0]
    h2 = next((h for h in safe[1:] if h["key"] != "fallback"), None)
    c = contact(rec)
    timing = budget_timing(s.get("latest_period_end"), today)
    me = settings.get("name") or "[Your name]"
    role = settings.get("role") or "[Your role]"
    cal = settings.get("calendly") or "[your Calendly link]"
    sig = f"{me}\n{role}, mhance"
    dates = {d: add_working_days(start, d) for d, _, _ in STEPS}

    email1 = (
        f"{c['salutation']},\n\n"
        f"{' '.join(x for x in (h1['line'], h1['extra'], h1['why']) if x)}\n\n"
        f"I'm {me} at mhance. We work only with UK charities and nonprofits, helping them run fundraising, "
        f"grants, volunteers and finance on Microsoft Dynamics 365, so their systems keep up with the mission "
        f"instead of holding it back.\n\n"
        f"Would a 20-minute call be useful to compare notes? You can pick a time that suits you here: {cal}\n\n"
        f"Kind regards,\n{sig}"
    )
    second = (f"I also noticed {_mid_sentence(h2['fact'], c['charity'])} {h2['why']}" if h2 else h1["why"])
    email2 = (
        f"{c['salutation']},\n\n"
        f"Just following up on my note from {dates[0]:%A}. {second}\n\n"
        f"I'm happy to share what we've seen work for charities of a similar size, with no obligation. "
        f"If a short call would help, here's my calendar: {cal}\n\n"
        f"Best wishes,\n{sig}"
    )
    ask_for = c["chair"]["full"] + " (chair)" if c["chair"] else "whoever looks after systems or finance"
    qs = [h["question"] for h in hooks[:3]]
    call = (
        f"Call: {c['phone'] or 'no phone listed, check the website'}\n"
        f"Ask for: the {c['decision_maker']}, or {ask_for}\n\n"
        f"Opener: \"Hi, it's {me} from mhance. I sent a couple of emails about {h1['short']}. Have I caught you at an OK time?\"\n\n"
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
    note = hi + (f"I'm {me} at mhance. We help UK charities run fundraising and finance on Microsoft Dynamics 365. "
                 f"I've been following {c['charity']}'s work and {h1['short']}, and would love to connect.")
    if len(note) > LINKEDIN_LIMIT:
        note = hi + f"I'm {me} at mhance. We help UK charities with Microsoft Dynamics 365. Would love to connect."
    steps = [
        {"day": 0, "date": dates[0], "channel": "email", "title": "First email", "to": c["email"],
         "subject": h1["subject"], "body": email1},
        {"day": 3, "date": dates[3], "channel": "email", "title": "Follow-up email", "to": c["email"],
         "subject": f"Re: {h1['subject']}", "body": email2},
        {"day": 5, "date": dates[5], "channel": "call", "title": "Phone call", "to": c["phone"],
         "subject": "", "body": call},
        {"day": 7, "date": dates[7], "channel": "linkedin", "title": "LinkedIn connection",
         "to": c["chair"]["full"] if c["chair"] else "", "subject": "", "body": note},
    ]
    return {"hooks": hooks, "primary": h1, "secondary": h2, "contact": c, "timing": timing, "steps": steps}


def mailto(to: str | None, subject: str, body: str) -> str:
    return f"mailto:{quote(to or '')}?subject={quote(subject)}&body={quote(body)}"
