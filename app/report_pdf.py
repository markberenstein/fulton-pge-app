"""Generate the Fulton PG&E Reimbursement PDF report, styled after Mark's sample."""
import io
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle


def build_report_pdf(run: dict) -> bytes:
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleFulton", parent=styles["Heading1"], fontSize=14, spaceAfter=4)
    small_style = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, textColor=colors.grey)
    warn_style = ParagraphStyle("Warn", parent=styles["Normal"], fontSize=9, textColor=colors.red)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=0.5 * inch, rightMargin=0.5 * inch,
        topMargin=0.5 * inch, bottomMargin=0.5 * inch,
    )

    elements = []
    elements.append(Paragraph("Fulton PG&E Reimbursements", title_style))

    period = run.get("billing_period") or {}
    period_str = f"{period.get('start', '?')} thru {period.get('end', '?')}"
    elements.append(Paragraph(f"Billing Period: {period_str}", styles["Normal"]))
    elements.append(Paragraph(
        "Note: To get usage for day you have to have end time till midnight of next day",
        small_style,
    ))
    elements.append(Spacer(1, 10))

    calc = run["calculation"]
    mapping = run.get("mapping", {})

    # Build tenant -> address, and unit -> tenant for grouping display
    unit_to_group = {}
    for unit, info in mapping.items():
        unit_to_group.setdefault((info.get("tenant") or "Unassigned", info.get("address") or ""), []).append(unit)

    header = ["Point Name", "Start Read", "Start Read Date", "End Read", "End Read Date",
              "Consumption", "Units", "Charged"]
    table_data = [header]
    row_styles = []

    units_by_number = {u["unit"]: u for u in calc["units"]}

    for (tenant, address), unit_list in sorted(unit_to_group.items()):
        group_total = 0.0
        for unit_no in unit_list:
            u = units_by_number.get(unit_no)
            if not u:
                continue
            table_data.append([
                u.get("point_name", f"Unit {unit_no}"),
                _fmt_read(u.get("start_read")),
                u.get("start_date", ""),
                _fmt_read(u.get("end_read")),
                u.get("end_date", ""),
                f"{u['consumption_kwh']:.0f}",
                "kWh",
                f"${u['charged']:.2f}",
            ])
            group_total += u["charged"]
        # Group subtotal / tenant label row
        table_data.append([
            "", "", "", "", "", "", f"{address}",
            f"${group_total:.2f}  —  {tenant}",
        ])
        row_styles.append(len(table_data) - 1)

    # Grand total row
    table_data.append(["", "", "", "", "", "", "Total", f"${calc['running_total_charged']:.2f}"])

    col_widths = [0.85*inch, 0.7*inch, 0.95*inch, 0.7*inch, 0.95*inch, 0.75*inch, 0.5*inch, 1.6*inch]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -2), 0.4, colors.grey),
        ("ALIGN", (5, 0), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
    ]
    for r in row_styles:
        style_cmds.append(("BACKGROUND", (0, r), (-1, r), colors.HexColor("#eef2f5")))
        style_cmds.append(("FONTNAME", (0, r), (-1, r), "Helvetica-Bold"))
        style_cmds.append(("SPAN", (0, r), (5, r)))

    t.setStyle(TableStyle(style_cmds))
    elements.append(t)
    elements.append(Spacer(1, 14))

    summary_data = [
        ["Total kWh Consumption (Leviton)", f"{calc['sum_consumption_kwh']:.2f} kWh"],
        ["Total kWh Consumption from Bill", f"{calc['bill_total_kwh']:.2f} kWh" if calc.get("bill_total_kwh") else "—"],
        ["Total PG&E Bill", f"${calc['total_amount_due']:.2f}"],
        ["Total Charged to Tenants", f"${calc['running_total_charged']:.2f}"],
    ]
    s = Table(summary_data, colWidths=[2.6*inch, 1.5*inch])
    s.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(s)

    if calc.get("variance_flag"):
        elements.append(Spacer(1, 10))
        elements.append(Paragraph(
            f"⚠ Verification flag: Leviton total ({calc['sum_consumption_kwh']:.2f} kWh) differs from the "
            f"PG&E bill's kWh ({calc['bill_total_kwh']:.2f} kWh) by {calc['consumption_variance_kwh']:.2f} kWh. "
            f"Check for a missing or misread meter before sending this report.",
            warn_style,
        ))

    pge = run.get("pge", {})
    if pge:
        elements.append(Spacer(1, 14))
        elements.append(Paragraph(
            f"PG&E Account: {pge.get('account_number', '—')}  |  "
            f"Statement Date: {pge.get('statement_date', '—')}  |  "
            f"Service Address: {pge.get('service_address', '—')}",
            small_style,
        ))

    doc.build(elements)
    return buf.getvalue()


def _fmt_read(value):
    if value is None:
        return ""
    try:
        return f"{float(value):,.1f}"
    except (TypeError, ValueError):
        return str(value)
