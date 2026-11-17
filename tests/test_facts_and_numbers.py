"""Transforms, fact building and the number guard."""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from vps import facts, fmt, transforms
from vps.numbers import REMOVED, apply_facts, has_stray_number
from vps.sources.models import Series


def monthly(values, start=date(2024, 1, 1), skip=()):
    dates, out = [], []
    d = start
    for v in values:
        if d not in skip:
            dates.append(d)
            out.append(v)
        d = date(d.year + (d.month // 12), d.month % 12 + 1, 1)
    return Series("IDX", "Test index", "index", dates, out, "FRED (BLS)", "https://x.test/IDX", "monthly")


def daily(values, end=date(2026, 11, 13)):
    dates = [end - timedelta(days=len(values) - 1 - i) for i in range(len(values))]
    return Series("RATE", "Test rate", "percent", dates, list(values), "FRED (Test)", "https://x.test/RATE", "daily")


# ---------- transforms ----------
def test_year_over_year_math():
    series = monthly([100.0] * 12 + [103.0, 104.0])
    yoy = transforms.year_over_year(series)
    assert yoy.dates == [date(2025, 1, 1), date(2025, 2, 1)]
    assert yoy.values == pytest.approx([3.0, 4.0])


def test_year_over_year_never_fills_a_missing_base_month():
    # February 2024 was never published, so February 2025 has no 12-month change.
    series = monthly([100.0] * 12 + [103.0, 104.0, 105.0], skip={date(2024, 2, 1)})
    assert date(2025, 2, 1) not in transforms.year_over_year(series).dates


def test_period_change_skips_a_gap_instead_of_merging_two_months():
    series = monthly([100, 110, 125, 130, 150], skip={date(2024, 3, 1)})
    change = transforms.period_change(series)
    assert date(2024, 4, 1) not in change.dates  # that "change" would span two months
    assert change.values == [10, 20]


def test_monthly_payment_matches_the_textbook_formula():
    assert transforms.monthly_payment(100_000, 6.0) == pytest.approx(599.55, abs=0.01)
    assert transforms.monthly_payment(120_000, 0.0, years=10) == pytest.approx(1000.0)


def test_recession_spans():
    series = monthly([0, 1, 1, 0, 0, 1])
    series.id = "USREC"
    assert transforms.recession_spans(series) == [(date(2024, 2, 1), date(2024, 3, 1)), (date(2024, 6, 1), date(2024, 6, 1))]


def test_rebase_to_100():
    assert transforms.rebase_to_100(monthly([50.0, 55.0])).values == pytest.approx([100.0, 110.0])


# ---------- formatting ----------
@pytest.mark.parametrize("value,units,kwargs,expected", [
    (7.11, "percent", {}, "7.11%"),
    (3.995, "usd", {"per": "per gallon"}, "$4.00 per gallon"),
    (393300, "usd", {"decimals": 0}, "$393,300"),
    (40.6167, "usd_trillions", {}, "$40.62 trillion"),
    (159293, "thousands", {}, "159.3 million"),
    (6758867, "usd_millions", {}, "$6.76 trillion"),
])
def test_fmt_value(value, units, kwargs, expected):
    assert fmt.fmt_value(value, units, **kwargs) == expected


def test_fmt_date_by_frequency():
    d = date(2026, 10, 1)
    assert fmt.fmt_date(d, "monthly") == "October 2026"
    assert fmt.fmt_date(d, "quarterly") == "Q4 2026"
    assert fmt.fmt_date(d, "daily") == "Oct 1, 2026"


# ---------- facts ----------
META = {"noun": "the test rate", "units": "percent", "freq": "daily", "decimals": 2}


def test_level_facts_report_latest_year_month_and_record():
    values = [4.0] * 800
    values[-400] = 4.11  # roughly a year ago
    values[-31] = 5.19   # a month ago
    values[-1] = 5.15
    out = {f["key"].split(".")[1]: f for f in facts.level_facts(daily(values), META)}
    assert out["latest"]["claim"] == "The test rate was 5.15% as of Nov 13, 2026."
    assert out["latest"]["status"] == "primary" and out["latest"]["value"] == "5.15%"
    assert "up 1.15 percentage points from a year earlier" in out["year"]["claim"]
    assert "down 0.04 percentage points" in out["month"]["claim"]
    assert out["year"]["status"] == "calculated"
    assert all(f["source_url"] == "https://x.test/RATE" for f in out.values())


def test_record_fact_names_when_it_was_last_this_high():
    values = [3.0] * 900
    values[100] = 6.0
    values[-1] = 5.0
    record = next(f for f in facts.level_facts(daily(values), META) if f["key"].endswith(".record"))
    assert record["claim"].startswith("That is the highest level since")
    assert record["trend"] == "highest"


def test_no_record_fact_for_an_ordinary_reading():
    values = [3.0, 5.0] * 400 + [4.0]
    assert not [f for f in facts.level_facts(daily(values), META) if f["key"].endswith(".record")]


def test_yoy_facts_leave_a_missing_comparison_blank_and_say_so():
    # 14 months, but the month a year before the latest one was never published.
    series = monthly([100 + i for i in range(14)], start=date(2025, 9, 1), skip={date(2025, 10, 1)})
    assert series.latest_date == date(2026, 10, 1)
    out = facts.yoy_facts(series, {"noun": "test prices"})
    missing = next(f for f in out if f["key"].endswith(".yoy_missing"))
    assert missing["value"] == "" and "never published" in missing["claim"]
    latest = next(f for f in out if f["key"].endswith(".yoy"))
    assert "12 months ending September 2026" in latest["claim"]  # the latest month that CAN be compared


def test_news_facts_are_always_flagged_verify():
    out = facts.news_facts([{"title": "Rates hit 7.2%", "url": "https://n.test/a", "source": "N"},
                            {"title": "Bond selloff deepens", "url": "https://n.test/b", "source": "N"}])
    assert [f["status"] for f in out] == ["verify", "verify"]
    assert "number that comes only from a news article" in out[0]["note"]
    assert out[0]["value"] == ""  # a news number is never offered to the wording step


def test_mortgage_payment_example_uses_only_fetched_inputs():
    rate = daily([6.0] * 400 + [7.0])
    price = Series("MSPUS", "Median price", "usd", [date(2026, 7, 1)], [400_000.0], "FRED (Census)", "https://x.test/MSPUS", "quarterly")
    fact = facts.mortgage_payment_fact(rate, price)
    loan = 320_000
    assert f"${transforms.monthly_payment(loan, 7.0):,.0f} a month" == fact["value"]
    assert "$320,000 loan" in fact["claim"] and "7.00%" in fact["claim"] and "6.00%" in fact["claim"]
    assert fact["status"] == "calculated"


# ---------- the number guard ----------
FACTS = {"F1": {"id": "F1", "value": "7.11%"}, "F2": {"id": "F2", "value": ""}}


def test_placeholders_are_filled_from_the_fact_sheet():
    text, used, removed = apply_facts("Mortgage rates are {F1} [CHART 2], and your 401(k) tracks the S&P 500", FACTS)
    assert text == "Mortgage rates are 7.11% [CHART 2], and your 401(k) tracks the S&P 500"
    assert used == ["F1"] and removed == []


def test_numbers_the_writer_invented_are_removed():
    text, used, removed = apply_facts("Rates could reach 8% by 2027, up from {F1}. That wiped out $5 trillion.", FACTS)
    assert "8%" not in text and "2027" not in text and "$5 trillion" not in text
    assert "7.11%" in text and text.count(REMOVED) == 3
    assert removed == ["8%", "2027", "$5 trillion"]


def test_unknown_or_blank_fact_ids_are_not_filled():
    text, used, removed = apply_facts("Unknown {F9} and blank {F2}", FACTS)
    assert used == [] and removed == ["{F9}", "{F2}"] and text.count(REMOVED) == 2


@pytest.mark.parametrize("text,expected", [
    ("The 10-year yield and the 30-year mortgage, explained like I'm 12", False),
    ("Why {F1} matters for your 401(k)", False),
    ("3 Charts That Explain Everything", True),
    ("Rates at 7.2% again", True),
])
def test_has_stray_number(text, expected):
    assert has_stray_number(text) is expected
