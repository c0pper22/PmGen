from __future__ import annotations
import sys
import shutil
import os
import logging # Import logging
from pmgen.io.http_client import get_db_path
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QCoreApplication

# --- NEW IMPORTS ---
from pmgen.system.diagnostics import setup_logging, install_crash_handlers

os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

def bootstrap_database():
    target_path = get_db_path()
    if os.path.exists(target_path):
        return

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
            logging.info(f"Successfully bootstrapped database to {target_path}") 
        except Exception as e:
            logging.error(f"Error copying database: {e}") 
        logging.critical(f"Master database not found at {os.path.abspath(source_path)}")

def main() -> int:
    setup_logging()
    install_crash_handlers()

    """PmGen GUI entry point."""
    try:
        app = QApplication(sys.argv)
        QCoreApplication.setOrganizationName("PmGen")
        QCoreApplication.setOrganizationDomain("pmgen.local")
        QCoreApplication.setApplicationName("PmGen 2.0")
        
        bootstrap_database()
        
        from pmgen.ui.main_window import MainWindow, apply_static_theme
        apply_static_theme(app)

        win = MainWindow()
        win.show()
        
        logging.info("Application loop starting.")
        exit_code = app.exec()
        logging.info(f"Application closing with code {exit_code}")
        return exit_code

    except Exception:
        # This catch-all handles errors during app startup (e.g., ImportError, init failure)
        # The install_crash_handlers should catch most, but this is a final safety net.
        logging.exception("Critical failure during application startup.")
        raise

if __name__ == "__main__":
    raise SystemExit(main())