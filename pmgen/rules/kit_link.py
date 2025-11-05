from __future__ import annotations
from typing import Dict, List, Optional, Set, Iterable
from pmgen.rules.base import Context, RuleBase
from pmgen.types import Finding

from pmgen.catalog import part_kit_catalog as catalog_mod


def _ensure_catalog_for_model(model: str):
    """
    Try several conventions to obtain a Catalog for the given model WITHOUT
    hard-coding any kit codes in the rule layer.
    Expected options on part_kit_catalog:
      - get_catalog_for_model(model) -> Catalog
      - MODEL_MAP: Dict[pattern, Catalog] (regex or substring)
      - DEFAULT_CATALOG: Catalog
      - Any top-level variable that *is* a Catalog (last resort)
    """
    # 1) First, a helper function if you provide it.
    get_func = getattr(catalog_mod, "get_catalog_for_model", None)
    if callable(get_func):
        cat = get_func(model)
        if cat:
            return cat

    # 2) MODEL_MAP (regex/substring keys) -> Catalog
    model_map = getattr(catalog_mod, "MODEL_MAP", None)
    if isinstance(model_map, dict) and model:
        m_up = (model or "").upper()
        import re
        for patt, cat in model_map.items():
            try:
                if patt and ((patt in m_up) or re.search(patt, m_up, re.I)):
                    return cat
            except re.error:
                # Treat invalid regex as plain substring
                if patt in m_up:
                    return cat

    # 3) DEFAULT_CATALOG
    dc = getattr(catalog_mod, "DEFAULT_CATALOG", None)
    if dc:
        return dc

    # 4) Any Catalog instance defined at module level
    for name, val in vars(catalog_mod).items():
        if name.isupper() and getattr(val, "__class__", None).__name__ == "Catalog":
            return val

    return None


def _canon_to_kit_map_from_catalog(cat) -> Dict[str, str]:
    """
    Build {canon -> kit_code} from the catalog’s PmUnits.
    - kit_code comes from PmUnit.unit_name
    - canons come from PmUnit.canon_items (strings)
    """
    mapping: Dict[str, str] = {}
    if not cat or not getattr(cat, "pm_units", None):
        return mapping

    # The catalog owns the truth: add/modify PmUnits there; the rule auto-picks it up.
    for unit in getattr(cat, "pm_units", []):
        kit_code = getattr(unit, "unit_name", None)
        canons: Iterable[str] = getattr(unit, "canon_items", []) or []
        if not kit_code:
            continue
        for canon in canons:
            # First one wins; if you intentionally want an override, order your PmUnits accordingly
            mapping.setdefault(canon, kit_code)
    return mapping


def _best_life_used(items: List, basis: str) -> Optional[float]:
    best: Optional[float] = None
    for it in items:
        # items are pmgen.types.PmItem
        p = getattr(it, "page_life", None)
        d = getattr(it, "drive_life", None)
        used = None
        if basis == "page":
            used = p if isinstance(p, (int, float)) else (d if isinstance(d, (int, float)) else None)
        elif basis == "drive":
            used = d if isinstance(d, (int, float)) else (p if isinstance(p, (int, float)) else None)
        else:
            used = p if isinstance(p, (int, float)) else (d if isinstance(d, (int, float)) else None)
        if isinstance(used, (int, float)):
            best = used if best is None else max(best, used)
    return best


class KitLinkRule(RuleBase):
    """
    Data-driven: link DUE canons to kit codes using the model catalog.
    No kit strings are hard-coded here — everything comes from part_kit_catalog.
    """
    name = "KitLinkRule"

    # Cache canon→kit maps by model to avoid rebuilding every run
    _CACHE: Dict[str, Dict[str, str]] = {}

    def apply(self, ctx: Context) -> List[Finding]:
        out: List[Finding] = []

        model = (ctx.model or "").strip()
        # Build/reuse canon->kit map for this model
        cmap = self._CACHE.get(model)
        if cmap is None:
            cat = _ensure_catalog_for_model(model)
            cmap = _canon_to_kit_map_from_catalog(cat)
            # Even if empty, cache the result to avoid repeated probing
            self._CACHE[model] = cmap

        if not cmap:
            # Nothing to do if the catalog doesn’t define any units yet
            return out

        # Walk the canons present in the report
        for canon, items in (ctx.items_by_canon or {}).items():
            if not canon:
                continue

            best_used = _best_life_used(items, ctx.life_basis)
            if best_used is None or best_used < ctx.threshold:
                continue

            kit_code = cmap.get(canon)
            if not kit_code:
                # Canon is due, but the catalog doesn’t (yet) tie it to a kit
                # This will still show up in “Most-due items” from GenericLifeRule.
                continue

            # Emit a finding carrying the kit_code. Qty is per-canon here;
            # your selection layer applies unit semantics (once per PmUnit,
            # except drums/CST per canon).
            f = Finding(
                canon=canon,
                life_used=best_used,
                due=True,
                conf=0.9,
                reason=f"Catalog link: {canon} → {kit_code} (basis={ctx.life_basis}, used={best_used:.2f} ≥ thr={ctx.threshold:.2f})",
            )
            setattr(f, "kit_code", kit_code)
            setattr(f, "qty", 1)
            out.append(f)

        return out
