
"""StatDesk — Phase I I-MR Statistical Engine.

Methods:
- Time-ordered individual observations
- Moving Range span 2
- Within sigma estimated by MRbar / d2
- Shewhart three-sigma control limits
- Test 1: points strictly outside control limits

Session Output:
- Shared SPC number formatter
- Fixed three decimals for ordinary values
- Scientific notation for extreme values
- Full numerical precision during calculations

No GUI or visualization dependencies.
"""

from dataclasses import dataclass
from math import fsum, isfinite
from numbers import Real

from statdesk.statistics.spc_number_format import (
    format_spc_number,
)


# ======================================================
# 1. ENGINE CONFIGURATION
# ======================================================

SPC_ENGINE_VERSION = "0.6.0"

D2 = 1.128
D3 = 0.0
D4 = 3.267

MIN_N = 3
RECOMMENDED_N = 100


# ======================================================
# 2. EXCEPTION
# ======================================================

class SpcError(ValueError):
    """Input or numerical error preventing a valid I-MR result."""


# ======================================================
# 3. IMMUTABLE RESULT CONTRACT
# ======================================================

@dataclass(frozen=True)
class ImrResult:

    column_name: str

    values: tuple[float, ...]
    moving_ranges: tuple[float, ...]

    n: int

    i_center: float
    i_ucl: float
    i_lcl: float

    mr_center: float
    mr_ucl: float
    mr_lcl: float

    sigma_within: float

    # Observation numbers start at 1.
    i_violations: tuple[int, ...]

    # MR(i) belongs to observations i-1 and i.
    mr_violations: tuple[int, ...]

    warnings: tuple[str, ...]


# ======================================================
# 4. I-MR STATISTICAL ENGINE
# ======================================================

class SpcEngine:

    @staticmethod
    def calculate_imr(
        values,
        column_name: str
    ) -> ImrResult:

        # =====================================
        # 1. COLUMN VALIDATION
        # =====================================

        if (
            not isinstance(column_name, str)
            or not column_name.strip()
        ):
            raise SpcError(
                "Nama kolom Numeric tidak valid."
            )

        try:
            iterator = iter(values)

        except TypeError as exc:
            raise SpcError(
                "Data harus berupa urutan pengukuran."
            ) from exc

        # =====================================
        # 2. MEASUREMENT VALIDATION
        # =====================================

        numbers = []

        for row_number, raw in enumerate(
            iterator,
            start=1
        ):

            if raw is None:
                raise SpcError(
                    f"Baris {row_number} kosong. "
                    "I-MR membutuhkan pengukuran "
                    "berurutan tanpa missing value."
                )

            if (
                isinstance(raw, bool)
                or not isinstance(raw, Real)
            ):
                raise SpcError(
                    f"Baris {row_number}: "
                    "nilai harus Numeric, "
                    "bukan teks/bool."
                )

            try:
                number = float(raw)

            except (
                TypeError,
                ValueError,
                OverflowError
            ) as exc:
                raise SpcError(
                    f"Baris {row_number}: "
                    "nilai tidak dapat dikonversi."
                ) from exc

            if not isfinite(number):
                raise SpcError(
                    f"Baris {row_number}: "
                    "NaN atau Infinity "
                    "tidak diperbolehkan."
                )

            numbers.append(number)

        # =====================================
        # 3. MINIMUM SAMPLE SIZE
        # =====================================

        n = len(numbers)

        if n < MIN_N:
            raise SpcError(
                f"I-MR membutuhkan minimal "
                f"{MIN_N} pengukuran berurutan."
            )

        # =====================================
        # 4. CALCULATE MOVING RANGES
        # =====================================

        try:

            moving_ranges = [
                abs(current - previous)
                for previous, current in zip(
                    numbers,
                    numbers[1:]
                )
            ]

            # =================================
            # 5. MEAN AND MR BAR
            # =================================

            xbar = fsum(numbers) / n

            mrbar = (
                fsum(moving_ranges)
                / (n - 1)
            )

            # =================================
            # 6. WITHIN-SIGMA ESTIMATOR
            # =================================

            sigma_within = mrbar / D2

            # =================================
            # 7. INDIVIDUALS CONTROL LIMITS
            # =================================

            i_ucl = (
                xbar + 3.0 * sigma_within
            )

            i_lcl = (
                xbar - 3.0 * sigma_within
            )

            # =================================
            # 8. MOVING RANGE CONTROL LIMITS
            # =================================

            mr_ucl = D4 * mrbar

            mr_lcl = D3 * mrbar

        except (
            ValueError,
            OverflowError,
            ZeroDivisionError
        ) as exc:
            raise SpcError(
                "Perhitungan melebihi rentang "
                "bilangan floating-point."
            ) from exc

        # =====================================
        # 9. NUMERICAL VALIDATION
        # =====================================

        calculated = (
            xbar,
            mrbar,
            sigma_within,
            i_ucl,
            i_lcl,
            mr_ucl,
            mr_lcl,
            *moving_ranges,
        )

        if not all(
            isfinite(value)
            for value in calculated
        ):
            raise SpcError(
                "Hasil perhitungan tidak finite; "
                "periksa skala pengukuran."
            )

        if mrbar == 0.0:
            raise SpcError(
                "Semua Moving Range bernilai nol; "
                "batas kendali tidak informatif."
            )

        if not (
            i_lcl < xbar < i_ucl
        ):
            raise SpcError(
                "Presisi float tidak cukup "
                "untuk membedakan batas I Chart."
            )

        # =====================================
        # 10. TEST 1 — INDIVIDUALS
        # =====================================

        # Strictly beyond control limits.
        # Equality does not count as a signal.

        i_violations = tuple(
            index
            for index, value in enumerate(
                numbers,
                start=1
            )
            if (
                value < i_lcl
                or value > i_ucl
            )
        )

        # =====================================
        # 11. TEST 1 — MOVING RANGE
        # =====================================

        mr_violations = tuple(
            index
            for index, value in enumerate(
                moving_ranges,
                start=2
            )
            if (
                value < mr_lcl
                or value > mr_ucl
            )
        )

        # =====================================
        # 12. INDUSTRIAL WARNINGS
        # =====================================

        warnings = []

        if n < RECOMMENDED_N:
            warnings.append(
                f"N={n} < {RECOMMENDED_N}: "
                "batas kendali bersifat pendahuluan; "
                "Minitab merekomendasikan "
                ">=100 observasi."
            )

        warnings.extend((
            "Phase I: semua titik, termasuk "
            "titik yang bersinyal, ikut "
            "mengestimasi batas kendali; "
            "investigasi sebelum menetapkan "
            "baseline resmi.",

            "Hanya Test 1 (di luar 3-sigma) "
            "yang diperiksa; tidak membuktikan "
            "proses stabil atau produk "
            "sesuai spesifikasi.",

            "Pastikan data berurutan menurut waktu, "
            "interval sampling sesuai, "
            "dan observasi tidak "
            "berkorelasi kuat.",
        ))

        # =====================================
        # 13. RETURN IMMUTABLE RESULT
        # =====================================

        return ImrResult(
            column_name=column_name.strip(),

            values=tuple(numbers),
            moving_ranges=tuple(
                moving_ranges
            ),

            n=n,

            i_center=xbar,
            i_ucl=i_ucl,
            i_lcl=i_lcl,

            mr_center=mrbar,
            mr_ucl=mr_ucl,
            mr_lcl=mr_lcl,

            sigma_within=sigma_within,

            i_violations=i_violations,
            mr_violations=mr_violations,

            warnings=tuple(warnings),
        )


