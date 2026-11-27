
"""StatDesk R4.9.5 — Sixpack UI refinement + Anderson-Darling.

Creates six panels:
    1. Individuals / Xbar chart (Phase I)
    2. Capability histogram with fitted Within / Overall normal densities
    3. MR / R / S chart (Phase I)
    4. Normal Q-Q plot and Anderson-Darling normality statistics
    5. Last 25 observations / rational subgroups
    6. Capability plot with 6-sigma Within / Overall intervals

SPC limits come from the existing StatDesk SPC engines (not recalculated
here). Capability indices and sigma estimates come from CapabilityResult.
SPC chart limits and capability sigma may use different estimators.
The AD statistic/p-value are calculated by AndersonDarlingEngine, not here.

This version accepts subgroup sizes 1, 2–8 and 9–25, matching the
existing SPC engines. A separate capability-only analysis supports
larger subgroups; this Sixpack intentionally does not claim to.
"""

from math import ceil, isfinite, log2, pi, sqrt

import numpy as np
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator
from scipy import stats

from statdesk.statistics.capability_engine import CapabilityResult
from statdesk.statistics.anderson_darling_engine import (
    AndersonDarlingEngine,
    AndersonDarlingError,
    AndersonDarlingResult,
)
from statdesk.statistics.spc_engine import SpcEngine, SpcError
from statdesk.statistics.xbar_r_engine import XbarREngine, XbarRError
from statdesk.statistics.xbar_s_engine import XbarSEngine, XbarSError


COLOR_TEXT = "#334155"
COLOR_MUTED = "#64748b"
COLOR_GRID = "#e2e8f0"
COLOR_BLUE = "#2563eb"
COLOR_ORANGE = "#ea580c"
COLOR_SPEC = "#dc2626"
COLOR_CENTER = "#059669"
COLOR_HIST = "#b3d4f5"


class CapabilitySixpackError(ValueError):
    """Unsupported or inconsistent data for Normal Capability Sixpack."""


def _fmt(value):
    return "N/A" if value is None else f"{value:.3f}"


def _check_result(result):
    if not isinstance(result, CapabilityResult):
        raise CapabilitySixpackError(
            "Sixpack membutuhkan CapabilityResult dari CapabilityEngine."
        )
    if result.n != len(result.values) or result.n < 3:
        raise CapabilitySixpackError("Jumlah pengukuran tidak konsisten.")
    if result.subgroup_size not in range(1, 26):
        raise CapabilitySixpackError(
            "Sixpack R4.9 mendukung subgroup size 1–25. "
            "Ukuran lebih besar belum didukung engine SPC yang tersedia."
        )
    if result.subgroup_size * result.subgroup_count != result.n:
        raise CapabilitySixpackError("Subgroup count/size tidak konsisten.")
    if result.layout == "individuals" and result.subgroup_size != 1:
        raise CapabilitySixpackError("Individuals harus subgroup size 1.")
    if result.layout == "subgroups" and result.subgroup_size == 1:
        raise CapabilitySixpackError("Subgroups membutuhkan size >= 2.")
    if result.layout not in ("individuals", "subgroups"):
        raise CapabilitySixpackError("Data layout tidak dikenal.")

    try:
        values = np.asarray(result.values, dtype=np.float64)
    except (ValueError, TypeError, OverflowError) as exc:
        raise CapabilitySixpackError("Data pengukuran tidak valid.") from exc
    if values.ndim != 1 or not np.all(np.isfinite(values)):
        raise CapabilitySixpackError("Data harus berupa angka finite.")
    if not (
        isfinite(result.mean)
        and isfinite(result.sigma_within)
        and isfinite(result.sigma_overall)
    ):
        raise CapabilitySixpackError("Estimasi proses tidak finite.")
    if result.sigma_within <= 0 or result.sigma_overall <= 0:
        raise CapabilitySixpackError("Standard deviation harus positif.")
    if result.lsl is None and result.usl is None:
        raise CapabilitySixpackError("LSL atau USL harus tersedia.")
    if (
        result.lsl is not None
        and result.usl is not None
        and result.lsl >= result.usl
    ):
        raise CapabilitySixpackError("LSL harus lebih kecil daripada USL.")
    return values


