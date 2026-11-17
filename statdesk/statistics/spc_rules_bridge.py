
"""StatDesk — Advanced SPC Rules Integration.

R3.16 - Advanced SPC Session Output Refinement.

Supported charts:
- I-MR
- Xbar-R
- Xbar-S

Responsibilities:
- Evaluate SPC Tests 1 through 4.
- Preserve existing statistical control limits.
- Verify Test 1 consistency with the original engine.
- Preserve original observation numbering.
- Support selectable SPC rule profiles.
- Produce detailed Advanced SPC Session Output.
- Distinguish insufficient data from no signals.
- Present statistical interpretation without QA approval.

This module never recalculates statistical control limits.
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

    # Original statistical engine control limits.
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
    """Evaluate SPC Rules using existing chart statistics.

    The function preserves the original R3 implementation.

    All control limits originate from the corresponding
    statistical calculation engine.

    For I-MR:
        Individuals begin at observation 1.
        Moving ranges begin at observation 2.
    """

    # =====================================
    # 1. VALIDATE PROFILE
    # =====================================

    get_rule_windows(rule_profile)

    # =====================================
    # 2. VALIDATE SELECTED TESTS
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
    # 6. EVALUATE BOTH PANELS
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

        # Existing SPC rules engine.
        rule_result = evaluate_spc_rules(
            values,
            center_line=center,
            lcl=lower,
            ucl=upper,
            enabled_tests=selected,
            rule_profile=rule_profile,
        )

        # =================================
        # 7. TEST 1 CONSISTENCY
        # =================================

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
        # 8. STORE ORIGINAL RESULTS
        # =================================

        panels.append(
            PlotRules(
                name=label,
                values=tuple(values),
                first_observation=first,
                result=rule_result,

                center_line=float(center),
                ucl=float(upper),
                lcl=float(lower),
            )
        )

    return ControlChartRules(
        chart_name=chart_name,
        enabled_tests=panels[0].result.enabled_tests,
        upper=panels[0],
        lower=panels[1],
        rule_profile=rule_profile,
    )


# ======================================================
# 3. R3.16 - SIGNAL FORMATTING
# ======================================================

def _format_rule_findings(
    panel: PlotRules,
    test: int,
    required_points: int,
) -> str:
    """Format findings for one selected SPC Test.

    Report states:
    - BELUM CUKUP DATA: The required window cannot complete.
    - No signals: The test was evaluable but had no findings.
    - Signal positions: One or more completed rule windows.

    Observation numbers are translated from relative
    series positions into original worksheet positions.
    """

    n = panel.result.n_points

    # =====================================
    # 1. INSUFFICIENT DATA
    # =====================================

    if n < required_points:
        return (
            f"BELUM CUKUP DATA "
            f"({n}/{required_points} titik)"
        )

    # =====================================
    # 2. FINDINGS FOR THIS TEST
    # =====================================

    findings = [
        finding
        for finding in panel.result.findings
        if finding.test == test
    ]

    if not findings:
        return "No signals"

    # =====================================
    # 3. ORIGINAL OBSERVATION NUMBERS
    # =====================================

    labels = []

    for finding in findings:

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

        if test == 1:
            label = f"T1@{end}"

        else:
            label = (
                f"T{test}@{end} "
                f"(window {start}-{end})"
            )

        labels.append(label)

    return ", ".join(labels)


# ======================================================
# 4. R3.16 - FORMAT PANEL RESULTS
# ======================================================

def _format_panel_report(
    panel: PlotRules,
    enabled_tests,
    windows,
) -> list[str]:
    """Display one panel's fixed limits and SPC Test results."""

    f = format_spc_number

    n = panel.result.n_points

    first = panel.first_observation

    last = (
        first + n - 1
    )

    lines = [
        "",
        panel.name.upper(),
        "-" * 56,

        f"Plotted points       : {n}",
        f"Observation range    : {first}-{last}",
    ]

    # =====================================
    # 1. CONTROL LIMITS
    # =====================================

    if (
        panel.center_line is not None
        and panel.ucl is not None
        and panel.lcl is not None
    ):
        lines.extend([
            "",
            "CONTROL LIMITS",

            f"UCL                  : {f(panel.ucl)}",
            f"CL                   : {f(panel.center_line)}",
            f"LCL                  : {f(panel.lcl)}",
        ])

    # =====================================
    # 2. SIGNAL SUMMARY
    # =====================================

    lines.extend([
        "",
        "SPC TEST RESULTS",
    ])

    for test in enabled_tests:

        status = _format_rule_findings(
            panel,
            test,
            windows[test],
        )

        lines.append(
            f"Test {test}: {status}"
        )

    # =====================================
    # 3. TOTAL FINDINGS
    # =====================================

    lines.extend([
        "",
        f"Total findings       : "
        f"{len(panel.result.findings)}",
    ])

    return lines


# ======================================================
# 5. R3.16 - MAIN SESSION OUTPUT
# ======================================================

