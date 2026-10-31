"""Trend logic. Kept separate from the UI so the rules are easy to read, test and change.

THE RULES (all thresholds live in this file)

1. Window: the charity's last 3 annual returns, oldest -> latest. Charity financial
   years end on all sorts of dates, so "3 years" means 3 returns, not 3 calendar years.

2. Can we trust a trend at all? Each charity gets a STATUS first:
     Under 3 yrs data - fewer than 3 returns on record. Too early to call a trend.
     Base under £10k  - income 3 years ago was under £10k. A % change off a tiny
                        base ("+40,000%") is meaningless.
     Check data       - income or expenditure changed more than 50x (or fell to under
                        1/50th) between two returns. On the register this is almost
                        always a filing error, e.g. £88,933 typed as £88,933,000.
     OK               - everything else. Only OK charities get a trend or a hot flag.

3. Trend = compared with similar-sized charities, not in absolute terms.
   Almost every charity's income has risen in cash terms recently (the median charity
   grew ~9% over 3 years, largely inflation), so "Up" in absolute terms says little.
   Instead:
     - peers = OK, up-to-date charities in the same size band, where size is income
       at the START of the window (using latest income would bias the bands, because
       growers move up a band)
     - peer baseline = the median 3-year % change in that band
     - compare the charity's % change with that baseline, e.g. peers grew +8%:
          grew more than +13%  -> ▲ Above peers
          grew less than +3%   -> ▼ Below peers
          anything in between  -> ► In line   (±5% around the peer median)
   Expenditure uses the same method against the band's median expenditure change.

4. 🔥 Hot = latest year's income up more than 10% on the year before (the brief's rule,
   in absolute terms), status OK, and the year before was at least £10k.
5. ⚡ Spike = income more than doubled in a year. Real, but often a one-off (legacy,
   merger, appeal), so it's flagged for a human to check.
6. Stale = latest return ended more than 22 months ago (charities have 10 months to
   file, so older than ~22 months means a late or missing filing).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

YEARS = 3
FLAT_BAND = 0.05          # 'In line' = within ±5% of the peer median change
HOT_THRESHOLD = 0.10
MIN_BASE = 10_000
SPIKE = 1.0               # +100% in a year
SUSPECT_RATIO = 50        # 50x jump or drop between returns = check data
STALE_MONTHS = 22

SIZE_BANDS = [  # (lower, upper, label); based on income at the start of the window
    (1e4, 1e5, "£10k–£100k"),
    (1e5, 5e5, "£100k–£500k"),
    (5e5, 1e6, "£500k–£1m"),
    (1e6, 5e6, "£1m–£5m"),
    (5e6, 1e7, "£5m–£10m"),
    (1e7, 2.5e7, "£10m–£25m"),
    (2.5e7, 1e8, "£25m–£100m"),
    (1e8, np.inf, "Over £100m"),
]

OK, NEW, SMALL, CHECK = "OK", "Under 3 yrs data", "Base under £10k", "Check data"
ABOVE, INLINE, BELOW = "Above peers", "In line", "Below peers"
LABELS = {
    ABOVE: "▲ Above peers", INLINE: "► In line", BELOW: "▼ Below peers",
    NEW: "◌ Under 3 yrs data", SMALL: "◌ Base under £10k", CHECK: "⚠ Check data",
}
STATUS_HELP = {
    NEW: "Fewer than 3 annual returns on record, so it's too early to call a trend.",
    SMALL: "Income three years ago was under £10k, so percentage changes would be meaningless.",
    CHECK: "Income or expenditure changed more than 50× between two returns. That's almost always "
           "a filing error (e.g. £88,933 entered as £88.9m). Check the published accounts before relying on these figures.",
}


def size_band(income) -> str | None:
    if income is None or pd.isna(income):
        return None
    for lo, hi, label in SIZE_BANDS:
        if lo <= income < hi:
            return label
    return None


def _suspect(a, b) -> bool:
    if a is None or b is None or pd.isna(a) or pd.isna(b) or a <= 0 or b <= 0:
        return False
    r = b / a
    return r >= SUSPECT_RATIO or r <= 1 / SUSPECT_RATIO


def _rel_trend(change, peer_median, band: float) -> str:
    diff = change - (peer_median if peer_median is not None and not pd.isna(peer_median) else 0.0)
    return ABOVE if diff > band else BELOW if diff < -band else INLINE


def _months_since(end, today: date) -> int:
    end = pd.Timestamp(end)
    return (today.year - end.year) * 12 + (today.month - end.month)


# ---------- one charity ----------
def summarise(history: list[dict], bench: dict | None = None, band: float = FLAT_BAND,
              hot: float = HOT_THRESHOLD, today: date | None = None) -> dict:
    """history: [{period_end, income, expenditure}, ...] in any order.
    bench: output of benchmarks() -> {band_label: {"income": median, "expenditure": median, "n": count}}"""
    today = today or date.today()
    bench = bench or {}
    rows = sorted(({**h} for h in history if h.get("income") is not None), key=lambda h: str(h["period_end"]))
    last = rows[-YEARS:]
    out = {"years": last, "all_years": rows, "status": NEW, "income_trend": NEW, "expenditure_trend": NEW,
           "income_change": None, "expenditure_change": None, "income_yoy": None, "size_band": None,
           "peer": None, "hot": False, "spike": False, "stale": False, "latest_period_end": None}
    for i, r in enumerate(last):  # YoY for display, vs the return before (even if outside the window)
        j = len(rows) - len(last) + i - 1
        prev = rows[j] if j >= 0 else None
        for col in ("income", "expenditure"):
            p, c = (prev or {}).get(col), r.get(col)
            r[f"{col}_yoy"] = (c - p) / p if prev and p and p > 0 and c is not None else None
    if not last:
        return out
    out["latest_period_end"] = last[-1]["period_end"]
    out["stale"] = _months_since(last[-1]["period_end"], today) > STALE_MONTHS
    out["income_yoy"] = last[-1].get("income_yoy")

    if len(last) < YEARS:
        status = NEW
    elif last[0]["income"] < MIN_BASE:
        status = SMALL
    elif any(_suspect(a[c], b[c]) for c in ("income", "expenditure") for a, b in zip(last, last[1:])):
        status = CHECK
    else:
        status = OK
    out["status"] = status
    if status != OK:
        out["income_trend"] = out["expenditure_trend"] = status
        return out

    out["size_band"] = size_band(last[0]["income"])
    peer = bench.get(out["size_band"])
    out["peer"] = peer
    out["income_change"] = last[-1]["income"] / last[0]["income"] - 1
    e0 = last[0]["expenditure"]
    out["expenditure_change"] = last[-1]["expenditure"] / e0 - 1 if e0 and e0 > 0 else None
    out["income_trend"] = _rel_trend(out["income_change"], peer and peer["income"], band)
    out["expenditure_trend"] = (_rel_trend(out["expenditure_change"], peer and peer["expenditure"], band)
                                if out["expenditure_change"] is not None else SMALL)
    yoy = out["income_yoy"]
    out["hot"] = yoy is not None and yoy > hot and last[-2]["income"] >= MIN_BASE
    out["spike"] = yoy is not None and yoy > SPIKE
    return out


# ---------- every charity at once ----------
def base_table(fin: pd.DataFrame, today: date | None = None) -> pd.DataFrame:
    """Same rules as summarise(), vectorised. fin: org_number, period_end, income, expenditure."""
    today = today or date.today()
    f = fin.dropna(subset=["income"]).sort_values(["org_number", "period_end"]).copy()
    for col in ("income", "expenditure"):  # previous return, for YoY (may be outside the window)
        f[f"{col}_prev"] = f.groupby("org_number")[col].shift()
    last3 = f.groupby("org_number").tail(YEARS).copy()
    # suspect jumps inside the window only
    first_in_window = ~last3["org_number"].duplicated()
    sus = pd.Series(False, index=last3.index)
    for col in ("income", "expenditure"):
        a, b = last3[f"{col}_prev"], last3[col]
        r = b / a.where(a > 0)
        sus |= ((r >= SUSPECT_RATIO) | (r <= 1 / SUSPECT_RATIO)) & (b > 0) & ~first_in_window
    last3["sus"] = sus

    g = last3.groupby("org_number")
    first, latest = g.nth(0).set_index("org_number"), g.nth(-1).set_index("org_number")
    prev = g.nth(-2).set_index("org_number")
    t = pd.DataFrame(index=latest.index)
    t["n_years"] = g.size()
    t["latest_period_end"] = latest["period_end"]
    for col in ("income", "expenditure"):
        t[f"{col}_y1"] = first[col]
        t[f"{col}_y2"] = prev[col].where(t["n_years"] >= 2)
        t[f"{col}_y3"] = latest[col]
    t["status"] = np.select(
        [t["n_years"] < YEARS, t["income_y1"] < MIN_BASE, g["sus"].any()], [NEW, SMALL, CHECK], OK)
    ok = t["status"] == OK
    t["size_band"] = t["income_y1"].map(size_band).where(ok)
    t["income_change"] = (t["income_y3"] / t["income_y1"] - 1).where(ok)
    e1 = t["expenditure_y1"].where(t["expenditure_y1"] > 0)
    t["expenditure_change"] = (t["expenditure_y3"] / e1 - 1).where(ok)
    p = latest["income_prev"]
    t["income_yoy"] = ((latest["income"] - p) / p.where(p > 0))
    t["hot"] = ok & (t["income_yoy"] > HOT_THRESHOLD) & (t["income_y2"] >= MIN_BASE)
    t["spike"] = ok & (t["income_yoy"] > SPIKE)
    ends = pd.to_datetime(t["latest_period_end"])
    t["stale"] = ((today.year - ends.dt.year) * 12 + (today.month - ends.dt.month)) > STALE_MONTHS
    return t.reset_index()


def benchmarks(base: pd.DataFrame) -> dict:
    """Median 3-yr change per size band, from OK and up-to-date charities only."""
    peers = base[(base["status"] == OK) & ~base["stale"]]
    out = {}
    for label, grp in peers.groupby("size_band"):
        out[label] = {"income": float(grp["income_change"].median()),
                      "expenditure": float(grp["expenditure_change"].median()),
                      "n": int(len(grp))}
    return out


def apply_trends(base: pd.DataFrame, bench: dict, band: float = FLAT_BAND, hot: float = HOT_THRESHOLD) -> pd.DataFrame:
    t = base.copy()
    ok = t["status"] == OK
    for col in ("income", "expenditure"):
        med = t["size_band"].map(lambda b: bench.get(b, {}).get(col, 0.0) if isinstance(b, str) else np.nan)
        t[f"peer_{col}_median"] = med
        diff = t[f"{col}_change"] - med
        trend = np.select([diff > band, diff < -band], [ABOVE, BELOW], INLINE)
        t[f"{col}_trend"] = np.where(ok, trend, t["status"])
        if col == "expenditure":
            t.loc[ok & t["expenditure_change"].isna(), "expenditure_trend"] = SMALL
    t["peer_n"] = t["size_band"].map(lambda b: bench.get(b, {}).get("n") if isinstance(b, str) else None)
    t["hot"] = ok & (t["income_yoy"] > hot) & (t["income_y2"] >= MIN_BASE)
    return t


# ---------- formatting ----------
def money(v) -> str:
    """£1.2m / £340k / £950 style formatting for humans."""
    if v is None or pd.isna(v):
        return "–"
    s = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1e9:
        return f"{s}£{v / 1e9:.2f}bn"
    if v >= 1e6:
        return f"{s}£{v / 1e6:.1f}m"
    if v >= 1e3:
        return f"{s}£{v / 1e3:.0f}k"
    return f"{s}£{v:,.0f}"


def pct(v) -> str:
    return "–" if v is None or pd.isna(v) else f"{v:+.1%}"
