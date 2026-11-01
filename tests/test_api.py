"""LiveAPI parsing, using responses shaped exactly like the published API schema."""

import pytest

import data_sources as ds

FAKE = {
    "allcharitydetailsV2/202918/0": {
        "charity_name": "OXFAM",
        "reg_status": "R",
        "date_of_registration": "1965-09-07T00:00:00",
        "charity_type": "Charitable company",
        "charity_co_reg_number": "00612172",
        "address_line_one": "Oxfam House",
        "address_line_two": "John Smith Drive",
        "address_post_code": "OX4 2JY",
        "web": "www.oxfam.org.uk",
        "email": None,
        "phone": "0300 200 1300",
        "who_what_where": [
            {"classification_code": 105, "classification_type": "What", "classification_desc": "Overseas Aid/famine Relief"},
            {"classification_code": 203, "classification_type": "Who", "classification_desc": "The General Public/mankind"},
        ],
        "CharityAoOLocalAuthority": [],
        "CharityAoORegion": [{"region": "Throughout England And Wales"}],
    },
    "charityfinancialhistory/202918/0": [
        {"financial_period_end_date": "2023-03-31T00:00:00", "income": 400_600_000, "expenditure": 360_400_000},
        {"financial_period_end_date": "2024-03-31T00:00:00", "income": None, "inc_total": 368_000_000, "expenditure": None, "exp_total": 396_400_000},
        {"financial_period_end_date": "2025-03-31T00:00:00", "income": 339_366_903, "expenditure": 362_636_196},
    ],
    "charityoverview/202918/0": {"employees": 2000, "volunteers": 20000, "activities": "Fighting poverty"},
    "charitytrusteeinformationv2/202918/0": [
        {"name": "Jane Chair", "is_chair": True, "date_of_appointment": "2020-01-01"},
        {"name": "Joe Trustee", "is_chair": False, "date_of_appointment": None},
    ],
    "searchCharityName/oxfam": [
        {"reg_charity_number": 202918, "group_subsid_suffix": 0, "charity_name": "OXFAM", "reg_status": "R", "date_of_registration": "1965-09-07"},
        {"reg_charity_number": 202918, "group_subsid_suffix": 1, "charity_name": "OXFAM SUBSIDIARY", "reg_status": "R", "date_of_registration": "1990-01-01"},
        {"reg_charity_number": 111111, "group_subsid_suffix": 0, "charity_name": "OLD OXFAM SHOP", "reg_status": "RM", "date_of_registration": "1970-01-01"},
    ],
}


@pytest.fixture
def api(monkeypatch, tmp_path):
    monkeypatch.setattr(ds, "CACHE", tmp_path / "cache")
    a = ds.LiveAPI("fake-key")
    monkeypatch.setattr(a, "_get", lambda path: FAKE.get(path))
    return a


def test_lookup_parses_everything(api):
    rec = api.lookup(202918)
    assert rec["name"] == "OXFAM"
    assert [f["income"] for f in rec["financials"]] == [400_600_000, 368_000_000, 339_366_903]  # inc_total fallback
    assert rec["financials"][1]["expenditure"] == 396_400_000
    assert rec["trustees"][0] == {"name": "Jane Chair", "is_chair": True, "appointed": "2020-01-01"}
    assert rec["profile"]["Sectors"] == "Overseas Aid/famine Relief"
    assert rec["profile"]["Address"] == "Oxfam House, John Smith Drive, OX4 2JY"
    assert rec["profile"]["Employees"] == 2000


def test_search_keeps_registered_main_charities_only(api):
    assert [h["name"] for h in api.search("oxfam")] == ["OXFAM"]


def test_not_found(api):
    with pytest.raises(ds.NotFound):
        api.lookup(123)


# ---------- failures and malformed data ----------
class _Resp:
    def __init__(self, status=200, body=b"", js=None):
        self.status_code, self.content, self._js = status, body, js
        self.ok = 200 <= status < 300

    def json(self):
        if self._js is None:
            raise ValueError("not json")
        return self._js


