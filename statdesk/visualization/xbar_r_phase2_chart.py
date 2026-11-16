
"""StatDesk R3.3 — Xbar-R Phase II control chart visualization.

Draw a two-panel Matplotlib figure from Phase2XbarRResult:
    - Xbar: new subgroup means versus fixed historical limits.
    - R: new subgroup ranges versus fixed historical limits.
    - SPC Tests 1–4: group findings by plotted subgroup.

This module never estimates parameters, recalculates control limits,
or evaluates SPC rules. Only the supplied engine result is plotted.
"""

from math import isfinite
from numbers import Real

from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from statdesk.statistics.spc_number_format import format_spc_number
from statdesk.statistics.spc_phase2 import (
    Phase2XbarRResult,
    XbarRHistoricalLimits,
)
from statdesk.statistics.spc_rules import RulesResult


class XbarRPhase2ChartError(ValueError):
    """Invalid or inconsistent Phase II data for plotting."""


# ======================================================
# 1. CHART STYLE
# ======================================================

DATA_COLOR = "#2563eb"
LIMIT_COLOR = "#dc2626"
CENTER_COLOR = "#059669"
TEST1_COLOR = "#dc2626"
OTHER_TEST_COLOR = "#9333ea"
TEXT_COLOR = "#334155"

# All signal markers remain visible.
# Text annotations are reduced on densely
# signalled charts to avoid excessive overlap.

MAX_SIGNAL_ANNOTATIONS = 40


# ======================================================
# 2. NUMERICAL VALIDATION
# ======================================================

