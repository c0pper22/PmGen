from __future__ import annotations
import os
from datetime import datetime

# ReportLab Imports
from reportlab.lib.pagesizes import LETTER
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
)
from reportlab.platypus.flowables import KeepTogether, HRFlowable
from reportlab.platypus.doctemplate import LayoutError

# New Imports for Inventory
try:
    import pandas as pd
    from PyQt6.QtCore import QStandardPaths
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

def _pct_color(v) -> colors.Color:
    p = v
    if p < 84.0: return colors.darkgray
    elif p < 100.0: return colors.orange
    else: return colors.red

def _hline(thickness=1, color=colors.HexColor("#DDDDDD")):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceBefore=4, spaceAfter=6)

def _load_inventory_map():
    """
    Loads inventory from cache and returns a dict: {(PartNumber, UnitName): Quantity}
    Note: The grouping key order here is (Part Number, Unit Name)
    """
    if not HAS_DEPS: return {}
    try:
        base_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        path = os.path.join(base_dir, "inventory_cache.csv")
        if not os.path.exists(path): return {}
        
        df = pd.read_csv(path)
        # Normalization matches inventory.py
        if "Part Number" in df.columns:
            df["Part Number"] = df["Part Number"].astype(str).str.strip().str.upper()
        if "Unit Name" in df.columns:
            df["Unit Name"] = df["Unit Name"].astype(str).str.strip().str.upper()
        if "Quantity" in df.columns:
            df["Quantity"] = pd.to_numeric(df["Quantity"], errors='coerce').fillna(0)
                
        return df.groupby(["Part Number", "Unit Name"])["Quantity"].sum().to_dict()
    
    except Exception:
        return {}

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

def _make_inventory_check_table(rows):
    """
    Rows: [Need, Have, Order, Part, Unit, ColorCode]
    ColorCode: 0=Red, 1=Yellow, 2=Green
    """
    data = [["Needed", "Have", "Order", "Part Number", "Unit"]]
    
    # Base styles
    style_cmds = [
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#111827")), 
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E5E7EB")), # Gray Header
        ("ALIGN", (0, 0), (2, -1), "CENTER"), # Center numbers
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#9CA3AF")),
        ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#D1D5DB")),
    ]
    
    for i, r in enumerate(rows):
        # r = [need, have, order, pn, unit, color_code]
        row_data = [str(r[0]), str(r[1]), str(r[2]), r[3], r[4]]
        data.append(row_data)
        
        c_code = r[5]
        if c_code == 0:   # Red (0 stock)
             bg = colors.HexColor("#FECACA") 
        elif c_code == 1: # Yellow (partial)
             bg = colors.HexColor("#FEF3C7") 
        else:             # Green (full)
             bg = colors.HexColor("#DCFCE7") 
             
        # i + 1 because row 0 is header
        style_cmds.append(('BACKGROUND', (0, i+1), (-1, i+1), bg))

    tbl = Table(data, colWidths=[0.8*inch, 0.8*inch, 0.8*inch, 2.8*inch, 2.3*inch], hAlign="LEFT")
    tbl.setStyle(TableStyle(style_cmds))
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

    # --- 1. PRE-CALCULATION ---
    
    total_over_upn = {}
    total_thr_upn = {}
    
    individual_serials_story = [] 

    for r in top:
        serial = r.get("serial", "UNKNOWN")
        model = r.get("model", "UNKNOWN MODEL")
        best_used = r.get("best_used", 0.0) * 100

        c = _pct_color(best_used)
        hexcolor = f"#{int(c.red*255):02X}{int(c.green*255):02X}{int(c.blue*255):02X}"
        serial_line = f"<b>{serial}</b> — best used <font color='{hexcolor}'>{best_used:.1f}%</font> — {model}"
        individual_serials_story.append(Paragraph(serial_line, styles["SerialLine"]))

        grouped   = r.get("grouped") or {}
        flat      = r.get("flat") or {}
        kit_by_pn = r.get("kit_by_pn") or {}
        due_src   = r.get("due_sources") or {}

        over_100_kits  = set((due_src.get("over_100") or []))
        threshold_kits = set((due_src.get("threshold") or []))
        if not threshold_enabled:
            threshold_kits = set()
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
                individual_serials_story.append(Paragraph("(no final parts)", styles["Muted"]))
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

        individual_serials_story.append(Paragraph("Final Parts — Over 100%", styles["Section"]))
        individual_serials_story.append(_hline())
        if rows_over:
            rows_over.sort(key=lambda x: (x[2], x[1]))
            tbl_over = _make_parts_table(rows_over)
            # FIX: KeepTogether expects a LIST of flowables, not a single Table object
            try: individual_serials_story.append(KeepTogether([tbl_over]))
            except LayoutError: individual_serials_story.append(tbl_over)
        else: individual_serials_story.append(Paragraph("(none)", styles["Muted"]))
        individual_serials_story.append(Spacer(1, 0.10 * inch))

        individual_serials_story.append(Paragraph(f"Final Parts — Threshold - {thr*100:.1f}%", styles["Section"]))
        individual_serials_story.append(_hline())
        if rows_thr:
            rows_thr.sort(key=lambda x: (x[2], x[1]))
            tbl_thr = _make_parts_table(rows_thr)
            # FIX: KeepTogether expects a LIST of flowables
            try: individual_serials_story.append(KeepTogether([tbl_thr]))
            except LayoutError: individual_serials_story.append(tbl_thr)
        else: individual_serials_story.append(Paragraph("(none)", styles["Muted"]))
        
        individual_serials_story.append(Spacer(1, 0.25 * inch))

    # --- 2. BUILD THE FINAL PDF STORY ---
    story = []

    # A. Header
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

    # B. INVENTORY CHECK (Combined & Factored)
    inv_map = _load_inventory_map()
    
    # Merge Over 100 and Threshold needs
    combined_needed = total_over_upn.copy()
    for k, v in total_thr_upn.items():
        combined_needed[k] = combined_needed.get(k, 0) + v
