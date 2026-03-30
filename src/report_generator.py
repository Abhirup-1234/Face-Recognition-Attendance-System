"""PDF and Excel attendance report generation."""
from datetime import datetime
from pathlib import Path

import pandas as pd
import config
import database as db


def generate_pdf_report(target_date: str, class_name: str = None) -> str:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                    Paragraph, Spacer, HRFlowable)

    fname = f"attendance_{target_date}"
    if class_name:
        fname += f"_{class_name.replace(' ', '_')}"
    fname += ".pdf"
    path = config.REPORT_DIR / fname

    doc = SimpleDocTemplate(str(path), pagesize=landscape(A4),
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    styles = getSampleStyleSheet()
    title_s = ParagraphStyle("t", fontSize=18, alignment=TA_CENTER,
                              spaceAfter=6)
    sub_s   = ParagraphStyle("s", fontSize=11, alignment=TA_CENTER,
                              spaceAfter=12, textColor=colors.HexColor("#555"))

    records = db.get_attendance_by_date(target_date, class_name)

    # Deduplicate: first detection per student
    seen    = {}
    for r in records:
        sid = r["student_id"]
        if sid not in seen:
            seen[sid] = r

    elements = [
        Paragraph("School Attendance Report", title_s),
        Paragraph(
            f"Date: {target_date}" + (f" | Class: {class_name}" if class_name else ""),
            sub_s
        ),
        HRFlowable(width="100%", thickness=1,
                   color=colors.HexColor("#4f8ef7")),
        Spacer(1, 0.4*cm),
    ]

    headers   = ["Roll No", "Student ID", "Name", "Class", "Time", "Confidence"]
    table_data = [headers]
    for sid, r in sorted(seen.items(),
                          key=lambda x: (x[1]["class_name"], x[1]["roll_no"])):
        conf = round(r["confidence"] or 0, 3)
        table_data.append([
            str(r["roll_no"]), sid, r["name"], r["class_name"],
            str(r["detected_at"])[-8:] if r["detected_at"] else "",
            str(conf)
        ])

    if len(table_data) == 1:
        elements.append(Paragraph("No records found.", styles["Normal"]))
    else:
        col_w = [2*cm, 3*cm, 6*cm, 3*cm, 2.5*cm, 2.5*cm]
        tbl   = Table(table_data, colWidths=col_w, repeatRows=1)
        tbl.setStyle(TableStyle([
            ("BACKGROUND",   (0,0), (-1,0), colors.HexColor("#1a1a2e")),
            ("TEXTCOLOR",    (0,0), (-1,0), colors.white),
            ("FONTNAME",     (0,0), (-1,0), "Helvetica-Bold"),
            ("FONTSIZE",     (0,0), (-1,0), 9),
            ("ALIGN",        (0,0), (-1,-1), "CENTER"),
            ("ROWBACKGROUNDS",(0,1),(-1,-1),
             [colors.white, colors.HexColor("#f0f0ff")]),
            ("GRID",         (0,0), (-1,-1), 0.5, colors.HexColor("#ccccdd")),
            ("FONTSIZE",     (0,1), (-1,-1), 8),
        ]))
        elements.append(tbl)

    elements.append(Spacer(1, 0.4*cm))
    stats = db.get_daily_stats(target_date)
    lines = ["Summary: "]
    for cls in stats["classes"]:
        if class_name and cls["class_name"] != class_name:
            continue
        lines.append(f"{cls['class_name']}: {cls['present']}/{cls['total']}"
                     f" ({cls['percentage']}%)  ")
    elements.append(Paragraph("".join(lines), styles["Normal"]))
    elements.append(Spacer(1, 0.3*cm))
    elements.append(Paragraph(
        f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        styles["Normal"]
    ))

    doc.build(elements)
    return str(path)


def generate_excel_report(target_date: str, class_name: str = None) -> str:
    fname = f"attendance_{target_date}"
    if class_name:
        fname += f"_{class_name.replace(' ', '_')}"
    fname += ".xlsx"
    path = config.REPORT_DIR / fname

    records = db.get_attendance_by_date(target_date, class_name)
    if records:
        df = pd.DataFrame(records)
        df["confidence"] = df["confidence"].round(3)
        df = df[["student_id", "name", "class_name", "roll_no",
                 "detected_at", "confidence", "camera_id", "status"]]
        df.columns = ["ID", "Name", "Class", "Roll",
                      "Time", "Confidence", "Camera", "Status"]
    else:
        df = pd.DataFrame(columns=["ID", "Name", "Class", "Roll",
                                   "Time", "Confidence", "Camera", "Status"])

    stats_df = pd.DataFrame(db.get_daily_stats(target_date)["classes"])

    with pd.ExcelWriter(str(path), engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Attendance", index=False)
        stats_df.to_excel(writer, sheet_name="Summary", index=False)

    return str(path)
