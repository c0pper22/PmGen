from __future__ import annotations
import sys, os, re
from fnmatch import fnmatchcase
from PyQt6.QtWidgets import QFileDialog, QSpinBox
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from PyQt6.QtCore import (
    Qt, QSize, QPoint, QRect, QEvent, QRegularExpression, QCoreApplication, QSettings,
    QObject, QThread, pyqtSignal, QTimer, pyqtSlot
)
from PyQt6.QtGui import (
    QAction, QIcon, QCursor, QRegularExpressionValidator, QKeySequence, QShortcut,
    QSyntaxHighlighter, QTextCharFormat, QColor, QFont, QTextCursor 
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPlainTextEdit,
    QToolBar, QSizePolicy, QToolButton, QHBoxLayout, QLabel, QMenu,
    QDialog, QPushButton, QFrame, QLineEdit, QComboBox, QCheckBox, QSlider, QSpinBox, QDoubleSpinBox
)

import requests
from collections import deque

# ─────────────────────────────────────────────────────────────────────────────
# Static theme
# ─────────────────────────────────────────────────────────────────────────────
THEME = "dark"  # set to "light" for the light theme
VERSION = "2.2.1"

GLOBAL_STYLE_LIGHT = """
#TopBarBg { background-color: #f4f4f6; }
#MainEditor { background: white; color: black; border: none; font-family: Consolas, "Fira Code", monospace; font-size: 13px; }
QMainWindow { background: white; }
QLabel#TitleLabel { color: #111; font-size: 16pt; font-weight: 500; }

/* Toolbar */
QToolBar { background: transparent; border: none; spacing: 0px; padding: 0 8px; }
QToolButton { border: none; background: transparent; padding: 6px 8px; }
QToolButton:hover { background-color: rgba(127,127,127,0.15); border-radius: 0; }
QToolButton#SettingsBtn, QToolButton#BulkBtn { padding: 6px 10px; border-radius: 0; font-weight: 500; }
QToolButton#SettingsBtn::menu-indicator, QToolButton#BulkBtn::menu-indicator { image: none; width: 0px; }

/* Menus */
QMenu { background: #ffffff; color: #111; border: 1px solid #d9d9dc; }
QMenu::item:selected { background: #e9e9ef; }

/* Frameless dialogs */
QDialog#FramelessDialogRoot { background: #ffffff; border: 1px solid #d9d9dc; border-radius: 0; }
#DialogTitleBar { background: #f4f4f6; border-top-left-radius: 0; border-top-right-radius: 0; }
#DialogTitleLabel { color: #111; font-weight: 600; }
#DialogBtn { padding: 6px 10px; border-radius: 0; }
#DialogSeparator { background: #e0e0e6; max-height: 1px; min-height: 1px; }

/* Secondary bar */
#SecondaryBar { background: #f4f4f6; border: 1px solid #d9d9dc; border-radius: 0; padding: 6px; }

/* Keep support for QLineEdit if used anywhere else */
QLineEdit#IdInput { background: white; color: #111; border: 1px solid #cfcfd4; border-radius: 0; padding: 6px 8px; }

/* Editable combo styling for the recent-serials input */
QComboBox#IdInput { border: 1px solid #cfcfd4; border-radius: 0; padding: 0 6px; background: #ffffff; color: #111; }
QComboBox#IdInput::drop-down { width: 0px; border: none; } /* clean, no arrow */
QComboBox#IdInput QLineEdit { background: #ffffff; color: #111; border: none; padding: 6px 8px; }

QPushButton#GenerateBtn { padding: 6px 12px; border-radius: 0; border: 1px solid #cfcfd4; background: #f8f8fb; }
QPushButton#GenerateBtn:hover { background: #ededf3; }

QPushButton { padding: 6px 12px; border-radius: 0; border: 1px solid #cfcfd4; background: #f8f8fb; }
QPushButton:hover { background: #ededf3; }
"""

GLOBAL_STYLE_DARK = """
#TopBarBg { background-color: #202225; }
#MainEditor { background: #1e1f22; color: #e9e9e9; border: 1px solid #000000; font-family: Consolas, "Fira Code", monospace; font-size: 13px; }
QMainWindow { background: #181a1b; }
QLabel#TitleLabel { color: #e9e9e9; font-size: 16pt; font-weight: 500; }

/* Toolbar */
QToolBar { background: transparent; border: none; spacing: 0px; padding: 0 8px; }
QToolButton { border: none; background: transparent; padding: 6px 8px; }
QToolButton:hover { background-color: rgba(127,127,127,0.15); border-radius: 0; }
QToolButton#SettingsBtn, QToolButton#BulkBtn { padding: 6px 10px; border-radius: 0; font-weight: 500; }
QToolButton#SettingsBtn::menu-indicator, QToolButton#BulkBtn::menu-indicator { image: none; width: 0px; }

/* Menus */
QMenu { background: #2a2c2f; color: #e9e9e9; border: 1px solid #3a3d41; }
QMenu::item:selected { background: #3a3d41; }

/* Frameless dialogs */
QDialog#FramelessDialogRoot { background: #1f2023; border: 1px solid #000000; border-radius: 0; }
#DialogTitleBar { background: #202225; border-top-left-radius: 0; border-top-right-radius: 0; }
#DialogTitleLabel { color: #e9e9e9; font-weight: 600; }
#DialogBtn { padding: 6px 10px; border-radius: 0; }
#DialogSeparator { background: #000000; max-height: 1px; min-height: 1px; }
#DialogCheckbox { background: #1f2023; }
#DialogCheckbox::indicator { border: 1px solid #000000; width:16px; height:16px; }
QCheckBox#DialogCheckbox::indicator:checked { background:#1f2023; border:1px solid #000000; image: url(pmgen/ui/icons/checkmark.svg); }
QCheckBox#DialogCheckbox::indicator:unchecked { image: none; }
#DialogLabel { background: #1f2023; color: #e9e9e9; }
#UserLabel { background: #1f2023; color: #e9e9e9; font-weight: 800 }
#DialogInput { background: #2a2c2f; color: #e9e9e9; border: 1px solid #000000; font-weight: 800; }
#DialogInput:focus { background: #2a2c2f; color: #e9e9e9; border-radius: 0; border: 1px solid #000000; font-weight: 800 }
#DialogInput::up-arrow {
    image: url(pmgen/ui/icons/up.svg);
}
#DialogInput::down-arrow {
    image: url(pmgen/ui/icons/down.svg);
}


/* Secondary bar */
#SecondaryBar { background: #202225; border: 1px solid #000000; border-radius: 0; padding: 6px; }

/* Keep support for QLineEdit if used anywhere else */
QLineEdit#IdInput { background: #000000; color: #e9e9e9; border: 1px solid #000000; border-radius: 0; padding: 6px 8px; font-weight: 800 }
QLineEdit#IdInput:focus { border: 1px solid #000000; }

/* Editable combo styling for the recent-serials input */
QComboBox#IdInput { border: 1px solid #000000; border-radius: 0; padding: 0 6px; background: #2a2c2f; color: #e9e9e9; font-weight: 800; }
QComboBox#IdInput::drop-down { width: 0px; border: none; }
QComboBox#IdInput QLineEdit { background: #000000; color: #e9e9e9; border: none; padding: 6px 8px; font-weight: 800; }

QPushButton#GenerateBtn { padding: 6px 12px; border-radius: 0; border: 1px solid #000000; background: #2a2c2f; color: #e9e9e9; }
QPushButton#GenerateBtn:hover { background: #33363b; }

QPushButton { padding: 6px 12px; border-radius: 0; border: 1px solid #000000; background: #2a2c2f; color: #e9e9e9; }
QPushButton:hover { background: #33363b; }
QDoubleSpinBox#DialogInput {
    border: 1px solid #000000;
    background: #2a2c2f;
    color: #ffffff;
    border-radius: 0;
    padding-right: 6px;  /* reduce right padding since no arrows */
    selection-background-color: #000000;
    selection-color: #ffffff;
}

/* Remove both arrow buttons completely */
QDoubleSpinBox#DialogInput::up-button,
QDoubleSpinBox#DialogInput::down-button {
    width: 0;
    height: 0;
    border: none;
    margin: 0;
    padding: 0;
}

/* Hide arrow icons */
QDoubleSpinBox#DialogInput::up-arrow,
QDoubleSpinBox#DialogInput::down-arrow {
    image: none;
}

/* Disabled state */
QDoubleSpinBox#DialogInput:disabled {
    color: #8a8d91;
    background: #191b1e;
    border-color: #2a2c2f;
}
"""

def apply_static_theme(app: QApplication):
    app.setStyle("Fusion")
    css = GLOBAL_STYLE_DARK if THEME.lower() == "dark" else GLOBAL_STYLE_LIGHT
    app.setStyleSheet(css)

