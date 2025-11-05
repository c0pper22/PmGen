from __future__ import annotations
from typing import Optional, Any, Iterable, List
from pmgen.parsing import ParsePmReport
from pmgen.engine.run_rules import run_rules
from pmgen.types import PmReport as PmReportType, PmItem as PmItemType
from pmgen.types import PmReport
from pmgen.engine.run_rules import run_rules
from pmgen.parsing.parse_pm_report import parse_pm_report
from datetime import datetime

def _coerce_items(items: Iterable[Any]) -> list[PmItemType]:
    out: list[PmItemType] = []
    for it in (items or []):
        if hasattr(it, "page_life") and hasattr(it, "drive_life"):
            out.append(it)  # already our dataclass
            continue
        try:
            get = (lambda k: getattr(it, k) if hasattr(it, k) else (it.get(k) if isinstance(it, dict) else None))
            out.append(PmItemType(
                descriptor=get("descriptor") or get("name") or "",
                page_current=get("page_current"),
                page_expected=get("page_expected"),
                drive_current=get("drive_current"),
                drive_expected=get("drive_expected"),
                canon=get("canon") or None,
            ))
        except Exception:
            continue
    return out

def _life_used(item: PmItemType, basis: str) -> Optional[float]:
    p = getattr(item, 'page_life', None)
    d = getattr(item, 'drive_life', None)
    if basis == 'page':
        return p if isinstance(p, (int, float)) else (d if isinstance(d, (int, float)) else None)
    if basis == 'drive':
        return d if isinstance(d, (int, float)) else (p if isinstance(p, (int, float)) else None)
    return p if isinstance(p, (int, float)) else (d if isinstance(d, (int, float)) else None)

def _fmt_pct(p: Optional[float]) -> str:
    if p is None:
        return "—"
    return f"{(float(p) * 100):.1f}%"

