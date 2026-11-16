"""Subgroup column selection dialog for Xbar-R and Xbar-S."""

from PySide6.QtCore import Qt

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


class SubgroupColumnsDialog(QDialog):

    def __init__(
        self,
        parent,
        columns,
        *,
        chart_name="Xbar-R",
        min_columns=2,
        max_columns=8
    ):
        super().__init__(parent)

        if not 2 <= min_columns <= max_columns <= 25:
            raise ValueError(
                "Batas ukuran subgrup tidak valid."
            )

        self.min_columns = min_columns
        self.max_columns = max_columns

        self.setWindowTitle(
            f"{chart_name} — Pilih kolom sampel"
        )

        self.resize(550, 480)

        layout = QVBoxLayout(self)

        # =====================================
        # 1. INSTRUCTIONS
        # =====================================

        explanation = QLabel(
            f"Pilih {min_columns}–{max_columns} "
            "kolom Numeric yang mengukur "
            "karakteristik kualitas yang SAMA.\n\n"

            "Setiap BARIS adalah satu rational subgroup, "
            "berurutan dari waktu terlama ke terbaru.\n\n"

            "Jangan pilih Batch, ID, nomor urut, "
            "atau tanggal."
        )

        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        # =====================================
        # 2. NUMERIC COLUMN CHECKBOXES
        # =====================================

        self.column_list = QListWidget(self)

        for index, column in enumerate(columns):

            if column.data_type != "numeric":
                continue

            item = QListWidgetItem(
                f"C{index + 1} — "
                f"{column.name} [Numeric]"
            )

            item.setData(
                Qt.ItemDataRole.UserRole,
                index
            )

            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsUserCheckable
            )

            item.setCheckState(
                Qt.CheckState.Unchecked
            )

            self.column_list.addItem(item)

        self.column_list.itemChanged.connect(
            self._refresh
        )

        layout.addWidget(self.column_list)

        # =====================================
        # 3. SELECTION INFORMATION
        # =====================================

        self.selection_info = QLabel(self)
        layout.addWidget(self.selection_info)

        # =====================================
        # 4. OK / CANCEL BUTTONS
        # =====================================

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )

        self.buttons.accepted.connect(
            self.accept
        )

        self.buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(self.buttons)

        self._refresh()

    # =====================================
    # 5. SELECTED COLUMN INDEXES
    # =====================================

    def selected_column_indexes(self):

        return [
            int(
                self.column_list.item(i).data(
                    Qt.ItemDataRole.UserRole
                )
            )
            for i in range(
                self.column_list.count()
            )
            if self.column_list.item(i).checkState()
            == Qt.CheckState.Checked
        ]

    # =====================================
    # 6. VALIDATE SELECTION COUNT
    # =====================================

    def _refresh(self, _item=None):

        count = len(
            self.selected_column_indexes()
        )

        valid = (
            self.min_columns
            <= count
            <= self.max_columns
        )

        self.selection_info.setText(
            f"{count} kolom dipilih — "
            + (
                "siap divalidasi."
                if valid
                else (
                    f"pilih {self.min_columns}–"
                    f"{self.max_columns} kolom."
                )
            )
        )

        self.buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setEnabled(valid)