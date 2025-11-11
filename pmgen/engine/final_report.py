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
    if p < 84.0:
        return colors.darkgray
    elif p < 100.0:
        return colors.orange
    else:
        return colors.red

def _hline(thickness=1, color=colors.HexColor("#DDDDDD")):
    return HRFlowable(width="100%", thickness=thickness, color=color, spaceBefore=4, spaceAfter=6)

def _make_parts_table(rows, col_names=("Qty", "Part Number", "Unit")):
    """
    rows: list of tuples/lists [qty, pn, unit]
    returns a styled Table
    """
    data = [list(col_names)]
    for qty, pn, unit in rows:
        data.append([str(int(qty)), pn, unit])

    tbl = Table(
        data,
        colWidths=[0.7 * inch, 3.0 * inch, 3.05 * inch],
        hAlign="LEFT",
    )

    tbl.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, 0), 10),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#3B82F6")),  # header

                ("FONT", (0, 1), (-1, -1), "Helvetica"),
                ("FONTSIZE", (0, 1), (-1, -1), 9),
                ("ALIGN", (0, 1), (0, -1), "RIGHT"),  # Qty right-aligned
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),

                ("INNERGRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#E5E7EB")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#CBD5E1")),
            ]
        )
    )

    for r in range(1, len(data)):
        if r % 2 == 0:
            tbl.setStyle(
                TableStyle(
                    [("BACKGROUND", (0, r), (-1, r), colors.HexColor("#F8FAFC"))]
                )
            )

    tbl.splitByRow = 1
    tbl.repeatRows = 1
    return tbl


def write_final_summary_pdf(
    *,
    out_dir: str,
    results: list,
    top: list,
    thr: float,
    basis: str,
    filename: str = "Final_Summary.pdf",
):
    """
    Build the same report you were printing to text, but as a PDF with colored text
    and tables for parts.
    """
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, filename)

    doc = SimpleDocTemplate(
        path,
        pagesize=LETTER,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
        title="Bulk Final Summary",
        author="PmGen",
    )

    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="H1",
            parent=styles["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#111827"),
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Meta",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=9,
            textColor=colors.HexColor("#374151"),
            spaceAfter=3,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
            parent=styles["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=14,
            textColor=colors.HexColor("#111827"),
            spaceBefore=10,
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SerialLine",
            parent=styles["BodyText"],
            fontName="Helvetica",
            fontSize=10,
            leading=12,
            textColor=colors.HexColor("#111827"),
            spaceBefore=4,
            spaceAfter=2,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Muted",
            parent=styles["BodyText"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            textColor=colors.HexColor("#6B7280"),
            spaceAfter=6,
        )
    )

    story = []

    # Title
    story.append(Paragraph("Bulk Final Summary", styles["H1"]))
    story.append(_hline())

    # Meta block
    successful = len([r for r in results if r.get("ok", True)])
    meta_lines = [
        f"Threshold: <b>{thr:.2f}</b> • Basis: <b>{basis.upper()}</b>",
        f"Selected top <b>{len(top)}</b> of <b>{successful}</b> successful (from <b>{len(results)}</b> attempts).",
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
    ]
    for ml in meta_lines:
        story.append(Paragraph(ml, styles["Meta"]))
    story.append(Spacer(1, 0.15 * inch))

    total_upn = {}

    # Per-serial sections (keep each table together on a single page)
    for r in top:
        serial = r.get("serial", "UNKNOWN")
        model = r.get("model", "UNKNOWN MODEL")
        best_used = r.get("best_used", 0.0) * 100

        c = _pct_color(best_used)
        hexcolor = f"#{int(c.red*255):02X}{int(c.green*255):02X}{int(c.blue*255):02X}"
        serial_line = (
            f"<b>{serial}</b> — best used "
            f"<font color='{hexcolor}'>{best_used:.1f}%</font>"
            f" — {model}"
        )
        story.append(Paragraph(serial_line, styles["SerialLine"]))

        grouped = r.get("grouped") or {}
        flat = r.get("flat") or {}
        kit_by_pn = r.get("kit_by_pn") or {}

        # Build rows for this serial's table
        rows = []
        if grouped:
            for unit, pnmap in grouped.items():
                for pn, qty in (pnmap or {}).items():
                    rows.append([int(qty), pn, unit or "UNKNOWN-UNIT"])
                    total_upn[(unit or "UNKNOWN-UNIT", pn)] = total_upn.get(
                        (unit or "UNKNOWN-UNIT", pn), 0
                    ) + int(qty)
        else:
            if not flat:
                story.append(Paragraph("(no final parts)", styles["Muted"]))
            else:
                for pn, qty in flat.items():
                    unit = kit_by_pn.get(pn, "UNKNOWN-UNIT")
                    rows.append([int(qty), pn, unit])
                    total_upn[(unit, pn)] = total_upn.get((unit, pn), 0) + int(qty)

        if rows:
            rows.sort(key=lambda x: (x[2], x[1]))
            tbl = _make_parts_table(rows)
            try:
                story.append(KeepTogether(tbl))
            except LayoutError:
                story.append(tbl)
        story.append(Spacer(1, 0.15 * inch))

    story.append(Paragraph("All Serials — Consolidated Parts", styles["Section"]))
    story.append(_hline())

    if total_upn:
        rows = []
        for (unit, pn), qty in sorted(total_upn.items(), key=lambda k: (k[0][0], k[0][1])):
            rows.append([qty, pn, unit])
        tbl = _make_parts_table(rows)
        story.append(tbl)
    else:
        story.append(Paragraph("(none)", styles["Muted"]))
    story.append(Spacer(1, 0.2 * inch))

    doc.build(story)
    return path
