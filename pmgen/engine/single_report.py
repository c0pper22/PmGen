from __future__ import annotations
from typing import Optional, Any, Iterable, List

from pmgen.engine.run_rules import run_rules
from pmgen.types import PmReport, PmItem
from pmgen.types import PmReport
from pmgen.parsing.parse_pm_report import parse_pm_report

from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
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

    out.sort(key=lambda x: (getattr(x, "life_used", None) or 0.0), reverse=True)
    return out


def format_report(
    *,
    report,
    selection,
    threshold: float,
    life_basis: str,
    show_all: bool = False,
    threshold_enabled: bool = True
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
    hdrs = getattr(report, "headers", {}) or {}
    model  = hdrs.get("model", "Unknown")
    serial = hdrs.get("serial", "Unknown")

    # Report date: use header string if present, else now
    dt_raw = hdrs.get("date")
    if isinstance(dt_raw, str) and dt_raw.strip():
        dt_str = dt_raw
    else:
        dt_str = datetime.now().strftime("%m-%d-%Y %H:%M")

    # ---------- counters ----------
    counters_lines: List[str] = []
    c = getattr(report, "counters", {}) or {}
    if isinstance(c, dict):
        parts = []
        if _get(c, "color") is not None:
            parts.append(f"Color: {_get(c, 'color')}")
        if _get(c, "black") is not None:
            parts.append(f"Black: {_get(c, 'black')}")
        if _get(c, "df") is not None:
            parts.append(f"DF: {_get(c, 'df')}")
        if _get(c, "total") is not None:
            parts.append(f"Total: {_get(c, 'total')}")
        if parts:
            counters_lines.append("Counters:")
            counters_lines.append("  " + "  ".join(parts))

    # ---------- due / not-due items for “Most-Due Items” ----------
    due_items = list(getattr(selection, "items", []) or [])

    # Pull under-threshold (not-due) items when show_all=True
    if show_all:
        combined = _collect_all_findings(selection, show_all=True)
    else:
        combined = due_items

    # Build the rows (sorted by life_used then conf)
    most_due_rows: List[str] = []
    for f in combined:
        canon = getattr(f, "canon", "—")
        pct   = _fmt_pct(getattr(f, "life_used", None))
        kit   = getattr(f, "kit_code", None) or "(N/A)"
        is_due = bool(getattr(f, "due", False))
        if is_due:
            most_due_rows.append(f"  • {canon} — {pct} → DUE")
            most_due_rows.append(f"      ↳ Unit: {kit}")
        else:
            most_due_rows.append(f"  • {canon} — {pct}")
            most_due_rows.append(f"      ↳ Unit: (N/A)")
        most_due_rows.append("")

    # ---------- final parts (grouped by kit → PN × qty) ----------
    final_lines: List[str] = []

    meta = getattr(selection, "meta", {}) or {}
    grouped = meta.get("selection_pn_grouped", {}) or {}
    flat    = meta.get("selection_pn", {}) or {}
    by_pn   = meta.get("kit_by_pn", {}) or {}
    due_src = meta.get("due_sources", {}) or {}

    over_100_kits    = set(due_src.get("over_100", []) or [])
    threshold_kits   = set(due_src.get("threshold", []) or [])
    threshold_only   = threshold_kits - over_100_kits

    over_rows: List[str] = []
    thr_rows: List[str] = []

    if grouped:
        for kit, pns in grouped.items():
            if kit in over_100_kits:
                for pn, qty in (pns or {}).items():
                    over_rows.append(f"{int(qty)}x → {pn} → {kit}")
            elif kit in threshold_only:
                for pn, qty in (pns or {}).items():
                    thr_rows.append(f"{int(qty)}x → {pn} → {kit}")
    elif flat:
        for pn, qty in flat.items():
            kit = by_pn.get(pn, "UNKNOWN-UNIT")
            if kit in over_100_kits:
                over_rows.append(f"{int(qty)}x → {pn} → {kit}")
            elif kit in threshold_only:
                thr_rows.append(f"{int(qty)}x → {pn} → {kit}")

    # Over-100% section
    final_lines.append("Final Parts — Over 100%")
    final_lines.append("───────────────────────────────────────────────────────────────")
    final_lines.append("(Qty → Part Number → Unit )")
    if over_rows:
        final_lines.extend(over_rows)
    else:
        final_lines.append("(none)")
    final_lines.append("")

    # Threshold-based section
    if thr_rows:
        final_lines.append("Final Parts — Threshold")
        final_lines.append("───────────────────────────────────────────────────────────────")
        final_lines.append("(Qty → Part Number → Unit )")
        if thr_rows:
            final_lines.extend(thr_rows)
        else:
            final_lines.append("(none)")
        final_lines.append("")

    # ---------- assemble full text report ----------
    lines: List[str] = []

    # Title + header
    lines.append("───────────────────────────────────────────────────────────────")
    lines.append(f"Model: {model}  |  Serial: {serial}  |  Date: {dt_str}")

    # Threshold line
    if threshold_enabled:
        thr_text = f"{threshold * 100:.1f}%"
    else:
        thr_text = "100.0%"
    lines.append(f"Due threshold: {thr_text}  •  Basis: {life_basis.upper()}")

    # Counters
    if counters_lines:
        lines.append("")
        lines.extend(counters_lines)

    # Most-due section
    lines.append("")
    lines.append("Highest Wear Items")
    lines.append("───────────────────────────────────────────────────────────────")
    if most_due_rows:
        lines.extend(most_due_rows)
    else:
        lines.append("(none)")
        lines.append("")
    lines.append("")

    # Final parts sections
    lines.extend(final_lines)

    # Footer
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


# ──────────────────────────────────────────────────────────────────────────────
# COMPACT DIVIDER: slimmer spacing to reduce vertical whitespace
# ──────────────────────────────────────────────────────────────────────────────
def _hline(thickness=1, color=colors.HexColor("#DDDDDD")):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceBefore=2, spaceAfter=2)


