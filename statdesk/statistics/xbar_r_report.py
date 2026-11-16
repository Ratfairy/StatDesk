
"""StatDesk — Xbar-R Session Output Formatter.

Responsibilities:
- Present Phase I Xbar-R results.
- Use the shared SPC number formatter.
- Display Test 1 signals.
- Describe statistical assumptions and warnings.

This module performs no statistical calculations.

All control limits and signals originate
from XbarREngine.
"""

from statdesk.statistics.spc_number_format import (
    format_spc_number,
)


# ======================================================
# 1. SIGNAL FORMATTING
# ======================================================

def _signals(indices):
    """Format 1-based subgroup signal indexes."""

    if not indices:
        return "Tidak ada"

    return ", ".join(
        str(index)
        for index in indices
    )


# ======================================================
# 2. XBAR-R SESSION REPORT
# ======================================================

def format_xbar_r_report(
    result,
    measurement_names,
) -> str:
    """Create a read-only Phase I Xbar-R report.

    Keeps the original two-argument interface.

    Uses numerical results produced by
    XbarREngine.calculate().
    """

    names = tuple(measurement_names)

    if len(names) != result.subgroup_size:
        raise ValueError(
            "Jumlah nama sampel tidak sesuai "
            "ukuran subgrup."
        )

    f = format_spc_number

    output = [
        "XBAR-R CONTROL CHART — PHASE I",
        "=" * 56,

        "",

        "DATA INFORMATION",
        "-" * 40,

        "Data layout        : one subgroup per row",

        "Measurement columns: "
        + ", ".join(names),

        f"Subgroups          : {result.subgroup_count}",
        f"Subgroup size      : {result.subgroup_size}",

        "Total measurements : "
        f"{result.subgroup_count * result.subgroup_size}",

        "",

        "STATISTICAL METHOD",
        "-" * 40,

        "Sigma method       : Rbar / d2",
        "Control limits     : Shewhart 3-sigma",

        "Constants          : published d2/d3 values",

        "Factor calculation : derived A2/D3/D4 "
        "without rounding the derived factors",

        "Numerical precision: full precision internally; "
        "adaptive formatting for display",

        "Base engine signals: Test 1 only",

        "Advanced SPC Tests : reported separately "
        "when enabled",

        "",

        "R CHART — REVIEW PROCESS VARIATION FIRST",
        "-" * 40,

        f"CL (Rbar)          : {f(result.r_cl)}",
        f"UCL                : {f(result.r_ucl)}",
        f"LCL                : {f(result.r_lcl)}",

        "Test 1 signals     : "
        + _signals(result.range_signals),

        "",

        "XBAR CHART — REVIEW SUBGROUP MEANS NEXT",
        "-" * 40,

        f"CL (grand mean)    : {f(result.xbar_cl)}",
        f"UCL                : {f(result.xbar_ucl)}",
        f"LCL                : {f(result.xbar_lcl)}",

        "Test 1 signals     : "
        + _signals(result.mean_signals),

        "",

        "WARNINGS & ASSUMPTIONS",
        "-" * 40,
    ]

    output.extend(
        f"- {warning}"
        for warning in result.warnings
    )

    output.extend([
        "",

        "INTERPRETATION NOTES",
        "-" * 40,

        "- Review the R Chart before "
        "the Xbar Chart.",

        "- Absence of Test 1 signals "
        "does not prove process stability.",

        "- Statistical control limits are not "
        "product specification limits.",

        "- Selected columns must contain "
        "rational subgroup measurements.",

        "- Subgroups must be ordered by time.",

        "- Historical Phase I limits require "
        "QC/QA investigation and approval.",

        "- Published d2/d3 constants are "
        "approximations; exact Minitab "
        "internal precision is not guaranteed.",

        "- Adaptive formatting affects "
        "display only, not calculations.",

        "",

        "StatDesk | Xbar-R | Phase I",
    ])

    return "\n".join(output)
