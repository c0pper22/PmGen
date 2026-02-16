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

    # =========================================================================
    # [TEMPORARY] FORCE FRESH DATABASE ON STARTUP
    # TODO: Remove the following block when you want user data to persist across sessions!
    if os.path.exists(target_path):
        try:
            os.remove(target_path)
            logging.info(f"Deleted old database at {target_path} to force a fresh copy.")
        except OSError as e:
            logging.error(f"Failed to delete old database: {e}")
    # =========================================================================

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
    else:
        # Only log critical if we really needed to copy it but couldn't find the source
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
        logging.exception("Critical failure during application startup.")
        raise

if __name__ == "__main__":
    raise SystemExit(main())