from PyQt6.QtWidgets import QApplication

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
QCheckBox#DialogCheckbox::indicator:checked { background:#1f2023; border:1px solid #000000; image: url(_internal/pmgen/assets/icons/checkmark.svg); }
QCheckBox#DialogCheckbox::indicator:unchecked { image: none; }
#DialogLabel { background: #1f2023; color: #e9e9e9; }
#UserLabel { background: #1f2023; color: #e9e9e9; font-weight: 800 }
#DialogInput { background: #2a2c2f; color: #e9e9e9; border: 1px solid #000000; font-weight: 800; }
#DialogInput:focus { background: #2a2c2f; color: #e9e9e9; border-radius: 0; border: 1px solid #000000; font-weight: 800 }
#DialogInput::up-arrow { image: url(_internal/pmgen/assets/icons/up.svg); }
#DialogInput::down-arrow { image: url(_internal/pmgen/assets/icons/down.svg); }

/* Secondary bar */
#SecondaryBar { background: #202225; border: 1px solid #000000; border-radius: 0; padding: 6px; }

/* Keep support for QLineEdit if used anywhere else */
QLineEdit#IdInput { background: #000000; color: #e9e9e9; border: 1px solid #000000; border-radius: 0; padding: 6px 8px; font-weight: 800 }
QLineEdit#IdInput:focus { border: 1px solid #000000; }

/* Editable combo styling for the recent-serials input */
QComboBox#IdInput {
    border: 1px solid #000000;
    border-radius: 0;
    padding-left: 8px; /* text padding */
    background: #202225; /* Match LineEdit background */
    color: #e9e9e9;
    font-weight: 800;
    selection-background-color: #3a3d41;
}

QComboBox#IdInput QLineEdit {
    background: transparent; /* Let parent color show through */
    color: #e9e9e9;
    border: none;
    padding: 0px; /* Reset padding here, handled by parent */
    font-weight: 800;
}

QComboBox#IdInput::drop-down {
    subcontrol-origin: padding;
    subcontrol-position: top right;
    width: 20px; /* Give it width so we can see the arrow */
    border-left-width: 0px;
    border-left-color: #3a3d41;
    border-left-style: solid; 
    border-top-right-radius: 0;
    border-bottom-right-radius: 0;
    background: #2a2c2f; /* Slightly lighter than input for contrast */
}

QComboBox#IdInput::down-arrow {
    image: url(_internal/pmgen/assets/icons/down.svg);
    width: 12px;
    height: 12px;
}

QComboBox#IdInput QAbstractItemView {
    background: #2a2c2f;       /* Dark background for the list */
    border: 1px solid #000000; /* Border around the list */
    color: #e9e9e9;            /* Text color */
    selection-background-color: #3a3d41; /* Hover color */
    selection-color: #ffffff;
    outline: 0;
    padding: 2px;
}

QComboBox#IdInput QAbstractItemView::item {
    min-height: 24px;
    padding: 4px;
}

QComboBox#IdInput QAbstractItemView QScrollBar:vertical {
    background: #1e1f22;
    width: 10px;
}

/* 1. The floating list container */
QAbstractItemView#IdCompleterPopup {
    border: 1px solid #000000;
    background: #2a2c2f; /* Dark background */
    color: #e9e9e9;      /* Text color */
    selection-background-color: #3a3d41; /* Hover/Select color */
    selection-color: #ffffff;
    padding: 2px;
    outline: 0;
}

/* 2. The items inside the list */
QAbstractItemView#IdCompleterPopup::item {
    padding: 4px 8px;
    min-height: 24px;
}

/* 3. The Scrollbar inside the completer */
/* We need to copy your scrollbar styles here specifically for the ID selector */
QAbstractItemView#IdCompleterPopup QScrollBar:vertical {
    border-left: 1px solid #000000;
    background: #1e1f22;
    width: 14px;
    margin: 0px;
}
QAbstractItemView#IdCompleterPopup QScrollBar::handle:vertical {
    background: #44474d;
    min-height: 20px;
    border: 1px solid #000000;
    margin: 2px;
}
QAbstractItemView#IdCompleterPopup QScrollBar::handle:vertical:hover { 
    background: #5f636a; 
}
QAbstractItemView#IdCompleterPopup QScrollBar::add-line:vertical, 
QAbstractItemView#IdCompleterPopup QScrollBar::sub-line:vertical { 
    height: 0px; 
}
QAbstractItemView#IdCompleterPopup QScrollBar::add-page:vertical, 
QAbstractItemView#IdCompleterPopup QScrollBar::sub-page:vertical { 
    background: none; 
}

