
"""StatDesk R4.2 — Normal Process Capability configuration dialog.

This module collects selections and specification limits only.
Statistical calculations belong to capability_engine.py.

Data layout:
- individuals: one Numeric column, time-ordered observations
- subgroups: checked Numeric columns, one rational subgroup per row

No QA approval, file I/O, or calculations in this dialog.
"""

import re
from dataclasses import dataclass
from math import isfinite

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGroupBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from statdesk.statistics.capability_engine import (
    MAX_SUBGROUP_SIZE,
    VALID_SUBGROUP_METHODS,
)
from statdesk.statistics.xbar_r_engine import RANGE_CONSTANTS


@dataclass(frozen=True)
class CapabilitySelection:
    """Validated configuration from the accepted dialog.

    `selected_indexes` refer to original worksheet columns (zero-based).
    For individuals, there is exactly one selected index.
    For subgroups, there are 2..MAX_SUBGROUP_SIZE selected indexes.

    The caller obtains rows from WorksheetModel.export_snapshot(),
    validates the actual measurements, and calls CapabilityEngine.
    """

    layout: str
    selected_indexes: tuple[int, ...]
    column_name: str
    lsl: float | None
    usl: float | None
    target: float | None
    within_method: str
    use_unbiasing_within: bool
    use_unbiasing_overall: bool

    @property
    def subgroup_size(self) -> int:
        return (
            len(self.selected_indexes)
            if self.layout == "subgroups"
            else 1
        )


