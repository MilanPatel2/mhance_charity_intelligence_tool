"""Where charity data comes from.

  LiveAPI   - Charity Commission Register of Charities API (needs a free key).
              Used for EVERYTHING about a specific charity you name: search,
              lookup, and the "check a list" tab. Responses are cached on disk
              for 24h (requests-cache + SQLite), so repeat lookups are instant
              and we don't hammer the Commission. No local-data fallback: if the
              API fails, the app says so rather than quietly showing older data.
  Snapshot  - the Commission's daily bulk extract, pre-built into parquet by
              build_dataset.py. Used only for things the API can't do: filtering
              the whole register (prospect search) and working out the market
              benchmarks (median growth per size band) that trends are compared to.

LiveAPI.lookup returns a "charity record" dict:
  {reg_number, name, status, profile{...}, financials[{period_end, income, expenditure}],
   trustees[{name, is_chair, appointed}], source}
"""

from __future__ import annotations

import re
from functools import cached_property
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
import requests_cache

API_BASE = "https://api.charitycommission.gov.uk/register/api"
DATA = Path(__file__).parent / "data"
CACHE = Path(__file__).parent / ".cache" / "cc_api"


class APIError(Exception):
    pass


class NotFound(Exception):
    pass


class LiveAPI:
    name = "Live API"

    def __init__(self, key: str, ttl_hours: int = 24):
        CACHE.parent.mkdir(exist_ok=True)
        self.s = requests_cache.CachedSession(
            str(CACHE),
            backend="sqlite",
            expire_after=ttl_hours * 3600,
            allowable_codes=(200, 404),  # cache "not found" too
        )
        self.s.headers.update({"Ocp-Apim-Subscription-Key": key, "Cache-Control": "no-cache"})

    def _get(self, path: str):
        try:
            r = self.s.get(f"{API_BASE}/{path}", timeout=20)
        except requests.RequestException as e:
            raise APIError(f"Couldn't reach the Charity Commission API ({e.__class__.__name__}).") from e
        if r.status_code == 401:
            raise APIError("API key rejected (401). Check the key in api_key.txt (new keys can take a few minutes to activate).")
        if r.status_code == 429:
            raise APIError("Rate limited by the Charity Commission API (429). Try again in a minute.")
        if r.status_code == 404 or not r.content:
            return None
        if not r.ok:
            raise APIError(f"Charity Commission API returned {r.status_code}.")
        try:
            return r.json()
        except ValueError as e:  # HTML error page, truncated body, etc.
            raise APIError("The Charity Commission API sent back something that wasn't valid data. Try again shortly.") from e

    def check_key(self) -> str | None:
        """Returns None if the key works, otherwise a human-readable problem."""
        try:
            with self.s.cache_disabled():
                self._get("charitydetails/202918/0")
            return None
        except APIError as e:
            return str(e)

    def search(self, text: str) -> list[dict]:
        rows = _as_list(self._get(f"searchCharityName/{quote(text)}"))
        out, seen = [], set()
        for r in rows:
            reg = r.get("reg_charity_number")
            registered = r.get("reg_status") == "R" or str(r.get("reg_status", "")).lower().startswith("reg")
            if not reg or not registered or r.get("group_subsid_suffix") or reg in seen:
                continue  # removed charities, subsidiaries, duplicates and malformed rows are skipped
            seen.add(reg)
            out.append({"reg_number": int(reg), "name": r.get("charity_name") or f"Charity {reg}", "registered_on": (r.get("date_of_registration") or "")[:10]})
        return out

    def latest_incomes(self, reg_numbers: list[int]) -> dict[int, float]:
        """Latest income for several charities, used to sort search results biggest first."""
        out = {}
        for i in range(0, len(reg_numbers), 20):
            chunk = ",".join(str(n) for n in reg_numbers[i : i + 20])
            for r in _as_list(self._get(f"charitydetailsmulti/{chunk}")):
                if r.get("reg_charity_number") and not r.get("group_subsid_suffix"):
                    out[r["reg_charity_number"]] = r.get("latest_income")
        return out

    def lookup(self, reg_number: int) -> dict:
        d = self._get(f"allcharitydetailsV2/{reg_number}/0")
        if isinstance(d, list):
            d = d[0] if d else None
        if not isinstance(d, dict) or not d.get("charity_name"):
            raise NotFound(f"No charity found with number {reg_number}.")
        fin = _as_list(self._get(f"charityfinancialhistory/{reg_number}/0"))
        ov = self._get(f"charityoverview/{reg_number}/0")
        ov = ov if isinstance(ov, dict) else {}
        tr = _as_list(self._get(f"charitytrusteeinformationv2/{reg_number}/0"))
        cls = d.get("who_what_where") or []
        pick = lambda t: [c["classification_desc"] for c in cls if c.get("classification_type") == t]
        address = ", ".join(x for x in [d.get(f"address_line_{n}") for n in ["one", "two", "three", "four", "five"]] + [d.get("address_post_code")] if x)
        return {
            "reg_number": reg_number,
            "name": d.get("charity_name"),
            "status": d.get("reg_status"),
            "source": self.name,
            "profile": {
                "Registered": (d.get("date_of_registration") or "")[:10],
                "Type": d.get("charity_type"),
                "Company no.": d.get("charity_co_reg_number"),
                "Address": address,
                "Website": d.get("web"),
                "Email": d.get("email"),
                "Phone": d.get("phone"),
                "Sectors": " | ".join(pick("What")),
                "Beneficiaries": " | ".join(pick("Who")),
                "Operates in": " | ".join(
                    [a["local_authority"] for a in d.get("CharityAoOLocalAuthority") or []] + [a["region"] for a in d.get("CharityAoORegion") or []]
                ),
                "Employees": ov.get("employees"),
                "Volunteers": ov.get("volunteers"),
                "Activities": ov.get("activities"),
            },
            "financials": [
                {
                    "period_end": (f.get("financial_period_end_date") or "")[:10],
                    "income": f.get("income") if f.get("income") is not None else f.get("inc_total"),
                    "expenditure": f.get("expenditure") if f.get("expenditure") is not None else f.get("exp_total"),
                    # income by source (only filed by larger charities; None otherwise). Used for outreach hooks.
                    "govt_contracts": f.get("income_from_govt_contracts"),
                    "govt_grants": f.get("income_from_govt_grants"),
                    "donations": f.get("inc_donations_and_legacies"),
                    "trading": f.get("inc_other_trading_activities"),
                }
                for f in fin
                if f.get("financial_period_end_date") and isinstance(f.get("income") if f.get("income") is not None else f.get("inc_total"), (int, float))
            ],
            "trustees": _dedupe_trustees(tr),
        }