# ======================================================
# 5. SHARED NUMBER FORMATTER COMPATIBILITY
# ======================================================

# Keep this private alias for backward compatibility
# with any existing internal imports.
#
# The implementation is now centralized in:
# statdesk/statistics/spc_number_format.py
#
# No duplicate formatting logic remains here.

_format_spc_number = format_spc_number


# ======================================================
# 6. TEST 1 SIGNAL FORMATTING
# ======================================================

def _format_test1_signals(signals) -> str:
    """Format original 1-based observation numbers."""

    if not signals:
        return "Tidak ada (Test 1)"

    return ", ".join(
        str(index)
        for index in signals
    )


# ======================================================
# 7. FORMAT I-MR SESSION OUTPUT
# ======================================================

def format_imr_report(
    result: ImrResult
) -> str:
    """Format Phase I I-MR results for Session Output.

    Advanced SPC Tests 2–4 are reported
    separately by spc_rules_bridge.py.

    Uses the shared SPC number formatter.
    Display formatting never changes
    statistical values or signals.
    """

    preliminary = (
        result.n < RECOMMENDED_N
    )

    heading = (
        "I-MR CONTROL CHART — PHASE I"
    )

    if preliminary:
        heading += " (PRELIMINARY)"

    # Shared presentation-only formatter.
    f = format_spc_number

    lines = [
        heading,
        "=" * 56,

        "",

        "DATA INFORMATION",
        "-" * 40,

        f"Column             : {result.column_name}",
        f"Observations       : {result.n}",
        "Moving Range Span  : 2",

        "",

        "STATISTICAL METHOD",
        "-" * 40,

        "Sigma method       : Average MR / d2 (d2 = 1.128)",
        "Control limits     : Shewhart 3-sigma",

        "Base engine signals: Test 1 only "
        "(strictly beyond limits)",

        "Advanced SPC Tests : reported separately "
        "when enabled",

        "Report precision   : 3 decimals / "
        "scientific notation for extreme values",

        "",

        "MOVING RANGE (MR) — REVIEW VARIATION FIRST",
        "-" * 40,

        f"UCL                : {f(result.mr_ucl)}",
        f"CL (MRbar)         : {f(result.mr_center)}",
        f"LCL                : {f(result.mr_lcl)}",

        "Test 1 signals     : "
        + _format_test1_signals(
            result.mr_violations
        ),

        "MR(i) refers to the change between "
        "observations i-1 and i.",

        "",

        "INDIVIDUALS (I) — REVIEW PROCESS LEVEL NEXT",
        "-" * 40,

        f"UCL                : {f(result.i_ucl)}",
        f"CL (mean)          : {f(result.i_center)}",
        f"LCL                : {f(result.i_lcl)}",

        f"Within sigma       : "
        f"{f(result.sigma_within)}",

        "Test 1 signals     : "
        + _format_test1_signals(
            result.i_violations
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

        "- Review the MR Chart before "
        "the Individuals Chart.",

        "- No Test 1 signal does not "
        "prove process stability.",

        "- Control limits are NOT "
        "specification limits.",

        "- Measurement data must be "
        "time ordered.",

        "- Phase I limits require investigation "
        "and QC/QA approval.",

        "- Internal statistical calculations "
        "retain floating-point precision.",

        "- Adaptive formatting affects "
        "display only, not calculations.",

        "",

        f"StatDesk I-MR engine {SPC_ENGINE_VERSION} | "
        "Research/testing only; "
        "not production release criteria",
    ])

    return "\n".join(lines)
