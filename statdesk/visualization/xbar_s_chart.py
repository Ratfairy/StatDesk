
"""StatDesk — Xbar-S Control Chart Visualization.

R3.17 — Phase I Chart Visualization Refinement.

Responsibilities:
- Render Xbar and S control charts.
- Display original control limits from XbarSEngine.
- Highlight SPC Test 1 special-cause signals.
- Keep legends outside the plotting areas.
- Improve signal annotation placement.
- Preserve Advanced SPC Tests 1-4 compatibility.
- Display statistical guidance without approval workflows.

This module is visualization-only.

It does not calculate or modify:
- Subgroup means
- Subgroup standard deviations
- Within-process sigma
- Control limits
- SPC signal findings
"""

from math import isfinite

from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from statdesk.statistics.xbar_s_engine import (
    XbarSResult,
    ENGINE_VERSION,
)

from statdesk.statistics.spc_number_format import (
    format_spc_number,
)


# ======================================================
# 1. VISUAL CONFIGURATION
# ======================================================

DATA_COLOR = "#2563eb"
LIMIT_COLOR = "#dc2626"
CENTER_COLOR = "#059669"

SIGNAL_COLOR = "#dc2626"
SIGNAL_TEXT_COLOR = "#b91c1c"

TITLE_COLOR = "#0f172a"
TEXT_COLOR = "#475569"
GRID_COLOR = "#cbd5e1"

PRELIMINARY_MIN_OBSERVATIONS = 60


# ======================================================
# 2. EXCEPTION
# ======================================================

class XbarSChartError(ValueError):
    """Invalid or inconsistent Xbar-S chart result."""


# ======================================================
# 3. VALIDATE ENGINE RESULT
# ======================================================

def _validate_result(result: XbarSResult):
    """Validate the original statistical engine result."""

    if not isinstance(result, XbarSResult):
        raise TypeError(
            "Expected XbarSResult from "
            "XbarSEngine.calculate()."
        )

    m = result.subgroup_count
    n = result.subgroup_size

    if m < 2 or not 9 <= n <= 25:
        raise XbarSChartError(
            "Jumlah atau ukuran subgroup tidak valid."
        )

    if (
        len(result.subgroup_means) != m
        or len(result.subgroup_stdevs) != m
    ):
        raise XbarSChartError(
            "Panjang hasil subgroup tidak konsisten."
        )

    numerical_values = (
        *result.subgroup_means,
        *result.subgroup_stdevs,

        result.xbar_center,
        result.xbar_ucl,
        result.xbar_lcl,

        result.s_center,
        result.s_ucl,
        result.s_lcl,
    )

    if not all(
        isfinite(value)
        for value in numerical_values
    ):
        raise XbarSChartError(
            "Hasil statistik mengandung nilai non-finite."
        )

    signals = (
        *result.xbar_signals,
        *result.s_signals,
    )

    if any(
        type(index) is not int
        or index < 1
        or index > m
        for index in signals
    ):
        raise XbarSChartError(
            "Nomor SPC signal di luar rentang subgroup."
        )

    return m, n


# ======================================================
# 4. AXIS VISUAL STYLE
# ======================================================

def _style_axis(ax):
    """Apply consistent visual formatting."""

    ax.set_facecolor("white")
    ax.set_axisbelow(True)

    ax.grid(
        axis="both",
        color=GRID_COLOR,
        linewidth=0.7,
        alpha=0.40,
    )

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.spines["left"].set_color("#64748b")
    ax.spines["bottom"].set_color("#64748b")

    ax.tick_params(
        axis="both",
        labelsize=9,
        colors="#334155",
    )


# ======================================================
# 5. CONTROL LIMIT LINES
# ======================================================

def _add_control_limits(
    ax,
    *,
    lcl,
    center,
    ucl,
):
    """Draw original Shewhart control limits.

    All numerical values originate from XbarSEngine.
    Formatting is performed only for the legend.
    """

    ax.axhline(
        y=ucl,
        color=LIMIT_COLOR,
        linestyle="--",
        linewidth=1.4,
        label=(
            "UCL = "
            + format_spc_number(ucl)
        ),
        zorder=2,
    )

    ax.axhline(
        y=center,
        color=CENTER_COLOR,
        linestyle="-",
        linewidth=1.3,
        label=(
            "CL = "
            + format_spc_number(center)
        ),
        zorder=2,
    )

    ax.axhline(
        y=lcl,
        color=LIMIT_COLOR,
        linestyle="--",
        linewidth=1.4,
        label=(
            "LCL = "
            + format_spc_number(lcl)
        ),
        zorder=2,
    )


