
"""StatDesk R3.7 — Xbar-R Phase II chart renderer.

Only visualizes the Phase2XbarRResult calculated by spc_phase2.py.
Historical control limits and SPC rule findings are never recalculated.
The header, charts, and footer have separate fixed layout regions.
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
    """Invalid Xbar-R Phase II result passed to the renderer."""


DATA_COLOR = "#2563eb"
LIMIT_COLOR = "#dc2626"
CENTER_COLOR = "#059669"
TEST1_COLOR = "#dc2626"
OTHER_TEST_COLOR = "#9333ea"
TEXT_COLOR = "#334155"

MAX_SIGNAL_ANNOTATIONS = 40


def _numeric(value, label):
    if isinstance(value, bool) or not isinstance(value, Real):
        raise XbarRPhase2ChartError(f"{label} harus angka Numeric.")

    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise XbarRPhase2ChartError(
            f"{label} tidak dapat dikonversi."
        ) from exc

    if not isfinite(number):
        raise XbarRPhase2ChartError(
            f"{label} tidak boleh NaN/Infinity."
        )

    return number


def _validate_result(result):
    """Validate plotting inputs without recomputing any statistics."""

    if not isinstance(result, Phase2XbarRResult):
        raise XbarRPhase2ChartError(
            "Diperlukan Phase2XbarRResult dari monitor_xbar_r_phase2()."
        )

    reference = result.baseline

    if not isinstance(reference, XbarRHistoricalLimits):
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

    if count < 1 or len(result.ranges) != count:
        raise XbarRPhase2ChartError(
            "Panjang data monitoring tidak konsisten."
        )

    for name, values in (
        ("Xbar", result.means),
        ("R", result.ranges),
    ):
        for index, value in enumerate(values, start=1):
            number = _numeric(
                value,
                f"{name} subgroup {index}",
            )

            if name == "R" and number < 0:
                raise XbarRPhase2ChartError(
                    f"Range subgroup {index} tidak boleh negatif."
                )

    for name, lcl, cl, ucl in (
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
        low = _numeric(lcl, f"{name} LCL")
        mid = _numeric(cl, f"{name} CL")
        high = _numeric(ucl, f"{name} UCL")

        if not low < mid < high:
            raise XbarRPhase2ChartError(
                f"{name} membutuhkan LCL < CL < UCL."
            )

        if name == "R" and low < 0:
            raise XbarRPhase2ChartError(
                "R LCL tidak boleh negatif."
            )

    for name, rules in (
        ("Xbar", result.xbar_rules),
        ("R", result.r_rules),
    ):
        if (
            not isinstance(rules, RulesResult)
            or rules.n_points != count
        ):
            raise XbarRPhase2ChartError(
                f"Jumlah SPC points untuk {name} tidak sesuai."
            )

        for finding in rules.findings:
            if (
                type(finding.point) is not int
                or not 1 <= finding.point <= count
                or finding.test not in rules.enabled_tests
            ):
                raise XbarRPhase2ChartError(
                    f"SPC signal {name} memiliki test/indeks tidak valid."
                )

    if (
        result.xbar_rules.enabled_tests
        != result.r_rules.enabled_tests
        or result.xbar_rules.rule_profile
        != result.r_rules.rule_profile
    ):
        raise XbarRPhase2ChartError(
            "Konfigurasi SPC Tests pada Xbar dan R berbeda."
        )

    return reference, count


def _group_signals(rules):
    """Group one or more SPC tests at the same 1-based point."""

    signals = {}

    for finding in rules.findings:
        signals.setdefault(
            finding.point,
            set(),
        ).add(finding.test)

    return {
        point: tuple(sorted(tests))
        for point, tests in sorted(signals.items())
    }


def _labelled_points(points):
    """Show every marker, but cap text labels on crowded charts."""

    if len(points) <= MAX_SIGNAL_ANNOTATIONS:
        return set(points)

    last = len(points) - 1

    return {
        points[round(i * last / (MAX_SIGNAL_ANNOTATIONS - 1))]
        for i in range(MAX_SIGNAL_ANNOTATIONS)
    }


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
    """Draw values, fixed control limits and supplied SPC findings."""

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

    for level, color, style, label in (
        (ucl, LIMIT_COLOR, "--", "UCL"),
        (cl, CENTER_COLOR, "-", "CL"),
        (lcl, LIMIT_COLOR, "--", "LCL"),
    ):
        ax.axhline(
            y=level,
            color=color,
            linestyle=style,
            linewidth=1.25,
            label=f"{label} = {format_spc_number(level)}",
            zorder=2,
        )

    ax.set_title(
        title,
        fontsize=11,
        pad=10,
    )

    ax.set_ylabel(ylabel)
    ax.set_facecolor("white")
    ax.set_axisbelow(True)
    ax.grid(alpha=0.23)

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)

    ax.margins(y=0.16)

    if (
        ylabel == "Subgroup range"
        and ax.get_ylim()[0] < 0
    ):
        ax.set_ylim(bottom=0)

    grouped = _group_signals(rules)

    test1_points = [
        p
        for p, tests in grouped.items()
        if 1 in tests
    ]

    other_points = [
        p
        for p, tests in grouped.items()
        if any(test > 1 for test in tests)
    ]

    if test1_points:
        ax.scatter(
            test1_points,
            [values[p - 1] for p in test1_points],
            s=70,
            color=TEST1_COLOR,
            edgecolors="white",
            linewidths=0.75,
            label="SPC Test 1 signal",
            zorder=6,
        )

    if other_points:
        ax.scatter(
            other_points,
            [values[p - 1] for p in other_points],
            s=125,
            facecolors="none",
            edgecolors=OTHER_TEST_COLOR,
            linewidths=1.8,
            label="SPC Tests 2–4 signal",
            zorder=7,
        )

    to_label = _labelled_points(list(grouped))

    y_bottom, y_top = ax.get_ylim()
    y_span = y_top - y_bottom
    n_points = len(values)

    for point, tests in grouped.items():
        if point not in to_label:
            continue

        value = values[point - 1]

        label = "/".join(
            f"T{test}"
            for test in tests
        )

        near_right = point >= max(
            1,
            n_points * 0.82,
        )

        near_top = (
            (value - y_bottom) / y_span >= 0.75
        )

        ax.annotate(
            label,
            xy=(point, value),
            xytext=(
                -11 if near_right else 9,
                -14 if near_top else 12,
            ),
            textcoords="offset points",
            ha="right" if near_right else "left",
            va="top" if near_top else "bottom",
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

    ax.legend(
        loc="upper left",
        bbox_to_anchor=(1.01, 1.0),
        borderaxespad=0,
        fontsize=8,
        frameon=True,
    )

    return len(grouped), len(to_label)


def create_xbar_r_phase2_figure(
    result: Phase2XbarRResult,
) -> Figure:
    """Create a Figure for GraphWindow, without showing or saving it.

    All Xbar/R values, historical limits and findings come from result.
    Fixed figure zones avoid overlaps between header, panels and footer.
    """

    reference, count = _validate_result(result)

    x = list(range(1, count + 1))

    figure = Figure(
        figsize=(11.3, 8.0),
        dpi=100,
        facecolor="white",
    )

    # ==========================================
    # FIXED LAYOUT REGIONS
    # ==========================================
    #
    # Regions use figure-relative coordinates.
    #
    # HEADER       : above both charts
    # XBAR CHART   : upper chart area
    # R CHART      : lower chart area
    # FOOTER       : below the x-axis label
    #
    # Right margin is reserved for legends.
    #
    # Do not call tight_layout() or
    # constrained_layout() after this setup.
    # ==========================================

    ax_xbar = figure.add_axes(
        [0.105, 0.565, 0.64, 0.205]
    )

    ax_r = figure.add_axes(
        [0.105, 0.275, 0.64, 0.205],
        sharex=ax_xbar,
    )

    # ==========================================
    # XBAR CHART
    # ==========================================

    xbar_count, xbar_labels = _draw_panel(
        ax_xbar,
        x,
        result.means,
        title="Xbar Chart — Monitoring Subgroup Means",
        ylabel="Subgroup mean",
        lcl=reference.xbar_lcl,
        cl=reference.xbar_cl,
        ucl=reference.xbar_ucl,
        rules=result.xbar_rules,
    )

    # ==========================================
    # R CHART
    # ==========================================

    r_count, r_labels = _draw_panel(
        ax_r,
        x,
        result.ranges,
        title="R Chart — Monitoring Subgroup Ranges",
        ylabel="Subgroup range",
        lcl=reference.r_lcl,
        cl=reference.r_cl,
        ucl=reference.r_ucl,
        rules=result.r_rules,
    )

    # ==========================================
    # X AXIS
    # ==========================================

    ax_r.set_xlabel(
        "Subgroup (time order)",
        labelpad=10,
    )

    ax_r.set_xlim(
        0.5,
        count + 0.5,
    )

    ax_xbar.tick_params(
        axis="x",
        labelbottom=False,
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

    # ==========================================
    # STATISTICAL METADATA
    # ==========================================

    reference_source = (
        "Estimated from historical data"
        if reference.source == "estimated"
        else "Manually specified historical parameters"
    )

    active_tests = ", ".join(
        str(test)
        for test in result.xbar_rules.enabled_tests
    )

    # ==========================================
    # HEADER
    # ==========================================

    figure.text(
        0.5,
        0.966,
        "StatDesk | Xbar-R Control Chart — Phase II",
        ha="center",
        va="center",
        fontsize=15,
        color="black",
    )

    figure.text(
        0.5,
        0.916,
        (
            f"Monitoring subgroups: {count}  |  "
            f"Observations/subgroup: {reference.subgroup_size}  |  "
            "Historical limits: FIXED"
        ),
        ha="center",
        va="center",
        fontsize=9,
        color=TEXT_COLOR,
    )

    figure.text(
        0.5,
        0.867,
        reference_source,
        ha="center",
        va="center",
        fontsize=9,
        color=TEXT_COLOR,
    )

    # ==========================================
    # FOOTER — SPC CONFIGURATION
    # ==========================================

    figure.text(
        0.5,
        0.145,
        (
            f"SPC Tests: {active_tests}  |  "
            f"Profile: {result.xbar_rules.rule_profile}"
        ),
        ha="center",
        va="center",
        fontsize=8,
        color=TEXT_COLOR,
    )

    # ==========================================
    # FOOTER — SIGNAL INFORMATION
    # ==========================================

    if (
        xbar_count > xbar_labels
        or r_count > r_labels
    ):
        footnote = (
            "All signal markers are shown; some text labels "
            "are omitted for readability."
        )
    else:
        footnote = (
            "Signals marked at their subgroup position; "
            "multiple tests at one point share a label."
        )

    figure.text(
        0.5,
        0.099,
        footnote,
        ha="center",
        va="center",
        fontsize=8,
        color=TEXT_COLOR,
    )

    # ==========================================
    # FOOTER — METHOD INFORMATION
    # ==========================================

    figure.text(
        0.5,
        0.054,
        (
            "Historical limits are not recalculated from "
            "monitoring data; control limits are not "
            "specification limits."
        ),
        ha="center",
        va="center",
        fontsize=8,
        color=TEXT_COLOR,
    )

    return figure
