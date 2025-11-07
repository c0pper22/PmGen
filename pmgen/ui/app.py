
from __future__ import annotations
import sys
import os
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication

os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

from PyQt6.QtWidgets import QApplication

def main() -> int:
    """PmGen GUI entry point."""
    app = QApplication(sys.argv)
    QCoreApplication.setOrganizationName("PmGen")
    QCoreApplication.setOrganizationDomain("pmgen.local")
    QCoreApplication.setApplicationName("PmGen 2.0")
    from pmgen.ui.main_window import MainWindow, apply_static_theme
    apply_static_theme(app)

    win = MainWindow()
    win.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())