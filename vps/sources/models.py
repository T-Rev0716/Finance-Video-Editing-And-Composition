"""The one shape every data source returns."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Series:
    id: str
    title: str
    units: str  # e.g. "percent", "index", "usd", "thousands"
    dates: list[date]
    values: list[float]
    source_name: str  # who to credit on screen, e.g. "FRED (Board of Governors)"
    source_url: str  # a page a viewer can open to see the same numbers
    frequency: str = ""  # "daily", "weekly", "monthly", "quarterly", "annual"
    fetched_via: str = ""  # "fred_api", "fred_csv", "bls_api", "treasury_api", "sec_edgar"
    notes: list[str] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.values)

    @property
    def latest_date(self) -> date:
        return self.dates[-1]

    @property
    def latest_value(self) -> float:
        return self.values[-1]

    def since(self, start: date) -> "Series":
        pairs = [(d, v) for d, v in zip(self.dates, self.values) if d >= start]
        return Series(
            self.id, self.title, self.units, [d for d, _ in pairs], [v for _, v in pairs],
            self.source_name, self.source_url, self.frequency, self.fetched_via, list(self.notes),
        )

    def value_on_or_before(self, target: date) -> tuple[date, float] | None:
        """Latest observation at or before target (None if the series starts later)."""
        found = None
        for d, v in zip(self.dates, self.values):
            if d > target:
                break
            found = (d, v)
        return found

    def to_csv(self) -> str:
        lines = [f"date,{self.id}"]
        lines += [f"{d.isoformat()},{v}" for d, v in zip(self.dates, self.values)]
        return "\n".join(lines) + "\n"
