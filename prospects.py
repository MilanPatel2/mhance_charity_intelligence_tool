"""Saved prospects (the outreach call list) and the salesperson's settings.

Stored as one small JSON file (outreach.json, git-ignored) next to the app. That is
deliberately simple: no database to install for an assessment prototype, and the
file format is plain enough to inspect. In production this would live in Dynamics 365
(leads, activities and tasks) rather than a file.

Duplicates are impossible by construction: prospects are keyed by registration number.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

OUTCOMES = ["Active", "Replied", "Meeting booked", "Not interested", "Paused"]
DEFAULT_SETTINGS = {
    "name": "",
    "role": "",
    "calendly": "",
    # Estimated budget-planning window, in months before the charity's financial year end.
    "budget_start_months": 6,
    "budget_end_months": 2,
}


class ProspectStore:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.data = self._load()

    # ---------- persistence ----------
    def _load(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict):
                raise ValueError("not an object")
        except (OSError, ValueError):
            data = {}  # missing or corrupt file: start empty rather than crash
        data["settings"] = {**DEFAULT_SETTINGS, **(data.get("settings") or {})}
        data["list"] = {str(k): self._clean(v) for k, v in (data.get("list") or {}).items()}
        return data

    @staticmethod
    def _clean(item: dict) -> dict:
        item = dict(item or {})
        item.setdefault("name", "")
        item.setdefault("added", date.today().isoformat())
        item.setdefault("start", date.today().isoformat())
        item.setdefault("done", {})
        item.setdefault("notes", "")
        if item.get("outcome") not in OUTCOMES:
            item["outcome"] = "Active"
        return item

    def save(self) -> bool:
        try:
            self.path.write_text(json.dumps(self.data, indent=2, default=str))
            return True
        except OSError:
            return False  # read-only host: the list still works for this session

    # ---------- prospects ----------
    @property
    def items(self) -> dict:
        return self.data["list"]

    def __contains__(self, reg) -> bool:
        return str(int(reg)) in self.items

    def __len__(self) -> int:
        return len(self.items)

    def add(self, entries: list[tuple[int, str]], start: date) -> int:
        """Add (reg_number, name) pairs; ones already saved are skipped. Returns how many were new."""
        added = 0
        for reg, name in entries:
            key = str(int(reg))
            if key in self.items:
                continue
            self.items[key] = self._clean({"name": name, "added": date.today().isoformat(), "start": start.isoformat()})
            added += 1
        if added:
            self.save()
        return added

    def remove(self, reg) -> None:
        if self.items.pop(str(int(reg)), None) is not None:
            self.save()

    def update(self, reg, **fields) -> None:
        item = self.items[str(int(reg))]
        for k, v in fields.items():
            item[k] = v.isoformat() if isinstance(v, date) else v
        self.save()

    def set_done(self, reg, day: int, done: bool) -> None:
        self.items[str(int(reg))]["done"][str(day)] = bool(done)
        self.save()

    # ---------- settings ----------
    @property
    def settings(self) -> dict:
        return self.data["settings"]

    def update_settings(self, **fields) -> None:
        self.settings.update(fields)
        self.save()
