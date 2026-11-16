import sys

from PySide6.QtWidgets import QApplication
from statdesk.ui.main_window import MainWindow


def main():
    print("Starting StatDesk...")

    # Membuat instance aplikasi Qt
    app = QApplication(sys.argv)

    app.setApplicationName("StatDesk")
    app.setOrganizationName("Internal Quality Engineering")

    # Membuat jendela utama
    window = MainWindow()

    # Menampilkan jendela
    window.show()

    print("StatDesk window displayed successfully!")

    # Menjalankan event loop
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())