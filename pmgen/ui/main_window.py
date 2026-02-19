from __future__ import annotations
import sys, os, re
import shutil
import requests
import logging
from typing import Dict
from collections import deque
from datetime import datetime
from PyQt6.QtCore import (
    Qt, QSize, QPoint, QRect, QEvent, QRegularExpression,
    QCoreApplication, QSettings, QThread, pyqtSlot, QTimer, pyqtSignal,
    QSortFilterProxyModel, QModelIndex
)
from PyQt6.QtGui import (
    QAction, QIcon, QCursor, QRegularExpressionValidator, QKeySequence, 
    QShortcut, QTextCursor 
)
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPlainTextEdit,
    QToolBar, QSizePolicy, QToolButton, QHBoxLayout, QLabel, QMenu,
    QPushButton, QLineEdit, QComboBox, QCheckBox, QSlider, 
    QSpinBox, QDoubleSpinBox, QFileDialog, QProgressBar, QCompleter,
    QTabWidget, QTableView, QHeaderView, QSplitter, QTabBar
)

# Imports from our new split files
from pmgen.ui.bulk_model import BulkQueueModel
from pmgen.system.wrappers import safe_slot
from .theme import apply_static_theme
from .components import (
    DragRegion, TitleDragLabel, FramelessDialog, CustomMessageBox, ResizeState
)
from .highlighter import OutputHighlighter
from .workers import BulkConfig, BulkRunner
from pmgen.io.http_client import get_customer_map_after_login
from pmgen.updater.updater import UpdateWorker, perform_restart, CURRENT_VERSION
from .inventory import InventoryTab
from .factory import UIFactory


SERVICE_NAME = "PmGen"

# Constants
BORDER_WIDTH = 8
BULK_TOPN_KEY = "bulk/top_n"
BULK_DIR_KEY  = "bulk/out_dir"
BULK_POOL_KEY = "bulk/pool_size"
BULK_BLACKLIST_KEY = "bulk/blacklist"

