from __future__ import annotations
from typing import Optional, Any, Iterable, List

from pmgen.engine.run_rules import run_rules
from pmgen.types import PmReport, PmItem
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
    """

    # ---------- helpers ----------
    def _fmt_pct(p):
        if p is None: return "—"
        try: return f"{(float(p) * 100):.1f}%"
        except Exception: return "—"

    def _get(d, key, default=None):
        try: return d.get(key, default)
        except Exception: return default

    # ---------- header line ----------
    hdrs = getattr(report, "headers", {}) or {}
    model  = hdrs.get("model", "Unknown")
    serial = hdrs.get("serial", "Unknown")

    dt_raw = hdrs.get("date")
    dt_str = dt_raw if isinstance(dt_raw, str) and dt_raw.strip() else datetime.now().strftime("%m-%d-%Y %H:%M")

    # ---------- counters ----------
    counters_lines: List[str] = []
    c = getattr(report, "counters", {}) or {}
    if isinstance(c, dict):
        parts = []
        if _get(c, "color") is not None: parts.append(f"Color: {_get(c, 'color')}")
        if _get(c, "black") is not None: parts.append(f"Black: {_get(c, 'black')}")
        if _get(c, "df") is not None: parts.append(f"DF: {_get(c, 'df')}")
        if _get(c, "total") is not None: parts.append(f"Total: {_get(c, 'total')}")
        if parts:
            counters_lines.append("Counters:")
            counters_lines.append("  " + "  ".join(parts))

    # ---------- due / not-due items ----------
    due_items = list(getattr(selection, "items", []) or [])
    combined = _collect_all_findings(selection, show_all=True) if show_all else due_items

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

    # ---------- final parts logic ----------
    final_lines: List[str] = []

    meta = getattr(selection, "meta", {}) or {}
    grouped = meta.get("selection_pn_grouped", {}) or {}
    flat    = meta.get("selection_pn", {}) or {}
    by_pn   = meta.get("kit_by_pn", {}) or {}
    due_src = meta.get("due_sources", {}) or {}
    inv_matches = meta.get("inventory_matches", []) or []
    inv_missing = meta.get("inventory_missing", []) or []

    over_100_kits    = set(due_src.get("over_100", []) or [])
    threshold_kits   = set(due_src.get("threshold", []) or [])
    threshold_only   = threshold_kits - over_100_kits

    over_rows: List[str] = []
    thr_rows: List[str] = []

    if grouped:
        for kit, pns in grouped.items():
            if kit in over_100_kits:
                for pn, qty in (pns or {}).items(): over_rows.append(f"{int(qty)}x → {pn} → {kit}")
            elif kit in threshold_only:
                for pn, qty in (pns or {}).items(): thr_rows.append(f"{int(qty)}x → {pn} → {kit}")
    elif flat:
        for pn, qty in flat.items():
            kit = by_pn.get(pn, "UNKNOWN-UNIT")
            if kit in over_100_kits: over_rows.append(f"{int(qty)}x → {pn} → {kit}")
            elif kit in threshold_only: thr_rows.append(f"{int(qty)}x → {pn} → {kit}")

    # Over-100% section
    final_lines.append("Final Parts — Over 100%")
    final_lines.append("───────────────────────────────────────────────────────────────")
    final_lines.append("(Qty → Part Number → Unit )")
    final_lines.extend(over_rows if over_rows else ["(none)"])
    final_lines.append("")

    # Threshold-based section
    if thr_rows:
        final_lines.append("Final Parts — Threshold")
        final_lines.append("───────────────────────────────────────────────────────────────")
        final_lines.append("(Qty → Part Number → Unit )")
        final_lines.extend(thr_rows)
        final_lines.append("")

    # --- INVENTORY: MATCHES ---
    inv_lines = []
    if inv_matches:
        inv_lines.append("Inventory Matches (In Stock)")
        inv_lines.append("───────────────────────────────────────────────────────────────")
        inv_lines.append("(Matched Code → Needed → In Stock)")
        for m in inv_matches:
            code = m.get("code")
            needed = int(m.get("needed", 0))
            stock = int(m.get("in_stock", 0))
            inv_lines.append(f"  ✓ {code} : Need {needed} | Have {stock}")
        inv_lines.append("")

    # --- INVENTORY: MISSING (ORDER LIST) ---
    miss_lines = []
    if inv_missing:
        miss_lines.append("Items to Order (Missing from Stock)")
        miss_lines.append("───────────────────────────────────────────────────────────────")
        miss_lines.append("(Code → Qty to Order)")
        for m in inv_missing:
            code = m.get("code")
            order_qty = int(m.get("ordering", 0))
            note = m.get("note", "")
            suffix = f" {note}" if note else ""
            miss_lines.append(f"  ! {code} : {order_qty}{suffix}")
        miss_lines.append("")

    # ---------- assemble full text report ----------
    lines: List[str] = []
    lines.append("───────────────────────────────────────────────────────────────")
    lines.append(f"Model: {model}  |  Serial: {serial}  |  Date: {dt_str}")

    if threshold_enabled: thr_text = f"{threshold * 100:.1f}%"
    else: thr_text = "100.0%"
    lines.append(f"Due threshold: {thr_text}  •  Basis: {life_basis.upper()}")

    if counters_lines:
        lines.append("")
        lines.extend(counters_lines)

    lines.append("")
    lines.append("Highest Wear Items")
    lines.append("───────────────────────────────────────────────────────────────")
    lines.extend(most_due_rows if most_due_rows else ["(none)", ""])
    
    lines.append("")
    lines.extend(final_lines)

    if inv_lines:
        lines.extend(inv_lines)
    
    # Add Missing section
    if miss_lines:
        lines.extend(miss_lines)

    lines.append("")
    lines.append("───────────────────────────────────────────────────────────────")
    lines.append("End of Report")
    lines.append("───────────────────────────────────────────────────────────────")

    return "\n".join(lines)


def _pct_color(v) -> colors.Color:
    if v < 84.0: return colors.darkgray
    if v < 100.0: return colors.orange
    return colors.red

def _hline(thickness=1, color=colors.HexColor("#DDDDDD")):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceBefore=2, spaceAfter=2)

def _tbl_style_base():
    return TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 9),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3B82F6")),
        ("FONT", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
        ("LEFTPADDING", (0, 0), (-1, -1), 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), 2),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ])

def _zebra(tbl, rows):
    for r in range(1, rows):
        if r % 2 == 0:
            tbl.setStyle(TableStyle([("BACKGROUND", (0, r), (-1, r), colors.HexColor("#F8FAFC"))]))

ef create_pdf_report(
    report, 
    selection, 
    threshold: float, 
    life_basis: str, 
    show_all: bool, 
    out_dir: str, 
    threshold_enabled: bool = True
):
    """
    Generates the individual PDF report for a single machine.
    """
    headers = report.headers or {}
    serial = headers.get("serial", "Unknown")
    model = headers.get("model", "Unknown")
    date_str = headers.get("date", "Unknown")

    filename = f"{threshold}_{serial}.pdf" 
    # Or keep your naming convention: f"{model}_{serial}.pdf" etc.
    # We'll stick to a safe default:
    safe_model = "".join([c for c in model if c.isalnum() or c in (' ','-','_')]).strip()
    filename = f"{safe_model}_{serial}.pdf"

    filepath = os.path.join(out_dir, filename)

    doc = SimpleDocTemplate(
        filepath, 
        pagesize=LETTER,
        rightMargin=0.5*inch, leftMargin=0.5*inch,
        topMargin=0.5*inch, bottomMargin=0.5*inch
    )

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='Small', parent=styles['Normal'], fontSize=9, leading=11))
    styles.add(ParagraphStyle(name='HeaderInfo', parent=styles['Normal'], fontSize=10, leading=12, spaceAfter=6))
    styles.add(ParagraphStyle(name='MissHeader', parent=styles['Normal'], fontSize=10, fontName='Helvetica-Bold', textColor=colors.red))

    story = []

    # --- HEADER ---
    story.append(Paragraph(f"<b>PM Report:</b> {model}", styles["Title"]))
    info_txt = f"<b>Serial:</b> {serial} &nbsp;|&nbsp; <b>Date:</b> {date_str}"
    story.append(Paragraph(info_txt, styles["HeaderInfo"]))

    thr_txt = f"{threshold}%" if threshold_enabled else "Disabled"
    mode_txt = f"<b>Threshold:</b> {thr_txt} &nbsp;|&nbsp; <b>Basis:</b> {life_basis}"
    if show_all:
        mode_txt += " &nbsp;|&nbsp; <b>(Show All Active)</b>"
    story.append(Paragraph(mode_txt, styles["HeaderInfo"]))

    story.append(Spacer(1, 0.2 * inch))

    # --- GET ITEMS ---
    # THIS IS THE KEY FIX: Using the collector helper logic
    items_to_show = _collect_all_findings(selection, show_all)

    # Sort items: Due items first, then by usage descending
    def sort_key(x):
        is_due = getattr(x, "due", False)
        # Use helper to get life_used safely
        used = getattr(x, "life_used", 0.0)
        if used is None: used = 0.0
        return (not is_due, -float(used)) # True(not due) comes after False(due), then desc usage
    
    items_to_show.sort(key=sort_key)

    # --- BUILD TABLE ---
    if not items_to_show:
        story.append(Paragraph("(No items to display)", styles["Normal"]))
    else:
        # Columns: Qty | Part Number | Description | Life Used | Status
        table_data = [["Qty", "Part Number", "Description", "Life", "Status"]]
        
        row_styles = []
        
        for i, item in enumerate(items_to_show):
            # Extract basic data
            qty = getattr(item, "qty", 1)
            pn = getattr(item, "kit_code", "") or getattr(item, "part_number", "") or "N/A"
            desc = getattr(item, "description", "") or getattr(item, "desc", "") or ""
            
            # Life Percentage
            used = getattr(item, "life_used", 0.0)
            if used is None: used = 0.0
            pct_str = f"{used*100:.1f}%"
            
            # Status
            is_due = getattr(item, "due", False)
            status = "DUE" if is_due else "OK"
            
            # Check Threshold for "OK" items (to see if they are close)
            # If show_all is on, we might want to highlight items that are 0% differently from 40%
            
            table_data.append([str(qty), pn, desc, pct_str, status])

            # Styling the row
            row_idx = i + 1
            if is_due:
                # Bold red for due items
                row_styles.append(('FONTNAME', (0, row_idx), (-1, row_idx), 'Helvetica-Bold'))
                row_styles.append(('TEXTCOLOR', (3, row_idx), (4, row_idx), colors.red))
            else:
                # Grey text for "Show All" items that aren't due
                row_styles.append(('TEXTCOLOR', (0, row_idx), (-1, row_idx), colors.darkgrey))

        # Create Table
        t = Table(table_data, colWidths=[0.6*inch, 1.5*inch, 3.2*inch, 0.8*inch, 0.8*inch])
        
        # Base Style
        t_style = TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('ALIGN', (0, 0), (0, -1), 'CENTER'), # Qty center
            ('ALIGN', (3, 0), (-1, -1), 'CENTER'), # Life/Status center
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ])
        
        # Add dynamic row styles
        for s in row_styles:
            t_style.add(*s)
            
        t.setStyle(t_style)
        story.append(t)

    # --- INVENTORY MISSING SECTION ---
    # (If your rules populated the inventory missing meta)
    meta = getattr(selection, "meta", {}) or {}
    inv_missing = meta.get("inventory_missing")
    
    if inv_missing:
        story.append(Spacer(1, 0.25 * inch))
        story.append(Paragraph("Inventory Missing / To Order", styles["MissHeader"]))
        
        m_data = [["Code", "Needed", "Order Qty"]]
        for m in inv_missing:
            m_data.append([
                m.get("code", "?"), 
                str(m.get("needed", 0)), 
                str(m.get("ordering", 0))
            ])
            
        m_table = Table(m_data, colWidths=[3.0*inch, 1.0*inch, 1.0*inch])
        m_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#FCA5A5")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(m_table)

    doc.build(story)
    return filepath


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