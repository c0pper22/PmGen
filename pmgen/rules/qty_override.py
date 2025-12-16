from __future__ import annotations
from typing import List, Dict
from pmgen.rules.base import Context, RuleBase
from pmgen.types import Finding
from pmgen.catalog import part_kit_catalog as cat

class QtyOverrideRule(RuleBase):
    name = "QtyOverrideRule"
    
    OVERRIDES: Dict[str, int] = {}
    
    def __init__(self):
        try:
            self.OVERRIDES[cat.FILTER_OZN_KCH_A08K.unit_name] = 2
            self.OVERRIDES[cat.ASYS_ROLL_FEED_SFB_H44X.unit_name] = 2
        except AttributeError:
            pass

    def apply(self, ctx: Context) -> None:
        for kit, qty in ctx.kit_selection.items():
            if kit in self.OVERRIDES:
                ctx.kit_selection[kit] = self.OVERRIDES[kit]