class CapabilityDialog(QDialog):
    """Collect Normal Capability options using current worksheet columns.

    Usage in R4.4:
        dialog = CapabilityDialog(self, self.model.columns)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            config = dialog.configuration()
    """

    NUMBER_PATTERN = re.compile(
        r"^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?$"
    )

    def __init__(self, parent, columns):
        super().__init__(parent)

        self._selection: CapabilitySelection | None = None
        self._custom_characteristic = False

        self._numeric_columns = tuple(
            (index, column.name)
            for index, column in enumerate(columns)
            if column.data_type == "numeric"
        )

        self.setWindowTitle("StatDesk — Normal Process Capability")
        self.resize(650, 730)
        self.setMinimumWidth(560)

        self._setup_ui()
        self._refresh_mode()

    # ==================================================
    # 1. DIALOG LAYOUT
    # ==================================================

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(10)

        heading = QLabel("NORMAL PROCESS CAPABILITY — R4")
        heading.setStyleSheet("font-weight: 600; font-size: 14px;")
        root.addWidget(heading)

        introduction = QLabel(
            "Pilih sumber pengukuran dan batas spesifikasi produk. "
            "Cp/Cpk memakai within sigma, sedangkan Pp/Ppk memakai "
            "overall sigma. Grafik dan perhitungan dilakukan setelah "
            "konfigurasi diterima."
        )
        introduction.setWordWrap(True)
        root.addWidget(introduction)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll)

        content = QWidget(scroll)
        form = QVBoxLayout(content)
        form.setSpacing(12)
        scroll.setWidget(content)

        # ----------------------------------------------
        # A. DATA LAYOUT
        # ----------------------------------------------
        source_group = QGroupBox("1. Data Layout & Characteristic", content)
        source_form = QFormLayout(source_group)

        self.layout_combo = QComboBox(source_group)
        self.layout_combo.addItem(
            "Individuals — one Numeric column, ordered by time",
            "individuals",
        )
        self.layout_combo.addItem(
            "Rational Subgroups — one subgroup per worksheet row",
            "subgroups",
        )
        source_form.addRow("Data layout:", self.layout_combo)

        self.characteristic_input = QLineEdit(source_group)
        self.characteristic_input.setPlaceholderText(
            "Contoh: Diameter (mm)"
        )
        source_form.addRow(
            "Characteristic:", self.characteristic_input
        )
        form.addWidget(source_group)

        # ----------------------------------------------
        # B. INDIVIDUAL COLUMN
        # ----------------------------------------------
        self.individual_group = QGroupBox(
            "2. Individuals — Measurement Column", content
        )
        individual_layout = QVBoxLayout(self.individual_group)

        self.individual_column_combo = QComboBox(self.individual_group)
        for index, name in self._numeric_columns:
            self.individual_column_combo.addItem(
                f"C{index + 1} — {name} [Numeric]", index
            )
        individual_layout.addWidget(self.individual_column_combo)

        individual_note = QLabel(
            "Pilih satu kolom berisi pengukuran yang diurutkan "
            "berdasarkan waktu. Within sigma dihitung dari "
            "MRbar / d2(2); overall sigma dari sample SD. "
            "Baris kosong di tengah data tidak dilewati otomatis."
        )
        individual_note.setWordWrap(True)
        individual_layout.addWidget(individual_note)
        form.addWidget(self.individual_group)

        # ----------------------------------------------
        # C. RATIONAL SUBGROUP COLUMNS
        # ----------------------------------------------
        self.subgroup_group = QGroupBox(
            "2. Subgroups — Measurement Columns", content
        )
        subgroup_layout = QVBoxLayout(self.subgroup_group)

        subgroup_note = QLabel(
            "Centang 2 sampai 200 kolom Numeric yang semuanya "
            "mengukur karakteristik kualitas yang SAMA. "
            "Setiap baris = satu rational subgroup. "
            "Jangan pilih kolom Shift, Batch, ID, atau tanggal "
            "sebagai pengukuran. Baris harus berurutan menurut waktu."
        )
        subgroup_note.setWordWrap(True)
        subgroup_layout.addWidget(subgroup_note)

        self.subgroup_list = QListWidget(self.subgroup_group)
        self.subgroup_list.setMinimumHeight(145)
        self.subgroup_list.setMaximumHeight(200)

        for index, name in self._numeric_columns:
            item = QListWidgetItem(
                f"C{index + 1} — {name} [Numeric]"
            )
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setFlags(
                item.flags() | Qt.ItemFlag.ItemIsUserCheckable
            )
            item.setCheckState(Qt.CheckState.Unchecked)
            self.subgroup_list.addItem(item)

        subgroup_layout.addWidget(self.subgroup_list)

        self.selection_info = QLabel()
        self.selection_info.setWordWrap(True)
        subgroup_layout.addWidget(self.selection_info)
        form.addWidget(self.subgroup_group)

        # ----------------------------------------------
        # D. SPECIFICATION LIMITS
        # ----------------------------------------------
        spec_group = QGroupBox("3. Specification Limits", content)
        spec_form = QFormLayout(spec_group)

        self.lsl_input = QLineEdit(spec_group)
        self.lsl_input.setPlaceholderText("Optional, contoh: 9.90")
        spec_form.addRow("LSL:", self.lsl_input)

        self.usl_input = QLineEdit(spec_group)
        self.usl_input.setPlaceholderText("Optional, contoh: 10.10")
        spec_form.addRow("USL:", self.usl_input)

        self.target_input = QLineEdit(spec_group)
        self.target_input.setPlaceholderText("Optional, contoh: 10.00")
        spec_form.addRow("Target:", self.target_input)

        spec_note = QLabel(
            "Wajib isi LSL atau USL (boleh keduanya). "
            "LSL harus lebih kecil daripada USL. "
            "Gunakan titik atau koma untuk desimal, "
            "tanpa pemisah ribuan. Target bersifat opsional."
        )
        spec_note.setWordWrap(True)
        spec_form.addRow(spec_note)
        form.addWidget(spec_group)

        # ----------------------------------------------
        # E. SIGMA ESTIMATION
        # ----------------------------------------------
        self.within_group = QGroupBox(
            "4. Within Sigma — Subgroup Method", content
        )
        within_layout = QVBoxLayout(self.within_group)

        self.method_combo = QComboBox(self.within_group)
        self.method_combo.addItem(
            "Pooled SD — default", "pooled"
        )
        self.method_combo.addItem(
            "Average Subgroup SD (Sbar)", "sbar"
        )
        self.method_combo.addItem(
            "Average Range (Rbar), subgroup size 2–8", "rbar"
        )
        within_layout.addWidget(self.method_combo)

        self.within_unbiasing = QCheckBox(
            "Apply c4 unbiasing correction", self.within_group
        )
        self.within_unbiasing.setChecked(True)
        within_layout.addWidget(self.within_unbiasing)

        self.method_note = QLabel()
        self.method_note.setWordWrap(True)
        within_layout.addWidget(self.method_note)
        form.addWidget(self.within_group)

        # ----------------------------------------------
        # F. OVERALL SIGMA
        # ----------------------------------------------
        overall_group = QGroupBox(
            "5. Overall Sigma", content
        )
        overall_layout = QVBoxLayout(overall_group)

        self.overall_unbiasing = QCheckBox(
            "Apply c4(N) correction to overall sample SD",
            overall_group,
        )
        self.overall_unbiasing.setChecked(False)
        overall_layout.addWidget(self.overall_unbiasing)

        overall_note = QLabel(
            "Default: sample SD dari semua pengukuran "
            "menggunakan penyebut N−1 tanpa koreksi c4. "
            "Koreksi overall dapat diaktifkan jika "
            "metode pembanding menggunakannya."
        )
        overall_note.setWordWrap(True)
        overall_layout.addWidget(overall_note)
        form.addWidget(overall_group)

        assumptions = QLabel(
            "Catatan: Capability Normal mengasumsikan distribusi "
            "yang sesuai dan proses yang cukup stabil. "
            "Pemilihan metode tidak otomatis menguji kedua asumsi itu."
        )
        assumptions.setWordWrap(True)
        form.addWidget(assumptions)
        form.addStretch(1)

        # ----------------------------------------------
        # G. ACTION BUTTONS
        # ----------------------------------------------
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        self.buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText("Run Analysis")
        self.buttons.accepted.connect(self._validate_and_accept)
        self.buttons.rejected.connect(self.reject)
        root.addWidget(self.buttons)

        # ----------------------------------------------
        # H. UI SIGNALS
        # ----------------------------------------------
        self.layout_combo.currentIndexChanged.connect(
            self._refresh_mode
        )
        self.individual_column_combo.currentIndexChanged.connect(
            self._sync_characteristic
        )
        self.characteristic_input.textEdited.connect(
            self._characteristic_edited
        )
        self.subgroup_list.itemChanged.connect(
            self._refresh_selection
        )
        self.method_combo.currentIndexChanged.connect(
            self._refresh_method
        )

    # ==================================================
    # 2. SELECTION & DYNAMIC UI
    # ==================================================

    def _characteristic_edited(self, _text=None):
        self._custom_characteristic = True

    def _sync_characteristic(self, _index=None):
        if self._custom_characteristic:
            return

        if self.layout_combo.currentData() == "individuals":
            self.characteristic_input.setText(
                self.individual_column_combo.currentText()
                .split(" — ", 1)[-1]
                .removesuffix(" [Numeric]")
                if self.individual_column_combo.count()
                else "Measurement"
            )
        else:
            self.characteristic_input.setText("Measurement")

    def selected_subgroup_indexes(self) -> tuple[int, ...]:
        indexes = (
            int(self.subgroup_list.item(i).data(
                Qt.ItemDataRole.UserRole
            ))
            for i in range(self.subgroup_list.count())
            if self.subgroup_list.item(i).checkState()
            == Qt.CheckState.Checked
        )
        return tuple(sorted(indexes))

    def _refresh_selection(self, _item=None):
        count = len(self.selected_subgroup_indexes())
        allowed = (
            min(RANGE_CONSTANTS) <= count <= max(RANGE_CONSTANTS)
            if self.method_combo.currentData() == "rbar"
            else 2 <= count <= MAX_SUBGROUP_SIZE
        )
        self.selection_info.setText(
            f"{count} kolom dipilih — "
            + ("siap dianalisis" if allowed else
               ("Rbar hanya mendukung ukuran subgroup 2–8"
                if self.method_combo.currentData() == "rbar"
                else f"pilih 2 sampai {MAX_SUBGROUP_SIZE} kolom"))
        )
        self._refresh_accept()

    def _refresh_mode(self, _index=None):
        individuals = self.layout_combo.currentData() == "individuals"
        self.individual_group.setVisible(individuals)
        self.subgroup_group.setVisible(not individuals)
        self.within_group.setVisible(not individuals)
        self._sync_characteristic()
        self._refresh_method()
        self._refresh_accept()

    def _refresh_method(self, _index=None):
        method = self.method_combo.currentData()
        rbar = method == "rbar"

        self.within_unbiasing.setEnabled(not rbar)
        if rbar:
            self.within_unbiasing.setChecked(True)

        explanations = {
            "pooled": (
                "Pooled SD dari variansi dalam subgroup, "
                "opsional dikoreksi dengan c4(df + 1). "
                "df = m × (n − 1) untuk subgroup sama besar."
            ),
            "sbar": (
                "Average sample SD dalam subgroup; "
                "opsional dibagi c4(n)."
            ),
            "rbar": (
                "Rbar / d2(n) dengan konstanta tersedia "
                "untuk subgroup size 2–8. Koreksi d2 wajib."
            ),
        }
        self.method_note.setText(explanations[method])
        self._refresh_selection()

    def _refresh_accept(self):
        layout = self.layout_combo.currentData()
        if layout == "individuals":
            enabled = self.individual_column_combo.count() >= 1
        else:
            count = len(self.selected_subgroup_indexes())
            enabled = 2 <= count <= MAX_SUBGROUP_SIZE
            if self.method_combo.currentData() == "rbar":
                enabled = enabled and count in RANGE_CONSTANTS

        self.buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setEnabled(enabled)

    # ==================================================
    # 3. SPECIFICATION INPUT
    # ==================================================

    @classmethod
    def _optional_number(cls, text: str, name: str) -> float | None:
        raw = text.strip()
        if not raw:
            return None

        if not cls.NUMBER_PATTERN.fullmatch(raw):
            raise ValueError(
                f"{name} harus angka valid, contoh: 9.90. "
                "Jangan gunakan pemisah ribuan."
            )

        number = float(raw.replace(",", "."))
        if not isfinite(number):
            raise ValueError(f"{name} tidak boleh NaN/Infinity.")

        return number

    # ==================================================
    # 4. FINAL VALIDATION
    # ==================================================

    def _validate_and_accept(self):
        try:
            layout = self.layout_combo.currentData()
            characteristic = self.characteristic_input.text().strip()

            if not characteristic:
                raise ValueError(
                    "Characteristic harus diisi, contoh: Diameter (mm)."
                )

            if layout == "individuals":
                current = self.individual_column_combo.currentData()
                if current is None:
                    raise ValueError("Pilih satu kolom Numeric.")
                selected_indexes = (int(current),)
                within_method = "mrbar"
                use_unbiasing_within = True

            elif layout == "subgroups":
                selected_indexes = self.selected_subgroup_indexes()
                count = len(selected_indexes)

                if not 2 <= count <= MAX_SUBGROUP_SIZE:
                    raise ValueError(
                        f"Pilih 2 sampai {MAX_SUBGROUP_SIZE} kolom "
                        "Numeric untuk rational subgroup."
                    )

                within_method = self.method_combo.currentData()
                if within_method not in VALID_SUBGROUP_METHODS:
                    raise ValueError("Metode within sigma tidak dikenal.")

                if (within_method == "rbar"
                        and count not in RANGE_CONSTANTS):
                    raise ValueError(
                        "Rbar hanya tersedia untuk subgroup size 2–8."
                    )

                use_unbiasing_within = (
                    True if within_method == "rbar"
                    else self.within_unbiasing.isChecked()
                )

            else:
                raise ValueError("Data layout tidak dikenal.")

            lsl = self._optional_number(self.lsl_input.text(), "LSL")
            usl = self._optional_number(self.usl_input.text(), "USL")
            target = self._optional_number(
                self.target_input.text(), "Target"
            )

            if lsl is None and usl is None:
                raise ValueError("Isi minimal LSL atau USL.")

            if lsl is not None and usl is not None and lsl >= usl:
                raise ValueError("LSL harus lebih kecil daripada USL.")

            self._selection = CapabilitySelection(
                layout=layout,
                selected_indexes=selected_indexes,
                column_name=characteristic,
                lsl=lsl,
                usl=usl,
                target=target,
                within_method=within_method,
                use_unbiasing_within=use_unbiasing_within,
                use_unbiasing_overall=self.overall_unbiasing.isChecked(),
            )

        except (ValueError, OverflowError) as exc:
            QMessageBox.warning(
                self, "StatDesk — Capability", str(exc)
            )
            return

        self.accept()

    def configuration(self) -> CapabilitySelection:
        """Return configuration after dialog acceptance."""
        if self._selection is None:
            raise ValueError(
                "Capability Dialog belum berhasil dikonfirmasi."
            )
        return self._selection
 