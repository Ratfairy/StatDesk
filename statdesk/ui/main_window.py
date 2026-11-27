"""StatDesk desktop: worksheet, statistics, graphs and SPC."""

from pathlib import Path

from statdesk.statistics.capability_engine import (
    CapabilityEngine,
    CapabilityError,
    MAX_SUBGROUP_SIZE,
    format_capability_report,
)
from statdesk.statistics.capability_sixpack_report import (
    format_sixpack_spc_report,
)
from statdesk.statistics.anderson_darling_engine import (
    AndersonDarlingEngine,
    AndersonDarlingError,
    format_anderson_darling_report,
)

from statdesk.ui.capability_dialog import (
    CapabilityDialog,
)

from statdesk.visualization.capability_chart import (
    CapabilityChartError,
    create_capability_figure,
)

from statdesk.visualization.capability_sixpack_chart import (
    CapabilitySixpackError,
    create_capability_sixpack_figure,
)

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QInputDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QTextEdit,
    QTreeWidget,
    QTreeWidgetItem,
)

from statdesk.models.worksheet_model import WorksheetModel
from statdesk.services.data_io_service import DataIOError, DataIOService
from statdesk.services.subgroup_service import (
    SubgroupDataError,
    prepare_subgroups,
)
from statdesk.statistics.statistical_engine import (
    StatisticalEngine,
    StatisticalError,
    format_report,
)
from statdesk.statistics.spc_engine import (
    SpcEngine,
    SpcError,
    format_imr_report,
)
from statdesk.statistics.xbar_r_engine import XbarREngine, XbarRError
from statdesk.statistics.xbar_r_report import format_xbar_r_report
from statdesk.statistics.xbar_s_engine import (
    XbarSEngine,
    XbarSError,
    format_xbar_s_report,
)
from statdesk.statistics.spc_phase2 import (
    Phase2Error,
    estimate_xbar_r_historical_limits,
    monitor_xbar_r_phase2,
    format_xbar_r_historical_limits_report,
    format_phase2_xbar_r_report,
)
from statdesk.statistics.spc_rules_bridge import (
    evaluate_control_chart_rules,
    format_control_chart_rules_report,
)
from statdesk.ui.graph_window import GraphWindow
from statdesk.ui.worksheet_table import WorksheetTableView
from statdesk.ui.subgroup_columns_dialog import SubgroupColumnsDialog
from statdesk.ui.spc_tests_dialog import SpcTestsDialog
from statdesk.ui.xbar_r_phase2_dialog import XbarRPhase2Dialog
from statdesk.visualization.chart_engine import (
    ChartDataset,
    ChartEngine,
    ChartError,
)
from statdesk.visualization.spc_chart import create_imr_figure
from statdesk.visualization.xbar_r_chart import create_xbar_r_figure
from statdesk.visualization.xbar_r_phase2_chart import (
    create_xbar_r_phase2_figure,
    XbarRPhase2ChartError,
)
from statdesk.visualization.xbar_s_chart import (
    create_xbar_s_figure,
    XbarSChartError,
)
from statdesk.visualization.spc_rules_overlay import overlay_optional_rules

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.is_modified = False
        self.has_analysis = False
        self.graph_windows = []

        # R3.4: historical parameters are kept in memory
        # across worksheet edits and imports.
        self.xbar_r_historical_limits = None

        self.data_io = DataIOService()
        self.engine = StatisticalEngine()
        self.chart_engine = ChartEngine()
        self.spc_engine = SpcEngine()
        self.xbar_r_engine = XbarREngine()
        self.xbar_s_engine = XbarSEngine()

        # R4.4 — Normal Process Capability
        self.capability_engine = CapabilityEngine()

        self.setWindowTitle("StatDesk - Industrial Statistics")
        self.resize(1200, 750)
        self.setMinimumSize(850, 550)

        self.setup_ui()
        self.setup_menu()

        self.statusBar().showMessage(
            "StatDesk Ready | SPC Tests 1-4 v0.7.1"
        )

    # ==================================================
    # 1. SETUP USER INTERFACE
    # ==================================================

    def setup_ui(self):
        self.model = WorksheetModel(self)

        self.model.validation_error.connect(self.show_error)
        self.model.modified.connect(self.mark_modified)

        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        self.navigator = QTreeWidget()
        self.navigator.setHeaderLabel("Project Navigator")

        project = QTreeWidgetItem(["Project 1"])
        project.addChild(QTreeWidgetItem(["Worksheet 1"]))

        self.navigator.addTopLevelItem(project)
        self.navigator.expandAll()

        main_splitter.addWidget(self.navigator)

        workspace = QSplitter(Qt.Orientation.Vertical)

        self.table = WorksheetTableView()
        self.table.setModel(self.model)
        self.table.setAlternatingRowColors(True)

        self.table.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        self.table.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectItems
        )

        for index, width in enumerate((220, 150, 180)):
            self.table.setColumnWidth(index, width)

        self.table.verticalHeader().setDefaultSectionSize(28)
        workspace.addWidget(self.table)

        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.output.setLineWrapMode(QTextEdit.LineWrapMode.NoWrap)

        self.output.setPlainText(
            "StatDesk Statistical Analysis\n"
            "============================\n\n"
            "StatDesk v0.7.1 ready.\n"
            "Load data, then choose Statistics, "
            "Graph, or Quality."
        )

        workspace.addWidget(self.output)
        workspace.setSizes([500, 200])

        main_splitter.addWidget(workspace)
        main_splitter.setSizes([220, 980])

        self.setCentralWidget(main_splitter)

    # ==================================================
    # 2. SETUP MENUS
    # ==================================================

    def setup_menu(self):
        file_menu = self.menuBar().addMenu("File")
        data_menu = self.menuBar().addMenu("Data")
        statistics_menu = self.menuBar().addMenu("Statistics")
        graph_menu = self.menuBar().addMenu("Graph")
        quality_menu = self.menuBar().addMenu("Quality")

        def action(menu, text, callback, shortcut=None):
            item = QAction(text, self)

            if shortcut:
                item.setShortcut(shortcut)

            item.triggered.connect(callback)
            menu.addAction(item)
            return item

        # FILE
        import_action = action(
            file_menu,
            "Import Excel / CSV...",
            self.import_data,
            "Ctrl+O",
        )

        export_action = action(
            file_menu,
            "Export Excel / CSV...",
            self.export_data,
            "Ctrl+Shift+S",
        )

        file_menu.addSeparator()

        action(
            file_menu,
            "New / Clear Worksheet",
            self.clear_worksheet,
        )
        action(file_menu, "Exit", self.close)

        # DATA
        add_row = action(
            data_menu,
            "Add Rows...",
            self.add_rows,
        )

        action(
            data_menu,
            "Delete Selected Rows",
            self.delete_rows,
        )

        add_column = action(
            data_menu,
            "Add Column",
            self.add_column,
        )

        action(
            data_menu,
            "Delete Current Column",
            self.delete_column,
        )

        rename = action(
            data_menu,
            "Rename Current Column...",
            self.rename_column,
        )

        change_type = action(
            data_menu,
            "Set Column Type...",
            self.change_column_type,
        )

        data_menu.addSeparator()

        action(
            data_menu,
            "Load Sample Data",
            self.load_sample_data,
        )

        action(
            data_menu,
            "Clear Selected Cells (Delete)",
            self.table.clear_selected_cells,
        )

        # STATISTICS
        descriptive = action(
            statistics_menu,
            "Descriptive Statistics + Normality...",
            self.run_descriptive,
        )

        # GRAPH
        histogram = action(
            graph_menu,
            "Histogram...",
            lambda checked=False: self.run_chart(
                ChartEngine.HISTOGRAM
            ),
        )

        boxplot = action(
            graph_menu,
            "Boxplot...",
            lambda checked=False: self.run_chart(
                ChartEngine.BOXPLOT
            ),
        )

        probability = action(
            graph_menu,
            "Normal Probability Plot...",
            lambda checked=False: self.run_chart(
                ChartEngine.NORMAL_PROBABILITY
            ),
        )

        # QUALITY - PHASE I
        imr = action(
            quality_menu,
            "I-MR Control Chart (Phase I)...",
            self.run_imr,
        )

        xbar_r = action(
            quality_menu,
            "Xbar-R Control Chart (Phase I)...",
            self.run_xbar_r,
        )

        xbar_s = action(
            quality_menu,
            "Xbar-S Control Chart (Phase I)...",
            self.run_xbar_s,
        )

        # QUALITY - ADVANCED SPC TESTS
        quality_menu.addSeparator()

        action(
            quality_menu,
            "I-MR with SPC Tests 1-4...",
            lambda checked=False: self.run_spc_advanced("imr"),
        )

        action(
            quality_menu,
            "Xbar-R with SPC Tests 1-4...",
            lambda checked=False: self.run_spc_advanced("xbar_r"),
        )

        action(
            quality_menu,
            "Xbar-S with SPC Tests 1-4...",
            lambda checked=False: self.run_spc_advanced("xbar_s"),
        )

        # R3.4: HISTORICAL PARAMETERS / PHASE II
        quality_menu.addSeparator()

        action(
            quality_menu,
            "Xbar-R — Historical Parameters / Phase II...",
            self.run_xbar_r_phase2,
        )

        action(
            quality_menu,
            "Xbar-R — Clear Historical Parameters",
            self.clear_xbar_r_historical_limits,
        )

        quality_menu.addSeparator()

        capability_action = action(
            quality_menu,
            "Normal Process Capability Analysis...",
            self.run_normal_capability,
        )

        # R4.8.2 — Sixpack uses the same CapabilityDialog and engine.
        action(
            quality_menu,
            "Normal Capability Sixpack...",
            self.run_capability_sixpack,
        )

        # TOOLBAR
        toolbar = self.addToolBar("Worksheet Tools")
        toolbar.setMovable(False)

        for item in (
            import_action,
            export_action,
            add_row,
            add_column,
            rename,
            change_type,
            descriptive,
            histogram,
            boxplot,
            probability,
            imr,
            xbar_r,
            xbar_s,
            capability_action,
        ):
            toolbar.addAction(item)

    # ==================================================
    # 3. WORKSHEET STATE
    # ==================================================

    def mark_modified(self):
        self.is_modified = True

        self.setWindowTitle(
            "StatDesk * - Industrial Statistics"
        )

        for graph in list(self.graph_windows):
            graph.mark_stale()

        if self.has_analysis:
            self.output.append(
                "\n[WARNING] Worksheet berubah. "
                "Analisis/grafik lama menggunakan "
                "snapshot sebelumnya. "
                "Jalankan ulang analisis.\n"
            )
            self.has_analysis = False

        # Do not delete self.xbar_r_historical_limits here.
        # Existing historical parameters may be intentionally
        # reused for a new monitoring worksheet.

    def show_error(self, message):
        QMessageBox.warning(
            self,
            "StatDesk",
            str(message),
        )

    def confirm_replace(self):
        if not self.model.has_data():
            return True

        answer = QMessageBox.question(
            self,
            "Ganti Worksheet",
            "Data worksheet saat ini akan diganti. Lanjutkan?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        return answer == QMessageBox.StandardButton.Yes

    # ==================================================
    # 4. IMPORT DATA
    # ==================================================

    def import_data(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import Dataset",
            "",
            "Supported Data (*.xlsx *.csv);;"
            "Excel Workbook (*.xlsx);;"
            "CSV UTF-8 (*.csv)",
        )

        if not path or not self.confirm_replace():
            return

        try:
            sheet = None

            if Path(path).suffix.lower() == ".xlsx":
                names = self.data_io.sheet_names(path)

                if len(names) > 1:
                    sheet, ok = QInputDialog.getItem(
                        self,
                        "Pilih Excel Worksheet",
                        "Nama sheet:",
                        names,
                        0,
                        False,
                    )
                    if not ok:
                        return

            answer = QMessageBox.question(
                self,
                "Header Dataset",
                "Apakah baris pertama berisi nama kolom?\n\n"
                "Yes: baris pertama menjadi header.\n"
                "No: baris pertama dianggap data.",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Yes,
            )

            if answer == QMessageBox.StandardButton.Cancel:
                return

            dataset = self.data_io.import_file(
                path,
                has_header=(
                    answer == QMessageBox.StandardButton.Yes
                ),
                sheet_name=sheet,
            )

            self.model.replace_dataset(dataset)

        except (DataIOError, ValueError) as exc:
            self.show_error(str(exc))
            return

        self.has_analysis = False

        self.output.setPlainText(
            f"IMPORT: {Path(path).name}\n"
            f"Records: {len(dataset.rows)} | "
            f"Columns: {len(dataset.columns)}\n"
            "Numeric columns: "
            f"{sum(c.data_type == 'numeric' for c in dataset.columns)}\n"
            "Choose Statistics, Graph, or Quality to analyze the dataset."
        )

        self.statusBar().showMessage(
            f"Berhasil import: {Path(path).name}"
        )

    # ==================================================
    # 5. EXPORT DATA
    # ==================================================

    def export_data(self):
        path, selected = QFileDialog.getSaveFileName(
            self,
            "Export Dataset",
            "StatDesk_Export.xlsx",
            "Excel Workbook (*.xlsx);;"
            "CSV UTF-8 (*.csv)",
        )

        if not path:
            return

        expected = ".csv" if "CSV" in selected else ".xlsx"

        if not Path(path).suffix:
            path += expected
        elif Path(path).suffix.lower() in (".xlsx", ".csv"):
            path = str(Path(path).with_suffix(expected))

        if Path(path).suffix.lower() not in (".xlsx", ".csv"):
            self.show_error(
                "Gunakan ekstensi .xlsx atau .csv."
            )
            return

        try:
            count = self.data_io.export_file(
                path,
                self.model,
            )

        except DataIOError as exc:
            self.show_error(str(exc))
            return

        self.output.append(
            f"\nEXPORT: {path}\nRecords: {count}"
        )

        self.statusBar().showMessage(
            f"Berhasil export: {path}"
        )

        QMessageBox.information(
            self,
            "Export selesai",
            f"File berhasil disimpan:\n{path}",
        )

    # ==================================================
    # 6. NUMERIC COLUMN SELECTION
    # ==================================================

    def choose_numeric_column(self):
        numeric_columns = [
            (idx, col.name)
            for idx, col in enumerate(self.model.columns)
            if col.data_type == "numeric"
        ]

        if not numeric_columns:
            self.show_error(
                "Tidak ada kolom Numeric. "
                "Gunakan Data > Set Column Type."
            )
            return None

        labels = [
            f"C{idx + 1} - {name}"
            for idx, name in numeric_columns
        ]

        selected, ok = QInputDialog.getItem(
            self,
            "Select Numeric Column",
            "Pilih kolom Numeric:",
            labels,
            0,
            False,
        )

        if not ok:
            return None

        col_index, col_name = numeric_columns[
            labels.index(selected)
        ]

        _, rows = self.model.export_snapshot()

        values = [
            row[col_index]
            for row in rows
        ]

        return col_name, values

    # ==================================================
    # 7. DESCRIPTIVE STATISTICS
    # ==================================================

    def run_descriptive(self):
        selection = self.choose_numeric_column()

        if selection is None:
            return

        name, values = selection

        try:
            result = self.engine.describe(
                values,
                name,
                alpha=0.05,
            )

        except StatisticalError as exc:
            self.show_error(str(exc))
            return

        self.output.append(
            "\n" + format_report(result) + "\n"
        )

        self.has_analysis = True

        self.statusBar().showMessage(
            f"Analisis selesai: {name} | N={result.n_valid}"
        )

    # ==================================================
    # 8. GRAPH WINDOW MANAGEMENT
    # ==================================================

    def _show_graph(self, figure, chart_type, dataset):
        window = GraphWindow(
            self,
            figure,
            chart_type,
            dataset,
        )

        window.closed.connect(
            self.remove_graph_window
        )

        self.graph_windows.append(window)
        window.show()

        return window

    def remove_graph_window(self, window):
        if window in self.graph_windows:
            self.graph_windows.remove(window)

    # ==================================================
    # 9. HISTOGRAM / BOXPLOT / PROBABILITY PLOT
    # ==================================================

    def run_chart(self, chart_type):
        selection = self.choose_numeric_column()

        if selection is None:
            return

        name, values = selection

        try:
            dataset = self.chart_engine.prepare(
                values,
                name,
            )

            figure = self.chart_engine.create_figure(
                chart_type,
                dataset,
            )

        except (
            ChartError,
            ValueError,
            OverflowError,
        ) as exc:
            self.show_error(str(exc))
            return

        self._show_graph(
            figure,
            chart_type,
            dataset,
        )

        self.has_analysis = True

        label = GraphWindow.GRAPH_LABELS.get(
            chart_type,
            chart_type,
        )

        self.output.append(
            f"\nGRAPH: {label} | "
            f"Column: {name} | "
            f"N={dataset.n} | "
            f"Missing={dataset.missing_rows}"
        )

        self.statusBar().showMessage(
            f"Grafik dibuat: {label}"
        )

    # ==================================================
    # 10. I-MR CONTROL CHART
    # ==================================================

    def run_imr(self):
        selection = self.choose_numeric_column()

        if selection is None:
            return

        name, values = selection

        try:
            result = self.spc_engine.calculate_imr(
                values,
                name,
            )

            figure = create_imr_figure(result)

            dataset = self.chart_engine.prepare(
                values,
                name,
            )

        except (
            SpcError,
            ChartError,
            ValueError,
            OverflowError,
        ) as exc:
            self.show_error(str(exc))
            return

        self._show_graph(
            figure,
            "I-MR Control Chart",
            dataset,
        )

        self.output.append(
            "\n" + format_imr_report(result) + "\n"
        )

        self.has_analysis = True

        self.statusBar().showMessage(
            f"I-MR: N={result.n} | "
            f"I signals={len(result.i_violations)} | "
            f"MR signals={len(result.mr_violations)}"
        )

    # ==================================================
    # 11. SUBGROUP SELECTION
    # ==================================================

    def _select_subgroups(
        self,
        *,
        chart_name,
        min_columns,
        max_columns,
        min_subgroups=2,
    ):
        """
        Select rational subgroups from worksheet columns.
        One worksheet row = one subgroup.
        """

        numeric_count = sum(
            col.data_type == "numeric"
            for col in self.model.columns
        )

        if numeric_count < min_columns:
            self.show_error(
                f"{chart_name} memerlukan "
                f"{min_columns}–{max_columns} "
                "kolom pengukuran Numeric."
            )
            return None

        dialog = SubgroupColumnsDialog(
            self,
            self.model.columns,
            chart_name=chart_name,
            min_columns=min_columns,
            max_columns=max_columns,
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        indexes = dialog.selected_column_indexes()
        columns, rows = self.model.export_snapshot()

        try:
            subgroups = prepare_subgroups(
                columns,
                rows,
                indexes,
                min_columns=min_columns,
                max_columns=max_columns,
                min_subgroups=min_subgroups,
            )

        except SubgroupDataError as exc:
            self.show_error(str(exc))
            return None

        ordered_indexes = sorted(indexes)

        names = [
            columns[index].name
            for index in ordered_indexes
        ]

        confirmation = QMessageBox.question(
            self,
            "Konfirmasi Rational Subgroup",
            "Kolom pengukuran:\n  - "
            + "\n  - ".join(names)
            + "\n\nSetiap baris berisi pengukuran "
            "karakteristik kualitas yang SAMA pada "
            "satu waktu/kondisi produksi. "
            "Baris berurutan dari waktu terlama "
            "ke terbaru. "
            "Kolom Batch/ID/tanggal tidak ikut "
            "dihitung.\n\n"
            "Lanjutkan analisis?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if confirmation != QMessageBox.StandardButton.Yes:
            return None

        return subgroups, names

    @staticmethod
    def _subgroup_dataset(subgroups, chart_name):
        flattened = tuple(
            value
            for group in subgroups
            for value in group
        )

        return ChartDataset(
            column_name=(
                f"{chart_name} subgroup measurements"
            ),
            values=flattened,
            total_rows=len(flattened),
            missing_rows=0,
        )

    # ==================================================
    # 12. XBAR-R PHASE I
    # ==================================================

    def run_xbar_r(self):
        selection = self._select_subgroups(
            chart_name="Xbar-R",
            min_columns=2,
            max_columns=8,
        )

        if selection is None:
            return

        subgroups, names = selection

        try:
            result = self.xbar_r_engine.calculate(
                subgroups
            )

            figure = create_xbar_r_figure(result)

            dataset = self._subgroup_dataset(
                subgroups,
                "Xbar-R",
            )

        except (
            XbarRError,
            ValueError,
            OverflowError,
        ) as exc:
            self.show_error(str(exc))
            return

        self._show_graph(
            figure,
            "Xbar-R Control Chart",
            dataset,
        )

        self.output.append(
            "\n"
            + format_xbar_r_report(result, names)
            + "\n"
        )

        self.has_analysis = True

        self.statusBar().showMessage(
            f"Xbar-R: {result.subgroup_count} "
            f"subgrup × {result.subgroup_size} | "
            f"R signals={len(result.range_signals)} | "
            f"Xbar signals={len(result.mean_signals)}"
        )

    # ==================================================
    # 13. XBAR-S PHASE I
    # ==================================================

    def run_xbar_s(self):
        selection = self._select_subgroups(
            chart_name="Xbar-S",
            min_columns=9,
            max_columns=25,
        )

        if selection is None:
            return

        subgroups, _names = selection

        try:
            result = self.xbar_s_engine.calculate(
                subgroups
            )

            figure = create_xbar_s_figure(result)

            dataset = self._subgroup_dataset(
                subgroups,
                "Xbar-S",
            )

        except (
            XbarSError,
            XbarSChartError,
            ValueError,
            OverflowError,
        ) as exc:
            self.show_error(str(exc))
            return

        self._show_graph(
            figure,
            "Xbar-S Control Chart",
            dataset,
        )

        self.output.append(
            "\n" + format_xbar_s_report(result) + "\n"
        )

        self.has_analysis = True

        self.statusBar().showMessage(
            f"Xbar-S: {result.subgroup_count} "
            f"subgrup × {result.subgroup_size} | "
            f"S signals={len(result.s_signals)} | "
            f"Xbar signals={len(result.xbar_signals)}"
        )

    # ==================================================
    # 14. ADVANCED SPC TESTS 1–4
    # ==================================================

    def run_spc_advanced(self, kind):
        if kind not in ("imr", "xbar_r", "xbar_s"):
            self.show_error(
                "Jenis SPC analysis tidak dikenal."
            )
            return

        dialog = SpcTestsDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        enabled_tests = dialog.enabled_tests()
        rule_profile = dialog.rule_profile()

        try:
            if kind == "imr":
                selection = self.choose_numeric_column()

                if selection is None:
                    return

                name, values = selection

                result = self.spc_engine.calculate_imr(
                    values,
                    name,
                )

                figure = create_imr_figure(result)

                dataset = self.chart_engine.prepare(
                    values,
                    name,
                )

                original_report = format_imr_report(
                    result
                )

                chart_name = "I-MR Control Chart"

            elif kind == "xbar_r":
                selection = self._select_subgroups(
                    chart_name="Xbar-R",
                    min_columns=2,
                    max_columns=8,
                )

                if selection is None:
                    return

                subgroups, names = selection

                result = self.xbar_r_engine.calculate(
                    subgroups
                )

                figure = create_xbar_r_figure(
                    result
                )

                dataset = self._subgroup_dataset(
                    subgroups,
                    "Xbar-R",
                )

                original_report = format_xbar_r_report(
                    result,
                    names,
                )

                chart_name = "Xbar-R Control Chart"

            else:
                selection = self._select_subgroups(
                    chart_name="Xbar-S",
                    min_columns=9,
                    max_columns=25,
                )

                if selection is None:
                    return

                subgroups, _names = selection

                result = self.xbar_s_engine.calculate(
                    subgroups
                )

                figure = create_xbar_s_figure(
                    result
                )

                dataset = self._subgroup_dataset(
                    subgroups,
                    "Xbar-S",
                )

                original_report = format_xbar_s_report(
                    result
                )

                chart_name = "Xbar-S Control Chart"

            assessment = evaluate_control_chart_rules(
                kind,
                result,
                enabled_tests=enabled_tests,
                rule_profile=rule_profile,
            )

            overlay_optional_rules(
                figure,
                assessment,
            )

            rules_report = format_control_chart_rules_report(
                assessment
            )

        except (
            SpcError,
            XbarRError,
            XbarSError,
            XbarSChartError,
            ChartError,
            ValueError,
            OverflowError,
        ) as exc:
            self.show_error(str(exc))
            return

        self._show_graph(
            figure,
            chart_name,
            dataset,
        )

        self.output.append(
            "\n"
            + original_report
            + "\n\n"
            + rules_report
            + "\n"
        )

        self.has_analysis = True

        finding_count = (
            len(assessment.upper.result.findings)
            + len(assessment.lower.result.findings)
        )

        self.statusBar().showMessage(
            f"{assessment.chart_name} | "
            f"Tests {enabled_tests} | "
            f"Profile: {rule_profile} | "
            f"Rule findings: {finding_count}"
        )

    # ==================================================
    # 15. R3.4 — XBAR-R HISTORICAL / PHASE II
    # ==================================================

    def run_xbar_r_phase2(self):
        """
        Analysis modes:

        estimate:
            Use current worksheet as historical data.
            Calculate and store historical parameters.

        manual:
            Use current worksheet as monitoring data.
            Enter historical mean and sigma manually.

        reuse:
            Use current worksheet as monitoring data.
            Reuse previously estimated historical limits.
        """

        selection = self._select_subgroups(
            chart_name="Xbar-R Historical Parameters / Phase II",
            min_columns=2,
            max_columns=8,
            # Allow a single monitoring subgroup. Estimate mode still
            # checks its minimum count in the statistical engine.
            min_subgroups=1,
        )

        if selection is None:
            return

        subgroups, column_names = selection

        subgroup_size = len(subgroups[0])

        try:
            dialog = XbarRPhase2Dialog(
                subgroup_size=subgroup_size,
                historical_limits=self.xbar_r_historical_limits,
                parent=self,
            )

        except (TypeError, ValueError) as exc:
            self.show_error(str(exc))
            return

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        configuration = dialog.configuration()

        # --------------------------------------
        # A. ESTIMATE HISTORICAL PARAMETERS
        # --------------------------------------

        if configuration.mode == "estimate":
            try:
                limits = estimate_xbar_r_historical_limits(
                    subgroups,
                    enabled_tests=configuration.enabled_tests,
                    rule_profile=configuration.rule_profile,
                )

                # Historical data uses the existing
                # Xbar-R Phase I figure.
                historical_result = self.xbar_r_engine.calculate(
                    subgroups
                )

                figure = create_xbar_r_figure(
                    historical_result
                )

                dataset = self._subgroup_dataset(
                    subgroups,
                    "Xbar-R Historical",
                )

                report = format_xbar_r_historical_limits_report(
                    limits
                )

            except (
                Phase2Error,
                XbarRError,
                ValueError,
                OverflowError,
            ) as exc:
                self.show_error(str(exc))
                return

            # Save statistical parameters in memory.
            # Importing another worksheet does not clear them.
            self.xbar_r_historical_limits = limits

            self._show_graph(
                figure,
                "Xbar-R Historical Data (Phase I)",
                dataset,
            )

            self.output.append(
                "\n"
                + report
                + "\nHistorical columns: "
                + ", ".join(column_names)
                + "\n"
                "Chart: Phase I historical overview. "
                "Historical SPC findings are listed above.\n"
                "Import new monitoring data and choose "
                "Reuse Previous Historical Parameters "
                "to run Phase II.\n"
            )

            self.has_analysis = True

            self.statusBar().showMessage(
                "Xbar-R: historical parameters estimated "
                f"from {limits.subgroup_count} subgroups; "
                "available for Phase II monitoring"
            )

            return

        # --------------------------------------
        # B. MANUAL OR REUSE HISTORICAL LIMITS
        # --------------------------------------

        if configuration.mode not in ("manual", "reuse"):
            self.show_error(
                "Metode Phase II tidak dikenal."
            )
            return

        try:
            limits = configuration.historical_limits

            if limits is None:
                raise Phase2Error(
                    "Historical mean/sigma belum tersedia."
                )

            # Calculate monitoring subgroup mean/range
            # and test against frozen historical limits.
            result = monitor_xbar_r_phase2(
                limits,
                subgroups,
                enabled_tests=configuration.enabled_tests,
                rule_profile=configuration.rule_profile,
            )

            figure = create_xbar_r_phase2_figure(
                result
            )

            dataset = self._subgroup_dataset(
                subgroups,
                "Xbar-R Phase II",
            )

            report = format_phase2_xbar_r_report(
                result
            )

        except (
            Phase2Error,
            XbarRPhase2ChartError,
            ValueError,
            OverflowError,
        ) as exc:
            self.show_error(str(exc))
            return

        # Store the reference to allow reuse.
        self.xbar_r_historical_limits = limits

        self._show_graph(
            figure,
            "Xbar-R Control Chart (Phase II)",
            dataset,
        )

        self.output.append(
            "\n"
            + report
            + "\nMeasurement columns: "
            + ", ".join(column_names)
            + "\n"
        )

        self.has_analysis = True

        n_signals = (
            len(result.xbar_rules.findings)
            + len(result.r_rules.findings)
        )

        self.statusBar().showMessage(
            f"Xbar-R Phase II: {len(result.means)} subgroups | "
            f"SPC findings: {n_signals} | "
            "Historical limits unchanged"
        )

    # ==================================================
    # 16. CLEAR HISTORICAL PARAMETERS
    # ==================================================

    def clear_xbar_r_historical_limits(self):
        """
        Clear previously calculated historical parameters.
        The current worksheet and existing graphs are unchanged.
        """

        if self.xbar_r_historical_limits is None:
            self.statusBar().showMessage(
                "Belum ada historical parameters tersimpan."
            )
            return

        answer = QMessageBox.question(
            self,
            "Clear Historical Parameters",
            "Hapus historical parameters Xbar-R dari memori?\n"
            "Grafik dan Session Output yang sudah dibuat "
            "tidak akan berubah.",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer != QMessageBox.StandardButton.Yes:
            return

        self.xbar_r_historical_limits = None

        self.output.append(
            "\nXbar-R: historical parameters in-memory cleared.\n"
        )

        self.statusBar().showMessage(
            "Xbar-R historical parameters dihapus dari memori."
        )

    # ==================================================
    # 17. CURRENT COLUMN
    # ==================================================

    def current_column(self):
        index = self.table.currentIndex()

        if not index.isValid():
            QMessageBox.information(
                self,
                "Pilih Kolom",
                "Klik sel pada kolom yang ingin diubah.",
            )
            return None

        return index.column()

    # ==================================================
    # R4.4 — NORMAL PROCESS CAPABILITY ANALYSIS
    # ==================================================

    def run_normal_capability(self):
        """Keep R4.7 Normal Capability as the default analysis."""
        self._run_capability_analysis(sixpack=False)

    def run_capability_sixpack(self):
        """Open the same dialog and render the R4.8 six-panel report."""
        self._run_capability_analysis(sixpack=True)

    def _run_capability_analysis(self, *, sixpack):
        """
        Normal Process Capability Analysis.

        Flow:
        1. Select data layout and measurement columns.
        2. Read worksheet snapshot.
        3. Validate measurements.
        4. Calculate capability indices.
        5. Generate Capability Histogram.
        6. Display Session Output.

        Statistical calculations belong to CapabilityEngine.
        Existing SPC engines remain unchanged.
        """

        # ==========================================
        # 1. CHECK NUMERIC COLUMNS
        # ==========================================

        numeric_columns = [
            column
            for column in self.model.columns
            if column.data_type == "numeric"
        ]

        if not numeric_columns:
            self.show_error(
                "Tidak ada kolom Numeric untuk "
                "Process Capability Analysis.\n\n"
                "Gunakan Data > Set Column Type "
                "untuk mengubah tipe kolom."
            )
            return

        # ==========================================
        # 2. OPEN CAPABILITY DIALOG
        # ==========================================

        try:
            dialog = CapabilityDialog(
                self,
                self.model.columns,
            )

        except (TypeError, ValueError) as exc:
            self.show_error(str(exc))
            return

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        try:
            configuration = dialog.configuration()

        except ValueError as exc:
            self.show_error(str(exc))
            return

        # ==========================================
        # 3. READ WORKSHEET SNAPSHOT
        # ==========================================

        columns, rows = self.model.export_snapshot()

        if not rows:
            self.show_error(
                "Worksheet belum memiliki data "
                "pengukuran untuk dianalisis."
            )
            return

        # ==========================================
        # 4. CALCULATE NORMAL CAPABILITY
        # ==========================================

        try:

            # --------------------------------------
            # A. INDIVIDUAL OBSERVATIONS
            # --------------------------------------

            if configuration.layout == "individuals":

                column_index = (
                    configuration.selected_indexes[0]
                )

                values = []

                for row_number, row in enumerate(
                    rows,
                    start=1,
                ):

                    raw_value = row[column_index]

                    if raw_value is None:

                        raise CapabilityError(
                            f"Baris {row_number}, "
                            f"kolom "
                            f"{columns[column_index].name}: "
                            "pengukuran kosong.\n\n"
                            "Normal Capability Individuals "
                            "tidak melewati missing value "
                            "secara otomatis."
                        )

                    values.append(raw_value)

                result = (
                    self.capability_engine.calculate_individuals(
                        values,
                        configuration.column_name,

                        lsl=configuration.lsl,
                        usl=configuration.usl,
                        target=configuration.target,

                        use_unbiasing_overall=(
                            configuration.use_unbiasing_overall
                        ),
                    )
                )

            # --------------------------------------
            # B. RATIONAL SUBGROUPS
            # --------------------------------------

            elif configuration.layout == "subgroups":

                selected_indexes = (
                    configuration.selected_indexes
                )

                # Sixpack SPC engines support subgroup sizes 2–25;
                # standalone Normal Capability supports up to 200.
                max_size = (
                    min(MAX_SUBGROUP_SIZE, 25)
                    if sixpack
                    else MAX_SUBGROUP_SIZE
                )

                subgroups = prepare_subgroups(
                    columns,
                    rows,
                    selected_indexes,

                    min_columns=2,
                    max_columns=max_size,
                    min_subgroups=2,
                )

                result = (
                    self.capability_engine.calculate_subgroups(
                        subgroups,
                        configuration.column_name,

                        lsl=configuration.lsl,
                        usl=configuration.usl,
                        target=configuration.target,

                        within_method=(
                            configuration.within_method
                        ),

                        use_unbiasing_within=(
                            configuration.use_unbiasing_within
                        ),

                        use_unbiasing_overall=(
                            configuration.use_unbiasing_overall
                        ),
                    )
                )

            # --------------------------------------
            # C. UNKNOWN DATA LAYOUT
            # --------------------------------------

            else:

                raise CapabilityError(
                    "Data layout Process Capability "
                    "tidak dikenal."
                )

            # ======================================
            # 5. GENERATE CAPABILITY FIGURE
            # ======================================

            if sixpack:
                # R4.9.3: Calculate AD once and reuse exactly the same
                # result for the Sixpack Q-Q panel and Session Output.
                ad_result = AndersonDarlingEngine.calculate_normal(
                    result.values,
                    result.column_name,
                )
                figure = create_capability_sixpack_figure(
                    result,
                    ad_result=ad_result,
                )
            else:
                figure = create_capability_figure(result)

            # ======================================
            # 6. PREPARE GRAPH DATASET
            # ======================================

            dataset = ChartDataset(
                column_name=result.column_name,
                values=result.values,
                total_rows=result.n,
                missing_rows=0,
            )

            # ======================================
            # 7. GENERATE SESSION OUTPUT
            # ======================================

            report = format_capability_report(result)

            if sixpack:
                # R4.9.5: CapabilityEngine is intentionally analysis-only.
                # Adjust only the Sixpack report wording, never the estimates
                # nor the standalone Normal Capability report.
                default_note = (
                    "- Capability Normal mengasumsikan distribusi normal; "
                    "normalitas belum diuji oleh engine ini."
                )
                p_text = (
                    "< 0.001" if ad_result.p_value < 0.001
                    else f"{ad_result.p_value:.3f}"
                )
                if ad_result.reject_normality:
                    normality_note = (
                        "- Sixpack Anderson-Darling: asumsi normalitas DITOLAK "
                        f"(AD={ad_result.ad_statistic:.3f}, "
                        f"p={p_text}, alpha={ad_result.alpha:.3f}). "
                        "Estimasi capability berbasis normal perlu ditafsirkan "
                        "dengan hati-hati."
                    )
                else:
                    normality_note = (
                        "- Sixpack Anderson-Darling: tidak cukup bukti untuk "
                        "menolak normalitas "
                        f"(AD={ad_result.ad_statistic:.3f}, "
                        f"p={p_text}, alpha={ad_result.alpha:.3f}); "
                        "ini bukan bukti bahwa distribusi pasti normal."
                    )
                report = report.replace(default_note, normality_note)

                spc_report = format_sixpack_spc_report(result)
                ad_report = format_anderson_darling_report(ad_result)
                report = (
                    "NORMAL CAPABILITY SIXPACK — R4.9.5\n"
                    "Six panels: Phase I SPC, capability histogram, "
                    "variation chart, normal Q-Q with Anderson-Darling, "
                    "last 25 subgroups and 6-sigma capability intervals.\n"
                    "SPC limits use existing R3 Phase I engines.\n"
                    "Anderson-Darling tests normality of all measurements; "
                    "it does not establish process stability.\n\n"
                    + spc_report
                    + "\n\n"
                    + ad_report
                    + "\n\n"
                    + report
                )

        except (
            CapabilityError,
            CapabilityChartError,
            CapabilitySixpackError,
            AndersonDarlingError,
            SubgroupDataError,
            ValueError,
            OverflowError,
        ) as exc:

            self.show_error(str(exc))
            return

        # ==========================================
        # 8. DISPLAY GRAPH
        # ==========================================

        window = self._show_graph(
            figure,
            (
                "Normal Capability Sixpack"
                if sixpack
                else "Normal Process Capability"
            ),
            dataset,
        )

        if sixpack:
            # Larger default window for six panels, constrained to the
            # user's available desktop area. Export keeps full resolution.
            screen = window.screen()
            if screen is not None:
                area = screen.availableGeometry()
                window.resize(
                    min(1400, area.width()),
                    min(960, area.height()),
                )
            else:
                window.resize(1300, 850)

        # ==========================================
        # 9. DISPLAY SESSION OUTPUT
        # ==========================================

        self.output.append(
            "\n"
            + report
            + "\n"
        )

        self.has_analysis = True

        # ==========================================
        # 10. STATUS BAR
        # ==========================================

        cp_text = (
            format(result.cp, ".3f")
            if result.cp is not None
            else "N/A"
        )

        self.statusBar().showMessage(
            (
                "Normal Capability Sixpack: "
                if sixpack
                else "Normal Capability: "
            )
            + f"{result.column_name} | "
            f"N={result.n} | "
            f"Cp={cp_text} | "
            f"Cpk={result.cpk:.3f} | "
            f"Ppk={result.ppk:.3f}"
        )

    # ==================================================
    # 18. ADD ROWS
    # ==================================================

    def add_rows(self):
        count, ok = QInputDialog.getInt(
            self,
            "Tambah Baris",
            "Jumlah baris:",
            100,
            1,
            10000,
        )

        if ok:
            if self.model.insertRows(
                self.model.rowCount(),
                count,
            ):
                self.statusBar().showMessage(
                    f"{count} baris ditambahkan"
                )
            else:
                self.show_error(
                    "Jumlah baris melampaui batas 50.000."
                )

    # ==================================================
    # 19. DELETE ROWS
    # ==================================================

    def delete_rows(self):
        rows = sorted(
            {
                index.row()
                for index in self.table.selectedIndexes()
            },
            reverse=True,
        )

        if (
            not rows
            and self.table.currentIndex().isValid()
        ):
            rows = [
                self.table.currentIndex().row()
            ]

        if not rows:
            self.show_error(
                "Pilih sel pada baris yang akan dihapus."
            )
            return

        if len(rows) >= self.model.rowCount():
            self.show_error(
                "Worksheet harus memiliki setidaknya satu baris."
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete Rows",
            f"Hapus {len(rows)} baris?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer == QMessageBox.StandardButton.Yes:
            for row in rows:
                self.model.removeRows(row, 1)

    # ==================================================
    # 20. ADD COLUMN
    # ==================================================

    def add_column(self):
        if not self.model.insertColumns(
            self.model.columnCount(),
            1,
        ):
            self.show_error(
                "Maksimal 200 kolom."
            )

    # ==================================================
    # 21. DELETE COLUMN
    # ==================================================

    def delete_column(self):
        col = self.current_column()

        if col is None:
            return

        if self.model.columnCount() <= 1:
            self.show_error(
                "Worksheet harus memiliki "
                "setidaknya satu kolom."
            )
            return

        answer = QMessageBox.question(
            self,
            "Delete Column",
            f"Hapus kolom {self.model.columns[col].name}?",
            QMessageBox.StandardButton.Yes
            | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if answer == QMessageBox.StandardButton.Yes:
            self.model.removeColumns(col, 1)

    # ==================================================
    # 22. RENAME COLUMN
    # ==================================================

    def rename_column(self):
        col = self.current_column()

        if col is None:
            return

        name, ok = QInputDialog.getText(
            self,
            "Rename Column",
            "Nama kolom:",
            text=self.model.columns[col].name,
        )

        if ok:
            try:
                self.model.rename_column(
                    col,
                    name,
                )

            except ValueError as exc:
                self.show_error(str(exc))

    # ==================================================
    # 23. CHANGE COLUMN TYPE
    # ==================================================

    def change_column_type(self):
        col = self.current_column()

        if col is None:
            return

        current = (
            0
            if self.model.columns[col].data_type == "numeric"
            else 1
        )

        kind, ok = QInputDialog.getItem(
            self,
            "Column Type",
            "Tipe data:",
            ["Numeric", "Text"],
            current,
            False,
        )

        if ok:
            try:
                self.model.set_column_type(
                    col,
                    kind.lower(),
                )

            except ValueError as exc:
                self.show_error(str(exc))

    # ==================================================
    # 24. CLEAR WORKSHEET
    # ==================================================

    def clear_worksheet(self):
        if self.confirm_replace():
            self.model.reset_blank()
            self.has_analysis = False

            self.output.setPlainText(
                "Worksheet kosong. "
                "Siap untuk input data baru."
            )

    # ==================================================
    # 25. LOAD SAMPLE DATA
    # ==================================================

    def load_sample_data(self):
        if self.confirm_replace():
            self.model.load_sample_data()
            self.has_analysis = False

            self.output.setPlainText(
                "Sample dataset: "
                "5 pengukuran diameter dimuat.\n"
                "Pilih Statistics, Graph, atau "
                "Quality untuk analisis."
            )

    # ==================================================
    # 26. CLOSE APPLICATION
    # ==================================================

    def closeEvent(self, event):
        if self.is_modified:
            answer = QMessageBox.question(
                self,
                "Keluar dari StatDesk",
                "Perubahan worksheet tidak "
                "tersimpan sebagai project.\n"
                "Export Excel/CSV jika perlu "
                "menyimpan datanya.\n\n"
                "Keluar?",
                QMessageBox.StandardButton.Yes
                | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )

            if answer != QMessageBox.StandardButton.Yes:
                event.ignore()
                return

        for graph in list(self.graph_windows):
            graph.close()

        event.accept()
