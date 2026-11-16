
"""StatDesk — Xbar-R Control Chart Visualization (Phase I).

Responsibilities:
- Display subgroup means (Xbar Chart).
- Display subgroup ranges (R Chart).
- Draw UCL, CL and LCL from XbarREngine.
- Highlight Test 1 special-cause signals.
- Support optional Advanced SPC Rules overlays.
- Use the shared SPC number formatter.

Statistical calculations are not performed here.

The control limits and signal positions come
directly from the statistical engine.

Number formatting affects presentation only.
"""

from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from statdesk.statistics.xbar_r_engine import (
    XbarRResult,
    VERSION,
)

from statdesk.statistics.spc_number_format import (
    format_spc_number,
)


# ======================================================
# 1. OBSERVATION COUNT GUIDANCE
# ======================================================

MIN_RECOMMENDED_OBSERVATIONS = {
    2: 100,
    3: 80,
    4: 70,
    5: 70,
    6: 60,
    7: 60,
    8: 60,
}


# ======================================================
# 2. CREATE XBAR-R FIGURE
# ======================================================

def create_xbar_r_figure(
    result: XbarRResult
) -> Figure:
    """Create a Phase I Xbar-R Control Chart.

    Parameters
    ----------
    result : XbarRResult
        Result produced by XbarREngine.calculate().

    Returns
    -------
    Figure
        Matplotlib Figure with two chart panels:
        - Xbar Chart
        - R Chart

    Notes
    -----
    Statistical values are never recalculated.

    Control-limit coordinates retain their
    original floating-point precision.

    Legend labels use the shared formatter.
    """

    # =====================================
    # 1. VALIDATE STATISTICAL RESULT
    # =====================================

    if not isinstance(result, XbarRResult):
        raise TypeError(
            "Expected XbarRResult from "
            "XbarREngine.calculate()."
        )

    m = result.subgroup_count
    n = result.subgroup_size

    if (
        len(result.means) != m
        or len(result.ranges) != m
    ):
        raise ValueError(
            "Panjang data subgrup tidak konsisten."
        )

    if n not in MIN_RECOMMENDED_OBSERVATIONS:
        raise ValueError(
            "Ukuran subgrup Xbar-R tidak valid."
        )

    # =====================================
    # 2. CREATE FIGURE
    # =====================================

    figure = Figure(
        figsize=(11.3, 8.0),
        dpi=100,
        facecolor="white",
    )

    ax_mean, ax_range = figure.subplots(
        2,
        1,
        sharex=True,
    )

    # Subgroup numbering starts at 1.
    x = list(
        range(1, m + 1)
    )

    # =====================================
    # 3. PLOT XBAR VALUES
    # =====================================

    ax_mean.plot(
        x,
        result.means,
        marker="o",
        markersize=4,
        linewidth=1.4,
        color="#2563eb",
        label="Subgroup means",
        zorder=3,
    )

    # =====================================
    # 4. PLOT R VALUES
    # =====================================

    ax_range.plot(
        x,
        result.ranges,
        marker="o",
        markersize=4,
        linewidth=1.4,
        color="#2563eb",
        label="Subgroup ranges",
        zorder=3,
    )

    # =====================================
    # 5. DRAW CONTROL LIMITS
    # =====================================

    # Original control limits are inherited
    # from the statistical calculation engine.
    #
    # Only the legend text is formatted.
    # Line coordinates are never rounded.

    chart_limits = (
        (
            ax_mean,
            result.xbar_lcl,
            result.xbar_cl,
            result.xbar_ucl,
        ),
        (
            ax_range,
            result.r_lcl,
            result.r_cl,
            result.r_ucl,
        ),
    )

    for ax, lcl, cl, ucl in chart_limits:

        # =================================
        # UPPER CONTROL LIMIT
        # =================================

        ax.axhline(
            y=ucl,
            color="#dc2626",
            linestyle="--",
            linewidth=1.3,
            label=(
                "UCL = "
                + format_spc_number(ucl)
            ),
            zorder=2,
        )

        # =================================
        # CENTER LINE
        # =================================

        ax.axhline(
            y=cl,
            color="#059669",
            linestyle="-",
            linewidth=1.2,
            label=(
                "CL = "
                + format_spc_number(cl)
            ),
            zorder=2,
        )

        # =================================
        # LOWER CONTROL LIMIT
        # =================================

        ax.axhline(
            y=lcl,
            color="#dc2626",
            linestyle="--",
            linewidth=1.3,
            label=(
                "LCL = "
                + format_spc_number(lcl)
            ),
            zorder=2,
        )

        # =================================
        # CHART APPEARANCE
        # =================================

        ax.set_facecolor("white")
        ax.set_axisbelow(True)

        ax.grid(
            alpha=0.22,
        )

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # Preserve legend position:
        # outside the plotting area,
        # on the right side.

        ax.legend(
            loc="upper left",
            bbox_to_anchor=(1.01, 1),
            borderaxespad=0,
            fontsize=8,
            frameon=True,
        )

    # =====================================
    # 6. TEST 1 SPECIAL-CAUSE SIGNALS
    # =====================================

    # Test 1 signal positions are provided
    # by XbarREngine.
    #
    # The renderer does not run SPC tests.

    chart_signals = (
        (
            ax_mean,
            result.means,
            result.mean_signals,
        ),
        (
            ax_range,
            result.ranges,
            result.range_signals,
        ),
    )

    for ax, values, signals in chart_signals:

        for index in signals:

            # Subgroup indexes are 1-based.
            value = values[index - 1]

            ax.scatter(
                [index],
                [value],
                s=75,
                color="#dc2626",
                edgecolors="white",
                linewidths=0.8,
                zorder=6,
            )

            ax.annotate(
                str(index),
                xy=(index, value),
                xytext=(5, 7),
                textcoords="offset points",
                color="#b91c1c",
                fontsize=9,
                fontweight="bold",
                zorder=7,
            )

    # =====================================
    # 7. CHART LABELS
    # =====================================

    ax_mean.set_title(
        "Xbar Chart — Subgroup Means",
        pad=10,
    )

    ax_mean.set_ylabel(
        "Subgroup mean",
    )

    ax_range.set_title(
        "R Chart — Subgroup Ranges",
        pad=10,
    )

    ax_range.set_ylabel(
        "Subgroup range",
    )

    ax_range.set_xlabel(
        "Subgroup (time order)",
    )

    ax_range.set_xlim(
        0.5,
        m + 0.5,
    )

    # =====================================
    # 8. X-AXIS SUBGROUP NUMBERING
    # =====================================

    if m <= 20:

        ax_range.set_xticks(x)

    else:

        ax_range.xaxis.set_major_locator(
            MaxNLocator(
                nbins=12,
                integer=True,
            )
        )

    # =====================================
    # 9. MAIN CHART TITLE
    # =====================================

    figure.suptitle(
        "StatDesk | Xbar-R Control Chart — Phase I",
        fontsize=15,
        y=0.982,
    )

    figure.text(
        0.5,
        0.905,
        (
            f"Subgroups = {m}   |   "
            f"Observations/subgroup = {n}   |   "
            f"Total measurements = {m * n}"
        ),
        ha="center",
        fontsize=10,
        color="#334155",
    )

    # =====================================
    # 10. PRELIMINARY WARNING
    # =====================================

    minimum = (
        MIN_RECOMMENDED_OBSERVATIONS[n]
    )

    total_measurements = m * n

    if total_measurements < minimum:

        figure.text(
            0.5,
            0.108,
            (
                f"PRELIMINARY: {total_measurements} "
                "observations; "
                "Minitab recommends at least "
                f"{minimum} for subgroup size {n}."
            ),
            fontsize=9,
            ha="center",
            color="#b45309",
        )

    else:

        figure.text(
            0.5,
            0.108,
            (
                "Observation-count guidance met; "
                "limits still require QC/QA validation."
            ),
            fontsize=9,
            ha="center",
            color="#475569",
        )

    # =====================================
    # 11. METHOD INFORMATION
    # =====================================

    # Preserve "Test 1 only" because
    # the Advanced SPC Rules overlay can
    # replace this text with active tests.

    figure.text(
        0.5,
        0.072,
        (
            "Phase I | Rbar method | "
            "Test 1 only "
            "(strictly beyond 3-sigma limits)"
        ),
        ha="center",
        fontsize=8,
        color="#475569",
    )

    figure.text(
        0.5,
        0.044,
        (
            f"StatDesk Xbar-R engine {VERSION} | "
            "Control limits are NOT "
            "product specifications"
        ),
        ha="center",
        fontsize=8,
        color="#475569",
    )

    # =====================================
    # 12. FIGURE SPACING
    # =====================================

    # Preserve space for the legends
    # outside both plotting areas.

    figure.subplots_adjust(
        left=0.095,
        right=0.77,
        top=0.83,
        bottom=0.205,
        hspace=0.47,
    )

    # =====================================
    # 13. RETURN FIGURE
    # =====================================

    return figure