def _spc_series(result, values):
    """Get chart points, limits and Test 1 positions from existing engines."""
    n = result.subgroup_size

    if n == 1:
        spc = SpcEngine.calculate_imr(
            tuple(float(v) for v in values),
            result.column_name
        )
        return (
            (
                "Individuals Chart",
                np.arange(1, result.n + 1),
                values,
                spc.i_lcl,
                spc.i_center,
                spc.i_ucl,
                spc.i_violations,
            ),
            (
                "Moving Range Chart",
                np.arange(2, result.n + 1),
                np.asarray(spc.moving_ranges),
                spc.mr_lcl,
                spc.mr_center,
                spc.mr_ucl,
                spc.mr_violations,
            ),
        )

    groups = values.reshape(result.subgroup_count, n)
    subgroups = tuple(tuple(float(x) for x in group) for group in groups)

    if n <= 8:
        spc = XbarREngine.calculate(subgroups)
        return (
            (
                "Xbar Chart",
                np.arange(1, result.subgroup_count + 1),
                np.asarray(spc.means),
                spc.xbar_lcl,
                spc.xbar_cl,
                spc.xbar_ucl,
                spc.mean_signals,
            ),
            (
                "R Chart",
                np.arange(1, result.subgroup_count + 1),
                np.asarray(spc.ranges),
                spc.r_lcl,
                spc.r_cl,
                spc.r_ucl,
                spc.range_signals,
            ),
        )

    spc = XbarSEngine.calculate(subgroups)
    return (
        (
            "Xbar Chart",
            np.arange(1, result.subgroup_count + 1),
            np.asarray(spc.subgroup_means),
            spc.xbar_lcl,
            spc.xbar_center,
            spc.xbar_ucl,
            spc.xbar_signals,
        ),
        (
            "S Chart",
            np.arange(1, result.subgroup_count + 1),
            np.asarray(spc.subgroup_stdevs),
            spc.s_lcl,
            spc.s_center,
            spc.s_ucl,
            spc.s_signals,
        ),
    )


def _style(ax):
    ax.set_facecolor("white")
    ax.set_axisbelow(True)
    ax.grid(axis="y", color=COLOR_GRID, linewidth=0.7)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["bottom"].set_color("#94a3b8")
    ax.spines["left"].set_color("#94a3b8")
    ax.tick_params(labelsize=8, colors=COLOR_TEXT)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=5))
    ax.title.set_color("#0f172a")


def _control_chart(ax, bundle):
    title, xx, yy, lcl, cl, ucl, signals = bundle
    _style(ax)

    ax.set_title(
        title,
        fontsize=11,
        fontweight="semibold",
        loc="left",
        pad=25
    )

    ax.plot(
        xx, yy,
        color=COLOR_BLUE,
        marker="o",
        markersize=3.5,
        linewidth=1.35
    )

    ax.axhline(
        cl,
        color=COLOR_CENTER,
        linewidth=1.2,
        label=f"CL {_fmt(cl)}"
    )
    ax.axhline(
        ucl,
        color=COLOR_SPEC,
        linestyle="--",
        linewidth=1.1,
        label=f"UCL {_fmt(ucl)}"
    )
    ax.axhline(
        lcl,
        color=COLOR_SPEC,
        linestyle="--",
        linewidth=1.1,
        label=f"LCL {_fmt(lcl)}"
    )

    signals = set(signals)
    if signals:
        match = np.array(
            [int(x) in signals for x in xx],
            dtype=bool
        )
        ax.scatter(
            xx[match],
            yy[match],
            s=45,
            color=COLOR_SPEC,
            zorder=7,
            label="Test 1 signal"
        )

    ax.set_xlabel(
        "Observation" if title.startswith(("Individuals", "Moving"))
        else "Subgroup",
        fontsize=8.5,
        color=COLOR_MUTED
    )

    # R4.9.5 — legend berada di luar area plot.
    handles, labels = ax.get_legend_handles_labels()

    ax.legend(
        handles,
        labels,
        loc="upper right",
        bbox_to_anchor=(1.0, 1.16),
        ncol=len(labels),
        fontsize=7.0,
        frameon=False,
        handlelength=1.35,
        handletextpad=0.35,
        columnspacing=0.85,
        borderaxespad=0.0,
    )


