
"""StatDesk — Xbar-S Control Chart Phase I.

R3.17 — Statistical Engine & Session Output Refinement.

Statistical methods:
- Equal rational subgroups, size 9 to 25.
- Sample standard deviation (ddof=1).
- Within sigma = Sbar / c4(n).
- Shewhart 3-sigma control limits.
- Test 1: points strictly outside control limits.
- Advanced SPC Tests 2-4 handled by spc_rules_bridge.py.

R3.17 improvements:
- Clearer Session Output.
- Process estimates.
- Subgroup statistics table.
- Test 1 signal indicators.
- Neutral statistical interpretation.

Statistical calculations remain unchanged.
No GUI or plotting dependencies.
"""

from dataclasses import dataclass
from math import exp, fsum, hypot, isfinite, lgamma, sqrt
from numbers import Real

from statdesk.statistics.spc_number_format import (
    format_spc_number,
)


# ======================================================
# 1. ENGINE CONFIGURATION
# ======================================================

MIN_SIZE = 9
MAX_SIZE = 25

MIN_GROUPS = 2
MAX_GROUPS = 50_000

MIN_TOTAL_OBSERVATIONS = 60
MAX_REPORT_ROWS = 30

ENGINE_VERSION = "0.7.0"
REPORT_VERSION = "0.8.0"


# ======================================================
# 2. EXCEPTION
# ======================================================

class XbarSError(ValueError):
    """Invalid subgroup structure or numerical result."""


# ======================================================
# 3. IMMUTABLE RESULT CONTRACT
# ======================================================

@dataclass(frozen=True)
class XbarSResult:

    subgroup_count: int
    subgroup_size: int

    subgroup_means: tuple[float, ...]
    subgroup_stdevs: tuple[float, ...]

    xbar_center: float
    xbar_ucl: float
    xbar_lcl: float

    s_center: float
    s_ucl: float
    s_lcl: float

    sigma_within: float

    c4: float
    a3: float
    b3: float
    b4: float

    xbar_signals: tuple[int, ...]
    s_signals: tuple[int, ...]

    warnings: tuple[str, ...]


# ======================================================
# 4. C4 UNBIASING CONSTANT
# ======================================================

def _c4(n: int) -> float:
    """Calculate the c4 unbiasing constant.

    c4(n) = sqrt(2 / (n-1))
            * Gamma(n/2) / Gamma((n-1)/2)

    Full numerical precision is retained.
    """

    return sqrt(2.0 / (n - 1)) * exp(
        lgamma(n / 2.0)
        - lgamma((n - 1) / 2.0)
    )


# ======================================================
# 5. STATISTICAL ENGINE
# ======================================================

