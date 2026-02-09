import sqlite3
import os
from typing import List, Tuple, Optional, Dict
from pmgen.io.http_client import get_db_path

class CatalogDB:
    """
    Helper class to manage interactions with catalog_manager.db
    Handles Models, PM Units, Unit Contents, and Canon Mappings.
    """
    def __init__(self):
        self.db_path = get_db_path()
        self._ensure_tables()

    def _get_conn(self):
        return sqlite3.connect(self.db_path)

    def _ensure_tables(self):
        """Ensures the required tables exist to prevent crashes on fresh installs."""
        conn = self._get_conn()
        cur = conn.cursor()
        
        # 1. Models Table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS models (
                model_name TEXT PRIMARY KEY
            )
        """)

        # 2. Units Table (The kits themselves)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS pm_units (
                unit_name TEXT PRIMARY KEY
            )
        """)

        # 3. Model <-> Unit Link (Many-to-Many)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS model_catalog (
                model_name TEXT,
                unit_name TEXT,
                PRIMARY KEY (model_name, unit_name),
                FOREIGN KEY(model_name) REFERENCES models(model_name) ON DELETE CASCADE,
                FOREIGN KEY(unit_name) REFERENCES pm_units(unit_name) ON DELETE CASCADE
            )
        """)

        # 4. Unit Contents (What parts are in a kit)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS unit_items (
                unit_name TEXT,
                canon_item TEXT,
                FOREIGN KEY(unit_name) REFERENCES pm_units(unit_name) ON DELETE CASCADE
            )
        """)

        # 5. Canon Mappings (Regex Rules)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS canon_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                pattern TEXT NOT NULL,
                template TEXT NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()

    # =========================================================================
    #  MODELS
    # =========================================================================
    
    def get_all_models(self) -> List[str]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT model_name FROM models ORDER BY model_name")
            return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

    def add_model(self, model_name: str):
        if not model_name.strip(): return
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("INSERT OR IGNORE INTO models (model_name) VALUES (?)", (model_name.upper().strip(),))
            conn.commit()
        finally:
            conn.close()

    def delete_model(self, model_name: str):
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM model_catalog WHERE model_name = ?", (model_name,))
            cur.execute("DELETE FROM models WHERE model_name = ?", (model_name,))
            conn.commit()
        finally:
            conn.close()

    # =========================================================================
    #  PM UNITS (Kits)
    # =========================================================================

    def get_all_units(self) -> List[str]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT unit_name FROM pm_units ORDER BY unit_name")
            return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

    def add_unit(self, unit_name: str):
        if not unit_name.strip(): return
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("INSERT OR IGNORE INTO pm_units (unit_name) VALUES (?)", (unit_name.strip(),))
            conn.commit()
        finally:
            conn.close()

    def delete_unit(self, unit_name: str):
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM unit_items WHERE unit_name = ?", (unit_name,))
            cur.execute("DELETE FROM model_catalog WHERE unit_name = ?", (unit_name,))
            cur.execute("DELETE FROM pm_units WHERE unit_name = ?", (unit_name,))
            conn.commit()
        finally:
            conn.close()

    # =========================================================================
    #  LINKS (Model <-> Unit)
    # =========================================================================

    def get_units_for_model(self, model_name: str) -> List[str]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("""
                SELECT unit_name FROM model_catalog 
                WHERE model_name = ? 
                ORDER BY unit_name
            """, (model_name,))
            return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

    def link_unit_to_model(self, model_name: str, unit_name: str):
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("INSERT OR IGNORE INTO model_catalog (model_name, unit_name) VALUES (?, ?)", 
                        (model_name, unit_name))
            conn.commit()
        finally:
            conn.close()

    def unlink_unit_from_model(self, model_name: str, unit_name: str):
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM model_catalog WHERE model_name = ? AND unit_name = ?", 
                        (model_name, unit_name))
            conn.commit()
        finally:
            conn.close()

    # =========================================================================
    #  UNIT CONTENTS (Items inside a Unit)
    # =========================================================================

    def get_items_for_unit(self, unit_name: str) -> List[str]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("SELECT canon_item FROM unit_items WHERE unit_name = ? ORDER BY canon_item", (unit_name,))
            return [row[0] for row in cur.fetchall()]
        finally:
            conn.close()

    def add_item_to_unit(self, unit_name: str, item: str):
        if not item.strip(): return
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO unit_items (unit_name, canon_item) VALUES (?, ?)", (unit_name, item.strip()))
            conn.commit()
        finally:
            conn.close()

    def remove_item_from_unit(self, unit_name: str, item: str):
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            # SQLite specific: delete only one row matching criteria
            cur.execute("""
                DELETE FROM unit_items 
                WHERE rowid IN (
                    SELECT rowid FROM unit_items 
                    WHERE unit_name = ? AND canon_item = ? 
                    LIMIT 1
                )
            """, (unit_name, item))
            conn.commit()
        finally:
            conn.close()

    # =========================================================================
    #  CANON MAPPINGS (Regex)
    # =========================================================================

    def get_mappings(self) -> List[Tuple[int, str, str]]:
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            try:
                cur.execute("SELECT id, pattern, template FROM canon_mappings ORDER BY pattern")
            except sqlite3.OperationalError:
                cur.execute("SELECT rowid, pattern, template FROM canon_mappings ORDER BY pattern")
            return cur.fetchall()
        finally:
            conn.close()

    def add_mapping(self, pattern: str, template: str):
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            cur.execute("INSERT INTO canon_mappings (pattern, template) VALUES (?, ?)", (pattern, template))
            conn.commit()
        finally:
            conn.close()

    def delete_mapping(self, mapping_id: int):
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            try:
                cur.execute("DELETE FROM canon_mappings WHERE id = ?", (mapping_id,))
            except sqlite3.OperationalError:
                cur.execute("DELETE FROM canon_mappings WHERE rowid = ?", (mapping_id,))
            conn.commit()
        finally:
            conn.close()

    def update_mapping(self, mapping_id: int, pattern: str, template: str):
        conn = self._get_conn()
        try:
            cur = conn.cursor()
            try:
                cur.execute("UPDATE canon_mappings SET pattern=?, template=? WHERE id=?", (pattern, template, mapping_id))
            except sqlite3.OperationalError:
                cur.execute("UPDATE canon_mappings SET pattern=?, template=? WHERE rowid=?", (pattern, template, mapping_id))
            conn.commit()
        finally:
            conn.close()