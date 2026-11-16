
"""StatDesk — Advanced SPC Rules Integration.

Connect existing statistical control chart results
to optional SPC Tests 1 through 4.

Supported charts:
- I-MR
- Xbar-R
- Xbar-S

Responsibilities:
- Evaluate enabled SPC rules.
- Preserve existing statistical control limits.
- Verify Test 1 consistency with the base engine.
- Maintain original observation numbering.
- Support StatDesk and experimental rule profiles.
- Generate Advanced SPC Session Output.
- Format numbers using shared SPC formatter.

Statistical control limits are never recalculated
or modified by this module.
"""

from dataclasses import dataclass

from statdesk.statistics.spc_number_format import (
    format_spc_number,
)

from statdesk.statistics.spc_rules import (
    RULE_PROFILE_STANDARD,
    RULE_PROFILE_LABELS,
    RulesResult,
    SpcRulesError,
    evaluate_spc_rules,
    get_rule_windows,
)


# ======================================================
# 1. RESULT CONTRACTS
# ======================================================

@dataclass(frozen=True)
class PlotRules:
    """Rule assessment for one plotted chart panel."""

    name: str
    values: tuple[float, ...]
    first_observation: int
    result: RulesResult

    # Optional statistical metadata.
    # All control limits originate from
    # the original calculation engine.
    center_line: float | None = None
    ucl: float | None = None
    lcl: float | None = None


@dataclass(frozen=True)
class ControlChartRules:
    """Combined rule assessment for two chart panels."""

    chart_name: str
    enabled_tests: tuple[int, ...]
    upper: PlotRules
    lower: PlotRules

    rule_profile: str = RULE_PROFILE_STANDARD


# ======================================================
# 2. EVALUATE CONTROL CHART RULES
# ======================================================

def evaluate_control_chart_rules(
    kind,
    statistical_result,
    enabled_tests=(1,),
    *,
    rule_profile=RULE_PROFILE_STANDARD,
):
    """Evaluate SPC Rules on existing control chart data.

    Parameters
    ----------
    kind:
        "imr", "xbar_r", or "xbar_s".

    statistical_result:
        Immutable result from the corresponding
        statistical calculation engine.

    enabled_tests:
        Selected SPC Tests. Test 1 is mandatory.

    rule_profile:
        Selected rule-profile identifier.

    Returns
    -------
    ControlChartRules

    Notes
    -----
    Control limits are inherited from the engine.
    They are never recalculated here.

    For I-MR, the first MR point belongs to
    original observation number 2.
    """

    # =====================================
    # 1. VALIDATE RULE PROFILE
    # =====================================

    get_rule_windows(rule_profile)

    # =====================================
    # 2. VALIDATE ENABLED TESTS
    # =====================================

    try:
        selected = tuple(enabled_tests)

    except TypeError as exc:
        raise SpcRulesError(
            "Pilihan SPC Tests tidak valid."
        ) from exc

    if 1 not in selected:
        raise SpcRulesError(
            "Test 1 wajib aktif pada mode ini."
        )

    r = statistical_result

    # =====================================
    # 3. I-MR DATA MAPPING
    # =====================================

    if kind == "imr":

        specs = (
            (
                "Individuals (I)",
                r.values,
                1,
                r.i_center,
                r.i_lcl,
                r.i_ucl,
                r.i_violations,
            ),
            (
                "Moving Range (MR)",
                r.moving_ranges,
                2,
                r.mr_center,
                r.mr_lcl,
                r.mr_ucl,
                r.mr_violations,
            ),
        )

        chart_name = "I-MR"

    # =====================================
    # 4. XBAR-R DATA MAPPING
    # =====================================

    elif kind == "xbar_r":

        specs = (
            (
                "Xbar",
                r.means,
                1,
                r.xbar_cl,
                r.xbar_lcl,
                r.xbar_ucl,
                r.mean_signals,
            ),
            (
                "R",
                r.ranges,
                1,
                r.r_cl,
                r.r_lcl,
                r.r_ucl,
                r.range_signals,
            ),
        )

        chart_name = "Xbar-R"

    # =====================================
    # 5. XBAR-S DATA MAPPING
    # =====================================

    elif kind == "xbar_s":

        specs = (
            (
                "Xbar",
                r.subgroup_means,
                1,
                r.xbar_center,
                r.xbar_lcl,
                r.xbar_ucl,
                r.xbar_signals,
            ),
            (
                "S",
                r.subgroup_stdevs,
                1,
                r.s_center,
                r.s_lcl,
                r.s_ucl,
                r.s_signals,
            ),
        )

        chart_name = "Xbar-S"

    else:
        raise ValueError(
            "Jenis SPC chart tidak dikenal."
        )

    # =====================================
    # 6. EVALUATE BOTH CHART PANELS
    # =====================================

    panels = []

    for (
        label,
        values,
        first,
        center,
        lower,
        upper,
        original_signals,
    ) in specs:

        # =================================
        # CALL EXISTING SPC RULE ENGINE
        # =================================

        rule_result = evaluate_spc_rules(
            values,
            center_line=center,
            lcl=lower,
            ucl=upper,
            enabled_tests=selected,
            rule_profile=rule_profile,
        )

        # =================================
        # 7. VERIFY TEST 1 CONSISTENCY
        # =================================

        # SPC Rules use positions relative
        # to each plotted series.
        #
        # For MR, the first plotted position
        # corresponds to observation number 2.

        detected = tuple(
            index + first - 1
            for index in rule_result.points_for(1)
        )

        if detected != tuple(original_signals):
            raise ValueError(
                f"Ketidaksesuaian Test 1 pada {label}; "
                "analisis dihentikan."
            )

        # =================================
        # 8. STORE PANEL ASSESSMENT
        # =================================

        panels.append(
            PlotRules(
                name=label,
                values=tuple(values),
                first_observation=first,
                result=rule_result,

                # Original, unrounded limits.
                center_line=float(center),
                ucl=float(upper),
                lcl=float(lower),
            )
        )

    # =====================================
    # 9. RETURN COMBINED ASSESSMENT
    # =====================================

    return ControlChartRules(
        chart_name=chart_name,
        enabled_tests=panels[0].result.enabled_tests,
        upper=panels[0],
        lower=panels[1],
        rule_profile=rule_profile,
    )