# ======================================================
# 6. SPC TEST 1 SIGNAL MARKERS
# ======================================================

def _add_test1_signals(
    ax,
    values,
    signal_indexes,
):
    """Display engine-detected SPC Test 1 signals.

    Signal numbering is 1-based.

    This function never performs statistical
    signal detection.
    """

    if not signal_indexes:
        return

    signals = [
        (
            number,
            values[number - 1],
        )
        for number in signal_indexes
    ]

    # =====================================
    # 1. DRAW SIGNAL POINTS
    # =====================================

    for index, (number, value) in enumerate(signals):

        ax.scatter(
            [number],
            [value],
            s=80,
            facecolors=SIGNAL_COLOR,
            edgecolors="white",
            linewidths=0.9,
            zorder=7,
            label=(
                "SPC Test 1 signal"
                if index == 0
                else "_nolegend_"
            ),
        )

    # Reserve additional vertical space for labels.
    # Original data and control limits remain unchanged.

    ax.margins(y=0.13)

    x_min, x_max = ax.get_xlim()
    y_min, y_max = ax.get_ylim()

    x_span = max(
        x_max - x_min,
        1.0,
    )

    y_span = max(
        y_max - y_min,
        1e-12,
    )

    # =====================================
    # 2. ANNOTATION POSITIONS
    # =====================================

    for number, value in signals:

        x_fraction = (
            (number - x_min)
            / x_span
        )

        y_fraction = (
            (value - y_min)
            / y_span
        )

        # Near the right boundary, place
        # the label toward the chart interior.

        if x_fraction >= 0.80:
            dx = -9
            horizontal = "right"

        else:
            dx = 9
            horizontal = "left"

        # Near the upper boundary, place
        # the label below the signal point.

        if y_fraction >= 0.78:
            dy = -11
            vertical = "top"

        else:
            dy = 10
            vertical = "bottom"

        ax.annotate(
            str(number),
            xy=(number, value),
            xytext=(dx, dy),
            textcoords="offset points",
            ha=horizontal,
            va=vertical,
            fontsize=9,
            fontweight="bold",
            color=SIGNAL_TEXT_COLOR,
            annotation_clip=True,
            zorder=8,
        )


# ======================================================
# 7. LEGEND
# ======================================================

def _add_external_legend(ax):
    """Place the legend outside the plotting area."""

    ax.legend(
        loc="upper left",
        bbox_to_anchor=(1.02, 1.0),
        borderaxespad=0.0,
        fontsize=8,
        frameon=True,
        facecolor="white",
        edgecolor=GRID_COLOR,
        framealpha=0.96,
        handlelength=2.1,
    )


# ======================================================
# 8. CREATE XBAR-S FIGURE
# ======================================================

