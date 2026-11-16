
"""StatDesk Xbar-S Control Chart — Phase I.

Equal rational subgroups, size 9..25.

Statistical method:
- Subgroup means
- Sample standard deviation (ddof=1)
- Sbar / c4 within-sigma estimator
- Shewhart three-sigma control limits
- Test 1 special-cause detection

Display formatting:
- Shared SPC number formatter
- Three decimal places for ordinary values
- Scientific notation for extreme values
- Full numerical precision during calculations

Advanced SPC Tests 2-4 are handled separately by
spc_rules_bridge.py.

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

ENGINE_VERSION = "0.7.0"


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
    """Calculate c4(n) using the gamma function ratio.

    c4(n) = sqrt(2 / (n-1))
            * Gamma(n/2) / Gamma((n-1)/2)

    Do not round the result.
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

                # Sample standard deviation
                # uses denominator n-1.

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

            # c4 unbiasing constant.
            c4 = _c4(n)

            # Estimate within-process sigma.
            sigma = sbar / c4

            # Xbar Chart factor.
            a3 = 3.0 / (
                c4 * sqrt(n)
            )

            # S Chart factors.
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

        # Points exactly on limits are not
        # counted as Test 1 violations.

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
                f"minimal {MIN_TOTAL_OBSERVATIONS} "
                "direkomendasikan."
            )

        warnings.extend((
            "Phase I: limits dihitung dari semua "
            "subgrup; investigasi special cause "
            "sebelum menyetujui baseline.",

            "Periksa S Chart lebih dahulu "
            "sebelum menginterpretasikan "
            "Xbar Chart.",

            "Hanya Test 1 (di luar batas "
            "3-sigma); tidak membuktikan "
            "stabilitas.",

            "Semua subgrup harus rasional, "
            "berurutan waktu, dan "
            "berukuran sama.",
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
    """Format original 1-based subgroup indexes."""

    if not indices:
        return "Tidak ada (Test 1)"

    return ", ".join(
        str(index)
        for index in indices
    )


# ======================================================
# 7. FORMAT XBAR-S SESSION REPORT
# ======================================================

def format_xbar_s_report(
    result: XbarSResult
) -> str:
    """Build Xbar-S Phase I Session Output.

    Statistical results come from XbarSEngine.

    All displayed statistical values use the
    shared SPC number formatter.

    Advanced SPC Tests 2-4 are reported
    separately by spc_rules_bridge.

    Display formatting does not alter
    statistical calculations.
    """

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

    f = format_spc_number

    lines = [
        heading,
        "=" * 56,

        "",

        "DATA INFORMATION",
        "-" * 40,

        f"Subgroups          : "
        f"{result.subgroup_count}",

        f"Subgroup size      : "
        f"{result.subgroup_size}",

        f"Total measurements : "
        f"{total_measurements}",

        "Data layout        : "
        "one subgroup per row",

        "",

        "STATISTICAL METHOD",
        "-" * 40,

        "Sigma method       : Sbar / c4(n)",

        "Standard deviation : "
        "sample SD (n-1)",

        "Control limits     : "
        "Shewhart 3-sigma",

        "Base engine signals: Test 1 only",

        "Advanced SPC Tests : reported "
        "separately when enabled",

        "Report precision   : 3 decimals / "
        "scientific notation for extreme values",

        "",

        "STATISTICAL CONSTANTS",
        "-" * 40,

        f"c4(n)              : {f(result.c4)}",
        f"A3                 : {f(result.a3)}",
        f"B3                 : {f(result.b3)}",
        f"B4                 : {f(result.b4)}",

        "Constants note     : values above "
        "are display-rounded; calculations "
        "use full precision",

        "",

        "S CHART — REVIEW VARIATION FIRST",
        "-" * 40,

        f"UCL                : {f(result.s_ucl)}",
        f"CL (Sbar)          : {f(result.s_center)}",
        f"LCL                : {f(result.s_lcl)}",

        "Test 1 signals     : "
        + _format_test1_signals(
            result.s_signals
        ),

        "",

        "XBAR CHART — REVIEW SUBGROUP MEANS NEXT",
        "-" * 40,

        f"UCL                : {f(result.xbar_ucl)}",
        f"CL (grand mean)    : {f(result.xbar_center)}",
        f"LCL                : {f(result.xbar_lcl)}",

        f"Within sigma       : {f(result.sigma_within)}",

        "Test 1 signals     : "
        + _format_test1_signals(
            result.xbar_signals
        ),

        "",

        "WARNINGS & ASSUMPTIONS",
        "-" * 40,
    ]

    lines.extend(
        f"- {warning}"
        for warning in result.warnings
    )

    lines.extend([
        "",

        "INTERPRETATION NOTES",
        "-" * 40,

        "- Review the S Chart before "
        "the Xbar Chart.",

        "- Absence of Test 1 signals "
        "does not prove process stability.",

        "- Control limits are not "
        "product specification limits.",

        "- All subgroup measurements must "
        "be ordered and collected as "
        "rational subgroups.",

        "- Phase I control limits require "
        "QC/QA investigation and approval.",

        "- Internal statistical calculations "
        "retain full floating-point precision.",

        "- Adaptive formatting affects "
        "display only, not calculations.",

        "- Observed agreement with reference "
        "software does not establish "
        "full standards compliance.",

        "",

        f"StatDesk Xbar-S engine "
        f"{ENGINE_VERSION} | "
        "Research/testing only; "
        "QC/QA sign-off required",
    ])

    return "\n".join(lines)
