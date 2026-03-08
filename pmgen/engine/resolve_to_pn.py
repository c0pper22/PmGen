from __future__ import annotations
from typing import Dict, Tuple

from pmgen.io.ribon_db import query_parts_rows, expand_to_part_numbers

def resolve_with_rows(selection: Dict[str, int]) -> Tuple[Dict[str, dict], Dict[str, int]]:
    """Return both DB rows and final PARTS_NO quantities.

    Args:
        selection: Mapping of kit codes (PARTS_NAME_COM) to quantities.

    Returns:
        (rows_by_code, parts_no_map)
    """
    rows = query_parts_rows(selection.keys())
    pns = expand_to_part_numbers(selection, rows)
    return rows, pns


def resolve_to_part_numbers(selection: Dict[str, int]) -> Dict[str, int]:
    """Shortcut: only return PARTS_NO -> qty mapping."""
    _, pns = resolve_with_rows(selection)
    return pns
