from PyQt6.QtCore import Qt, QAbstractTableModel, pyqtSignal, QModelIndex
from PyQt6.QtGui import QColor, QBrush

class BulkQueueModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        # Added "Customer" at index 3
        self.headers = ["#", "Serial", "Model", "Customer", "Unpack Date", "Status", "Result"]
        self._data = []

    def rowCount(self, parent=None):
        return len(self._data)

    def columnCount(self, parent=None):
        return len(self.headers)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        
        row = index.row()
        col = index.column()

        # Internal Data Structure: [Serial, Model, Customer, UnpackDate, Status, Result]
        # Indices:                 0       1      2         3           4       5

        if role == Qt.ItemDataRole.DisplayRole:
            # Column 0 is the row number
            if col == 0:
                return str(row + 1)
            
            # Shift visual columns 1-6 to internal 0-5
            if 0 < col <= 6:
                return self._data[row][col - 1]
        
        # Color Logic (Status is now Visual Column 5 / Internal Index 4)
        if role == Qt.ItemDataRole.ForegroundRole and col == 5:
            status = self._data[row][4]
            if status == "Done": return QBrush(QColor("#40ed68"))       # Green
            if status == "Failed": return QBrush(QColor("#f7768e"))     # Pink/Red
            if status == "Processing": return QBrush(QColor("#7aa2f7")) # Blue
            if status == "Queued": return QBrush(QColor("#bbbbbb"))     # Grey
            if status == "Filtered": return QBrush(QColor("#d83d37"))   # Red/Orange

        return None

    def headerData(self, section, orientation, role):
        if role == Qt.ItemDataRole.DisplayRole and orientation == Qt.Orientation.Horizontal:
            return self.headers[section]
        return None

    def add_item(self, serial, model="Unknown", customer=""):
        self.beginInsertRows(QModelIndex(), len(self._data), len(self._data))
        # Initialize with empty date
        self._data.append([serial, model, customer, "", "Queued", ""])
        self.endInsertRows()

    def update_status(self, serial, status, result, model=None, unpack_date=None, customer=None):
        for i, row in enumerate(self._data):
            if row[0] == serial:
                row[4] = status # Status index 4
                row[5] = result # Result index 5
                
                # Update Model if provided
                if model and model != "Unknown":
                    row[1] = model
                
                # Update Customer if provided
                if customer:
                    row[2] = customer

                # Update Date if provided
                if unpack_date:
                    row[3] = unpack_date

                # Notify view that the whole row changed
                self.dataChanged.emit(self.index(i, 1), self.index(i, 6))
                return
    
    def get_serial_at(self, row):
        if 0 <= row < len(self._data):
            return self._data[row][0]
        return None

    def sort_by_status(self):
        """
        Sorts the data: 
        1. Status (Done > Failed > Filtered > Queued)
        2. If Done: Sort by Percentage (Highest to Lowest)
        """
        self.beginResetModel()
        
        def _get_percentage(result_str):
            try:
                if "%" in result_str:
                    return float(result_str.replace('%', ''))
            except (ValueError, TypeError):
                pass
            return -1.0 

        def _sort_key(row):
            status = row[4]  # Internal index 4 is Status
            result = row[5]  # Internal index 5 is Result
            
            if status == "Done": priority = 0
            elif status == "Failed": priority = 1
            elif status == "Filtered": priority = 2
            else: priority = 3 

            percentage = _get_percentage(result)
            return (priority, -percentage) 

        self._data.sort(key=_sort_key)
        self.endResetModel()

    def clear(self):
        self.beginResetModel()
        self._data = []
        self.endResetModel()