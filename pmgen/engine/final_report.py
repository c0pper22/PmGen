from __future__ import annotations
from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)
from reportlab.platypus.flowables import KeepTogether, HRFlowable
from reportlab.platypus.doctemplate import LayoutError
from datetime import datetime
import os


def _pct_color(v) -> colors.Color:
    p = v
    if p < 84.0: return colors.darkgray
    elif p < 100.0: return colors.orange
    else: return colors.red

def _hline(thickness=1, color=colors.HexColor("#DDDDDD")):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceBefore=4, spaceAfter=6)

def _make_parts_table(rows, col_names=("Qty", "Part Number", "Unit")):
    data = [list(col_names)]
    for qty, pn, unit in rows:
        data.append([str(int(qty)), pn, unit])

    tbl = Table(data, colWidths=[0.7 * inch, 3.0 * inch, 3.05 * inch], hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3B82F6")), 
        ("FONT", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (0, 1), (0, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
    ]))
    for r in range(1, len(data)):
        if r % 2 == 0:
            tbl.setStyle(TableStyle([("BACKGROUND", (0, r), (-1, r), colors.HexColor("#F8FAFC"))]))

    tbl.splitByRow = 1
    tbl.repeatRows = 1
    return tbl

def _make_inv_table(rows):
    """Specific table style for inventory matches (Green headers)"""
    data = [["Matched Item", "Needed", "In Stock"]]
    for m in rows:
        data.append([m["code"], str(m["needed"]), str(int(m["in_stock"]))])

    tbl = Table(data, colWidths=[3.0 * inch, 1.5 * inch, 2.25 * inch], hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#22C55E")), # Green Header
        ("FONT", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
    ]))
    for r in range(1, len(data)):
        if r % 2 == 0:
            tbl.setStyle(TableStyle([("BACKGROUND", (0, r), (-1, r), colors.HexColor("#F0FDF4"))])) # Light Green Stripe

    tbl.splitByRow = 1
    tbl.repeatRows = 1
    return tbl

def _make_missing_table(rows):
    """Specific table style for Missing items (Red headers)"""
    data = [["Item Code", "Qty to Order"]]
    for m in rows:
        note = m.get("note", "")
        qty_str = str(int(m["ordering"]))
        if note: qty_str += f" ({note})"
        data.append([m["code"], qty_str])

    tbl = Table(data, colWidths=[4.5 * inch, 2.25 * inch], hAlign="LEFT")
    tbl.setStyle(TableStyle([
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EF4444")), # Red Header
        ("FONT", (0, 1), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 1), (-1, -1), 9),
        ("ALIGN", (1, 1), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
    ]))
    for r in range(1, len(data)):
        if r % 2 == 0:
            tbl.setStyle(TableStyle([("BACKGROUND", (0, r), (-1, r), colors.HexColor("#FEF2F2"))])) # Light Red Stripe

    tbl.splitByRow = 1
    tbl.repeatRows = 1
    return tbl

