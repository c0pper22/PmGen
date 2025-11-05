from __future__ import annotations
from typing import List, Optional
from pmgen.rules.base import Context, RuleBase
from pmgen.types import Finding, PmItem

def _life_used(item: PmItem, basis: str) -> Optional[float]:
    p = item.page_life
    d = item.drive_life
    if basis == 'page':
        return p if isinstance(p,(int,float)) else (d if isinstance(d,(int,float)) else None)
    if basis == 'drive':
        return d if isinstance(d,(int,float)) else (p if isinstance(p,(int,float)) else None)
    return p if isinstance(p,(int,float)) else (d if isinstance(d,(int,float)) else None)

class GenericLifeRule(RuleBase):
    name = "GenericLifeRule"
    def apply(self, ctx: Context) -> List[Finding]:
        out: List[Finding] = []
        for canon, items in ctx.items_by_canon.items():
            for it in items:
                used = _life_used(it, ctx.life_basis)
                if used is None:
                    continue
                due = used >= ctx.threshold
                reason = f"{canon}: basis={ctx.life_basis} used={used:.2f} threshold={ctx.threshold:.2f}"
                ev = {
                    "page_life": it.page_life,
                    "drive_life": it.drive_life,
                    "page_current": it.page_current,
                    "page_expected": it.page_expected,
                    "drive_current": it.drive_current,
                    "drive_expected": it.drive_expected,
                }
                out.append(Finding(
                    canon=canon or (it.canon or it.descriptor or "?"),
                    life_used=used,
                    due=due,
                    conf=0.8,
                    reason=reason,
                    evidence=ev
                ))
        return out
