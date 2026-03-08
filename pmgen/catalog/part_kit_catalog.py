from pmgen.io.http_client import get_db_path
import sqlite3
from typing import Optional
import os

class PmUnit:
    def __init__(self, unit_name, canon_items):
        self.unit_name = unit_name
        self.canon_items = canon_items

class Catalog:
    def __init__(self, pm_units):
        self.pm_units = pm_units
    
class Model:
    def __init__(self, catalog):
        self.catalog = catalog

def get_catalog_for_model(model: str) -> Optional[Catalog]:
    if not model:
        return None

    up = model.upper()
    db_path = get_db_path()
    if not os.path.exists(db_path):
        return None

    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    cur.execute("SELECT model_name FROM models")
    db_models = [row[0] for row in cur.fetchall()]
    
    matched_model = None
    for dm in db_models:
        if dm in up:
            matched_model = dm
            break
    
    if not matched_model:
        conn.close()
        return None

    cur.execute("SELECT unit_name FROM model_catalog WHERE model_name = ?", (matched_model,))
    unit_names = [row[0] for row in cur.fetchall()]

    pm_units = []
    for uname in unit_names:
        cur.execute("SELECT canon_item FROM unit_items WHERE unit_name = ?", (uname,))
        items = [row[0] for row in cur.fetchall()]
        pm_units.append(PmUnit(uname, items))

    conn.close()
    return Catalog(pm_units)