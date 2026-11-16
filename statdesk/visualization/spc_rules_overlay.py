
"""StatDesk — SPC Rules 2–4 visualization overlay.

Responsibilities:
- Overlay optional SPC Test 2, 3 and 4 signals.
- Preserve Test 1 markers from base chart renderers.
- Group multiple rules detected at one observation.
- Improve annotation placement near chart boundaries.
- Reduce overlapping labels for nearby signals.
- Update Advanced SPC footer to show active tests.

This module is visualization-only.

It never:
- Recalculates statistical control limits.
- Changes plotted measurement values.
- Changes SPC Rules findings.
- Changes the observation numbering.
"""

from matplotlib.figure import Figure


# ======================================================
# 1. STYLE CONSTANTS
# ======================================================

SIGNAL_COLOR = "#9333EA"
SIGNAL_TEXT_COLOR = "#7E22CE"

SIGNAL_RING_SIZE = 120
SIGNAL_RING_WIDTH = 1.8

SIGNAL_LABEL_SIZE = 8

RIGHT_EDGE_THRESHOLD = 0.78
LEFT_EDGE_THRESHOLD = 0.18

TOP_EDGE_THRESHOLD = 0.78
BOTTOM_EDGE_THRESHOLD = 0.16


# ======================================================
# 2. NORMALIZED POSITION
# ======================================================

def _normalized_position(value, lower, upper):
    """Return a normalized position within given axis limits.

    A value near 0 is close to the lower axis boundary.
    A value near 1 is close to the upper axis boundary.

    Handles nonstandard or reversed axis limits.
    """

    minimum = min(lower, upper)
    maximum = max(lower, upper)

    if maximum == minimum:
        return 0.5

    position = (
        (float(value) - minimum)
        / (maximum - minimum)
    )

    return max(
        0.0,
        min(1.0, position)
    )


# ======================================================
# 3. ANNOTATION POSITION
# ======================================================

def _annotation_position(
    ax,
    x,
    y,
    *,
    nearby=False,
    has_test1=False,
):
    """Choose an inward-facing annotation position.

    Returns:
        xytext, horizontal_alignment, vertical_alignment

    Text positions are expressed in display-point offsets.

    These heuristics reduce clipping and collisions
    without changing the location of a statistical signal.
    """

    x_left, x_right = ax.get_xlim()
    y_bottom, y_top = ax.get_ylim()

    x_fraction = _normalized_position(
        x,
        x_left,
        x_right
    )

    y_fraction = _normalized_position(
        y,
        y_bottom,
        y_top
    )

    # =====================================
    # HORIZONTAL POSITION
    # =====================================

    if x_fraction >= RIGHT_EDGE_THRESHOLD:

        # At the right edge, place text
        # toward the interior of the chart.
        x_offset = -9
        horizontal_alignment = "right"

    elif x_fraction <= LEFT_EDGE_THRESHOLD:

        # At the left edge, place text
        # toward the chart interior.
        x_offset = 9
        horizontal_alignment = "left"

    else:

        x_offset = 8
        horizontal_alignment = "left"

    # =====================================
    # VERTICAL POSITION
    # =====================================

    if y_fraction >= TOP_EDGE_THRESHOLD:

        # Avoid placing labels outside
        # the top boundary.
        y_offset = -11
        vertical_alignment = "top"

    elif y_fraction <= BOTTOM_EDGE_THRESHOLD:

        # Avoid the bottom boundary.
        y_offset = 11
        vertical_alignment = "bottom"

    else:

        y_offset = 11
        vertical_alignment = "bottom"

    # =====================================
    # COLLISION MITIGATION
    # =====================================

    if has_test1:

        # Base renderer already places a red
        # Test 1 observation number above
        # the point. Move optional rule labels
        # below the point where possible.
        if y_fraction > BOTTOM_EDGE_THRESHOLD:
            y_offset = -12
            vertical_alignment = "top"

    elif nearby:

        # Alternate the vertical direction
        # for nearby rule labels, provided
        # there is enough vertical space.
        if (
            y_fraction > BOTTOM_EDGE_THRESHOLD
            and y_fraction < TOP_EDGE_THRESHOLD
        ):
            y_offset = -12
            vertical_alignment = "top"

    # =====================================
    # UPPER-LEFT LEGEND MITIGATION
    # =====================================

    # I-MR charts place their legends
    # inside the upper-left corner.
    #
    # Move a nearby label toward the lower
    # portion of the plot to reduce overlap.

    legend = ax.get_legend()

    if (
        legend is not None
        and x_fraction < 0.30
        and y_fraction > 0.72
    ):
        y_offset = -15
        vertical_alignment = "top"

    return (
        (x_offset, y_offset),
        horizontal_alignment,
        vertical_alignment,
    )


# ======================================================
# 4. GROUP OPTIONAL RULE FINDINGS
# ======================================================

def _group_optional_findings(panel):
    """Group Tests 2–4 by their plotted point index.

    Test 1 is excluded because it is already
    rendered by each original SPC chart.
    """

    grouped = {}

    for finding in panel.result.findings:

        if finding.test not in (2, 3, 4):
            continue

        point = finding.point

        if not (
            isinstance(point, int)
            and 1 <= point <= len(panel.values)
        ):
            raise ValueError(
                "SPC rule finding memiliki "
                "nomor titik di luar rentang data."
            )

        grouped.setdefault(
            point,
            set()
        ).add(finding.test)

    return grouped


