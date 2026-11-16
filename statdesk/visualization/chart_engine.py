"""StatDesk Data Visualization Engine."""

from dataclasses import dataclass
from math import ceil, isfinite, log2
from numbers import Real

import numpy as np

from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

from scipy import stats


class ChartError(ValueError):
    """Error untuk validasi data grafik."""


@dataclass(frozen=True)
class ChartDataset:
    column_name: str
    values: tuple[float, ...]
    total_rows: int
    missing_rows: int

    @property
    def n(self) -> int:
        return len(self.values)


class ChartEngine:

    HISTOGRAM = "histogram"
    BOXPLOT = "boxplot"
    NORMAL_PROBABILITY = "normal_probability"

    # =====================================
    # DATA PREPARATION
    # =====================================

    @staticmethod
    def prepare(values, column_name: str) -> ChartDataset:

        if not isinstance(column_name, str) or not column_name.strip():
            raise ChartError("Pilih kolom Numeric yang valid.")

        cleaned = []
        total = 0
        missing = 0

        for row_number, value in enumerate(values, start=1):

            total += 1

            if value is None:
                missing += 1
                continue

            if isinstance(value, bool) or not isinstance(value, Real):
                raise ChartError(
                    f"Baris {row_number}: data bukan angka Numeric."
                )

            try:
                number = float(value)
            except (OverflowError, ValueError) as exc:
                raise ChartError(
                    f"Baris {row_number}: nilai tidak dapat dikonversi."
                ) from exc

            if not isfinite(number):
                raise ChartError(
                    f"Baris {row_number}: NaN/Infinity tidak didukung."
                )

            cleaned.append(number)

        if not cleaned:
            raise ChartError("Kolom tidak memiliki pengukuran valid.")

        return ChartDataset(
            column_name=column_name.strip(),
            values=tuple(cleaned),
            total_rows=total,
            missing_rows=missing,
        )

    # =====================================
    # FIGURE GENERATOR
    # =====================================

    @classmethod
    def create_figure(
        cls,
        chart_type: str,
        data: ChartDataset
    ) -> Figure:

        if chart_type not in {
            cls.HISTOGRAM,
            cls.BOXPLOT,
            cls.NORMAL_PROBABILITY,
        }:
            raise ChartError("Jenis grafik tidak dikenal.")

        numbers = np.asarray(
            data.values,
            dtype=np.float64
        )

        figure = Figure(
            figsize=(9.2, 5.7),
            dpi=100
        )

        figure.patch.set_facecolor("white")

        ax = figure.add_subplot(111)
        ax.set_facecolor("white")

        name = data.column_name

        # =====================================
        # HISTOGRAM - IMPROVED VERSION
        # =====================================

        if chart_type == cls.HISTOGRAM:

            # Jumlah bin berdasarkan Sturges
            bins = max(
                1,
                min(60, ceil(1 + log2(data.n)))
            )

            # Buat histogram dengan jarak antarbins
            counts, _edges, patches = ax.hist(
                numbers,
                bins=bins,
                rwidth=0.84,
                color="#2878B5",
                edgecolor="white",
                linewidth=1.3,
                alpha=0.95,
            )

            # Judul dan label
            ax.set_title(
                f"Histogram — {name}",
                fontsize=15,
                pad=16
            )

            ax.set_xlabel(name)
            ax.set_ylabel("Frequency (count)")

            # Grid berada di belakang batang
            ax.set_axisbelow(True)

            ax.grid(
                axis="y",
                color="#CBD5E1",
                linewidth=0.8,
                alpha=0.6
            )

            # Frekuensi harus menggunakan tick integer
            ax.yaxis.set_major_locator(
                MaxNLocator(
                    integer=True,
                    nbins=6
                )
            )

            # Ruang untuk label frekuensi
            peak = float(counts.max())

            ax.set_ylim(
                0,
                max(2.0, peak * 1.33)
            )

            # Tampilkan angka di atas batang
            for count, patch in zip(counts, patches):

                if count == 0:
                    continue

                ax.annotate(
                    str(int(count)),
                    xy=(
                        patch.get_x()
                        + patch.get_width() / 2,
                        patch.get_height()
                    ),
                    xytext=(0, 5),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=10,
                    weight="bold",
                    color="#334155"
                )

            # Informasi dataset pada pojok kanan atas
            ax.text(
                0.99,
                0.98,
                (
                    f"N = {data.n}   |   "
                    f"Missing = {data.missing_rows}   |   "
                    f"Bins = {bins}"
                ),
                transform=ax.transAxes,
                ha="right",
                va="top",
                fontsize=9,
                color="#475569",
                bbox={
                    "boxstyle": "round,pad=0.35",
                    "facecolor": "#F8FAFC",
                    "edgecolor": "#E2E8F0",
                },
            )

            # Hilangkan border atas dan kanan
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)

        # =====================================
        # BOXPLOT - EXISTING FEATURE
        # =====================================

        elif chart_type == cls.BOXPLOT:

            if data.n < 2:
                raise ChartError(
                    "Boxplot membutuhkan minimal 2 data valid."
                )

            ax.boxplot(
                numbers,
                orientation="vertical",
                tick_labels=[name],
                whis=1.5,
                showmeans=True,
            )

            ax.set_title(f"Boxplot — {name}")
            ax.set_ylabel(name)

            ax.grid(
                axis="y",
                alpha=0.25
            )

        # =====================================
        # NORMAL PROBABILITY PLOT
        # =====================================

        else:

            if data.n < 3:
                raise ChartError(
                    "Normal Probability Plot membutuhkan minimal 3 data valid."
                )

            if numbers.min() == numbers.max():
                raise ChartError(
                    "Normal Probability Plot tidak dapat dibuat dari data konstan."
                )

            (theoretical, ordered), (slope, intercept, _r) = (
                stats.probplot(
                    numbers,
                    dist="norm",
                    fit=True
                )
            )

            if not all(
                isfinite(float(x))
                for x in (slope, intercept)
            ):
                raise ChartError(
                    "Fit Normal Probability Plot tidak finite."
                )

            ax.scatter(
                theoretical,
                ordered,
                s=24
            )

            ax.plot(
                theoretical,
                slope * theoretical + intercept,
                linestyle="--"
            )

            ax.set_title(
                f"Normal Probability Plot — {name}"
            )

            ax.set_xlabel(
                "Theoretical quantiles (normal)"
            )

            ax.set_ylabel(
                f"Ordered {name}"
            )

            ax.grid(alpha=0.25)

        # =====================================
        # FIGURE FOOTER
        # =====================================

        figure.text(
            0.015,
            0.025,
            (
                f"StatDesk v0.5 | Snapshot | "
                f"N={data.n}, "
                f"Missing={data.missing_rows} | "
                "Not an SPC/control chart"
            ),
            fontsize=8
        )

        figure.tight_layout(
            rect=(0, 0.11, 1, 1)
        )

        return figure