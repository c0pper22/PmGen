
from __future__ import annotations
import sys
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication
from .main_window import MainWindow, apply_static_theme

def main():
    app = QApplication(sys.argv)
    QCoreApplication.setOrganizationName("PmGen")
    QCoreApplication.setOrganizationDomain("pmgen.local")
    QCoreApplication.setApplicationName("PmGen 2.0")
    apply_static_theme(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
