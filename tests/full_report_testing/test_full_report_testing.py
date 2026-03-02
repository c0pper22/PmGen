import os
import json
import pytest
import shutil
from PyQt6.QtCore import QStandardPaths, QCoreApplication

@pytest.fixture(autouse=True)
def setup_test_db(qtbot):
    """
    Isolates QSettings and bootstraps the master database for tests,
    ensuring that the rules engine has access to the actual part catalogs.
    """
    QCoreApplication.setOrganizationName("PmGen_TestOrg")
    QCoreApplication.setApplicationName("PmGen_TestApp")
    
    app_data = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    os.makedirs(app_data, exist_ok=True)
    target_db = os.path.join(app_data, "catalog_manager.db")
    
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    master_db = os.path.join(project_root, "catalog_manager.db")
    
    if os.path.exists(master_db):
        shutil.copy2(master_db, target_db)
    else:
        print(f"\n[WARNING] Master database not found at {master_db}")
    
    yield
    
    if os.path.exists(target_db):
        try:
            os.remove(target_db)
        except OSError:
            pass

from pmgen.parsing.parse_pm_report import parse_pm_report
from pmgen.engine.run_rules import run_rules

TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPORTS_DIR = os.path.join(TEST_DIR, "..", "example_pm_reports")

def get_test_cases():
    """
    Scans the example_pm_reports directory.
    Returns a list of tuples containing (csv_path, json_path) for each valid test case.
    """
    cases = []
    if not os.path.exists(REPORTS_DIR):
        return cases
        
    for filename in os.listdir(REPORTS_DIR):
        if filename.endswith(".csv"):
            csv_path = os.path.join(REPORTS_DIR, filename)
            json_path = os.path.join(REPORTS_DIR, filename.replace(".csv", ".json"))
            
            if os.path.exists(json_path):
                test_id = filename.replace(".csv", "")
                cases.append(pytest.param(csv_path, json_path, id=test_id))
                
    return cases

@pytest.mark.parametrize("csv_path, json_path", get_test_cases())
def test_full_pm_report_generation(csv_path, json_path):
    """
    Reads a PM report CSV, processes it through the rule engine, 
    and verifies the final parts list against the expected JSON.
    """
    with open(json_path, "r", encoding="utf-8-sig") as f:
        test_data = json.load(f)
        
    config = test_data.get("config", {})
    expected_parts = test_data.get("expected_parts", {})

    with open(csv_path, "rb") as f:
        csv_bytes = f.read()

    report = parse_pm_report(csv_bytes)

    selection = run_rules(
        report=report,
        threshold=config.get("threshold", 0.8),
        life_basis=config.get("life_basis", "page"),
        threshold_enabled=config.get("threshold_enabled", True)
    )

    meta = getattr(selection, "meta", {})
    actual_parts = meta.get("selection_pn") or {}

    alerts = meta.get("alerts", [])
    
    due_items = []
    if hasattr(selection, "items") and selection.items:
        due_items = [getattr(item, "canon", "Unknown") for item in selection.items]

    debug_msg = (
        f"\n\n--- TEST FAILED FOR {os.path.basename(csv_path)} ---\n"
        f"Model Parsed: {report.headers.get('model')}\n"
        f"Items Evaluated as DUE: {due_items}\n"
        f"Engine Alerts/Errors: {alerts}\n"
        f"Expected Parts: {expected_parts}\n"
        f"Actual Parts: {actual_parts}\n"
    )

    assert actual_parts == expected_parts, debug_msg