from __future__ import annotations
import sys, os, re
import requests
from collections import deque
from PyQt6.QtCore import (
    Qt, QSize, QPoint, QRect, QEvent, QRegularExpression, 
    QCoreApplication, QSettings, QThread, pyqtSlot, QTimer
)
from PyQt6.QtGui import (
    QAction, QIcon, QCursor, QRegularExpressionValidator, QKeySequence, 
    QShortcut, QTextCursor 
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPlainTextEdit,
    QToolBar, QSizePolicy, QToolButton, QHBoxLayout, QLabel, QMenu,
    QPushButton, QLineEdit, QComboBox, QCheckBox, QSlider, 
    QSpinBox, QDoubleSpinBox, QFileDialog
)

# Imports from our new split files
from .theme import apply_static_theme
from .components import (
    DragRegion, TitleDragLabel, FramelessDialog, CustomMessageBox, ResizeState
)
from .highlighter import OutputHighlighter
from .workers import BulkConfig, BulkRunner

VERSION = "2.2.3"
SERVICE_NAME = "PmGen"

# Constants
BORDER_WIDTH = 8
BULK_TOPN_KEY = "bulk/top_n"
BULK_DIR_KEY  = "bulk/out_dir"
BULK_POOL_KEY = "bulk/pool_size"
BULK_BLACKLIST_KEY = "bulk/blacklist"