def _histogram(ax, result, values):
    _style(ax)
    ax.set_title(
        "Capability Histogram",
        fontsize=11,
        fontweight="semibold",
        loc="left",
        pad=8
    )

    bins = max(5, min(40, ceil(1 + log2(result.n))))

    ax.hist(
        values,
        bins=bins,
        density=True,
        color=COLOR_HIST,
        edgecolor="white",
        linewidth=0.7,
        alpha=0.92
    )

    extent = [float(values.min()), float(values.max())]

    for sigma in (result.sigma_within, result.sigma_overall):
        extent.extend([
            result.mean - 4.5 * sigma,
            result.mean + 4.5 * sigma
        ])

    extent.extend(
        float(v)
        for v in (result.lsl, result.usl)
        if v is not None
    )

    span = max(extent) - min(extent)
    if not isfinite(span) or span <= 0:
        raise CapabilitySixpackError("Rentang histogram tidak valid.")

    xx = np.linspace(
        min(extent) - .04 * span,
        max(extent) + .04 * span,
        600
    )

    for sigma, color, name, style in (
        (result.sigma_within, COLOR_BLUE, "Within", "-"),
        (result.sigma_overall, COLOR_ORANGE, "Overall", "--"),
    ):
        yy = np.exp(-0.5 * ((xx - result.mean) / sigma) ** 2)
        yy = yy / (sigma * sqrt(2.0 * pi))
        ax.plot(
            xx, yy,
            color=color,
            ls=style,
            linewidth=1.8,
            label=name
        )

    for lim, name in ((result.lsl, "LSL"), (result.usl, "USL")):
        if lim is not None:
            ax.axvline(
                lim,
                color=COLOR_SPEC,
                linestyle="-.",
                linewidth=1.3,
                label=name
            )

    ax.set_xlabel(result.column_name, fontsize=8.5, color=COLOR_MUTED)
    ax.set_ylabel("Density", fontsize=8.5, color=COLOR_MUTED)
    ax.legend(
        fontsize=7.3,
        ncol=2,
        frameon=False,
        loc="upper right"
    )


def _qq(ax, values, ad_result: AndersonDarlingResult):
    """Show normal Q-Q plot with Anderson-Darling results."""
    _style(ax)
    ax.set_title(
        "Normal Q-Q Plot",
        fontsize=11,
        fontweight="semibold",
        loc="left",
        pad=8
    )

    (theoretical, ordered), (slope, intercept, _) = stats.probplot(
        values, dist="norm"
    )

    ax.scatter(
        theoretical,
        ordered,
        color=COLOR_BLUE,
        s=15,
        alpha=0.8
    )

    ax.plot(
        theoretical,
        slope * theoretical + intercept,
        color=COLOR_ORANGE,
        linestyle="--",
        linewidth=1.5
    )

    p_text = (
        "< 0.001"
        if ad_result.p_value < 0.001
        else f"{ad_result.p_value:.3f}"
    )

    ax.text(
        1.0,
        1.035,
        f"AD = {ad_result.ad_statistic:.3f}  |  p = {p_text}",
        transform=ax.transAxes,
        ha="right",
        va="bottom",
        fontsize=8.7,
        fontweight="medium",
        color=COLOR_TEXT,
        clip_on=False
    )

    ax.set_xlabel(
        "Theoretical normal quantile",
        fontsize=8.5,
        color=COLOR_MUTED
    )
    ax.set_ylabel(
        "Ordered measurements",
        fontsize=8.5,
        color=COLOR_MUTED
    )


def _last25(ax, result, values):
    _style(ax)

    n = result.subgroup_size
    m = min(25, result.subgroup_count)

    if n == 1:
        xx = np.arange(result.n - m + 1, result.n + 1)
        yy = values[-m:]
        ax.plot(
            xx, yy,
            color=COLOR_BLUE,
            marker="o",
            markersize=3,
            linewidth=1.1
        )
        title = f"Last {m} Observations"
        xlabel = "Observation"
    else:
        group = values.reshape(result.subgroup_count, n)[-m:]
        ids = np.arange(
            result.subgroup_count - m + 1,
            result.subgroup_count + 1
        )

        for idx, row in zip(ids, group):
            ax.scatter(
                np.full(n, idx),
                row,
                color=COLOR_BLUE,
                s=13,
                alpha=.68
            )

        title = f"Last {m} Subgroups"
        xlabel = "Subgroup"

    ax.axhline(
        result.mean,
        color=COLOR_CENTER,
        linewidth=1.3,
        linestyle="--",
        label="Mean"
    )

    ax.set_title(
        title,
        fontsize=11,
        fontweight="semibold",
        loc="left",
        pad=8
    )

    ax.set_xlabel(xlabel, fontsize=8.5, color=COLOR_MUTED)
    ax.set_ylabel(result.column_name, fontsize=8.5, color=COLOR_MUTED)
    ax.legend(
        loc="upper right",
        fontsize=7.7,
        frameon=False
    )


