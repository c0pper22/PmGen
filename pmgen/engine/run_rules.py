# run_rules.py
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional, Tuple, Set
import re

from pmgen.types import PmReport, PmItem, Finding, Selection
from pmgen.rules import Context, RuleBase, GenericLifeRule, KitLinkRule

# Optional: resolver is only for PN *expansion*; unit *quantities* come from our selection logic.
try:
    from pmgen.engine.resolve_to_pn import resolve_with_rows
    HAVE_RIBON = True
except Exception:
    resolve_with_rows = None
    HAVE_RIBON = False

# Read model catalog helpers/sets (safe if not present)
try:
    from pmgen.catalog import part_kit_catalog as cat
    _PER_COLOR_UNITS: Set[str] = set(getattr(cat, "PER_COLOR_UNIT_NAMES", set()) or set())
except Exception:
    _PER_COLOR_UNITS = set()

# NEW: import overrides table (no need to run a rule)
try:
    from pmgen.rules.qty_override import QtyOverrideRule as _QtyOverride
    _QTY_OVERRIDES: Dict[str, int] = dict(getattr(_QtyOverride, "QTY_OVERRIDES", {}) or {})
except Exception:
    _QTY_OVERRIDES = {}

# Order can be adjusted if rules develop dependencies
RULES: List[RuleBase] = [GenericLifeRule(), KitLinkRule()]

def build_context(report: PmReport, threshold: float, life_basis: str) -> Context:
    model = (report.headers or {}).get("model", "")
    counters = report.counters or {}
    items_by_canon: Dict[str, List[PmItem]] = defaultdict(list)
    for it in (report.items or []):
        key = (getattr(it, "canon", None) or getattr(it, "descriptor", None) or "?")
        items_by_canon[key].append(it)
    return Context(
        report=report,
        model=model,
        counters=counters,
        items_by_canon=dict(items_by_canon),
        threshold=threshold,
        life_basis=life_basis,
    )

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

def run_rules(report: PmReport, threshold: float, life_basis: str) -> Selection:
    ctx = build_context(report, threshold, life_basis)

    # 1) Run all rules resiliently
    findings: List[Finding] = []
    for rule in RULES:
        try:
            findings.extend(rule.apply(ctx))
        except Exception:
            # keep pipeline resilient — one bad rule shouldn't kill the run
            pass

    # 2) Deduplicate by canon: keep highest (life_used, conf)
    best: Dict[str, Finding] = {}
    for f in findings:
        prev = best.get(f.canon)
        if not prev:
            best[f.canon] = f
            continue
        key_prev = ((prev.life_used or -1.0), prev.conf)
        key_new = ((f.life_used or -1.0), f.conf)
        if key_new > key_prev:
            best[f.canon] = f

    # 3) Due + watch
    due = [f for f in best.values() if f.due]
    due.sort(key=lambda x: (x.life_used or 0.0, x.conf), reverse=True)

    watch = [f for f in best.values() if not f.due and (f.life_used or 0) >= max(0.0, threshold - 0.05)]
    watch.sort(key=lambda x: (x.life_used or 0.0, x.conf), reverse=True)

    # 4) Build kit_selection using *unit semantics*
    seen_buckets: Set[Tuple[str, Optional[str]]] = set()
    kit_selection: Dict[str, int] = {}

    for f in due:
        kit_code = getattr(f, "kit_code", None)
        if not kit_code:
            continue
        bk = _unit_bucket_key(kit_code, getattr(f, "canon", None))
        if bk in seen_buckets:
            continue  # already counted this unit/canon/channel/tray
        seen_buckets.add(bk)
        # NOTE: base count per distinct unit bucket is +1
        kit_selection[kit_code] = kit_selection.get(kit_code, 0) + 1

    # 4b) APPLY QTY OVERRIDES (force quantity for listed kits)
    if _QTY_OVERRIDES and kit_selection:
        for kit_code, forced_qty in _QTY_OVERRIDES.items():
            if kit_code in kit_selection:
                try:
                    kit_selection[kit_code] = int(forced_qty)
                except Exception:
                    pass  # ignore bad values; keep computed qty

    # 5) Expand to PN totals (optional; selection qty already finalized above)
    ribon_rows: Dict[str, List] = {}
    selection_pn_flat: Dict[str, int] = {}
    if HAVE_RIBON and resolve_with_rows and kit_selection:
        try:
            ribon_rows, selection_pn_flat = resolve_with_rows(kit_selection)
        except Exception:
            ribon_rows, selection_pn_flat = {}, {}

    # 6) Group PNs by kit (for formatter "UNIT - PN xqty")
    selection_pn_grouped: Dict[str, Dict[str, int]] = {}
    kit_by_pn: Dict[str, str] = {}

    def _as_list(x) -> List:
        if x is None:
            return []
        if isinstance(x, list):
            return x
        return [x]

    def _get_pn_field(row) -> Optional[str]:
        if isinstance(row, str):
            return row.strip()
        if isinstance(row, dict):
            for k in ("PARTS_NO", "PART_NO", "PARTSNO", "PARTS_NO_COM", "PN"):
                v = row.get(k)
                if v:
                    return str(v)
        return None

    any_grouped = False
    for kit_code in (kit_selection or {}):
        rows = _as_list(ribon_rows.get(kit_code) if ribon_rows else [])
        if not rows:
            continue
        bucket = selection_pn_grouped.setdefault(kit_code, {})
        for row in rows:
            pn = _get_pn_field(row)
            if not pn:
                continue
            q_flat = int(selection_pn_flat.get(pn, 0))
            bucket[pn] = bucket.get(pn, 0) + (q_flat if q_flat > 0 else 1)
            kit_by_pn.setdefault(pn, kit_code)
            any_grouped = True

    if not any_grouped and selection_pn_flat:
        reverse_index: Dict[str, str] = {}
        for kit_code in (kit_selection or {}):
            rows = _as_list(ribon_rows.get(kit_code) if ribon_rows else [])
            for row in rows:
                pn = _get_pn_field(row)
                if pn and pn not in reverse_index:
                    reverse_index[pn] = kit_code
        for pn, qty in selection_pn_flat.items():
            owner = reverse_index.get(pn, "UNKNOWN-UNIT")
            selection_pn_grouped.setdefault(owner, {})
            selection_pn_grouped[owner][pn] = selection_pn_grouped[owner].get(pn, 0) + int(qty or 0)
            kit_by_pn.setdefault(pn, owner)

    # 7) Return
    meta = {
        "watch": watch,
        "all": list(best.values()),
        "selection_codes": kit_selection,               # {kit_code: qty of units}
        "selection_pn": selection_pn_flat,              # flat {PN: total qty}
        "selection_pn_grouped": selection_pn_grouped,   # {kit_code: {PN: qty}}
        "kit_by_pn": kit_by_pn,                         # {PN: kit_code}
        "ribon_rows": ribon_rows,                       # raw rows (if any)
        "qty_source": "unit_selection+override" if _QTY_OVERRIDES else "unit_selection",
    }

    sel = Selection(items=due, kits=[], meta=meta)
    setattr(sel, "watch", watch)
    setattr(sel, "all_items", list(best.values()))
    setattr(sel, "not_due", [f for f in best.values() if not f.due])
    return sel
