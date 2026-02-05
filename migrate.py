import sqlite3
import re
from pmgen.canon.canon_utils import CANON_MAP
from pmgen.catalog.part_kit_catalog import REGISTRY, PmUnit

DB_PATH = "catalog_manager.db"

def init_db(cursor):
    # 1. Regex Mappings
    cursor.execute("""CREATE TABLE IF NOT EXISTS canon_mappings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        pattern TEXT UNIQUE,
        template TEXT
    )""")
    
    # 2. Kits (PmUnits)
    cursor.execute("""CREATE TABLE IF NOT EXISTS pm_units (
        unit_name TEXT PRIMARY KEY
    )""")
    
    # 3. Items inside Kits
    cursor.execute("""CREATE TABLE IF NOT EXISTS unit_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        unit_name TEXT,
        canon_item TEXT,
        FOREIGN KEY(unit_name) REFERENCES pm_units(unit_name)
    )""")
    
    # 4. Models and their Catalogs
    cursor.execute("""CREATE TABLE IF NOT EXISTS models (
        model_name TEXT PRIMARY KEY
    )""")
    
    cursor.execute("""CREATE TABLE IF NOT EXISTS model_catalog (
        model_name TEXT,
        unit_name TEXT,
        PRIMARY KEY(model_name, unit_name),
        FOREIGN KEY(model_name) REFERENCES models(model_name),
        FOREIGN KEY(unit_name) REFERENCES pm_units(unit_name)
    )""")

def migrate_data():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    init_db(cur)
    
    # --- Migrate Canon Mappings ---
    for pattern_obj, template in CANON_MAP.items():
        cur.execute("INSERT OR IGNORE INTO canon_mappings (pattern, template) VALUES (?, ?)", 
                    (pattern_obj.pattern, template))
    
    # --- Migrate Models and Kits ---
    # We do NOT use 'seen_units' to block item insertion anymore.
    # Instead, we insert items intelligently.

    for model_name, model_obj in REGISTRY.items():
        cur.execute("INSERT OR IGNORE INTO models (model_name) VALUES (?)", (model_name,))
        
        # Access the catalog inside the Model object
        catalog = getattr(model_obj, "catalog", None)
        if catalog and hasattr(catalog, "pm_units"):
            for unit in catalog.pm_units:
                # 1. Ensure Unit Name exists (Idempotent)
                cur.execute("INSERT OR IGNORE INTO pm_units (unit_name) VALUES (?)", (unit.unit_name,))
                
                # 2. Insert Items (Check if exists first to avoid duplicates)
                for item in unit.canon_items:
                    cur.execute("SELECT 1 FROM unit_items WHERE unit_name=? AND canon_item=?", (unit.unit_name, item))
                    if not cur.fetchone():
                        cur.execute("INSERT INTO unit_items (unit_name, canon_item) VALUES (?, ?)", 
                                    (unit.unit_name, item))
                
                # 3. Link Model to Unit
                cur.execute("INSERT OR IGNORE INTO model_catalog (model_name, unit_name) VALUES (?, ?)", 
                            (model_name, unit.unit_name))
    
    conn.commit()
    print(f"Migration complete! Data saved to {DB_PATH}")
    conn.close()

if __name__ == "__main__":
   migrate_data()