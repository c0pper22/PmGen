from PyQt6.QtCore import Qt, QAbstractTableModel, QModelIndex
from PyQt6.QtGui import QColor, QBrush

class BulkQueueModel(QAbstractTableModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.headers = ["#", "Serial", "Model", "Customer", "Unpack Date", "Status", "Result"]
        # Internal Data Structure: [Serial, Model, Customer, UnpackDate, Status, Result]
        # Internal Indices:        0       1      2         3           4       5
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

        if role == Qt.ItemDataRole.DisplayRole:
            # Column 0 is the visual row number
            if col == 0:
                return str(row + 1)
            
            # Shift visual columns 1-6 to internal 0-5
            if 0 < col <= 6:
                return self._data[row][col - 1]
        
        # Color Logic (Status is Visual Column 5 / Internal Index 4)
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

    def sort(self, column, order):
        """
        Called by QTableView when a header is clicked.
        """
        if column == 0:
            return
        
        internal_idx = column - 1
        self.layoutAboutToBeChanged.emit()

        reverse = (order == Qt.SortOrder.DescendingOrder)

        # --- Helper Functions ---
        def status_priority(val):
            # Done > Failed > Filtered > Queued > Processing
            if val == "Done": return 0
            if val == "Failed": return 1
            if val == "Filtered": return 2
            if val == "Queued": return 3
            return 4

        def percentage_value(val_str):
            try:
                return float(val_str.replace('%', ''))
            except (ValueError, AttributeError):
                return -1.0

        def sort_key(row_data):
            val = row_data[internal_idx]
            
            if internal_idx == 4: 
                return status_priority(val)
            
            if internal_idx == 5:
                s_val = str(val)
                if "%" in s_val:
                    return (0, percentage_value(s_val))
                return (1, s_val.lower())

            return str(val).lower()

        self._data.sort(key=sort_key, reverse=reverse)

        self.layoutChanged.emit()

    def add_item(self, serial, model="Unknown", customer=""):
        self.beginInsertRows(QModelIndex(), len(self._data), len(self._data))
        self._data.append([serial, model, customer, "", "Queued", ""])
        self.endInsertRows()

    def update_status(self, serial, status, result, model=None, unpack_date=None, customer=None):
        for i, row in enumerate(self._data):
            if row[0] == serial:
                row[4] = status
                row[5] = result
                
                if model and model != "Unknown": row[1] = model
                if customer: row[2] = customer
                if unpack_date: row[3] = unpack_date

                self.dataChanged.emit(self.index(i, 1), self.index(i, 6))
                return
    
    def get_serial_at(self, row):
        if 0 <= row < len(self._data):
            return self._data[row][0]
        return None

    def clear(self):
        self.beginResetModel()
        self._data = []
        self.endResetModel()

    def sort_by_status(self):
        # Sort by Status column (Visual Col 5 / Internal 4), Ascending
        self.sort(5, Qt.SortOrder.AscendingOrder)