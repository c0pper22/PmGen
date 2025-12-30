from __future__ import annotations
from typing import Dict, List, Optional, Set, Iterable
from pmgen.rules.base import Context, RuleBase
from pmgen.types import Finding

from pmgen.catalog import part_kit_catalog as catalog_mod
from pmgen.rules.generic_life import _is_due

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
            mapping.setdefault(canon.strip().upper(), kit_code)
    return mapping

class KitLinkRule(RuleBase):
    name = "KitLinkRule"
    _CACHE = {} 

    def _get_cached_map(self, model: str) -> Dict[str, str]:
        if model in self._CACHE:
            return self._CACHE[model]
        
        cat = _ensure_catalog_for_model(model)
        cmap = _canon_to_kit_map_from_catalog(cat)
        
        self._CACHE[model] = cmap
        return cmap

    def apply(self, ctx: Context) -> None:
        model = ctx.model
        cmap = self._get_cached_map(model)
        if not cmap:
            ctx.alerts.append(f"Could not link part to kit, No parts catalog found for model '{model}'.")
            return

        for canon, finding in ctx.findings.items():
            if not finding.due:
                continue

            kit_code = cmap.get(canon)
            if kit_code:
                setattr(finding, "kit_code", kit_code)
            else:
                ctx.alerts.append(f"Missing Link: Item '{canon}' is DUE, but no Kit Code is defined in catalog.")