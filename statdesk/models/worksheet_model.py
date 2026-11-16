import math
import re

from dataclasses import dataclass

from PySide6.QtCore import (
    QAbstractTableModel,
    QModelIndex,
    Qt,
    Signal,
)


@dataclass
class ColumnDefinition:
    name: str
    data_type: str  # "numeric" atau "text"


class WorksheetModel(QAbstractTableModel):

    validation_error = Signal(str)
    modified = Signal()

    MAX_ROWS = 50_000
    MAX_COLUMNS = 200

    NUMBER_PATTERN = re.compile(
        r"^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?$"
    )

    def __init__(self, parent=None):
        super().__init__(parent)

        self.columns = self._default_columns()
        self._rows = [
            [None] * 3
            for _ in range(30)
        ]

    @staticmethod
    def _default_columns():
        return [
            ColumnDefinition(
                "Diameter (mm)",
                "numeric"
            ),
            ColumnDefinition("Shift", "text"),
            ColumnDefinition("Operator", "text"),
        ]

    @staticmethod
    def _display_value(value):

        if value is None:
            return ""

        if isinstance(value, float):
            return format(value, ".15g")

        return str(value)

    @classmethod
    def _normalize(cls, raw, kind):

        text = (
            ""
            if raw is None
            else str(raw).strip()
        )

        if not text:
            return None

        if kind == "text":
            return text

        if (
            kind != "numeric"
            or not cls.NUMBER_PATTERN.fullmatch(text)
        ):
            raise ValueError(
                "Kolom Numeric hanya menerima angka "
                "(10.25 atau 10,25) "
                "tanpa pemisah ribuan."
            )

        number = float(
            text.replace(",", ".")
        )

        if not math.isfinite(number):
            raise ValueError(
                "Nilai angka harus finite "
                "(bukan NaN atau Infinity)."
            )

        return number

    # =====================================
    # MODEL DIMENSIONS
    # =====================================

    def rowCount(
        self,
        parent=QModelIndex()
    ):
        return (
            0
            if parent.isValid()
            else len(self._rows)
        )

    def columnCount(
        self,
        parent=QModelIndex()
    ):
        return (
            0
            if parent.isValid()
            else len(self.columns)
        )

    # =====================================
    # READ DATA
    # =====================================

    def data(
        self,
        index,
        role=Qt.ItemDataRole.DisplayRole
    ):

        if not index.isValid():
            return None

        value = self._rows[
            index.row()
        ][index.column()]

        if role in (
            Qt.ItemDataRole.DisplayRole,
            Qt.ItemDataRole.EditRole
        ):
            return self._display_value(value)

        if (
            role == Qt.ItemDataRole.TextAlignmentRole
            and self.columns[
                index.column()
            ].data_type == "numeric"
        ):
            return (
                Qt.AlignmentFlag.AlignRight
                | Qt.AlignmentFlag.AlignVCenter
            )

        return None

    # =====================================
    # COLUMN HEADERS
    # =====================================

    def headerData(
        self,
        section,
        orientation,
        role=Qt.ItemDataRole.DisplayRole
    ):

        if role != Qt.ItemDataRole.DisplayRole:
            return None

        if orientation == Qt.Orientation.Vertical:
            return str(section + 1)

        if not 0 <= section < self.columnCount():
            return None

        col = self.columns[section]

        marker = (
            "N"
            if col.data_type == "numeric"
            else "T"
        )

        return (
            f"C{section + 1} - "
            f"{col.name} [{marker}]"
        )

    # =====================================
    # FLAGS / EDITING
    # =====================================

    def flags(self, index):

        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        return (
            Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
            | Qt.ItemFlag.ItemIsEditable
        )

    def setData(
        self,
        index,
        value,
        role=Qt.ItemDataRole.EditRole
    ):

        if (
            not index.isValid()
            or role != Qt.ItemDataRole.EditRole
        ):
            return False

        col = index.column()

        try:
            normalized = self._normalize(
                value,
                self.columns[col].data_type
            )

        except ValueError as exc:
            self.validation_error.emit(
                f"{self.columns[col].name}: {exc}"
            )
            return False

        if self._rows[
            index.row()
        ][col] == normalized:
            return True

        self._rows[
            index.row()
        ][col] = normalized

        self.dataChanged.emit(
            index,
            index,
            [
                Qt.ItemDataRole.DisplayRole,
                Qt.ItemDataRole.EditRole
            ]
        )

        self.modified.emit()

        return True

    # =====================================
    # ROW MANAGEMENT
    # =====================================

    def insertRows(
        self,
        row,
        count,
        parent=QModelIndex()
    ):

        if (
            parent.isValid()
            or count <= 0
            or not 0 <= row <= self.rowCount()
            or self.rowCount() + count > self.MAX_ROWS
        ):
            return False

        self.beginInsertRows(
            QModelIndex(),
            row,
            row + count - 1
        )

        self._rows[row:row] = [
            [None] * self.columnCount()
            for _ in range(count)
        ]

        self.endInsertRows()
        self.modified.emit()

        return True

    def removeRows(
        self,
        row,
        count,
        parent=QModelIndex()
    ):

        if (
            parent.isValid()
            or count <= 0
            or row < 0
            or row + count > self.rowCount()
            or self.rowCount() - count < 1
        ):
            return False

        self.beginRemoveRows(
            QModelIndex(),
            row,
            row + count - 1
        )

        del self._rows[row:row + count]

        self.endRemoveRows()
        self.modified.emit()

        return True

    # =====================================
    # COLUMN MANAGEMENT
    # =====================================

    def insertColumns(
        self,
        column,
        count,
        parent=QModelIndex()
    ):

        if (
            parent.isValid()
            or count <= 0
            or not 0 <= column <= self.columnCount()
            or self.columnCount() + count > self.MAX_COLUMNS
        ):
            return False

        taken = {
            c.name.casefold()
            for c in self.columns
        }

        new_columns = []
        number = 1

        for _ in range(count):

            while f"variable {number}" in taken:
                number += 1

            name = f"Variable {number}"

            taken.add(
                name.casefold()
            )

            new_columns.append(
                ColumnDefinition(
                    name,
                    "text"
                )
            )

            number += 1

        self.beginInsertColumns(
            QModelIndex(),
            column,
            column + count - 1
        )

        self.columns[
            column:column
        ] = new_columns

        for row in self._rows:
            row[column:column] = (
                [None] * count
            )

        self.endInsertColumns()
        self.modified.emit()

        return True

    def removeColumns(
        self,
        column,
        count,
        parent=QModelIndex()
    ):

        if (
            parent.isValid()
            or count <= 0
            or column < 0
            or column + count > self.columnCount()
            or self.columnCount() - count < 1
        ):
            return False

        self.beginRemoveColumns(
            QModelIndex(),
            column,
            column + count - 1
        )

        del self.columns[
            column:column + count
        ]

        for row in self._rows:
            del row[
                column:column + count
            ]

        self.endRemoveColumns()
        self.modified.emit()

        return True

    def rename_column(
        self,
        column,
        name
    ):

        name = name.strip()

        if not name:
            raise ValueError(
                "Nama kolom tidak boleh kosong."
            )

        if any(
            i != column
            and c.name.casefold() == name.casefold()
            for i, c in enumerate(self.columns)
        ):
            raise ValueError(
                "Nama kolom sudah dipakai."
            )

        self.columns[column].name = name

        self.headerDataChanged.emit(
            Qt.Orientation.Horizontal,
            column,
            column
        )

        self.modified.emit()

    def set_column_type(
        self,
        column,
        kind
    ):

        if kind not in ("numeric", "text"):
            raise ValueError(
                "Tipe kolom tidak dikenal."
            )

        if self.columns[column].data_type == kind:
            return

        converted = []

        for row_number, row in enumerate(
            self._rows,
            start=1
        ):
            try:
                converted.append(
                    self._normalize(
                        self._display_value(
                            row[column]
                        ),
                        kind
                    )
                )

            except ValueError as exc:
                raise ValueError(
                    f"Baris {row_number}: {exc}"
                ) from exc

        for row, value in zip(
            self._rows,
            converted
        ):
            row[column] = value

        self.columns[column].data_type = kind

        self.headerDataChanged.emit(
            Qt.Orientation.Horizontal,
            column,
            column
        )

        self.dataChanged.emit(
            self.index(0, column),
            self.index(
                self.rowCount() - 1,
                column
            )
        )

        self.modified.emit()

    # =====================================
    # BULK PASTE
    # =====================================

    def paste_matrix(
        self,
        start_row,
        start_col,
        matrix
    ):

        if not matrix or not any(matrix):
            return 0

        needed_rows = (
            start_row + len(matrix)
        )

        needed_cols = (
            start_col
            + max(
                len(row)
                for row in matrix
            )
        )

        if (
            start_row < 0
            or start_col < 0
            or needed_rows > self.MAX_ROWS
            or needed_cols > self.MAX_COLUMNS
        ):
            raise ValueError(
                "Paste melebihi batas worksheet "
                "(50.000 baris / 200 kolom)."
            )

        prepared = []

        for dr, raw_row in enumerate(matrix):
            for dc, value in enumerate(raw_row):

                row_no = start_row + dr
                col_no = start_col + dc

                kind = (
                    self.columns[col_no].data_type
                    if col_no < self.columnCount()
                    else "text"
                )

                try:
                    normalized = self._normalize(
                        value,
                        kind
                    )

                except ValueError as exc:
                    raise ValueError(
                        f"Paste gagal di baris "
                        f"{row_no + 1}, "
                        f"kolom {col_no + 1}: {exc}"
                    ) from exc

                prepared.append(
                    (row_no, col_no, normalized)
                )

        if needed_cols > self.columnCount():
            self.insertColumns(
                self.columnCount(),
                needed_cols - self.columnCount()
            )

        if needed_rows > self.rowCount():
            self.insertRows(
                self.rowCount(),
                needed_rows - self.rowCount()
            )

        for row_no, col_no, value in prepared:
            self._rows[
                row_no
            ][col_no] = value

        self.dataChanged.emit(
            self.index(start_row, start_col),
            self.index(
                needed_rows - 1,
                needed_cols - 1
            )
        )

        self.modified.emit()

        return len(prepared)

    # =====================================
    # CLEAR SELECTED CELLS
    # =====================================

    def clear_cells(self, indexes):

        changed = 0

        for index in indexes:

            if (
                self._rows[
                    index.row()
                ][index.column()]
                is not None
            ):
                self._rows[
                    index.row()
                ][index.column()] = None

                self.dataChanged.emit(
                    index,
                    index
                )

                changed += 1

        if changed:
            self.modified.emit()

        return changed

    # =====================================
    # RESET / SAMPLE DATA
    # =====================================

    def reset_blank(self):

        self.beginResetModel()

        self.columns = (
            self._default_columns()
        )

        self._rows = [
            [None] * 3
            for _ in range(30)
        ]

        self.endResetModel()
        self.modified.emit()

    def load_sample_data(self):

        sample = [
            [10.02, "A", "Operator 1"],
            [9.98, "A", "Operator 1"],
            [10.05, "B", "Operator 2"],
            [10.01, "B", "Operator 2"],
            [9.99, "A", "Operator 1"],
        ]

        self.beginResetModel()

        self.columns = (
            self._default_columns()
        )

        self._rows = (
            sample
            + [
                [None] * 3
                for _ in range(25)
            ]
        )

        self.endResetModel()
        self.modified.emit()

    def has_data(self):

        return any(
            value is not None
            for row in self._rows
            for value in row
        )

    # =====================================
    # TAHAP 3: IMPORT SECARA ATOMIK
    # =====================================

    def replace_dataset(self, dataset):
        """Validasi seluruh data sebelum mengganti worksheet."""

        columns = dataset.columns
        rows = dataset.rows

        if (
            not 1 <= len(columns) <= self.MAX_COLUMNS
            or len(rows) > self.MAX_ROWS
        ):
            raise ValueError(
                "Ukuran dataset melebihi batas worksheet."
            )

        seen = set()

        for column in columns:

            if (
                not column.name.strip()
                or column.name.casefold() in seen
            ):
                raise ValueError(
                    "Nama kolom harus unik "
                    "dan tidak boleh kosong."
                )

            if column.data_type not in (
                "numeric",
                "text"
            ):
                raise ValueError(
                    "Tipe kolom tidak didukung."
                )

            seen.add(
                column.name.casefold()
            )

        # Validasi semua nilai terlebih dahulu
        prepared = []

        for r, raw_row in enumerate(
            rows,
            start=1
        ):

            if len(raw_row) != len(columns):
                raise ValueError(
                    f"Panjang baris {r} "
                    "tidak sesuai jumlah kolom."
                )

            converted = []

            for c, raw_value in enumerate(
                raw_row,
                start=1
            ):
                try:
                    converted.append(
                        self._normalize(
                            raw_value,
                            columns[c - 1].data_type
                        )
                    )

                except ValueError as exc:
                    raise ValueError(
                        f"Baris {r}, kolom {c}: {exc}"
                    ) from exc

            prepared.append(converted)

        # Sisakan minimal 30 baris
        prepared += [
            [None] * len(columns)
            for _ in range(
                max(0, 30 - len(prepared))
            )
        ]

        # Worksheet lama baru diganti
        # setelah seluruh proses validasi berhasil
        self.beginResetModel()

        self.columns = [
            ColumnDefinition(
                c.name,
                c.data_type
            )
            for c in columns
        ]

        self._rows = prepared

        self.endResetModel()
        self.modified.emit()

    # =====================================
    # TAHAP 3: DATA EXPORT SNAPSHOT
    # =====================================

    def export_snapshot(self):
        """
        Buang hanya baris kosong paling bawah.
        Baris kosong di tengah tetap dipertahankan.
        """

        last_data_row = 0

        for index, row in enumerate(
            self._rows,
            start=1
        ):
            if any(
                value is not None
                for value in row
            ):
                last_data_row = index

        columns = [
            ColumnDefinition(
                c.name,
                c.data_type
            )
            for c in self.columns
        ]

        rows = [
            list(row)
            for row in self._rows[
                :last_data_row
            ]
        ]

        return columns, rows