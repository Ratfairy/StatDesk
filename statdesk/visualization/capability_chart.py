
"""StatDesk R4.7.3 — Normal Process Capability chart.

Presentation only. All capability estimates, expected PPM and Cpm are
provided by CapabilityEngine R4.7. No statistical index is recalculated here.

Layout:
- Title and legend
- Histogram with fitted normal curves
- Process data, specifications and capability indices
- Expected PPM performance table
- Interpretation notes
"""

from math import ceil, isfinite, log2, pi, sqrt

import numpy as np
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from statdesk.statistics.capability_engine import (
    CapabilityResult,
    ENGINE_VERSION,
)
from statdesk.statistics.spc_number_format import format_spc_number


TITLE = "#0f172a"
TEXT = "#334155"
MUTED = "#64748b"
GRID = "#e2e8f0"
HIST = "#b3d4f5"
WITHIN = "#2563eb"
OVERALL = "#ea580c"
SPEC = "#dc2626"
TARGET = "#059669"
MEAN = "#64748b"
CARD = "#f8fafc"
BORDER = "#dbe3ec"


class CapabilityChartError(ValueError):
    """Invalid or non-renderable capability result."""


def _fmt(value):
    return "N/A" if value is None else format_spc_number(value)


def _fmt_ppm(value):
    return "N/A" if value is None else f"{value:.2f}"


def _validate_result(result):
    if not isinstance(result, CapabilityResult):
        raise CapabilityChartError(
            "Result harus berupa CapabilityResult."
        )

    if result.layout not in ("individuals", "subgroups"):
        raise CapabilityChartError("Layout Capability tidak dikenal.")

    if (
        not isinstance(result.column_name, str)
        or not result.column_name.strip()
    ):
        raise CapabilityChartError(
            "Nama characteristic tidak valid."
        )

    if result.n < 3 or len(result.values) != result.n:
        raise CapabilityChartError(
            "Jumlah pengukuran tidak konsisten."
        )

    try:
        values = np.asarray(result.values, dtype=np.float64)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CapabilityChartError(
            "Data pengukuran tidak valid."
        ) from exc

    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise CapabilityChartError(
            "Pengukuran harus Numeric dan finite."
        )

    mandatory = (
        ("Mean", result.mean),
        ("Within SD", result.sigma_within),
        ("Overall SD", result.sigma_overall),
        ("Observed PPM", result.observed_ppm),
        ("Expected Within Total PPM", result.expected_within_total_ppm),
        ("Expected Overall Total PPM", result.expected_overall_total_ppm),
    )

    optional = (
        ("LSL", result.lsl),
        ("USL", result.usl),
        ("Target", result.target),
        ("Cp", result.cp),
        ("CPL", result.cpl),
        ("CPU", result.cpu),
        ("Cpk", result.cpk),
        ("Pp", result.pp),
        ("PPL", result.ppl),
        ("PPU", result.ppu),
        ("Ppk", result.ppk),
        ("Cpm", result.cpm),
        ("Expected Within Below PPM", result.expected_within_below_ppm),
        ("Expected Within Above PPM", result.expected_within_above_ppm),
        ("Expected Overall Below PPM", result.expected_overall_below_ppm),
        ("Expected Overall Above PPM", result.expected_overall_above_ppm),
    )

    for label, value in mandatory:
        if not isfinite(value):
            raise CapabilityChartError(f"{label} harus finite.")

    for label, value in optional:
        if value is not None and not isfinite(value):
            raise CapabilityChartError(f"{label} harus finite.")

    if result.sigma_within <= 0 or result.sigma_overall <= 0:
        raise CapabilityChartError(
            "Standard deviation harus positif."
        )

    if result.lsl is None and result.usl is None:
        raise CapabilityChartError(
            "Minimal LSL atau USL harus tersedia."
        )

    if (
        result.lsl is not None
        and result.usl is not None
        and result.lsl >= result.usl
    ):
        raise CapabilityChartError(
            "LSL harus lebih kecil daripada USL."
        )

    if not 0 <= result.observed_total <= result.n:
        raise CapabilityChartError(
            "Observed out-of-spec count tidak valid."
        )

    return values


