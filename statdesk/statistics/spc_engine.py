
"""StatDesk — Phase I I-MR Statistical Engine and Session Output.

R3.14 enhances report presentation only. Statistical calculations,
control limits, and Test 1 detection use the established I-MR engine.

Methods:
- Time-ordered individual observations
- Moving ranges of two consecutive observations
- Within sigma = MRbar / d2, d2 = 1.128
- Shewhart 3-sigma I limits and D3/D4 moving-range limits
- Test 1: strictly beyond the control limits

No GUI, plotting, authentication, or QA approval workflow.
"""

from dataclasses import dataclass
from math import fsum, isfinite
from numbers import Real

from statdesk.statistics.spc_number_format import (
    format_spc_number,
)


# ======================================================
# 1. CONFIGURATION
# ======================================================

SPC_ENGINE_VERSION = "0.6.0"
IMR_REPORT_VERSION = "0.8.0"

D2 = 1.128
D3 = 0.0
D4 = 3.267

MIN_N = 3
RECOMMENDED_N = 100
MAX_REPORT_ROWS = 30


# ======================================================
# 2. ERRORS AND RESULT CONTRACT
# ======================================================

class SpcError(ValueError):
    """Invalid I-MR input or numerical result."""


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

    # Individual positions are 1-based.
    i_violations: tuple[int, ...]

    # MR(i) belongs to the later observation i.
    mr_violations: tuple[int, ...]

    warnings: tuple[str, ...]


# ======================================================
# 3. STATISTICAL ENGINE (UNCHANGED METHOD)
# ======================================================

