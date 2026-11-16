
"""StatDesk Xbar-S Phase I chart renderer (no Qt dependency).

Responsibilities:
- Render subgroup means and standard deviations.
- Display UCL, CL, and LCL from XbarSEngine.
- Highlight Test 1 special-cause signals.
- Preserve compatibility with Advanced SPC Rules.
- Use the shared SPC number formatter.

Statistical values originate from XbarSEngine.

This module only presents the results and
does not recalculate control limits.

Formatting affects display labels only.
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
# 1. EXCEPTION
# ======================================================

class XbarSChartError(ValueError):
    """Invalid/inconsistent result given to the renderer."""


# ======================================================
# 2. CREATE XBAR-S FIGURE
# ======================================================

def create_xbar_s_figure(result: XbarSResult) -> Figure:
    """Create a two-panel Phase I Xbar-S chart.

    Panels:
    - Xbar Chart: subgroup means
    - S Chart: subgroup sample standard deviations

    Original control limits are inherited from
    the statistical engine.

    Shared number formatting is applied only
    to legend labels.
    """

    # =====================================
    # 1. VALIDATE ENGINE RESULT
    # =====================================

    if not isinstance(result, XbarSResult):
        raise TypeError(
            "Expected XbarSResult from "
            "XbarSEngine.calculate()."
        )

    m = result.subgroup_count
    n = result.subgroup_size

    if m < 2 or not 9 <= n <= 25:
        raise XbarSChartError(
            "Jumlah/ukuran subgrup tidak valid."
        )

    if (
        len(result.subgroup_means) != m
        or len(result.subgroup_stdevs) != m
    ):
        raise XbarSChartError(
            "Panjang hasil subgrup tidak konsisten."
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
            "Hasil numerik tidak finite."
        )

    signals = (
        *result.xbar_signals,
        *result.s_signals,
    )

    if any(
        index < 1 or index > m
        for index in signals
    ):
        raise XbarSChartError(
            "Nomor sinyal di luar rentang subgrup."
        )

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

    # Subgroup numbering starts at 1.
    x = list(
        range(1, m + 1)
    )

    # =====================================
    # 3. XBAR CHART DATA
    # =====================================

    ax_xbar.plot(
        x,
        result.subgroup_means,
        color="#2563eb",
        linewidth=1.4,
        marker="o",
        markersize=4,
        label="Subgroup means",
    )

    # =====================================
    # 4. S CHART DATA
    # =====================================

    ax_s.plot(
        x,
        result.subgroup_stdevs,
        color="#2563eb",
        linewidth=1.4,
        marker="o",
        markersize=4,
        label="Subgroup SD (n-1)",
    )

    # =====================================
    # 5. DRAW CONTROL LIMITS
    # =====================================

    # The statistical engine provides
    # all UCL, CL, and LCL values.
    #
    # Do not recalculate or round them
    # before drawing the horizontal lines.
    #
    # format_spc_number() converts values
    # to text only for the legend.

    chart_limits = (
        (
            ax_xbar,
            result.xbar_lcl,
            result.xbar_center,
            result.xbar_ucl,
        ),
        (
            ax_s,
            result.s_lcl,
            result.s_center,
            result.s_ucl,
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
            linewidth=1.25,
            label=(
                "UCL = "
                + format_spc_number(ucl)
            ),
        )

        # =================================
        # CENTER LINE
        # =================================

        ax.axhline(
            y=cl,
            color="#059669",
            linewidth=1.25,
            label=(
                "CL = "
                + format_spc_number(cl)
            ),
        )

        # =================================
        # LOWER CONTROL LIMIT
        # =================================

        ax.axhline(
            y=lcl,
            color="#dc2626",
            linestyle="--",
            linewidth=1.25,
            label=(
                "LCL = "
                + format_spc_number(lcl)
            ),
        )

        # =================================
        # CHART APPEARANCE
        # =================================

        ax.set_facecolor("white")

        ax.grid(
            alpha=0.22,
        )

        ax.set_axisbelow(True)

        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

        # Preserve legend placement
        # outside the plotting area.

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

    # Signal detection is performed
    # by the statistical calculation engine.
    #
    # This renderer only displays signals
    # at their original subgroup indexes.

    chart_signals = (
        (
            ax_xbar,
            result.subgroup_means,
            result.xbar_signals,
        ),
        (
            ax_s,
            result.subgroup_stdevs,
            result.s_signals,
        ),
    )

    for ax, values, signal_indexes in chart_signals:

        for subgroup_number in signal_indexes:

            # Subgroup numbering is 1-based.
            y = values[subgroup_number - 1]

            ax.scatter(
                [subgroup_number],
                [y],
                s=75,
                color="#dc2626",
                edgecolors="white",
                linewidths=0.8,
                zorder=6,
            )

            ax.annotate(
                str(subgroup_number),
                (subgroup_number, y),
                xytext=(5, 7),
                textcoords="offset points",
                fontsize=9,
                fontweight="bold",
                color="#b91c1c",
            )

    # =====================================
    # 7. CHART LABELS
    # =====================================

    ax_xbar.set_title(
        "Xbar Chart — Subgroup Means",
        pad=10,
    )

    ax_xbar.set_ylabel(
        "Subgroup mean",
    )

    ax_s.set_title(
        "S Chart — Subgroup Standard Deviations",
        pad=10,
    )

    ax_s.set_ylabel(
        "Subgroup SD",
    )

    ax_s.set_xlabel(
        "Subgroup (time order)",
    )

    ax_s.set_xlim(
        0.5,
        m + 0.5,
    )

    # =====================================
    # 8. SUBGROUP INDEX LABELS
    # =====================================

    if m <= 20:

        ax_s.set_xticks(x)

    else:

        ax_s.xaxis.set_major_locator(
            MaxNLocator(
                nbins=12,
                integer=True,
            )
        )

    # =====================================
    # 9. MAIN TITLE
    # =====================================

    figure.suptitle(
        "StatDesk | Xbar-S Control Chart — Phase I",
        fontsize=15,
        y=0.981,
    )

    figure.text(
        0.5,
        0.920,
        (
            f"Subgroups = {m}   |   "
            f"Measurements/subgroup = {n}   |   "
            f"Total = {m * n}"
        ),
        ha="center",
        fontsize=10,
        color="#334155",
    )

    # =====================================
    # 10. PRELIMINARY WARNING
    # =====================================

    is_preliminary = any(
        "PRELIMINARY" in warning
        for warning in result.warnings
    )

    if is_preliminary:

        warning_text = (
            f"PRELIMINARY: N={m * n} measurements; "
            "at least 60 recommended."
        )

    else:

        warning_text = (
            "Observation-count guideline met; "
            "QC/QA validation still required."
        )

    figure.text(
        0.5,
        0.109,
        warning_text,
        ha="center",
        fontsize=9,
        color=(
            "#b45309"
            if is_preliminary
            else "#475569"
        ),
    )

    # =====================================
    # 11. METHOD INFORMATION
    # =====================================

    # Preserve "Test 1 only" for
    # compatibility with Advanced SPC
    # overlays and existing GUI behavior.

    figure.text(
        0.5,
        0.073,
        (
            "Review S Chart first | Phase I | "
            "Sbar/c4 | Test 1 only (3-sigma)"
        ),
        ha="center",
        fontsize=8,
        color="#475569",
    )

    figure.text(
        0.5,
        0.043,
        (
            f"StatDesk Engine {ENGINE_VERSION} | "
            "Control limits are NOT specification limits"
        ),
        ha="center",
        fontsize=8,
        color="#475569",
    )

    # =====================================
    # 12. FIGURE SPACING
    # =====================================

    # Preserve space for the legends
    # to the right of both panels.

    figure.subplots_adjust(
        left=0.095,
        right=0.77,
        top=0.850,
        bottom=0.210,
        hspace=0.50,
    )

    # =====================================
    # 13. RETURN FIGURE
    # =====================================

    return figure
