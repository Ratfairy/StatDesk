
"""StatDesk Xbar-R Control Chart — Phase I.

Equal-size rational subgroups, size 2..8.

Methods:
- Subgroup mean and range
- Rbar / d2 estimator for within-process sigma
- Three-sigma Xbar limits
- Three-sigma R limits
- Test 1: points strictly outside control limits

A2, D3 and D4 are derived from published d2/d3
constants rather than rounded A2/D3/D4 tables.

The published d2/d3 constants are themselves rounded.
Consequently this is not a claim of full internal
numerical equivalence with Minitab.

No GUI, plotting, or file-system dependencies.
"""

from dataclasses import dataclass
from math import fsum, isfinite, sqrt
from numbers import Real


VERSION = "0.6.2"

MIN_SUBGROUP_SIZE = 2
MAX_SUBGROUP_SIZE = 8

MIN_SUBGROUPS = 2
MAX_SUBGROUPS = 50_000


# ======================================================
# 1. PUBLISHED RANGE CONSTANTS
# ======================================================
#
# Source:
# Minitab support — Methods and formulas for R Chart,
# including unbiasing constants d2 and d3.
#
# Values are published approximations.
#
# n: (d2, d3)
#
# d2 = expected range of n independent N(0,1) values.
# d3 = standard deviation of that range.
#
# Do not round derived factors during calculation.
# ======================================================

RANGE_CONSTANTS = {
    2: (1.128, 0.8525),
    3: (1.693, 0.8884),
    4: (2.059, 0.8798),
    5: (2.326, 0.8641),
    6: (2.534, 0.8480),
    7: (2.704, 0.8332),
    8: (2.847, 0.8198),
}


def _calculate_factors(subgroup_size):
    """Derive A2, D3 and D4 from published d2/d3.

    A2 = 3 / (d2 * sqrt(n))
    D3 = max(0, 1 - 3*d3/d2)
    D4 = 1 + 3*d3/d2

    Returned factors are not rounded.
    """

    if subgroup_size not in RANGE_CONSTANTS:
        raise ValueError(
            "Ukuran subgrup harus 2 sampai 8."
        )

    d2, d3 = RANGE_CONSTANTS[subgroup_size]

    a2 = 3.0 / (d2 * sqrt(subgroup_size))

    range_multiplier = 3.0 * d3 / d2

    d3_factor = max(
        0.0,
        1.0 - range_multiplier
    )

    d4_factor = (
        1.0 + range_multiplier
    )

    return (
        a2,
        d3_factor,
        d4_factor,
    )


# Keep the original FACTORS interface for compatibility
# with any code that reads factors by subgroup size.
#
# The values now have more digits than the original
# rounded A2/D3/D4 lookup table.

FACTORS = {
    size: _calculate_factors(size)
    for size in RANGE_CONSTANTS
}


# ======================================================
# 2. EXCEPTIONS AND RESULT CONTRACT
# ======================================================

class XbarRError(ValueError):
    """Invalid subgroup input or numerical result."""


@dataclass(frozen=True)
class XbarRResult:

    subgroup_size: int
    subgroup_count: int

    means: tuple[float, ...]
    ranges: tuple[float, ...]

    xbar_cl: float
    xbar_ucl: float
    xbar_lcl: float

    r_cl: float
    r_ucl: float
    r_lcl: float

    mean_signals: tuple[int, ...]
    range_signals: tuple[int, ...]

    warnings: tuple[str, ...]


# ======================================================
# 3. XBAR-R STATISTICAL ENGINE
# ======================================================

