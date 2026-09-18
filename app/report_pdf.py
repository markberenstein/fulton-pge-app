"""Generate the Fulton PG&E Reimbursement PDF report, styled after Mark's sample."""
import io
from xml.sax.saxutils import escape as _xml_escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image as RLImage
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

PAGE_MARGIN = 0.35 * inch
# SimpleDocTemplate wraps the page in a Frame with its own default 6pt
# padding on every side, on top of the margins above — account for it here
# so our "how much space is left" math matches what actually gets drawn.
FRAME_PADDING = 6
CONTENT_WIDTH = letter[0] - 2 * PAGE_MARGIN - 2 * FRAME_PADDING
USABLE_HEIGHT = letter[1] - 2 * PAGE_MARGIN - 2 * FRAME_PADDING


def build_report_pdf(run: dict, bill_pdf_bytes: bytes | None = None) -> bytes:
    """Build the calculated reimbursement report. If bill_pdf_bytes is given,
    a compact row of thumbnails from the three relevant PG&E bill sections
    (Account Summary, Summary of energy related services, Details of PG&E
    Electric Delivery Charges) is added below the calculation, sized to fit
    in the space left on the page — matching Mark's manual sample, which
    fit the whole thing (calc + bill snapshots) on a single page."""
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleFulton", parent=styles["Heading1"], fontSize=12, spaceAfter=3, leading=14)
    small_style = ParagraphStyle("Small", parent=styles["Normal"], fontSize=7, textColor=colors.grey, leading=9)
    warn_style = ParagraphStyle("Warn", parent=styles["Normal"], fontSize=8, textColor=colors.red, leading=10)
    normal_style = ParagraphStyle("NormalSmall", parent=styles["Normal"], fontSize=8, leading=10)

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=letter,
        leftMargin=PAGE_MARGIN, rightMargin=PAGE_MARGIN,
        topMargin=PAGE_MARGIN, bottomMargin=PAGE_MARGIN,
    )

    elements = []
    elements.append(Paragraph("Fulton PG&amp;E Reimbursements", title_style))

    period = run.get("billing_period") or {}
    period_str = f"{period.get('start', '?')} thru {period.get('end', '?')}"
    elements.append(Paragraph(f"Billing Period: {period_str}", normal_style))
    elements.append(Paragraph(
        "Note: To get usage for day you have to have end time till midnight of next day",
        small_style,
    ))
    elements.append(Spacer(1, 6))

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
        label = f"{address} — {tenant}" if address else tenant
        table_data.append([
            label, "", "", "", "", "", "",
            f"${group_total:.2f}",
        ])
        row_styles.append(len(table_data) - 1)

    # Grand total row
    table_data.append(["", "", "", "", "", "", "Total", f"${calc['running_total_charged']:.2f}"])

    col_widths = [0.85*inch, 0.65*inch, 0.85*inch, 0.65*inch, 0.85*inch, 0.65*inch, 0.45*inch, 1.35*inch]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)

    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 5.5),
        ("TOPPADDING", (0, 0), (-1, -1), 2
