from PySide6.QtCore import Qt
from PySide6.QtGui import QKeySequence

from PySide6.QtWidgets import (
    QApplication,
    QMessageBox,
    QTableView,
)


class WorksheetTableView(QTableView):

    def keyPressEvent(self, event):

        # CTRL + C
        if event.matches(
            QKeySequence.StandardKey.Copy
        ):
            self.copy_selected_cells()
            return

        # CTRL + V
        if event.matches(
            QKeySequence.StandardKey.Paste
        ):
            self.paste_cells()
            return

        # DELETE / BACKSPACE
        if event.key() in (
            Qt.Key.Key_Delete,
            Qt.Key.Key_Backspace
        ):
            self.clear_selected_cells()
            return

        super().keyPressEvent(event)

    # =====================================
    # COPY SELECTED CELLS
    # =====================================

    def copy_selected_cells(self):
        indexes = self.selectedIndexes()

        if (
            not indexes
            and self.currentIndex().isValid()
        ):
            indexes = [self.currentIndex()]

        if not indexes:
            return

        top = min(
            index.row() for index in indexes
        )

        bottom = max(
            index.row() for index in indexes
        )

        left = min(
            index.column() for index in indexes
        )

        right = max(
            index.column() for index in indexes
        )

        selected = {
            (index.row(), index.column())
            for index in indexes
        }

        lines = []

        for row in range(top, bottom + 1):
            values = []

            for col in range(left, right + 1):

                if (row, col) in selected:
                    value = self.model().data(
                        self.model().index(row, col)
                    )
                else:
                    value = ""

                values.append(str(value or ""))

            lines.append("\t".join(values))

        QApplication.clipboard().setText(
            "\n".join(lines)
        )

    # =====================================
    # PASTE CELLS FROM CLIPBOARD
    # =====================================

    def paste_cells(self):
        text = QApplication.clipboard().text()

        if not text:
            return

        current = self.currentIndex()

        row = (
            current.row()
            if current.isValid()
            else 0
        )

        col = (
            current.column()
            if current.isValid()
            else 0
        )

        lines = (
            text.replace("\r\n", "\n")
            .replace("\r", "\n")
            .rstrip("\n")
            .split("\n")
        )

        matrix = [
            line.split("\t")
            for line in lines
        ]

        try:
            count = self.model().paste_matrix(
                row,
                col,
                matrix
            )

        except ValueError as exc:
            QMessageBox.warning(
                self,
                "Paste ditolak",
                str(exc)
            )
            return

        self.window().statusBar().showMessage(
            f"Berhasil paste {count} sel"
        )

    # =====================================
    # CLEAR SELECTED CELLS
    # =====================================

    def clear_selected_cells(self):
        indexes = self.selectedIndexes()

        if (
            not indexes
            and self.currentIndex().isValid()
        ):
            indexes = [self.currentIndex()]

        count = self.model().clear_cells(
            indexes
        )

        self.window().statusBar().showMessage(
            f"{count} sel dikosongkan"
        )