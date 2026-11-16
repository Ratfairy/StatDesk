
"""StatDesk R3 — Xbar-R Phase II with historical control limits.

Statistical workflow:
1. Estimate historical mean and sigma from rational subgroups,
   using the existing Phase I XbarREngine (Rbar / d2); OR
   enter historical mean and sigma directly.
2. Calculate fixed Shewhart 3-sigma Xbar and R control limits.
3. Evaluate new subgroups against those historical limits.
4. Report SPC Tests 1-4, without recalculating monitoring limits.

This module has no GUI, approval, authentication, or disk dependencies.
Subgroup sizes are 2..8, matching the current Xbar-R engine.
SPC run tests are evaluated per batch (no cross-batch continuity).
"""

from dataclasses import dataclass
from hashlib import sha256
import json
from math import fsum, isfinite, sqrt
from numbers import Real

from statdesk.statistics.spc_number_format import (
    format_spc_number,
)

from statdesk.statistics.spc_rules import (
    RULE_PROFILE_STANDARD,
    RulesResult,
    SpcRulesError,
    evaluate_spc_rules,
    get_rule_windows,
)

from statdesk.statistics.xbar_r_engine import (
    MAX_SUBGROUP_SIZE,
    MIN_SUBGROUP_SIZE,
    RANGE_CONSTANTS,
    XbarREngine,
    XbarRError,
)


# ======================================================
# 1. CONFIGURATION
# ======================================================

PHASE2_VERSION = "0.2.0"

MAX_SUBGROUPS = 50_000
MAX_REPORT_ROWS = 30

BASELINE_SCREENING_TESTS = (1, 2, 3, 4)

DEFAULT_HISTORICAL_TESTS = BASELINE_SCREENING_TESTS


# ======================================================
# 2. EXCEPTION
# ======================================================

class Phase2Error(ValueError):
    """Invalid input, configuration, or Phase II result."""


# ======================================================
# 3. IMMUTABLE RESULT CONTRACTS
# ======================================================

@dataclass(frozen=True)
class XbarRHistoricalLimits:
    """Fixed Xbar-R limits for one subgroup size.

    source:
        "estimated" — from historical subgroups
        "specified" — historical mean and sigma entered manually

    The SHA-256 fingerprint records the converted historical
    floating-point input values when parameters are estimated.
    """

    subgroup_size: int

    historical_mean: float
    historical_sigma: float

    xbar_cl: float
    xbar_ucl: float
    xbar_lcl: float

    r_cl: float
    r_ucl: float
    r_lcl: float

    source: str

    subgroup_count: int = 0
    source_sha256: str = ""

    process_id: str = ""
    characteristic: str = ""
    unit: str = ""

    historical_xbar_rules: RulesResult | None = None
    historical_r_rules: RulesResult | None = None

    warnings: tuple[str, ...] = ()


# Compatibility with the existing R3 Step-1 GUI.
# The old GUI reads process_id, characteristic, unit,
# subgroup_count, source_sha256, and control limits.

XbarRBaselineCandidate = XbarRHistoricalLimits


@dataclass(frozen=True)
class Phase2XbarRResult:
    """Results of monitoring against historical limits."""

    baseline: XbarRHistoricalLimits

    means: tuple[float, ...]
    ranges: tuple[float, ...]

    xbar_rules: RulesResult
    r_rules: RulesResult

    @property
    def historical_limits(self) -> XbarRHistoricalLimits:
        return self.baseline


# ======================================================
# 4. COMMON NUMERICAL VALIDATION
# ======================================================

def _finite_number(raw, label: str) -> float:
    """Convert an existing numeric value to finite float."""

    if (
        isinstance(raw, bool)
        or not isinstance(raw, Real)
    ):
        raise Phase2Error(
            f"{label} harus angka Numeric."
        )

    try:
        number = float(raw)

    except (
        TypeError,
        ValueError,
        OverflowError,
    ) as exc:
        raise Phase2Error(
            f"{label} tidak dapat dikonversi."
        ) from exc

    if not isfinite(number):
        raise Phase2Error(
            f"{label} tidak boleh NaN/Infinity."
        )

    return number


def _optional_text(value, label: str) -> str:
    """Normalize optional descriptive metadata."""

    if value is None:
        return ""

    if not isinstance(value, str):
        raise Phase2Error(
            f"{label} harus berupa teks."
        )

    return value.strip()


