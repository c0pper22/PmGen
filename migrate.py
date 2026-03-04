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

    # 5. Quantity Overrides
    cursor.execute("""CREATE TABLE IF NOT EXISTS qty_overrides (
        unit_name TEXT PRIMARY KEY,
        quantity INTEGER NOT NULL,
        FOREIGN KEY(unit_name) REFERENCES pm_units(unit_name)
    )""")

    # 6. Unit semantics (count once per color channel)
    cursor.execute("""CREATE TABLE IF NOT EXISTS per_color_units (
        unit_name TEXT PRIMARY KEY,
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
    for model_name, model_obj in REGISTRY.items():
        cur.execute("INSERT OR IGNORE INTO models (model_name) VALUES (?)", (model_name,))
        
        catalog = getattr(model_obj, "catalog", None)
        if catalog and hasattr(catalog, "pm_units"):
            for unit in catalog.pm_units:
                cur.execute("INSERT OR IGNORE INTO pm_units (unit_name) VALUES (?)", (unit.unit_name,))
                
                for item in unit.canon_items:
                    cur.execute("SELECT 1 FROM unit_items WHERE unit_name=? AND canon_item=?", (unit.unit_name, item))
                    if not cur.fetchone():
                        cur.execute("INSERT INTO unit_items (unit_name, canon_item) VALUES (?, ?)", 
                                    (unit.unit_name, item))
                
                cur.execute("INSERT OR IGNORE INTO model_catalog (model_name, unit_name) VALUES (?, ?)", 
                            (model_name, unit.unit_name))

    # --- Seed Quantity Overrides (if missing) ---
    qty_overrides = [
        ("FILTER-OZN-KCH-A08K", 2),
        ("ASYS-ROLL-FEED-SFB-H44X", 2),
    ]
    for unit_name, qty in qty_overrides:
        cur.execute(
            "INSERT OR IGNORE INTO qty_overrides (unit_name, quantity) VALUES (?, ?)",
            (unit_name, qty),
        )

    # --- Seed Per-Color Unit Semantics (if missing) ---
    # ─────────────────────────────────────────────────────────────────────────────
    # All PmUnit names listed here are treated as *per-color kits* by the rules engine.
    # That means each kit will count **once per color channel (K/C/M/Y)**, regardless
    # of how many color-tagged canons inside it are due (e.g., DRUM[K], GRID[K], etc.).
    # 
    # This prevents double-counting within multi-part developer/drum units such as
    # EPU-FC330-K or EPU-KIT-FC556-G, which include several related K-channel canons.
    # ─────────────────────────────────────────────────────────────────────────────
    per_color_units = [
        "EPU-KIT-FC556-G",
        "EPU-FC330-K",
        "EPU-FC330-Y",
        "EPU-FC330-M",
        "EPU-FC330-C",
    ]
    for unit_name in per_color_units:
        cur.execute(
            "INSERT OR IGNORE INTO per_color_units (unit_name) VALUES (?)",
            (unit_name,),
        )
    
    conn.commit()
    print(f"Migration complete! Data saved to {DB_PATH}")
    conn.close()

if __name__ == "__main__":
   migrate_data()