# ──────────────────────────────────────────────────────────────────────────────
# COMPACT TABLE BASE STYLE: smaller fonts & paddings
# ──────────────────────────────────────────────────────────────────────────────
def _tbl_style_base():
    return TableStyle(
        [
            ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3B82F6")),

            ("FONT", (0, 1), (-1, -1), "Helvetica"),
            ("FONTSIZE", (0, 1), (-1, -1), 9),

            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),

            # COMPACT paddings (defaults ~6; trimmed to 2)
            ("LEFTPADDING", (0, 0), (-1, -1), 2),
            ("RIGHTPADDING", (0, 0), (-1, -1), 2),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
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
    threshold_enabled: bool = True,
):
    """
    Renders a single parsed PM report into a colorized PDF.
    (Compact layout; tables allowed to split across pages)
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
    combined.sort(
        key=lambda x: (getattr(x, "life_used", None) or 0.0),
        reverse=True,
    )

    most_due = []
    for f in combined:
        canon = getattr(f, "canon", "—")
        pct = (getattr(f, "life_used", None) or 0.0) * 100.0
        kit = getattr(f, "kit_code", None) or "(N/A)"
        most_due.append([canon, f"{pct:.1f}%", "DUE" if getattr(f, "due", False) else "", kit])

    # Final parts
    meta = getattr(selection, "meta", {}) or {}
    grouped = meta.get("selection_pn_grouped", {}) or {}
    flat    = meta.get("selection_pn", {}) or {}
    by_pn   = meta.get("kit_by_pn", {}) or {}
    due_src = meta.get("due_sources", {}) or {}

    over_100_kits  = set(due_src.get("over_100", []) or [])
    threshold_kits = set(due_src.get("threshold", []) or [])
    threshold_only = threshold_kits - over_100_kits

    final_over: List[List[Any]] = []
    final_thr: List[List[Any]] = []

    if grouped:
        for unit, pns in grouped.items():
            if unit in over_100_kits:
                for pn, qty in (pns or {}).items():
                    final_over.append([int(qty), pn, unit])
            elif unit in threshold_only:
                for pn, qty in (pns or {}).items():
                    final_thr.append([int(qty), pn, unit])
    elif flat:
        for pn, qty in flat.items():
            unit = by_pn.get(pn, "UNKNOWN-UNIT")
            if unit in over_100_kits:
                final_over.append([int(qty), pn, unit])
            elif unit in threshold_only:
                final_thr.append([int(qty), pn, unit])

    # Build PDF
    if combined:
        best_used = max(
            (getattr(f, "life_used", None) or 0.0)
            for f in combined
        )
    else:
        best_used = 0.0

    best_used_pct = best_used * 100.0
    fname = f"{best_used_pct:.1f}_{serial}.pdf"

    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, fname)
    doc = SimpleDocTemplate(
        path,
        pagesize=LETTER,
        leftMargin=0.5 * inch,
        rightMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="H1", fontName="Helvetica-Bold", fontSize=14, leading=16, textColor=colors.HexColor("#111827"), spaceBefore=0, spaceAfter=2))
    styles.add(ParagraphStyle(name="Meta", fontName="Helvetica", fontSize=9, leading=10, textColor=colors.HexColor("#374151"), spaceBefore=0, spaceAfter=2))
    styles.add(ParagraphStyle(name="Section", fontName="Helvetica-Bold", fontSize=11, leading=12, textColor=colors.HexColor("#111827"), spaceBefore=4, spaceAfter=2))

    story = []
    story.append(Paragraph(f"Model: {model}  |  Serial: {serial}  |  Date: {dt_str}", styles["H1"]))
    story.append(_hline())
    if threshold_enabled:
        thr_text = f"{threshold*100:.1f}%"
    else:
        thr_text = "100.0%"
    story.append(Paragraph(f"Due threshold: {thr_text}  •  Basis: {life_basis.upper()}", styles["Meta"]))
    if parts:
        story.append(Paragraph("Counters: " + "  ".join(parts), styles["Meta"]))
    story.append(Spacer(1, 4))

    # Most-Due Items (ALLOW SPLIT)
    if most_due:
        data = [["Canon", "Life Used", "Status", "Unit"]] + most_due
        tbl = Table(data, colWidths=[2.8 * inch, 0.95 * inch, 0.8 * inch, 2.05 * inch])
        tbl.setStyle(_tbl_style_base())
        tbl.setStyle(TableStyle([("ALIGN", (1, 1), (1, -1), "RIGHT"),
                                 ("ALIGN", (2, 1), (2, -1), "CENTER")]))
        _zebra(tbl, len(data))
        for r_idx in range(1, len(data)):
            try:
                val = float(most_due[r_idx - 1][1].strip("%"))
                tbl.setStyle(TableStyle([("TEXTCOLOR", (1, r_idx), (1, r_idx), _pct_color(val))]))
            except Exception:
                pass
        tbl.splitByRow = 1
        tbl.repeatRows = 1
        story.append(tbl)
    else:
        story.append(Paragraph("(none)", styles["Meta"]))

    story.append(Spacer(1, 4))

    # Final Parts — Over 100% (ALLOW SPLIT)
    story.append(Paragraph("Final Parts — Over 100%", styles["Section"]))
    story.append(_hline())
    if final_over:
        data = [["Qty", "Part Number", "Unit"]] + [[str(q), pn, u] for q, pn, u in final_over]
        tbl = Table(data, colWidths=[0.6 * inch, 3.0 * inch, 3.0 * inch])
        tbl.setStyle(_tbl_style_base())
        tbl.setStyle(TableStyle([("ALIGN", (0, 1), (0, -1), "RIGHT")]))
        _zebra(tbl, len(data))
        tbl.splitByRow = 1
        tbl.repeatRows = 1
        story.append(KeepTogether(tbl))
    else:
        story.append(Paragraph("(none)", styles["Meta"]))

    story.append(Spacer(1, 4))

    # Final Parts — Threshold (ALLOW SPLIT)
    if final_thr:
        story.append(Paragraph("Final Parts — Threshold", styles["Section"]))
        story.append(_hline())
        if final_thr:
            data = [["Qty", "Part Number", "Unit"]] + [[str(q), pn, u] for q, pn, u in final_thr]
            tbl = Table(data, colWidths=[0.6 * inch, 3.0 * inch, 3.0 * inch])
            tbl.setStyle(_tbl_style_base())
            tbl.setStyle(TableStyle([("ALIGN", (0, 1), (0, -1), "RIGHT")]))
            _zebra(tbl, len(data))
            tbl.splitByRow = 1
            tbl.repeatRows = 1
            story.append(KeepTogether(tbl))
        else:
            story.append(Paragraph("(none)", styles["Meta"]))

    doc.build(story)


def generate_from_bytes(
    pm_pdf_bytes: bytes,
    threshold: float,
    life_basis: str,
    show_all: bool = False,
    threshold_enabled: bool = True,
) -> str:
    report: PmReport = parse_pm_report(pm_pdf_bytes)
    selection = run_rules(
        report,
        threshold=threshold,
        life_basis=life_basis,
        threshold_enabled=threshold_enabled,
    )
    return format_report(
        report=report,
        selection=selection,
        threshold=threshold,
        life_basis=life_basis,
        show_all=show_all,
        threshold_enabled=threshold_enabled,
    )