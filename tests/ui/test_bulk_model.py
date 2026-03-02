import pytest
from PyQt6.QtCore import Qt
from pmgen.ui.bulk_model import BulkQueueModel

def test_add_item(qtbot):
    """Test that adding an item correctly populates the internal data structure."""
    model = BulkQueueModel()
    
    model.add_item(serial="SN123", model="PrinterX", customer="CorpA")
    
    assert model.rowCount() == 1
    
    assert model._data[0][0] == "SN123"
    assert model._data[0][1] == "PrinterX"
    assert model._data[0][5] == "Queued"

def test_update_status(qtbot):
    """Test that updating an item modifies the correct indices."""
    model = BulkQueueModel()
    model.add_item(serial="SN123")
    
    model.update_status(
        serial="SN123", 
        status="Done", 
        result="95.0%", 
        model="PrinterY",
        customer="CorpB"
    )
    
    assert model._data[0][5] == "Done"
    assert model._data[0][6] == "95.0%"
    assert model._data[0][1] == "PrinterY" 
    assert model._data[0][2] == "CorpB"