def _subgroup_size(value) -> int:
    """Validate supported Xbar-R subgroup size."""

    if (
        type(value) is not int
        or not MIN_SUBGROUP_SIZE <= value <= MAX_SUBGROUP_SIZE
    ):
        raise Phase2Error(
            "Xbar-R mendukung subgroup size "
            f"{MIN_SUBGROUP_SIZE} sampai "
            f"{MAX_SUBGROUP_SIZE}."
        )

    return value


# ======================================================
# 5. SUBGROUP DATA VALIDATION
# ======================================================

def _read_subgroups(
    subgroups,
    *,
    expected_size=None,
) -> tuple[tuple[float, ...], ...]:
    """Read ordered, equal-size rational subgroups.

    Rules:
    - One row represents one subgroup.
    - Each subgroup has equal measurement count.
    - Measurements must be finite numeric values.
    - Missing values are not silently omitted.
    - Original row order is preserved.
    """

    if expected_size is not None:
        _subgroup_size(expected_size)

    if isinstance(subgroups, (str, bytes)):
        raise Phase2Error(
            "Subgroups harus berupa baris pengukuran."
        )

    try:
        iterator = iter(subgroups)

    except TypeError as exc:
        raise Phase2Error(
            "Subgroups harus iterable."
        ) from exc

    prepared = []
    width = expected_size

    for row_index, group in enumerate(
        iterator,
        start=1,
    ):

        if row_index > MAX_SUBGROUPS:
            raise Phase2Error(
                f"Maksimal {MAX_SUBGROUPS} subgroup."
            )

        if isinstance(group, (str, bytes)):
            raise Phase2Error(
                f"Subgroup {row_index} "
                "bukan baris pengukuran."
            )

        try:
            row = tuple(group)

        except TypeError as exc:
            raise Phase2Error(
                f"Subgroup {row_index} tidak iterable."
            ) from exc

        if width is None:
            width = _subgroup_size(len(row))

        if len(row) != width:
            raise Phase2Error(
                f"Subgroup {row_index} harus berisi "
                f"{width} pengukuran."
            )

        numeric_row = tuple(
            _finite_number(
                value,
                f"Subgroup {row_index}, sampel {index}",
            )
            for index, value in enumerate(
                row,
                start=1,
            )
        )

        prepared.append(numeric_row)

    if not prepared:
        raise Phase2Error(
            "Minimal diperlukan satu subgroup."
        )

    return tuple(prepared)


# ======================================================
# 6. HISTORICAL DATA FINGERPRINT
# ======================================================

def _digest(
    groups: tuple[tuple[float, ...], ...],
) -> str:
    """Create a deterministic historical-data fingerprint.

    Float.hex() preserves the binary floating-point
    representation used by the calculation engine.
    """

    payload = [
        [value.hex() for value in row]
        for row in groups
    ]

    encoded = json.dumps(
        payload,
        separators=(",", ":"),
    ).encode("ascii")

    return sha256(encoded).hexdigest()


# ======================================================
# 7. SPC TEST VALIDATION
# ======================================================

def _validate_tests(
    enabled_tests,
    rule_profile,
) -> tuple[int, ...]:
    """Validate SPC Tests and rule profile."""

    try:
        windows = get_rule_windows(rule_profile)
        selected = tuple(enabled_tests)

    except (
        SpcRulesError,
        TypeError,
    ) as exc:
        raise Phase2Error(
            f"Konfigurasi SPC Tests tidak valid: {exc}"
        ) from exc

    if (
        not selected
        or any(
            type(test) is not int
            or test not in windows
            for test in selected
        )
    ):
        raise Phase2Error(
            "Pilih satu atau beberapa "
            "SPC Tests 1, 2, 3, 4."
        )

    if len(set(selected)) != len(selected):
        raise Phase2Error(
            "SPC Tests tidak boleh duplikat."
        )

    return tuple(sorted(selected))


def _evaluate(
    points,
    *,
    cl,
    lcl,
    ucl,
    enabled_tests,
    rule_profile,
) -> RulesResult:
    """Evaluate existing SPC rules without changing limits."""

    try:
        return evaluate_spc_rules(
            points,
            center_line=cl,
            lcl=lcl,
            ucl=ucl,
            enabled_tests=enabled_tests,
            rule_profile=rule_profile,
        )

    except SpcRulesError as exc:
        raise Phase2Error(
            f"Gagal mengevaluasi SPC Tests: {exc}"
        ) from exc


# ======================================================
# 8. HISTORICAL LIMIT VALIDATION
# ======================================================

