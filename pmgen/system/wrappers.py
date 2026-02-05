import logging
import functools
from PyQt6.QtWidgets import QMessageBox, QApplication

def safe_slot(func):
    """
    Decorator for PyQt Slots. 
    Catches exceptions, logs them, and shows a warning box 
    instead of crashing or doing nothing.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # 1. Log the full traceback
            logging.exception(f"Error in UI slot '{func.__name__}': {e}")
            
            # 2. Attempt to find a parent widget for the message box
            parent = args[0] if args and hasattr(args[0], "window") else None
            
            # 3. Show non-fatal alert
            app = QApplication.instance()
            if app:
                box = QMessageBox(parent)
                box.setIcon(QMessageBox.Icon.Warning)
                box.setWindowTitle("Action Failed")
                box.setText(f"An error occurred while executing '{func.__name__}'.")
                box.setInformativeText(str(e))
                # Add a "Copy Log" button logic here if desired
                box.exec()
    return wrapper