class SpcEngine:

    @staticmethod
    def calculate_imr(values, column_name: str) -> ImrResult:
        """Calculate Phase I I-MR with moving-range span 2."""

        # =====================================
        # 1. VALIDATE COLUMN
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
        # 2. VALIDATE MEASUREMENTS
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
        # 3. SAMPLE SIZE
        # =====================================

        n = len(numbers)

        if n < MIN_N:
            raise SpcError(
                f"I-MR membutuhkan minimal "
                f"{MIN_N} pengukuran berurutan."
            )

        # =====================================
        # 4. STATISTICAL CALCULATIONS
        # =====================================

        try:
            moving_ranges = [
                abs(current - previous)
                for previous, current in zip(
                    numbers,
                    numbers[1:]
                )
            ]

            # Individuals mean
            xbar = fsum(numbers) / n

            # Average moving range
            mrbar = (
                fsum(moving_ranges)
                / (n - 1)
            )

            # Within-process sigma
            sigma_within = mrbar / D2

            # Individuals control limits
            i_ucl = xbar + 3.0 * sigma_within
            i_lcl = xbar - 3.0 * sigma_within

            # Moving Range control limits
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
        # 5. NUMERICAL VALIDATION
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

        if not i_lcl < xbar < i_ucl:
            raise SpcError(
                "Presisi float tidak cukup "
                "untuk membedakan batas I Chart."
            )

        # =====================================
        # 6. TEST 1 - INDIVIDUALS
        # =====================================

        # Equality to limits is NOT a signal.
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
        # 7. TEST 1 - MOVING RANGE
        # =====================================

        # The first MR corresponds to observation 2.
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
        # 8. STATISTICAL WARNINGS
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
            "periksa pola sebelum menggunakan "
            "batas sebagai referensi.",

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
        # 9. RETURN RESULT
        # =====================================

        return ImrResult(
            column_name=column_name.strip(),

            values=tuple(numbers),
            moving_ranges=tuple(moving_ranges),
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
# 4. BACKWARD-COMPATIBLE FORMATTER
# ======================================================

_format_spc_number = format_spc_number


def _format_test1_signals(signals) -> str:
    """Format original 1-based observation numbers."""

    if not signals:
        return "Tidak ada (Test 1)"

    return ", ".join(
        str(index)
        for index in signals
    )


# ======================================================
# 5. R3.14 - OBSERVATION TABLE
# ======================================================

def _format_observation_table(
    result: ImrResult
) -> list[str]:
    """Show individuals, moving ranges, and Test 1 signals.

    The first moving range is undefined.
    MR(i) belongs to observation i, starting at i=2.

    All values and signals are obtained from the
    original statistical engine result.
    """

    f = format_spc_number

    i_signals = set(
        result.i_violations
    )

    mr_signals = set(
        result.mr_violations
    )

    lines = [
        "",
        "OBSERVATION STATISTICS",
        "-" * 64,

        (
            f"{'No':>4} | "
            f"{'Individual':>12} | "
            f"{'MR(2)':>12} | "
            f"{'I T1':>6} | "
            f"{'MR T1':>6}"
        ),

        "-" * 64,
    ]

    shown = min(
        result.n,
        MAX_REPORT_ROWS,
    )

    for pos in range(1, shown + 1):
        individual = f(
            result.values[pos - 1]
        )

        # MR is undefined for observation 1.
        mr_text = (
            "N/A"
            if pos == 1
            else f(
                result.moving_ranges[pos - 2]
            )
        )

        i_tag = (
            "T1"
            if pos in i_signals
            else "-"
        )

        mr_tag = (
            "T1"
            if pos in mr_signals
            else "-"
        )

        lines.append(
            f"{pos:>4} | "
            f"{individual:>12} | "
            f"{mr_text:>12} | "
            f"{i_tag:>6} | "
            f"{mr_tag:>6}"
        )

    # =====================================
    # REPORT ROW LIMIT
    # =====================================

    if shown < result.n:
        omitted = (
            result.n - shown
        )

        lines.extend([
            "",
            f"... {omitted} observations omitted "
            "from Session Output.",

            "All observations were still used "
            "in calculations and Test 1 evaluation.",
        ])

    lines.extend([
        "",

        "MR(i) = |Individual(i) - Individual(i-1)|, "
        "for i >= 2.",

        "N/A = moving range is undefined "
        "at observation 1.",

        "T1 = strictly beyond the "
        "corresponding control limits.",

        "- = no Test 1 signal "
        "at that observation.",
    ])

    return lines


# ======================================================
# 6. R3.14 - I-MR SESSION OUTPUT
# ======================================================

def format_imr_report(
    result: ImrResult
) -> str:
    """Format full I-MR Phase I Session Output.

    Statistical results and Test 1 signals originate
    from the existing engine.

    Advanced SPC Tests 2-4 are reported separately
    by spc_rules_bridge.py when enabled.

    This function does not modify statistical values.
    """

    # =====================================
    # 1. VALIDATE RESULT
    # =====================================

    if not isinstance(result, ImrResult):
        raise TypeError(
            "Expected ImrResult from SpcEngine."
        )

    if (
        len(result.values) != result.n
        or len(result.moving_ranges) != result.n - 1
    ):
        raise ValueError(
            "Panjang data I-MR tidak konsisten."
        )

    f = format_spc_number

    preliminary = (
        result.n < RECOMMENDED_N
    )

    heading = (
        "I-MR CONTROL CHART — PHASE I"
    )

    if preliminary:
        heading += " (PRELIMINARY)"

    # =====================================
    # 2. REPORT HEADER
    # =====================================

    lines = [
        heading,
        "=" * 64,

        "",
        "DATA INFORMATION",
        "-" * 40,

        f"Column              : {result.column_name}",
        f"Observations        : {result.n}",
        f"Moving ranges       : {result.n - 1}",
        "Moving Range Span   : 2",

        "",
        "STATISTICAL METHOD",
        "-" * 40,

        "Within sigma method : MRbar / d2",
        "Control limits      : Shewhart 3-sigma",
        "Test 1              : Point strictly beyond limits",

        "Advanced SPC Tests  : "
        "Reported separately if enabled",

        "",
        "STATISTICAL CONSTANTS",
        "-" * 40,

        f"d2                  : {D2:.4f}",
        f"D3                  : {D3:.4f}",
        f"D4                  : {D4:.4f}",

        "",
        "PROCESS ESTIMATES",
        "-" * 40,

        f"Individuals Mean    : {f(result.i_center)}",
        f"Average MR (MRbar)  : {f(result.mr_center)}",
        f"Within Sigma        : {f(result.sigma_within)}",

        "Within sigma = Average MR / d2",

        "",
        "MOVING RANGE (MR) CHART",
        "-" * 40,

        f"UCL                 : {f(result.mr_ucl)}",
        f"CL (MRbar)          : {f(result.mr_center)}",
        f"LCL                 : {f(result.mr_lcl)}",

        "Test 1 signals      : "
        + _format_test1_signals(
            result.mr_violations
        ),

        "",
        "INDIVIDUALS (I) CHART",
        "-" * 40,

        f"UCL                 : {f(result.i_ucl)}",
        f"CL (Mean)           : {f(result.i_center)}",
        f"LCL                 : {f(result.i_lcl)}",

        "Test 1 signals      : "
        + _format_test1_signals(
            result.i_violations
        ),
    ]

    # =====================================
    # 3. OBSERVATION TABLE
    # =====================================

    lines.extend(
        _format_observation_table(result)
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
    # 5. INTERPRETATION
    # =====================================

    lines.extend([
        "",
        "INTERPRETATION NOTES",
        "-" * 40,

        "- Review MR variation before "
        "interpreting the I Chart.",

        "- No Test 1 signal does not "
        "prove process stability.",

        "- Control limits are not "
        "product specification limits.",

        "- Observations must be "
        "ordered chronologically.",

        "- Test 1 is evaluated against "
        "Phase I limits computed from "
        "these observations.",

        "- Advanced SPC Test findings "
        "are shown separately "
        "when enabled.",

        "- Calculations retain "
        "floating-point precision; "
        "display is rounded.",

        "",
        "STATDESK REPORT INFORMATION",
        "-" * 40,

        f"Report version      : {IMR_REPORT_VERSION}",
        f"Statistical engine  : {SPC_ENGINE_VERSION}",
        "Analysis            : I-MR Phase I",
        "Control limits     : Calculated by SpcEngine",

        "",
        "END OF I-MR REPORT",
    ])

    return "\n".join(lines)