class XbarSEngine:

    @staticmethod
    def calculate(subgroups) -> XbarSResult:
        """Calculate Phase I Xbar-S statistics.

        One input row represents one rational subgroup.

        The existing statistical formulas and data
        validation behavior are preserved.
        """

        # =====================================
        # 1. VALIDATE SUBGROUP COLLECTION
        # =====================================

        if isinstance(subgroups, (str, bytes)):
            raise XbarSError(
                "Subgrup harus berupa kumpulan "
                "baris pengukuran."
            )

        try:
            groups = list(subgroups)

        except TypeError as exc:
            raise XbarSError(
                "Data subgrup tidak dapat dibaca."
            ) from exc

        m = len(groups)

        if not MIN_GROUPS <= m <= MAX_GROUPS:
            raise XbarSError(
                f"Jumlah subgrup harus "
                f"{MIN_GROUPS}–{MAX_GROUPS}."
            )

        try:
            first = list(groups[0])

        except TypeError as exc:
            raise XbarSError(
                "Setiap subgrup harus berupa "
                "deretan nilai."
            ) from exc

        n = len(first)

        if not MIN_SIZE <= n <= MAX_SIZE:
            raise XbarSError(
                "Xbar-S tahap ini mendukung "
                f"{MIN_SIZE}–{MAX_SIZE} pengukuran "
                "per subgrup."
            )

        means = []
        stdevs = []

        # =====================================
        # 2. VALIDATE SUBGROUP VALUES
        # =====================================

        for i, group in enumerate(
            groups,
            start=1
        ):

            if isinstance(group, (str, bytes)):
                raise XbarSError(
                    f"Subgrup {i} harus berupa "
                    "deretan angka."
                )

            try:
                row = list(group)

            except TypeError as exc:
                raise XbarSError(
                    f"Subgrup {i} tidak dapat dibaca."
                ) from exc

            if len(row) != n:
                raise XbarSError(
                    f"Subgrup {i} memiliki "
                    f"{len(row)} pengukuran; "
                    f"harus tepat {n}."
                )

            observations = []

            for j, raw in enumerate(
                row,
                start=1
            ):

                if raw is None:
                    raise XbarSError(
                        f"Subgrup {i}, sampel {j}: "
                        "nilai kosong."
                    )

                if (
                    isinstance(raw, bool)
                    or not isinstance(raw, Real)
                ):
                    raise XbarSError(
                        f"Subgrup {i}, sampel {j}: "
                        "wajib angka Numeric."
                    )

                try:
                    value = float(raw)

                except (
                    TypeError,
                    ValueError,
                    OverflowError
                ) as exc:
                    raise XbarSError(
                        f"Subgrup {i}, sampel {j}: "
                        "konversi angka gagal."
                    ) from exc

                if not isfinite(value):
                    raise XbarSError(
                        f"Subgrup {i}, sampel {j}: "
                        "NaN/Infinity ditolak."
                    )

                observations.append(value)

            # =================================
            # 3. SUBGROUP MEAN AND SAMPLE SD
            # =================================

            try:
                avg = fsum(observations) / n

                # Sample standard deviation:
                # denominator = n-1.

                s = hypot(
                    *(v - avg for v in observations)
                ) / sqrt(n - 1)

            except (
                ValueError,
                OverflowError
            ) as exc:
                raise XbarSError(
                    f"Subgrup {i}: perhitungan "
                    "tidak valid."
                ) from exc

            if not (
                isfinite(avg)
                and isfinite(s)
            ):
                raise XbarSError(
                    f"Subgrup {i}: hasil non-finite."
                )

            means.append(avg)
            stdevs.append(s)

        # =====================================
        # 4. CONTROL LIMIT CALCULATIONS
        # =====================================

        try:
            grand_mean = fsum(means) / m

            sbar = fsum(stdevs) / m

            # C4 unbiasing constant.
            c4 = _c4(n)

            # Within-process sigma estimate.
            sigma = sbar / c4

            # Xbar chart factor.
            a3 = 3.0 / (
                c4 * sqrt(n)
            )

            # S chart factors.
            variation_factor = (
                3.0
                * sqrt(
                    max(
                        0.0,
                        1.0 - c4 * c4
                    )
                )
                / c4
            )

            b3 = max(
                0.0,
                1.0 - variation_factor
            )

            b4 = 1.0 + variation_factor

            # Xbar control limits.
            xbar_ucl = (
                grand_mean + a3 * sbar
            )

            xbar_lcl = (
                grand_mean - a3 * sbar
            )

            # S control limits.
            s_ucl = b4 * sbar
            s_lcl = b3 * sbar

        except (
            ValueError,
            OverflowError,
            ZeroDivisionError
        ) as exc:
            raise XbarSError(
                "Control limits tidak "
                "dapat dihitung."
            ) from exc

        # =====================================
        # 5. NUMERICAL VALIDATION
        # =====================================

        results = (
            grand_mean,
            sbar,
            c4,
            sigma,
            a3,
            b3,
            b4,
            xbar_ucl,
            xbar_lcl,
            s_ucl,
            s_lcl,
        )

        if not all(
            isfinite(value)
            for value in results
        ):
            raise XbarSError(
                "Hasil control limits non-finite."
            )

        if sbar == 0.0:
            raise XbarSError(
                "Sbar = 0; estimasi variasi "
                "tidak informatif."
            )

        if not (
            xbar_lcl
            < grand_mean
            < xbar_ucl
        ):
            raise XbarSError(
                "Presisi float tidak cukup "
                "untuk Xbar limits."
            )

        if not (
            0.0 <= s_lcl < sbar < s_ucl
        ):
            raise XbarSError(
                "Presisi float tidak cukup "
                "untuk S limits."
            )

        # =====================================
        # 6. TEST 1 SPECIAL-CAUSE SIGNALS
        # =====================================

        # Equality to a control limit is not
        # considered a Test 1 violation.

        xbar_signals = tuple(
            i
            for i, mean in enumerate(
                means,
                start=1
            )
            if (
                mean < xbar_lcl
                or mean > xbar_ucl
            )
        )

        s_signals = tuple(
            i
            for i, value in enumerate(
                stdevs,
                start=1
            )
            if (
                value < s_lcl
                or value > s_ucl
            )
        )

        # =====================================
        # 7. STATISTICAL WARNINGS
        # =====================================

        warnings = []

        if m * n < MIN_TOTAL_OBSERVATIONS:
            warnings.append(
                "PRELIMINARY: hanya "
                f"{m * n} observasi; "
                f"pedoman awal StatDesk menggunakan "
                f"{MIN_TOTAL_OBSERVATIONS} observasi "
                "sebagai batas minimum."
            )

        warnings.extend((
            "Phase I: control limits dihitung dari "
            "seluruh subgroup yang tersedia. "
            "Evaluasi special-cause variation "
            "sebelum menggunakan limits "
            "sebagai referensi historis.",

            "Periksa S Chart terlebih dahulu "
            "sebelum menginterpretasikan "
            "Xbar Chart.",

            "Base engine hanya mengevaluasi "
            "Test 1. Advanced SPC Tests 2-4 "
            "dievaluasi secara terpisah "
            "ketika diaktifkan.",

            "Tidak adanya SPC signal tidak "
            "membuktikan proses telah stabil.",

            "Seluruh subgroup harus rasional, "
            "berurutan berdasarkan waktu, "
            "dan memiliki ukuran yang sama.",
        ))

        # =====================================
        # 8. RETURN IMMUTABLE RESULT
        # =====================================

        return XbarSResult(
            subgroup_count=m,
            subgroup_size=n,

            subgroup_means=tuple(means),
            subgroup_stdevs=tuple(stdevs),

            xbar_center=grand_mean,
            xbar_ucl=xbar_ucl,
            xbar_lcl=xbar_lcl,

            s_center=sbar,
            s_ucl=s_ucl,
            s_lcl=s_lcl,

            sigma_within=sigma,

            c4=c4,
            a3=a3,
            b3=b3,
            b4=b4,

            xbar_signals=xbar_signals,
            s_signals=s_signals,

            warnings=tuple(warnings),
        )