def _normal_pdf(x, mean, sigma):
    with np.errstate(
        over="ignore",
        under="ignore",
        divide="ignore",
    ):
        z = (x - mean) / sigma
        return np.exp(-0.5 * z * z) / (
            sigma * sqrt(2.0 * pi)
        )


def _card(fig, rect):
    ax = fig.add_axes(rect)
    ax.set_facecolor(CARD)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xticks([])
    ax.set_yticks([])

    for spine in ax.spines.values():
        spine.set_color(BORDER)
        spine.set_linewidth(0.9)

    return ax


def _txt(
    ax,
    x,
    y,
    value,
    *,
    size=9,
    weight="normal",
    color=TEXT,
    align="left",
):
    return ax.text(
        x,
        y,
        str(value),
        transform=ax.transAxes,
        ha=align,
        va="center",
        fontsize=size,
        fontweight=weight,
        color=color,
    )


def _key_value(ax, y, label, value):
    _txt(ax, .065, y, label, size=8.9)

    _txt(
        ax,
        .945,
        y,
        value,
        size=9.0,
        weight="medium",
        color=TITLE,
        align="right",
    )


def _draw_metrics(fig, result):
    # Process Data
    process = _card(fig, [.695, .646, .274, .155])

    _txt(
        process,
        .065,
        .88,
        "PROCESS DATA",
        size=9.5,
        weight="bold",
        color=TITLE,
    )

    _key_value(process, .68, "Observations", result.n)
    _key_value(process, .50, "Mean", _fmt(result.mean))
    _key_value(process, .32, "StDev (Within)", _fmt(result.sigma_within))
    _key_value(process, .14, "StDev (Overall)", _fmt(result.sigma_overall))

    # Specification Limits
    specs = _card(fig, [.695, .540, .274, .097])

    _txt(
        specs,
        .065,
        .80,
        "SPECIFICATION LIMITS",
        size=9.4,
        weight="bold",
        color=TITLE,
    )

    for x, name, value in (
        (.08, "LSL", result.lsl),
        (.40, "USL", result.usl),
        (.72, "Target", result.target),
    ):
        _txt(
            specs,
            x,
            .48,
            name,
            size=8.1,
            color=MUTED,
        )

        _txt(
            specs,
            x,
            .19,
            _fmt(value),
            size=9.2,
            color=TITLE,
            weight="medium",
        )

    # Capability Indices
    indices = _card(fig, [.695, .326, .274, .205])

    _txt(
        indices,
        .065,
        .91,
        "CAPABILITY",
        size=9.4,
        weight="bold",
        color=TITLE,
    )

    _txt(
        indices,
        .945,
        .91,
        f"Cpm  {_fmt(result.cpm)}",
        size=8.7,
        weight="medium",
        color=TITLE,
        align="right",
    )

    _txt(
        indices,
        .065,
        .755,
        "WITHIN",
        size=8.0,
        weight="bold",
        color=WITHIN,
    )

    _txt(
        indices,
        .525,
        .755,
        "OVERALL",
        size=8.0,
        weight="bold",
        color=OVERALL,
    )

    rows = (
        (.615, "Cp", result.cp, "Pp", result.pp),
        (.475, "CPL", result.cpl, "PPL", result.ppl),
        (.335, "CPU", result.cpu, "PPU", result.ppu),
        (.195, "Cpk", result.cpk, "Ppk", result.ppk),
    )

    for y, w_label, w_value, o_label, o_value in rows:
        _txt(indices, .065, y, w_label, size=8.8)

        _txt(
            indices,
            .455,
            y,
            _fmt(w_value),
            size=9.0,
            align="right",
            weight="medium",
            color=TITLE,
        )

        _txt(indices, .525, y, o_label, size=8.8)

        _txt(
            indices,
            .945,
            y,
            _fmt(o_value),
            size=9.0,
            align="right",
            weight="medium",
            color=TITLE,
        )


