
"""StatDesk — Xbar-R Phase I Session Output Formatter.

Responsibilities:
- Display statistical results from XbarREngine.
- Show subgroup means, ranges, and Test 1 signals.
- Show the constants used for within-sigma estimation.
- Preserve the original calculated control limits.
- Provide statistical interpretation without QA workflows.

Control limits and SPC signals are never recalculated here.
The within-sigma display is derived from the same Rbar/d2
estimator already used by XbarREngine.

Data layout:
    One worksheet row = one rational subgroup.

This module does not create charts or modify worksheet data.
"""

from statdesk.statistics.spc_number_format import (
    format_spc_number,
)

from statdesk.statistics.xbar_r_engine import (
    RANGE_CONSTANTS,
    XbarRResult,
)


# ======================================================
# 1. REPORT CONFIGURATION
# ======================================================

MAX_REPORT_ROWS = 30

REPORT_VERSION = "0.8.0"


# ======================================================
# 2. SIGNAL FORMATTING
# ======================================================

def _signals(indices):
    """Format one-based subgroup signal numbers."""

    if not indices:
        return "Tidak ada"

    return ", ".join(
        str(index)
        for index in indices
    )


# ======================================================
# 3. STATISTICAL WARNINGS
# ======================================================

def _format_warning(message):
    """Keep statistical warnings without approval language.

    Historical warning texts from older engine versions
    are converted to neutral statistical guidance.

    No SPC signals or numerical results are changed.
    """

    old_approval_warning = (
        "Phase I; batas dihitung dari seluruh "
        "subgrup dan perlu disetujui QC/QA."
    )

    if message == old_approval_warning:
        return (
            "Phase I: batas kendali dihitung dari "
            "seluruh subgroup yang tersedia. "
            "Evaluasi kestabilan proses sebelum "
            "menggunakan batas sebagai referensi."
        )

    return str(message)


# ======================================================
# 4. SUBGROUP SUMMARY
# ======================================================

def _format_subgroup_summary(result):
    """Display calculated subgroup means and ranges.

    Values and signals are read directly from the
    statistical engine result.

    Test 1 uses one-based subgroup numbers.
    """

    f = format_spc_number

    mean_signals = set(result.mean_signals)
    range_signals = set(result.range_signals)

    lines = [
        "",
        "SUBGROUP STATISTICS",
        "-" * 56,
        "",
        (
            f"{'No':>4} | "
            f"{'Xbar':>12} | "
            f"{'Range':>12} | "
            f"{'Xbar T1':>7} | "
            f"{'R T1':>5}"
        ),
        "-" * 56,
    ]

    display_count = min(
        result.subgroup_count,
        MAX_REPORT_ROWS,
    )

    for index in range(display_count):
        subgroup_number = index + 1

        mean = result.means[index]
        spread = result.ranges[index]

        xbar_status = (
            "T1"
            if subgroup_number in mean_signals
            else "-"
        )

        range_status = (
            "T1"
            if subgroup_number in range_signals
            else "-"
        )

        lines.append(
            f"{subgroup_number:>4} | "
            f"{f(mean):>12} | "
            f"{f(spread):>12} | "
            f"{xbar_status:>7} | "
            f"{range_status:>5}"
        )

    omitted = result.subgroup_count - display_count

    if omitted > 0:
        lines.extend([
            "",
            f"... {omitted} subgroup rows omitted "
            "from Session Output.",
            "The chart and statistical calculations "
            "still use all subgroups.",
        ])

    lines.extend([
        "",
        "T1 = point strictly outside control limits.",
        "-  = no Test 1 signal.",
    ])

    return lines


# ======================================================
# 5. MAIN XBAR-R SESSION REPORT
# ======================================================

