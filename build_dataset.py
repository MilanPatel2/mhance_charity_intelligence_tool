"""Build the local snapshot from the Charity Commission's free daily bulk extract.

Why this exists
---------------
The Register of Charities API looks up one charity at a time. It has no way to say
"give me every education charity in Ealing with £1m-£10m income", which is what the
sales team needs to build a prospect list. The Commission publishes the whole
register as a free daily download, so this script turns that download into three
small parquet files the app can filter instantly:

    data/charities.parquet   one row per registered charity (profile, sector, area)
    data/financials.parquet  last 5 annual returns per charity (income, expenditure)

They're also used to work out the market benchmarks (median growth per size band).
Single-charity lookups (including trustees) always come from the live API.

Usage:
    python build_dataset.py --download          # fetch the latest extract, then build
    python build_dataset.py --src ./bulk        # build from already-unzipped files
"""

from __future__ import annotations

import argparse
import io
import zipfile
from collections import defaultdict
from pathlib import Path

import orjson
import pandas as pd
import requests

BASE = "https://ccewuksprdoneregsadata1.blob.core.windows.net/data/json"
FILES = [
    "charity",
    "charity_annual_return_history",
    "charity_classification",
    "charity_area_of_operation",
]
OUT = Path(__file__).parent / "data"
YEARS_KEPT = 5


def download(dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        print(f"Downloading {name} ...")
        r = requests.get(f"{BASE}/publicextract.{name}.zip", timeout=600)
        r.raise_for_status()
        zipfile.ZipFile(io.BytesIO(r.content)).extractall(dest)


def stream(path: Path):
    """Yield records one by one. The extract is a JSON array with one record per
    line, so we can parse line by line instead of loading 600MB at once."""
    with open(path, "rb") as f:
        for line in f:
            line = line.strip().lstrip(b"\xef\xbb\xbf").lstrip(b"[,").rstrip(b"],")
            if line.startswith(b"{"):
                yield orjson.loads(line)


def build(src: Path) -> None:
    OUT.mkdir(exist_ok=True)
    f = lambda n: src / f"publicextract.{n}.json"

    # 1. Registered main charities (subsidiaries/linked charities excluded)
    rows = []
    for r in stream(f("charity")):
        if r["charity_registration_status"] != "Registered" or r["linked_charity_number"] != 0:
            continue
        rows.append(
            {
                "reg_number": r["registered_charity_number"],
                "org_number": r["organisation_number"],
                "name": r["charity_name"],
                "charity_type": r["charity_type"],
                "reporting_status": r["charity_reporting_status"],
                "registered_on": (r["date_of_registration"] or "")[:10],
                "latest_income": r["latest_income"],
                "latest_expenditure": r["latest_expenditure"],
                "postcode": r["charity_contact_postcode"],
                "web": r["charity_contact_web"],
                "email": r["charity_contact_email"],
                "phone": r["charity_contact_phone"],
                "company_number": r["charity_company_registration_number"],
                "extract_date": (r["date_of_extract"] or "")[:10],
            }
        )
    charities = pd.DataFrame(rows)
    keep = set(charities["org_number"])
    print(f"Registered main charities: {len(charities):,}")

    # 2. Sector (What), beneficiaries (Who), method (How)
    cls = defaultdict(lambda: defaultdict(list))
    for r in stream(f("charity_classification")):
        if r["organisation_number"] in keep and r["linked_charity_number"] == 0:
            cls[r["organisation_number"]][r["classification_type"]].append(r["classification_description"])
    for col, t in [("sectors", "What"), ("beneficiaries", "Who"), ("methods", "How")]:
        charities[col] = charities["org_number"].map(lambda o, t=t: " | ".join(cls[o][t]) if o in cls else "")

    # 3. Geography: local authorities and regions they operate in
    geo = defaultdict(lambda: defaultdict(list))
    for r in stream(f("charity_area_of_operation")):
        if r["organisation_number"] in keep and r["linked_charity_number"] == 0:
            geo[r["organisation_number"]][r["geographic_area_type"]].append(r["geographic_area_description"])
    charities["local_authorities"] = charities["org_number"].map(lambda o: " | ".join(geo[o]["Local Authority"]) if o in geo else "")
    charities["regions"] = charities["org_number"].map(lambda o: " | ".join(geo[o]["Region"]) if o in geo else "")
    charities["countries"] = charities["org_number"].map(lambda o: " | ".join(geo[o]["Country"]) if o in geo else "")

    # 4. Financial history: last N annual returns per charity
    hist = defaultdict(dict)
    for r in stream(f("charity_annual_return_history")):
        o = r["organisation_number"]
        if o not in keep or r["total_gross_income"] is None or not r["fin_period_end_date"]:
            continue
        # keyed by period end so a resubmitted return replaces the old one
        hist[o][r["fin_period_end_date"][:10]] = (r["total_gross_income"], r["total_gross_expenditure"])
    fin_rows = []
    for o, periods in hist.items():
        for end in sorted(periods)[-YEARS_KEPT:]:
            inc, exp = periods[end]
            fin_rows.append({"org_number": o, "period_end": end, "income": inc, "expenditure": exp})
    fin = pd.DataFrame(fin_rows)
    print(f"Financial rows: {len(fin):,}")

    charities.to_parquet(OUT / "charities.parquet", index=False, compression="zstd")
    fin.to_parquet(OUT / "financials.parquet", index=False, compression="zstd")
    for p in OUT.glob("*.parquet"):
        print(f"{p.name}: {p.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="bulk", help="folder with unzipped publicextract.*.json files")
    ap.add_argument("--download", action="store_true", help="download the latest extract first")
    a = ap.parse_args()
    src = Path(a.src)
    if a.download:
        download(src)
    build(src)