def _norm(text: str) -> str:
    """Lower case, punctuation removed, leading 'the' dropped: 'The Oxfam!' -> 'oxfam'."""
    words = re.sub(r"[^a-z0-9 ]+", " ", (text or "").lower()).split()
    return " ".join(words[1:] if words[:1] == ["the"] and len(words) > 1 else words)


def rank_search_hits(hits: list[dict], query: str, incomes: dict | None = None) -> list[dict]:
    """Best match first: exact name, then names starting with the query, then names containing it,
    then anything else the register returned. Ties go to the larger charity, then by name."""
    q, incomes = _norm(query), incomes or {}

    def key(h):
        n = _norm(h["name"])
        tier = 0 if n == q else 1 if n.startswith(q) else 2 if q in n else 3
        return (tier, -(incomes.get(h["reg_number"]) or 0), n)

    return sorted(hits, key=key)


def _as_list(x) -> list[dict]:
    """API endpoints return a list, a single object or nothing; always give back a list of dicts."""
    if isinstance(x, dict):
        x = [x]
    return [r for r in (x or []) if isinstance(r, dict)]


def _dedupe_trustees(rows: list[dict]) -> list[dict]:
    """The API sometimes repeats the same trustee (e.g. once per role). Keep one row per name."""
    seen, out = set(), []
    for t in rows:
        name = (t.get("name") or t.get("trustee_name") or "").strip()
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        out.append({"name": name, "is_chair": bool(t.get("is_chair")), "appointed": (t.get("date_of_appointment") or "")[:10] or None})
    return out


class Snapshot:
    """Whole-register data for prospect search and market benchmarks. No single-charity lookups."""

    @cached_property
    def charities(self) -> pd.DataFrame:
        return pd.read_parquet(DATA / "charities.parquet")

    @cached_property
    def financials(self) -> pd.DataFrame:
        return pd.read_parquet(DATA / "financials.parquet")

    @property
    def extract_date(self) -> str:
        return str(self.charities["extract_date"].iloc[0])
