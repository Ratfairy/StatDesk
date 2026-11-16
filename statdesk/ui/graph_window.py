from pathlib import Path

from matplotlib.backends.backend_qtagg import (
    FigureCanvasQTAgg,
    NavigationToolbar2QT,
)

from PySide6.QtCore import Qt, Signal

from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class GraphWindow(QMainWindow):

    closed = Signal(object)

    GRAPH_LABELS = {
        "histogram": "Histogram",
        "boxplot": "Boxplot",
        "normal_probability": "Normal Probability Plot",
    }

    def __init__(self, parent, figure, chart_type, dataset):
        super().__init__(parent, Qt.WindowType.Window)

        self.setAttribute(
            Qt.WidgetAttribute.WA_DeleteOnClose,
            True
        )

        self.figure = figure
        self.chart_type = chart_type
        self.dataset = dataset
        self.is_stale = False

        graph_name = self.GRAPH_LABELS.get(
            chart_type, chart_type
        )

        self.setWindowTitle(
            f"StatDesk | {graph_name} — {dataset.column_name}"
        )

        self.resize(1050, 700)

        # Main container
        container = QWidget(self)
        layout = QVBoxLayout(container)

        # Matplotlib Canvas
        self.canvas = FigureCanvasQTAgg(
            self.figure
        )

        # Toolbar bawaan Matplotlib:
        # zoom, pan, home, back, forward, save
        toolbar = NavigationToolbar2QT(
            self.canvas, self
        )

        layout.addWidget(toolbar)
        layout.addWidget(self.canvas, stretch=1)

        # Status data grafik
        self.notice = QLabel(
            "Snapshot: grafik menggunakan data saat dibuat. "
            "Grafik tidak berubah otomatis saat worksheet diedit."
        )
        self.notice.setWordWrap(True)

        layout.addWidget(self.notice)

        # Bottom action buttons
        buttons = QHBoxLayout()
        buttons.addStretch()

        export_button = QPushButton("Export PNG...")
        export_button.clicked.connect(
            self.export_png
        )
        buttons.addWidget(export_button)

        close_button = QPushButton("Close")
        close_button.clicked.connect(
            self.close
        )
        buttons.addWidget(close_button)

        layout.addLayout(buttons)
        self.setCentralWidget(container)

        self.statusBar().showMessage(
            f"N={dataset.n} | Missing={dataset.missing_rows}"
        )

    # =====================================
    # MARK OLD GRAPH AS STALE
    # =====================================

    def mark_stale(self):
        if self.is_stale:
            return

        self.is_stale = True

        self.setWindowTitle(
            self.windowTitle() + " [STALE]"
        )

        self.notice.setText(
            "PERINGATAN: Worksheet telah berubah. "
            "Grafik ini memakai snapshot lama. "
            "Buat grafik baru untuk data terbaru."
        )

        # Warning ikut tersimpan di gambar
        self.figure.text(
            0.015,
            0.065,
            "WARNING: Source worksheet changed "
            "after this chart was created.",
            fontsize=8,
        )

        self.canvas.draw_idle()

    # =====================================
    # EXPORT GRAPH TO PNG
    # =====================================

    def export_png(self):

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export Graph as PNG",
            "StatDesk_Graph.png",
            "PNG Image (*.png)"
        )

        if not path:
            return

        if Path(path).suffix.lower() != ".png":
            QMessageBox.warning(
                self,
                "Format tidak didukung",
                "Simpan grafik dengan ekstensi .png."
            )
            return

        try:
            self.figure.savefig(
                path,
                format="png",
                dpi=200
            )

        except (OSError, ValueError) as exc:
            QMessageBox.critical(
                self,
                "Export gagal",
                str(exc)
            )
            return

        self.statusBar().showMessage(
            f"PNG saved: {path}"
        )

        QMessageBox.information(
            self,
            "Export berhasil",
            f"Grafik disimpan:\n{path}"
        )

    # =====================================
    # CLEAN UP GRAPH WINDOW
    # =====================================

    def closeEvent(self, event):
        self.closed.emit(self)
        super().closeEvent(event)