
"""StatDesk R4.1 — Normal Process Capability statistical engine.

No GUI, plotting, file I/O, or administrative approval workflow.

Data layout:
- individuals: chronological measurements, one observation per subgroup
- subgroups: equal-size rational subgroups, one subgroup per row

Within standard deviation:
- individuals: MRbar / d2(2) with moving-range span 2
- subgroups: pooled SD (default), Rbar / d2(n), or Sbar / c4(n)

Overall standard deviation: sample SD of all observations (N - 1).
The optional bias correction is applied separately to pooled/Sbar and
overall SD, following the corresponding Minitab estimation options.

The normality and statistical stability assumptions are NOT established
by the capability indices themselves. This version does not calculate confidence intervals or distribution
transformations. R4.7 adds normal-fitted Expected PPM (Within/Overall)
and two-sided Cpm. These results are model-based estimates, not observed
process defect rates or evidence of normality.
"""

from dataclasses import dataclass
from math import erfc, exp, fsum, hypot, isfinite, lgamma, log, sqrt
from numbers import Real

from statdesk.statistics.spc_number_format import format_spc_number
from statdesk.statistics.xbar_r_engine import RANGE_CONSTANTS


ENGINE_VERSION = "0.2.0"
REPORT_VERSION = "0.2.0"
MIN_INDIVIDUALS = 3
MIN_SUBGROUPS = 2
MAX_SUBGROUPS = 50_000
MAX_SUBGROUP_SIZE = 200
MAX_TOTAL_MEASUREMENTS = 1_000_000
VALID_SUBGROUP_METHODS = ("pooled", "rbar", "sbar")


class CapabilityError(ValueError):
    """Invalid data, specification, or numerical result."""


@dataclass(frozen=True)
class CapabilityResult:
    column_name: str
    layout: str
    values: tuple[float, ...]
    subgroup_count: int
    subgroup_size: int
    n: int

    lsl: float | None
    usl: float | None
    target: float | None

    mean: float
    sigma_within: float
    sigma_overall: float
    within_method: str
    within_statistic: float
    use_unbiasing_within: bool
    use_unbiasing_overall: bool
    c4_within: float | None
    c4_overall: float | None

    cp: float | None
    cpl: float | None
    cpu: float | None
    cpk: float
    pp: float | None
    ppl: float | None
    ppu: float | None
    ppk: float

    subgroup_means: tuple[float, ...]
    subgroup_ranges: tuple[float, ...]
    subgroup_stdevs: tuple[float, ...]

    observed_below: int
    observed_above: int
    observed_total: int
    observed_ppm: float

    # Normal-fitted performance, in parts per million (PPM).
    # None means that the corresponding specification limit is absent.
    expected_within_below_ppm: float | None
    expected_within_above_ppm: float | None
    expected_within_total_ppm: float
    expected_overall_below_ppm: float | None
    expected_overall_above_ppm: float | None
    expected_overall_total_ppm: float

    # Two-sided Cpm requires LSL, USL, and target.
    cpm: float | None
    warnings: tuple[str, ...]


# ======================================================
# 1. VALIDATION
# ======================================================

def _number(raw, name: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, Real):
        raise CapabilityError(
            f"{name} harus berupa angka Numeric."
        )

    try:
        value = float(raw)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CapabilityError(
            f"{name} tidak dapat dikonversi ke float."
        ) from exc

    if not isfinite(value):
        raise CapabilityError(
            f"{name} tidak boleh NaN atau Infinity."
        )

    return value