def format_control_chart_rules_report(
    assessment: ControlChartRules,
) -> str:
    """Format detailed Advanced SPC Session Output.

    The report does not change:
    - SPC calculation results.
    - Control limits.
    - Selected rule profile.
    - Signal locations.
    - Statistical observations.
    """

    if not isinstance(
        assessment,
        ControlChartRules,
    ):
        raise TypeError(
            "Expected ControlChartRules result."
        )

    # =====================================
    # 1. RULE CONFIGURATION
    # =====================================

    profile = assessment.rule_profile

    windows = get_rule_windows(profile)

    profile_label = RULE_PROFILE_LABELS[profile]

    active_tests = tuple(
        assessment.enabled_tests
    )

    tests_text = ", ".join(
        str(test)
        for test in active_tests
    )

    upper = assessment.upper
    lower = assessment.lower

    total_findings = (
        len(upper.result.findings)
        + len(lower.result.findings)
    )

    # =====================================
    # 2. REPORT HEADER
    # =====================================

    lines = [
        f"ADVANCED SPC TESTS — {assessment.chart_name}",
        "=" * 64,

        "",
        "SPC RULE CONFIGURATION",
        "-" * 40,

        f"Rule profile         : {profile_label}",
        f"Profile ID           : {profile}",
        f"Active SPC Tests     : {tests_text}",

        "",
        "RULE DEFINITIONS",
        "-" * 40,

        "Test 1               : One point strictly "
        "outside control limits",

        f"Test 2               : {windows[2]} consecutive "
        "points on the same side of CL",

        f"Test 3               : {windows[3]} consecutive "
        "points strictly increasing/decreasing",

        f"Test 4               : {windows[4]} consecutive "
        "points strictly alternating",

        "",
        "STATISTICAL METHOD",
        "-" * 40,

        "Control limits       : Inherited from "
        "the original Phase I engine",

        "Signal numbering     : Original observation "
        "or subgroup number",

        "Signal position      : Last point "
        "of the qualifying window",

        "Numerical formatting : Shared SPC formatter",

        "",
        "OVERALL SIGNAL SUMMARY",
        "-" * 40,

        f"Upper panel          : {upper.name}",
        f"Upper findings       : {len(upper.result.findings)}",

        f"Lower panel          : {lower.name}",
        f"Lower findings       : {len(lower.result.findings)}",

        f"Total findings       : {total_findings}",
    ]

    # =====================================
    # 3. UPPER PANEL
    # =====================================

    lines.extend(
        _format_panel_report(
            upper,
            active_tests,
            windows,
        )
    )

    # =====================================
    # 4. LOWER PANEL
    # =====================================

    lines.extend(
        _format_panel_report(
            lower,
            active_tests,
            windows,
        )
    )

    # =====================================
    # 5. INTERPRETATION
    # =====================================

    lines.extend([
        "",
        "INTERPRETATION NOTES",
        "-" * 40,

        "- Test 1 detects points strictly "
        "outside the control limits.",

        "- Test 2 requires consecutive points "
        "strictly on the same side of CL.",

        "- A point exactly on CL interrupts "
        "the Test 2 run.",

        "- Tests 3 and 4 detect time-ordered "
        "patterns, not specification failures.",

        "- BELUM CUKUP DATA means the number "
        "of plotted points is smaller than "
        "the required test window.",

        "- No signals means the selected test "
        "was evaluated without detecting "
        "a qualifying pattern.",

        "- SPC signal numbers indicate the "
        "last point of a qualifying window.",

        "- Moving Range signals use original "
        "observation numbering.",

        "- Additional SPC Tests may increase "
        "the frequency of false signals.",

        "- Historical Phase I control limits "
        "should be evaluated for process "
        "stability before reuse.",

        "- No detected signal does not prove "
        "that the process is statistically stable.",

        "- Statistical control limits are not "
        "product specification limits.",

        "- SPC results describe process behavior "
        "and do not represent QA approval.",

        "- Display formatting does not change "
        "statistical calculations.",
    ])

    # =====================================
    # 6. EXPERIMENTAL PROFILE WARNING
    # =====================================

    if profile != RULE_PROFILE_STANDARD:

        lines.extend([
            "",
            "EXPERIMENTAL RULE PROFILE",
            "-" * 40,

            "The selected 7/15 profile is "
            "experimental and has not been "
            "verified as equivalent to all "
            "Minitab configurations.",
        ])

    # =====================================
    # 7. END REPORT
    # =====================================

    lines.extend([
        "",
        "STATDESK REPORT INFORMATION",
        "-" * 40,

        "Analysis             : Advanced SPC Tests 1-4",
        f"Chart                : {assessment.chart_name}",
        "Control limits       : Unchanged",
        "Signal calculation   : Existing SPC rules engine",

        "",
        "END OF ADVANCED SPC REPORT",
    ])

    return "\n".join(lines)