# ======================================================
# 6. TEST 1 SIGNAL FORMATTING
# ======================================================

def _format_test1_signals(indices) -> str:
    """Format original 1-based subgroup numbers."""

    if not indices:
        return "Tidak ada (Test 1)"

    return ", ".join(
        str(index)
        for index in indices
    )


# ======================================================
# 7. R3.17 - SUBGROUP STATISTICS TABLE
# ======================================================

def _format_subgroup_table(
    result: XbarSResult
) -> list[str]:
    """Display subgroup means and sample SD.

    All values and Test 1 signal positions originate
    from the existing statistical engine.

    Control limits are not recalculated here.
    """

    f = format_spc_number

    xbar_signals = set(
        result.xbar_signals
    )

    s_signals = set(
        result.s_signals
    )

    lines = [
        "",
        "SUBGROUP STATISTICS",
        "-" * 62,

        (
            f"{'No':>4} | "
            f"{'Xbar':>12} | "
            f"{'Sample SD':>12} | "
            f"{'Xbar T1':>7} | "
            f"{'S T1':>5}"
        ),

        "-" * 62,
    ]

    total = result.subgroup_count

    shown = min(
        total,
        MAX_REPORT_ROWS,
    )

    for index in range(shown):
        number = index + 1

        mean = result.subgroup_means[index]
        sd = result.subgroup_stdevs[index]

        xbar_status = (
            "T1"
            if number in xbar_signals
            else "-"
        )

        s_status = (
            "T1"
            if number in s_signals
            else "-"
        )

        lines.append(
            f"{number:>4} | "
            f"{f(mean):>12} | "
            f"{f(sd):>12} | "
            f"{xbar_status:>7} | "
            f"{s_status:>5}"
        )

    omitted = total - shown

    if omitted > 0:
        lines.extend([
            "",
            f"... {omitted} subgroup rows omitted "
            "from Session Output.",

            "All subgroups were still used "
            "for statistical calculations.",
        ])

    lines.extend([
        "",
        "Sample SD uses denominator (n-1).",
        "T1 = point strictly beyond control limits.",
        "-  = no Test 1 signal.",
    ])

    return lines


# ======================================================
# 8. R3.17 - FORMAT XBAR-S SESSION REPORT
# ======================================================