def _draw_performance(fig, result):
    table = _card(fig, [.075, .096, .894, .205])

    _txt(
        table,
        .025,
        .875,
        "PERFORMANCE (PPM)",
        size=10.2,
        weight="bold",
        color=TITLE,
    )

    observed = (
        f"Observed: {result.observed_total}/{result.n} out of spec"
        f"   |   {_fmt(result.observed_ppm)} PPM"
    )

    _txt(
        table,
        .975,
        .875,
        observed,
        size=8.7,
        align="right",
        color=MUTED,
    )

    columns = (.44, .69, .96)

    for x, label in zip(
        columns,
        ("Below LSL", "Above USL", "Total PPM"),
    ):
        _txt(
            table,
            x,
            .625,
            label,
            size=9.0,
            align="right",
            color=MUTED,
        )

    table.plot(
        [.025, .975],
        [.525, .525],
        color=GRID,
        linewidth=.9,
        transform=table.transAxes,
    )

    rows = (
        (
            "Expected Within",
            (
                result.expected_within_below_ppm,
                result.expected_within_above_ppm,
                result.expected_within_total_ppm,
            ),
        ),
        (
            "Expected Overall",
            (
                result.expected_overall_below_ppm,
                result.expected_overall_above_ppm,
                result.expected_overall_total_ppm,
            ),
        ),
    )

    for y, (name, row) in zip((.377, .158), rows):
        _txt(table, .025, y, name, size=9.2)

        for x, value in zip(columns, row):
            _txt(
                table,
                x,
                y,
                _fmt_ppm(value),
                size=9.3,
                align="right",
                color=TITLE,
            )


def _limit_label(ax, position, label, color):
    ax.text(
        position,
        1.012,
        label,
        transform=ax.get_xaxis_transform(),
        ha="center",
        va="bottom",
        fontsize=8.5,
        color=color,
        bbox={
            "facecolor": "white",
            "edgecolor": "none",
            "alpha": .90,
            "pad": 1.0,
        },
        clip_on=False,
    )


