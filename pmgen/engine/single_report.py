from __future__ import annotations
from typing import Optional, Any, Iterable, List
from pmgen.parsing import ParsePmReport
from pmgen.engine.run_rules import run_rules
from pmgen.types import PmReport as PmReportType, PmItem as PmItemType
from pmgen.types import PmReport
from pmgen.engine.run_rules import run_rules
from pmgen.parsing.parse_pm_report import parse_pm_report
from datetime import datetime
from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)
from reportlab.platypus.flowables import KeepTogether, HRFlowable
from datetime import datetime
import os

def _collect_all_findings(selection, show_all: bool):
    due = list(getattr(selection, "items", []) or [])
    if not show_all:
        return due

    meta = getattr(selection, "meta", {}) or {}
    pools = [
        getattr(selection, "not_due", None),
        getattr(selection, "all_items", None),
        meta.get("all"),
        meta.get("all_items"),
        meta.get("watch"),
    ]

    extra = []
    for p in pools:
        if p:
            extra.extend(p)

    def _key(f):
        return (getattr(f, "canon", None), getattr(f, "kit_code", None))

    seen = {_key(f) for f in due}
    out = list(due)
    for f in extra:
        k = _key(f)
        if k not in seen:
            out.append(f)
            seen.add(k)

    out.sort(key=lambda x: (getattr(x, "life_used", 0.0), getattr(x, "conf", 0.0)), reverse=True)
    return out

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
        combined = _collect_all_findings(selection, show_all)
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

def _pct_color(v) -> colors.Color:
    if v < 84.0:
        return colors.darkgray
    
    if v < 100.0:
        return colors.orange
    
    if v >= 100:
        return colors.red

def _hline(thickness=1, color=colors.HexColor("#DDDDDD")):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceBefore=4, spaceAfter=6)

def _tbl_style_base():
    return TableStyle(
        [
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3B82F6")),
            ("FONT", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ]
    )

def _zebra(tbl, rows):
    for r in range(1, rows):
        if r % 2 == 0:
            tbl.setStyle(TableStyle([("BACKGROUND", (0, r), (-1, r), colors.HexColor("#F8FAFC"))]))

def create_pdf_report(
    *,
    report,
    selection,
    threshold: float,
    life_basis: str,
    show_all: bool = False,
    out_dir: str = ".",
):
    """
    Renders a single parsed PM report into a colorized PDF.
    (Same interface as your original format_report)
    """
    hdrs = getattr(report, "headers", {}) or {}
    model = hdrs.get("model", "Unknown")
    serial = hdrs.get("serial", "Unknown")
    dt_raw = hdrs.get("date")
    dt_str = dt_raw if isinstance(dt_raw, str) and dt_raw.strip() else datetime.now().strftime("%m-%d-%Y %H:%M")

    # Counters
    c = getattr(report, "counters", {}) or {}
    parts = [f"{k.title()}: {v}" for k, v in c.items() if v is not None]

    # Due items
    due_items = list(getattr(selection, "items", []) or [])
    not_due_items = []
    if show_all:
        if hasattr(selection, "not_due") and selection.not_due:
            not_due_items = list(selection.not_due)
        else:
            meta = getattr(selection, "meta", {}) or {}
            all_items = meta.get("all", []) or []
            not_due_items = [f for f in all_items if not getattr(f, "due", False)]

    combined = due_items + not_due_items if show_all else due_items
    combined.sort(key=lambda x: getattr(x, "life_used", 0.0), reverse=True)

    most_due = []
    for f in combined:
        canon = getattr(f, "canon", "—")
        pct = getattr(f, "life_used", 0.0) * 100
        kit = getattr(f, "kit_code", None) or "(N/A)"
        most_due.append([canon, f"{pct:.1f}%", "DUE" if getattr(f, "due", False) else "", kit])

    # Final parts
    meta = getattr(selection, "meta", {}) or {}
    grouped = meta.get("selection_pn_grouped", {}) or {}
    flat = meta.get("selection_pn", {}) or {}
    by_pn = meta.get("kit_by_pn", {}) or {}

    final_parts = []
    if grouped:
        for unit, pns in grouped.items():
            for pn, qty in (pns or {}).items():
                final_parts.append([int(qty), pn, unit])
    elif flat:
        for pn, qty in flat.items():
            final_parts.append([int(qty), pn, by_pn.get(pn, "UNKNOWN-UNIT")])

    # Build PDF
    best_used = max(
        [getattr(f, "life_used", 0.0) for f in combined],
    )
    best_used_pct = best_used * 100.0
    fname = f"{best_used_pct:.1f}_{serial}.pdf"

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, fname)
    doc = SimpleDocTemplate(
        path,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="H1", fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=colors.HexColor("#111827")))
    styles.add(ParagraphStyle(name="Meta", fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#374151")))
    styles.add(ParagraphStyle(name="Section", fontName="Helvetica-Bold", fontSize=12, leading=14, textColor=colors.HexColor("#111827"), spaceBefore=10))

    story = []
    story.append(Paragraph(f"Model: {model}  |  Serial: {serial}  |  Date: {dt_str}", styles["H1"]))
    story.append(_hline())
    story.append(Paragraph(f"Due threshold: {threshold*100:.1f}%  •  Basis: {life_basis.upper()}", styles["Meta"]))
    if parts:
        story.append(Paragraph("Counters: " + "  ".join(parts), styles["Meta"]))
    story.append(Spacer(1, 0.15 * inch))

    # Most-Due Items
    story.append(Paragraph("Most-Due Items", styles["Section"]))
    story.append(_hline())
    if most_due:
        data = [["Canon", "Life Used", "Status", "Catalog"]] + most_due
        tbl = Table(data, colWidths=[2.9 * inch, 1.0 * inch, 0.9 * inch, 2.1 * inch])
        tbl.setStyle(_tbl_style_base())
        tbl.setStyle(TableStyle([("ALIGN", (1, 1), (1, -1), "RIGHT"), ("ALIGN", (2, 1), (2, -1), "CENTER")]))
        _zebra(tbl, len(data))
        for r_idx in range(1, len(data)):
            try:
                val = float(most_due[r_idx - 1][1].strip("%"))
                tbl.setStyle(TableStyle([("TEXTCOLOR", (1, r_idx), (1, r_idx), _pct_color(val))]))
            except Exception:
                pass
        tbl.splitByRow = 1
        tbl.repeatRows = 1
        story.append(KeepTogether(tbl))
    else:
        story.append(Paragraph("(none)", styles["Meta"]))
    story.append(Spacer(1, 0.15 * inch))

    # Final Parts
    story.append(Paragraph("Final Parts", styles["Section"]))
    story.append(_hline())
    if final_parts:
        data = [["Qty", "Part Number", "Unit"]] + [[str(q), pn, u] for q, pn, u in final_parts]
        tbl = Table(data, colWidths=[0.7 * inch, 3.0 * inch, 3.05 * inch])
        tbl.setStyle(_tbl_style_base())
        tbl.setStyle(TableStyle([("ALIGN", (0, 1), (0, -1), "RIGHT")]))
        _zebra(tbl, len(data))
        tbl.splitByRow = 1
        tbl.repeatRows = 1
        story.append(KeepTogether(tbl) if len(data) <= 28 else tbl)
    else:
        story.append(Paragraph("(no final parts)", styles["Meta"]))
    story.append(Spacer(1, 0.15 * inch))

    doc.build(story)

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
