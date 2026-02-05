"""
RIBON (Access) database adapter

Purpose
-------
Given a set of PARTS_NAME_COM codes (e.g. "EPU-KIT-FC505CLR"),
resolve them to actual part numbers (e.g. "6LE00000000") by querying
T_RBN_PARTS_MASTER in Ribon.accdb.

Usage
-----
from pmgen.io.ribon_db import query_parts_rows, expand_to_part_numbers

rows = query_parts_rows({"EPU-KIT-FC505CLR", "FR-KIT-FC505"})
parts = expand_to_part_numbers({"EPU-KIT-FC505CLR": 2, "FR-KIT-FC505": 1}, rows)
# parts => {"6LE0-...": 2, "6LH0-...": 1}

Notes
-----
• Thread-safe: all cursor work is serialized with a module-level lock to
  avoid Access ODBC error (-1036: "Too many client tasks").
• Single shared connection to minimize login overhead with the Access driver.
• Path/password are configurable via environment variables.
• Graceful fallback if pyodbc is not installed.
"""
from __future__ import annotations

from typing import Dict, Iterable, Optional, Tuple
import os
import threading

try:
    import pyodbc  # type: ignore
    pyodbc.pooling = False
except Exception:  # pragma: no cover
    pyodbc = None  # sentinel

# ------------------------- Configuration -------------------------
# Default values match the legacy tool; can be overridden by env vars.
_DEF_PATH = r"C:\\TTECCDRibon\\db\\Ribon.accdb"
_DEF_PWD  = "rbn-MTomy3s8NuM7IbtQ"

RIBON_DB_PATH = os.environ.get("RIBON_DB_PATH", _DEF_PATH)
RIBON_DB_PASSWORD = os.environ.get("RIBON_DB_PASSWORD", _DEF_PWD)

_CONN_STR = (
    r"Driver={Microsoft Access Driver (*.mdb, *.accdb)};"
    fr"Dbq={RIBON_DB_PATH};"
    fr"PWD={RIBON_DB_PASSWORD};"
)

_DB_LOCK = threading.Lock()
_DB_CONN: Optional["pyodbc.Connection"] = None  # type: ignore[name-defined]

# The PARTS# field name varies across dumps; probe these in order.
_PARTS_NO_FIELDS = ("PARTS_NO", "PART_NO", "PARTSNO", "PARTS_NO_COM", "PN")

# ------------------------- Connection helpers -------------------------

def _ensure_odbc():
    if pyodbc is None:
        raise RuntimeError(
            "pyodbc is not available. Install it to enable RIBON lookups.")


def _get_db_conn():
    """Lazily create a single shared pyodbc connection.

    All cursor operations MUST be guarded by _DB_LOCK.
    """
    _ensure_odbc()
    global _DB_CONN
    if _DB_CONN is None:
        _DB_CONN = pyodbc.connect(_CONN_STR, autocommit=True)  # type: ignore[attr-defined]
    return _DB_CONN


# ------------------------- Public API -------------------------

def query_parts_rows(parts_name_com_list: Iterable[str]) -> Dict[str, Dict[str, object]]:
    """Fetch the newest matching row for each PARTS_NAME_COM.

    Returns a mapping: PARTS_NAME_COM -> row(dict).
    Unknown codes are omitted.
    """
    codes = [c for c in (parts_name_com_list or []) if isinstance(c, str) and c]
    out: Dict[str, Dict[str, object]] = {}
    if not codes:
        return out
    
    print(f"DEBUG: About to query DB for {len(codes)} items...", flush=True)

    with _DB_LOCK:
        cn = _get_db_conn()
        cur = cn.cursor()
        try:
            for code in codes:
                # Prefer an ORDER BY to keep newest rows first
                try:
                    cur.execute(
                        "SELECT TOP 1 * FROM T_RBN_PARTS_MASTER "
                        "WHERE PARTS_NAME_COM=? "
                        "ORDER BY CREATION_DATE DESC, LAST_UPDATE_DATE DESC",
                        (code,),
                    )
                except Exception:
                    # Fallback for drivers that don't support TOP + ORDER BY properly
                    cur.execute(
                        "SELECT * FROM T_RBN_PARTS_MASTER WHERE PARTS_NAME_COM=?",
                        (code,),
                    )
                rows = cur.fetchall()
                if not rows:
                    continue
                cols = [c[0] for c in cur.description]
                newest = rows[0]
                out[code] = {col: newest[i] for i, col in enumerate(cols)}
        finally:
            try:
                cur.close()
            except Exception:
                pass
    return out


def expand_to_part_numbers(selection: Dict[str, int],
                           db_rows_by_code: Dict[str, Dict[str, object]]) -> Dict[str, int]:
    """Convert a PARTS_NAME_COM->qty selection into PARTS_NO->qty.

    Any codes missing in *db_rows_by_code* are silently skipped.
    """
    consolidated: Dict[str, int] = {}
    for code, qty in (selection or {}).items():
        row = db_rows_by_code.get(code)
        if not row:
            continue
        # Find the first existing parts number field
        parts_field = next((f for f in _PARTS_NO_FIELDS if f in row), None)
        if not parts_field:
            # If the row doesn't expose any expected field, skip it
            continue
        pn = str(row.get(parts_field) or "").strip()
        if not pn:
            continue
        consolidated[pn] = consolidated.get(pn, 0) + int(qty or 0)
    return consolidated


# ------------------------- Convenience wrapper -------------------------

def resolve_selection_to_part_numbers(selection: Dict[str, int]) -> Dict[str, int]:
    """Single-call helper used by the engine.

    1) query the DB for all selection keys
    2) expand to actual part numbers
    """
    rows = query_parts_rows(selection.keys())
    return expand_to_part_numbers(selection, rows)


# ------------------------- ALIASES (one-module import) ------------------

# Same as resolve_selection_to_part_numbers; name fits “codes -> PNs”
def resolve_codes_to_pns(selection: Dict[str, int]) -> Dict[str, int]:
    return resolve_selection_to_part_numbers(selection)

# Return both raw rows (for UI details) and the consolidated PN map.
def resolve_with_rows(selection: Dict[str, int]) -> Tuple[Dict[str, dict], Dict[str, int]]:
    rows = query_parts_rows(selection.keys())
    pns = expand_to_part_numbers(selection, rows)
    return rows, pns


# ------------------------- CLI smoke test -------------------------
if __name__ == "__main__":  # pragma: no cover
    test = {"EPU-KIT-FC505CLR": 1, "FR-KIT-FC505": 1}
    try:
        rows = query_parts_rows(test.keys())
        print("Resolved rows:")
        for k, v in rows.items():
            print(" ", k, "→", {f: v.get(f) for f in ("PARTS_NAME_COM", "PARTS_NO", "DESCRIPTION", "LAST_UPDATE_DATE")})
        print("\nParts numbers:")
        print(resolve_selection_to_part_numbers(test))
    except Exception as e:
        print("RIBON test failed:", e)
