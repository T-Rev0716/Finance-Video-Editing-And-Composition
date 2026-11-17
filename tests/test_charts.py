"""Chart rendering: exact pixel sizes, both orientations, every chart kind."""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest
from PIL import Image

from vps import charts
from vps.sources.models import Series


def make_series(n=400, title="Test rate", units="percent", start=date(2024, 1, 1), step=3, base=4.0):
    dates = [start + timedelta(days=i * step) for i in range(n)]
    values = [base + (i % 50) * 0.02 for i in range(n)]
    return Series("TEST", title, units, dates, values, "FRED (Test Agency)", "https://fred.stlouisfed.org/series/TEST", "daily")


def chart(kind="lines", series=None, **extra):
    return {"id": "test", "kind": kind, "title": "A test chart with a fairly long title that needs to wrap",
            "units": "percent", "series": [make_series()] if series is None else series, **extra}


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_render_writes_both_sizes_at_exact_pixels(tmp_path, theme):
    files = charts.render_chart(chart(), tmp_path, 1, theme)
    assert set(files) == {"1920x1080", "1080x1920"}
    assert files["1920x1080"] == "chart_01_test_1920x1080.png"
    assert Image.open(tmp_path / files["1920x1080"]).size == (1920, 1080)
    assert Image.open(tmp_path / files["1080x1920"]).size == (1080, 1920)


def test_dark_and_light_backgrounds_differ(tmp_path):
    dark = charts.render_chart(chart(), tmp_path / "d", 1, "dark")["1920x1080"]
    light = charts.render_chart(chart(), tmp_path / "l", 1, "light")["1920x1080"]
    dark_px = Image.open(tmp_path / "d" / dark).convert("RGB").getpixel((5, 5))
    light_px = Image.open(tmp_path / "l" / light).convert("RGB").getpixel((5, 5))
    assert sum(dark_px) < 150 and sum(light_px) > 700


def test_the_data_line_is_actually_drawn(tmp_path):
    files = charts.render_chart(chart(), tmp_path, 1, "dark")
    image = Image.open(tmp_path / files["1920x1080"]).convert("RGB")
    blue = tuple(int(charts.THEMES["dark"]["series"][0][i:i + 2], 16) for i in (1, 3, 5))
    pixels = np.asarray(image).reshape(-1, 3)
    assert int((pixels == np.array(blue)).all(axis=1).sum()) > 1500


@pytest.mark.parametrize("kind,extra", [
    ("lines", {"recessions": [(date(2024, 6, 1), date(2024, 9, 1))], "zero_line": True}),
    ("yoy", {"target": 2.0, "target_label": "Fed's 2% goal"}),
    ("bars", {}),
    ("bars_change", {"units": "thousands"}),
    ("indexed", {"units": "index"}),
])
def test_every_chart_kind_renders(tmp_path, kind, extra):
    series = [make_series(n=36, step=30)] if kind.startswith("bars") else [make_series(), make_series(title="Second", base=4.05)]
    files = charts.render_chart(chart(kind, series, **extra), tmp_path, 2, "dark")
    for name in files.values():
        assert (tmp_path / name).stat().st_size > 20_000


def test_three_series_with_colliding_end_labels(tmp_path):
    series = [make_series(title=f"Series {i}", base=4.0 + i * 0.001) for i in range(3)]
    files = charts.render_chart(chart(series=series), tmp_path, 3, "light")
    assert Image.open(tmp_path / files["1080x1920"]).size == (1080, 1920)


def test_refuses_to_draw_without_data(tmp_path):
    with pytest.raises(ValueError):
        charts.render_chart(chart(series=[]), tmp_path, 1)
    with pytest.raises(ValueError):
        charts.render_chart(chart(series=[make_series(n=1)]), tmp_path, 1)


def test_spread_labels_separates_close_positions_and_stays_in_frame():
    placed = charts._spread_labels([0.50, 0.51, 0.52], 0.08)
    ordered = sorted(placed)
    assert all(b - a >= 0.08 - 1e-9 for a, b in zip(ordered, ordered[1:]))
    assert max(charts._spread_labels([0.97, 0.98], 0.08)) <= 0.98 + 1e-9


@pytest.mark.parametrize("value,units,kwargs,expected", [
    (7.114, "percent", {}, "7.11%"),
    (3.995, "usd", {}, "$4.00"),
    (393300, "usd", {"decimals": 0}, "$393K"),
    (40.617, "usd_trillions", {}, "$40.62T"),
    (115.9, "usd_billions", {}, "$116B"),
    (1328.8, "usd_billions", {}, "$1.33T"),
    (165, "thousands", {"signed": True}, "+165K"),
    (-153, "thousands", {"signed": True}, "-153K"),
    (159293, "thousands", {}, "159.3M"),
    (7416.59, "index", {"decimals": 0}, "7,417"),
])
def test_fmt_compact(value, units, kwargs, expected):
    assert charts.fmt_compact(value, units, **kwargs) == expected


def test_credit_line_merges_fred_agencies():
    a = make_series()
    b = make_series()
    b.source_name = "FRED (Freddie Mac)"
    assert charts._credit({"series": [a, b]}) == "Source: FRED (Test Agency; Freddie Mac)"