BORDER_WIDTH = 8  # pixels for custom resize grip

# ─────────────────────────────────────────────────────────────────────────────
# Auth / keyring helpers (constant used by http_client)
# ─────────────────────────────────────────────────────────────────────────────
SERVICE_NAME = "PmGen"

def _tz_offset_minutes() -> int:
    try:
        offset = datetime.now(timezone.utc).astimezone().utcoffset()
        return int(offset.total_seconds() // 60) if offset is not None else 0
    except Exception:
        import time as _t
        is_dst = _t.localtime().tm_isdst > 0 and _t.daylight
        seconds = -(_t.altzone if is_dst else _t.timezone)
        return int(seconds // 60)

# ---------------------------- Drag Region ----------------------------
class DragRegion(QWidget):
    def __init__(self, parent_window: QMainWindow):
        super().__init__(parent_window)
        self._win = parent_window
        self._dragging = False
        self._drag_pos = QPoint()
        self.setMinimumWidth(40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setMouseTracking(True)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging:
            self._win.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            e.accept()
        else:
            super().mouseReleaseEvent(e)

# ---------------------------- Draggable Title Label ----------------------------
class TitleDragLabel(QLabel):
    def __init__(self, text: str, parent_window: QMainWindow):
        super().__init__(text, parent_window)
        self._win = parent_window
        self._dragging = False
        self._drag_pos = QPoint()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setFixedHeight(36)
        self.setObjectName("TitleLabel")
        self.setMouseTracking(True)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging and not self._win.isFullScreen():
            self._win.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            e.accept()
        else:
            super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            if self._win.isFullScreen():
                if hasattr(self._win, "_act_full"):
                    self._win._act_full.setChecked(False)
                self._win.showNormal()
            else:
                if hasattr(self._win, "_act_full"):
                    self._win._act_full.setChecked(True)
                self._win.showFullScreen()
            e.accept()
        else:
            super().mouseDoubleClickEvent(e)

# ---------------------------- Custom TitleBar for dialogs ----------------------------
class DialogTitleBar(QWidget):
    def __init__(self, window: QDialog, title: str, icon_dir: str):
        super().__init__(window)
        self.setObjectName("DialogTitleBar")
        self._win = window
        self._dragging = False
        self._drag_pos = QPoint()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        lbl = QLabel(title, self)
        lbl.setObjectName("DialogTitleLabel")

        minimize_icon = os.path.join(icon_dir, "minimize.svg")
        maximize_icon = os.path.join(icon_dir, "fullscreen.svg")
        exit_icon = os.path.join(icon_dir, "exit.svg")

        btn_min = QToolButton(self); btn_min.setObjectName("DialogBtn")
        btn_min.setIcon(QIcon(minimize_icon)); btn_min.setToolTip("Minimize")
        btn_min.clicked.connect(self._win.showMinimized)

        self._act_max = QAction(QIcon(maximize_icon), "Maximize", self)
        self._act_max.setCheckable(True)
        self._act_max.triggered.connect(self._toggle_max_restore)
        btn_max = QToolButton(self); btn_max.setObjectName("DialogBtn")
        btn_max.setDefaultAction(self._act_max)

        btn_close = QToolButton(self); btn_close.setObjectName("DialogBtn")
        btn_close.setIcon(QIcon(exit_icon)); btn_close.setToolTip("Close")
        btn_close.clicked.connect(self._win.close)

        layout.addWidget(lbl, 1, Qt.AlignmentFlag.AlignVCenter)
        right = QHBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)

        box = QWidget(self)
        box.setLayout(right)
        right.addWidget(btn_min)
        right.addWidget(btn_max)
        right.addWidget(btn_close)
        layout.addWidget(box, 0)

        self.setFixedHeight(36)

    def _toggle_max_restore(self, checked: bool):
        if checked:
            self._win.showMaximized()
        else:
            self._win.showNormal()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = e.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
            e.accept()
        else:
            super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._dragging:
            self._win.move(e.globalPosition().toPoint() - self._drag_pos)
            e.accept()
        else:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            e.accept()
        else:
            super().mouseReleaseEvent(e)

# ---------------------------- FramelessDialog base ----------------------------
class FramelessDialog(QDialog):
    def __init__(self, parent, title: str, icon_dir: str):
        super().__init__(parent, flags=Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool)
        self.setObjectName("FramelessDialogRoot")
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._titlebar = DialogTitleBar(self, title, icon_dir)
        outer.addWidget(self._titlebar)

        sep = QFrame(self)
        sep.setObjectName("DialogSeparator")
        sep.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(sep)

        self._content = QWidget(self)
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 12, 12, 12)
        self._content_layout.setSpacing(12)
        outer.addWidget(self._content)

        self.setMinimumSize(420, 220)

# ---------------------------- CustomMessageBox ----------------------------
class CustomMessageBox(FramelessDialog):
    def __init__(self, parent, title: str, text: str, icon_dir: str, buttons: list[tuple[str, str]]):
        super().__init__(parent, title, icon_dir)

        lbl = QLabel(text, self._content)
        lbl.setWordWrap(True)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self._clicked_role = None

        for label, role in buttons:
            b = QPushButton(label, self._content)
            b.clicked.connect(lambda _=False, r=role: self._finish(r))
            btn_row.addWidget(b)

        self._content_layout.addWidget(lbl)
        self._content_layout.addLayout(btn_row)

    def _finish(self, role: str):
        self._clicked_role = role
        self.accept()

    @staticmethod
    def none(parent, title: str, text: str, icon_dir: str):
        dlg = CustomMessageBox(parent, title, text, icon_dir, [])
        dlg.exec()
        return dlg._clicked_role or "ok"

    @staticmethod
    def info(parent, title: str, text: str, icon_dir: str):
        dlg = CustomMessageBox(parent, title, text, icon_dir, [("OK", "ok")])
        dlg.exec()
        return dlg._clicked_role or "ok"

    @staticmethod
    def warn(parent, title: str, text: str, icon_dir: str):
        dlg = CustomMessageBox(parent, title, text, icon_dir, [("OK", "ok")])
        dlg.exec()
        return dlg._clicked_role or "ok"

    @staticmethod
    def apply(parent, title: str, text: str, icon_dir: str):
        dlg = CustomMessageBox(parent, title, text, icon_dir, [("CANCEL", "cancel"),("APPLY", "apply")])
        dlg.exec()
        return dlg._clicked_role or "ok"

    @staticmethod
    def confirm(parent, title: str, text: str, icon_dir: str):
        dlg = CustomMessageBox(parent, title, text, icon_dir, [("Cancel", "cancel"), ("OK", "ok")])
        dlg.exec()
        return dlg._clicked_role or "cancel"

# ---------------------------- Output Highlighter ----------------------------
class OutputHighlighter(QSyntaxHighlighter):
    def __init__(self, parent_doc):
        super().__init__(parent_doc)
        self._build_formats()

    def _mkfmt(self, fg=None, bold=False, italic=False):
        fmt = QTextCharFormat()
        if fg is not None:
            fmt.setForeground(QColor(fg))
        if bold:
            fmt.setFontWeight(QFont.Weight.DemiBold)
        if italic:
            fmt.setFontItalic(True)
        return fmt

    def _build_formats(self):
        self.fmt_header     = self._mkfmt("#7aa2f7", bold=True)
        self.fmt_rule       = self._mkfmt("#444444")
        self.fmt_muted      = self._mkfmt("#888888", italic=True)
        self.fmt_kit_row    = self._mkfmt("#a6da95")
        self.fmt_due_bullet = self._mkfmt("#f7768e", bold=True)
        self.fmt_percentage = self._mkfmt("#f77600", bold=True)
        self.fmt_label      = self._mkfmt("#c0caf5", bold=True)

        self.fmt_due_row_base = self._mkfmt("#bbbbbb")
        self.fmt_due_canon    = self._mkfmt("#1c94d5", bold=True)
        self.fmt_due_pct      = self._mkfmt("#e0af68", bold=True)
        self.fmt_due_flag     = self._mkfmt("#f7768e", bold=True)

        self.fmt_header_line_base = self._mkfmt("#bfbfbf")
        self.fmt_model_value      = self._mkfmt("#a6da95", bold=True)
        self.fmt_serial_value     = self._mkfmt("#7dcfff", bold=True)
        self.fmt_date_value       = self._mkfmt("#e0af68")

        self.fmt_badge_line_base  = self._mkfmt("#bfbfbf")
        self.fmt_thresh_value     = self._mkfmt("#e0af68", bold=True)
        self.fmt_basis_badge      = self._mkfmt("#e0af68", bold=True)

        self.fmt_counters_base    = self._mkfmt("#bfbfbf")
        self.fmt_kv_label         = self._mkfmt("#1c94d5", bold=True)
        self.fmt_kv_value         = self._mkfmt("#e0af68", bold=True)
        
        self.fmt_bulk             = self._mkfmt("#5fd0e3", bold=True)
        self.fmt_info             = self._mkfmt("#f5db30", bold=True)

        self.fmt_pct_low          = self._mkfmt("#40ed68", bold=True)
        self.fmt_pct_mid          = self._mkfmt("#f79346", bold=True)
        self.fmt_pct_high         = self._mkfmt("#d83d37", bold=True)

        self.fmt_bulk_serial      = self._mkfmt("#b28af3", bold=True)
        self.fmt_bulk_ok          = self._mkfmt("#40ed68", bold=True)
        self.fmt_bulk_filtered    = self._mkfmt("#d83d37", bold=True)

    def highlightBlock(self, text: str):
        import re
        t = text.strip()

        if "[Auto-Login]" in t:
            self.setFormat(0, len(text), self.fmt_muted)
            return
        
        if "[Info]" in t:
            self.setFormat(0, len(text), self.fmt_info)

        if "[Bulk]" in t:
            self.setFormat(0, len(text), self.fmt_bulk)

            pct_re = re.compile(r"(?P<num>\d+(?:\.\d+)?)%")
            for m in pct_re.finditer(t):
                val_str = m.group("num")
                try:
                    val = float(val_str)
                except ValueError:
                    continue

                if val < 84.0:
                    fmt = self.fmt_pct_low
                elif val < 100.0:
                    fmt = self.fmt_pct_mid
                else:
                    fmt = self.fmt_pct_high

                start = m.start()
                length = m.end() - m.start()
                self.setFormat(start, length, fmt)

            ok_re = re.compile(r"\bOK\b", re.IGNORECASE)
            for m in ok_re.finditer(t):
                self.setFormat(m.start(), m.end() - m.start(), self.fmt_bulk_ok)

            filtered_re = re.compile(r"\bFILTERED\b", re.IGNORECASE)
            for m in filtered_re.finditer(t):
                self.setFormat(m.start(), m.end() - m.start(), self.fmt_bulk_filtered)

            serial_re = re.compile(r"\b[A-Z0-9]{5,10}\b")
            for m in serial_re.finditer(t):
                self.setFormat(m.start(), m.end() - m.start(), self.fmt_bulk_serial)
            return

        if t in ("Final Parts", "Most-Due Items", "Counters", "End of Report"):
            self.setFormat(0, len(text), self.fmt_header)
            return

        if set(t) in ({"─"}, {"-"}, {"="}):
            self.setFormat(0, len(text), self.fmt_rule)
            return

        if t.startswith("(") and any(tok in t.lower() for tok in ("qty", "catalog", "part number", "×", " x ")):
            self.setFormat(0, len(text), self.fmt_muted)
            return

        if "→" in t and not t.startswith("Report Date"):
            kit_new_after = re.compile(
                r"^\s*(?P<qty>\d+)\s*[x×]\s*→\s*(?P<pn>\S+)\s*→\s*(?P<kit>\S.*?)\s*$",
                re.IGNORECASE
            )
            kit_new_before = re.compile(
                r"^\s*x\s*(?P<qty>\d+)\s*→\s*(?P<pn>\S+)\s*→\s*(?P<kit>\S.*?)\s*$",
                re.IGNORECASE
            )
            kit_old = re.compile(
                r"^\s*(?P<kit>\S.*?)\s*→\s*(?P<pn>\S+)\s*[×x]\s*(?P<qty>\d+)\s*$",
                re.IGNORECASE
            )

            if kit_new_after.match(t) or kit_new_before.match(t) or kit_old.match(t):
                self.setFormat(0, len(text), self.fmt_kit_row)
                return

        if t.startswith("• ") or "→ DUE" in t:
            m = re.match(
                r"^\s*•\s+(?P<canon>.+?)\s+—\s+(?P<pct>\S+)(?:\s*→\s*(?P<due>DUE))?\s*$",
                t
            )
            if m:
                self.setFormat(0, len(text), self.fmt_due_row_base)
                left_ws = len(text) - len(text.lstrip())

                def _apply(name, fmt):
                    if name in m.groupdict() and m.group(name):
                        s, e = m.start(name), m.end(name)
                        self.setFormat(left_ws + s, e - s, fmt)

                _apply("canon", self.fmt_due_canon)
                _apply("pct",   self.fmt_due_pct)
                if m.group("due"):
                    _apply("due", self.fmt_due_flag)
                return
            else:
                self.setFormat(0, len(text), self.fmt_due_bullet)
                return

        if t.startswith("Model:") and "Serial:" in t and "Date:" in t:
            self.setFormat(0, len(text), self.fmt_header_line_base)
            m = re.search(
                r"Model:\s*(?P<model>.+?)\s*\|\s*Serial:\s*(?P<serial>\S+)\s*\|\s*Date:\s*(?P<date>.+)$",
                text
            )
            if m:
                def _apply_span(name, fmt):
                    s, e = m.span(name)
                    self.setFormat(s, e - s, fmt)
                _apply_span("model",  self.fmt_model_value)
                _apply_span("serial", self.fmt_serial_value)
                _apply_span("date",   self.fmt_date_value)
            return

        if t.startswith("Basis:") or t.startswith("Report Date:"):
            self.setFormat(0, len(text), self.fmt_label)
            return

        if t.lower().startswith("due threshold:") and "basis:" in t.lower():
            self.setFormat(0, len(text), self.fmt_badge_line_base)
            m = re.search(
                r"(?i)due\s*threshold:\s*(?P<thresh>[0-9.]+%?)\s*•\s*basis:\s*(?P<basis>\S+)",
                text
            )
            if m:
                def _apply_span(s_e, fmt):
                    s, e = s_e
                    self.setFormat(s, e - s, fmt)
                _apply_span(m.span("thresh"), self.fmt_thresh_value)
                _apply_span(m.span("basis"),  self.fmt_basis_badge)
            return

        if t.lower().startswith("color:") or (" black:" in t.lower() and " total:" in t.lower()):
            self.setFormat(0, len(text), self.fmt_counters_base)
            for m in re.finditer(r"([A-Za-z]+):\s*([0-9,]+)", text):
                label_span = m.span(1)
                val_span   = m.span(2)
                self.setFormat(*label_span, self.fmt_kv_label)
                self.setFormat(*val_span,   self.fmt_kv_value)
            return

@dataclass
class BulkConfig:
    top_n: int = 25
    out_dir: str = ""
    pool_size: int = 4
    blacklist: list[str] = None
    show_all: bool = False
    def __post_init__(self):
        if self.blacklist is None:
            self.blacklist = []

BULK_TOPN_KEY = "bulk/top_n"
BULK_DIR_KEY  = "bulk/out_dir"
BULK_POOL_KEY = "bulk/pool_size"
BULK_BLACKLIST_KEY = "bulk/blacklist"

# ---------------------------- Main Window ----------------------------
@dataclass
class ResizeState:
    resizing: bool = False
    edge_left: bool = False
    edge_right: bool = False
    edge_top: bool = False
    edge_bottom: bool = False
    press_pos: QPoint = QPoint()
    press_geom: QRect = QRect()

class BulkRunner(QObject):
    progress = pyqtSignal(str)
    finished = pyqtSignal(str)

    def __init__(self, cfg: BulkConfig, threshold: float, life_basis: str,
                 unpack_filter_enabled: bool = False, unpack_extra_months: int = 0):
        super().__init__()
        self.cfg = cfg
        self.threshold = threshold
        self.life_basis = life_basis
        self._blacklist = [p.upper() for p in (cfg.blacklist or [])]
        self._unpack_filter_enabled = bool(unpack_filter_enabled)
        self._unpack_extra_months = max(0, min(120, int(unpack_extra_months)))

    def _is_blacklisted(self, serial: str) -> bool:
        s = (serial or "").upper()
        for pat in (self._blacklist or []):
            if fnmatchcase(s, pat):
                return True
        return False

    def _prefilter_by_unpack_date(self, serials: list[str], pool) -> list[str]:
        if not self._unpack_filter_enabled:
            self.progress.emit("[Info] Unpack filter disabled.")
            return list(serials)

        try:
            from pmgen.io.http_client import get_unpacking_date as _get_unpack
            _sig_uses_kw = True
        except Exception:
            try:
                from pmgen.io.http_client import get_unpack_date as _get_unpack
                _sig_uses_kw = False
            except Exception as e:
                self.progress.emit(f"[Bulk] Unpack filter unavailable ({e}).")
                return list(serials)

        from datetime import date
        import calendar

        def _add_months(d: date, months: int) -> date:
            y = d.year + (d.month - 1 + months) // 12
            m = (d.month - 1 + months) % 12 + 1
            return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))

        kept = []
        base_months = int(self._unpack_extra_months)
        with pool.acquire() as sess:
            self.progress.emit(f"[Bulk] Applying unpacking date filter (+{self._unpack_extra_months} mo)…")
            for s in serials:
                try:
                    if _sig_uses_kw:
                        d = _get_unpack(s, sess=sess)
                    else:
                        d = _get_unpack(s, sess)
                except Exception:
                    kept.append(s)
                    continue

                if not d:
                    kept.append(s)
                    self.progress.emit(f"[Bulk] OK: {s} (no unpack date)")
                    continue

                cutoff = _add_months(d, base_months)
                today = date.today()
                if today > cutoff:
                    over = (today.year - cutoff.year) * 12 + (today.month - cutoff.month)
                    if today.day < cutoff.day:
                        over -= 1
                    over = max(0, over)
                    self.progress.emit(
                        f"[Bulk] Filtered: {s} unpacked {d:%Y-%m-%d} → cutoff {cutoff:%Y-%m-%d} (>{base_months} mo{f' +{over}' if over else ''})"
                    )
                else:
                    self.progress.emit(
                        f"[Bulk] OK: {s} unpacked {d:%Y-%m-%d} (cutoff {cutoff:%Y-%m-%d})"
                    )
                    kept.append(s)
        return kept

    def _fmt_pct(self, p):
        if p is None:
            return "—"
        try:
            return f"{(float(p) * 100):.1f}%"
        except Exception:
            return "—"

    def run(self):
        try:
            from pmgen.io.http_client import SessionPool, get_serials_after_login, get_service_file_bytes
            from pmgen.parsing.parse_pm_report import parse_pm_report
            from pmgen.engine.run_rules import run_rules
            from pmgen.engine.single_report import format_report

            os.makedirs(self.cfg.out_dir, exist_ok=True)

            self.progress.emit("[Info] Creating session pool...")
            pool = SessionPool(self.cfg.pool_size)

            with pool.acquire() as sess:
                serials = get_serials_after_login(sess)
            self.progress.emit(f"[Info] Found {len(serials)} Active Serials.")

            serials0 = list(serials or [])
            serials1 = [s for s in serials0 if not self._is_blacklisted(s)]
            skipped = len(serials0) - len(serials1)
            if skipped:
                self.progress.emit(f"[Bulk] Skipped {skipped} serial(s) via blacklist.")
            if not serials1:
                raise RuntimeError("No serials to process after applying blacklist.")

            kept_serials = self._prefilter_by_unpack_date(serials1, pool)
            if not kept_serials:
                raise RuntimeError("All serials were filtered out by unpack-date/cutoff logic.")
            
            self.progress.emit(f"[Info] Filtered out {len(serials) - len(kept_serials)} Serials")
            self.progress.emit(f"[Info] Countinuing with {len(kept_serials)} Serials")

            thr = self.threshold
            basis = self.life_basis
            show_all = self.cfg.show_all

            def work(serial: str):
                try:
                    with pool.acquire() as sess:
                        blob = get_service_file_bytes(serial, "PMSupport", sess=sess)
                    report = parse_pm_report(blob)
                    selection = run_rules(report, threshold=thr, life_basis=basis)

                    all_items = (getattr(selection, "meta", {}) or {}).get("all", []) or getattr(selection, "all_items", []) or []
                    best_used = max([getattr(f, "life_used", 0.0) or 0.0 for f in all_items], default=0.0)

                    text = format_report(
                        report=report,
                        selection=selection,
                        threshold=thr,
                        life_basis=basis,
                        show_all=show_all
                    )

                    meta = getattr(selection, "meta", {}) or {}
                    grouped = meta.get("selection_pn_grouped", {}) or {}
                    flat    = meta.get("selection_pn", {}) or {}
                    kit_by_pn = meta.get("kit_by_pn", {}) or {}

                    return {
                        "serial": (report.headers or {}).get("serial") or serial,
                        "model":  (report.headers or {}).get("model")  or "Unknown",
                        "best_used": float(best_used),
                        "text": text,
                        "grouped": grouped,
                        "flat": flat,
                        "kit_by_pn": kit_by_pn
                    }
                except Exception as e:
                    import traceback
                    return {"serial": serial, "error": str(e), "trace": traceback.format_exc()}

            results = []
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=self.cfg.pool_size) as ex:
                futures = {ex.submit(work, s): s for s in kept_serials}
                for fut in as_completed(futures):
                    s = futures[fut]
                    try:
                        res = fut.result()
                        if "error" in res:
                            self.progress.emit(f"[Bulk] {s}: ERROR — {res['error']}")
                        else:
                            self.progress.emit(f"[Bulk] {s}: OK — {self._fmt_pct(res['best_used'])}")
                        results.append(res)
                    except Exception as e:
                        self.progress.emit(f"[Bulk] {s}: ERROR — {e}")

            ok = [r for r in results if "error" not in r]
            ok.sort(key=lambda r: r["best_used"], reverse=True)
            top = ok[: self.cfg.top_n]

            for r in top:
                pct = self._fmt_pct(r["best_used"]).replace("%", "")
                fname = f"{pct}_{r['serial']}.txt"
                path = os.path.join(self.cfg.out_dir, fname)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(r["text"])
            self.progress.emit(f"[Info] Wrote {len(top)} report files to: {self.cfg.out_dir}")

            lines = []
            lines.append("Bulk Final Summary")
            lines.append("───────────────────────────────────────────────────────────────")
            lines.append(f"Threshold: {thr:.2f} • Basis: {basis.upper()}")
            lines.append(f"Selected top {len(top)} of {len(ok)} successful (from {len(results)} attempts).")
            lines.append("")

            total_upn = {}
            for r in top:
                lines.append(f"{r['serial']}  —  best used {self._fmt_pct(r['best_used'])}  —  {r['model']}")
                grouped = r.get("grouped") or {}

                if not grouped:
                    flat = r.get("flat") or {}
                    kit_by_pn = r.get("kit_by_pn") or {}
                    if not flat:
                        lines.append("  (no final parts)")
                        lines.append("")
                    else:
                        for pn, qty in flat.items():
                            unit = kit_by_pn.get(pn, "UNKNOWN-UNIT")
                            lines.append(f"  • {unit} → {pn} ×{int(qty)}")
                            total_upn[(unit, pn)] = total_upn.get((unit, pn), 0) + int(qty)
                        lines.append("")
                else:
                    for unit, pnmap in grouped.items():
                        for pn, qty in (pnmap or {}).items():
                            lines.append(f"  • {unit} → {pn} ×{int(qty)}")
                            total_upn[(unit, pn)] = total_upn.get((unit, pn), 0) + int(qty)
                    lines.append("")

            lines.append("All Serials — Consolidated Parts")
            lines.append("───────────────────────────────────────────────────────────────")
            if total_upn:
                for (unit, pn) in sorted(total_upn.keys(), key=lambda k: (k[0], k[1])):
                    lines.append(f"  • {unit} → {pn} ×{int(total_upn[(unit, pn)])}")
            else:
                lines.append("  (none)")
            lines.append("")

            sum_path = os.path.join(self.cfg.out_dir, "Final_Summary.txt")
            with open(sum_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))

            pool.close()
            self.finished.emit(f"[Info] Complete. Summary written to: {sum_path}")
        except Exception as e:
            self.finished.emit(f"[Bulk] Failed: {e}")