def write_final_summary_pdf(
    *, out_dir: str, results: list, top: list, thr: float, basis: str,
    filename: str = "Final_Summary.pdf", threshold_enabled: bool = True
):
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)

    doc = SimpleDocTemplate(path, pagesize=LETTER, leftMargin=0.75 * inch, rightMargin=0.75 * inch, topMargin=0.75 * inch, bottomMargin=0.75 * inch, title="Bulk Final Summary", author="PmGen")

    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=16, leading=20, textColor=colors.HexColor("#111827"), spaceAfter=8))
    styles.add(ParagraphStyle(name="Meta", parent=styles["BodyText"], fontName="Helvetica", fontSize=9, textColor=colors.HexColor("#374151"), spaceAfter=3))
    styles.add(ParagraphStyle(name="Section", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=14, textColor=colors.HexColor("#111827"), spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="SerialLine", parent=styles["BodyText"], fontName="Helvetica", fontSize=10, leading=12, textColor=colors.HexColor("#111827"), spaceBefore=4, spaceAfter=2))
    styles.add(ParagraphStyle(name="Muted", parent=styles["BodyText"], fontName="Helvetica-Oblique", fontSize=9, textColor=colors.HexColor("#6B7280"), spaceAfter=6))
    
    # Styles for Inv/Missing headers
    styles.add(ParagraphStyle(name="InvHeader", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=14, textColor=colors.HexColor("#166534"), spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle(name="MissHeader", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=14, textColor=colors.HexColor("#DC2626"), spaceBefore=10, spaceAfter=6))

    story = []

    story.append(Paragraph("Bulk Final Summary", styles["H1"]))
    story.append(_hline())

    successful = len([r for r in results if r.get("ok", True)])
    thr_str = f"{thr*100:.1f}%" if threshold_enabled else "Off (only >100% due)"
    meta_lines = [
        f"Threshold: <b>{thr_str}</b> • Basis: <b>{basis.upper()}</b>",
        f"Selected top <b>{len(top)}</b> of <b>{successful}</b> successful (from <b>{len(results)}</b> attempts).",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    for ml in meta_lines: story.append(Paragraph(ml, styles["Meta"]))
    story.append(Spacer(1, 0.15 * inch))

    total_over_upn = {}
    total_thr_upn = {}

    for r in top:
        serial = r.get("serial", "UNKNOWN")
        model = r.get("model", "UNKNOWN MODEL")
        best_used = r.get("best_used", 0.0) * 100

        c = _pct_color(best_used)
        hexcolor = f"#{int(c.red*255):02X}{int(c.green*255):02X}{int(c.blue*255):02X}"
        serial_line = f"<b>{serial}</b> — best used <font color='{hexcolor}'>{best_used:.1f}%</font> — {model}"
        story.append(Paragraph(serial_line, styles["SerialLine"]))

        grouped   = r.get("grouped") or {}
        flat      = r.get("flat") or {}
        kit_by_pn = r.get("kit_by_pn") or {}
        due_src   = r.get("due_sources") or {}
        inv_matches = r.get("inventory_matches") or []
        inv_missing = r.get("inventory_missing") or [] # <--- NEW

        over_100_kits  = set((due_src.get("over_100") or []))
        threshold_kits = set((due_src.get("threshold") or []))
        threshold_only = threshold_kits - over_100_kits

        rows_over: list = []
        rows_thr: list = []

        if grouped:
            for unit, pnmap in grouped.items():
                for pn, qty in (pnmap or {}).items():
                    unit_name = unit or "UNKNOWN-UNIT"
                    q_int = int(qty)
                    row = [q_int, pn, unit_name]
                    if unit in over_100_kits:
                        total_over_upn[(unit_name, pn)] = total_over_upn.get((unit_name, pn), 0) + q_int
                        rows_over.append(row)
                    elif unit in threshold_only:
                        total_thr_upn[(unit_name, pn)] = total_thr_upn.get((unit_name, pn), 0) + q_int
                        rows_thr.append(row)
        else:
            if not flat:
                story.append(Paragraph("(no final parts)", styles["Muted"]))
            else:
                for pn, qty in flat.items():
                    unit = kit_by_pn.get(pn, "UNKNOWN-UNIT")
                    q_int = int(qty)
                    row = [q_int, pn, unit]
                    if unit in over_100_kits:
                        total_over_upn[(unit, pn)] = total_over_upn.get((unit, pn), 0) + q_int
                        rows_over.append(row)
                    elif unit in threshold_only:
                        total_thr_upn[(unit, pn)] = total_thr_upn.get((unit, pn), 0) + q_int
                        rows_thr.append(row)

        # Over-100 table
        story.append(Paragraph("Final Parts — Over 100%", styles["Section"]))
        story.append(_hline())
        if rows_over:
            rows_over.sort(key=lambda x: (x[2], x[1]))
            tbl_over = _make_parts_table(rows_over)
            try: story.append(KeepTogether(tbl_over))
            except LayoutError: story.append(tbl_over)
        else: story.append(Paragraph("(none)", styles["Muted"]))
        story.append(Spacer(1, 0.10 * inch))

        # Threshold table
        story.append(Paragraph("Final Parts — Threshold", styles["Section"]))
        story.append(_hline())
        if rows_thr:
            rows_thr.sort(key=lambda x: (x[2], x[1]))
            tbl_thr = _make_parts_table(rows_thr)
            try: story.append(KeepTogether(tbl_thr))
            except LayoutError: story.append(tbl_thr)
        else: story.append(Paragraph("(none)", styles["Muted"]))
        
        # --- NEW: INVENTORY MATCHES (SERIAL LEVEL) ---
        if inv_matches:
            story.append(Spacer(1, 0.10 * inch))
            story.append(Paragraph("Inventory Matches (In Stock)", styles["InvHeader"]))
            story.append(_hline(color=colors.HexColor("#86EFAC")))
            
            inv_tbl = _make_inv_table(inv_matches)
            try: story.append(KeepTogether(inv_tbl))
            except LayoutError: story.append(inv_tbl)
            
        # --- NEW: MISSING ITEMS (SERIAL LEVEL) ---
        if inv_missing:
            story.append(Spacer(1, 0.10 * inch))
            story.append(Paragraph("Items to Order (Missing from Stock)", styles["MissHeader"]))
            story.append(_hline(color=colors.HexColor("#FCA5A5")))
            
            miss_tbl = _make_missing_table(inv_missing)
            try: story.append(KeepTogether(miss_tbl))
            except LayoutError: story.append(miss_tbl)

        story.append(Spacer(1, 0.15 * inch))

    # Consolidated parts
    story.append(Paragraph("All Serials — Consolidated Parts — Over 100%", styles["Section"]))
    story.append(_hline())
    if total_over_upn:
        rows = []
        for (unit, pn), qty in sorted(total_over_upn.items(), key=lambda k: (k[0][0], k[0][1])):
            rows.append([qty, pn, unit])
        story.append(_make_parts_table(rows))
    else: story.append(Paragraph("(none)", styles["Muted"]))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph("All Serials — Consolidated Parts — Threshold", styles["Section"]))
    story.append(_hline())
    if total_thr_upn:
        rows = []
        for (unit, pn), qty in sorted(total_thr_upn.items(), key=lambda k: (k[0][0], k[0][1])):
            rows.append([qty, pn, unit])
        story.append(_make_parts_table(rows))
    else: story.append(Paragraph("(none)", styles["Muted"]))
    story.append(Spacer(1, 0.2 * inch))

    doc.build(story)
    return path