def _numeric(value, label):
    """Validate a finite numeric value."""

    if (
        isinstance(value, bool)
        or not isinstance(value, Real)
    ):
        raise XbarRPhase2ChartError(
            f"{label} harus angka Numeric."
        )

    try:
        number = float(value)

    except (
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise XbarRPhase2ChartError(
            f"{label} tidak dapat dikonversi."
        ) from exc

    if not isfinite(number):
        raise XbarRPhase2ChartError(
            f"{label} tidak boleh NaN/Infinity."
        )

    return number


# ======================================================
# 3. VALIDATE ENGINE RESULT
# ======================================================

def _validate_result(result):
    """Check plotting contracts without recomputing statistics."""

    if not isinstance(
        result,
        Phase2XbarRResult,
    ):
        raise XbarRPhase2ChartError(
            "Diperlukan Phase2XbarRResult dari "
            "monitor_xbar_r_phase2()."
        )

    reference = result.baseline

    if not isinstance(
        reference,
        XbarRHistoricalLimits,
    ):
        raise XbarRPhase2ChartError(
            "Historical limits tidak valid."
        )

    if (
        type(reference.subgroup_size) is not int
        or not 2 <= reference.subgroup_size <= 8
    ):
        raise XbarRPhase2ChartError(
            "Subgroup size harus 2 sampai 8."
        )

    count = len(result.means)

    if (
        count < 1
        or len(result.ranges) != count
    ):
        raise XbarRPhase2ChartError(
            "Panjang data monitoring tidak konsisten."
        )

    # ======================================
    # VALIDATE PLOTTED VALUES
    # ======================================

    for panel_name, values in (
        ("Xbar", result.means),
        ("R", result.ranges),
    ):

        for index, value in enumerate(
            values,
            start=1,
        ):

            number = _numeric(
                value,
                f"{panel_name} subgroup {index}",
            )

            if (
                panel_name == "R"
                and number < 0.0
            ):
                raise XbarRPhase2ChartError(
                    f"Range subgroup {index} "
                    "tidak boleh negatif."
                )

    # ======================================
    # VALIDATE HISTORICAL CONTROL LIMITS
    # ======================================

    for name, lower, center, upper in (
        (
            "Xbar",
            reference.xbar_lcl,
            reference.xbar_cl,
            reference.xbar_ucl,
        ),
        (
            "R",
            reference.r_lcl,
            reference.r_cl,
            reference.r_ucl,
        ),
    ):

        lcl = _numeric(
            lower,
            f"{name} LCL",
        )

        cl = _numeric(
            center,
            f"{name} CL",
        )

        ucl = _numeric(
            upper,
            f"{name} UCL",
        )

        if not lcl < cl < ucl:
            raise XbarRPhase2ChartError(
                f"{name} membutuhkan LCL < CL < UCL."
            )

        if name == "R" and lcl < 0:
            raise XbarRPhase2ChartError(
                "R LCL tidak boleh negatif."
            )

    # ======================================
    # VALIDATE SPC RULE RESULTS
    # ======================================

    for name, rules in (
        ("Xbar", result.xbar_rules),
        ("R", result.r_rules),
    ):

        if (
            not isinstance(rules, RulesResult)
            or rules.n_points != count
        ):
            raise XbarRPhase2ChartError(
                f"Jumlah SPC points untuk "
                f"{name} tidak sesuai."
            )

        for finding in rules.findings:

            if (
                type(finding.point) is not int
                or not 1 <= finding.point <= count
                or finding.test not in rules.enabled_tests
            ):
                raise XbarRPhase2ChartError(
                    f"SPC signal {name} memiliki "
                    "test/indeks tidak valid."
                )

    if (
        result.xbar_rules.enabled_tests
        != result.r_rules.enabled_tests
        or result.xbar_rules.rule_profile
        != result.r_rules.rule_profile
    ):
        raise XbarRPhase2ChartError(
            "Konfigurasi SPC Tests pada "
            "Xbar dan R berbeda."
        )

    return reference, count


# ======================================================
# 4. GROUP SPC SIGNALS
# ======================================================

def _group_signals(rules):
    """Return subgroup numbers and their detected tests.

    Example:
        {
            8: (1, 3),
            9: (1, 2, 3),
        }

    The rule engine supplies 1-based indexes.
    """

    signals = {}

    for finding in rules.findings:

        signals.setdefault(
            finding.point,
            set(),
        ).add(
            finding.test
        )

    return {
        point: tuple(sorted(tests))
        for point, tests in sorted(signals.items())
    }


# ======================================================
# 5. SELECT SIGNAL LABELS
# ======================================================

def _labelled_points(points):
    """Reduce crowded annotations without hiding markers."""

    if len(points) <= MAX_SIGNAL_ANNOTATIONS:
        return set(points)

    last = len(points) - 1

    return {
        points[
            round(
                i * last
                / (MAX_SIGNAL_ANNOTATIONS - 1)
            )
        ]
        for i in range(MAX_SIGNAL_ANNOTATIONS)
    }


# ======================================================
# 6. DRAW ONE CONTROL CHART PANEL
# ======================================================

def _draw_panel(
    ax,
    x,
    values,
    *,
    title,
    ylabel,
    lcl,
    cl,
    ucl,
    rules,
):
    """Draw one panel using statistical engine results."""

    # ======================================
    # SUBGROUP VALUES
    # ======================================

    ax.plot(
        x,
        values,
        color=DATA_COLOR,
        marker="o",
        markersize=4,
        linewidth=1.4,
        label="Subgroup values",
        zorder=3,
    )

    # ======================================
    # FIXED HISTORICAL CONTROL LIMITS
    # ======================================

    for level, color, style, text in (
        (ucl, LIMIT_COLOR, "--", "UCL"),
        (cl, CENTER_COLOR, "-", "CL"),
        (lcl, LIMIT_COLOR, "--", "LCL"),
    ):

        ax.axhline(
            y=level,
            color=color,
            linestyle=style,
            linewidth=1.25,
            label=(
                f"{text} = "
                f"{format_spc_number(level)}"
            ),
            zorder=2,
        )

    # ======================================
    # PANEL APPEARANCE
    # ======================================

    ax.set_title(
        title,
        fontsize=11,
        pad=11,
    )

    ax.set_ylabel(ylabel)

    ax.set_facecolor("white")
    ax.set_axisbelow(True)

    ax.grid(alpha=0.23)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.margins(y=0.16)

    # A subgroup range cannot be negative.

    if (
        ylabel == "Subgroup range"
        and ax.get_ylim()[0] < 0
    ):
        ax.set_ylim(bottom=0)

    # ======================================
    # GROUP RULE FINDINGS
    # ======================================

    grouped = _group_signals(rules)

    t1_points = [
        point
        for point, tests in grouped.items()
        if 1 in tests
    ]

    other_points = [
        point
        for point, tests in grouped.items()
        if any(test > 1 for test in tests)
    ]

    # ======================================
    # TEST 1 — RED SIGNAL MARKERS
    # ======================================

    if t1_points:

        ax.scatter(
            t1_points,
            [
                values[point - 1]
                for point in t1_points
            ],
            s=70,
            color=TEST1_COLOR,
            edgecolors="white",
            linewidths=0.75,
            label="SPC Test 1 signal",
            zorder=6,
        )

    # ======================================
    # TESTS 2–4 — PURPLE SIGNAL RINGS
    # ======================================

    if other_points:

        ax.scatter(
            other_points,
            [
                values[point - 1]
                for point in other_points
            ],
            s=125,
            facecolors="none",
            edgecolors=OTHER_TEST_COLOR,
            linewidths=1.8,
            label="SPC Tests 2–4 signal",
            zorder=7,
        )

    # ======================================
    # SIGNAL ANNOTATIONS
    # ======================================

    label_points = _labelled_points(
        list(grouped)
    )

    y_bottom, y_top = ax.get_ylim()

    y_span = y_top - y_bottom

    last_index = len(values)

    for point, tests in grouped.items():

        if point not in label_points:
            continue

        value = values[point - 1]

        # One label can show multiple tests.
        # Example: T1/T2/T3

        label = "/".join(
            f"T{test}"
            for test in tests
        )

        near_right = (
            point
            >= max(1, last_index * 0.82)
        )

        near_top = (
            (value - y_bottom) / y_span
            >= 0.75
        )

        ax.annotate(
            label,
            xy=(point, value),
            xytext=(
                -8 if near_right else 8,
                -12 if near_top else 10,
            ),
            textcoords="offset points",
            ha=(
                "right"
                if near_right
                else "left"
            ),
            va=(
                "top"
                if near_top
                else "bottom"
            ),
            fontsize=8,
            fontweight="bold",
            color=(
                TEST1_COLOR
                if tests == (1,)
                else OTHER_TEST_COLOR
            ),
            annotation_clip=True,
            zorder=8,
        )

    # ======================================
    # LEGEND
    # ======================================

    ax.legend(
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        borderaxespad=0,
        fontsize=8,
        frameon=True,
    )

    return (
        len(grouped),
        len(label_points),
    )


# ======================================================
# 7. CREATE COMPLETE XBAR-R PHASE II FIGURE
# ======================================================

def create_xbar_r_phase2_figure(
    result: Phase2XbarRResult,
) -> Figure:
    """Create a two-panel Xbar-R Phase II Figure.

    Parameters
    ----------
    result:
        Output of monitor_xbar_r_phase2().

    Returns
    -------
    matplotlib.figure.Figure:
        Two panels showing subgroup means/ranges,
        historical limits, and SPC signals.

    The Figure can be passed directly to GraphWindow.
    This function does not show or save the figure.
    """

    # ======================================
    # VALIDATE INPUT
    # ======================================

    reference, count = _validate_result(
        result
    )

    x = list(
        range(1, count + 1)
    )

    # ======================================
    # CREATE MATPLOTLIB FIGURE
    # ======================================

    figure = Figure(
        figsize=(11.3, 8.0),
        dpi=100,
        facecolor="white",
    )

    ax_xbar, ax_r = figure.subplots(
        2,
        1,
        sharex=True,
    )

    # ======================================
    # XBAR PANEL
    # ======================================

    xbar_count, xbar_labels = _draw_panel(
        ax_xbar,
        x,
        result.means,

        title=(
            "Xbar Chart — Monitoring "
            "Subgroup Means"
        ),

        ylabel="Subgroup mean",

        lcl=reference.xbar_lcl,
        cl=reference.xbar_cl,
        ucl=reference.xbar_ucl,

        rules=result.xbar_rules,
    )

    # ======================================
    # R PANEL
    # ======================================

    r_count, r_labels = _draw_panel(
        ax_r,
        x,
        result.ranges,

        title=(
            "R Chart — Monitoring "
            "Subgroup Ranges"
        ),

        ylabel="Subgroup range",

        lcl=reference.r_lcl,
        cl=reference.r_cl,
        ucl=reference.r_ucl,

        rules=result.r_rules,
    )

    # ======================================
    # X-AXIS
    # ======================================

    ax_r.set_xlabel(
        "Subgroup (time order)"
    )

    ax_r.set_xlim(
        0.5,
        count + 0.5,
    )

    if count <= 20:

        ax_r.set_xticks(x)

    else:

        ax_r.xaxis.set_major_locator(
            MaxNLocator(
                nbins=12,
                integer=True,
            )
        )

    # ======================================
    # STATISTICAL METADATA
    # ======================================

    active_tests = ", ".join(
        str(test)
        for test in result.xbar_rules.enabled_tests
    )

    if reference.source == "estimated":

        reference_source = (
            "Estimated from historical data"
        )

    else:

        reference_source = (
            "Manually specified "
            "historical parameters"
        )

    # ======================================
    # FIGURE TITLE
    # ======================================

    figure.suptitle(
        "StatDesk | Xbar-R Control Chart — Phase II",
        fontsize=15,
        y=0.983,
    )

    figure.text(
        0.5,
        0.912,
        (
            f"Monitoring subgroups: {count}  |  "
            f"Observations/subgroup: "
            f"{reference.subgroup_size}  |  "
            "Historical limits: FIXED"
        ),
        ha="center",
        fontsize=9,
        color=TEXT_COLOR,
    )

    figure.text(
        0.5,
        0.879,
        reference_source,
        ha="center",
        fontsize=9,
        color=TEXT_COLOR,
    )

    # ======================================
    # FOOTER: SPC CONFIGURATION
    # ======================================

    figure.text(
        0.5,
        0.105,
        (
            f"SPC Tests: {active_tests}  |  "
            f"Profile: "
            f"{result.xbar_rules.rule_profile}"
        ),
        ha="center",
        fontsize=8,
        color=TEXT_COLOR,
    )

    # ======================================
    # FOOTER: SIGNAL INFORMATION
    # ======================================

    if (
        xbar_count > xbar_labels
        or r_count > r_labels
    ):

        footnote = (
            "All signal markers are shown; "
            "some text labels are omitted "
            "for readability."
        )

    else:

        footnote = (
            "Signals marked at their subgroup "
            "position; multiple tests at one "
            "point share a label."
        )

    figure.text(
        0.5,
        0.073,
        footnote,
        ha="center",
        fontsize=8,
        color=TEXT_COLOR,
    )

    # ======================================
    # FOOTER: METHOD INFORMATION
    # ======================================

    figure.text(
        0.5,
        0.044,
        (
            "Historical control limits are not "
            "recalculated from monitoring data; "
            "control limits are not "
            "specification limits."
        ),
        ha="center",
        fontsize=8,
        color=TEXT_COLOR,
    )

    # ======================================
    # LAYOUT SPACING
    # ======================================

    figure.subplots_adjust(
        left=0.105,
        right=0.75,
        top=0.83,
        bottom=0.19,
        hspace=0.48,
    )

    # ======================================
    # RETURN FIGURE
    # ======================================

    return figure
