
"""StatDesk R3 — Xbar-R Phase II with historical control limits.

Statistical workflow:
1. Estimate historical mean and sigma from rational subgroups,
   using the Phase I XbarREngine (Rbar / d2), or enter parameters.
2. Calculate fixed Shewhart 3-sigma Xbar and R control limits.
3. Monitor new subgroups against those historical limits.
4. Report SPC Tests 1-4 without recalculating control limits.

R3.13:
- Enhanced Phase II Session Output.
- Individual SPC Test results for Xbar and R.
- Subgroup statistics with signal labels.
- Distinguish insufficient rule windows from no signals.

No administrative QA/QC workflows.
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
PHASE2_REPORT_VERSION = "0.3.0"

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
# 3. RESULT CONTRACTS
# ======================================================

@dataclass(frozen=True)
class XbarRHistoricalLimits:
    """Fixed historical Xbar-R limits for one subgroup size."""

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


# Backward compatibility with the earlier R3 interface.
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
# 4. NUMERICAL VALIDATION
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
# 5. SUBGROUP VALIDATION
# ======================================================

def _read_subgroups(
    subgroups,
    *,
    expected_size=None,
) -> tuple[tuple[float, ...], ...]:
    """Read ordered, complete, equal-size rational subgroups."""

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
    """Create a deterministic fingerprint of historical data."""

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
    """Validate selected SPC Tests and rule profile."""

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
    """Evaluate SPC rules without changing control limits."""

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
    """Validate historical parameters and control limits."""

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

    Xbar:
        CL  = mu
        UCL = mu + 3*sigma/sqrt(n)
        LCL = mu - 3*sigma/sqrt(n)

    R:
        CL  = d2*sigma
        UCL = (d2 + 3*d3)*sigma
        LCL = max(0, (d2 - 3*d3)*sigma)

    Sigma represents within-process standard deviation.
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

    d2, d3 = RANGE_CONSTANTS[n]

    try:
        margin = 3.0 * sigma / sqrt(n)

        xbar_ucl = mu + margin
        xbar_lcl = mu - margin

        r_cl = d2 * sigma
        r_ucl = (d2 + 3.0 * d3) * sigma

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
# 10. ESTIMATE HISTORICAL PARAMETERS
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
    """Estimate historical limits using Phase I Xbar-R.

    Historical SPC findings are reported, not removed.
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

    try:
        phase1 = XbarREngine.calculate(groups)

    except XbarRError as exc:
        raise Phase2Error(
            str(exc)
        ) from exc

    # Historical SPC Rules
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

    warnings = [
        "Sigma within diestimasi dengan Rbar/d2.",
        "Konstanta d2/d3 menggunakan nilai "
        "tabel publikasi yang dibulatkan.",
    ]

    windows = get_rule_windows(rule_profile)

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

    # Within sigma from the existing Phase I estimator.
    d2 = RANGE_CONSTANTS[
        phase1.subgroup_size
    ][0]

    sigma_within = phase1.r_cl / d2

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
# 11. BACKWARD COMPATIBILITY
# ======================================================

def build_xbar_r_baseline_candidate(
    subgroups,
    *,
    process_id,
    characteristic,
    unit,
) -> XbarRHistoricalLimits:
    """Compatibility entry point for the older R3 interface."""

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

    # Preserve the original compatibility behavior.
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
# 12. PHASE II MONITORING ENGINE
# ======================================================

