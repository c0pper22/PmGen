from __future__ import annotations
from typing import Dict
from pmgen.rules.base import Context, RuleBase
from pmgen.io.db_access import CatalogDB

class QtyOverrideRule(RuleBase):
    name = "QtyOverrideRule"

    def __init__(self):
        try:
            db_overrides = CatalogDB().get_qty_overrides()
        except Exception:
            db_overrides = {}

        self.overrides: Dict[str, int] = db_overrides

    def apply(self, ctx: Context) -> None:
        for kit in list(ctx.kit_selection.keys()):
            if kit in self.overrides:
                ctx.kit_selection[kit] = self.overrides[kit]