QPushButton#GenerateBtn { padding: 6px 12px; border-radius: 0; border: 1px solid #000000; background: #2a2c2f; color: #e9e9e9; }
QPushButton#GenerateBtn:hover { background: #33363b; }

QPushButton { padding: 6px 12px; border-radius: 0; border: 1px solid #000000; background: #2a2c2f; color: #e9e9e9; }
QPushButton:hover { background: #33363b; }
QDoubleSpinBox#DialogInput {
    border: 1px solid #000000;
    background: #2a2c2f;
    color: #ffffff;
    border-radius: 0;
    padding-right: 6px;  
    selection-background-color: #000000;
    selection-color: #ffffff;
}

/* Remove both arrow buttons completely */
QDoubleSpinBox#DialogInput::up-button,
QDoubleSpinBox#DialogInput::down-button { width: 0; height: 0; border: none; margin: 0; padding: 0; }

/* Hide arrow icons */
QDoubleSpinBox#DialogInput::up-arrow,
QDoubleSpinBox#DialogInput::down-arrow { image: none; }

/* Disabled state */
QDoubleSpinBox#DialogInput:disabled { color: #8a8d91; background: #191b1e; border-color: #2a2c2f; }

QScrollBar:vertical {
    border-left: 1px solid #000000;
    background: #1e1f22;
    width: 14px;
    margin: 0px;
}
QScrollBar::handle:vertical {
    background: #44474d;
    min-height: 20px;
    border: 1px solid #000000;
    margin: 2px;
}
QScrollBar::handle:vertical:hover { background: #5f636a; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0px; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }

#SettingsBtn {
    color: #ffffff;
}
#BulkBtn {
    color: #ffffff;
}

QLabel {
    color: #ffffff;
}

#DialogCheckbox {
    color: #ffffff;
}

QSlider::groove:horizontal#ThresholdSlider {
    border: 1px solid #000000;
    background: #181a1b;
    height: 8px;
    margin: 2px 0;
}

QSlider::handle:horizontal#ThresholdSlider {
    background: #44474d;
    border: 1px solid #000000;
    width: 16px;
    height: 16px;
    margin: -5px 0;
    border-radius: 0;
}

QSlider::handle:horizontal:hover#ThresholdSlider {
    background: #5f636a;
}

QSlider::sub-page:horizontal#ThresholdSlider {
    background: #2a2c2f;
    border: 1px solid #000000;
    height: 8px;
}

QSlider::add-page:horizontal#ThresholdSlider {
    background: #181a1b;
    border: 1px solid #000000;
    height: 8px;
}

QComboBox#DialogInput QAbstractItemView {
    background: #2a2c2f;
    border: 1px solid #000000;
    color: #e9e9e9;
    selection-background-color: #3a3d41;
    selection-color: #ffffff;
    outline: 0;
}

QProgressBar#ProgressBar {
    border: 1px solid #000000;
    background: #1e1f22;
    color: #e9e9e9;
    text-align: center;
    border-radius: 0;
}

QProgressBar#ProgressBar::chunk {
    background-color: #44474d;
    width: 1px; 
}

QTabWidget::pane { 
    border: 1px solid #000000;
    background: #181a1b;
    margin-top: -1px; /* Overlap border */
}

QTabWidget::tab-bar {
    alignment: left;
}

QTabBar::tab {
    background: #202225;
    color: #888888;
    padding: 8px 20px;
    border: 1px solid #000000;
    border-bottom: none;
    border-top-left-radius: 0px;
    border-top-right-radius: 0px;
    margin-right: 2px;
    font-weight: 600;
}

QTabBar::tab:selected {
    background: #2a2c2f;
    color: #ffffff;
    border-bottom: 1px solid #2a2c2f; /* Mask the pane border */
}

QTabBar::tab:hover:!selected {
    background: #25272a;
    color: #cccccc;
}

QTableView {
    background-color: #1e1f22; 
    color: #e9e9e9;
    border: 1px solid #000000;
    gridline-color: #2a2c2f;
    selection-background-color: #3a3d41;
    selection-color: #ffffff;
    alternate-background-color: #232529;
}
QHeaderView::section {
    background-color: #202225;
    color: #e9e9e9;
    padding: 6px;
    border: 1px solid #000000;
    font-weight: bold;
}
QTableCornerButton::section {
    background-color: #202225;
    border: 1px solid #000000;
}

QTableView 
{ 
    border: 1px solid #333; 
    gridline-color: #444; 
}
QHeaderView::section 
{ 
    background-color: #2d2d2d; 
    padding: 4px; 
    border: none; 
    font-weight: bold;
}
"""

def apply_static_theme(app: QApplication):
    app.setStyle("Fusion")
    app.setStyleSheet(GLOBAL_STYLE_DARK)