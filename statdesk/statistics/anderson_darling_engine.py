
"""StatDesk R4.9.5 — Anderson-Darling normality test.

Normal-distribution AD test with estimated mean and sample SD (n-1).
The AD statistic is computed with stable log-CDFs; the p-value uses
Minitab/Stephens piecewise approximations on the adjusted AD statistic.

The R4.9.5 change only refines the interpretation text in the report.
The numerical method from R4.9.1 is unchanged.
"""

from dataclasses import dataclass
from math import exp, fsum, isfinite, sqrt
from numbers import Real

import numpy as np
from scipy.special import log_ndtr


ENGINE_VERSION = "0.1.0"
MIN_N = 3


class AndersonDarlingError(ValueError):
    """Invalid measurements or non-computable AD result."""


@dataclass(frozen=True)
class AndersonDarlingResult:
    column_name: str
    n: int
    mean: float
    sample_stdev: float
    ad_statistic: float
    adjusted_ad_statistic: float
    p_value: float
    alpha: float
    reject_normality: bool
    warnings: tuple[str, ...]


def _normal_pvalue(ad_adjusted: float) -> float:
    """Minitab/Stephens approximation for fitted normal parameters."""
    if ad_adjusted < 0.200:
        p = -np.expm1(
            -13.436 + 101.14 * ad_adjusted - 223.73 * ad_adjusted ** 2
        )
    elif ad_adjusted < 0.340:
        p = -np.expm1(
            -8.318 + 42.796 * ad_adjusted - 59.938 * ad_adjusted ** 2
        )
    elif ad_adjusted < 0.600:
        p = exp(0.9177 - 4.279 * ad_adjusted - 1.38 * ad_adjusted ** 2)
    elif ad_adjusted < 13.0:
        p = exp(1.2937 - 5.709 * ad_adjusted + 0.0186 * ad_adjusted ** 2)
    else:
        return 0.0

    if not isfinite(p):
        raise AndersonDarlingError("P-value Anderson-Darling tidak finite.")

    return min(1.0, max(0.0, float(p)))