def monitor_xbar_r_phase2(
    historical_limits,
    new_subgroups,
    *,
    enabled_tests=(1,),
    rule_profile=RULE_PROFILE_STANDARD,
) -> Phase2XbarRResult:
    """Monitor new data against fixed historical limits.

    Control limits are not recalculated.
    SPC run tests restart for each monitoring batch.
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

    for index, row in enumerate(
        groups,
        start=1,
    ):
        try:
            mean = fsum(row) / len(row)
            spread = max(row) - min(row)

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
# 13. COMMON SPC SIGNAL FORMATTER
# ======================================================

def _signals(
    rules: RulesResult | None,
) -> str:
    """Format findings as T1@point, T2@point, etc."""

    if rules is None:
        return "Tidak diperiksa"

    if not rules.findings:
        return "Tidak ada"

    return ", ".join(
        f"T{item.test}@{item.point}"
        for item in rules.findings
    )


# ======================================================
# 14. HISTORICAL PARAMETERS SESSION OUTPUT
# ======================================================

def format_xbar_r_historical_limits_report(
    limits: XbarRHistoricalLimits,
) -> str:
    """Format historical control limits and screening results."""

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
# 15. R3.13 - REPORT HELPER FUNCTIONS
# ======================================================

def _rule_test_summary(
    rules: RulesResult,
    chart_name: str,
) -> list[str]:
    """Describe each SPC Test using existing engine findings.

    No signal:
        The test had enough observations but no finding.

    Insufficient data:
        The test's required window cannot yet be completed.
    """

    windows = get_rule_windows(
        rules.rule_profile
    )

    lines = [
        "",
        f"{chart_name} — SPC TEST DETAILS",
        "-" * 56,
    ]

    for test in rules.enabled_tests:
        required = windows[test]

        findings = [
            item
            for item in rules.findings
            if item.test == test
        ]

        if rules.n_points < required:
            lines.append(
                f"Test {test}: BELUM CUKUP DATA "
                f"({rules.n_points}/{required} titik)"
            )
            continue

        if not findings:
            lines.append(
                f"Test {test}: Tidak ada signal"
            )
            continue

        locations = []

        for finding in findings:
            if test == 1:
                locations.append(
                    f"T1@{finding.point}"
                )
            else:
                locations.append(
                    f"T{test}@{finding.point} "
                    f"(window {finding.window_start}-"
                    f"{finding.point})"
                )

        lines.append(
            f"Test {test}: "
            + ", ".join(locations)
        )

    return lines


def _signal_tags_at(
    rules: RulesResult,
    subgroup_number: int,
) -> str:
    """Return all SPC Test labels ending at one subgroup."""

    tests = sorted({
        finding.test
        for finding in rules.findings
        if finding.point == subgroup_number
    })

    if not tests:
        return "-"

    return ",".join(
        f"T{test}"
        for test in tests
    )


def _monitoring_table(
    result: Phase2XbarRResult,
) -> list[str]:
    """Format subgroup statistics without recalculating them."""

    f = format_spc_number

    total = len(result.means)

    shown = min(
        total,
        MAX_REPORT_ROWS,
    )

    lines = [
        "",
        "MONITORING SUBGROUP STATISTICS",
        "-" * 68,

        (
            f"{'No':>4} | "
            f"{'Xbar':>12} | "
            f"{'Range':>12} | "
            f"{'Xbar Tests':>12} | "
            f"{'R Tests':>10}"
        ),

        "-" * 68,
    ]

    for index in range(shown):
        number = index + 1

        xbar_tags = _signal_tags_at(
            result.xbar_rules,
            number,
        )

        r_tags = _signal_tags_at(
            result.r_rules,
            number,
        )

        lines.append(
            f"{number:>4} | "
            f"{f(result.means[index]):>12} | "
            f"{f(result.ranges[index]):>12} | "
            f"{xbar_tags:>12} | "
            f"{r_tags:>10}"
        )

    omitted = total - shown

    if omitted > 0:
        lines.extend([
            "",
            f"... {omitted} subgroup rows omitted "
            "from Session Output.",
            "All monitoring points were still evaluated "
            "by the statistical engine.",
        ])

    lines.extend([
        "",
        "T1-T4 = detected SPC Test at this subgroup.",
        "-     = no detected signal at this subgroup.",
    ])

    return lines


# ======================================================
# 16. R3.13 - PHASE II SESSION OUTPUT
# ======================================================

def format_phase2_xbar_r_report(
    result: Phase2XbarRResult,
) -> str:
    """Generate a complete Xbar-R Phase II monitoring report.

    Historical control limits, subgroup statistics,
    and SPC findings originate from the existing engine.

    This function does not modify or recalculate limits.
    """

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

    subgroup_count = len(result.means)

    selected = ", ".join(
        str(test)
        for test in result.xbar_rules.enabled_tests
    )

    profile = result.xbar_rules.rule_profile

    source_name = (
        "Estimated from historical data"
        if ref.source == "estimated"
        else "Manually specified historical parameters"
    )

    # ==========================================
    # A. REPORT HEADER
    # ==========================================

    lines = [
        "XBAR-R CONTROL CHART — PHASE II",
        "=" * 68,

        "",
        "DATA INFORMATION",
        "-" * 40,

        f"Monitoring subgroups  : {subgroup_count}",
        f"Subgroup size         : {ref.subgroup_size}",
        f"Total measurements    : "
        f"{subgroup_count * ref.subgroup_size}",

        "",
        "HISTORICAL PARAMETERS",
        "-" * 40,

        f"Parameter source      : {source_name}",
        f"Historical mean       : {f(ref.historical_mean)}",
        f"Historical sigma      : {f(ref.historical_sigma)}",
    ]

    if ref.subgroup_count:
        lines.append(
            f"Historical subgroups  : {ref.subgroup_count}"
        )

    # ==========================================
    # B. STATISTICAL METHOD
    # ==========================================

    d2, d3 = RANGE_CONSTANTS[
        ref.subgroup_size
    ]

    lines.extend([
        "",
        "STATISTICAL METHOD",
        "-" * 40,

        "Chart type            : Xbar-R Phase II",
        "Control limit method  : Shewhart 3-sigma",
        "Historical limits     : FIXED",
        "Monitoring limits     : Not recalculated",

        f"d2                    : {d2:.4f}",
        f"d3                    : {d3:.4f}",

        "",
        "XBAR CHART — FIXED HISTORICAL LIMITS",
        "-" * 40,

        f"UCL                   : {f(ref.xbar_ucl)}",
        f"CL                    : {f(ref.xbar_cl)}",
        f"LCL                   : {f(ref.xbar_lcl)}",

        "",
        "R CHART — FIXED HISTORICAL LIMITS",
        "-" * 40,

        f"UCL                   : {f(ref.r_ucl)}",
        f"CL                    : {f(ref.r_cl)}",
        f"LCL                   : {f(ref.r_lcl)}",
    ])

    # ==========================================
    # C. SPC CONFIGURATION
    # ==========================================

    lines.extend([
        "",
        "SPC TEST CONFIGURATION",
        "-" * 40,

        f"Enabled Tests         : {selected}",
        f"Rule profile          : {profile}",
        "Signal numbering      : 1-based subgroup index",

        "",
        "SPC SIGNAL SUMMARY",
        "-" * 40,

        f"Xbar signals          : {_signals(result.xbar_rules)}",
        f"R signals             : {_signals(result.r_rules)}",

        f"Xbar findings         : "
        f"{len(result.xbar_rules.findings)}",

        f"R findings            : "
        f"{len(result.r_rules.findings)}",
    ])

    # ==========================================
    # D. INDIVIDUAL RULE RESULTS
    # ==========================================

    lines.extend(
        _rule_test_summary(
            result.xbar_rules,
            "XBAR CHART",
        )
    )

    lines.extend(
        _rule_test_summary(
            result.r_rules,
            "R CHART",
        )
    )

    # ==========================================
    # E. SUBGROUP RESULTS
    # ==========================================

    lines.extend(
        _monitoring_table(result)
    )

    # ==========================================
    # F. INTERPRETATION
    # ==========================================

    lines.extend([
        "",
        "INTERPRETATION NOTES",
        "-" * 40,

        "- Historical control limits remain fixed "
        "during Phase II monitoring.",

        "- New observations are evaluated against "
        "the historical control limits.",

        "- SPC Test 1 identifies points strictly "
        "outside the control limits.",

        "- SPC Tests 2-4 require enough consecutive "
        "subgroups to evaluate their patterns.",

        "- Insufficient data for a rule window "
        "does not mean the rule has passed.",

        "- SPC run tests restart within each "
        "monitoring batch; cross-batch continuity "
        "is not implemented.",

        "- Signal numbers refer to subgroup "
        "positions in the current monitoring batch.",

        "- No detected signal does not prove "
        "that a process is statistically stable.",

        "- Control limits are not product "
        "specification limits.",

        "- Statistical calculations retain "
        "floating-point precision; displayed "
        "values are rounded.",

        "",
        "STATDESK REPORT INFORMATION",
        "-" * 40,

        f"Report version        : {PHASE2_REPORT_VERSION}",
        f"Phase II engine       : {PHASE2_VERSION}",
        "Analysis              : Xbar-R Phase II",
        "Historical limits     : Unchanged",

        "",
        "END OF XBAR-R PHASE II REPORT",
    ])

    return "\n".join(lines)