def format_xbar_r_report(
    result,
    measurement_names,
) -> str:
    """Generate Xbar-R Phase I Session Output.

    Parameters
    ----------
    result:
        XbarRResult returned by XbarREngine.calculate().

    measurement_names:
        Names of the selected numeric measurement columns.

    Returns
    -------
    str:
        Complete formatted report.

    This function preserves the existing two-argument
    interface used by MainWindow.
    """

    # ==========================================
    # A. VALIDATE RESULT
    # ==========================================

    if not isinstance(result, XbarRResult):
        raise TypeError(
            "Expected XbarRResult from XbarREngine."
        )

    names = tuple(measurement_names)

    if len(names) != result.subgroup_size:
        raise ValueError(
            "Jumlah nama sampel tidak sesuai "
            "ukuran subgroup."
        )

    if result.subgroup_size not in RANGE_CONSTANTS:
        raise ValueError(
            "Ukuran subgroup Xbar-R tidak didukung."
        )

    if (
        len(result.means) != result.subgroup_count
        or len(result.ranges) != result.subgroup_count
    ):
        raise ValueError(
            "Jumlah hasil subgroup tidak konsisten."
        )

    # ==========================================
    # B. STATISTICAL CONSTANTS
    # ==========================================

    d2, d3 = RANGE_CONSTANTS[
        result.subgroup_size
    ]

    # The same Rbar/d2 estimator used in XbarREngine.
    # This value is for display only.
    # Control limits are NOT recalculated.

    sigma_within = result.r_cl / d2

    f = format_spc_number

    total_measurements = (
        result.subgroup_count
        * result.subgroup_size
    )

    # ==========================================
    # C. REPORT HEADER
    # ==========================================

    lines = [
        "XBAR-R CONTROL CHART — PHASE I",
        "=" * 56,

        "",
        "DATA INFORMATION",
        "-" * 40,

        "Data layout          : One subgroup per row",
        "Measurement columns  : "
        + ", ".join(str(name) for name in names),

        f"Subgroups            : {result.subgroup_count}",
        f"Subgroup size        : {result.subgroup_size}",
        f"Total measurements   : {total_measurements}",

        "",
        "STATISTICAL METHOD",
        "-" * 40,

        "Sigma estimator      : Rbar / d2",
        "Control limit method : Shewhart 3-sigma",
        "Subgroup size        : Constant",
        "Control chart type   : Xbar-R Phase I",

        "",
        "STATISTICAL CONSTANTS",
        "-" * 40,

        f"d2                   : {d2:.4f}",
        f"d3                   : {d3:.4f}",

        "",
        "PROCESS ESTIMATES",
        "-" * 40,

        f"Grand Mean           : {f(result.xbar_cl)}",
        f"Average Range (Rbar) : {f(result.r_cl)}",
        f"Within Sigma         : {f(sigma_within)}",

        "",
        "Within sigma = Rbar / d2",
        "The sigma estimate is based on "
        "within-subgroup variation.",

        "",
        "R CHART — PROCESS VARIATION",
        "-" * 40,

        f"UCL                  : {f(result.r_ucl)}",
        f"CL (Rbar)            : {f(result.r_cl)}",
        f"LCL                  : {f(result.r_lcl)}",

        "Test 1 signals       : "
        + _signals(result.range_signals),

        "",
        "XBAR CHART — PROCESS CENTER",
        "-" * 40,

        f"UCL                  : {f(result.xbar_ucl)}",
        f"CL (Grand Mean)      : {f(result.xbar_cl)}",
        f"LCL                  : {f(result.xbar_lcl)}",

        "Test 1 signals       : "
        + _signals(result.mean_signals),
    ]

    # ==========================================
    # D. SUBGROUP STATISTICS
    # ==========================================

    lines.extend(
        _format_subgroup_summary(result)
    )

    # ==========================================
    # E. ENGINE WARNINGS
    # ==========================================

    if result.warnings:
        lines.extend([
            "",
            "WARNINGS & ASSUMPTIONS",
            "-" * 40,
        ])

        lines.extend(
            "- " + _format_warning(warning)
            for warning in result.warnings
        )

    # ==========================================
    # F. INTERPRETATION
    # ==========================================

    lines.extend([
        "",
        "INTERPRETATION NOTES",
        "-" * 40,

        "- Review the R Chart before "
        "interpreting the Xbar Chart.",

        "- Test 1 identifies observations "
        "strictly beyond control limits.",

        "- No Test 1 signal does not prove "
        "that a process is statistically stable.",

        "- Advanced SPC Tests 2-4 are reported "
        "separately when selected.",

        "- Control limits are not product "
        "specification limits.",

        "- Measurements within a subgroup "
        "should represent comparable process "
        "conditions.",

        "- Subgroups must be ordered by time.",

        "- Published d2/d3 constants are "
        "rounded approximations.",

        "- Different statistical software "
        "settings may produce different "
        "control limit estimates.",

        "- Internal calculations retain "
        "floating-point precision; display "
        "values are rounded.",

        "",
        "STATDESK REPORT INFORMATION",
        "-" * 40,

        f"Report version       : {REPORT_VERSION}",
        "Statistical engine   : XbarREngine",
        "Analysis             : Xbar-R Phase I",
        "Control limits       : Calculated by engine",

        "",
        "END OF XBAR-R REPORT",
    ])

    return "\n".join(lines)
