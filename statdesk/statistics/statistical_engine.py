"""Pure statistics: independent of UI and worksheet persistence."""

from dataclasses import dataclass
from math import fsum, isfinite, sqrt
from statistics import median
from numbers import Real

import numpy as np
import scipy

from scipy import stats


ENGINE_VERSION = "0.4.0"


class StatisticalError(ValueError):
    pass


@dataclass(frozen=True)
class DescriptiveResult:
    column_name: str

    n_total: int
    n_valid: int
    n_missing: int

    mean: float
    median: float
    minimum: float
    maximum: float
    data_range: float

    sample_variance: float | None
    sample_std: float | None

    shapiro_w: float | None
    shapiro_p: float | None
    shapiro_note: str

    alpha: float


class StatisticalEngine:

    @staticmethod
    def describe(
        values,
        column_name: str,
        alpha: float = 0.05
    ) -> DescriptiveResult:

        # =====================================
        # 1. VALIDATE CONFIGURATION
        # =====================================

        if not column_name or not column_name.strip():
            raise StatisticalError(
                "Nama kolom tidak valid."
            )

        if (
            not isinstance(alpha, Real)
            or isinstance(alpha, bool)
            or not isfinite(float(alpha))
            or not 0 < alpha < 1
        ):
            raise StatisticalError(
                "Alpha harus berada di antara 0 dan 1."
            )

        # =====================================
        # 2. VALIDATE OBSERVATIONS
        # =====================================

        numbers = []
        n_total = 0
        n_missing = 0

        for row, value in enumerate(values, start=1):

            n_total += 1

            if value is None:
                n_missing += 1
                continue

            if (
                isinstance(value, bool)
                or not isinstance(value, Real)
            ):
                raise StatisticalError(
                    f"Baris {row}: kolom Numeric "
                    "mengandung data bukan angka."
                )

            value = float(value)

            if not isfinite(value):
                raise StatisticalError(
                    f"Baris {row}: NaN/Infinity "
                    "tidak diperbolehkan."
                )

            numbers.append(value)

        n = len(numbers)

        if n == 0:
            raise StatisticalError(
                "Tidak ada pengukuran valid "
                "pada kolom ini."
            )

        # =====================================
        # 3. DESCRIPTIVE STATISTICS
        # =====================================

        try:
            # fsum membantu mengurangi error
            # akumulasi saat menjumlahkan float
            mean = fsum(numbers) / n

            minimum = min(numbers)
            maximum = max(numbers)

            data_range = maximum - minimum

            # Varians sampel: denominator (n - 1)
            sample_variance = (
                fsum(
                    (x - mean) ** 2
                    for x in numbers
                ) / (n - 1)
                if n >= 2
                else None
            )

            sample_std = (
                sqrt(sample_variance)
                if sample_variance is not None
                else None
            )

            computed = [
                mean,
                data_range,
                *(
                    value
                    for value in (
                        sample_variance,
                        sample_std
                    )
                    if value is not None
                )
            ]

            if not all(
                isfinite(value)
                for value in computed
            ):
                raise StatisticalError(
                    "Hasil di luar rentang "
                    "floating-point; gunakan skala "
                    "pengukuran yang sesuai."
                )

        except (OverflowError, ValueError) as exc:

            if isinstance(exc, StatisticalError):
                raise

            raise StatisticalError(
                "Perhitungan melebihi rentang "
                "presisi floating-point."
            ) from exc

        # =====================================
        # 4. SHAPIRO-WILK NORMALITY TEST
        # =====================================

        shapiro_w = None
        shapiro_p = None

        if n < 3:
            note = (
                "Tidak dijalankan: perlu minimal "
                "3 pengukuran."
            )

        elif n > 5000:
            note = (
                "Tidak dijalankan: N > 5000 "
                "(akurasi p-value SciPy terbatas)."
            )

        elif minimum == maximum:
            note = (
                "Tidak dijalankan: semua nilai "
                "pengukuran sama."
            )

        else:
            try:
                test = stats.shapiro(
                    np.asarray(
                        numbers,
                        dtype=np.float64
                    )
                )

                shapiro_w = float(
                    test.statistic
                )

                shapiro_p = float(
                    test.pvalue
                )

            except (
                ValueError,
                FloatingPointError
            ) as exc:
                raise StatisticalError(
                    f"Shapiro-Wilk gagal: {exc}"
                ) from exc

            if not (
                isfinite(shapiro_w)
                and isfinite(shapiro_p)
            ):
                raise StatisticalError(
                    "Shapiro-Wilk mengembalikan "
                    "hasil non-finite."
                )

            note = (
                "p < alpha: terdapat bukti menolak "
                "asumsi normalitas."
                if shapiro_p < alpha
                else
                "p >= alpha: tidak cukup bukti "
                "menolak normalitas; bukan bukti "
                "data pasti normal."
            )

        # =====================================
        # 5. RETURN STRUCTURED RESULT
        # =====================================

        return DescriptiveResult(
            column_name=column_name,

            n_total=n_total,
            n_valid=n,
            n_missing=n_missing,

            mean=mean,
            median=float(median(numbers)),
            minimum=minimum,
            maximum=maximum,
            data_range=data_range,

            sample_variance=sample_variance,
            sample_std=sample_std,

            shapiro_w=shapiro_w,
            shapiro_p=shapiro_p,
            shapiro_note=note,

            alpha=float(alpha)
        )


def format_report(result: DescriptiveResult) -> str:

    def f(value):
        return (
            "N/A"
            if value is None
            else format(value, ".12g")
        )

    return "\n".join([
        "DESCRIPTIVE STATISTICS + SHAPIRO-WILK",
        "=" * 48,

        f"Column             : {result.column_name}",
        f"Total rows         : {result.n_total}",
        f"Valid measurements : {result.n_valid}",
        f"Missing values     : {result.n_missing}",

        f"Mean               : {f(result.mean)}",
        f"Median             : {f(result.median)}",
        f"Minimum            : {f(result.minimum)}",
        f"Maximum            : {f(result.maximum)}",
        f"Range              : {f(result.data_range)}",

        f"Sample Variance    : {f(result.sample_variance)}  (n-1)",
        f"Sample Std. Dev.   : {f(result.sample_std)}  (n-1)",

        "",

        f"Shapiro-Wilk (alpha = {f(result.alpha)})",
        f"W                  : {f(result.shapiro_w)}",
        f"p-value            : {f(result.shapiro_p)}",
        f"Interpretation     : {result.shapiro_note}",

        "",

        f"Engine {ENGINE_VERSION} | "
        f"NumPy {np.__version__} | "
        f"SciPy {scipy.__version__}",

        "Note: Results are exploratory until "
        "method validation/sign-off."
    ])