def _validate_limits(
    limits,
) -> XbarRHistoricalLimits:
    """Validate the structure and numerical limits."""

    if not isinstance(
        limits,
        XbarRHistoricalLimits,
    ):
        raise Phase2Error(
            "Historical limits harus "
            "XbarRHistoricalLimits."
        )

    _subgroup_size(limits.subgroup_size)

    _finite_number(
        limits.historical_mean,
        "Historical mean",
    )

    sigma = _finite_number(
        limits.historical_sigma,
        "Historical sigma",
    )

    if sigma <= 0.0:
        raise Phase2Error(
            "Historical sigma harus "
            "lebih besar dari nol."
        )

    for name in (
        "xbar_cl",
        "xbar_ucl",
        "xbar_lcl",
        "r_cl",
        "r_ucl",
        "r_lcl",
    ):
        _finite_number(
            getattr(limits, name),
            name,
        )

    if not (
        limits.xbar_lcl
        < limits.xbar_cl
        < limits.xbar_ucl
    ):
        raise Phase2Error(
            "Batas Xbar harus LCL < CL < UCL."
        )

    if not (
        0.0 <= limits.r_lcl
        < limits.r_cl
        < limits.r_ucl
    ):
        raise Phase2Error(
            "Batas R harus 0 <= LCL < CL < UCL."
        )

    if limits.xbar_cl != limits.historical_mean:
        raise Phase2Error(
            "Xbar CL harus sama "
            "dengan historical mean."
        )

    if limits.source not in (
        "estimated",
        "specified",
    ):
        raise Phase2Error(
            "Sumber historical limits tidak dikenal."
        )

    return limits


# ======================================================
# 9. MANUAL HISTORICAL PARAMETERS
# ======================================================

def create_xbar_r_historical_limits(
    *,
    historical_mean,
    historical_sigma,
    subgroup_size,
    process_id="",
    characteristic="",
    unit="",
) -> XbarRHistoricalLimits:
    """Calculate historical Xbar-R limits from mean and sigma.

    For constant subgroup size n:

    Xbar:
        CL  = mu
        UCL = mu + 3*sigma/sqrt(n)
        LCL = mu - 3*sigma/sqrt(n)

    R:
        CL  = d2*sigma
        UCL = (d2 + 3*d3)*sigma
        LCL = max(0, (d2 - 3*d3)*sigma)

    sigma is within-process standard deviation,
    NOT the average subgroup range.
    """

    n = _subgroup_size(subgroup_size)

    mu = _finite_number(
        historical_mean,
        "Historical mean",
    )

    sigma = _finite_number(
        historical_sigma,
        "Historical sigma",
    )

    if sigma <= 0.0:
        raise Phase2Error(
            "Historical sigma harus "
            "lebih besar dari nol."
        )

    # Reuse published constants from the Phase I engine.
    d2, d3 = RANGE_CONSTANTS[n]

    try:
        margin = 3.0 * sigma / sqrt(n)

        xbar_ucl = mu + margin
        xbar_lcl = mu - margin

        r_cl = d2 * sigma

        r_ucl = (
            (d2 + 3.0 * d3) * sigma
        )

        r_lcl = max(
            0.0,
            (d2 - 3.0 * d3) * sigma,
        )

    except (
        ValueError,
        OverflowError,
        ZeroDivisionError,
    ) as exc:
        raise Phase2Error(
            "Gagal menghitung "
            "historical control limits."
        ) from exc

    limits = XbarRHistoricalLimits(
        subgroup_size=n,

        historical_mean=mu,
        historical_sigma=sigma,

        xbar_cl=mu,
        xbar_ucl=xbar_ucl,
        xbar_lcl=xbar_lcl,

        r_cl=r_cl,
        r_ucl=r_ucl,
        r_lcl=r_lcl,

        source="specified",

        process_id=_optional_text(
            process_id,
            "Process ID",
        ),
        characteristic=_optional_text(
            characteristic,
            "Characteristic",
        ),
        unit=_optional_text(
            unit,
            "Unit",
        ),
    )

    return _validate_limits(limits)


# ======================================================
# 10. ESTIMATE HISTORICAL PARAMETERS FROM DATA
# ======================================================

