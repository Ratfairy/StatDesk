
"""StatDesk R3.2 — Xbar-R Historical Parameters dialog.

This GUI only collects statistical configuration. Calculations belong
in statdesk.statistics.spc_phase2, not in this dialog.

Modes:
- estimate: treat selected worksheet subgroups as historical data.
- manual: monitor selected worksheet data with entered mean and sigma.
- reuse: monitor selected worksheet data using prior historical limits.
"""

import re
from dataclasses import dataclass
from math import isfinite

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QLineEdit,
    QMessageBox,
    QVBoxLayout,
)

from statdesk.statistics.spc_phase2 import (
    Phase2Error,
    XbarRHistoricalLimits,
    create_xbar_r_historical_limits,
)

from statdesk.statistics.spc_rules import (
    RULE_PROFILE_LABELS,
    RULE_PROFILE_MINITAB18_OBSERVED,
    RULE_PROFILE_STANDARD,
    get_rule_windows,
)


# ======================================================
# 1. RESULT CONFIGURATION
# ======================================================

@dataclass(frozen=True)
class XbarRPhase2Selection:
    """Configuration returned after dialog acceptance.

    mode:
        estimate
        manual
        reuse

    historical_limits is None only for estimate mode.
    """

    mode: str
    subgroup_size: int

    historical_limits: XbarRHistoricalLimits | None

    enabled_tests: tuple[int, ...]
    rule_profile: str


# ======================================================
# 2. HISTORICAL PARAMETERS DIALOG
# ======================================================