class MainWindow(QMainWindow):
    # ---- PM settings Keys ----
    THRESH_KEY = "pm/due_threshold"
    THRESH_ENABLED_KEY = "pm/due_threshold_enabled"
    LIFE_BASIS_KEY = "pm/life_basis"
    COLORIZED_KEY = "ui/colorized_output"
    SHOW_ALL_KEY = "ui/show_all_items"

    BULK_UNPACK_KEY_ENABLE = "bulk/unpack_filter_enabled"
    BULK_UNPACK_KEY_EXTRA  = "bulk/unpack_extra_months"

    # ---- Auth prefs Keys ----
    AUTH_REMEMBER_KEY = "auth/remember"
    AUTH_USERNAME_KEY = "auth/username"
    HISTORY_KEY = "recent_serials"
    MAX_HISTORY = 25

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PmGen")
        self.resize(1100, 720)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        
        # Paths
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            base_dir = sys._MEIPASS
        else:
            # Assumes this file is in pmgen/ui/
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self._icon_dir = os.path.join(base_dir, "pmgen", "assets", "icons")

        # Auth UI state
        self._signed_in: bool = False
        self._current_user: str = ""
        self._auto_login_attempted: bool = False

        # Global tracking + event filter
        app = QApplication.instance()
        app.installEventFilter(self)
        self.setMouseTracking(True)

        # UI Setup
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

        self.setCentralWidget(central)
        self.centralWidget().setMouseTracking(True)

        self.toolbar = self._build_toolbar()
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        # Logging / Threads
        self._log_queue = deque()
        self._log_timer = QTimer(self)
        self._log_timer.setInterval(40)
        self._log_timer.timeout.connect(self._flush_log_queue)
        self._log_timer.start()
        self._log_batch_limit = 200
        self._bulk_thread: QThread | None = None
        self._bulk_runner = None

        # Shortcuts
        clear_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        clear_shortcut.activated.connect(self._clear_output_window)

        self._update_auth_ui()
        QTimer.singleShot(0, self._attempt_auto_login)

        self._rs = ResizeState()

    # =========================================================================
    #  Settings Management
    # =========================================================================

    def _get_unpack_filter_enabled(self) -> bool:
        return bool(QSettings().value(self.BULK_UNPACK_KEY_ENABLE, False, bool))

    def _get_unpack_extra_months(self) -> int:
        try: v = int(QSettings().value(self.BULK_UNPACK_KEY_EXTRA, 0, int))
        except: v = 0
        return max(0, min(120, v))

    def _get_bulk_config(self) -> BulkConfig:
        s = QSettings()
        top_n = int(s.value(BULK_TOPN_KEY, 25, int))
        out   = s.value(BULK_DIR_KEY, "", str)
        pool  = int(s.value(BULK_POOL_KEY, 4, int))
        bl_raw = s.value(BULK_BLACKLIST_KEY, "", str) or ""
        bl = [line.strip().upper() for line in re.split(r"[,\n]+", bl_raw) if line.strip()]
        return BulkConfig(top_n=max(1, min(9999, top_n)), out_dir=out, pool_size=max(1, min(16, pool)), blacklist=bl)

    def _save_bulk_config(self, cfg: BulkConfig):
        s = QSettings()
        s.setValue(BULK_TOPN_KEY, int(cfg.top_n))
        s.setValue(BULK_DIR_KEY, cfg.out_dir or "")
        s.setValue(BULK_POOL_KEY, int(cfg.pool_size))
        s.setValue(BULK_BLACKLIST_KEY, "\n".join(cfg.blacklist or []))

    def _get_show_all(self) -> bool:
        return bool(QSettings().value(self.SHOW_ALL_KEY, False, bool))

    def _set_show_all(self, on: bool):
        QSettings().setValue(self.SHOW_ALL_KEY, bool(on))

    def _get_colorized(self) -> bool:
        return bool(QSettings().value(self.COLORIZED_KEY, True, bool))

    def _set_colorized(self, on: bool):
        QSettings().setValue(self.COLORIZED_KEY, bool(on))

    def _get_threshold(self) -> float:
        try: v = float(QSettings().value(self.THRESH_KEY, 0.80, float))
        except: v = 0.80
        return max(0.0, min(1.0, v))

    def _set_threshold(self, v: float):
        QSettings().setValue(self.THRESH_KEY, float(v))

    def _get_threshold_enabled(self) -> bool:
        return bool(QSettings().value(self.THRESH_ENABLED_KEY, False, bool))

    def _set_threshold_enabled(self, on: bool):
        QSettings().setValue(self.THRESH_ENABLED_KEY, bool(on))
        self._update_threshold_label()

    def _get_life_basis(self) -> str:
        v = (QSettings().value(self.LIFE_BASIS_KEY, "page", str) or "page").lower()
        return "drive" if v.startswith("d") else "page"

    def _set_life_basis(self, v: str):
        QSettings().setValue(self.LIFE_BASIS_KEY, (v or "page").lower())

    def _load_id_history(self):
        h = QSettings().value(self.HISTORY_KEY, [], list)
        if not isinstance(h, list): h = list(h)
        self._set_history([x for x in h if isinstance(x, str) and x])

    def _save_id_history(self):
        QSettings().setValue(self.HISTORY_KEY, [self._id_combo.itemText(i) for i in range(self._id_combo.count())])

    def _set_history(self, items: list[str]):
        self._id_combo.clear()
        for it in items: self._id_combo.addItem(it)

    # =========================================================================
    #  UI Builders
    # =========================================================================

    def _build_toolbar(self) -> QToolBar:
            tb = QToolBar("Window Controls", self)
            tb.setMovable(False)
            tb.setFloatable(False)
            tb.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
            tb.setContentsMargins(0, 0, 0, 0)
            tb.setMouseTracking(True)

            bar = QWidget()
            bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
            bar.setMouseTracking(True)
            
            h = QHBoxLayout(bar)
            # --- FIX START ---

            h.setContentsMargins(BORDER_WIDTH, BORDER_WIDTH, BORDER_WIDTH, 0)

            
            h.setSpacing(0)

            # Settings Menu
            settings_btn = QToolButton(); settings_btn.setObjectName("SettingsBtn")
            settings_btn.setText("Settings ▾"); settings_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            settings_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly); settings_btn.setFixedHeight(36)
            settings_menu = QMenu(settings_btn)
            
            self.act_login = QAction("Login", self); self.act_login.triggered.connect(self._open_login_dialog)
            self.act_logout = QAction("Logout", self); self.act_logout.triggered.connect(self._logout)
            settings_menu.addAction(self.act_login); settings_menu.addAction(self.act_logout)
            
            act_due = QAction("Optional Threshold", self); act_due.triggered.connect(self._open_due_threshold_dialog)
            settings_menu.addAction(act_due)
            
            act_basis = QAction("Life Basis", self); act_basis.triggered.connect(self._open_life_basis_dialog)
            settings_menu.addAction(act_basis)
            
            act_show_all = QAction("Show All Items", self); act_show_all.setCheckable(True)
            act_show_all.setChecked(self._get_show_all())
            act_show_all.toggled.connect(self._set_show_all)
            settings_menu.addAction(act_show_all)
            
            act_color = QAction("Colorized Output", self); act_color.setCheckable(True)
            act_color.setChecked(self._get_colorized())
            act_color.toggled.connect(lambda c: (self._set_colorized(c), self._apply_colorized_highlighter()))
            settings_menu.addAction(act_color)
            
            act_clear = QAction("Clear Output Window", self); act_clear.triggered.connect(self._clear_output_window)
            settings_menu.addAction(act_clear)
            act_about = QAction("About", self); act_about.triggered.connect(self._show_about)
            settings_menu.addAction(act_about)
            settings_btn.setMenu(settings_menu)

            # Bulk Menu
            bulk_btn = QToolButton(); bulk_btn.setObjectName("BulkBtn")
            bulk_btn.setText("Bulk ▾"); bulk_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
            bulk_btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly); bulk_btn.setFixedHeight(36)
            bulk_menu = QMenu(bulk_btn)
            act_run_bulk = QAction("Run Bulk", self); act_run_bulk.triggered.connect(self._start_bulk)
            act_bulk_settings = QAction("Bulk Settings", self); act_bulk_settings.triggered.connect(self._open_bulk_settings)
            bulk_menu.addAction(act_run_bulk); bulk_menu.addSeparator(); bulk_menu.addAction(act_bulk_settings)
            bulk_btn.setMenu(bulk_menu)

            drag_left = DragRegion(self)
            title = TitleDragLabel("PmGen", self)
            drag_right = DragRegion(self)

            # Right Controls
            btn_min = QToolButton(); btn_min.setDefaultAction(QAction(QIcon(os.path.join(self._icon_dir, "minimize.svg")), "Min", self, triggered=self.showMinimized))
            self._act_full = QAction(QIcon(os.path.join(self._icon_dir, "fullscreen.svg")), "Max", self)
            self._act_full.setCheckable(True); self._act_full.triggered.connect(self._toggle_fullscreen)
            btn_full = QToolButton(); btn_full.setDefaultAction(self._act_full)
            btn_exit = QToolButton(); btn_exit.setDefaultAction(QAction(QIcon(os.path.join(self._icon_dir, "exit.svg")), "Exit", self, triggered=self._confirm_exit))

            right_box = QWidget(); right_l = QHBoxLayout(right_box); right_l.setContentsMargins(0,0,0,0); right_l.setSpacing(0)
            right_l.addWidget(btn_min); right_l.addWidget(btn_full); right_l.addWidget(btn_exit)

            h.addWidget(settings_btn, 0); h.addWidget(bulk_btn, 0); h.addWidget(DragRegion(self), 1)
            h.addWidget(title, 0); h.addWidget(drag_right, 1); h.addWidget(right_box, 0)
            tb.addWidget(bar)
            return tb

    def _build_secondary_bar(self) -> QWidget:
        bar = QWidget(self); bar.setObjectName("SecondaryBar")
        h = QHBoxLayout(bar); h.setContentsMargins(8, 6, 8, 6); h.setSpacing(8)

        self.user_label = QLabel("Not signed in", bar); self.user_label.setObjectName("UserLabel")
        h.addWidget(self.user_label, 0, Qt.AlignmentFlag.AlignVCenter)
        h.addStretch(1)

        self._thr_label = QLabel("", bar); self._thr_label.setObjectName("DialogLabel")
        self._basis_label = QLabel("", bar); self._basis_label.setObjectName("DialogLabel")
        self._update_threshold_label(); self._update_basis_label()
        h.addWidget(self._thr_label, 0, Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(self._basis_label, 0, Qt.AlignmentFlag.AlignVCenter)

        self._id_combo = QComboBox(bar); self._id_combo.setObjectName("IdInput")
        self._id_combo.setEditable(True); self._id_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self._id_combo.setMaxVisibleItems(12); self._id_combo.setMinimumWidth(200); self._id_combo.setFixedHeight(28)
        
        le = self._id_combo.lineEdit()
        le.setValidator(QRegularExpressionValidator(QRegularExpression(r"[A-Za-z0-9]*"), self))
        le.textChanged.connect(self._auto_capitalize)
        self._load_id_history()

        self._generate_btn = QPushButton("Generate", bar); self._generate_btn.setObjectName("GenerateBtn")
        self._generate_btn.setFixedHeight(28); self._generate_btn.clicked.connect(self._on_generate_clicked)

        h.addWidget(self._id_combo, 0); h.addWidget(self._generate_btn, 0)
        return bar

    # =========================================================================
    #  Actions & Logic
    # =========================================================================

    def _update_threshold_label(self):
        if hasattr(self, "_thr_label"):
            txt = "Threshold: 100.0%" if not self._get_threshold_enabled() else f"Threshold: {self._get_threshold() * 100:.1f}%"
            self._thr_label.setText(txt)

    def _update_basis_label(self):
        if hasattr(self, "_basis_label"):
            self._basis_label.setText(f"Basis: {self._get_life_basis().upper()}")

    def _auto_capitalize(self, text: str):
        le = self._id_combo.lineEdit()
        cursor = le.cursorPosition()
        le.blockSignals(True)
        le.setText(text.upper())
        le.setCursorPosition(cursor)
        le.blockSignals(False)

    def _apply_colorized_highlighter(self):
        if not hasattr(self, "_out_highlighter"): self._out_highlighter = None
        want, have = self._get_colorized(), self._out_highlighter is not None
        if want and not have:
            self._out_highlighter = OutputHighlighter(self.editor.document())
        elif not want and have:
            self._out_highlighter.setDocument(None); self._out_highlighter.deleteLater(); self._out_highlighter = None
            self.editor.setPlainText(self.editor.toPlainText())

    def _on_generate_clicked(self):
        le = self._id_combo.lineEdit()
        text = le.text().strip().upper()
        if not text:
            CustomMessageBox.warn(self, "Missing Serial", "Please Enter A Serial Number", self._icon_dir)
            return

        items = [text] + [self._id_combo.itemText(i) for i in range(self._id_combo.count()) if self._id_combo.itemText(i).upper() != text]
        self._set_history(items[:self.MAX_HISTORY])
        self._save_id_history()

        try: from pmgen.engine.single_report import generate_from_bytes
        except ImportError: from pmgen.engine import generate_from_bytes

        data = None
        try:
            from pmgen.io.http_client import get_service_file_bytes
            data = get_service_file_bytes(text, "PMSupport")
        except Exception:
            try:
                if hasattr(self, "act_login"): self.act_login.trigger()
                from pmgen.io.http_client import get_service_file_bytes as _refetch
                data = _refetch(text, "PMSupport")
            except Exception as e2:
                CustomMessageBox.warn(self, "Online fetch failed", str(e2), self._icon_dir)

        if data is None:
            path, _ = QFileDialog.getOpenFileName(self, "Open PM Report", "", "PM Export (*.csv *.txt);;All Files (*.*)")
            if not path: return
            with open(path, "rb") as f: data = f.read()

        try:
            out = generate_from_bytes(
                pm_pdf_bytes=data,
                threshold=self._get_threshold(),
                life_basis=self._get_life_basis(),
                show_all=self._get_show_all(),
                threshold_enabled=self._get_threshold_enabled(),
            )
            self.editor.setPlainText(out)
            self._apply_colorized_highlighter()
        except Exception as e:
            CustomMessageBox.warn(self, "Generate failed", str(e), self._icon_dir)

    def _start_bulk(self):
        cfg = self._get_bulk_config(); cfg.show_all = self._get_show_all()
        self.editor.clear()
        self._log_queue.append(f"[Info] Bulk Starting… (Top N={cfg.top_n}, Pool={cfg.pool_size})")

        if self._bulk_thread and self._bulk_thread.isRunning():
            self._log_queue.append("[Info] A run is already active."); return

        self._bulk_thread = QThread(self)
        self._bulk_runner = BulkRunner(
            cfg, threshold=self._get_threshold(), life_basis=self._get_life_basis(),
            threshold_enabled=self._get_threshold_enabled(),
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

    @pyqtSlot(str)
    def on_bulk_progress(self, line: str): self._log_queue.append(line)

    @pyqtSlot(str)
    def on_bulk_finished(self, msg: str):
        self._log_queue.append(msg); self._log_queue.append("[Info] (done)")
        self._bulk_runner = None; self._bulk_thread = None

    def _flush_log_queue(self):
        if not self._log_queue: return
        chunk = [self._log_queue.popleft() for _ in range(min(self._log_batch_limit, len(self._log_queue)))]
        self.editor.appendPlainText("\n".join(chunk))
        self.editor.moveCursor(QTextCursor.MoveOperation.End)

    def _clear_output_window(self): self.editor.clear()

    # =========================================================================
    #  Dialogs
    # =========================================================================

    def _open_due_threshold_dialog(self):
        dlg = FramelessDialog(self, "Optional Threshold", self._icon_dir)
        top = QLabel("Items over 100% life are always DUE.\nOptionally enable a lower due threshold.", dlg)
        top.setObjectName("DialogLabel")
        
        enable_cb = QCheckBox("Enable Optional threshold", dlg); enable_cb.setObjectName("DialogCheckbox")
        enable_cb.setChecked(self._get_threshold_enabled())

        slider = QSlider(Qt.Orientation.Horizontal, dlg)
        slider.setObjectName("ThresholdSlider")
        slider.setRange(0, 100); slider.setTickInterval(10); slider.setValue(int(self._get_threshold()*100))

        pct_box = QDoubleSpinBox(dlg); pct_box.setObjectName("DialogInput")
        pct_box.setRange(0.0, 100.0); pct_box.setSuffix("%"); pct_box.setValue(self._get_threshold()*100.0)
        
        slider.setEnabled(enable_cb.isChecked()); pct_box.setEnabled(enable_cb.isChecked())
        
        enable_cb.toggled.connect(lambda c: (self._set_threshold_enabled(c), slider.setEnabled(c), pct_box.setEnabled(c)))
        slider.valueChanged.connect(lambda v: pct_box.setValue(float(v)))
        pct_box.valueChanged.connect(lambda v: slider.setValue(int(v)))

        save_btn = QPushButton("Save", dlg)
        save_btn.clicked.connect(lambda: (self._set_threshold(pct_box.value()/100.0), self._update_threshold_label(), dlg.accept()))

        dlg._content_layout.addWidget(top); dlg._content_layout.addWidget(enable_cb)
        r1 = QHBoxLayout(); r1.addWidget(slider, 1); r1.addWidget(pct_box); dlg._content_layout.addLayout(r1)
        r2 = QHBoxLayout(); r2.addStretch(1); r2.addWidget(save_btn); dlg._content_layout.addLayout(r2)
        dlg.exec()

    def _open_login_dialog(self):
        dlg = FramelessDialog(self, "Login", self._icon_dir)
        u_in = QLineEdit(dlg); u_in.setObjectName("DialogInput"); u_in.setPlaceholderText("Username")
        if (last_user := QSettings().value(self.AUTH_USERNAME_KEY, "", str)): u_in.setText(last_user)
        p_in = QLineEdit(dlg); p_in.setEchoMode(QLineEdit.EchoMode.Password); p_in.setObjectName("DialogInput"); p_in.setPlaceholderText("Password")
        
        remember = QCheckBox("Stay Logged In", dlg); remember.setObjectName("DialogCheckbox")
        remember.setChecked(bool(QSettings().value(self.AUTH_REMEMBER_KEY, False, bool)))
        
        btn_login = QPushButton("Login", dlg); btn_login.setDefault(True)

        def _do_login():
            u, p = u_in.text().strip(), p_in.text()
            if not u or not p: return
            btn_login.setEnabled(False); self.user_label.setText("Signing in…"); self.editor.appendPlainText(f"[Auto-Login] Attempting as {u}…")
            try:
                from pmgen.io import http_client as hc
                hc.save_credentials(u, p)
                sess = requests.Session()
                hc.login(sess)
                QSettings().setValue(self.AUTH_REMEMBER_KEY, remember.isChecked())
                QSettings().setValue(self.AUTH_USERNAME_KEY, u)
                self._signed_in = True; self._current_user = u; self._update_auth_ui()
                self.editor.appendPlainText(f"[Auto-Login] {u} — success")
                dlg.accept()
            except Exception as e:
                self._signed_in = False; self._current_user = ""; self._update_auth_ui()
                self.editor.appendPlainText(f"[Auto-Login] {u} — failed: {e}")
                CustomMessageBox.warn(self, "Login failed", str(e), self._icon_dir)
            finally: btn_login.setEnabled(True)

        btn_login.clicked.connect(_do_login)
        dlg._content_layout.addWidget(QLabel("Username", dlg)); dlg._content_layout.addWidget(u_in)
        dlg._content_layout.addWidget(QLabel("Password", dlg)); dlg._content_layout.addWidget(p_in)
        row = QHBoxLayout(); row.addWidget(remember); row.addStretch(1); row.addWidget(btn_login)
        dlg._content_layout.addLayout(row); dlg.exec()

    def _open_life_basis_dialog(self):
        dlg = FramelessDialog(self, "Life Basis", self._icon_dir)
        lbl = QLabel("Choose counter basis (fallback to other if missing).", dlg); lbl.setObjectName("DialogLabel")
        box = QComboBox(dlg); box.setObjectName("DialogInput"); box.addItems(["Page", "Drive"])
        box.setCurrentIndex(0 if self._get_life_basis() == "page" else 1)
        btn = QPushButton("Save", dlg)
        btn.clicked.connect(lambda: (self._set_life_basis("page" if box.currentIndex()==0 else "drive"), self._update_basis_label(), dlg.accept()))
        dlg._content_layout.addWidget(lbl); dlg._content_layout.addWidget(box)
        r = QHBoxLayout(); r.addStretch(1); r.addWidget(btn); dlg._content_layout.addLayout(r)
        dlg.exec()

    def _open_bulk_settings(self):
        cfg = self._get_bulk_config()
        s = QSettings()
        dlg = FramelessDialog(self, "Bulk Settings", self._icon_dir)

        # Build UI rows manually to save vertical space
        def _row(label, widget): r = QHBoxLayout(); r.addWidget(QLabel(label, dlg)); r.addStretch(1); r.addWidget(widget); return r
        
        sp_top = QSpinBox(dlg); sp_top.setObjectName("DialogInput"); sp_top.setRange(1, 9999); sp_top.setValue(cfg.top_n)
        sp_pool = QSpinBox(dlg); sp_pool.setObjectName("DialogInput"); sp_pool.setRange(1, 16); sp_pool.setValue(cfg.pool_size)
        ed_dir = QLineEdit(cfg.out_dir, dlg); ed_dir.setObjectName("DialogInput")
        btn_br = QPushButton("Browse", dlg); btn_br.clicked.connect(lambda: ed_dir.setText(QFileDialog.getExistingDirectory(self, "Out", cfg.out_dir) or cfg.out_dir))
        
        bl_edit = QPlainTextEdit(dlg); bl_edit.setObjectName("MainEditor"); bl_edit.setFixedHeight(80); bl_edit.setPlainText("\n".join(cfg.blacklist or []))
        
        cb_unpack = QCheckBox("Enable unpacking date filter", dlg); cb_unpack.setObjectName("DialogCheckbox")
        cb_unpack.setChecked(bool(s.value("bulk/unpack_filter_enabled", False, bool)))
        sp_extra = QSpinBox(dlg); sp_extra.setObjectName("DialogInput"); sp_extra.setRange(0, 120); sp_extra.setValue(int(s.value("bulk/unpack_extra_months", 0, int)))

        btn_save = QPushButton("Save", dlg)
        def _save():
            bl = [l.strip().upper() for l in re.split(r"[\n,]+", bl_edit.toPlainText()) if l.strip()]
            self._save_bulk_config(BulkConfig(sp_top.value(), ed_dir.text().strip(), sp_pool.value(), bl))
            s.setValue("bulk/unpack_filter_enabled", cb_unpack.isChecked())
            s.setValue("bulk/unpack_extra_months", sp_extra.value())
            dlg.accept()
        btn_save.clicked.connect(_save)

        l = dlg._content_layout
        l.addLayout(_row("Top N serials:", sp_top)); l.addLayout(_row("Parallel workers:", sp_pool))
        r_dir = QHBoxLayout(); r_dir.addWidget(QLabel("Out Dir:", dlg)); r_dir.addWidget(ed_dir, 1); r_dir.addWidget(btn_br); l.addLayout(r_dir)
        l.addWidget(QLabel("Blacklist:", dlg)); l.addWidget(bl_edit)
        r_pk = QHBoxLayout(); r_pk.addWidget(cb_unpack); r_pk.addStretch(1); r_pk.addWidget(QLabel("+Months:", dlg)); r_pk.addWidget(sp_extra); l.addLayout(r_pk)
        r_btn = QHBoxLayout(); r_btn.addStretch(1); r_btn.addWidget(btn_save); l.addLayout(r_btn)
        dlg.exec()

    def _show_about(self):
        from pmgen.catalog.part_kit_catalog import REGISTRY
        models = sorted([k for k, v in REGISTRY.items() if v is not None])
        txt = f"PmGen\nVersion: {VERSION}\nSupported models: {len(models)}\n—\n"
        # Simple columns
        for i in range(0, len(models), 4): txt += "".join(s.ljust(12) for s in models[i:i+4]) + "\n"
        
        dlg = FramelessDialog(self, "About", self._icon_dir)
        t = QPlainTextEdit(dlg); t.setReadOnly(True); t.setObjectName("MainEditor"); t.setPlainText(txt)
        btn = QPushButton("OK", dlg); btn.clicked.connect(dlg.accept)
        dlg._content_layout.addWidget(t); dlg._content_layout.addWidget(btn)
        dlg.exec()

    # =========================================================================
    #  Auth & Event Logic
    # =========================================================================

    def _attempt_auto_login(self):
        if self._auto_login_attempted or self._signed_in: return
        self._auto_login_attempted = True
        s = QSettings()
        if not bool(s.value(self.AUTH_REMEMBER_KEY, False, bool)): return
        
        u = s.value(self.AUTH_USERNAME_KEY, "", str)
        if not u: return
        
        self.user_label.setText("Signing in…"); self.editor.appendPlainText(f"[Auto-Login] Attempting as {u}…")
        try:
            from pmgen.io import http_client as hc
            sess = requests.Session()
            hc.login(sess)
            self._signed_in = True; self._current_user = u; self._update_auth_ui()
            self.editor.appendPlainText(f"[Auto-Login] {u} — success")
        except Exception as e:
            self._signed_in = False; self._current_user = ""; self._update_auth_ui()
            self.editor.appendPlainText(f"[Auto-Login] {u} — failed: {e}")

    def _logout(self):
        QSettings().setValue(self.AUTH_REMEMBER_KEY, False); QSettings().setValue(self.AUTH_USERNAME_KEY, "")
        try:
            from pmgen.io import http_client as hc
            if hasattr(hc, "server_side_logout"): hc.server_side_logout()
            if hasattr(hc, "SessionPool"): hc.SessionPool.close_all_pools()
            hc.clear_credentials()
        except: pass
        self._signed_in = False; self._current_user = ""; self._update_auth_ui(); self.editor.appendPlainText("[Info] - Logout Successful")

    def _update_auth_ui(self):
        self.user_label.setText(self._current_user or "(signed in)" if self._signed_in else "Not signed in")

    def _toggle_fullscreen(self, checked: bool): self.showFullScreen() if checked else self.showNormal()

    def _confirm_exit(self):
        if CustomMessageBox.confirm(self, "Exit", "Are you sure you want to exit?", self._icon_dir) == "ok": self.close()

    def closeEvent(self, ev):
        self._save_id_history()
        super().closeEvent(ev)

    def eventFilter(self, obj, event):
        if not self.isFullScreen() and event.type() in (QEvent.Type.MouseMove, QEvent.Type.HoverMove, QEvent.Type.Leave):
            self._update_cursor(QCursor.pos())
        return super().eventFilter(obj, event)

    def _edge_flags_at_pos(self, pos_global: QPoint):
        pos = self.mapFromGlobal(pos_global); r = self.rect()
        return (pos.x() <= BORDER_WIDTH, pos.x() >= r.width() - BORDER_WIDTH, 
                pos.y() <= BORDER_WIDTH, pos.y() >= r.height() - BORDER_WIDTH)

    def _update_cursor(self, pos_global: QPoint):
        if self.isFullScreen(): self.unsetCursor(); return
        left, right, top, bottom = self._edge_flags_at_pos(pos_global)
        if (left and top) or (right and bottom): self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif (right and top) or (left and bottom): self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif left or right: self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif top or bottom: self.setCursor(Qt.CursorShape.SizeVerCursor)
        else: self.setCursor(Qt.CursorShape.ArrowCursor)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and not self.isFullScreen():
            l, r, t, b = self._edge_flags_at_pos(e.globalPosition().toPoint())
            if any((l, r, t, b)):
                self._rs = ResizeState(True, l, r, t, b, e.globalPosition().toPoint(), self.geometry())
                e.accept(); return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._rs.resizing and not self.isFullScreen():
            delta = e.globalPosition().toPoint() - self._rs.press_pos
            g = QRect(self._rs.press_geom)
            if self._rs.edge_left: g.setLeft(min(g.left() + delta.x(), g.right() - 200))
            elif self._rs.edge_right: g.setRight(max(self._rs.press_geom.right() + delta.x(), g.left() + 200))
            if self._rs.edge_top: g.setTop(min(g.top() + delta.y(), g.bottom() - 150))
            elif self._rs.edge_bottom: g.setBottom(max(self._rs.press_geom.bottom() + delta.y(), g.top() + 150))
            self.setGeometry(g); e.accept(); return
        
        if not self.isFullScreen(): self._update_cursor(e.globalPosition().toPoint())
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self._rs.resizing:
            self._rs = ResizeState(); self._update_cursor(QCursor.pos()); e.accept(); return
        super().mouseReleaseEvent(e)

    def enterEvent(self, e):
        if not self.isFullScreen(): self._update_cursor(QCursor.pos())
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.unsetCursor()
        super().leaveEvent(e)