# ======================================================
# 5. ACTIVE SPC TESTS FOOTER
# ======================================================

def _update_footer(
    figure,
    assessment
):
    """Replace the legacy Test 1-only label.

    The base I-MR, Xbar-R and Xbar-S renderers
    have slightly different footer wording.
    """

    active_tests = ", ".join(
        str(number)
        for number in assessment.enabled_tests
    )

    replacement = (
        f"Active SPC Tests: {active_tests}"
    )

    # Specific phrases first so that
    # only the complete legacy text is replaced.

    old_labels = (
        "Test 1 only (strictly beyond 3-sigma limits)",
        "Test 1 only (strictly beyond 3-sigma control limits)",
        "Test 1 only (3-sigma)",
        "Test 1 only",
    )

    for text_artist in figure.texts:

        current_text = text_artist.get_text()

        for old_label in old_labels:

            if old_label in current_text:

                updated_text = current_text.replace(
                    old_label,
                    replacement
                )

                text_artist.set_text(
                    updated_text
                )

                break


# ======================================================
# 6. DRAW OPTIONAL SIGNALS
# ======================================================

def _draw_panel_signals(
    ax,
    panel,
):
    """Draw Test 2–4 markers for one SPC panel."""

    grouped = _group_optional_findings(panel)

    if not grouped:
        return

    # All Test 1 findings for this panel.
    test1_points = {
        finding.point
        for finding in panel.result.findings
        if finding.test == 1
    }

    last_x = None
    last_y = None

    x_left, x_right = ax.get_xlim()
    y_bottom, y_top = ax.get_ylim()

    x_span = abs(x_right - x_left)
    y_span = abs(y_top - y_bottom)

    for point, tests in sorted(
        grouped.items()
    ):

        # =====================================
        # ORIGINAL OBSERVATION NUMBER
        # =====================================

        x = (
            point
            + panel.first_observation
            - 1
        )

        # Rule result positions are 1-based.
        y = panel.values[point - 1]

        # =====================================
        # GROUP MULTIPLE TEST LABELS
        # =====================================

        # Examples:
        # T2
        # T3
        # T2/T3
        # T2/T3/T4

        label = "/".join(
            f"T{number}"
            for number in sorted(tests)
        )

        # =====================================
        # DETECT NEARBY LABELS
        # =====================================

        nearby = False

        if (
            last_x is not None
            and last_y is not None
        ):

            x_distance = abs(x - last_x)
            y_distance = abs(y - last_y)

            # Approximately adjacent points
            # at similar vertical positions.
            nearby = (
                x_span > 0
                and y_span > 0
                and x_distance / x_span < 0.075
                and y_distance / y_span < 0.12
            )

        # =====================================
        # CHOOSE LABEL POSITION
        # =====================================

        (
            text_offset,
            horizontal_alignment,
            vertical_alignment
        ) = _annotation_position(
            ax,
            x,
            y,
            nearby=nearby,
            has_test1=(point in test1_points),
        )

        # =====================================
        # DRAW PURPLE SIGNAL RING
        # =====================================

        ax.scatter(
            [x],
            [y],
            s=SIGNAL_RING_SIZE,
            facecolors="none",
            edgecolors=SIGNAL_COLOR,
            linewidths=SIGNAL_RING_WIDTH,
            zorder=9,
        )

        # =====================================
        # DRAW RULE LABEL
        # =====================================

        ax.annotate(
            label,
            xy=(x, y),
            xytext=text_offset,
            textcoords="offset points",
            ha=horizontal_alignment,
            va=vertical_alignment,
            fontsize=SIGNAL_LABEL_SIZE,
            fontweight="bold",
            color=SIGNAL_TEXT_COLOR,
            annotation_clip=True,
            zorder=10,
        )

        last_x = x
        last_y = y


# ======================================================
# 7. PUBLIC OVERLAY FUNCTION
# ======================================================

def overlay_optional_rules(
    figure,
    assessment,
):
    """Overlay optional SPC Tests 2–4 on existing charts.

    Supported base charts:
    - I-MR
    - Xbar-R
    - Xbar-S

    The base figure must contain exactly two
    chart panels with results aligned to the
    original statistical series.

    The function updates figure presentation only.
    """

    # =====================================
    # 1. VALIDATE FIGURE
    # =====================================

    if not isinstance(figure, Figure):
        raise TypeError(
            "Expected Matplotlib Figure."
        )

    if len(figure.axes) != 2:
        raise ValueError(
            "Expected two-panel SPC Figure."
        )

    # =====================================
    # 2. GET SPC PANELS
    # =====================================

    panels = (
        assessment.upper,
        assessment.lower,
    )

    # =====================================
    # 3. DRAW OVERLAYS
    # =====================================

    for ax, panel in zip(
        figure.axes,
        panels
    ):

        _draw_panel_signals(
            ax,
            panel
        )

    # =====================================
    # 4. UPDATE FOOTER
    # =====================================

    _update_footer(
        figure,
        assessment
    )

    return figure