# ======================================================
# 3. FORMAT ADVANCED SPC RULES REPORT
# ======================================================

def format_control_chart_rules_report(
    assessment: ControlChartRules,
) -> str:
    """Build Advanced SPC Rules Session Output.

    Uses the shared SPC number formatter.

    Formatting is presentation-only and does not
    modify the results of the statistical engine
    or any SPC Rule findings.
    """

    # =====================================
    # 1. PROFILE INFORMATION
    # =====================================

    profile = assessment.rule_profile

    windows = get_rule_windows(profile)

    profile_label = RULE_PROFILE_LABELS[profile]

    tests_text = ", ".join(
        str(number)
        for number in assessment.enabled_tests
    )

    # Shared number formatter.
    f = format_spc_number

    # =====================================
    # 2. REPORT HEADER
    # =====================================

    lines = [
        f"OPTIONAL SPC RULES — {assessment.chart_name}",
        "=" * 56,

        "",

        "SPC RULE CONFIGURATION",
        "-" * 40,

        f"Rule profile       : {profile_label}",
        f"Active SPC Tests   : {tests_text}",

        "Test 1             : point strictly "
        "beyond control limits",

        "Test 2             : 9 points "
        "strictly on the same side of CL",

        f"Test 3             : {windows[3]} points "
        "strictly increasing/decreasing",

        f"Test 4             : {windows[4]} points "
        "strictly alternating",

        "Rule limits        : inherited from "
        "the original Phase I engine",

        "Report precision   : 3 decimals / "
        "scientific notation for extreme values",

        "",

        "SIGNAL RESULTS",
        "-" * 40,
    ]

    # =====================================
    # 3. PER-PANEL RULE REPORTS
    # =====================================

    for panel in (
        assessment.upper,
        assessment.lower,
    ):

        lines.extend([
            "",
            panel.name,
            "-" * 40,
        ])

        # =================================
        # 4. DISPLAY CONTROL LIMITS
        # =================================

        # These limits originate from
        # the corresponding statistical engine.
        #
        # No new limits are calculated.

        if (
            panel.center_line is not None
            and panel.ucl is not None
            and panel.lcl is not None
        ):

            lines.extend([
                f"UCL                : {f(panel.ucl)}",
                f"CL                 : {f(panel.center_line)}",
                f"LCL                : {f(panel.lcl)}",
                "",
            ])

        # =================================
        # 5. FORMAT ENABLED TEST RESULTS
        # =================================

        for test in assessment.enabled_tests:

            findings = [
                finding
                for finding in panel.result.findings
                if finding.test == test
            ]

            if not findings:
                lines.append(
                    f"Test {test}: No signals"
                )
                continue

            labels = []

            for finding in findings:

                # Relative rule positions are
                # converted to original numbers.

                end = (
                    finding.point
                    + panel.first_observation
                    - 1
                )

                start = (
                    finding.window_start
                    + panel.first_observation
                    - 1
                )

                labels.append(
                    f"{end} (window {start}-{end})"
                )

            lines.append(
                f"Test {test}: "
                + ", ".join(labels)
            )

    # =====================================
    # 6. INTERPRETATION NOTES
    # =====================================

    lines.extend([
        "",

        "INTERPRETATION NOTES",
        "-" * 40,

        "- Signal numbers refer to the "
        "last observation of each qualifying window.",

        "- Moving Range signals use the "
        "original observation numbers.",

        "- A point equal to the Center Line "
        "breaks the Test 2 run in this profile.",

        "- Additional tests may increase "
        "false-signal frequency.",

        "- All statistical control limits "
        "remain unchanged.",

        "- Control limits are not "
        "product specification limits.",

        "- Phase I results require "
        "QC/QA investigation and approval.",

        "- Adaptive formatting changes "
        "display only, not calculations.",
    ])

    # =====================================
    # 7. EXPERIMENTAL PROFILE WARNING
    # =====================================

    if profile != RULE_PROFILE_STANDARD:

        lines.extend([
            "",

            "EXPERIMENTAL RULE PROFILE",

            "The selected 7/15 profile is "
            "experimental and has not been "
            "certified as equivalent to "
            "Minitab 18 default behavior.",
        ])

    # =====================================
    # 8. RETURN SESSION OUTPUT
    # =====================================

    return "\n".join(lines)