#--------------- This Logic is correct do not change this please ------------------
    inv_rows = []
    if combined_needed:
        for unit, needed_qty in sorted(combined_needed.items(), key=lambda k: (k[0][0], k[0][1])):
            have_qty = 0
            for inv_key, inv_qty in inv_map.items():
                    if unit[0] in inv_key[1]:
                        have_qty = int(inv_qty)
                        break
                        
            order_qty = max(0, needed_qty - have_qty)
            
            # Determine Color
            # 0=Red (0 stock), 1=Yellow (Partial), 2=Green (Full)
            if have_qty == 0:
                code = 0 
            elif have_qty < needed_qty:
                code = 1
            else:
                code = 2
            
            u_name = unit[0]
            pn_key = unit[1]
            inv_rows.append([needed_qty, have_qty, order_qty, pn_key, u_name, code])
#-------------------------------------------------------------------------------------------------------

    story.append(Paragraph("Inventory Check — Order List", styles["Section"]))
    story.append(_hline())
    if inv_rows:
        story.append(_make_inventory_check_table(inv_rows))
    else:
        story.append(Paragraph("(no parts needed)", styles["Muted"]))
    story.append(Spacer(1, 0.3 * inch))

    # C. Consolidated parts (Original Tables)
    story.append(Paragraph("All Serials — Consolidated Parts — Over 100%", styles["Section"]))
    story.append(_hline())
    if total_over_upn:
        rows = []
        for (unit, pn), qty in sorted(total_over_upn.items(), key=lambda k: (k[0][0], k[0][1])):
            rows.append([qty, pn, unit])
        story.append(_make_parts_table(rows))
    else: story.append(Paragraph("(none)", styles["Muted"]))
    story.append(Spacer(1, 0.2 * inch))

    story.append(Paragraph(f"All Serials — Consolidated Parts — Threshold - {thr*100:.1f}%", styles["Section"]))
    story.append(_hline())
    if total_thr_upn:
        rows = []
        for (unit, pn), qty in sorted(total_thr_upn.items(), key=lambda k: (k[0][0], k[0][1])):
            rows.append([qty, pn, unit])
        story.append(_make_parts_table(rows))
    else: story.append(Paragraph("(none)", styles["Muted"]))
    
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("Individual Serial Breakdowns", styles["H1"]))
    story.append(_hline())
    story.append(Spacer(1, 0.1 * inch))

    # D. Individual Serials
    story.extend(individual_serials_story)

    doc.build(story)
    return path