def _capability_plot(ax, result):
    _style(ax)

    ax.set_title(
        "Capability Plot — 6σ Intervals",
        fontsize=11,
        fontweight="semibold",
        loc="left",
        pad=8
    )

    for y, sigma, color, label in (
        (2, result.sigma_within, COLOR_BLUE, "Within"),
        (1, result.sigma_overall, COLOR_ORANGE, "Overall"),
    ):
        left = result.mean - 3.0 * sigma
        right = result.mean + 3.0 * sigma

        ax.plot(
            [left, right],
            [y, y],
            color=color,
            linewidth=3,
            solid_capstyle="round"
        )

        ax.plot(
            [left, right],
            [y, y],
            marker="|",
            color=color,
            markersize=12,
            linestyle="None"
        )

        ax.plot(
            result.mean,
            y,
            marker="o",
            color=color,
            markersize=4
        )

    for v, label in ((result.lsl, "LSL"), (result.usl, "USL")):
        if v is not None:
            ax.axvline(
                v,
                color=COLOR_SPEC,
                linestyle="--",
                linewidth=1.2
            )

    ax.set_ylim(0.4, 2.6)
    ax.set_yticks([1, 2], labels=["Overall", "Within"])
    ax.set_xlabel(result.column_name, fontsize=8.5, color=COLOR_MUTED)

    ax.text(
        .02,
        .96,
        f"Cp {_fmt(result.cp)}   Cpk {_fmt(result.cpk)}"
        f"    Pp {_fmt(result.pp)}   Ppk {_fmt(result.ppk)}",
        transform=ax.transAxes,
        va="top",
        fontsize=8,
        color=COLOR_TEXT
    )


def create_capability_sixpack_figure(
    result: CapabilityResult,
    ad_result: AndersonDarlingResult | None = None,
) -> Figure:
    """Create Sixpack using the existing SPC, Capability and AD engines."""
    values = _check_result(result)

    if ad_result is None:
        try:
            ad_result = AndersonDarlingEngine.calculate_normal(
                result.values,
                result.column_name
            )
        except AndersonDarlingError as exc:
            raise CapabilitySixpackError(
                f"Anderson-Darling gagal: {exc}"
            ) from exc
    else:
        if not isinstance(ad_result, AndersonDarlingResult):
            raise CapabilitySixpackError(
                "ad_result harus berupa AndersonDarlingResult."
            )

        if (
            ad_result.n != result.n
            or ad_result.column_name != result.column_name
        ):
            raise CapabilitySixpackError(
                "Hasil Anderson-Darling tidak sesuai dengan dataset Sixpack."
            )

        if not isfinite(ad_result.ad_statistic) or not (
            0.0 <= ad_result.p_value <= 1.0
        ):
            raise CapabilitySixpackError(
                "Hasil Anderson-Darling tidak finite atau p-value tidak valid."
            )

        if not np.isclose(
            ad_result.mean,
            result.mean,
            rtol=1e-12,
            atol=1e-12
        ):
            raise CapabilitySixpackError(
                "Mean hasil Anderson-Darling tidak sesuai dengan Sixpack."
            )

    try:
        charts = _spc_series(result, values)
    except (SpcError, XbarRError, XbarSError) as exc:
        raise CapabilitySixpackError(str(exc)) from exc

    fig = Figure(figsize=(14.0, 9.6), dpi=100)
    fig.patch.set_facecolor("white")

    # R4.9.5 — ruang vertikal lebih lega bagi title dan legend SPC.
    gs = fig.add_gridspec(
        3,
        2,
        left=.074,
        right=.97,
        top=.825,
        bottom=.145,
        hspace=.67,
        wspace=.28
    )

    axes = [
        [fig.add_subplot(gs[i, j]) for j in range(2)]
        for i in range(3)
    ]

    _control_chart(axes[0][0], charts[0])
    _histogram(axes[0][1], result, values)
    _control_chart(axes[1][0], charts[1])
    _qq(axes[1][1], values, ad_result)
    _last25(axes[2][0], result, values)
    _capability_plot(axes[2][1], result)

    fig.text(
        .074,
        .973,
        "Normal Capability Sixpack",
        ha="left",
        va="top",
        fontsize=19,
        fontweight="bold",
        color="#0f172a"
    )

    method = (
        "Individuals / MR(2)"
        if result.subgroup_size == 1
        else (
            f"Subgroups n={result.subgroup_size} / "
            f"{result.within_method.upper()}"
        )
    )

    fig.text(
        .074,
        .932,
        f"{result.column_name}   |   {method}   |   N = {result.n}",
        ha="left",
        va="top",
        fontsize=10.2,
        color=COLOR_MUTED
    )

    footer = (
        "SPC limits: existing StatDesk Phase I engine  |  "
        "Capability: Normal Capability Engine  |  "
        "Normality: Anderson-Darling AD + p-value"
    )

    fig.text(
        .074,
        .045,
        footer,
        fontsize=8.2,
        color=COLOR_MUTED,
        va="center"
    )

    if result.n < 100:
        fig.text(
            .074,
            .020,
            f"N={result.n}: capability results from small samples "
            "are preliminary; evaluate normality and process stability.",
            fontsize=8.0,
            color="#92400e",
            va="center"
        )

    return fig
