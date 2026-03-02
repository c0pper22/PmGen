import pytest
from unittest.mock import MagicMock
from PyQt6.QtCore import Qt, QRegularExpression, QCoreApplication, QSettings
from PyQt6.QtWidgets import QWidget, QToolBar, QLabel, QComboBox
from PyQt6.QtGui import QStandardItemModel, QStandardItem

# Import the classes we want to test
from pmgen.ui.main_window import BulkSortFilterProxyModel, MainWindow, BulkRunTab
from pmgen.ui.bulk_model import BulkQueueModel
from pmgen.ui.workers import BulkConfig

# =============================================================================
#  FIXTURES
# =============================================================================

@pytest.fixture(autouse=True)
def isolate_settings():
    """Isolates QSettings so tests do not overwrite actual user data."""
    QCoreApplication.setOrganizationName("PmGen_TestOrg")
    QCoreApplication.setApplicationName("PmGen_TestApp")
    settings = QSettings()
    settings.clear()
    yield
    settings.clear()

@pytest.fixture
def mock_main_window(qtbot, monkeypatch):
    """
    Safely creates a MainWindow by mocking out external dependencies and 
    injecting real dummy QWidgets so the Layouts don't throw TypeErrors.
    """
    class MockUIFactory:
        def __init__(self, *args, **kwargs): pass
        
        def create_secondary_bar(self, parent):
            # Inject labels/widgets that MainWindow expects the factory to create
            parent.user_label = QLabel(parent)
            
            # Use a REAL QComboBox here so MainWindow.closeEvent() doesn't 
            # crash trying to pickle a MagicMock when saving settings!
            parent._id_combo = QComboBox(parent) 
            
            return QWidget(parent)
            
        def create_toolbar(self, parent):
            return QToolBar(parent)

    class MockInventoryTab(QWidget):
        def __init__(self, parent=None, **kwargs):
            super().__init__(parent)
            # Prevent closeEvent from crashing when it tries to read the inventory cache
            self.model = MagicMock()
            self.model.get_dataframe.return_value = None
            
        def _get_cache_path(self):
            return "dummy_path"

    monkeypatch.setattr("pmgen.ui.main_window.UIFactory", MockUIFactory)
    monkeypatch.setattr("pmgen.ui.main_window.InventoryTab", MockInventoryTab)
    monkeypatch.setattr("pmgen.ui.main_window.QTimer.singleShot", MagicMock())
    
    window = MainWindow()
    qtbot.addWidget(window)
    return window

# =============================================================================
#  TESTS: BulkSortFilterProxyModel
# =============================================================================

def test_proxy_model_filtering():
    """Test that the search filter correctly matches Serial, Model, or Customer."""
    source = BulkQueueModel()
    source.add_item(serial="SN123", model="PrinterX", customer="CorpA")
    source.add_item(serial="SN999", model="ScannerY", customer="CorpB")
    
    proxy = BulkSortFilterProxyModel()
    proxy.setSourceModel(source)
    
    # 1. Test filtering by Serial
    proxy.setFilterRegularExpression(QRegularExpression("123"))
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 1)) == "SN123"

    # 2. Test filtering by Customer (Case Insensitive)
    proxy.setFilterRegularExpression(QRegularExpression("corpb"))
    assert proxy.rowCount() == 1
    assert proxy.data(proxy.index(0, 3)) == "CorpB"

class MockBulkModel(QStandardItemModel):
    """A clean item model to bypass BulkQueueModel's complex internal logic for testing."""
    def __init__(self):
        super().__init__(0, 4)
        self.status_col = 1
        self.result_col = 2
        
    def add_test_row(self, serial, status, result, customer):
        row = [
            QStandardItem(serial),
            QStandardItem(status),
            QStandardItem(result),
            QStandardItem(customer)
        ]
        self.appendRow(row)

def test_proxy_model_sorting_status():
    """Test that sorting by Status applies the custom priority order."""
    source = MockBulkModel()
    source.add_test_row("S1", "Queued", "", "")
    source.add_test_row("S2", "Done", "", "")
    source.add_test_row("S3", "Failed", "", "")
    source.add_test_row("S4", "Filtered", "", "")

    proxy = BulkSortFilterProxyModel()
    proxy.setSourceModel(source)
    
    # Sort ascending by the status column
    proxy.sort(source.status_col, Qt.SortOrder.AscendingOrder)
    
    # Expected custom priority: Done (0), Failed (1), Filtered (2), Queued (3)
    assert proxy.data(proxy.index(0, source.status_col)) == "Done"
    assert proxy.data(proxy.index(1, source.status_col)) == "Failed"
    assert proxy.data(proxy.index(2, source.status_col)) == "Filtered"
    assert proxy.data(proxy.index(3, source.status_col)) == "Queued"

def test_proxy_model_sorting_results():
    """Test that sorting by Results handles mixed floats, percentages, and strings."""
    source = MockBulkModel()
    source.add_test_row("S1", "", "—", "")
    source.add_test_row("S2", "", "10.5%", "")
    source.add_test_row("S3", "", "100.0%", "")
    source.add_test_row("S4", "", "5.0%", "")

    proxy = BulkSortFilterProxyModel()
    proxy.setSourceModel(source)
    
    # Sort ascending by result column
    proxy.sort(source.result_col, Qt.SortOrder.AscendingOrder)
    
    # The logic assigns "-2.0" to "—", making it smaller than 5.0. 
    # Therefore, it correctly sorts to the top in ascending order.
    assert proxy.data(proxy.index(0, source.result_col)) == "—"
    assert proxy.data(proxy.index(1, source.result_col)) == "5.0%"
    assert proxy.data(proxy.index(2, source.result_col)) == "10.5%"
    assert proxy.data(proxy.index(3, source.result_col)) == "100.0%"

# =============================================================================
#  TESTS: MainWindow Settings & UI Logic
# =============================================================================

def test_mainwindow_bulk_config_save_load(mock_main_window):
    """Test that MainWindow correctly saves and loads bulk configuration to QSettings."""
    window = mock_main_window
    
    cfg = BulkConfig(
        top_n=50, 
        out_dir="C:/Test", 
        pool_size=8, 
        blacklist=["BAD_SN"], 
        custom_08_name="TestCol", 
        custom_08_code=123
    )
    
    window._save_bulk_config(cfg)
    loaded_cfg = window._get_bulk_config()
    
    assert loaded_cfg.top_n == 50
    assert loaded_cfg.out_dir == "C:/Test"
    assert loaded_cfg.pool_size == 8
    assert "BAD_SN" in loaded_cfg.blacklist
    assert loaded_cfg.custom_08_name == "TestCol"
    assert loaded_cfg.custom_08_code == 123

def test_mainwindow_tab_close_protection(mock_main_window, monkeypatch):
    """Test that the Home and Inventory tabs cannot be closed."""
    window = mock_main_window
    mock_remove = MagicMock()
    monkeypatch.setattr(window.tabs, "removeTab", mock_remove)
    
    # Try closing protected tabs
    window._on_tab_close_requested(0)
    window._on_tab_close_requested(1)
    
    mock_remove.assert_not_called()