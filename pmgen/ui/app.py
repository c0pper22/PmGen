
from __future__ import annotations
import sys
import shutil
import os
from pmgen.io.http_client import get_db_path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication

os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

from PyQt6.QtWidgets import QApplication

def bootstrap_database():
    target_path = get_db_path() # User's AppData path
    
    # 1. If DB already exists in AppData, do nothing
    if os.path.exists(target_path):
        return

    # 2. Determine where the 'master' database lives
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        base_dir = sys._MEIPASS
    elif getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    source_path = os.path.join(base_dir, "catalog_manager.db")

    if os.path.exists(source_path):
        try:
            shutil.copy2(source_path, target_path)
            print(f"Successfully bootstrapped database to {target_path}")
        except Exception as e:
            print(f"Error copying database: {e}")
    else:
        # Debug helper: print the absolute path where it LOOKED for the file
        print(f"Critical: Master database not found at {os.path.abspath(source_path)}")

def main() -> int:
    """PmGen GUI entry point."""
    app = QApplication(sys.argv)
    QCoreApplication.setOrganizationName("PmGen")
    QCoreApplication.setOrganizationDomain("pmgen.local")
    QCoreApplication.setApplicationName("PmGen 2.0")
    bootstrap_database()
    from pmgen.ui.main_window import MainWindow, apply_static_theme
    apply_static_theme(app)

    win = MainWindow()
    win.show()
    return app.exec()

if __name__ == "__main__":
    raise SystemExit(main())