def format_xbar_s_report(
    result: XbarSResult
) -> str:
    """Build complete Xbar-S Phase I Session Output.

    Statistical estimates and SPC Test 1 signals are
    read directly from the original engine result.

    Advanced SPC Tests 2-4 are reported separately
    by spc_rules_bridge.py when enabled.
    """

    # =====================================
    # 1. VALIDATE RESULT
    # =====================================

    if not isinstance(result, XbarSResult):
        raise TypeError(
            "Expected XbarSResult from XbarSEngine."
        )

    if (
        len(result.subgroup_means)
        != result.subgroup_count
        or len(result.subgroup_stdevs)
        != result.subgroup_count
    ):
        raise ValueError(
            "Jumlah statistik subgroup "
            "tidak konsisten."
        )

    f = format_spc_number

    total_measurements = (
        result.subgroup_count
        * result.subgroup_size
    )

    preliminary = (
        total_measurements
        < MIN_TOTAL_OBSERVATIONS
    )

    heading = (
        "XBAR-S CONTROL CHART — PHASE I"
    )

    if preliminary:
        heading += " (PRELIMINARY)"

    # =====================================
    # 2. REPORT HEADER
    # =====================================

    lines = [
        heading,
        "=" * 62,

        "",
        "DATA INFORMATION",
        "-" * 40,

        f"Subgroups           : {result.subgroup_count}",
        f"Subgroup size       : {result.subgroup_size}",
        f"Total measurements  : {total_measurements}",
        "Data layout         : One subgroup per row",

        "",
        "STATISTICAL METHOD",
        "-" * 40,

        "Within sigma method : Sbar / c4(n)",
        "Standard deviation  : Sample SD (n-1)",
        "Control limits      : Shewhart 3-sigma",
        "Base engine signals : SPC Test 1",

        "Advanced SPC Tests  : Reported separately "
        "when enabled",

        "",
        "STATISTICAL CONSTANTS",
        "-" * 40,

        f"c4(n)               : {f(result.c4)}",
        f"A3                  : {f(result.a3)}",
        f"B3                  : {f(result.b3)}",
        f"B4                  : {f(result.b4)}",

        "",
        "PROCESS ESTIMATES",
        "-" * 40,

        f"Grand Mean          : {f(result.xbar_center)}",
        f"Average SD (Sbar)   : {f(result.s_center)}",
        f"Within Sigma        : {f(result.sigma_within)}",

        "",
        "Within Sigma = Sbar / c4(n)",

        "",
        "S CHART — PROCESS VARIATION",
        "-" * 40,

        f"UCL                 : {f(result.s_ucl)}",
        f"CL (Sbar)           : {f(result.s_center)}",
        f"LCL                 : {f(result.s_lcl)}",

        "Test 1 signals      : "
        + _format_test1_signals(
            result.s_signals
        ),

        "",
        "XBAR CHART — PROCESS CENTER",
        "-" * 40,

        f"UCL                 : {f(result.xbar_ucl)}",
        f"CL (Grand Mean)     : {f(result.xbar_center)}",
        f"LCL                 : {f(result.xbar_lcl)}",

        "Test 1 signals      : "
        + _format_test1_signals(
            result.xbar_signals
        ),
    ]

    # =====================================
    # 3. SUBGROUP STATISTICS
    # =====================================

    lines.extend(
        _format_subgroup_table(result)
    )

    # =====================================
    # 4. STATISTICAL WARNINGS
    # =====================================

    if result.warnings:
        lines.extend([
            "",
            "WARNINGS & ASSUMPTIONS",
            "-" * 40,
        ])

        lines.extend(
            f"- {warning}"
            for warning in result.warnings
        )

    # =====================================
    # 5. INTERPRETATION NOTES
    # =====================================

    lines.extend([
        "",
        "INTERPRETATION NOTES",
        "-" * 40,

        "- Review the S Chart before "
        "interpreting the Xbar Chart.",

        "- Xbar and S control limits are "
        "calculated from all Phase I subgroups.",

        "- SPC Test 1 detects points strictly "
        "outside the control limits.",

        "- No detected signal does not prove "
        "process stability.",

        "- Rational subgroups should represent "
        "comparable process conditions.",

        "- Subgroups must be ordered by time.",

        "- Control limits are not product "
        "specification limits.",

        "- Numerical calculations retain "
        "floating-point precision.",

        "- Displayed statistical values "
        "are rounded.",

        "- Results should be compared with "
        "reference statistical software "
        "using the same calculation method.",

        "",
        "STATDESK REPORT INFORMATION",
        "-" * 40,

        f"Report version      : {REPORT_VERSION}",
        f"Statistical engine  : {ENGINE_VERSION}",
        "Analysis            : Xbar-S Phase I",
        "Sigma estimator     : Sbar / c4(n)",
        "Control limits      : Calculated by engine",

        "",
        "END OF XBAR-S REPORT",
    ])

    return "\n".join(lines)