class XbarREngine:

    @staticmethod
    def calculate(subgroups) -> XbarRResult:

        # =====================================
        # 1. VALIDATE SUBGROUP COLLECTION
        # =====================================

        if isinstance(subgroups, (str, bytes)):
            raise XbarRError(
                "Subgroups harus berbentuk "
                "baris-baris pengukuran."
            )

        try:
            groups = list(subgroups)

        except TypeError as exc:
            raise XbarRError(
                "Subgroups harus bisa diiterasi."
            ) from exc

        subgroup_count = len(groups)

        if subgroup_count < MIN_SUBGROUPS:
            raise XbarRError(
                "Diperlukan minimal 2 subgrup "
                "untuk analisis awal."
            )

        if subgroup_count > MAX_SUBGROUPS:
            raise XbarRError(
                "Maksimal 50.000 subgrup."
            )

        try:
            width = len(groups[0])

        except TypeError as exc:
            raise XbarRError(
                "Setiap subgrup harus berupa "
                "urutan angka."
            ) from exc

        if width not in RANGE_CONSTANTS:
            raise XbarRError(
                "Ukuran subgrup harus 2 sampai "
                "8 pengukuran."
            )

        # =====================================
        # 2. VALIDATE AND CALCULATE SUBGROUPS
        # =====================================

        means = []
        ranges = []

        for row_idx, group in enumerate(
            groups,
            start=1
        ):

            if (
                isinstance(group, (str, bytes))
                or not hasattr(group, "__len__")
                or len(group) != width
            ):
                raise XbarRError(
                    f"Subgrup {row_idx}: ukuran "
                    f"harus sama, yaitu {width}."
                )

            numbers = []

            for col_idx, raw in enumerate(
                group,
                start=1
            ):

                if (
                    isinstance(raw, bool)
                    or not isinstance(raw, Real)
                ):
                    raise XbarRError(
                        f"Subgrup {row_idx}, "
                        f"sampel {col_idx}: wajib "
                        "Numeric tanpa missing."
                    )

                try:
                    value = float(raw)

                except (
                    ValueError,
                    OverflowError
                ) as exc:
                    raise XbarRError(
                        f"Subgrup {row_idx}, "
                        f"sampel {col_idx}: "
                        "angka tidak valid."
                    ) from exc

                if not isfinite(value):
                    raise XbarRError(
                        f"Subgrup {row_idx}, "
                        f"sampel {col_idx}: "
                        "NaN/Infinity ditolak."
                    )

                numbers.append(value)

            # =================================
            # 3. MEAN AND RANGE
            # =================================

            try:
                subgroup_mean = (
                    fsum(numbers) / width
                )

                subgroup_range = (
                    max(numbers) - min(numbers)
                )

            except (
                ValueError,
                OverflowError
            ) as exc:
                raise XbarRError(
                    f"Subgrup {row_idx}: "
                    "perhitungan overflow."
                ) from exc

            if not (
                isfinite(subgroup_mean)
                and isfinite(subgroup_range)
            ):
                raise XbarRError(
                    f"Subgrup {row_idx}: "
                    "hasil non-finite."
                )

            means.append(subgroup_mean)
            ranges.append(subgroup_range)

        # =====================================
        # 4. GRAND MEAN AND AVERAGE RANGE
        # =====================================

        try:
            grand_mean = (
                fsum(means) / subgroup_count
            )

            rbar = (
                fsum(ranges) / subgroup_count
            )

        except (
            ValueError,
            OverflowError
        ) as exc:
            raise XbarRError(
                "Perhitungan grand mean atau "
                "average range overflow."
            ) from exc

        if not (
            isfinite(grand_mean)
            and isfinite(rbar)
        ):
            raise XbarRError(
                "Grand mean atau Rbar non-finite."
            )

        if rbar == 0.0:
            raise XbarRError(
                "Semua range nol; batas "
                "kendali tidak informatif."
            )

        # =====================================
        # 5. WITHIN SIGMA ESTIMATOR
        # =====================================
        #
        # sigma_within = Rbar / d2
        #
        # d2 is the published range constant
        # for the subgroup size.
        # =====================================

        d2, d3 = RANGE_CONSTANTS[width]

        try:
            sigma_within = rbar / d2

            # =================================
            # 6. XBAR CONTROL LIMITS
            # =================================
            #
            # UCL/LCL = grand_mean
            #           +/- 3 * sigma / sqrt(n)
            #
            # Equivalent to A2 * Rbar.
            # =================================

            xbar_margin = (
                3.0 * sigma_within / sqrt(width)
            )

            xbar_ucl = (
                grand_mean + xbar_margin
            )

            xbar_lcl = (
                grand_mean - xbar_margin
            )

            # =================================
            # 7. R CONTROL LIMITS
            # =================================
            #
            # Rbar * (1 +/- 3*d3/d2)
            #
            # Lower limit is truncated at zero.
            # =================================

            range_margin = (
                3.0 * d3 * sigma_within
            )

            r_ucl = (
                rbar + range_margin
            )

            r_lcl = max(
                0.0,
                rbar - range_margin
            )

        except (
            ValueError,
            OverflowError,
            ZeroDivisionError
        ) as exc:
            raise XbarRError(
                "Perhitungan batas kendali "
                "overflow."
            ) from exc

        # =====================================
        # 8. NUMERICAL VALIDATION
        # =====================================

        calculated = (
            grand_mean,
            rbar,
            sigma_within,
            xbar_margin,
            xbar_ucl,
            xbar_lcl,
            range_margin,
            r_ucl,
            r_lcl,
        )

        if not all(
            isfinite(value)
            for value in calculated
        ):
            raise XbarRError(
                "Hasil batas kendali non-finite."
            )

        if not (
            xbar_lcl < grand_mean < xbar_ucl
        ):
            raise XbarRError(
                "Presisi float tidak cukup "
                "untuk batas Xbar."
            )

        if not (
            0.0 <= r_lcl < rbar < r_ucl
        ):
            raise XbarRError(
                "Batas R Chart tidak valid "
                "atau presisi float tidak cukup."
            )

        # =====================================
        # 9. DETECT TEST 1 SIGNALS
        # =====================================
        #
        # Values exactly on UCL/LCL are
        # not considered Test 1 violations.
        # =====================================

        mean_signals = tuple(
            index
            for index, value in enumerate(
                means,
                start=1
            )
            if (
                value < xbar_lcl
                or value > xbar_ucl
            )
        )

        range_signals = tuple(
            index
            for index, value in enumerate(
                ranges,
                start=1
            )
            if (
                value < r_lcl
                or value > r_ucl
            )
        )

        # =====================================
        # 10. WARNINGS AND ASSUMPTIONS
        # =====================================

        warnings = (
            "Phase I; batas dihitung dari "
            "seluruh subgrup dan perlu "
            "disetujui QC/QA.",

            "Sigma within diestimasi dengan "
            "metode Rbar / d2.",

            "Konstanta d2/d3 berasal dari "
            "tabel publikasi yang dibulatkan; "
            "presisi internal Minitab belum "
            "dijamin identik.",

            "Hanya Test 1; belum membuktikan "
            "proses stabil.",

            "Pastikan setiap baris adalah "
            "rational subgroup sesuai "
            "urutan waktu.",
        )

        # =====================================
        # 11. RETURN IMMUTABLE RESULT
        # =====================================

        return XbarRResult(
            subgroup_size=width,
            subgroup_count=subgroup_count,

            means=tuple(means),
            ranges=tuple(ranges),

            xbar_cl=grand_mean,
            xbar_ucl=xbar_ucl,
            xbar_lcl=xbar_lcl,

            r_cl=rbar,
            r_ucl=r_ucl,
            r_lcl=r_lcl,

            mean_signals=mean_signals,
            range_signals=range_signals,

            warnings=warnings,
        )