class XbarRPhase2Dialog(QDialog):
    """Choose historical limits calculation or monitoring."""

    NUMBER_PATTERN = re.compile(
        r"^[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?$"
    )

    # ==========================================
    # 3. INITIALIZATION
    # ==========================================

    def __init__(
        self,
        subgroup_size: int,
        historical_limits: XbarRHistoricalLimits | None = None,
        parent=None,
    ):
        super().__init__(parent)

        if (
            type(subgroup_size) is not int
            or not 2 <= subgroup_size <= 8
        ):
            raise ValueError(
                "Xbar-R membutuhkan ukuran subgroup "
                "2 sampai 8."
            )

        self.subgroup_size = subgroup_size

        self._selection: XbarRPhase2Selection | None = None
        self._previous_limits = None

        if historical_limits is not None:

            if not isinstance(
                historical_limits,
                XbarRHistoricalLimits,
            ):
                raise TypeError(
                    "Historical limits tidak valid."
                )

            if (
                historical_limits.subgroup_size
                == subgroup_size
            ):
                self._previous_limits = historical_limits

        self.setWindowTitle(
            "StatDesk — Xbar-R Historical Parameters"
        )

        self.setMinimumWidth(560)

        self._setup_ui()

    # ==========================================
    # 4. SETUP USER INTERFACE
    # ==========================================

    def _setup_ui(self):

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # ======================================
        # HEADER
        # ======================================

        heading = QLabel(
            "XBAR-R — HISTORICAL CONTROL LIMITS"
        )

        heading.setStyleSheet(
            "font-weight: 600; font-size: 14px;"
        )

        layout.addWidget(heading)

        explanation = QLabel(
            f"Ukuran subgroup yang dipilih: "
            f"{self.subgroup_size}. "
            "Pilih apakah worksheet berisi data historis "
            "untuk mengestimasi parameter, atau data baru "
            "untuk dipantau menggunakan parameter "
            "historis yang sudah ada."
        )

        explanation.setWordWrap(True)
        layout.addWidget(explanation)

        # ======================================
        # ANALYSIS MODE
        # ======================================

        source_group = QGroupBox(
            "Analysis Mode"
        )

        source_layout = QFormLayout(
            source_group
        )

        self.mode_combo = QComboBox(self)

        self.mode_combo.addItem(
            "Estimate from current worksheet "
            "(historical data)",
            "estimate",
        )

        self.mode_combo.addItem(
            "Monitor using manually entered "
            "historical mean/sigma",
            "manual",
        )

        # Previous reference is only available
        # when matching historical limits exist.

        if self._previous_limits is not None:

            self.mode_combo.addItem(
                "Monitor using previous "
                "historical parameters",
                "reuse",
            )

            self.mode_combo.setCurrentIndex(2)

        source_layout.addRow(
            "Method:",
            self.mode_combo,
        )

        layout.addWidget(source_group)

        # ======================================
        # ESTIMATION INFORMATION
        # ======================================

        self.estimate_note = QLabel(
            "Estimate: parameter dan batas kendali "
            "dihitung dari worksheet saat ini. "
            "Dataset ini diperlakukan sebagai "
            "historical reference, BUKAN "
            "monitoring Phase II."
        )

        self.estimate_note.setWordWrap(True)

        layout.addWidget(
            self.estimate_note
        )

        # ======================================
        # MANUAL HISTORICAL PARAMETERS
        # ======================================

        self.manual_group = QGroupBox(
            "Manual Historical Parameters"
        )

        manual_form = QFormLayout(
            self.manual_group
        )

        self.mean_input = QLineEdit(self)

        self.mean_input.setPlaceholderText(
            "Contoh: 10.0"
        )

        self.sigma_input = QLineEdit(self)

        self.sigma_input.setPlaceholderText(
            "Contoh: 0.5"
        )

        manual_form.addRow(
            "Historical mean (μ):",
            self.mean_input,
        )

        manual_form.addRow(
            "Historical sigma (σ):",
            self.sigma_input,
        )

        manual_info = QLabel(
            "Sigma harus positif. Nilai ini merupakan "
            "standard deviation proses (within sigma), "
            "bukan Rbar. Batas kendali tidak dihitung "
            "ulang dari data baru."
        )

        manual_info.setWordWrap(True)

        manual_form.addRow(
            manual_info
        )

        layout.addWidget(
            self.manual_group
        )

        # ======================================
        # PREVIOUS HISTORICAL PARAMETERS
        # ======================================

        self.previous_group = QGroupBox(
            "Previous Historical Parameters"
        )

        previous_form = QFormLayout(
            self.previous_group
        )

        previous = self._previous_limits

        if previous is not None:

            previous_form.addRow(
                "Historical mean:",
                QLabel(
                    f"{previous.historical_mean:.12g}"
                ),
            )

            previous_form.addRow(
                "Historical sigma:",
                QLabel(
                    f"{previous.historical_sigma:.12g}"
                ),
            )

            previous_form.addRow(
                "Reference source:",
                QLabel(previous.source),
            )

        layout.addWidget(
            self.previous_group
        )

        # ======================================
        # SPC TEST CONFIGURATION
        # ======================================

        rules_group = QGroupBox(
            "SPC Tests"
        )

        rules_layout = QVBoxLayout(
            rules_group
        )

        self.profile_combo = QComboBox(self)

        for identifier in (
            RULE_PROFILE_STANDARD,
            RULE_PROFILE_MINITAB18_OBSERVED,
        ):

            self.profile_combo.addItem(
                RULE_PROFILE_LABELS[identifier],
                identifier,
            )

        rules_layout.addWidget(
            QLabel("Rule profile:")
        )

        rules_layout.addWidget(
            self.profile_combo
        )

        # ======================================
        # SPC TEST CHECKBOXES
        # ======================================

        self.test_checkboxes = {}

        for test in (1, 2, 3, 4):

            checkbox = QCheckBox(self)

            # Test 1 enabled by default.
            checkbox.setChecked(
                test == 1
            )

            self.test_checkboxes[test] = checkbox

            rules_layout.addWidget(
                checkbox
            )

        self.profile_note = QLabel()

        self.profile_note.setWordWrap(True)

        rules_layout.addWidget(
            self.profile_note
        )

        layout.addWidget(
            rules_group
        )

        # ======================================
        # ACTION BUTTONS
        # ======================================

        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )

        self.buttons.button(
            QDialogButtonBox.StandardButton.Ok
        ).setText(
            "Run Analysis"
        )

        self.buttons.accepted.connect(
            self._validate_and_accept
        )

        self.buttons.rejected.connect(
            self.reject
        )

        layout.addWidget(
            self.buttons
        )

        # ======================================
        # UI SIGNALS
        # ======================================

        self.mode_combo.currentIndexChanged.connect(
            self._update_mode
        )

        self.profile_combo.currentIndexChanged.connect(
            self._update_rule_labels
        )

        self._update_mode()
        self._update_rule_labels()

    # ==========================================
    # 5. UPDATE ANALYSIS MODE
    # ==========================================

    def _update_mode(self, _index=None):

        mode = self.mode_combo.currentData()

        self.estimate_note.setVisible(
            mode == "estimate"
        )

        self.manual_group.setVisible(
            mode == "manual"
        )

        self.previous_group.setVisible(
            mode == "reuse"
        )

    # ==========================================
    # 6. UPDATE SPC RULE LABELS
    # ==========================================

    def _update_rule_labels(self, _index=None):

        profile = self.profile_combo.currentData()

        windows = get_rule_windows(
            profile
        )

        labels = {
            1: (
                "Test 1 — One point beyond "
                "control limits"
            ),
            2: (
                "Test 2 — 9 consecutive points "
                "on one side of CL"
            ),
            3: (
                f"Test 3 — {windows[3]} consecutive "
                "points trending"
            ),
            4: (
                f"Test 4 — {windows[4]} consecutive "
                "alternating points"
            ),
        }

        for test, label in labels.items():

            self.test_checkboxes[test].setText(
                label
            )

        if profile == RULE_PROFILE_MINITAB18_OBSERVED:

            self.profile_note.setText(
                "Experimental 7/15 profile: "
                "belum tervalidasi sebagai "
                "konfigurasi default Minitab."
            )

        else:

            self.profile_note.setText(
                "Standard StatDesk profile: "
                "6-point trend / "
                "14-point alternating."
            )

    # ==========================================
    # 7. NUMERICAL INPUT VALIDATION
    # ==========================================

    @classmethod
    def _parse_number(
        cls,
        text: str,
        label: str,
    ) -> float:

        raw = text.strip()

        if not cls.NUMBER_PATTERN.fullmatch(raw):

            raise ValueError(
                f"{label} harus angka yang valid."
            )

        try:

            number = float(
                raw.replace(",", ".")
            )

        except (
            ValueError,
            OverflowError,
        ) as exc:

            raise ValueError(
                f"{label} tidak dapat dikonversi."
            ) from exc

        if not isfinite(number):

            raise ValueError(
                f"{label} tidak boleh NaN/Infinity."
            )

        return number

    # ==========================================
    # 8. VALIDATE AND ACCEPT
    # ==========================================

    def _validate_and_accept(self):

        # ======================================
        # SELECT ENABLED SPC TESTS
        # ======================================

        tests = tuple(
            test
            for test in (1, 2, 3, 4)
            if self.test_checkboxes[test].isChecked()
        )

        if not tests:

            QMessageBox.warning(
                self,
                "SPC Tests",
                "Pilih minimal satu SPC Test.",
            )

            return

        mode = self.mode_combo.currentData()

        profile = self.profile_combo.currentData()

        try:

            # ==================================
            # ESTIMATE HISTORICAL PARAMETERS
            # ==================================

            if mode == "estimate":

                # The MainWindow will use the
                # current worksheet to estimate
                # historical parameters.

                limits = None

            # ==================================
            # MANUAL HISTORICAL PARAMETERS
            # ==================================

            elif mode == "manual":

                mean = self._parse_number(
                    self.mean_input.text(),
                    "Historical mean",
                )

                sigma = self._parse_number(
                    self.sigma_input.text(),
                    "Historical sigma",
                )

                # Use the statistical engine.
                # Do not duplicate control-limit
                # calculations inside the GUI.

                limits = create_xbar_r_historical_limits(
                    subgroup_size=self.subgroup_size,
                    historical_mean=mean,
                    historical_sigma=sigma,
                )

            # ==================================
            # REUSE PREVIOUS PARAMETERS
            # ==================================

            elif (
                mode == "reuse"
                and self._previous_limits is not None
            ):

                limits = self._previous_limits

            else:

                raise ValueError(
                    "Metode analisis tidak tersedia."
                )

        except (
            ValueError,
            Phase2Error,
            OverflowError,
        ) as exc:

            QMessageBox.warning(
                self,
                "Historical Parameters",
                str(exc),
            )

            return

        # ======================================
        # STORE VALIDATED CONFIGURATION
        # ======================================

        self._selection = XbarRPhase2Selection(
            mode=mode,
            subgroup_size=self.subgroup_size,
            historical_limits=limits,
            enabled_tests=tests,
            rule_profile=profile,
        )

        self.accept()

    # ==========================================
    # 9. RETURN CONFIGURATION
    # ==========================================

    def configuration(self) -> XbarRPhase2Selection:
        """Return validated configuration after acceptance."""

        if self._selection is None:

            raise RuntimeError(
                "Dialog belum menghasilkan konfigurasi."
            )

        return self._selection
