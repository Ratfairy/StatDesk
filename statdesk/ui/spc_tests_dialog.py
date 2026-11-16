
"""SPC Rules 1–4 selection dialog."""

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QVBoxLayout,
)

from statdesk.statistics.spc_rules import (
    RULE_PROFILE_STANDARD,
    RULE_PROFILE_MINITAB18_OBSERVED,
    get_rule_windows,
)


class SpcTestsDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle(
            "StatDesk — SPC Special-Cause Tests"
        )
        self.setMinimumWidth(540)

        layout = QVBoxLayout(self)

        info = QLabel(
            "Pilih profil statistik dan SPC Tests.\n"
            "Test 1 tetap wajib aktif pada mode Advanced ini."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        # RULE PROFILE
        layout.addWidget(QLabel("Rule Profile:"))

        self.profile_combo = QComboBox()
        self.profile_combo.addItem(
            "StatDesk — 6-point trend / 14-point alternating",
            RULE_PROFILE_STANDARD,
        )
        self.profile_combo.addItem(
            "Minitab 18 observed — 7/15 (experimental)",
            RULE_PROFILE_MINITAB18_OBSERVED,
        )
        layout.addWidget(self.profile_combo)

        self.profile_note = QLabel()
        self.profile_note.setWordWrap(True)
        layout.addWidget(self.profile_note)

        # TEST SELECTION
        self.checkboxes = {}

        definitions = {
            1: "Test 1 — One point beyond control limits",
            2: "Test 2 — Nine points on one side of CL",
            3: "",
            4: "",
        }

        for number, description in definitions.items():
            checkbox = QCheckBox(description)

            if number == 1:
                checkbox.setChecked(True)
                checkbox.setEnabled(False)
            else:
                checkbox.setChecked(False)

            self.checkboxes[number] = checkbox
            layout.addWidget(checkbox)

        self.profile_combo.currentIndexChanged.connect(
            self._update_profile_labels
        )
        self._update_profile_labels()

        warning = QLabel(
            "\nLebih banyak SPC Tests dapat meningkatkan "
            "sensitivitas sekaligus risiko false alarm.\n"
            "Control limits tetap berasal dari Phase I. "
            "Hasil perlu investigasi dan review QC/QA."
        )
        warning.setWordWrap(True)
        layout.addWidget(warning)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )

        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _update_profile_labels(self, _index=None):
        profile = self.rule_profile()
        windows = get_rule_windows(profile)

        self.checkboxes[3].setText(
            f"Test 3 — {windows[3]} consecutive points "
            "increasing or decreasing"
        )

        self.checkboxes[4].setText(
            f"Test 4 — {windows[4]} consecutive points "
            "alternating up and down"
        )

        if profile == RULE_PROFILE_STANDARD:
            note = (
                "Default StatDesk: mempertahankan aturan "
                "6/14 dari versi sebelumnya."
            )
        else:
            note = (
                "EXPERIMENTAL: mengikuti jumlah titik yang "
                "diamati pada pengujian Minitab 18. "
                "Belum menjamin kompatibilitas penuh."
            )

        self.profile_note.setText(note)

    def rule_profile(self):
        return self.profile_combo.currentData()

    def enabled_tests(self):
        return tuple(
            number
            for number, checkbox in self.checkboxes.items()
            if checkbox.isChecked()
        )