def estimate_xbar_r_historical_limits(
    historical_subgroups,
    *,
    process_id="",
    characteristic="",
    unit="",
    enabled_tests=DEFAULT_HISTORICAL_TESTS,
    rule_profile=RULE_PROFILE_STANDARD,
) -> XbarRHistoricalLimits:
    """Estimate historical limits with existing XbarREngine.

    Steps:
    1. Validate historical subgroups.
    2. Reuse Phase I Xbar-R calculations.
    3. Estimate sigma using Rbar/d2.
    4. Evaluate historical SPC Tests.
    5. Return fixed historical limits.

    SPC findings are reported, not automatically removed.

    A short history may not have enough points to
    complete the window of every selected SPC test.
    """

    selected = _validate_tests(
        enabled_tests,
        rule_profile,
    )

    groups = _read_subgroups(
        historical_subgroups
    )

    if len(groups) < 2:
        raise Phase2Error(
            "Estimasi membutuhkan minimal "
            "dua subgroup."
        )

    # ======================================
    # REUSE EXISTING PHASE I ENGINE
    # ======================================

    try:
        phase1 = XbarREngine.calculate(groups)

    except XbarRError as exc:
        raise Phase2Error(
            str(exc)
        ) from exc

    # ======================================
    # HISTORICAL SPC TESTS
    # ======================================

    r_rules = _evaluate(
        phase1.ranges,
        cl=phase1.r_cl,
        lcl=phase1.r_lcl,
        ucl=phase1.r_ucl,
        enabled_tests=selected,
        rule_profile=rule_profile,
    )

    xbar_rules = _evaluate(
        phase1.means,
        cl=phase1.xbar_cl,
        lcl=phase1.xbar_lcl,
        ucl=phase1.xbar_ucl,
        enabled_tests=selected,
        rule_profile=rule_profile,
    )

    # ======================================
    # METHOD NOTES
    # ======================================

    warnings = [
        "Sigma within diestimasi dengan Rbar/d2.",
        "Konstanta d2/d3 menggunakan nilai "
        "tabel publikasi yang dibulatkan.",
    ]

    windows = get_rule_windows(
        rule_profile
    )

    missing_windows = [
        f"T{test} ({windows[test]} titik)"
        for test in selected
        if len(groups) < windows[test]
    ]

    if missing_windows:
        warnings.append(
            "Data historis belum cukup "
            "untuk window: "
            + ", ".join(missing_windows)
            + "."
        )

    if (
        r_rules.findings
        or xbar_rules.findings
    ):
        warnings.append(
            "SPC signal terdeteksi pada data historis; "
            "periksa interpretasi sebelum memakai "
            "parameter tersebut."
        )

    # ======================================
    # HISTORICAL SIGMA
    # ======================================

    # XbarRResult currently exposes R center,
    # but does not expose sigma_within directly.
    #
    # sigma = Rbar / d2

    d2 = RANGE_CONSTANTS[
        phase1.subgroup_size
    ][0]

    sigma_within = (
        phase1.r_cl / d2
    )

    # ======================================
    # RETURN HISTORICAL LIMITS
    # ======================================

    limits = XbarRHistoricalLimits(
        subgroup_size=phase1.subgroup_size,
        subgroup_count=phase1.subgroup_count,

        historical_mean=phase1.xbar_cl,
        historical_sigma=sigma_within,

        xbar_cl=phase1.xbar_cl,
        xbar_ucl=phase1.xbar_ucl,
        xbar_lcl=phase1.xbar_lcl,

        r_cl=phase1.r_cl,
        r_ucl=phase1.r_ucl,
        r_lcl=phase1.r_lcl,

        source="estimated",
        source_sha256=_digest(groups),

        process_id=_optional_text(
            process_id,
            "Process ID",
        ),
        characteristic=_optional_text(
            characteristic,
            "Characteristic",
        ),
        unit=_optional_text(
            unit,
            "Unit",
        ),

        historical_xbar_rules=xbar_rules,
        historical_r_rules=r_rules,

        warnings=tuple(warnings),
    )

    return _validate_limits(limits)


# ======================================================
# 11. COMPATIBILITY WITH OLD R3 CANDIDATE GUI
# ======================================================

