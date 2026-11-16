"""Prepare equal-size rational subgroup rows from worksheet snapshots."""

from math import isfinite
from numbers import Real


class SubgroupDataError(ValueError):
    """Invalid subgroup selection or incomplete worksheet data."""


def prepare_subgroups(
    columns,
    rows,
    selected_indexes,
    *,
    min_columns=2,
    max_columns=8
):
    """
    One worksheet row = one rational subgroup.

    Default: Xbar-R, 2..8 measurement columns.
    Xbar-S: set min_columns=9, max_columns=25.

    No missing values or silently skipped rows.
    """

    # =====================================
    # 1. VALIDATE SUBGROUP SIZE LIMITS
    # =====================================

    if (
        type(min_columns) is not int
        or type(max_columns) is not int
        or min_columns < 2
        or max_columns < min_columns
    ):
        raise SubgroupDataError(
            "Batas ukuran subgrup tidak valid."
        )

    try:
        indexes = list(selected_indexes)

    except TypeError as exc:
        raise SubgroupDataError(
            "Pilihan kolom tidak valid."
        ) from exc

    if not min_columns <= len(indexes) <= max_columns:
        raise SubgroupDataError(
            f"Pilih {min_columns} sampai {max_columns} "
            "kolom pengukuran untuk satu subgrup."
        )

    # =====================================
    # 2. VALIDATE COLUMN INDEXES
    # =====================================

    if any(type(i) is not int for i in indexes):
        raise SubgroupDataError(
            "Indeks kolom harus bilangan bulat."
        )

    if len(indexes) != len(set(indexes)):
        raise SubgroupDataError(
            "Kolom tidak boleh dipilih dua kali."
        )

    if any(
        i < 0 or i >= len(columns)
        for i in indexes
    ):
        raise SubgroupDataError(
            "Kolom pengukuran tidak ditemukan."
        )

    # Preserve original worksheet column order
    indexes.sort()

    # =====================================
    # 3. VALIDATE COLUMN TYPES
    # =====================================

    for idx in indexes:

        if columns[idx].data_type != "numeric":
            raise SubgroupDataError(
                f"Kolom C{idx + 1} "
                f"({columns[idx].name}) harus Numeric."
            )

    if len(rows) < 2:
        raise SubgroupDataError(
            "Minimal diperlukan dua subgrup lengkap."
        )

    # =====================================
    # 4. VALIDATE ALL MEASUREMENTS
    # =====================================

    prepared = []

    for row_number, row in enumerate(
        rows,
        start=1
    ):

        subgroup = []

        for idx in indexes:

            if idx >= len(row):
                raise SubgroupDataError(
                    f"Baris {row_number}: "
                    f"kolom C{idx + 1} tidak tersedia."
                )

            raw = row[idx]

            if raw is None:
                raise SubgroupDataError(
                    f"Baris {row_number}, "
                    f"kolom {columns[idx].name}: "
                    "pengukuran kosong. "
                    "Subgrup harus lengkap."
                )

            if (
                isinstance(raw, bool)
                or not isinstance(raw, Real)
            ):
                raise SubgroupDataError(
                    f"Baris {row_number}, "
                    f"kolom {columns[idx].name}: "
                    "data bukan Numeric."
                )

            try:
                value = float(raw)

            except (
                ValueError,
                OverflowError
            ) as exc:
                raise SubgroupDataError(
                    f"Baris {row_number}, "
                    f"kolom {columns[idx].name}: "
                    "nilai tidak dapat dikonversi."
                ) from exc

            if not isfinite(value):
                raise SubgroupDataError(
                    f"Baris {row_number}, "
                    f"kolom {columns[idx].name}: "
                    "NaN/Infinity tidak diperbolehkan."
                )

            subgroup.append(value)

        prepared.append(subgroup)

    return prepared