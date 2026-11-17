
"""StatDesk — I-MR Control Chart Visualization (R3.15).

Display-only improvements:
- Move legends outside the plotting areas.
- Keep Test 1 labels visible near chart edges.
- Use statistical guidance without QA approval wording.
- Preserve compatibility with optional SPC Tests 2-4 overlays.

All measurements, control limits, and signal indices come from
SpcEngine. No statistical calculations are performed here.
"""

from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from statdesk.statistics.spc_engine import ImrResult
from statdesk.statistics.spc_number_format import format_spc_number


# ======================================================
# 1. VISUAL STYLE
# ======================================================

DATA_COLOR = "#2563eb"
LIMIT_COLOR = "#dc2626"
CENTER_COLOR = "#059669"
SIGNAL_COLOR = "#dc2626"
TITLE_COLOR = "#0F172A"
TEXT_COLOR = "#475569"
GRID_COLOR = "#CBD5E1"

PRELIMINARY_OBSERVATIONS = 100


# ======================================================
# 2. AXIS APPEARANCE
# ======================================================

def _style_axis(ax):
    """Apply consistent presentation without changing data."""

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


def _add_control_limits(ax, lower, center, upper):
    """Plot original, unrounded control limits from the engine."""

    ax.axhline(
        y=upper,
        color=LIMIT_COLOR,
        linestyle="--",
        linewidth=1.4,
        label="UCL = " + format_spc_number(upper),
        zorder=2,
    )

    ax.axhline(
        y=center,
        color=CENTER_COLOR,
        linestyle="-",
        linewidth=1.3,
        label="CL = " + format_spc_number(center),
        zorder=2,
    )

    ax.axhline(
        y=lower,
        color=LIMIT_COLOR,
        linestyle="--",
        linewidth=1.4,
        label="LCL = " + format_spc_number(lower),
        zorder=2,
    )


def _add_external_legend(ax):
    """Keep the legend in the reserved right-hand figure margin."""

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
# 3. TEST 1 SIGNAL MARKERS
# ======================================================

def _add_test1_markers(
    ax,
    values,
    signal_positions,
    *,
    first_observation,
):
    """Draw engine-detected signals using original observation numbers.

    first_observation = 1 for Individuals, 2 for Moving Range.
    Annotation offsets point inward near the top and right edges.
    """

    if not signal_positions:
        return

    # Markers use original observations, not reindexed series values.
    plotted = []

    for number in signal_positions:
        value = values[number - first_observation]
        plotted.append((number, value))

    for idx, (number, value) in enumerate(plotted):
        ax.scatter(
            [number],
            [value],
            color=SIGNAL_COLOR,
            s=75,
            edgecolors="white",
            linewidths=1,
            zorder=6,
            label="Test 1 signal" if idx == 0 else "_nolegend_",
        )

    # Give signal numbers breathing room while keeping all original
    # measurement coordinates and control limits unchanged.
    ax.margins(y=0.13)

    x_min, x_max = ax.get_xlim()
    y_min, y_max = ax.get_ylim()
    x_span = max(x_max - x_min, 1.0)
    y_span = max(y_max - y_min, 1e-12)

    for number, value in plotted:
        x_fraction = (number - x_min) / x_span
        y_fraction = (value - y_min) / y_span

        if x_fraction >= 0.80:
            dx, horizontal = -8, "right"
        else:
            dx, horizontal = 8, "left"

        if y_fraction >= 0.78:
            dy, vertical = -11, "top"
        else:
            dy, vertical = 9, "bottom"

        ax.annotate(
            str(number),
            xy=(number, value),
            xytext=(dx, dy),
            textcoords="offset points",
            ha=horizontal,
            va=vertical,
            fontsize=9,
            color="#b91c1c",
            fontweight="bold",
            annotation_clip=True,
            zorder=7,
        )


# ======================================================
# 4. CREATE I-MR FIGURE
# ======================================================

def create_imr_figure(result: ImrResult) -> Figure:
    """Create an I-MR chart with two axes for the existing GUI.

    The first axes is Individuals and the second is Moving Range.
    This order is required by spc_rules_overlay.py.
    """

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

    # Reserve the right margin for legends and the bottom
    # portion for method notes. Do not use tight_layout().
    figure.subplots_adjust(
        left=0.10,
        right=0.75,
        top=0.865,
        bottom=0.265,
        hspace=0.46,
    )

    # Individuals use observation numbers 1..N.
    x_i = list(range(1, result.n + 1))

    # MR(i) is the difference between observations i-1 and i.
    # Thus the first MR corresponds to observation number 2.
    x_mr = list(range(2, result.n + 1))

    ax_i.plot(
        x_i,
        result.values,
        color=DATA_COLOR,
        linewidth=1.4,
        marker="o",
        markersize=4.5,
        label="Individual values",
        zorder=3,
    )

    ax_mr.plot(
        x_mr,
        result.moving_ranges,
        color=DATA_COLOR,
        linewidth=1.4,
        marker="o",
        markersize=4.5,
        label="Moving ranges",
        zorder=3,
    )

    _add_control_limits(
        ax_i,
        result.i_lcl,
        result.i_center,
        result.i_ucl,
    )

    _add_control_limits(
        ax_mr,
        result.mr_lcl,
        result.mr_center,
        result.mr_ucl,
    )

    for ax in (ax_i, ax_mr):
        _style_axis(ax)

    # Set the shared x range before positioning signal labels.
    ax_mr.set_xlim(0.5, result.n + 0.5)

    _add_test1_markers(
        ax_i,
        result.values,
        result.i_violations,
        first_observation=1,
    )

    _add_test1_markers(
        ax_mr,
        result.moving_ranges,
        result.mr_violations,
        first_observation=2,
    )

    ax_i.set_title(
        f"Individuals (I) Chart — {result.column_name}",
        fontsize=12,
        pad=12,
        color=TITLE_COLOR,
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
        color=TITLE_COLOR,
    )

    ax_mr.set_ylabel(
        "Moving range",
        fontsize=10,
        labelpad=10,
    )

    ax_mr.set_xlabel(
        "Observation (time order)",
        fontsize=10,
        labelpad=10,
    )

    ax_mr.xaxis.set_major_locator(
        MaxNLocator(integer=True, nbins=12)
    )

    # Legends must be added after plotting the Test 1 markers.
    _add_external_legend(ax_i)
    _add_external_legend(ax_mr)

    figure.suptitle(
        "StatDesk | I-MR Control Chart — Phase I",
        fontsize=16,
        fontweight="medium",
        color=TITLE_COLOR,
        y=0.965,
    )

    if result.n < PRELIMINARY_OBSERVATIONS:
        warning_text = (
            f"PRELIMINARY — N={result.n} observations. "
            "Review process stability before using these limits."
        )
        warning_color = "#B45309"
    else:
        warning_text = (
            f"N={result.n} observations. "
            "Interpret control limits alongside process stability."
        )
        warning_color = TEXT_COLOR

    figure.text(
        0.5,
        0.125,
        warning_text,
        ha="center",
        va="center",
        fontsize=9,
        color=warning_color,
    )

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
        color=TEXT_COLOR,
    )

    # The substring "Test 1 only" is intentionally preserved.
    # spc_rules_overlay.py replaces it in Advanced SPC mode.
    figure.text(
        0.5,
        0.045,
        (
            "Test 1 only"
            "  |  "
            "Control limits are NOT specification limits"
        ),
        ha="center",
        va="center",
        fontsize=8,
        color="#64748B",
    )

    return figure