def format_report(
    *,
    report,
    selection,
    threshold: float,
    life_basis: str,
    show_all: bool = False
) -> str:
    """
    Pretty-print the single-report result.

    Expects:
      - report.headers: dict with "model" and "serial" (strings)
      - report.counters: dict with optional keys: color, black, df, total (ints)
      - selection.items: list[Finding] that are DUE (post-dedup)
      - selection.meta:
          - "watch": list[Finding] (near-due/under threshold)
          - "all":   list[Finding] (best-per-canon, due + not-due)
          - "selection_pn_grouped": {kit_code: {PN: qty}}
          - "selection_pn": {PN: qty} (flat)
          - "kit_by_pn": {PN: kit_code}
    """

    # ---------- helpers ----------
    def _fmt_pct(p):
        if p is None:
            return "—"
        try:
            return f"{(float(p) * 100):.1f}%"
        except Exception:
            return "—"

    def _get(d, key, default=None):
        try:
            return d.get(key, default)
        except Exception:
            return default

    # ---------- header line ----------
    # BUG FIX: don't call _get(..., key=None). Just take the dict.
    hdrs = getattr(report, "headers", {}) or {}
    model  = hdrs.get("model", "Unknown")
    serial = hdrs.get("serial", "Unknown")

    # Report date: use header string if present, else now
    from datetime import datetime
    dt_raw = hdrs.get("date")
    if isinstance(dt_raw, str) and dt_raw.strip():
        dt_str = dt_raw
    else:
        dt_str = datetime.now().strftime("%m-%d-%Y %H:%M")

    # ---------- counters ----------
    counters_lines = []
    c = getattr(report, "counters", {}) or {}
    if isinstance(c, dict):
        parts = []
        if _get(c, "color") is not None: parts.append(f"Color: {_get(c, 'color')}")
        if _get(c, "black") is not None: parts.append(f"Black: {_get(c, 'black')}")
        if _get(c, "df")    is not None: parts.append(f"DF: {_get(c, 'df')}")
        if _get(c, "total") is not None: parts.append(f"Total: {_get(c, 'total')}")
        if parts:
            counters_lines.append("Counters:")
            counters_lines.append("  " + "  ".join(parts))

    # ---------- due / not-due items for “Most-Due Items” ----------
    due_items = list(getattr(selection, "items", []) or [])

    # Pull under-threshold (not-due) items when show_all=True
    not_due_items = []
    if show_all:
        # NEW: Prefer the full not_due list instead of watch
        if hasattr(selection, "not_due") and selection.not_due:
            not_due_items = list(selection.not_due)
        elif hasattr(selection, "all_items") and selection.all_items:
            not_due_items = [f for f in selection.all_items if not getattr(f, "due", False)]
        else:
            meta = getattr(selection, "meta", {}) or {}
            all_items = meta.get("all", []) or meta.get("all_items", []) or []
            not_due_items = [f for f in all_items if not getattr(f, "due", False)]

    # Build the rows (sorted by life_used then conf)
    most_due_rows = []
    if show_all:
        combined = list(due_items) + list(not_due_items)
        combined.sort(key=lambda x: (getattr(x, "life_used", 0.0), getattr(x, "conf", 0.0)), reverse=True)
        for f in combined:
            canon = getattr(f, "canon", "—")
            pct   = _fmt_pct(getattr(f, "life_used", None))
            is_due = bool(getattr(f, "due", False))
            kit    = getattr(f, "kit_code", None)
            if is_due:
                most_due_rows.append(f"  • {canon} — {pct} → DUE")
                most_due_rows.append(f"      ↳ Catalog: {kit or '(N/A)'}")
            else:
                most_due_rows.append(f"  • {canon} — {pct}")
                most_due_rows.append(f"      ↳ Catalog: (N/A)")
            most_due_rows.append("")
    else:
        for f in due_items:
            canon = getattr(f, "canon", "—")
            pct   = _fmt_pct(getattr(f, "life_used", None))
            kit   = getattr(f, "kit_code", None) or "(N/A)"
            most_due_rows.append(f"  • {canon} — {pct} → DUE")
            most_due_rows.append(f"      ↳ Catalog: {kit}")
            most_due_rows.append("")

    # ---------- final parts (grouped by kit → PN × qty) ----------
    final_lines = []
    final_lines.append("Final Parts")
    final_lines.append("───────────────────────────────────────────────────────────────")
    #final_lines.append("(Unit → Part Number × Qty)")
    final_lines.append("(Qty → Part Number → Unit )")

    meta = getattr(selection, "meta", {}) or {}
    grouped = meta.get("selection_pn_grouped", {}) or {}
    flat    = meta.get("selection_pn", {}) or {}
    by_pn   = meta.get("kit_by_pn", {}) or {}

    # if grouped:
    #     for kit, pns in grouped.items():
    #         for pn, qty in (pns or {}).items():
    #             final_lines.append(f"{kit} → {pn} ×{int(qty)}")
    # elif flat:
    #     for pn, qty in flat.items():
    #         kit = by_pn.get(pn, "UNKNOWN-UNIT")
    #         final_lines.append(f"{kit} → {pn} ×{int(qty)}")
    # else:
    #     final_lines.append("(no final parts)")

    if grouped:
        for kit, pns in grouped.items():
            for pn, qty in (pns or {}).items():
                final_lines.append(f"{int(qty)}x → {pn} → {kit}")
    elif flat:
        for pn, qty in flat.items():
            kit = by_pn.get(pn, "UNKNOWN-UNIT")
            final_lines.append(f"{int(qty)}x → {pn} → {kit}")
    else:
        final_lines.append("(no final parts)")

    # ---------- compose ----------
    lines = []
    lines.append(f"Model: {model}  |  Serial: {serial}  |  Date: {dt_str}")
    lines.append(f"Due threshold: {threshold * 100:.1f}%  •  Basis: {life_basis.upper()}")
    lines.append("")

    if counters_lines:
        lines += counters_lines
        lines.append("")

    lines.append("───────────────────────────────────────────────────────────────")
    lines.append("Most-Due Items")
    lines.append("───────────────")
    if most_due_rows:
        lines += most_due_rows
    else:
        lines.append("  (none)")
        lines.append("")
    lines.append("")
    lines += final_lines
    lines.append("")
    lines.append("───────────────────────────────────────────────────────────────")
    lines.append("End of Report")
    lines.append("───────────────────────────────────────────────────────────────")

    return "\n".join(lines)


def generate_from_bytes(pm_pdf_bytes: bytes, threshold: float, life_basis: str, show_all: bool = False) -> str:
    """
    Orchestrates: parse -> rules -> selection -> format.
    `show_all=True` includes under-threshold PL items in 'Most-Due Items' without PN resolution.
    """
    report: PmReport = parse_pm_report(pm_pdf_bytes)
    selection = run_rules(report, threshold=threshold, life_basis=life_basis)
    return format_report(
        report=report,
        selection=selection,
        threshold=threshold,
        life_basis=life_basis,
        show_all=show_all,
    )
