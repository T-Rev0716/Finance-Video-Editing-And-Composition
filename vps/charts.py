"""Render charts from fetched data as video-ready PNGs.

Two sizes per chart: 1920x1080 for YouTube and 1080x1920 for TikTok/Shorts. The vertical
version keeps everything inside the area TikTok's own buttons and captions don't cover.
Only real observations are drawn; there is no smoothing, no forecast and one y-axis.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # no window needed; works the same on Windows, macOS and Linux
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.ticker import FuncFormatter, MaxNLocator  # noqa: E402

from . import fmt  # noqa: E402
from .sources.models import Series  # noqa: E402

# Colours validated for colour-blind separation on each background (blue, orange, green).
THEMES = {
    "dark": {"bg": "#1a1a19", "ink": "#f0efec", "ink2": "#c3c2b7", "muted": "#898781",
             "grid": "#2c2c2a", "axis": "#4a4a46", "series": ["#3987e5", "#d95926", "#199e70"]},
    "light": {"bg": "#fcfcfb", "ink": "#0b0b0b", "ink2": "#52514e", "muted": "#74726c",
              "grid": "#e1e0d9", "axis": "#c3c2b7", "series": ["#2a78d6", "#eb6834", "#1baf7a"]},
}

SIZES = {
    # name: (width_px, height_px, layout)
    "1920x1080": (1920, 1080, {
        "title_size": 44, "title_wrap": 52, "sub_size": 24, "tick_size": 24, "label_size": 30,
        "legend_size": 24, "foot_size": 18, "left": 0.075, "right": 0.865, "bottom": 0.17,
        "top_y": 0.93, "x": 0.05, "foot_y": 0.045, "line_gap": 0.062, "max_xticks": 8, "lw": 3.4,
        "plot_top_min": 0.60,
    }),
    "1080x1920": (1080, 1920, {
        "title_size": 40, "title_wrap": 24, "sub_size": 23, "tick_size": 23, "label_size": 28,
        "legend_size": 23, "foot_size": 16, "left": 0.15, "right": 0.79, "bottom": 0.29,
        "top_y": 0.885, "x": 0.08, "foot_y": 0.215, "line_gap": 0.034, "max_xticks": 4, "lw": 3.4,
        "plot_top_min": 0.50,
    }),
}
DPI = 100


def fmt_compact(value: float, units: str, decimals: int = 2, signed: bool = False) -> str:
    """Short label for chart ticks and end labels."""
    sign = "+" if signed and value > 0 else ""
    if units in ("percent", "percentage_points"):
        return f"{sign}{value:.{decimals}f}%" if units == "percent" else f"{sign}{value:.{decimals}f} pts"
    if units == "usd":
        if abs(value) >= 1e6:
            return f"{sign}${value / 1e6:,.2f}M"
        if abs(value) >= 10000:
            return f"{sign}${value / 1000:,.0f}K"
        return f"{sign}${value:,.{decimals}f}"
    if units == "usd_trillions":
        return f"{sign}${value:,.2f}T"
    if units == "usd_billions":
        return f"{sign}${value / 1000:,.2f}T" if abs(value) >= 1000 else f"{sign}${value:,.{1 if abs(value) < 100 else 0}f}B"
    if units == "usd_millions":
        return f"{sign}${value / 1e6:,.2f}T" if abs(value) >= 1e6 else f"{sign}${value / 1000:,.0f}B"
    if units == "thousands":
        return f"{sign}{value / 1000:,.1f}M" if abs(value) >= 1000 else f"{sign}{value:,.0f}K"
    if units == "count":
        return f"{sign}{value / 1000:,.0f}K" if abs(value) >= 10000 else f"{sign}{value:,.0f}"
    return f"{sign}{value:,.{decimals}f}"


def _step_decimals(step: float) -> int:
    """Decimals needed so neighbouring tick labels never round to the same text."""
    for decimals in (0, 1, 2):
        if abs(step * 10 ** decimals - round(step * 10 ** decimals)) < 1e-6:
            return decimals
    return 3


def _tick_formatter(units: str, span: float, step: float):
    decimals = _step_decimals(step)

    def _format(value, _pos):
        if abs(value) < 1e-12 and units not in ("percent", "percentage_points"):
            return "0"
        if units == "percent":
            return f"{value:.{decimals}f}%"
        if units == "percentage_points":
            return f"{value:.{decimals}f}"
        if units == "usd":
            if abs(value) >= 10000:
                return f"${value / 1000:,.{_step_decimals(step / 1000)}f}K"
            return f"${value:,.{decimals}f}"
        if units == "usd_trillions":
            return f"${value:,.{decimals}f}T"
        if units == "usd_billions":
            return f"${value / 1000:,.{_step_decimals(step / 1000)}f}T" if span >= 2000 else f"${value:,.{decimals}f}B"
        if units == "usd_millions":
            return f"${value / 1e6:,.{_step_decimals(step / 1e6)}f}T"
        if units == "thousands":
            return f"{value / 1000:,.{_step_decimals(step / 1000)}f}M" if span >= 4000 else f"{value:,.{decimals}f}K"
        if units == "count":
            return f"{value / 1000:,.{_step_decimals(step / 1000)}f}K" if abs(value) >= 10000 else f"{value:,.{decimals}f}"
        return f"{value:,.{decimals}f}"

    return FuncFormatter(_format)


def _subtitle(chart: dict) -> str:
    units = chart["units"]
    kind = chart["kind"]
    unit_text = {
        "percent": "Percent", "percentage_points": "Percentage points", "usd": "U.S. dollars",
        "usd_trillions": "Trillions of dollars", "usd_billions": "Billions of dollars",
        "usd_millions": "Trillions of dollars", "thousands": "Thousands", "count": "Count",
        "index": "Index",
    }.get(units, units)
    if kind == "yoy":
        unit_text = "Percent change from a year earlier"
    elif kind == "indexed":
        unit_text = "Start of chart = 100"
    elif kind == "bars_change":
        unit_text = "Change from the month before"
    parts = [unit_text]
    first, last = chart["series"][0].dates[0], chart["series"][0].dates[-1]
    parts.append(f"{first.year} to {last.year}" if first.year != last.year else str(last.year))
    if chart.get("recessions"):
        parts.append("shaded = U.S. recessions")
    return "  ·  ".join(parts)


def _credit(chart: dict) -> str:
    """One source line for the corner of the chart. Repeated publishers are merged."""
    names = list(dict.fromkeys(s.source_name for s in chart["series"]))
    fred, edgar, other = [], [], []
    for name in names:
        if name.startswith("FRED (") and name.endswith(")"):
            fred.append(name[6:-1])  # "FRED (A)" + "FRED (B)" reads better as "FRED (A; B)"
        elif name.startswith("SEC EDGAR, "):
            edgar.append(name[11:].split(" ")[0])  # the ticker
        else:
            other.append(name)
    credits = [f"FRED ({'; '.join(fred)})"] if fred else []
    if edgar:
        credits.append(f"SEC EDGAR, annual 10-K filings ({', '.join(edgar)})")
    return "Source: " + "; ".join(credits + other)


def _spread_labels(positions: list[float], min_gap: float) -> list[float]:
    """Nudge label positions (axes fraction, any order) apart so none overlap."""
    order = sorted(range(len(positions)), key=lambda i: positions[i])
    placed = list(positions)
    for rank, i in enumerate(order):
        if rank:
            below = placed[order[rank - 1]]
            if placed[i] - below < min_gap:
                placed[i] = below + min_gap
    overflow = max(placed) - 0.98 if placed else 0
    if overflow > 0:
        placed = [p - overflow for p in placed]
    return placed


def _draw(chart: dict, size_name: str, theme_name: str, path: Path) -> None:
    width, height, L = SIZES[size_name]
    T = THEMES.get(theme_name, THEMES["dark"])
    series_list: list[Series] = chart["series"]
    units, kind = chart["units"], chart["kind"]
    decimals = chart.get("decimals", 2)

    fig = plt.figure(figsize=(width / DPI, height / DPI), dpi=DPI, facecolor=T["bg"])

    # --- header: title, subtitle, legend (stacked top-down, plot starts under them)
    title_lines = textwrap.wrap(chart["title"], L["title_wrap"]) or [chart["title"]]
    y = L["top_y"]
    for line in title_lines:
        fig.text(L["x"], y, line, color=T["ink"], fontsize=L["title_size"], fontweight="bold", va="top", ha="left")
        y -= L["line_gap"] * 1.0
    y -= L["line_gap"] * 0.15
    fig.text(L["x"], y, _subtitle(chart), color=T["ink2"], fontsize=L["sub_size"], va="top", ha="left")
    y -= L["line_gap"] * 0.85
    multi = len(series_list) > 1
    if multi:
        handles = [Line2D([0], [0], color=T["series"][i], lw=L["lw"] + 1.5, solid_capstyle="round")
                   for i in range(len(series_list))]
        labels = [s.title for s in series_list]
        # Side by side when it fits; one per row on the vertical format or when names are long.
        stacked = height > width or sum(len(label) for label in labels) > 62
        legend = fig.legend(
            handles, labels, loc="upper left", bbox_to_anchor=(L["x"] - 0.004, y + 0.006),
            ncol=1 if stacked else len(labels), frameon=False, fontsize=L["legend_size"],
            labelcolor=T["ink2"], handlelength=1.4, handletextpad=0.6, columnspacing=2.0, borderaxespad=0,
            labelspacing=0.45,
        )
        legend.set_in_layout(False)
        rows = len(labels) if stacked else 1
        y -= L["line_gap"] * (0.86 * rows + 0.15)
    plot_top = min(y - 0.02, 0.80)
    plot_top = max(plot_top, L["plot_top_min"])

    ax = fig.add_axes([L["left"], L["bottom"], L["right"] - L["left"], plot_top - L["bottom"]], facecolor=T["bg"])

    # --- marks
    is_bars = kind in ("bars", "bars_change")
    if is_bars:
        s = series_list[0]
        gaps = [(b - a).days for a, b in zip(s.dates, s.dates[1:])] or [30]
        bar_width = sorted(gaps)[len(gaps) // 2] * 0.68
        ax.bar(s.dates, s.values, width=bar_width, color=T["series"][0], linewidth=0, zorder=3)
        ax.axhline(0, color=T["axis"], lw=1.6, zorder=2)
    else:
        for i, s in enumerate(series_list):
            lw = L["lw"] if len(s) < 1500 else L["lw"] - 0.8
            marker = "o" if len(s) <= 14 else None
            ax.plot(s.dates, s.values, color=T["series"][i], lw=lw, solid_capstyle="round",
                    solid_joinstyle="round", zorder=3 + i, marker=marker, markersize=9,
                    markeredgecolor=T["bg"], markeredgewidth=2)

    for start, end in chart.get("recessions", []):
        ax.axvspan(start, end, color=T["ink"], alpha=0.09, lw=0, zorder=1)
    if chart.get("zero_line") and not is_bars:
        ax.axhline(0, color=T["axis"], lw=1.6, zorder=2)
    if chart.get("target") is not None:
        ax.axhline(chart["target"], color=T["muted"], lw=1.8, ls=(0, (6, 5)), zorder=2)

    # --- axes
    first = min(s.dates[0] for s in series_list)
    last = max(s.dates[-1] for s in series_list)
    pad = (last - first) * 0.012
    ax.set_xlim(first - pad if is_bars else first, last + pad * (2.5 if is_bars else 1))
    ax.margins(y=0.10)
    lo, hi = ax.get_ylim()
    span_years = (last - first).days / 365.25
    if span_years >= 2.5:
        step = max(1, round(span_years / L["max_xticks"] + 0.4))
        ax.xaxis.set_major_locator(mdates.YearLocator(base=step))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    else:
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=L["max_xticks"]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=6, min_n_ticks=4))
    ticks = ax.get_yticks()
    step = float(ticks[1] - ticks[0]) if len(ticks) > 1 else float(hi - lo)
    ax.yaxis.set_major_formatter(_tick_formatter(units, hi - lo, step))
    ax.tick_params(axis="both", colors=T["ink2"], labelsize=L["tick_size"], length=0, pad=12)
    ax.grid(axis="y", color=T["grid"], lw=1.2, zorder=0)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(T["axis"])
    ax.spines["bottom"].set_linewidth(1.6)

    if chart.get("target") is not None and chart.get("target_label"):
        ax.annotate(chart["target_label"], xy=(0.012, chart["target"]), xycoords=("axes fraction", "data"),
                    xytext=(0, 8), textcoords="offset points", color=T["ink2"], fontsize=L["sub_size"] - 3,
                    va="bottom", ha="left")

    # --- end labels: the latest value of each series, in text colour, beside a dot in the series colour
    lo, hi = ax.get_ylim()
    ends = [(s.dates[-1], s.values[-1]) for s in series_list]
    fractions = [(v - lo) / (hi - lo) for _, v in ends]
    label_height_px = L["label_size"] * DPI / 72 * 1.35
    axes_height_px = (plot_top - L["bottom"]) * height
    placed = _spread_labels(fractions, label_height_px / axes_height_px)
    signed = kind == "bars_change"
    for i, ((d, v), frac, pos) in enumerate(zip(ends, fractions, placed)):
        color = T["series"][0 if is_bars else i]
        if not is_bars:
            ax.plot([d], [v], marker="o", markersize=13, color=color, markeredgecolor=T["bg"],
                    markeredgewidth=2.5, zorder=10, clip_on=False)
        label = fmt_compact(v, units, decimals, signed=signed)
        ax.annotate(label, xy=(1.0, pos), xycoords="axes fraction", xytext=(34 if multi else 18, 0),
                    textcoords="offset points", color=T["ink"], fontsize=L["label_size"], fontweight="bold",
                    va="center", ha="left", annotation_clip=False)
        if multi:
            ax.annotate("●", xy=(1.0, pos), xycoords="axes fraction", xytext=(12, 0),
                        textcoords="offset points", color=color, fontsize=L["label_size"] * 0.62,
                        va="center", ha="left", annotation_clip=False)

    # --- footer: source in the corner, and how fresh the data is
    freq = series_list[0].frequency or "daily"
    through = f"Data through {fmt.fmt_date(last, freq)}"
    credit = _credit(chart)
    if height > width:
        lines = textwrap.wrap(credit, 62) + [through]
        fig.text(L["x"], L["foot_y"], "\n".join(lines), color=T["muted"], fontsize=L["foot_size"],
                 va="top", ha="left", linespacing=1.5)
    else:
        fig.text(L["x"], L["foot_y"], textwrap.shorten(credit, 96, placeholder="..."), color=T["muted"],
                 fontsize=L["foot_size"], va="center", ha="left")
        fig.text(0.95, L["foot_y"], through, color=T["muted"], fontsize=L["foot_size"], va="center", ha="right")

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, facecolor=T["bg"])  # no bbox_inches: keeps the exact pixel size
    plt.close(fig)


def render_chart(chart: dict, out_dir: Path, number: int, theme: str = "dark") -> dict[str, str]:
    """Write both sizes. Returns {'1920x1080': filename, '1080x1920': filename}.

    chart: {id, kind, title, units, series: [Series], decimals?, target?, target_label?,
            zero_line?, recessions?}
    """
    if not chart.get("series") or any(len(s) < 2 for s in chart["series"]):
        raise ValueError(f"chart {chart.get('id')}: needs at least two observations per series")
    files = {}
    for size_name in SIZES:
        name = f"chart_{number:02d}_{chart['id']}_{size_name}.png"
        _draw(chart, size_name, theme, out_dir / name)
        files[size_name] = name
    return files