class MainWindow(QMainWindow):
    # ---- PM settings ----
    THRESH_KEY = "pm/due_threshold"
    LIFE_BASIS_KEY = "pm/life_basis"
    COLORIZED_KEY = "ui/colorized_output"
    SHOW_ALL_KEY = "ui/show_all_items"

    BULK_UNPACK_KEY_ENABLE = "bulk/unpack_filter_enabled"
    BULK_UNPACK_KEY_EXTRA  = "bulk/unpack_extra_months"

    # ---- Auth prefs (QSettings only; credentials live in http_client)
    AUTH_REMEMBER_KEY = "auth/remember"
    AUTH_USERNAME_KEY = "auth/username"

    def _get_unpack_filter_enabled(self) -> bool:
        s = QSettings()
        return bool(s.value(self.BULK_UNPACK_KEY_ENABLE, False, bool))

    def _set_unpack_filter_enabled(self, on: bool):
        s = QSettings()
        s.setValue(self.BULK_UNPACK_KEY_ENABLE, bool(on))

    def _get_unpack_extra_months(self) -> int:
        s = QSettings()
        try:
            v = int(s.value(self.BULK_UNPACK_KEY_EXTRA, 0, int))
        except Exception:
            v = 0
        return max(0, min(120, v))

    def _set_unpack_extra_months(self, months: int):
        s = QSettings()
        s.setValue(self.BULK_UNPACK_KEY_EXTRA, int(max(0, min(120, months))))

    def _get_bulk_config(self) -> BulkConfig:
        s = QSettings()
        top_n = int(s.value(BULK_TOPN_KEY, 25, int))
        out   = s.value(BULK_DIR_KEY, "", str)
        pool  = int(s.value(BULK_POOL_KEY, 4, int))
        bl_raw = s.value(BULK_BLACKLIST_KEY, "", str) or ""
        bl = []
        for line in re.split(r"[,\n]+", bl_raw):
            pat = line.strip()
            if pat:
                bl.append(pat.upper())
        top_n = max(1, min(9999, top_n))
        pool  = max(1, min(16, pool))
        return BulkConfig(top_n=top_n, out_dir=out, pool_size=pool, blacklist=bl)

    def _save_bulk_config(self, cfg: BulkConfig):
        s = QSettings()
        s.setValue(BULK_TOPN_KEY, int(cfg.top_n))
        s.setValue(BULK_DIR_KEY, cfg.out_dir or "")
        s.setValue(BULK_POOL_KEY, int(cfg.pool_size))
        s.setValue(BULK_BLACKLIST_KEY, "\n".join(cfg.blacklist or []))

    def _get_show_all(self) -> bool:
        s = QSettings()
        return bool(s.value(self.SHOW_ALL_KEY, False, bool))

    def _set_show_all(self, on: bool):
        s = QSettings()
        s.setValue(self.SHOW_ALL_KEY, bool(on))

    def _get_colorized(self) -> bool:
        s = QSettings()
        return bool(s.value(self.COLORIZED_KEY, True, bool))

    def _set_colorized(self, on: bool):
        s = QSettings()
        s.setValue(self.COLORIZED_KEY, bool(on))

    def _apply_colorized_highlighter(self):
        if not hasattr(self, "_out_highlighter"):
            self._out_highlighter = None

        want = self._get_colorized()
        have = self._out_highlighter is not None

        if want and not have:
            self._out_highlighter = OutputHighlighter(self.editor.document())
            self._out_highlighter.rehighlight()
        elif not want and have:
            self._out_highlighter.setDocument(None)
            self._out_highlighter.deleteLater()
            self._out_highlighter = None
            self.editor.setPlainText(self.editor.toPlainText())

    def _thr_to_slider(self, thr: float) -> int:
        try:
            v = int(round(float(thr) * 100))
        except Exception:
            v = 80
        return max(1, min(200, v))

    def _slider_to_thr(self, val: int) -> float:
        return max(0.01, min(2.00, val / 100.0))

    def _get_threshold(self) -> float:
        s = QSettings()
        try:
            v = float(s.value(self.THRESH_KEY, 0.80, float))
        except Exception:
            v = 0.80
        return max(0.0, min(2.0, v))

    def _set_threshold(self, v: float):
        s = QSettings()
        s.setValue(self.THRESH_KEY, float(v))

    def _get_life_basis(self) -> str:
        s = QSettings()
        v = (s.value(self.LIFE_BASIS_KEY, "page", str) or "page").lower()
        return "drive" if v.startswith("d") else "page"

    def _set_life_basis(self, v: str):
        s = QSettings()
        s.setValue(self.LIFE_BASIS_KEY, (v or "page").lower())

    def _update_threshold_label(self):
        if hasattr(self, "_thr_label") and self._thr_label is not None:
            self._thr_label.setText(f"Due threshold: {self._get_threshold() * 100:.1f}%")

    def _update_basis_label(self):
        if hasattr(self, "_basis_label") and self._basis_label is not None:
            self._basis_label.setText(f"Basis: {self._get_life_basis().upper()}")

    def _open_due_threshold_dialog(self):
        dlg = FramelessDialog(self, "Due Threshold", self._icon_dir)

        top = QLabel("Drag to set the fraction of life used that counts as DUE (0.01–2.00).", dlg)
        top.setObjectName("DialogLabel")

        cur_thr = self._get_threshold()
        slider = QSlider(Qt.Orientation.Horizontal, dlg)
        slider.setRange(1, 200)
        slider.setSingleStep(1)
        slider.setPageStep(5)
        slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        slider.setTickInterval(10)
        slider.setValue(self._thr_to_slider(cur_thr))

        pct_box = QDoubleSpinBox(dlg)
        pct_box.setObjectName("DialogInput")
        pct_box.setRange(1.0, 200.0)
        pct_box.setDecimals(1)
        pct_box.setSingleStep(0.1)
        pct_box.setSuffix("%")
        pct_box.setAlignment(Qt.AlignmentFlag.AlignRight)
        pct_box.setFixedWidth(80)
        pct_box.setValue(cur_thr * 100.0)

        btn_row = QHBoxLayout()
        reset_btn = QPushButton("Default", dlg)
        save_btn = QPushButton("Save", dlg)
        btn_row.addStretch(1)
        btn_row.addWidget(reset_btn)
        btn_row.addWidget(save_btn)

        dlg._content_layout.addWidget(top)
        r1 = QHBoxLayout()
        r1.setContentsMargins(0, -2, 0, 0) 
        r1.addWidget(slider, 1)
        r1.addWidget(pct_box)
        dlg._content_layout.addLayout(r1)
        dlg._content_layout.addLayout(btn_row)

        def _apply(thr: float):
            thr = max(0.01, min(2.00, float(thr)))
            self._set_threshold(thr)
            self._update_threshold_label()
            if hasattr(self, "_thr_label"):
                self._thr_label.repaint()
            return thr

        def on_slider_changed(_val: int):
            thr = self._slider_to_thr(slider.value())
            pct_box.blockSignals(True)
            pct_box.setValue(thr * 100.0)
            pct_box.blockSignals(False)
            _apply(thr)

        def on_pct_changed(pct_val: float):
            thr = float(pct_val) / 100.0
            thr = _apply(thr)
            slider.blockSignals(True)
            slider.setValue(self._thr_to_slider(thr))
            slider.blockSignals(False)

        slider.valueChanged.connect(on_slider_changed)
        pct_box.valueChanged.connect(on_pct_changed)

        def on_reset():
            def_thr = 0.90
            slider.blockSignals(True)
            slider.setValue(self._thr_to_slider(def_thr))
            slider.blockSignals(False)
            pct_box.blockSignals(True)
            pct_box.setValue(def_thr * 100.0)
            pct_box.blockSignals(False)
            _apply(def_thr)

        reset_btn.clicked.connect(on_reset)
        save_btn.clicked.connect(dlg.accept)
        dlg.exec()

    HISTORY_KEY = "recent_serials"
    MAX_HISTORY = 25

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PmGen")
        self.resize(1100, 720)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        # Auth UI state
        self._signed_in: bool = False
        self._current_user: str = ""
        self._auto_login_attempted: bool = False

        # Global tracking + event filter
        app = QApplication.instance()
        app.installEventFilter(self)
        self.setMouseTracking(True)

        central = QWidget()
        self._vbox = QVBoxLayout(central)
        self._vbox.setContentsMargins(6, 6, 6, 6)
        self._vbox.setSpacing(6)

        self._secondary_bar = self._build_secondary_bar()
        self._vbox.addWidget(self._secondary_bar, 0)

        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setMaximumBlockCount(2000)
        self._apply_colorized_highlighter()
        self.editor.setObjectName("MainEditor")
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.editor.setMouseTracking(True)
        self._vbox.addWidget(self.editor, 1)

        self._log_queue = deque()
        self._log_timer = QTimer(self)
        self._log_timer.setInterval(40)
        self._log_timer.timeout.connect(self._flush_log_queue)
        self._log_timer.start()

        self._log_batch_limit = 200
        self._bulk_thread: QThread | None = None
        self._bulk_runner = None

        clear_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        clear_shortcut.activated.connect(self._clear_output_window)

        self.setCentralWidget(central)
        self.centralWidget().setMouseTracking(True)

        self.toolbar = self._build_toolbar()
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        self._update_auth_ui()
        QTimer.singleShot(0, self._attempt_auto_login)

        self._rs = ResizeState()

    # Never react to OS palette/theme changes
    def event(self, ev):
        if ev.type() in (
            QEvent.Type.ApplicationPaletteChange,
            getattr(QEvent.Type, "ColorSchemeChange", QEvent.Type.None_)
        ):
            return True
        return super().event(ev)

    # ---------------- Secondary Bar ----------------
    def _auto_capitalize(self, text: str):
        le = self._id_combo.lineEdit()
        cursor = le.cursorPosition()
        le.blockSignals(True)
        le.setText(text.upper())
        le.setCursorPosition(cursor)
        le.blockSignals(False)

    def _build_secondary_bar(self) -> QWidget:
        bar = QWidget(self)
        bar.setObjectName("SecondaryBar")

        h = QHBoxLayout(bar)
        h.setContentsMargins(8, 6, 8, 6)
        h.setSpacing(8)

        self.user_label = QLabel("Not signed in", bar)
        self.user_label.setObjectName("UserLabel")
        h.addWidget(self.user_label, 0, Qt.AlignmentFlag.AlignVCenter)
        h.addStretch(1)

        self._thr_label = QLabel("", bar)
        self._thr_label.setObjectName("DialogLabel")
        self._update_threshold_label()
        self._basis_label = QLabel("", bar)
        self._basis_label.setObjectName("DialogLabel")
        self._update_basis_label()
        h.addWidget(self._thr_label, 0, Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(self._basis_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self._id_combo = QComboBox(bar)
        self._id_combo.setObjectName("IdInput")
        self._id_combo.setEditable(True)
        self._id_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._id_combo.setMaxVisibleItems(12)
        self._id_combo.setMinimumWidth(200)
        self._id_combo.setFixedHeight(28)

        le = self._id_combo.lineEdit()
        le.setPlaceholderText("")
        rx = QRegularExpression(r"[A-Za-z0-9]*")
        le.setValidator(QRegularExpressionValidator(rx, self))
        le.textChanged.connect(self._auto_capitalize)

        self._load_id_history()

        self._generate_btn = QPushButton("Generate", bar)
        self._generate_btn.setObjectName("GenerateBtn")
        self._generate_btn.setFixedHeight(28)
        self._generate_btn.clicked.connect(self._on_generate_clicked)

        h.addWidget(self._id_combo, 0)
        h.addWidget(self._generate_btn, 0)
        return bar

    def _on_generate_clicked(self):
        le = self._id_combo.lineEdit()
        text = le.text().strip().upper()
        if not text:
            CustomMessageBox.warn(self, "Missing Serial", "Please Enter A Serial Number", self._icon_dir)
            return

        items = [text] + [
            self._id_combo.itemText(i)
            for i in range(self._id_combo.count())
            if self._id_combo.itemText(i).upper() != text
        ]
        items = items[:self.MAX_HISTORY]
        self._set_history(items)
        self._save_id_history()

        try:
            from pmgen.engine import generate_from_bytes
        except Exception:
            from pmgen.engine.single_report import generate_from_bytes

        data = None
        try:
            from pmgen.io.http_client import get_service_file_bytes
            data = get_service_file_bytes(text, "PMSupport")
        except Exception:
            try:
                if hasattr(self, "act_login"):
                    self.act_login.trigger()
                from pmgen.io.http_client import get_service_file_bytes as _refetch
                data = _refetch(text, "PMSupport")
            except Exception as e2:
                CustomMessageBox.warn(self, "Online fetch failed", str(e2), self._icon_dir)

        if data is None:
            path, _ = QFileDialog.getOpenFileName(
                self,
                "Open PM Report",
                "",
                "PM Export (*.csv *.txt);;All Files (*.*)"
            )
            if not path:
                return
            with open(path, "rb") as f:
                data = f.read()

        try:
            out = generate_from_bytes(
                pm_pdf_bytes=data,
                threshold=self._get_threshold(),
                life_basis=self._get_life_basis(),
                show_all=self._get_show_all(),
            )
            self.editor.setPlainText(out)
            self._apply_colorized_highlighter()
        except Exception as e:
            CustomMessageBox.warn(self, "Generate failed", str(e), self._icon_dir)
            
    def _load_id_history(self):
        s = QSettings()
        history = s.value(self.HISTORY_KEY, [], list)
        if not isinstance(history, list):
            history = list(history)
        self._set_history([h for h in history if isinstance(h, str) and h])

    def _save_id_history(self):
        s = QSettings()
        s.setValue(self.HISTORY_KEY, [self._id_combo.itemText(i) for i in range(self._id_combo.count())])

    def _set_history(self, items: list[str]):
        self._id_combo.clear()
        for it in items:
            self._id_combo.addItem(it)

    def closeEvent(self, ev):
        self._save_id_history()
        super().closeEvent(ev)

    # ---------------- Toolbar ----------------
    def _build_toolbar(self) -> QToolBar:
        tb = QToolBar("Window Controls", self)
        tb.setMovable(False)
        tb.setFloatable(False)
        tb.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        tb.setIconSize(QSize(18, 18))
        tb.setContentsMargins(0, 0, 0, 0)
        tb.setMouseTracking(True)

        bar = QWidget()
        bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.setMouseTracking(True)
        h = QHBoxLayout(bar)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        settings_btn = QToolButton()
        settings_btn.setObjectName("SettingsBtn")
        settings_btn.setText("Settings ▾")
        settings_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        settings_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        settings_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        settings_btn.setFixedHeight(36)
        settings_btn.setMouseTracking(True)

        settings_menu = QMenu(settings_btn)
        self.act_login = QAction("Login", self)
        self.act_login.triggered.connect(self._open_login_dialog)
        self.act_logout = QAction("Logout", self)
        self.act_logout.triggered.connect(self._logout)
        act_prefs = QAction("Clear Output Window", self)
        act_prefs.triggered.connect(self._clear_output_window)
        act_about = QAction("About", self)
        act_about.triggered.connect(self._show_about)
        settings_menu.addAction(self.act_login)
        settings_menu.addAction(self.act_logout)

        act_due = QAction("Due Threshold…", self)
        act_due.triggered.connect(self._open_due_threshold_dialog)
        settings_menu.addAction(act_due)

        act_basis = QAction("Life Basis…", self)
        act_basis.triggered.connect(self._open_life_basis_dialog)
        settings_menu.addAction(act_basis)

        act_show_all = QAction("Show All Items", self)
        act_show_all.setToolTip("Show all PL items in the Most-Due section, even if under the due threshold.")
        act_show_all.setCheckable(True)
        act_show_all.setChecked(self._get_show_all())
        def _toggle_show_all(checked: bool):
            self._set_show_all(checked)
        act_show_all.toggled.connect(_toggle_show_all)
        settings_menu.addAction(act_show_all)

        act_color = QAction("Colorized Output", self)
        act_color.setCheckable(True)
        act_color.setChecked(self._get_colorized())
        def _toggle_color(checked: bool):
            self._set_colorized(checked)
            self._apply_colorized_highlighter()
        act_color.toggled.connect(_toggle_color)
        settings_menu.addAction(act_color)

        settings_menu.addAction(act_prefs)
        settings_menu.addAction(act_about)
        settings_btn.setMenu(settings_menu)

        bulk_btn = QToolButton()
        bulk_btn.setObjectName("BulkBtn")
        bulk_btn.setText("Bulk ▾")
        bulk_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        bulk_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        bulk_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        bulk_btn.setFixedHeight(36)
        bulk_btn.setMouseTracking(True)

        bulk_menu = QMenu(bulk_btn)
        act_run_bulk = QAction("Run Bulk…", self)
        act_run_bulk.triggered.connect(self._start_bulk)
        act_bulk_settings = QAction("Bulk Settings…", self)
        act_bulk_settings.triggered.connect(self._open_bulk_settings)
        bulk_menu.addAction(act_run_bulk)
        bulk_menu.addSeparator()
        bulk_menu.addAction(act_bulk_settings)
        bulk_btn.setMenu(bulk_menu)

        spacer_l_fixed = QWidget(); spacer_l_fixed.setFixedWidth(6); spacer_l_fixed.setMouseTracking(True)

        drag_left = DragRegion(self)
        title = TitleDragLabel("PmGen", self)
        drag_right = DragRegion(self)

        icon_dir = os.path.join(os.path.dirname(__file__), "icons")
        minimize_icon = os.path.join(icon_dir, "minimize.svg")
        fullscreen_icon = os.path.join(icon_dir, "fullscreen.svg")
        exit_icon = os.path.join(icon_dir, "exit.svg")
        self._icon_dir = icon_dir

        btn_min = QToolButton(); btn_min.setMouseTracking(True)
        btn_min.setDefaultAction(QAction(QIcon(minimize_icon), "Minimize", self, triggered=self.showMinimized))

        self._act_full = QAction(QIcon(fullscreen_icon), "Fullscreen", self)
        self._act_full.setToolTip("Toggle Fullscreen")
        self._act_full.setCheckable(True)
        self._act_full.triggered.connect(self._toggle_fullscreen)
        btn_full = QToolButton(); btn_full.setDefaultAction(self._act_full); btn_full.setMouseTracking(True)

        btn_exit = QToolButton(); btn_exit.setMouseTracking(True)
        btn_exit.setDefaultAction(QAction(QIcon(exit_icon), "Exit", self, triggered=self._confirm_exit))

        right_box = QWidget(); right_box.setMouseTracking(True)
        right_box_l = QHBoxLayout(right_box)
        right_box_l.setContentsMargins(0, 0, 0, 0)
        right_box_l.setSpacing(0)
        right_box_l.addWidget(btn_min)
        right_box_l.addWidget(btn_full)
        right_box_l.addWidget(btn_exit)

        h.addWidget(settings_btn, 0)
        h.addWidget(bulk_btn, 0)
        h.addWidget(spacer_l_fixed, 0)
        h.addWidget(drag_left, 1)
        h.addWidget(title, 0)
        h.addWidget(drag_right, 1)
        h.addWidget(right_box, 0)

        tb.addWidget(bar)
        return tb
    
    def _open_life_basis_dialog(self):
        dlg = FramelessDialog(self, "Life Basis", self._icon_dir)
        lbl = QLabel("Choose which counter to base life on (fallback to the other if missing).", dlg)
        lbl.setObjectName("DialogLabel")

        box = QComboBox(dlg)
        box.setObjectName("DialogInput")
        box.addItems(["Page", "Drive"])
        try:
            box.setCurrentIndex(0 if self._get_life_basis() == "page" else 1)
        except Exception:
            pass

        row = QHBoxLayout()
        row.addStretch(1)
        btn = QPushButton("Save", dlg)
        row.addWidget(btn)

        def _save():
            self._set_life_basis("page" if box.currentIndex() == 0 else "drive")
            self._update_basis_label()
            if hasattr(self, "_basis_label"): self._basis_label.repaint()
            dlg.accept()

        btn.clicked.connect(_save)
        dlg._content_layout.addWidget(lbl)
        dlg._content_layout.addWidget(box)
        dlg._content_layout.addLayout(row)
        dlg.exec()
    
    def _clear_output_window(self):
        self.editor.clear()

    # ---------------- Unified Login (via http_client) ----------------
    def _open_login_dialog(self):
        dlg = FramelessDialog(self, "Login", self._icon_dir)

        username_label = QLabel("Enter Username:", dlg)
        username_label.setObjectName("DialogLabel")
        username = QLineEdit(dlg); username.setObjectName("DialogInput")

        # seed with last remembered username if any
        s = QSettings()
        last_user = s.value(self.AUTH_USERNAME_KEY, "", str)
        if last_user:
            username.setText(last_user)

        password_label = QLabel("Enter Password:", dlg); password_label.setObjectName("DialogLabel")
        password = QLineEdit(dlg); password.setEchoMode(QLineEdit.EchoMode.Password); password.setObjectName("DialogInput")

        dlg._content_layout.addWidget(username_label)
        dlg._content_layout.addWidget(username)
        dlg._content_layout.addWidget(password_label)
        dlg._content_layout.addWidget(password)

        row = QHBoxLayout()
        stay_logged_in_checkbox = QCheckBox("Stay Logged In", dlg)
        stay_logged_in_checkbox.setObjectName("DialogCheckbox")
        stay_logged_in_checkbox.setChecked(bool(s.value(self.AUTH_REMEMBER_KEY, False, bool)))

        btn_login = QPushButton("Login", dlg)
        btn_login.setDefault(True)

        def _do_login():
            u = (username.text() or "").strip()
            p = password.text() or ""
            if not u or not p:
                CustomMessageBox.warn(self, "Login", "Please enter username and password.", self._icon_dir)
                return

            btn_login.setEnabled(False)
            self.user_label.setText("Signing in…")
            self.editor.appendPlainText(f"[Auto-Login] Attempting as {u}…")

            # Save creds to http_client; then verify by calling http_client.login(sess)
            try:
                from pmgen.io import http_client as hc
                hc.save_credentials(u, p)

                sess = requests.Session()
                hc.login(sess)  # raises on failure

                # persist UI prefs
                s.setValue(self.AUTH_REMEMBER_KEY, bool(stay_logged_in_checkbox.isChecked()))
                s.setValue(self.AUTH_USERNAME_KEY, u)

                # UI state
                self._signed_in = True
                self._current_user = u
                self._update_auth_ui()

                self.editor.appendPlainText(f"[Auto-Login] {u} — success")
                CustomMessageBox.info(self, "Login", "Login successful.", self._icon_dir)
                dlg.accept()
            except Exception as e:
                # clear possibly bad creds
                try:
                    hc.clear_credentials()
                except Exception:
                    pass
                self._signed_in = False
                self._current_user = ""
                self._update_auth_ui()
                self.editor.appendPlainText(f"[Auto-Login] {u} — failed: {e}")
                CustomMessageBox.warn(self, "Login failed", str(e), self._icon_dir)
            finally:
                btn_login.setEnabled(True)

        btn_login.clicked.connect(_do_login)

        row.addWidget(stay_logged_in_checkbox, alignment=Qt.AlignmentFlag.AlignLeft)
        row.addStretch(1)
        row.addWidget(btn_login)

        dlg._content_layout.addLayout(row)
        dlg.exec()

    def _attempt_auto_login(self):
        if self._auto_login_attempted or self._signed_in:
            return
        self._auto_login_attempted = True

        s = QSettings()
        if not bool(s.value(self.AUTH_REMEMBER_KEY, False, bool)):
            return

        try:
            from pmgen.io import http_client as hc
        except Exception:
            return

        u = None
        p = None
        try:
            u = hc.get_saved_username()
            p = hc.get_saved_password()
        except Exception:
            pass
        if not (u and p):
            # fall back to last username setting; still need password in keyring
            u = s.value(self.AUTH_USERNAME_KEY, "", str) or ""
            if not u:
                return
            try:
                p = hc.get_saved_password()
            except Exception:
                p = None
            if not p:
                return

        self.user_label.setText("Signing in…")
        self.editor.appendPlainText(f"[Auto-Login] Attempting as {u}…")

        try:
            sess = requests.Session()
            hc.login(sess)  # uses saved creds
            self._signed_in = True
            self._current_user = u
            self._update_auth_ui()
            self.editor.appendPlainText(f"[Auto-Login] {u} — success")
        except Exception as e:
            self._signed_in = False
            self._current_user = ""
            self._update_auth_ui()
            self.editor.appendPlainText(f"[Auto-Login] {u} — failed: {e}")

    def _open_bulk_settings(self):
        cfg = self._get_bulk_config()
        s = QSettings()

        unpack_enabled = bool(s.value("bulk/unpack_filter_enabled", False, bool))
        try:
            unpack_extra = int(s.value("bulk/unpack_extra_months", 0, int))
        except Exception:
            unpack_extra = 0

        dlg = FramelessDialog(self, "Bulk Settings", self._icon_dir)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("Top N serials to export:", dlg))
        sp_top = QSpinBox(dlg)
        sp_top.setObjectName("DialogInput")
        sp_top.setRange(1, 9999)
        sp_top.setValue(cfg.top_n)
        row1.addStretch(1)
        row1.addWidget(sp_top)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Parallel workers:", dlg))
        sp_pool = QSpinBox(dlg)
        sp_pool.setObjectName("DialogInput")
        sp_pool.setRange(1, 16)
        sp_pool.setValue(cfg.pool_size)
        row2.addStretch(1)
        row2.addWidget(sp_pool)

        row3 = QHBoxLayout()
        row3.addWidget(QLabel("Output folder:", dlg))
        ed_dir = QLineEdit(cfg.out_dir, dlg)
        ed_dir.setObjectName("DialogInput")
        btn_browse = QPushButton("Browse…", dlg)
        def _pick_dir():
            path = QFileDialog.getExistingDirectory(self, "Select Output Folder", cfg.out_dir or "")
            if path:
                ed_dir.setText(path)
        btn_browse.clicked.connect(_pick_dir)
        row3.addWidget(ed_dir, 1)
        row3.addWidget(btn_browse)

        row4 = QVBoxLayout()
        lbl_bl = QLabel("Blacklist (one pattern per line — supports * and ?):", dlg)
        lbl_bl.setObjectName("DialogLabel")
        bl_edit = QPlainTextEdit(dlg)
        bl_edit.setObjectName("MainEditor")
        bl_edit.setFixedHeight(100)
        bl_edit.setPlainText("\n".join(cfg.blacklist or []))
        row4.addWidget(lbl_bl)
        row4.addWidget(bl_edit)

        row5 = QHBoxLayout()
        cb_unpack = QCheckBox("Enable unpacking date filter", dlg)
        cb_unpack.setObjectName("DialogCheckbox")
        cb_unpack.setChecked(unpack_enabled)
        row5.addWidget(cb_unpack)
        row5.addStretch(1)

        row6 = QHBoxLayout()
        lbl_extra = QLabel("# Months:", dlg)
        lbl_extra.setObjectName("DialogLabel")
        sp_extra = QSpinBox(dlg)
        sp_extra.setObjectName("DialogInput")
        sp_extra.setRange(0, 120)
        sp_extra.setSingleStep(1)
        sp_extra.setValue(max(0, min(120, unpack_extra)))
        row6.addWidget(lbl_extra)
        row6.addWidget(sp_extra)
        row6.addStretch(1)

        lbl_rule = QLabel(
            "Rule: device is filtered out if Today > (Unpacking Date + # months).",
            dlg
        )
        lbl_rule.setObjectName("DialogLabel")

        btns = QHBoxLayout()
        btns.addStretch(1)
        btn_save = QPushButton("Save", dlg)
        def _save_and_close():
            raw = bl_edit.toPlainText()
            patterns = []
            for line in re.split(r"[\n,]+", raw):
                pat = line.strip()
                if pat:
                    patterns.append(pat.upper())

            self._save_bulk_config(BulkConfig(
                top_n=sp_top.value(),
                out_dir=ed_dir.text().strip(),
                pool_size=sp_pool.value(),
                blacklist=patterns
            ))
            s.setValue("bulk/unpack_filter_enabled", bool(cb_unpack.isChecked()))
            s.setValue("bulk/unpack_extra_months", int(sp_extra.value()))
            dlg.accept()
        btn_save.clicked.connect(_save_and_close)
        btns.addWidget(btn_save)

        dlg._content_layout.addLayout(row1)
        dlg._content_layout.addLayout(row2)
        dlg._content_layout.addLayout(row3)
        dlg._content_layout.addLayout(row4)
        dlg._content_layout.addSpacing(8)
        dlg._content_layout.addLayout(row5)
        dlg._content_layout.addLayout(row6)
        dlg._content_layout.addWidget(lbl_rule)
        dlg._content_layout.addLayout(btns)
        dlg.exec()

    def _logout(self):
        # turn off remember-me and forget last username
        s = QSettings()
        s.setValue(self.AUTH_REMEMBER_KEY, False)
        s.setValue(self.AUTH_USERNAME_KEY, "")

        # clear saved creds + close pools + server-side logout (best-effort)
        try:
            from pmgen.io import http_client as hc
            if hasattr(hc, "server_side_logout"):
                try:
                    hc.server_side_logout()
                except Exception:
                    pass
            if hasattr(hc, "SessionPool"):
                try:
                    hc.SessionPool.close_all_pools()
                except Exception:
                    pass
            if hasattr(hc, "clear_credentials"):
                hc.clear_credentials()
        except Exception:
            pass

        self._signed_in = False
        self._current_user = ""
        self._update_auth_ui()

    def _update_auth_ui(self):
        if self._signed_in:
            self.user_label.setText(self._current_user or "(signed in)")
        else:
            self.user_label.setText("Not signed in")

    def _show_about(self):
        ver = globals().get("VERSION", "dev")
        from pmgen.catalog.part_kit_catalog import REGISTRY
        models = sorted([k for k, v in REGISTRY.items() if v is not None])

        def _columns(items, cols=4, pad=12):
            out = []
            for i in range(0, len(items), cols):
                row = items[i:i+cols]
                out.append("".join(s.ljust(pad) for s in row))
            return "\n".join(out)

        about_top = (
            "PmGen\n"
            f"Version: {ver}\n"
            f"Supported models in registry: {len(models)}\n"
            "—\n"
        )
        about_body = _columns(models, cols=4, pad=12) if models else "(No models found in registry)"

        dlg = FramelessDialog(self, "About", self._icon_dir)
        txt = QPlainTextEdit(dlg)
        txt.setReadOnly(True)
        txt.setObjectName("MainEditor")
        txt.setPlainText(about_top + about_body)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_ok = QPushButton("OK", dlg)
        btn_ok.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_ok)

        dlg._content_layout.addWidget(txt)
        dlg._content_layout.addLayout(btn_row)
        dlg.exec()

    @pyqtSlot(str)
    def on_bulk_progress(self, line: str):
        self._log_queue.append(line)

    @pyqtSlot(str)
    def on_bulk_finished(self, msg: str):
        self._log_queue.append(msg)
        self._log_queue.append("[Info] (done)")
        self._bulk_runner = None
        self._bulk_thread = None

    def _flush_log_queue(self):
        if not self._log_queue:
            return
        chunk = []
        for _ in range(min(self._log_batch_limit, len(self._log_queue))):
            chunk.append(self._log_queue.popleft())
        self.editor.appendPlainText("\n".join(chunk))
        self.editor.moveCursor(QTextCursor.MoveOperation.End)

    def _start_bulk(self):
        cfg = self._get_bulk_config()
        cfg.show_all = self._get_show_all()
        self._log_queue.append(f"[Info] Bulk Starting… (Top N={cfg.top_n}, Pool={cfg.pool_size})")

        threshold = self._get_threshold()
        life_basis = self._get_life_basis()

        if self._bulk_thread and self._bulk_thread.isRunning():
            self._log_queue.append("[Info] A run is already active.")
            return

        self._bulk_thread = QThread(self)
        self._bulk_runner = BulkRunner(
            cfg,
            threshold=threshold,
            life_basis=life_basis,
            unpack_filter_enabled=self._get_unpack_filter_enabled(),
            unpack_extra_months=self._get_unpack_extra_months(),
        )
        self._bulk_runner.moveToThread(self._bulk_thread)

        self._bulk_thread.started.connect(self._bulk_runner.run)
        self._bulk_runner.progress.connect(self.on_bulk_progress)
        self._bulk_runner.finished.connect(self.on_bulk_finished)
        self._bulk_runner.finished.connect(self._bulk_thread.quit)
        self._bulk_runner.finished.connect(self._bulk_runner.deleteLater)
        self._bulk_thread.finished.connect(self._bulk_thread.deleteLater)

        self._bulk_thread.start()

    # --------------- Fullscreen + Exit ----------------
    def _toggle_fullscreen(self, checked: bool):
        self.showFullScreen() if checked else self.showNormal()

    def _confirm_exit(self):
        res = CustomMessageBox.confirm(self, "Exit", "Are you sure you want to exit?", self._icon_dir)
        if res == "ok":
            self.close()

    # --------------- Cursor/Event filtering ----------------
    def eventFilter(self, obj, event):
        et = event.type()
        if not self.isFullScreen():
            if et in (QEvent.Type.MouseMove, QEvent.Type.HoverMove):
                self._update_cursor(QCursor.pos())
            elif et == QEvent.Type.Leave:
                self._update_cursor(QCursor.pos())
        return super().eventFilter(obj, event)

    # --------------- Custom Resize Logic ----------------
    def _edge_flags_at_pos(self, pos_global: QPoint):
        pos = self.mapFromGlobal(pos_global)
        r = self.rect()
        left = pos.x() <= BORDER_WIDTH
        right = pos.x() >= r.width() - BORDER_WIDTH
        top = pos.y() <= BORDER_WIDTH
        bottom = pos.y() >= r.height() - BORDER_WIDTH
        return left, right, top, bottom

    def _update_cursor(self, pos_global: QPoint):
        if self.isFullScreen():
            self.unsetCursor()
            return

        left, right, top, bottom = self._edge_flags_at_pos(pos_global)
        if (left and top) or (right and bottom):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif (right and top) or (left and bottom):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif left or right:
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif top or bottom:
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            if self.cursor().shape() != Qt.CursorShape.ArrowCursor:
                self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self.isFullScreen():
            pos_global = e.globalPosition().toPoint()
            left, right, top, bottom = self._edge_flags_at_pos(pos_global)
            if left or right or top or bottom:
                self._rs = ResizeState(
                    resizing=True,
                    edge_left=left, edge_right=right, edge_top=top, edge_bottom=bottom,
                    press_pos=pos_global,
                    press_geom=self.geometry()
                )
                e.accept()
                return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._rs.resizing and not self.isFullScreen():
            delta = e.globalPosition().toPoint() - self._rs.press_pos
            geom = QRect(self._rs.press_geom)
            if self._rs.edge_left:
                new_left = geom.left() + delta.x()
                max_left = geom.right() - 200
                new_left = min(new_left, max_left)
                geom.setLeft(new_left)
            elif self._rs.edge_right:
                geom.setRight(self._rs.press_geom.right() + delta.x())
                if geom.width() < 200:
                    geom.setRight(geom.left() + 200)
            if self._rs.edge_top:
                new_top = geom.top() + delta.y()
                max_top = geom.bottom() - 150
                new_top = min(new_top, max_top)
                geom.setTop(new_top)
            elif self._rs.edge_bottom:
                geom.setBottom(self._rs.press_geom.bottom() + delta.y())
                if geom.height() < 150:
                    geom.setBottom(geom.top() + 150)

            self.setGeometry(geom)
            e.accept()
            return

        if not self.isFullScreen():
            self._update_cursor(e.globalPosition().toPoint())
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._rs.resizing:
            self._rs = ResizeState()
            self._update_cursor(QCursor.pos())
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def enterEvent(self, e):
        if not self.isFullScreen():
            self._update_cursor(QCursor.pos())
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.unsetCursor()
        super().leaveEvent(e)

# ---------------------------- App Entry ----------------------------
def main():
    QCoreApplication.setOrganizationName("IndyBiz")
    QCoreApplication.setApplicationName("PmGen-{VERSION}")

    app = QApplication(sys.argv)
    apply_static_theme(app)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
