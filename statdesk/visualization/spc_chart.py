
"""StatDesk — I-MR Control Chart Visualization.

Responsibilities:
- Render Individuals (I) Chart.
- Render Moving Range (MR) Chart.
- Display UCL, CL and LCL from SpcEngine.
- Highlight Test 1 special-cause signals.
- Support optional SPC Rules overlays.
- Format control limits using shared SPC formatter.
- Keep chart footer readable.

Statistical calculations are performed by SpcEngine.

This module does not recalculate or modify
statistical control limits.
"""

from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from statdesk.statistics.spc_engine import ImrResult

from statdesk.statistics.spc_number_format import (
    format_spc_number,
)


# ======================================================
# 1. CREATE I-MR FIGURE
# ======================================================

def create_imr_figure(result: ImrResult) -> Figure:
    """Create a two-panel Phase I I-MR Control Chart.

    Parameters
    ----------
    result : ImrResult
        Statistical result from SpcEngine.

    Returns
    -------
    Figure
        Matplotlib figure containing:
        - Individuals (I) Chart
        - Moving Range (MR) Chart

    Notes
    -----
    All statistical values originate from the
    calculation engine.

    Shared formatting affects labels only,
    never the underlying chart coordinates.
    """

    # =====================================
    # 1. CREATE FIGURE
    # =====================================

    figure = Figure(
        figsize=(11.3, 8.0),
        dpi=100,
        facecolor="white",
    )

    ax_i, ax_mr = figure.subplots(
        2,
        1,
        sharex=True,
    )

    # =====================================
    # 2. OBSERVATION INDEXES
    # =====================================

    # Individuals begin at observation 1.
    x_i = list(
        range(1, result.n + 1)
    )

    # MR(i) belongs to observations i-1 and i.
    # Therefore the first MR is observation 2.
    x_mr = list(
        range(2, result.n + 1)
    )

    # =====================================
    # 3. INDIVIDUALS CHART
    # =====================================

    ax_i.plot(
        x_i,
        result.values,
        color="#2563eb",
        linewidth=1.4,
        marker="o",
        markersize=4.5,
        label="Individual values",
        zorder=3,
    )

    # =====================================
    # 4. MOVING RANGE CHART
    # =====================================

    ax_mr.plot(
        x_mr,
        result.moving_ranges,
        color="#2563eb",
        linewidth=1.4,
        marker="o",
        markersize=4.5,
        label="Moving ranges",
        zorder=3,
    )

    # =====================================
    # 5. CONTROL LIMITS
    # =====================================

    # Use original statistical engine results.
    # Never round the control-limit coordinates.
    #
    # Formatting applies only to legend text.

    chart_limits = (
        (
            ax_i,
            result.i_lcl,
            result.i_center,
            result.i_ucl,
        ),
        (
            ax_mr,
            result.mr_lcl,
            result.mr_center,
            result.mr_ucl,
        ),
    )

    for axes, lower, center, upper in chart_limits:

        # =================================
        # UPPER CONTROL LIMIT
        # =================================

        axes.axhline(
            y=upper,
            color="#dc2626",
            linestyle="--",
            linewidth=1.4,
            label=(
                "UCL = "
                + format_spc_number(upper)
            ),
            zorder=2,
        )

        # =================================
        # CENTER LINE
        # =================================

        axes.axhline(
            y=center,
            color="#059669",
            linestyle="-",
            linewidth=1.3,
            label=(
                "CL = "
                + format_spc_number(center)
            ),
            zorder=2,
        )

        # =================================
        # LOWER CONTROL LIMIT
        # =================================

        axes.axhline(
            y=lower,
            color="#dc2626",
            linestyle="--",
            linewidth=1.4,
            label=(
                "LCL = "
                + format_spc_number(lower)
            ),
            zorder=2,
        )

        # =================================
        # CHART APPEARANCE
        # =================================

        axes.set_facecolor("white")
        axes.set_axisbelow(True)

        axes.grid(
            axis="both",
            color="#CBD5E1",
            linewidth=0.7,
            alpha=0.40,
        )

        axes.spines["top"].set_visible(False)
        axes.spines["right"].set_visible(False)

        axes.spines["left"].set_color(
            "#64748b"
        )

        axes.spines["bottom"].set_color(
            "#64748b"
        )

        axes.tick_params(
            axis="both",
            labelsize=9,
            colors="#334155",
        )

        # Shared number formatter keeps
        # legend labels readable for
        # both ordinary and extreme values.

        axes.legend(
            loc="upper left",
            fontsize=8,
            frameon=True,
            facecolor="white",
            edgecolor="#CBD5E1",
            framealpha=0.92,
        )

    # =====================================
    # 6. INDIVIDUALS TEST 1 SIGNALS
    # =====================================

    for index in result.i_violations:

        # Original 1-based observation index.
        value = result.values[index - 1]

        ax_i.scatter(
            [index],
            [value],
            color="#dc2626",
            s=75,
            edgecolors="white",
            linewidths=1,
            zorder=6,
        )

        # Move endpoint labels inward.
        near_right_edge = (
            index >= result.n - 1
        )

        ax_i.annotate(
            str(index),
            xy=(index, value),
            xytext=(
                (-7, 8)
                if near_right_edge
                else (5, 8)
            ),
            textcoords="offset points",
            ha=(
                "right"
                if near_right_edge
                else "left"
            ),
            fontsize=9,
            color="#b91c1c",
            fontweight="bold",
            zorder=7,
        )

    # =====================================
    # 7. MOVING RANGE TEST 1 SIGNALS
    # =====================================

    for index in result.mr_violations:

        # MR(i) uses observation number i.
        # The first MR is stored at index 0
        # and belongs to observation 2.

        value = result.moving_ranges[index - 2]

        ax_mr.scatter(
            [index],
            [value],
            color="#dc2626",
            s=75,
            edgecolors="white",
            linewidths=1,
            zorder=6,
        )

        near_right_edge = (
            index >= result.n - 1
        )

        ax_mr.annotate(
            str(index),
            xy=(index, value),
            xytext=(
                (-7, 8)
                if near_right_edge
                else (5, 8)
            ),
            textcoords="offset points",
            ha=(
                "right"
                if near_right_edge
                else "left"
            ),
            fontsize=9,
            color="#b91c1c",
            fontweight="bold",
            zorder=7,
        )

    # =====================================
    # 8. CHART TITLES
    # =====================================

    ax_i.set_title(
        f"Individuals (I) Chart — {result.column_name}",
        fontsize=12,
        pad=12,
        color="#0F172A",
    )

    ax_i.set_ylabel(
        result.column_name,
        fontsize=10,
        labelpad=10,
    )

    ax_mr.set_title(
        "Moving Range (MR) Chart — span 2",
        fontsize=12,
        pad=12,
        color="#0F172A",
    )

    ax_mr.set_ylabel(
        "Moving range",
        fontsize=10,
        labelpad=10,
    )

    # =====================================
    # 9. X AXIS
    # =====================================

    ax_mr.set_xlabel(
        "Observation (time order)",
        fontsize=10,
        labelpad=10,
    )

    ax_mr.set_xlim(
        0.5,
        result.n + 0.5,
    )

    ax_mr.xaxis.set_major_locator(
        MaxNLocator(
            integer=True,
            nbins=12,
        )
    )

    # =====================================
    # 10. MAIN TITLE
    # =====================================

    figure.suptitle(
        "StatDesk | I-MR Control Chart — Phase I",
        fontsize=16,
        fontweight="medium",
        color="#0F172A",
        y=0.965,
    )

    # =====================================
    # 11. LAYOUT
    # =====================================

    figure.subplots_adjust(
        left=0.10,
        right=0.97,
        top=0.865,
        bottom=0.265,
        hspace=0.46,
    )

    # =====================================
    # 12. PRELIMINARY WARNING
    # =====================================

    if result.n < 100:

        warning_text = (
            f"PRELIMINARY — N={result.n} observations. "
            "Review process stability before "
            "approving control limits."
        )

        warning_color = "#B45309"

    else:

        warning_text = (
            f"N={result.n} observations. "
            "Control limits still require "
            "QC/QA validation."
        )

        warning_color = "#475569"

    figure.text(
        0.5,
        0.125,
        warning_text,
        ha="center",
        va="center",
        fontsize=9,
        color=warning_color,
    )

    # =====================================
    # 13. METHOD INFORMATION
    # =====================================

    figure.text(
        0.5,
        0.080,
        (
            "Phase I  |  "
            "MR span = 2  |  "
            "MR(i) represents observations i-1 and i"
        ),
        ha="center",
        va="center",
        fontsize=8,
        color="#475569",
    )

    # =====================================
    # 14. SPC RULES FOOTER
    # =====================================

    # Preserve the "Test 1 only" phrase.
    #
    # spc_rules_overlay.py replaces this
    # phrase with the selected active tests
    # when Advanced SPC mode is enabled.

    figure.text(
        0.5,
        0.045,
        (
            "Test 1 only"
            "  |  "
            "Control limits are NOT "
            "specification limits"
        ),
        ha="center",
        va="center",
        fontsize=8,
        color="#64748B",
    )

    # =====================================
    # 15. RETURN FIGURE
    # =====================================

    return figure