def create_capability_figure(result: CapabilityResult) -> Figure:
    values = _validate_result(result)

    bins = max(
        5,
        min(40, ceil(1.0 + log2(result.n))),
    )

    extent = [
        float(values.min()),
        float(values.max()),
    ]

    for sigma in (
        result.sigma_within,
        result.sigma_overall,
    ):
        extent.extend(
            (
                result.mean - 4.5 * sigma,
                result.mean + 4.5 * sigma,
            )
        )

    extent.extend(
        float(v)
        for v in (result.lsl, result.usl, result.target)
        if v is not None
    )

    lo, hi = min(extent), max(extent)
    span = hi - lo

    if not (
        isfinite(lo)
        and isfinite(hi)
        and isfinite(span)
        and span > 0
    ):
        raise CapabilityChartError(
            "Rentang grafik tidak valid."
        )

    margin = .055 * span
    x_min, x_max = lo - margin, hi + margin

    if not (isfinite(x_min) and isfinite(x_max)):
        raise CapabilityChartError(
            "Batas sumbu grafik tidak finite."
        )

    x = np.unique(
        np.concatenate(
            (
                np.linspace(x_min, x_max, 700),
                np.linspace(
                    result.mean - 5 * result.sigma_within,
                    result.mean + 5 * result.sigma_within,
                    360,
                ),
                np.linspace(
                    result.mean - 5 * result.sigma_overall,
                    result.mean + 5 * result.sigma_overall,
                    360,
                ),
            )
        )
    )

    x = x[(x >= x_min) & (x <= x_max)]

    within_y = _normal_pdf(
        x,
        result.mean,
        result.sigma_within,
    )

    overall_y = _normal_pdf(
        x,
        result.mean,
        result.sigma_overall,
    )

    if not (
        np.all(np.isfinite(within_y))
        and np.all(np.isfinite(overall_y))
    ):
        raise CapabilityChartError(
            "Normal density tidak dapat digambar."
        )

    fig = Figure(figsize=(13.4, 7.6), dpi=100)
    fig.patch.set_facecolor("white")

    fig.text(
        .075,
        .967,
        "Normal Process Capability",
        fontsize=18.5,
        weight="bold",
        color=TITLE,
        va="top",
    )

    method = (
        "Individuals · MRbar / d2"
        if result.layout == "individuals"
        else f"Subgroups · {result.within_method.upper()}"
    )

    fig.text(
        .075,
        .908,
        f"{result.column_name}   |   {method}   |   N = {result.n}",
        fontsize=10.3,
        color=MUTED,
        va="top",
    )

    ax = fig.add_axes([.075, .397, .585, .375])

    try:
        _, _, patches = ax.hist(
            values,
            bins=bins,
            density=True,
            color=HIST,
            edgecolor="white",
            linewidth=1.1,
            alpha=.90,
            zorder=2,
        )
    except (ValueError, OverflowError, FloatingPointError) as exc:
        raise CapabilityChartError(
            "Histogram tidak dapat dirender."
        ) from exc

    line_within, = ax.plot(
        x,
        within_y,
        color=WITHIN,
        linewidth=2.5,
        zorder=4,
    )

    line_overall, = ax.plot(
        x,
        overall_y,
        color=OVERALL,
        linewidth=2.3,
        linestyle="--",
        zorder=4,
    )

    fig.legend(
        [patches[0], line_within, line_overall],
        ["Observed histogram", "Normal — Within", "Normal — Overall"],
        loc="upper left",
        bbox_to_anchor=(.075, .854),
        ncol=3,
        fontsize=9.7,
        frameon=False,
        handlelength=2.2,
        columnspacing=2.2,
        borderaxespad=0,
        labelcolor=TEXT,
    )

    if result.lsl is not None:
        ax.axvline(
            result.lsl,
            color=SPEC,
            linestyle="-.",
            linewidth=1.65,
            zorder=5,
        )
        _limit_label(ax, result.lsl, "LSL", SPEC)

    if result.usl is not None:
        ax.axvline(
            result.usl,
            color=SPEC,
            linestyle="-.",
            linewidth=1.65,
            zorder=5,
        )
        _limit_label(ax, result.usl, "USL", SPEC)

    same_target_mean = (
        result.target is not None
        and abs(result.target - result.mean)
        <= 1e-10 * max(1.0, abs(result.mean))
    )

    if result.target is not None:
        ax.axvline(
            result.target,
            color=TARGET,
            linestyle=":",
            linewidth=1.6,
            zorder=6,
        )
        _limit_label(
            ax,
            result.target,
            "Target / Mean" if same_target_mean else "Target",
            TARGET,
        )

    if not same_target_mean:
        ax.axvline(
            result.mean,
            color=MEAN,
            linestyle="--",
            linewidth=1.1,
            zorder=3,
        )

    ax.set_xlim(x_min, x_max)
    ax.set_ylim(bottom=0)

    ax.set_xlabel(
        result.column_name,
        fontsize=10.0,
        color=TEXT,
        labelpad=8,
    )
    ax.set_ylabel(
        "Probability density",
        fontsize=10.0,
        color=TEXT,
        labelpad=8,
    )

    ax.yaxis.set_major_locator(MaxNLocator(nbins=6))
    ax.tick_params(labelsize=9.0, colors=TEXT)
    ax.grid(axis="y", color=GRID, linewidth=.8)
    ax.set_axisbelow(True)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color("#94a3b8")
    ax.spines["left"].set_color("#94a3b8")

    _draw_metrics(fig, result)
    _draw_performance(fig, result)

    fig.text(
        .075,
        .063,
        "Expected PPM assumes normality; fitted curves do not prove stability.",
        fontsize=8.6,
        color="#92400e",
        va="center",
    )

    fig.text(
        .075,
        .032,
        f"StatDesk Capability Engine {ENGINE_VERSION}  ·  "
        "Observed PPM = sample counts; Expected PPM = normal model.",
        fontsize=8.1,
        color=MUTED,
        va="center",
    )

    return fig