class AndersonDarlingEngine:
    @staticmethod
    def calculate_normal(values, column_name: str, alpha: float = 0.05):
        """Test normality of individual measurements, not subgroup means."""
        if not isinstance(column_name, str) or not column_name.strip():
            raise AndersonDarlingError("Nama characteristic tidak valid.")

        if (
            isinstance(alpha, bool)
            or not isinstance(alpha, Real)
            or not isfinite(float(alpha))
            or not 0.0 < float(alpha) < 1.0
        ):
            raise AndersonDarlingError("Alpha harus antara 0 dan 1.")

        if isinstance(values, (str, bytes)):
            raise AndersonDarlingError("Pengukuran harus berupa urutan angka.")

        try:
            iterator = iter(values)
        except TypeError as exc:
            raise AndersonDarlingError("Data tidak dapat dibaca.") from exc

        numbers = []

        for row, raw in enumerate(iterator, 1):
            if raw is None:
                raise AndersonDarlingError(f"Baris {row}: nilai kosong.")

            if isinstance(raw, bool) or not isinstance(raw, Real):
                raise AndersonDarlingError(f"Baris {row}: wajib Numeric.")

            try:
                number = float(raw)
            except (ValueError, TypeError, OverflowError) as exc:
                raise AndersonDarlingError(
                    f"Baris {row}: angka tidak dapat dikonversi."
                ) from exc

            if not isfinite(number):
                raise AndersonDarlingError(
                    f"Baris {row}: NaN/Infinity ditolak."
                )

            numbers.append(number)

        n = len(numbers)
        if n < MIN_N:
            raise AndersonDarlingError(
                f"Anderson-Darling membutuhkan minimal {MIN_N} pengukuran."
            )

        try:
            mean = fsum(numbers) / n
            sample_variance = (
                fsum((v - mean) ** 2 for v in numbers) / (n - 1)
            )
            std = sqrt(sample_variance)
        except (ValueError, OverflowError) as exc:
            raise AndersonDarlingError(
                "Perhitungan mean/SD melebihi rentang floating-point."
            ) from exc

        if not (isfinite(mean) and isfinite(std) and std > 0):
            raise AndersonDarlingError(
                "Anderson-Darling tidak dapat dihitung pada data tanpa variasi."
            )

        ordered = np.sort(np.asarray(numbers, dtype=np.float64))
        z = (ordered - mean) / std
        if not np.all(np.isfinite(z)):
            raise AndersonDarlingError("Standardisasi pengukuran tidak finite.")

        log_cdf = log_ndtr(z)
        log_survival_reversed = log_ndtr(-z[::-1])

        if not (
            np.all(np.isfinite(log_cdf))
            and np.all(np.isfinite(log_survival_reversed))
        ):
            raise AndersonDarlingError("Log-CDF normal tidak finite.")

        weights = np.arange(1, n + 1, dtype=np.float64) * 2.0 - 1.0
        terms = weights * (log_cdf + log_survival_reversed)
        ad = -n - fsum(float(term) for term in terms) / n

        if not isfinite(ad) or ad < -1e-9:
            raise AndersonDarlingError(
                "Statistik Anderson-Darling tidak valid."
            )

        ad = max(0.0, ad)
        adjusted = ad * (1.0 + 0.75 / n + 2.25 / (n * n))
        p_value = _normal_pvalue(adjusted)

        warnings = []
        if n < 8:
            warnings.append(
                "Sampel sangat kecil; interpretasikan p-value dengan hati-hati."
            )
        if len(set(numbers)) < n:
            warnings.append(
                "Ada nilai berulang (ties); resolusi/pembulatan "
                "pengukuran dapat memengaruhi uji normalitas."
            )
        if adjusted >= 13.0:
            warnings.append(
                "P-value lebih kecil dari rentang aproksimasi; "
                "gunakan pelaporan p < 0.001, bukan p = 0 secara harfiah."
            )

        return AndersonDarlingResult(
            column_name=column_name.strip(),
            n=n,
            mean=mean,
            sample_stdev=std,
            ad_statistic=ad,
            adjusted_ad_statistic=adjusted,
            p_value=p_value,
            alpha=float(alpha),
            reject_normality=p_value < alpha,
            warnings=tuple(warnings),
        )


def format_anderson_darling_report(result: AndersonDarlingResult) -> str:
    """Standalone AD Session Output with decision-consistent language."""
    if not isinstance(result, AndersonDarlingResult):
        raise AndersonDarlingError("Hasil Anderson-Darling tidak valid.")

    p_text = "< 0.001" if result.p_value < 0.001 else f"{result.p_value:.3f}"

    if result.reject_normality:
        interpretation = (
            "Reject H0: terdapat bukti statistik bahwa data "
            "tidak mengikuti distribusi normal."
        )
        caution = (
            "Hasil ini menolak asumsi normalitas pada alpha yang dipilih."
        )
    else:
        interpretation = (
            "Fail to reject H0: belum cukup bukti menolak normalitas."
        )
        caution = (
            "Tidak menolak H0 bukan bukti data pasti berdistribusi normal."
        )

    lines = [
        "ANDERSON-DARLING NORMALITY TEST — R4.9",
        "=" * 56,
        "",
        f"Characteristic      : {result.column_name}",
        f"Measurements (N)    : {result.n}",
        "Distribution        : Normal (mean & sample SD estimated)",
        f"Mean                : {result.mean:.3f}",
        f"Sample StDev        : {result.sample_stdev:.3f}",
        f"AD Statistic (A2)   : {result.ad_statistic:.3f}",
        f"Adjusted AD (A2*)   : {result.adjusted_ad_statistic:.3f}",
        f"P-Value             : {p_text}",
        f"Significance (alpha): {result.alpha:.3f}",
        "",
        f"Interpretation      : {interpretation}",
        caution,
        "A normality test does NOT establish process stability.",
    ]

    if result.warnings:
        lines.extend(["", "NOTES", "-" * 40])
        lines.extend(f"- {note}" for note in result.warnings)

    lines.extend(["", "END OF ANDERSON-DARLING REPORT"])
    return "\n".join(lines)