def create_xbar_s_figure(
    result: XbarSResult,
) -> Figure:
    """Create the two-panel Xbar-S Phase I figure.

    Required axis order:
        axes[0] = Xbar Chart
        axes[1] = S Chart

    The axis order must remain unchanged for
    spc_rules_overlay.py compatibility.
    """

    # =====================================
    # 1. VALIDATE RESULT
    # =====================================

    m, n = _validate_result(result)

    # =====================================
    # 2. CREATE FIGURE
    # =====================================

    figure = Figure(
        figsize=(11.3, 7.8),
        dpi=100,
        facecolor="white",
    )

    ax_xbar, ax_s = figure.subplots(
        2,
        1,
        sharex=True,
    )

    # Reserve space for titles, external
    # legends, and statistical footnotes.

    figure.subplots_adjust(
        left=0.10,
        right=0.76,
        top=0.845,
        bottom=0.235,
        hspace=0.46,
    )

    subgroup_numbers = list(
        range(1, m + 1)
    )

    # =====================================
    # 3. PLOT XBAR DATA
    # =====================================

    ax_xbar.plot(
        subgroup_numbers,
        result.subgroup_means,
        color=DATA_COLOR,
        linewidth=1.5,
        marker="o",
        markersize=4.5,
        label="Subgroup means",
        zorder=3,
    )

    # =====================================
    # 4. PLOT SAMPLE SD DATA
    # =====================================

    ax_s.plot(
        subgroup_numbers,
        result.subgroup_stdevs,
        color=DATA_COLOR,
        linewidth=1.5,
        marker="o",
        markersize=4.5,
        label="Subgroup SD (n-1)",
        zorder=3,
    )

    # =====================================
    # 5. ORIGINAL CONTROL LIMITS
    # =====================================

    _add_control_limits(
        ax_xbar,
        lcl=result.xbar_lcl,
        center=result.xbar_center,
        ucl=result.xbar_ucl,
    )

    _add_control_limits(
        ax_s,
        lcl=result.s_lcl,
        center=result.s_center,
        ucl=result.s_ucl,
    )

    # =====================================
    # 6. AXIS STYLE
    # =====================================

    for ax in (ax_xbar, ax_s):
        _style_axis(ax)

    # Shared subgroup axis.
    ax_s.set_xlim(
        0.5,
        m + 0.5,
    )

    # =====================================
    # 7. ENGINE TEST 1 SIGNALS
    # =====================================

    _add_test1_signals(
        ax_xbar,
        result.subgroup_means,
        result.xbar_signals,
    )

    _add_test1_signals(
        ax_s,
        result.subgroup_stdevs,
        result.s_signals,
    )

    # =====================================
    # 8. CHART TITLES
    # =====================================

    ax_xbar.set_title(
        "Xbar Chart — Subgroup Means",
        fontsize=12,
        color=TITLE_COLOR,
        pad=12,
    )

    ax_xbar.set_ylabel(
        "Subgroup mean",
        fontsize=10,
        labelpad=10,
    )

    ax_s.set_title(
        "S Chart — Subgroup Standard Deviations",
        fontsize=12,
        color=TITLE_COLOR,
        pad=12,
    )

    ax_s.set_ylabel(
        "Subgroup SD",
        fontsize=10,
        labelpad=10,
    )

    ax_s.set_xlabel(
        "Subgroup (time order)",
        fontsize=10,
        labelpad=10,
    )

    # =====================================
    # 9. SUBGROUP AXIS LABELS
    # =====================================

    if m <= 20:

        ax_s.set_xticks(
            subgroup_numbers
        )

    else:

        ax_s.xaxis.set_major_locator(
            MaxNLocator(
                integer=True,
                nbins=12,
            )
        )

    # =====================================
    # 10. EXTERNAL LEGENDS
    # =====================================

    _add_external_legend(ax_xbar)
    _add_external_legend(ax_s)

    # =====================================
    # 11. MAIN FIGURE TITLE
    # =====================================

    figure.suptitle(
        "StatDesk | Xbar-S Control Chart — Phase I",
        fontsize=16,
        fontweight="medium",
        color=TITLE_COLOR,
        y=0.975,
    )

    figure.text(
        0.5,
        0.915,
        (
            f"Subgroups = {m}   |   "
            f"Measurements/subgroup = {n}   |   "
            f"Total measurements = {m * n}"
        ),
        ha="center",
        va="center",
        fontsize=10,
        color=TEXT_COLOR,
    )

    # =====================================
    # 12. STATISTICAL GUIDANCE
    # =====================================

    total_measurements = m * n

    is_preliminary = (
        total_measurements
        < PRELIMINARY_MIN_OBSERVATIONS
    )

    if is_preliminary:

        warning_text = (
            f"PRELIMINARY — N={total_measurements} measurements. "
            "Review sample size and process stability."
        )

        warning_color = "#b45309"

    else:

        warning_text = (
            "Phase I — evaluate process stability before "
            "using these limits as a historical reference."
        )

        warning_color = TEXT_COLOR

    figure.text(
        0.5,
        0.135,
        warning_text,
        ha="center",
        va="center",
        fontsize=9,
        color=warning_color,
    )

    # =====================================
    # 13. METHOD INFORMATION
    # =====================================

    # IMPORTANT:
    # Keep the exact text "Test 1 only (3-sigma)".
    #
    # spc_rules_overlay.py replaces this phrase
    # with "Active SPC Tests: 1, 2, 3, 4"
    # when Advanced SPC mode is selected.

    figure.text(
        0.5,
        0.091,
        (
            "Review S Chart first  |  "
            "Phase I  |  "
            "Sbar/c4  |  "
            "Test 1 only (3-sigma)"
        ),
        ha="center",
        va="center",
        fontsize=8,
        color=TEXT_COLOR,
    )

    figure.text(
        0.5,
        0.052,
        (
            f"StatDesk Xbar-S Engine {ENGINE_VERSION}"
            "  |  "
            "Control limits are NOT specification limits"
        ),
        ha="center",
        va="center",
        fontsize=8,
        color="#64748b",
    )

    # =====================================
    # 14. RETURN MATPLOTLIB FIGURE
    # =====================================

    return figure
