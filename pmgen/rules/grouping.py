from pmgen.rules.base import RuleBase, Context
import re
from typing import Dict, List, Optional, Tuple, Set

try:
    from pmgen.catalog import part_kit_catalog as cat
    _PER_COLOR_UNITS: Set[str] = set(getattr(cat, "PER_COLOR_UNIT_NAMES", set()) or set())
except Exception:
    _PER_COLOR_UNITS = set()

# ---------------------------
# Helpers for unit semantics
# ---------------------------
def _canon_channel(canon: Optional[str]) -> Optional[str]:
    """Return 'K'/'C'/'M'/'Y' if the canon includes a color channel, else None."""
    if not canon:
        return None
    m = re.search(r"\[(K|C|M|Y)\]", canon.upper())
    return m.group(1) if m else None


def _is_drum_canon(canon: Optional[str]) -> bool:
    """Identify canons that should be counted *per color drum* only."""
    if not canon:
        return False
    u = canon.upper().strip()
    return u.startswith("DRUM[") and u.endswith("]") and "BLADE" not in u


def _is_cst_canon(canon: Optional[str]) -> bool:
    """Return True if the canon belongs to a paper cassette (CST) unit."""
    if not canon:
        return False
    u = canon.upper()
    return "CST" in u


def _cassette_slot_id(canon: Optional[str]) -> Optional[str]:
    """Extract a per-tray id: 1st/2nd/3rd/4th CST (uppercased), else None."""
    if not canon:
        return None
    m = re.search(r"\((?P<slot>(1ST|2ND|3RD|4TH)\s*CST\.?)\)", canon.upper())
    return m.group("slot") if m else None


def _unit_bucket_key(kit_code: str, canon: Optional[str]) -> Tuple[str, Optional[str]]:
    """
    Build the *unit* key used to ensure we count each PmUnit once.

    - Normal units:              (kit_code, None)
    - Per-color kits (declared): (kit_code, <channel>)           → once per K/C/M/Y
    - Drum units:                (kit_code, canon)               → per color (DRUM[K/C/M/Y])
    - CST units:                 (kit_code, <tray-slot>)         → per tray (1st/2nd/3rd/4th)
    """
    # 1) Explicit per-color kits (e.g., EPU-KIT-FC556-G)
    if kit_code in _PER_COLOR_UNITS:
        ch = _canon_channel(canon)
        return (kit_code, ch or "<per-color>")

    # 2) Drums are per-color by canon name
    if _is_drum_canon(canon):
        return (kit_code, canon or "<per-canon>")

    # 3) Paper cassettes are per-tray
    if _is_cst_canon(canon):
        slot = _cassette_slot_id(canon)
        return (kit_code, slot or "<cst>")

    # 4) Everything else counts once
    return (kit_code, None)

class UnitGroupingRule(RuleBase):
    """
    Responsible for converting a list of Due Findings into a list of Unit Quantities.
    Handles 'Drum per color', 'CST per tray', etc.
    """
    name = "UnitGroupingRule"

    def apply(self, ctx: Context) -> None:
        seen_buckets = set()
        selection = {}

        for finding in ctx.findings.values():
            if not finding.due or not getattr(finding, "kit_code", None):
                continue
                
            kit = finding.kit_code
            canon = finding.canon
            
            # Use your helper logic here (moved from run_rules.py)
            bucket_key = self._get_bucket_key(kit, canon)
            
            if bucket_key in seen_buckets:
                continue
            
            seen_buckets.add(bucket_key)
            selection[kit] = selection.get(kit, 0) + 1
            
        ctx.kit_selection = selection

    def _get_bucket_key(self, kit, canon):
        return _unit_bucket_key(kit_code=kit, canon=canon)