def _required_text(value, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CapabilityError(
            f"{name} tidak boleh kosong."
        )

    return value.strip()


def _optional_limit(raw, name: str) -> float | None:
    if raw is None:
        return None

    return _number(raw, name)


def _specifications(lsl, usl, target):
    lower = _optional_limit(lsl, "LSL")
    upper = _optional_limit(usl, "USL")
    goal = _optional_limit(target, "Target")

    if lower is None and upper is None:
        raise CapabilityError(
            "Isi minimal satu specification limit: LSL atau USL."
        )

    if (
        lower is not None
        and upper is not None
        and lower >= upper
    ):
        raise CapabilityError(
            "LSL harus lebih kecil daripada USL."
        )

    return lower, upper, goal


def _positive_finite(value: float, name: str) -> float:
    if not isfinite(value) or value <= 0.0:
        raise CapabilityError(
            f"{name} harus positif dan finite. "
            "Data tanpa variasi tidak mempunyai capability "
            "index yang informatif."
        )

    return value


# ======================================================
# 2. NUMERICAL HELPERS
# ======================================================

def _sample_mean(values) -> float:
    try:
        result = fsum(values) / len(values)

    except (
        OverflowError,
        ValueError,
        ZeroDivisionError,
    ) as exc:
        raise CapabilityError(
            "Gagal menghitung mean; periksa skala data."
        ) from exc

    if not isfinite(result):
        raise CapabilityError(
            "Mean di luar rentang floating-point."
        )

    return result


def _sample_sd(values, mean=None) -> float:
    n = len(values)

    if n < 2:
        raise CapabilityError(
            "Sample SD membutuhkan minimal dua pengukuran."
        )

    center = (
        _sample_mean(values)
        if mean is None
        else mean
    )

    try:
        variance = (
            fsum(
                (x - center) ** 2
                for x in values
            ) / (n - 1)
        )

        result = sqrt(variance)

    except (OverflowError, ValueError) as exc:
        raise CapabilityError(
            "Gagal menghitung sample SD; periksa skala data."
        ) from exc

    if not isfinite(result):
        raise CapabilityError(
            "Sample SD di luar rentang floating-point."
        )

    return result


def _c4(n: int) -> float:
    """
    Unbiasing constant:

    c4(n) = sqrt(2/(n-1))
            * Gamma(n/2) / Gamma((n-1)/2)
    """

    if type(n) is not int or n < 2:
        raise CapabilityError(
            "c4 membutuhkan n integer minimal 2."
        )

    try:
        result = exp(
            0.5 * log(2.0 / (n - 1))
            + lgamma(n / 2.0)
            - lgamma((n - 1) / 2.0)
        )

    except (ValueError, OverflowError) as exc:
        raise CapabilityError(
            "Gagal menghitung konstanta c4."
        ) from exc

    if not isfinite(result) or not 0 < result <= 1.0:
        raise CapabilityError(
            "Konstanta c4 tidak valid."
        )

    return result


def _ratio(
    numerator: float,
    denominator: float,
    label: str,
) -> float:

    if (
        not isfinite(numerator)
        or not isfinite(denominator)
        or denominator <= 0
    ):
        raise CapabilityError(
            f"{label}: input perhitungan tidak valid."
        )

    try:
        result = numerator / denominator

    except (
        OverflowError,
        ZeroDivisionError,
    ) as exc:
        raise CapabilityError(
            f"{label} tidak dapat dihitung."
        ) from exc

    if not isfinite(result):
        raise CapabilityError(
            f"{label} di luar rentang floating-point."
        )

    return result


# ======================================================
# 2B. NORMAL-FITTED PERFORMANCE (EXPECTED PPM)
# ======================================================

def _expected_ppm_below(
    limit: float | None,
    mean: float,
    sigma: float,
) -> float | None:
    """1e6 * Phi((LSL - mean) / sigma).

    erfc avoids subtracting a CDF value from 1 in the extreme tails.
    The return value is None only when no LSL is provided.
    """
    if limit is None:
        return None
    _positive_finite(sigma, "Sigma expected PPM")

    # 1 - Phi((mean-LSL)/sigma) = erfc(z/sqrt(2))/2.
    # Very extreme z scores naturally give PPM = 0 or 1,000,000.
    z = (mean - limit) / sigma
    result = 500_000.0 * erfc(z / sqrt(2.0))
    if not isfinite(result) or not 0.0 <= result <= 1_000_000.0:
        raise CapabilityError("Expected PPM below LSL tidak finite.")
    return result


def _expected_ppm_above(
    limit: float | None,
    mean: float,
    sigma: float,
) -> float | None:
    """1e6 * [1 - Phi((USL - mean) / sigma)]."""
    if limit is None:
        return None
    _positive_finite(sigma, "Sigma expected PPM")

    z = (limit - mean) / sigma
    result = 500_000.0 * erfc(z / sqrt(2.0))
    if not isfinite(result) or not 0.0 <= result <= 1_000_000.0:
        raise CapabilityError("Expected PPM above USL tidak finite.")
    return result


def _expected_ppm(
    lsl: float | None,
    usl: float | None,
    mean: float,
    sigma: float,
) -> tuple[float | None, float | None, float]:
    """Return below, above, and total expected PPM for a normal model."""
    below = _expected_ppm_below(lsl, mean, sigma)
    above = _expected_ppm_above(usl, mean, sigma)
    total = (below if below is not None else 0.0) + (
        above if above is not None else 0.0
    )
    if not isfinite(total) or total < 0.0 or total > 1_000_000.000001:
        raise CapabilityError("Total Expected PPM tidak valid.")
    return below, above, min(total, 1_000_000.0)


# ======================================================
# 3. CALCULATE CAPABILITY INDICES
# ======================================================

def _build_result(
    *,
    column_name,
    layout,
    values,
    subgroup_count,
    subgroup_size,
    lsl,
    usl,
    target,
    mean,
    sigma_within,
    sigma_overall,
    within_method,
    within_statistic,
    use_unbiasing_within,
    use_unbiasing_overall,
    c4_within,
    c4_overall,
    subgroup_means,
    subgroup_ranges,
    subgroup_stdevs,
):

    _positive_finite(
        sigma_within,
        "Within sigma",
    )

    _positive_finite(
        sigma_overall,
        "Overall sigma",
    )

    # --------------------------------------
    # A. POTENTIAL CAPABILITY
    # --------------------------------------

    cp = (
        _ratio(
            usl - lsl,
            6.0 * sigma_within,
            "Cp",
        )
        if lsl is not None and usl is not None
        else None
    )

    cpl = (
        _ratio(
            mean - lsl,
            3.0 * sigma_within,
            "CPL",
        )
        if lsl is not None
        else None
    )

    cpu = (
        _ratio(
            usl - mean,
            3.0 * sigma_within,
            "CPU",
        )
        if usl is not None
        else None
    )

    cpk = min(
        value
        for value in (cpl, cpu)
        if value is not None
    )

    # --------------------------------------
    # B. OVERALL CAPABILITY
    # --------------------------------------

    pp = (
        _ratio(
            usl - lsl,
            6.0 * sigma_overall,
            "Pp",
        )
        if lsl is not None and usl is not None
        else None
    )

    ppl = (
        _ratio(
            mean - lsl,
            3.0 * sigma_overall,
            "PPL",
        )
        if lsl is not None
        else None
    )

    ppu = (
        _ratio(
            usl - mean,
            3.0 * sigma_overall,
            "PPU",
        )
        if usl is not None
        else None
    )

    ppk = min(
        value
        for value in (ppl, ppu)
        if value is not None
    )

    # --------------------------------------
    # C. OBSERVED PERFORMANCE
    # --------------------------------------

    below = (
        sum(value < lsl for value in values)
        if lsl is not None
        else 0
    )

    above = (
        sum(value > usl for value in values)
        if usl is not None
        else 0
    )

    observed_total = below + above

    observed_ppm = _ratio(
        observed_total * 1_000_000.0,
        float(len(values)),
        "Observed PPM",
    )

    # --------------------------------------
    # D. NORMAL-FITTED EXPECTED PERFORMANCE
    # --------------------------------------

    (
        expected_within_below,
        expected_within_above,
        expected_within_total,
    ) = _expected_ppm(lsl, usl, mean, sigma_within)

    (
        expected_overall_below,
        expected_overall_above,
        expected_overall_total,
    ) = _expected_ppm(lsl, usl, mean, sigma_overall)

    # --------------------------------------
    # E. Cpm (TAGUCHI CAPABILITY INDEX)
    # --------------------------------------

    # Two-sided definition:
    # Cpm = (USL-LSL) / (6*sqrt(sigma_overall^2 + (mean-target)^2))
    # Target is not inferred from the midpoint of specifications.
    # One-sided Minitab Cpm variants are intentionally not implemented.
    cpm = None
    if lsl is not None and usl is not None and target is not None:
        adjusted_sigma = hypot(sigma_overall, mean - target)
        cpm = _ratio(usl - lsl, 6.0 * adjusted_sigma, "Cpm")

    # --------------------------------------
    # F. STATISTICAL WARNINGS
    # --------------------------------------

    warnings = [
        (
            "Capability Normal mengasumsikan distribusi normal; "
            "normalitas belum diuji oleh engine ini."
        ),
        (
            "Verifikasi kestabilan proses dengan control chart "
            "sebelum menginterpretasikan capability sebagai "
            "kinerja proses."
        ),
        (
            "Control limits (SPC) berbeda dari "
            "specification limits (LSL/USL)."
        ),
        (
            "Observed PPM dihitung dari sampel, sedangkan Expected PPM "
            "berdasarkan model normal dan estimator sigma yang dipilih."
        ),
        (
            "Expected Within/Overall PPM dan Cpm tidak membuktikan "
            "normalitas data atau kestabilan proses."
        ),
    ]

    if layout == "subgroups":
        warnings.append(
            "Setiap subgroup harus berisi pengukuran sejenis "
            "dan merepresentasikan rational subgroup yang benar."
        )

    else:
        warnings.append(
            "Individuals harus berurutan secara waktu; "
            "MR(2) menggunakan dua observasi bertetangga."
        )

    if lsl is None or usl is None:
        warnings.append(
            "Hanya satu specification limit: Cp dan Pp tidak "
            "didefinisikan. Cpk/Ppk mengikuti sisi yang tersedia."
        )

    if target is not None and (lsl is None or usl is None):
        warnings.append(
            "Cpm belum dihitung untuk specification limit satu sisi "
            "pada versi ini."
        )

    if target is not None and (
        (lsl is not None and target < lsl)
        or (usl is not None and target > usl)
    ):
        warnings.append(
            "Target berada di luar specification limit."
        )

    if within_method == "rbar":
        warnings.append(
            "Konstanta d2 menggunakan nilai tabel yang "
            "dibulatkan; presisi internal Minitab "
            "dapat sedikit berbeda."
        )

    # --------------------------------------
    # E. RESULT
    # --------------------------------------

    return CapabilityResult(
        column_name=column_name,
        layout=layout,
        values=values,
        subgroup_count=subgroup_count,
        subgroup_size=subgroup_size,
        n=len(values),

        lsl=lsl,
        usl=usl,
        target=target,

        mean=mean,
        sigma_within=sigma_within,
        sigma_overall=sigma_overall,
        within_method=within_method,
        within_statistic=within_statistic,
        use_unbiasing_within=use_unbiasing_within,
        use_unbiasing_overall=use_unbiasing_overall,
        c4_within=c4_within,
        c4_overall=c4_overall,

        cp=cp,
        cpl=cpl,
        cpu=cpu,
        cpk=cpk,

        pp=pp,
        ppl=ppl,
        ppu=ppu,
        ppk=ppk,

        subgroup_means=subgroup_means,
        subgroup_ranges=subgroup_ranges,
        subgroup_stdevs=subgroup_stdevs,

        observed_below=below,
        observed_above=above,
        observed_total=observed_total,
        observed_ppm=observed_ppm,

        expected_within_below_ppm=expected_within_below,
        expected_within_above_ppm=expected_within_above,
        expected_within_total_ppm=expected_within_total,
        expected_overall_below_ppm=expected_overall_below,
        expected_overall_above_ppm=expected_overall_above,
        expected_overall_total_ppm=expected_overall_total,
        cpm=cpm,

        warnings=tuple(warnings),
    )


# ======================================================
# 4. PUBLIC CAPABILITY ENGINE
# ======================================================

class CapabilityEngine:

    # --------------------------------------
    # A. INDIVIDUAL MEASUREMENTS
    # --------------------------------------

    @staticmethod
    def calculate_individuals(
        values,
        column_name: str,
        *,
        lsl=None,
        usl=None,
        target=None,
        use_unbiasing_overall=False,
    ) -> CapabilityResult:

        """
        Normal capability for time-ordered individuals.

        Within sigma = MRbar / d2(2)
        Overall sigma = sample SD (N-1)
        """

        name = _required_text(
            column_name,
            "Nama kolom",
        )

        lower, upper, goal = _specifications(
            lsl,
            usl,
            target,
        )

        if type(use_unbiasing_overall) is not bool:
            raise CapabilityError(
                "use_unbiasing_overall harus True/False."
            )

        if isinstance(values, (str, bytes)):
            raise CapabilityError(
                "Individuals harus berupa deretan angka."
            )

        try:
            raw = tuple(values)

        except TypeError as exc:
            raise CapabilityError(
                "Individuals harus iterable."
            ) from exc

        if not (
            MIN_INDIVIDUALS
            <= len(raw)
            <= MAX_TOTAL_MEASUREMENTS
        ):
            raise CapabilityError(
                f"Individuals membutuhkan {MIN_INDIVIDUALS} "
                f"sampai {MAX_TOTAL_MEASUREMENTS} pengukuran."
            )

        data = tuple(
            _number(
                value,
                f"Pengukuran {i}",
            )
            for i, value in enumerate(
                raw,
                start=1,
            )
        )

        mean = _sample_mean(data)

        overall_s = _sample_sd(
            data,
            mean,
        )

        c4_overall = (
            _c4(len(data))
            if use_unbiasing_overall
            else None
        )

        sigma_overall = (
            overall_s / c4_overall
            if c4_overall is not None
            else overall_s
        )

        # MR span = 2
        try:
            moving_ranges = tuple(
                abs(data[i] - data[i - 1])
                for i in range(1, len(data))
            )

            mrbar = (
                fsum(moving_ranges)
                / len(moving_ranges)
            )

            sigma_within = (
                mrbar / RANGE_CONSTANTS[2][0]
            )

        except (
            ValueError,
            OverflowError,
        ) as exc:
            raise CapabilityError(
                "Gagal menghitung moving ranges."
            ) from exc

        return _build_result(
            column_name=name,
            layout="individuals",
            values=data,
            subgroup_count=len(data),
            subgroup_size=1,

            lsl=lower,
            usl=upper,
            target=goal,

            mean=mean,
            sigma_within=sigma_within,
            sigma_overall=sigma_overall,

            within_method="mrbar",
            within_statistic=mrbar,

            use_unbiasing_within=True,
            use_unbiasing_overall=use_unbiasing_overall,

            c4_within=None,
            c4_overall=c4_overall,

            subgroup_means=data,
            subgroup_ranges=(),
            subgroup_stdevs=(),
        )

    # --------------------------------------
    # B. RATIONAL SUBGROUPS
    # --------------------------------------

    @staticmethod
    def calculate_subgroups(
        subgroups,
        column_name: str,
        *,
        lsl=None,
        usl=None,
        target=None,
        within_method="pooled",
        use_unbiasing_within=True,
        use_unbiasing_overall=False,
    ) -> CapabilityResult:

        """
        Normal capability for equal-size rational subgroups.

        Methods:
          pooled : Sp / c4(df + 1), if corrected
          rbar   : Rbar / d2(n)
          sbar   : Sbar / c4(n), if corrected
        """

        name = _required_text(
            column_name,
            "Nama kolom",
        )

        lower, upper, goal = _specifications(
            lsl,
            usl,
            target,
        )

        if within_method not in VALID_SUBGROUP_METHODS:
            raise CapabilityError(
                "within_method harus 'pooled', "
                "'rbar', atau 'sbar'."
            )

        if (
            type(use_unbiasing_within) is not bool
            or type(use_unbiasing_overall) is not bool
        ):
            raise CapabilityError(
                "Pilihan unbiasing harus True/False."
            )

        if isinstance(subgroups, (str, bytes)):
            raise CapabilityError(
                "Subgroups harus berisi deretan "
                "baris pengukuran."
            )

        try:
            raw_groups = tuple(subgroups)

        except TypeError as exc:
            raise CapabilityError(
                "Subgroups harus iterable."
            ) from exc

        if not (
            MIN_SUBGROUPS
            <= len(raw_groups)
            <= MAX_SUBGROUPS
        ):
            raise CapabilityError(
                f"Subgroups membutuhkan {MIN_SUBGROUPS} "
                f"sampai {MAX_SUBGROUPS} baris."
            )

        # ----------------------------------
        # PREPARE SUBGROUP DATA
        # ----------------------------------

        prepared = []
        size = None

        for i, group in enumerate(
            raw_groups,
            start=1,
        ):

            if isinstance(group, (str, bytes)):
                raise CapabilityError(
                    f"Subgroup {i} bukan deretan pengukuran."
                )

            try:
                row = tuple(group)

            except TypeError as exc:
                raise CapabilityError(
                    f"Subgroup {i} tidak iterable."
                ) from exc

            if size is None:
                size = len(row)

                if not 2 <= size <= MAX_SUBGROUP_SIZE:
                    raise CapabilityError(
                        "Subgroup size harus 2 sampai "
                        f"{MAX_SUBGROUP_SIZE}."
                    )

                if (
                    len(raw_groups) * size
                    > MAX_TOTAL_MEASUREMENTS
                ):
                    raise CapabilityError(
                        "Total pengukuran melebihi batas engine."
                    )

            if len(row) != size:
                raise CapabilityError(
                    f"Subgroup {i} harus memiliki "
                    f"{size} pengukuran."
                )

            prepared.append(
                tuple(
                    _number(
                        value,
                        f"Subgroup {i}, pengukuran {j}",
                    )
                    for j, value in enumerate(
                        row,
                        start=1,
                    )
                )
            )

        # ----------------------------------
        # VALIDATE ESTIMATION METHOD
        # ----------------------------------

        if (
            within_method == "rbar"
            and not use_unbiasing_within
        ):
            raise CapabilityError(
                "Rbar selalu menggunakan d2(n). "
                "Pilihan tanpa unbiasing tidak berlaku "
                "untuk metode Rbar."
            )

        if (
            within_method == "rbar"
            and size not in RANGE_CONSTANTS
        ):
            raise CapabilityError(
                "Metode Rbar tersedia untuk subgroup "
                "size 2–8 sesuai tabel d2 engine SPC "
                "saat ini."
            )

        # ----------------------------------
        # SUBGROUP STATISTICS
        # ----------------------------------

        means = tuple(
            _sample_mean(row)
            for row in prepared
        )

        sds = tuple(
            _sample_sd(row, center)
            for row, center in zip(
                prepared,
                means,
            )
        )

        ranges = tuple(
            max(row) - min(row)
            for row in prepared
        )

        data = tuple(
            value
            for row in prepared
            for value in row
        )

        mean = _sample_mean(data)

        # ----------------------------------
        # OVERALL SIGMA
        # ----------------------------------

        overall_s = _sample_sd(
            data,
            mean,
        )

        c4_overall = (
            _c4(len(data))
            if use_unbiasing_overall
            else None
        )

        sigma_overall = (
            overall_s / c4_overall
            if c4_overall is not None
            else overall_s
        )

        # ----------------------------------
        # WITHIN SIGMA
        # ----------------------------------

        c4_within = None

        if within_method == "rbar":

            statistic = _sample_mean(
                ranges
            )

            sigma_within = (
                statistic
                / RANGE_CONSTANTS[size][0]
            )

        elif within_method == "sbar":

            statistic = _sample_mean(
                sds
            )

            c4_within = (
                _c4(size)
                if use_unbiasing_within
                else None
            )

            sigma_within = (
                statistic / c4_within
                if c4_within is not None
                else statistic
            )

        else:
            # Pooled SD for equal subgroup sizes.
            # Degrees of freedom = m * (n-1).

            df = (
                len(prepared) * (size - 1)
            )

            try:
                statistic = sqrt(
                    fsum(
                        (size - 1) * sd ** 2
                        for sd in sds
                    ) / df
                )

            except (
                OverflowError,
                ValueError,
            ) as exc:
                raise CapabilityError(
                    "Pooled SD tidak dapat dihitung."
                ) from exc

            c4_within = (
                _c4(df + 1)
                if use_unbiasing_within
                else None
            )

            sigma_within = (
                statistic / c4_within
                if c4_within is not None
                else statistic
            )

        # ----------------------------------
        # RESULT
        # ----------------------------------

        return _build_result(
            column_name=name,
            layout="subgroups",
            values=data,
            subgroup_count=len(prepared),
            subgroup_size=size,

            lsl=lower,
            usl=upper,
            target=goal,

            mean=mean,
            sigma_within=sigma_within,
            sigma_overall=sigma_overall,

            within_method=within_method,
            within_statistic=statistic,

            use_unbiasing_within=(
                use_unbiasing_within
                if within_method != "rbar"
                else True
            ),
            use_unbiasing_overall=use_unbiasing_overall,

            c4_within=c4_within,
            c4_overall=c4_overall,

            subgroup_means=means,
            subgroup_ranges=ranges,
            subgroup_stdevs=sds,
        )


def _fmt_expected_ppm(value: float | None) -> str:
    """Two decimal places to compare with standard Minitab PPM reports."""
    return "N/A" if value is None else f"{value:.2f}"


# ======================================================
# 5. SESSION OUTPUT
# ======================================================

def format_capability_report(
    result: CapabilityResult,
) -> str:

    """Generate Normal Capability Session Output."""

    if not isinstance(result, CapabilityResult):
        raise CapabilityError(
            "Result harus berupa CapabilityResult."
        )

    def f(value):
        return (
            "N/A"
            if value is None
            else format_spc_number(value)
        )

    layout_label = (
        "Individuals (time ordered)"
        if result.layout == "individuals"
        else "Rational subgroups (one row per subgroup)"
    )

    within_label = {
        "mrbar": "MRbar / d2(2)",
        "rbar": "Rbar / d2(n)",
        "sbar": (
            "Sbar / c4(n)"
            if result.use_unbiasing_within
            else "Sbar"
        ),
        "pooled": (
            "Pooled SD / c4(df + 1)"
            if result.use_unbiasing_within
            else "Pooled SD"
        ),
    }[result.within_method]

    lines = [
        "NORMAL PROCESS CAPABILITY — R4.7",
        "=" * 58,
        "",

        "DATA INFORMATION",
        "-" * 40,
        f"Column              : {result.column_name}",
        f"Layout              : {layout_label}",
        f"Subgroups           : {result.subgroup_count}",
        f"Subgroup size       : {result.subgroup_size}",
        f"Measurements (N)    : {result.n}",
        "",

        "SPECIFICATION LIMITS",
        "-" * 40,
        f"LSL                 : {f(result.lsl)}",
        f"USL                 : {f(result.usl)}",
        f"Target              : {f(result.target)}",
        "",

        "ESTIMATION METHODS",
        "-" * 40,
        f"Within Sigma method : {within_label}",
        "Overall Sigma       : Sample SD (N - 1)"
        + (
            " / c4(N)"
            if result.use_unbiasing_overall
            else ""
        ),
        f"Within raw statistic: {f(result.within_statistic)}",
        f"c4 (within)         : {f(result.c4_within)}",
        f"c4 (overall)        : {f(result.c4_overall)}",
        "",

        "PROCESS ESTIMATES",
        "-" * 40,
        f"Process Mean        : {f(result.mean)}",
        f"StDev (Within)      : {f(result.sigma_within)}",
        f"StDev (Overall)     : {f(result.sigma_overall)}",
        "",

        "POTENTIAL CAPABILITY — WITHIN",
        "-" * 40,
        f"Cp                  : {f(result.cp)}",
        f"CPL                 : {f(result.cpl)}",
        f"CPU                 : {f(result.cpu)}",
        f"Cpk                 : {f(result.cpk)}",
        "",

        "OVERALL CAPABILITY",
        "-" * 40,
        f"Pp                  : {f(result.pp)}",
        f"PPL                 : {f(result.ppl)}",
        f"PPU                 : {f(result.ppu)}",
        f"Ppk                 : {f(result.ppk)}",
        f"Cpm (two-sided)     : {f(result.cpm)}",
        "",

        "OBSERVED PERFORMANCE (SAMPLE)",
        "-" * 40,    
        f"Below LSL           : {'N/A' if result.lsl is None else result.observed_below}",
        f"Above USL           : {'N/A' if result.usl is None else result.observed_above}",
        f"Total out of spec   : {result.observed_total}",
        f"Observed PPM        : {f(result.observed_ppm)}",
        "",

        "EXPECTED PERFORMANCE — NORMAL MODEL (PPM)",
        "-" * 58,
        "                       Within          Overall",
        "PPM Below LSL       : "
        f"{_fmt_expected_ppm(result.expected_within_below_ppm):>12} "
        f"{_fmt_expected_ppm(result.expected_overall_below_ppm):>16}",
        "PPM Above USL       : "
        f"{_fmt_expected_ppm(result.expected_within_above_ppm):>12} "
        f"{_fmt_expected_ppm(result.expected_overall_above_ppm):>16}",
        "PPM Total           : "
        f"{_fmt_expected_ppm(result.expected_within_total_ppm):>12} "
        f"{_fmt_expected_ppm(result.expected_overall_total_ppm):>16}",
        "",

        "WARNINGS & ASSUMPTIONS",
        "-" * 40,
        *(
            f"- {warning}"
            for warning in result.warnings
        ),
        "",

        "STATDESK REPORT INFORMATION",
        "-" * 40,
        f"Engine version      : {ENGINE_VERSION}",
        f"Report version      : {REPORT_VERSION}",
        "",

        "END OF NORMAL CAPABILITY REPORT",
    ]

    return "\n".join(lines)
