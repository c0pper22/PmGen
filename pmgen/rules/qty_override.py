from __future__ import annotations
from typing import List, Dict
from pmgen.rules.base import Context, RuleBase
from pmgen.types import Finding
from pmgen.catalog import part_kit_catalog as cat

class QtyOverrideRule(RuleBase):
    name = "QtyOverrideRule"

    QTY_OVERRIDES: Dict[str, int] = {
        cat.FILTER_OZN_KCH_A08K.unit_name: 2,
        cat.ASYS_ROLL_FEED_SFB_H44X.unit_name: 2,        
    }

    def apply(self, ctx: Context) -> List[Finding]:
        out: List[Finding] = []
        for canon, items in ctx.items_by_canon.items():
            for it in items:
                kit_code = getattr(it, "kit_code", None)
                if not kit_code:
                    continue
                override_qty = self.QTY_OVERRIDES.get(kit_code)
                if override_qty is None:
                    continue
                f = Finding(
                    canon=canon,
                    life_used=getattr(it, "life_used", None),
                    due=True,
                    conf=1.0,
                    reason=f"QtyOverrideRule: {kit_code} → forced qty={override_qty}",
                    evidence={"override_qty": override_qty},
                )
                setattr(f, "kit_code", kit_code)
                setattr(f, "qty", override_qty)
                out.append(f)
        return out