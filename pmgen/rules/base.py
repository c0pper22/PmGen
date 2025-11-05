from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, List
from pmgen.types import PmReport, PmItem, Finding

@dataclass
class Context:
    report: PmReport
    model: str
    counters: Dict[str, int]
    items_by_canon: Dict[str, List[PmItem]]
    threshold: float
    life_basis: str  # 'page' or 'drive'

class RuleBase:
    name: str = "RuleBase"
    def apply(self, ctx: Context) -> List[Finding]:
        raise NotImplementedError
