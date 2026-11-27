
"""StatDesk R4.9.5 — Sixpack SPC Phase I Session Output.

Presentation only: obtains control limits and Test 1 signals directly
from the same I-MR, Xbar-R, and Xbar-S engines used by Sixpack.
Capability metrics and Anderson-Darling are reported separately.
"""

from math import isfinite

from statdesk.statistics.capability_engine import CapabilityResult
from statdesk.statistics.spc_engine import SpcEngine
from statdesk.statistics.spc_number_format import format_spc_number
from statdesk.statistics.xbar_r_engine import XbarREngine
from statdesk.statistics.xbar_s_engine import XbarSEngine


class CapabilitySixpackReportError(ValueError):
    """Invalid or unsupported Sixpack report input."""


def _fmt(value):
    if not isfinite(value):
        raise CapabilitySixpackReportError(
            "SPC control limit tidak finite."
        )
    return format_spc_number(value)


def _signal_text(indices):
    return ", ".join(str(i) for i in indices) if indices else "Tidak ada"


def _chart_section(title, lcl, center, ucl, signals):
    return [
        title,
        "-" * 43,
        f"UCL                 : {_fmt(ucl)}",
        f"CL                  : {_fmt(center)}",
        f"LCL                 : {_fmt(lcl)}",
        f"Test 1 Signals      : {_signal_text(signals)}",
        "",
    ]


def format_sixpack_spc_report(result: CapabilityResult) -> str:
    """Format the Sixpack SPC Phase I summary.

    Individuals => I-MR
    Subgroup size 2–8 => Xbar-R
    Subgroup size 9–25 => Xbar-S

    Signals and limits come from existing SPC engines.
    """
    if not isinstance(result, CapabilityResult):
        raise CapabilitySixpackReportError(
            "Laporan Sixpack membutuhkan CapabilityResult."
        )

    n = result.subgroup_size

    if (
        result.n != len(result.values)
        or result.n < 3
        or result.subgroup_count < 2
        or not 1 <= n <= 25
        or result.subgroup_count * n != result.n
    ):
        raise CapabilitySixpackReportError(
            "Jumlah pengukuran/subgroup Sixpack tidak konsisten."
        )

    try:
        values = tuple(float(value) for value in result.values)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CapabilitySixpackReportError(
            "Pengukuran bukan angka valid."
        ) from exc

    if not all(isfinite(v) for v in values):
        raise CapabilitySixpackReportError(
            "Pengukuran harus finite."
        )

    if result.layout == "individuals" and n == 1:

        spc = SpcEngine.calculate_imr(
            values,
            result.column_name,
        )

        chart_pair = "I-MR"

        chart_center = (
            "INDIVIDUALS CHART — PROCESS CENTER",
            spc.i_lcl,
            spc.i_center,
            spc.i_ucl,
            spc.i_violations,
        )

        chart_variation = (
            "MOVING RANGE CHART — PROCESS VARIATION",
            spc.mr_lcl,
            spc.mr_center,
            spc.mr_ucl,
            spc.mr_violations,
        )

        sigma_estimator = "MRbar / d2(2)"
        index_text = "Observation; MR indexed by later observation"

    elif result.layout == "subgroups" and n >= 2:

        groups = tuple(
            values[offset:offset + n]
            for offset in range(0, result.n, n)
        )

        index_text = "Subgroup (time order)"

        if n <= 8:

            spc = XbarREngine.calculate(groups)
            chart_pair = "Xbar-R"

            chart_center = (
                "XBAR CHART — PROCESS CENTER",
                spc.xbar_lcl,
                spc.xbar_cl,
                spc.xbar_ucl,
                spc.mean_signals,
            )

            chart_variation = (
                "R CHART — PROCESS VARIATION",
                spc.r_lcl,
                spc.r_cl,
                spc.r_ucl,
                spc.range_signals,
            )

            sigma_estimator = "Rbar / d2(n)"

        else:

            spc = XbarSEngine.calculate(groups)
            chart_pair = "Xbar-S"

            chart_center = (
                "XBAR CHART — PROCESS CENTER",
                spc.xbar_lcl,
                spc.xbar_center,
                spc.xbar_ucl,
                spc.xbar_signals,
            )

            chart_variation = (
                "S CHART — PROCESS VARIATION",
                spc.s_lcl,
                spc.s_center,
                spc.s_ucl,
                spc.s_signals,
            )

            sigma_estimator = "Sbar / c4(n)"

    else:
        raise CapabilitySixpackReportError(
            "Data layout dan subgroup size Sixpack tidak cocok."
        )

    has_signal = bool(
        chart_center[4] or chart_variation[4]
    )

    lines = [
        "SPC STABILITY SUMMARY — PHASE I",
        "=" * 58,
        "",
        "CHART INFORMATION",
        "-" * 43,
        f"Control chart pair  : {chart_pair}",
        f"Subgroups           : {result.subgroup_count}",
        f"Subgroup size       : {n}",
        f"Index convention    : {index_text}",
        "Limit method        : Phase I Shewhart 3-sigma",
        f"SPC sigma method    : {sigma_estimator}",
        "SPC tests           : Test 1 only (strictly outside limits)",
        "",
    ]

    lines.extend(_chart_section(*chart_center))
    lines.extend(_chart_section(*chart_variation))

    lines.extend([
        "STABILITY INTERPRETATION",
        "-" * 43,
    ])

    if has_signal:
        lines.extend([
            "Result              : SPECIAL-CAUSE SIGNAL DETECTED",
            "- Minimal satu titik berada di luar 3-sigma control limits.",
            "- Evaluasi sinyal sebelum menyimpulkan kestabilan proses.",
        ])
    else:
        lines.extend([
            "Result              : No Test 1 signals detected",
            "- Tidak ada Test 1 signal bukan bukti proses stabil.",
            "- Tests 2–4 tidak dievaluasi pada Sixpack ini.",
        ])

    lines.extend([
        "- Control limits berbeda dari specification limits (LSL/USL).",
        "- SPC dan Capability Within Sigma dapat menggunakan estimator",
        "  yang berbeda sesuai metode yang dipilih.",
        "- Interpretasikan capability setelah menilai kestabilan proses",
        "  dan kesesuaian asumsi distribusi.",
        "",
        "END OF SPC STABILITY SUMMARY",
    ])

    return "\n".join(lines)