def build_xbar_r_baseline_candidate(
    subgroups,
    *,
    process_id,
    characteristic,
    unit,
) -> XbarRHistoricalLimits:
    """Compatibility entry point for the old R3 GUI.

    New GUI code should call:
        estimate_xbar_r_historical_limits()

    This wrapper retains the old metadata arguments.
    """

    if not all((
        _optional_text(
            process_id,
            "Process ID",
        ),
        _optional_text(
            characteristic,
            "Characteristic",
        ),
        _optional_text(
            unit,
            "Unit",
        ),
    )):
        raise Phase2Error(
            "Process ID, Characteristic, dan Unit "
            "wajib diisi pada dialog lama."
        )

    limits = estimate_xbar_r_historical_limits(
        subgroups,
        process_id=process_id,
        characteristic=characteristic,
        unit=unit,
    )

    # The old GUI hard-codes "No SPC Tests 1-4 findings"
    # in its Session Output. Reject that obsolete GUI path
    # if signals exist, rather than displaying false results.
    #
    # The new estimation function above DOES NOT block
    # historical data merely because signals were detected.

    if (
        limits.historical_r_rules.findings
        or limits.historical_xbar_rules.findings
    ):
        raise Phase2Error(
            "Data historis memiliki SPC signal. "
            "Gunakan workflow Historical Parameters "
            "yang akan menggantikan dialog lama."
        )

    return limits


# ======================================================
# 12. PHASE II MONITORING
# ======================================================

def monitor_xbar_r_phase2(
    historical_limits,
    new_subgroups,
    *,
    enabled_tests=(1,),
    rule_profile=RULE_PROFILE_STANDARD,
) -> Phase2XbarRResult:
    """Monitor new subgroups against fixed historical limits.

    Historical control limits are NOT recalculated.

    Monitoring subgroups are used only to calculate:
    - Subgroup means.
    - Subgroup ranges.
    - SPC signal findings.

    SPC run tests restart at the beginning of each batch.
    """

    limits = _validate_limits(
        historical_limits
    )

    selected = _validate_tests(
        enabled_tests,
        rule_profile,
    )

    groups = _read_subgroups(
        new_subgroups,
        expected_size=limits.subgroup_size,
    )

    means = []
    ranges = []

    # ======================================
    # NEW SUBGROUP STATISTICS
    # ======================================

    for index, row in enumerate(
        groups,
        start=1,
    ):

        try:
            mean = (
                fsum(row) / len(row)
            )

            spread = (
                max(row) - min(row)
            )

        except (
            ValueError,
            OverflowError,
        ) as exc:
            raise Phase2Error(
                f"Subgroup {index}: gagal "
                "menghitung mean/range."
            ) from exc

        if not (
            isfinite(mean)
            and isfinite(spread)
        ):
            raise Phase2Error(
                f"Subgroup {index}: "
                "hasil non-finite."
            )

        means.append(mean)
        ranges.append(spread)

    # ======================================
    # EVALUATE USING HISTORICAL LIMITS
    # ======================================

    r_rules = _evaluate(
        ranges,
        cl=limits.r_cl,
        lcl=limits.r_lcl,
        ucl=limits.r_ucl,
        enabled_tests=selected,
        rule_profile=rule_profile,
    )

    xbar_rules = _evaluate(
        means,
        cl=limits.xbar_cl,
        lcl=limits.xbar_lcl,
        ucl=limits.xbar_ucl,
        enabled_tests=selected,
        rule_profile=rule_profile,
    )

    return Phase2XbarRResult(
        baseline=limits,

        means=tuple(means),
        ranges=tuple(ranges),

        xbar_rules=xbar_rules,
        r_rules=r_rules,
    )


# ======================================================
# 13. SPC SIGNAL FORMATTER
# ======================================================

def _signals(
    rules: RulesResult | None,
) -> str:
    """Format SPC findings using 1-based point indexes."""

    if rules is None:
        return "Tidak diperiksa"

    if not rules.findings:
        return "Tidak ada"

    return ", ".join(
        f"T{item.test}@{item.point}"
        for item in rules.findings
    )


# ======================================================
# 14. HISTORICAL LIMITS SESSION OUTPUT
# ======================================================