def _api_with(monkeypatch, tmp_path, resp=None, exc=None):
    monkeypatch.setattr(ds, "CACHE", tmp_path / "cache")
    a = ds.LiveAPI("k")

    def fake_get(url, timeout):
        if exc:
            raise exc
        return resp

    monkeypatch.setattr(a.s, "get", fake_get)
    return a


def test_network_failure_becomes_friendly_error(monkeypatch, tmp_path):
    a = _api_with(monkeypatch, tmp_path, exc=ds.requests.ConnectionError("down"))
    with pytest.raises(ds.APIError, match="Couldn't reach"):
        a.lookup(202918)


def test_bad_key_rate_limit_and_html_body(monkeypatch, tmp_path):
    with pytest.raises(ds.APIError, match="401"):
        _api_with(monkeypatch, tmp_path, _Resp(401, b"x")).search("oxfam")
    with pytest.raises(ds.APIError, match="429"):
        _api_with(monkeypatch, tmp_path, _Resp(429, b"x")).search("oxfam")
    with pytest.raises(ds.APIError, match="valid data"):
        _api_with(monkeypatch, tmp_path, _Resp(200, b"<html>", None)).search("oxfam")


def test_malformed_rows_are_skipped(monkeypatch, tmp_path):
    rows = [
        {"charity_name": "NO NUMBER", "reg_status": "R"},
        "junk",
        {"reg_charity_number": 5, "charity_name": "OK", "reg_status": "R", "group_subsid_suffix": 0},
        {"reg_charity_number": 5, "charity_name": "OK", "reg_status": "R", "group_subsid_suffix": 0},
    ]
    a = _api_with(monkeypatch, tmp_path, _Resp(200, b"[]", rows))
    assert [h["reg_number"] for h in a.search("x")] == [5]


def test_financial_rows_normalised_and_bad_values_dropped(api, monkeypatch):
    fake = dict(FAKE)
    fake["charityfinancialhistory/202918/0"] = FAKE["charityfinancialhistory/202918/0"] + [
        {"financial_period_end_date": "2020-03-31T00:00:00", "income": "n/a", "expenditure": 1},
        {"financial_period_end_date": None, "income": 5, "expenditure": 5},
    ]
    monkeypatch.setattr(api, "_get", lambda path: fake.get(path))
    rec = api.lookup(202918)
    assert [f["period_end"] for f in rec["financials"]] == ["2023-03-31", "2024-03-31", "2025-03-31"]


def test_duplicate_trustees_removed(api, monkeypatch):
    fake = dict(FAKE)
    fake["charitytrusteeinformationv2/202918/0"] = FAKE["charitytrusteeinformationv2/202918/0"] * 3
    monkeypatch.setattr(api, "_get", lambda path: fake.get(path))
    assert [t["name"] for t in api.lookup(202918)["trustees"]] == ["Jane Chair", "Joe Trustee"]


def test_no_trustees_is_an_empty_list(api, monkeypatch):
    fake = dict(FAKE)
    fake["charitytrusteeinformationv2/202918/0"] = None
    monkeypatch.setattr(api, "_get", lambda path: fake.get(path))
    assert api.lookup(202918)["trustees"] == []


def test_snapshot_version_changes_when_data_is_replaced(monkeypatch, tmp_path):
    import os

    import data_sources

    monkeypatch.setattr(data_sources, "DATA", tmp_path)
    assert data_sources.Snapshot.version() == "missing|missing"
    for name in ("charities.parquet", "financials.parquet"):
        (tmp_path / name).write_bytes(b"old")
    before = data_sources.Snapshot.version()
    f = tmp_path / "charities.parquet"
    f.write_bytes(b"new data")
    os.utime(f, ns=(f.stat().st_atime_ns, f.stat().st_mtime_ns + 1_000_000_000))
    assert data_sources.Snapshot.version() != before