# =============================================================================
#  NEW CLASS: BulkSortFilterProxyModel
#  Handles filtering (Search) and custom sorting for the Bulk Table
# =============================================================================
class BulkSortFilterProxyModel(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

    def filterAcceptsRow(self, source_row, source_parent):
        """
        Filters rows based on the search text. 
        Checks Serial (Col 1), Model (Col 2), and Customer (Col 3).
        """
        pattern = self.filterRegularExpression().pattern()
        if not pattern:
            return True
            
        model = self.sourceModel()
        
        # Helper to get string data from a specific column in the source model
        def get_col_str(col_idx):
            idx = model.index(source_row, col_idx, source_parent)
            return str(model.data(idx) or "").lower()

        # Check against Serial, Model, and Customer columns
        # Visual Mapping: 1=Serial, 2=Model, 3=Customer
        serial = get_col_str(1)
        model_name = get_col_str(2)
        customer = get_col_str(3)
        
        p = pattern.lower()
        return (p in serial) or (p in model_name) or (p in customer)

    def lessThan(self, left: QModelIndex, right: QModelIndex):
        """
        Replicates the custom sorting logic from BulkQueueModel 
        so header clicks work correctly on the Proxy.
        """
        left_data = self.sourceModel().data(left)
        right_data = self.sourceModel().data(right)
        
        col = left.column()
        
        # --- Sorting Logic for Status (Visual Column 5) ---
        if col == 5:
            def status_priority(val):
                # Done > Failed > Filtered > Queued > Processing
                if val == "Done": return 0
                if val == "Failed": return 1
                if val == "Filtered": return 2
                if val == "Queued": return 3
                return 4
            return status_priority(left_data) < status_priority(right_data)
            
        if col == 6:
            def get_val(val):
                s_val = str(val)
                if "%" in s_val:
                    try: return float(s_val.replace('%', ''))
                    except: return -1.0
                return s_val.lower() # Fallback
            
            l_v = get_val(left_data)
            r_v = get_val(right_data)
            
            if isinstance(l_v, float) and isinstance(r_v, float):
                return l_v < r_v
            return str(l_v) < str(r_v)

        # --- Default String Sort ---
        return str(left_data).lower() < str(right_data).lower()

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if role == Qt.ItemDataRole.DisplayRole and index.column() == 0:
            return str(index.row() + 1)
        
        return super().data(index, role)

# =============================================================================
#  CLASS: BulkRunTab
#  Encapsulates a single bulk run (UI + Logic + Thread)
# =============================================================================
class BulkRunTab(QWidget):
    """
    A self-contained tab for a single bulk processing job.
    Owms its own model, view, and worker thread.
    """
    inspect_requested = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, config: BulkConfig, runner_kwargs: dict, parent=None):
        super().__init__(parent)
        self.config = config
        self.runner_kwargs = runner_kwargs

        self.customer_map = runner_kwargs.get("customer_map", {})
        
        self._thread: QThread | None = None
        self._runner: BulkRunner | None = None
        self._is_running = False

        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        # --- Top Bar: Status, Progress, Search, Stop ---
        top_bar = QHBoxLayout()
        
        self.status_label = QLabel("Ready")
        self.status_label.setStyleSheet("font-weight: bold; color: #bbbbbb;")
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setObjectName("ProgressBar")
        self.progress_bar.setFixedHeight(12)
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)

        # Search Bar
        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("BulkSearch")
        self.search_bar.setPlaceholderText("Search serial, model...")
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.setFixedWidth(200)
        self.search_bar.textChanged.connect(self._on_search_changed)

        # Stop Button
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setObjectName("BulkStopBtn")
        self.btn_stop.setFixedHeight(24)
        self.btn_stop.clicked.connect(self.stop)
        self.btn_stop.setEnabled(False) # Enabled when running

        top_bar.addWidget(self.status_label)
        top_bar.addWidget(self.progress_bar, 1)
        top_bar.addWidget(self.search_bar) # Add Search Here
        top_bar.addWidget(self.btn_stop)

        layout.addLayout(top_bar)

        # --- Splitter: Table & Logs ---
        splitter = QSplitter(Qt.Orientation.Vertical)
        
        # 1. The Table & Models
        self.view = QTableView()
        
        # Create base model
        self.model = BulkQueueModel()
        
        # Create Proxy Model for Sorting/Filtering
        self.proxy_model = BulkSortFilterProxyModel(self)
        self.proxy_model.setSourceModel(self.model)
        
        # Assign Proxy to View
        self.view.setModel(self.proxy_model)
        
        self.view.setSortingEnabled(True)
        self.view.setColumnWidth(2, 160)
        self.view.setColumnWidth(3, 300)
        header = self.view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setStretchLastSection(True)
        self.view.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.view.customContextMenuRequested.connect(self._on_context_menu)
        
        splitter.addWidget(self.view)

        # 2. Local Log Window (so user sees errors for *this* run)
        self.log_editor = QPlainTextEdit()
        self.log_editor.setObjectName("MainEditor")
        self.log_editor.setReadOnly(True)
        self.log_editor.setMaximumBlockCount(1000)
        self.log_editor.setPlaceholderText("Run logs will appear here...")
        splitter.addWidget(self.log_editor)
        
        # Set initial sizes (Table gets most space)
        splitter.setSizes([400, 50])
        
        layout.addWidget(splitter, 1)

    def start(self):
        if self._is_running: return
        
        self.model.clear()
        self.log_editor.clear()
        self.btn_stop.setEnabled(True)
        self.status_label.setText("Initializing...")
        
        # Create Thread & Runner
        self._thread = QThread()
        self._runner = BulkRunner(self.config, **self.runner_kwargs)
        self._runner.moveToThread(self._thread)

        # Connect Signals
        self._thread.started.connect(self._runner.run)
        
        self._runner.progress.connect(self._on_progress_text)
        self._runner.progress_value.connect(self._on_progress_value)
        self._runner.item_updated.connect(self._on_item_updated)
        self._runner.finished.connect(self._on_finished)
        
        # Cleanup signals
        self._runner.finished.connect(self._thread.quit)
        self._runner.finished.connect(self._runner.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._on_thread_gone)

        self._thread.start()
        self._is_running = True

    def stop(self):
        if self._is_running and self._thread:
            self._log("[Info] Stop requested... (this may take a moment to finish current tasks)")
            self._thread.requestInterruption()
            self.btn_stop.setEnabled(False)

    def _on_search_changed(self, text):
        """Updates the proxy filter regex when search bar text changes."""
        # Use regex to escape special characters if you want exact matching, 
        # or simple string if you want wildcards. 
        # Here we just pass the text; QRegularExpression handles it cleanly.
        regex = QRegularExpression(re.escape(text), QRegularExpression.PatternOption.CaseInsensitiveOption)
        self.proxy_model.setFilterRegularExpression(regex)

    @safe_slot
    def _on_context_menu(self, pos):
        # Get index from View (This is a Proxy Index)
        proxy_index = self.view.indexAt(pos)
        if not proxy_index.isValid(): return
        
        # Map to Source Index to get the correct row for internal data
        source_index = self.proxy_model.mapToSource(proxy_index)
        
        # Use source index row to get data from the underlying model
        serial = self.model.get_serial_at(source_index.row())
        
        menu = QMenu(self.view)
        act_inspect = QAction("Inspect / Generate Single Report", self.view)
        act_inspect.triggered.connect(lambda: self.inspect_requested.emit(serial))
        menu.addAction(act_inspect)

        menu.exec(self.view.viewport().mapToGlobal(pos))

    def _open_folder(self):
        if self.config.out_dir and os.path.exists(self.config.out_dir):
            os.startfile(self.config.out_dir)

    # --- Worker Slots ---

    @pyqtSlot(str)
    def _on_progress_text(self, text):
        self._log(text)
        if text.startswith("[Bulk]"):
            clean = text.replace("[Bulk]", "").strip()
            self.status_label.setText(clean)
        elif text.startswith("[Info]"):
            clean = text.replace("[Info]", "").strip()
            self.status_label.setText(clean)

    @pyqtSlot(int, int)
    def _on_progress_value(self, current, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(current)

    @pyqtSlot(str, str, str, str, str)
    def _on_item_updated(self, serial, status, result, model, unpack_date):
        c_name = self.customer_map.get(serial, "")
        found = False
        for r in range(self.model.rowCount()):
            if self.model.get_serial_at(r) == serial:
                self.model.update_status(serial, status, result, model, unpack_date, customer=c_name)
                found = True
                break
        
        if not found:
            self.model.add_item(serial, model, customer=c_name)
            self.model.update_status(serial, status, result, model, unpack_date, customer=c_name)

    @pyqtSlot(str)
    def _on_finished(self, msg):
        self._log(msg)
        self.status_label.setText("Done")
        self.progress_bar.setValue(self.progress_bar.maximum())
        
        # We sort the proxy model now, not the source, to update the view
        # Sort by Status (Col 5), Ascending
        self.view.sortByColumn(5, Qt.SortOrder.AscendingOrder)
        
        self.btn_stop.setEnabled(False)
        self.finished.emit()

    def _on_thread_gone(self):
        self._thread = None
        self._runner = None
        self._is_running = False

    def _log(self, text):
        self.log_editor.appendPlainText(text)
        self.log_editor.moveCursor(QTextCursor.MoveOperation.End)


# =============================================================================
#  MAIN WINDOW
# =============================================================================

class MainWindow(QMainWindow):
    # ---- PM settings Keys ----
    THRESH_KEY = "pm/due_threshold"
    THRESH_ENABLED_KEY = "pm/due_threshold_enabled"
    LIFE_BASIS_KEY = "pm/life_basis"
    COLORIZED_KEY = "ui/colorized_output"
    SHOW_ALL_KEY = "ui/show_all_items"
    ALERTS_ENABLED_KEY = "ui/alerts_enabled"

    BULK_UNPACK_KEY_ENABLE = "bulk/unpack_filter_enabled"
    BULK_UNPACK_KEY_EXTRA  = "bulk/unpack_extra_months"

    # ---- Auth prefs Keys ----
    AUTH_REMEMBER_KEY = "auth/remember"
    AUTH_USERNAME_KEY = "auth/username"
    HISTORY_KEY = "recent_serials"
    MAX_HISTORY = 25

    sig_start_download = pyqtSignal(str)
    sig_start_extract = pyqtSignal(str)

    customerMap: Dict[str, str] = {}

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PmGen")
        self.resize(1100, 720)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)

        if getattr(sys, 'frozen', False):
                import glob
                current_dir = os.path.dirname(sys.executable)
                # Look for any file containing ".old."
                for p in glob.glob(os.path.join(current_dir, "*.old*")):
                    try:
                        if os.path.isdir(p):
                            shutil.rmtree(p)
                        else:
                            os.remove(p)
                    except OSError:
                        pass
        
        # Paths
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            base_dir = sys._MEIPASS
        else:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        self._icon_dir = os.path.join(base_dir, "pmgen", "assets", "icons")

        # Auth UI state
        self._signed_in: bool = False
        self._current_user: str = ""
        self._auto_login_attempted: bool = False
        self._session = None

        # Global tracking + event filter
        app = QApplication.instance()
        app.installEventFilter(self)
        self.setMouseTracking(True)

        # --- UI SETUP START ---
        central = QWidget()
        self.setCentralWidget(central)
        central.setMouseTracking(True)
        
        # Main layout for the window
        self._vbox = QVBoxLayout(central)
        self._vbox.setContentsMargins(6, 6, 6, 6)
        self._vbox.setSpacing(0)

        # Initialize the Tab Widget
        self.tabs = QTabWidget()
        self.tabs.setObjectName("MainTabs")
        self.tabs.setDocumentMode(True)
        self.tabs.setTabsClosable(True) # ENABLE TAB CLOSING
        self.tabs.tabCloseRequested.connect(self._on_tab_close_requested)
        self._vbox.addWidget(self.tabs)

        # -- TAB 1: Home (Cleaned up: Just Editor and Bar) --
        self.tab_home = QWidget()
        self.tab_home.setObjectName("TabHome")
        home_layout = QVBoxLayout(self.tab_home)
        home_layout.setContentsMargins(0, 8, 0, 0)
        home_layout.setSpacing(6)

        # --- REFACTOR: Use UIFactory ---
        ui_factory = UIFactory(self._icon_dir)
        self._secondary_bar = ui_factory.create_secondary_bar(self)
        home_layout.addWidget(self._secondary_bar, 0)

        self.editor = QPlainTextEdit()
        self.editor.setReadOnly(True)
        self.editor.setMaximumBlockCount(2000)
        self._apply_colorized_highlighter()
        self.editor.setObjectName("MainEditor")
        self.editor.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        
        home_layout.addWidget(self.editor, 1)

        self.tabs.addTab(self.tab_home, "Single")
        self.tabs.tabBar().setTabButton(0, QTabBar.ButtonPosition.RightSide, None)

        self.tab_tools = InventoryTab(self, icon_dir=self._icon_dir)
        self.tab_tools.setObjectName("TabInventory")
        self.tabs.addTab(self.tab_tools, "Inventory")

        self.tabs.tabBar().setTabButton(1, QTabBar.ButtonPosition.RightSide, None)

        # --- REFACTOR: Use UIFactory ---
        self.toolbar = ui_factory.create_toolbar(self)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, self.toolbar)

        # UPDATER STATE
        self._update_thread: QThread | None = None
        self._update_worker: UpdateWorker | None = None
        self._update_silent_mode = False

        # Shortcuts
        clear_shortcut = QShortcut(QKeySequence("Ctrl+L"), self)
        clear_shortcut.activated.connect(self._clear_output_window)
        generate_shortcut = QShortcut(QKeySequence("Return"), self)
        generate_shortcut.activated.connect(self._on_generate_clicked)

        self._update_auth_ui()
        QTimer.singleShot(0, self._attempt_auto_login)

        # --- AUTO CHECK ON STARTUP ---
        QTimer.singleShot(1500, lambda: self._start_update_check(silent=True))

        self._rs = ResizeState()

    # =========================================================================
    #  Tab Management
    # =========================================================================
    
    def _on_tab_close_requested(self, index):
        # Don't allow closing Home (0) or Inventory (1)
        # Adjust indices if you rearrange tabs.
        widget = self.tabs.widget(index)
        
        if widget == self.tab_home or widget == self.tab_tools:
            return # Ignore
            
        if isinstance(widget, BulkRunTab):
            # Check if running
            if widget._is_running:
                res = CustomMessageBox.confirm(
                    self, "Job Running", 
                    "This bulk job is still running.\nAre you sure you want to stop and close it?", 
                    self._icon_dir
                )
                if res != "ok": return
                widget.stop()
            
            self.tabs.removeTab(index)
            widget.deleteLater()

    # =========================================================================
    #  Settings Management
    # =========================================================================
    
    def _get_alerts_enabled(self) -> bool:
        return bool(QSettings().value(self.ALERTS_ENABLED_KEY, True, bool))

    def _set_alerts_enabled(self, on: bool):
        QSettings().setValue(self.ALERTS_ENABLED_KEY, bool(on))

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

    def _reset_update_thread(self):
            """
            Clears the python reference to the thread so we don't 
            accidentally access a deleted C++ object later.
            """
            self._update_thread = None
            self._update_worker = None

    def _start_update_check(self, silent=False):
        """
        silent=True: Used on startup (only notify if update FOUND).
        silent=False: Used on button click (notify if up-to-date or error).
        """
        # SAFE CHECK: Ensure we don't access a deleted thread
        if self._update_thread is not None:
            if self._update_thread.isRunning():
                if not silent:
                    self.editor.appendPlainText("[Update] Check already in progress...")
                return

        self._update_silent_mode = silent
        if not silent:
            self.editor.appendPlainText("[Info] Checking for updates...")
        
        self._update_thread = QThread()
        self._update_worker = UpdateWorker()
        self._update_worker.moveToThread(self._update_thread)
        
        self._update_thread.started.connect(self._update_worker.check_updates)
        self._update_worker.check_finished.connect(self._on_check_finished)
        self._update_worker.error_occurred.connect(self._on_update_error)
        self._update_worker.download_progress.connect(self._on_download_progress)
        self._update_worker.download_finished.connect(self._on_download_complete)
        
        self._update_worker.check_finished.connect(self._update_thread.quit)
        self._update_worker.error_occurred.connect(self._update_thread.quit)
        
        self._update_thread.finished.connect(self._update_thread.deleteLater)
        self._update_thread.finished.connect(self._update_thread.deleteLater)
        self._update_thread.finished.connect(self._reset_update_thread)
        
        self._update_thread.start()

    @pyqtSlot(bool, str, str)
    def _on_check_finished(self, found, version_tag, url):
        self._update_thread.quit() # Stop the check thread
        
        if found:
            res = CustomMessageBox.confirm(
                self, 
                "Update Available", 
                f"New version {version_tag} is available.\nDo you want to update now?", 
                self._icon_dir
            )
            if res == "ok":
                self._start_download(url)
        else:
            if not self._update_silent_mode:
                CustomMessageBox.info(self, "Up to Date", f"You are on the latest version ({CURRENT_VERSION}).", self._icon_dir)

    @pyqtSlot(str)
    def _on_update_error(self, msg):
        self._update_thread.quit()
        if not self._update_silent_mode:
            self.editor.appendPlainText(f"[Update Error] {msg}")
            CustomMessageBox.warn(self, "Update Error", msg, self._icon_dir)

    def _start_download(self, url):
        self.editor.appendPlainText("[Update] Starting download...")
        
        self._dl_thread = QThread()
        self._dl_worker = UpdateWorker()
        self._dl_worker.moveToThread(self._dl_thread)
        
        self.sig_start_download.connect(self._dl_worker.download_update)
        self.sig_start_extract.connect(self._dl_worker.extract_update)
        
        self._dl_worker.download_progress.connect(self._on_download_progress)
        self._dl_worker.extraction_progress.connect(self._on_download_progress)
        
        self._dl_worker.download_finished.connect(self._on_download_complete)
        self._dl_worker.extraction_finished.connect(self._on_extraction_complete)
        self._dl_worker.error_occurred.connect(self._on_update_error)
        
        self._dl_worker.extraction_finished.connect(self._dl_thread.quit)
        self._dl_worker.error_occurred.connect(self._dl_thread.quit)
        self._dl_thread.finished.connect(self._dl_thread.deleteLater)
        
        self._dl_thread.start()

        self._dl_dialog = FramelessDialog(self, "Updating PmGen", self._icon_dir)
        self._dl_bar = QProgressBar(self._dl_dialog)
        self._dl_bar.setObjectName("ProgressBar")
        self._dl_bar.setRange(0, 100)
        self._dl_bar.setValue(0)
        
        self._dl_label = QLabel("Downloading Update...", self._dl_dialog)
        self._dl_label.setObjectName("DialogLabel")

        self._dl_dialog._content_layout.addWidget(self._dl_label)
        self._dl_dialog._content_layout.addWidget(self._dl_bar)
        self._dl_dialog.show()

        self.sig_start_download.emit(url)

    @pyqtSlot(int)
    def _on_download_progress(self, pct):
        """Shared slot for both download and extraction progress."""
        if hasattr(self, "_dl_bar"):
            self._dl_bar.setValue(pct)

    @pyqtSlot(str)
    def _on_download_complete(self, zip_path):
        """Switch UI to Extraction mode and start extraction via signal."""
        if hasattr(self, "_dl_label"):
            self._dl_label.setText("Extracting Files...")
        if hasattr(self, "_dl_bar"):
            self._dl_bar.setValue(0)
            
        self.sig_start_extract.emit(zip_path)

    @pyqtSlot(str, str)
    def _on_extraction_complete(self, zip_path, extract_dir):
        if hasattr(self, "_dl_dialog"):
            self._dl_dialog.close()
        
        perform_restart(zip_path, extract_dir)

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
    
    @safe_slot
    def _on_generate_clicked(self, *args):
        self.tabs.setCurrentIndex(0)

        le = self._id_combo.lineEdit()
        text = le.text().strip().upper()

        cust_name = self.customerMap.get(text, "")

        logging.info(f"User requested generation for serial: {text}")

        if not text:
            CustomMessageBox.warn(self, "Missing Serial", "Please Enter A Serial Number", self._icon_dir)
            return

        items = [text] + [self._id_combo.itemText(i) for i in range(self._id_combo.count()) if self._id_combo.itemText(i).upper() != text]
        self._set_history(items[:self.MAX_HISTORY])
        self._save_id_history()

        try: from pmgen.engine.single_report import generate_from_bytes
        except ImportError: from pmgen.engine import generate_from_bytes

        data = None
        unpack_date = None

        try:
            from pmgen.io.http_client import get_service_file_bytes, get_unpacking_date, _parse_code_from_08_bytes
            
            # Fetch PM bytes
            data = get_service_file_bytes(text, "PMSupport", sess=self._session)
            
            # NEW: Fetch unpacking date (optional)
            try:
                unpack_date = get_unpacking_date(text, sess=self._session)
            except Exception as e:
                logging.warning(f"Could not fetch unpacking date for {text}: {e}")

            print("DEBUG: Download finished! Size:", len(data) if data else 0, flush=True)
        except Exception:
            try:
                if hasattr(self, "act_login"): self.act_login.trigger()
                from pmgen.io.http_client import get_service_file_bytes as _refetch
                # Retry fetching report
                data = _refetch(text, "PMSupport")
                # We skip retrying unpack_date here to keep fallback simple/fast
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
                unpacking_date=unpack_date,
                alerts_enabled=self._get_alerts_enabled(),
                customer_name=cust_name
            )
            self.editor.setPlainText(out)
            self._apply_colorized_highlighter()
            logging.info("Report generation successful.")
        except Exception as e:
            logging.error(f"Generation failed: {e}")
            CustomMessageBox.warn(self, "Generate failed", str(e), self._icon_dir)

    @safe_slot
    def _start_bulk(self, *args):
        # 1. Prepare Config & Args
        cfg = self._get_bulk_config()
        cfg.show_all = self._get_show_all()
        
        s = QSettings()
        unpack_max_enabled = bool(s.value("bulk/unpack_filter_enabled", False, bool))
        unpack_max_months = int(s.value("bulk/unpack_extra_months", 0, int))
        unpack_min_enabled = bool(s.value("bulk/unpack_min_filter_enabled", False, bool))
        unpack_min_months = int(s.value("bulk/unpack_min_months", 0, int))

        runner_kwargs = {
            "threshold": self._get_threshold(),
            "life_basis": self._get_life_basis(),
            "threshold_enabled": self._get_threshold_enabled(),
            "unpack_max_enabled": unpack_max_enabled,
            "unpack_max_months": unpack_max_months,
            "unpack_min_enabled": unpack_min_enabled,
            "unpack_min_months": unpack_min_months,
            "customer_map": self.customerMap,
        }

        # 2. Create the Tab
        tab = BulkRunTab(cfg, runner_kwargs)
        
        # 3. Connect Tab Signals to MainWindow Actions
        # When tab requests inspection, fill serial in Home and generate
        tab.inspect_requested.connect(self._on_bulk_inspect_requested)
        
        # 4. Add to TabWidget and Select it
        title = f"Bulk {datetime.now().strftime('%H:%M')}"
        idx = self.tabs.addTab(tab, title)
        self.tabs.setCurrentIndex(idx)
        
        # 5. Start the Job
        tab.start()
        
    @pyqtSlot(str)
    def _on_bulk_inspect_requested(self, serial):
        """Called when a Bulk Tab 'Inspect' context menu is clicked."""
        self.tabs.setCurrentIndex(0) # Go to Home
        self._id_combo.setEditText(serial)
        self._on_generate_clicked()

    def _clear_output_window(self): self.editor.clear()

    # =========================================================================
    #  Dialogs
    # =========================================================================
    @safe_slot
    def _open_due_threshold_dialog(self, *args):
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
    
    @safe_slot
    def _open_login_dialog(self, *args):
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

            logging.info(f"Attempting manual login for user: {u}")

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
                self.customerMap = get_customer_map_after_login(sess)
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

    @safe_slot
    def _open_life_basis_dialog(self, *args):
        dlg = FramelessDialog(self, "Life Basis", self._icon_dir)
        lbl = QLabel("Choose counter basis (fallback to other if missing).", dlg); lbl.setObjectName("DialogLabel")
        box = QComboBox(dlg); box.setObjectName("DialogInput"); box.addItems(["Page", "Drive"])
        box.setCurrentIndex(0 if self._get_life_basis() == "page" else 1)
        btn = QPushButton("Save", dlg)
        btn.clicked.connect(lambda: (self._set_life_basis("page" if box.currentIndex()==0 else "drive"), self._update_basis_label(), dlg.accept()))
        dlg._content_layout.addWidget(lbl); dlg._content_layout.addWidget(box)
        r = QHBoxLayout(); r.addStretch(1); r.addWidget(btn); dlg._content_layout.addLayout(r)
        dlg.exec()

    @safe_slot
    def _open_bulk_settings(self, *args):
        cfg = self._get_bulk_config()
        s = QSettings()
        dlg = FramelessDialog(self, "Bulk Settings", self._icon_dir)

        # Build UI rows manually to save vertical space
        def _row(label, widget): 
            r = QHBoxLayout()
            r.addWidget(QLabel(label, dlg))
            r.addStretch(1)
            r.addWidget(widget)
            return r
        
        # --- Standard Config ---
        sp_top = QSpinBox(dlg); sp_top.setObjectName("DialogInput"); sp_top.setRange(1, 9999); sp_top.setValue(cfg.top_n)
        sp_pool = QSpinBox(dlg); sp_pool.setObjectName("DialogInput"); sp_pool.setRange(1, 16); sp_pool.setValue(cfg.pool_size)
        ed_dir = QLineEdit(cfg.out_dir, dlg); ed_dir.setObjectName("DialogInput")
        btn_br = QPushButton("Browse", dlg); btn_br.clicked.connect(lambda: ed_dir.setText(QFileDialog.getExistingDirectory(self, "Out", cfg.out_dir) or cfg.out_dir))
        
        bl_edit = QPlainTextEdit(dlg); bl_edit.setObjectName("MainEditor"); bl_edit.setFixedHeight(60)
        bl_edit.setPlainText("\n".join(cfg.blacklist or []))
        
        # --- Date Filters (Max Age / Min Age) ---
        
        # 1. Max Age (Existing: "Unpack Filter")
        cb_max_age = QCheckBox("Exclude if OLDER than (Months):", dlg); cb_max_age.setObjectName("DialogCheckbox")
        cb_max_age.setChecked(bool(s.value("bulk/unpack_filter_enabled", False, bool)))
        sp_max_age = QSpinBox(dlg); sp_max_age.setObjectName("DialogInput"); sp_max_age.setRange(0, 120)
        sp_max_age.setValue(int(s.value("bulk/unpack_extra_months", 0, int))) # Reusing existing key
        
        # 2. Min Age (New)
        cb_min_age = QCheckBox("Exclude if NEWER than (Months):", dlg); cb_min_age.setObjectName("DialogCheckbox")
        cb_min_age.setChecked(bool(s.value("bulk/unpack_min_filter_enabled", False, bool)))
        sp_min_age = QSpinBox(dlg); sp_min_age.setObjectName("DialogInput"); sp_min_age.setRange(0, 120)
        sp_min_age.setValue(int(s.value("bulk/unpack_min_months", 0, int)))

        btn_save = QPushButton("Save", dlg)
        def _save():
            bl = [l.strip().upper() for l in re.split(r"[\n,]+", bl_edit.toPlainText()) if l.strip()]
            self._save_bulk_config(BulkConfig(sp_top.value(), ed_dir.text().strip(), sp_pool.value(), bl))
            
            # Save Max Age (Existing keys)
            s.setValue("bulk/unpack_filter_enabled", cb_max_age.isChecked())
            s.setValue("bulk/unpack_extra_months", sp_max_age.value())
            
            # Save Min Age (New keys)
            s.setValue("bulk/unpack_min_filter_enabled", cb_min_age.isChecked())
            s.setValue("bulk/unpack_min_months", sp_min_age.value())
            
            dlg.accept()
        btn_save.clicked.connect(_save)

        l = dlg._content_layout
        l.addLayout(_row("Top N serials:", sp_top))
        l.addLayout(_row("Parallel workers:", sp_pool))
        
        r_dir = QHBoxLayout(); r_dir.addWidget(QLabel("Out Dir:", dlg)); r_dir.addWidget(ed_dir, 1); r_dir.addWidget(btn_br); l.addLayout(r_dir)
        
        l.addWidget(QLabel("Blacklist:", dlg)); l.addWidget(bl_edit)
        
        # Add the two filter rows
        r_min = QHBoxLayout(); r_min.addWidget(cb_min_age); r_min.addStretch(1); r_min.addWidget(sp_min_age); l.addLayout(r_min)
        r_max = QHBoxLayout(); r_max.addWidget(cb_max_age); r_max.addStretch(1); r_max.addWidget(sp_max_age); l.addLayout(r_max)
        
        r_btn = QHBoxLayout(); r_btn.addStretch(1); r_btn.addWidget(btn_save); l.addLayout(r_btn)
        dlg.exec()

    def _show_about(self):
        from pmgen.catalog.part_kit_catalog import REGISTRY
        models = sorted([k for k, v in REGISTRY.items() if v is not None])
        txt = f"PmGen\nVersion: {CURRENT_VERSION}\nSupported models: {len(models)}\n—\n"
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
            self._session = sess
            self._signed_in = True; self._current_user = u; self._update_auth_ui()
            self.editor.appendPlainText(f"[Auto-Login] {u} — success")
            self.customerMap = get_customer_map_after_login(sess)
            print(self.customerMap)
        except Exception as e:
            self._signed_in = False; self._current_user = ""; self._update_auth_ui()
            self.editor.appendPlainText(f"[Auto-Login] {u} — failed: {e}")

    @safe_slot
    def _logout(self, *args):
        logging.info("User requested logout.")
        QSettings().setValue(self.AUTH_REMEMBER_KEY, False); QSettings().setValue(self.AUTH_USERNAME_KEY, "")
        try:
            from pmgen.io import http_client as hc
            if hasattr(hc, "server_side_logout"): hc.server_side_logout()
            if hasattr(hc, "SessionPool"): hc.SessionPool.close_all_pools()
            hc.clear_credentials()
        except: pass
        self._signed_in = False; self._current_user = ""; self._session = None; self._update_auth_ui(); self.editor.appendPlainText("[Info] - Logout Successful")

    def _update_auth_ui(self):
        self.user_label.setText(self._current_user or "(signed in)" if self._signed_in else "Not signed in")

    def _toggle_fullscreen(self, checked: bool): self.showFullScreen() if checked else self.showNormal()

    def _confirm_exit(self):
        if CustomMessageBox.confirm(self, "Exit", "Are you sure you want to exit?", self._icon_dir) == "ok": self.close()

    def closeEvent(self, ev):
        self._save_id_history()
        
        df = self.tab_tools.model.get_dataframe()
        
        if df is not None and not df.empty:
            dlg = CustomMessageBox(
                self, 
                "Active Inventory", 
                "You have items in your inventory.\nWould you like to keep them for your next session or delete them?", 
                self._icon_dir, 
                [("Cancel", "cancel"), ("Delete", "delete"), ("Keep", "keep")]
            )
            dlg.exec()
            
            choice = dlg._clicked_role or "cancel"
            
            if choice == "cancel":
                ev.ignore()
                return
            elif choice == "delete":
                cache_path = self.tab_tools._get_cache_path()
                if os.path.exists(cache_path):
                    try:
                        os.remove(cache_path)
                        logging.info("Inventory cache deleted on exit.")
                    except OSError as e:
                        logging.error(f"Failed to delete inventory cache: {e}")
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