def format_xbar_r_historical_limits_report(
    limits: XbarRHistoricalLimits,
) -> str:
    """Format estimated or manually specified control limits."""

    ref = _validate_limits(limits)

    f = format_spc_number

    lines = [
        "XBAR-R — HISTORICAL CONTROL LIMITS",
        "=" * 56,

        f"Parameter source    : {ref.source}",
        f"Subgroup size       : {ref.subgroup_size}",

        f"Historical mean     : {f(ref.historical_mean)}",
        f"Historical sigma    : {f(ref.historical_sigma)}",
    ]

    if ref.subgroup_count:
        lines.append(
            f"Historical subgroups: {ref.subgroup_count}"
        )

    for label, value in (
        ("Process ID", ref.process_id),
        ("Characteristic", ref.characteristic),
        ("Unit", ref.unit),
    ):
        if value:
            lines.append(
                f"{label:20}: {value}"
            )

    if ref.source_sha256:
        lines.append(
            f"Historical SHA-256  : {ref.source_sha256}"
        )

    lines += [
        "",

        "XBAR CHART — HISTORICAL 3-SIGMA LIMITS",

        f"UCL                 : {f(ref.xbar_ucl)}",
        f"CL                  : {f(ref.xbar_cl)}",
        f"LCL                 : {f(ref.xbar_lcl)}",

        "",

        "R CHART — HISTORICAL 3-SIGMA LIMITS",

        f"UCL                 : {f(ref.r_ucl)}",
        f"CL                  : {f(ref.r_cl)}",
        f"LCL                 : {f(ref.r_lcl)}",
    ]

    if ref.source == "estimated":
        lines += [
            "",

            "HISTORICAL SPC TESTS",

            "R signals           : "
            + _signals(ref.historical_r_rules),

            "Xbar signals        : "
            + _signals(ref.historical_xbar_rules),
        ]

    if ref.warnings:
        lines += [
            "",
            "NOTES",
        ]

        lines.extend(
            f"- {message}"
            for message in ref.warnings
        )

    lines += [
        "",

        "- Control limits are not specification limits.",

        "- Calculations retain full float precision; "
        "display is rounded.",

        f"StatDesk Phase II Engine {PHASE2_VERSION}",
    ]

    return "\n".join(lines)


# ======================================================
# 15. PHASE II MONITORING SESSION OUTPUT
# ======================================================

def format_phase2_xbar_r_report(
    result: Phase2XbarRResult,
) -> str:
    """Format monitoring results using frozen historical limits."""

    if not isinstance(
        result,
        Phase2XbarRResult,
    ):
        raise Phase2Error(
            "Hasil monitoring Phase II tidak valid."
        )

    ref = _validate_limits(
        result.baseline
    )

    f = format_spc_number

    selected = ", ".join(
        str(test)
        for test in result.xbar_rules.enabled_tests
    )

    profile = result.xbar_rules.rule_profile

    lines = [
        "XBAR-R PHASE II — HISTORICAL CONTROL LIMITS",
        "=" * 56,

        f"Source              : {ref.source}",
        f"Subgroup size       : {ref.subgroup_size}",
        f"Monitoring subgroups: {len(result.means)}",

        f"Historical mean     : {f(ref.historical_mean)}",
        f"Historical sigma    : {f(ref.historical_sigma)}",

        "",

        "R CHART (fixed limits)",

        f"UCL                 : {f(ref.r_ucl)}",
        f"CL                  : {f(ref.r_cl)}",
        f"LCL                 : {f(ref.r_lcl)}",

        "",

        "XBAR CHART (fixed limits)",

        f"UCL                 : {f(ref.xbar_ucl)}",
        f"CL                  : {f(ref.xbar_cl)}",
        f"LCL                 : {f(ref.xbar_lcl)}",

        "",

        "SPC SIGNALS (monitoring batch)",

        f"Enabled Tests       : {selected}",
        f"Rule profile        : {profile}",

        f"R signals           : {_signals(result.r_rules)}",
        f"Xbar signals        : {_signals(result.xbar_rules)}",

        "",

        "MONITORING SUBGROUP STATISTICS",

        "Subgroup | Xbar | R",
    ]

    for index, (mean, spread) in enumerate(
        zip(result.means, result.ranges),
        start=1,
    ):

        if index > MAX_REPORT_ROWS:
            omitted = (
                len(result.means) - MAX_REPORT_ROWS
            )

            lines.append(
                f"... {omitted} rows omitted "
                "from Session Output"
            )

            break

        lines.append(
            f"{index:8} | "
            f"{f(mean):>12} | "
            f"{f(spread):>12}"
        )

    lines += [
        "",

        "INTERPRETATION NOTES",

        "- Monitoring points do not change "
        "historical control limits.",

        "- SPC run tests restart in each batch; "
        "continuity is not implemented.",

        "- Signal numbers are 1-based within "
        "this monitoring batch.",

        "- Control limits are not product "
        "specification limits.",

        "- Display formatting does not round "
        "statistical calculations.",

        f"StatDesk Phase II Engine {PHASE2_VERSION}",
    ]

    return "\n".join(lines)
