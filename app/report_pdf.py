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
CONTENT_WIDTH = letter[0] - 2 * PAGE_MARGIN
USABLE_HEIGHT = letter[1] - 2 * PAGE_MARGIN


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
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
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
        style_cmds.append(("SPAN", (0, r), (6, r)))
        style_cmds.append(("ALIGN", (6, r), (6, r), "LEFT"))

    t.setStyle(TableStyle(style_cmds))
    elements.append(t)
    elements.append(Spacer(1, 8))

    summary_data = [
        ["Total kWh Consumption (Leviton)", f"{calc['sum_consumption_kwh']:.2f} kWh"],
        ["Total kWh Consumption from Bill", f"{calc['bill_total_kwh']:.2f} kWh" if calc.get("bill_total_kwh") else "—"],
        ["Total PG&E Bill", f"${calc['total_amount_due']:.2f}"],
        ["Total Charged to Tenants", f"${calc['running_total_charged']:.2f}"],
    ]
    s = Table(summary_data, colWidths=[2.3*inch, 1.3*inch])
    s.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("TOPPADDING", (0, 0), (-1, -1), 1),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, colors.grey),
    ]))
    elements.append(s)

    if calc.get("variance_flag"):
        elements.append(Spacer(1, 5))
        elements.append(Paragraph(
            f"⚠ Verification flag: Leviton total ({calc['sum_consumption_kwh']:.2f} kWh) differs from the "
            f"PG&amp;E bill's kWh ({calc['bill_total_kwh']:.2f} kWh) by {calc['consumption_variance_kwh']:.2f} kWh. "
            f"Check for a missing or misread meter before sending this report.",
            warn_style,
        ))

    pge = run.get("pge", {})
    if pge:
        elements.append(Spacer(1, 6))
        elements.append(Paragraph(
            f"PG&amp;E Account: {_xml_escape(str(pge.get('account_number', '—')))}  |  "
            f"Statement Date: {_xml_escape(str(pge.get('statement_date', '—')))}  |  "
            f"Service Address: {_xml_escape(str(pge.get('service_address', '—')))}",
            small_style,
        ))

    if bill_pdf_bytes:
        try:
            snapshot_flowable = _build_bill_snapshot_row(elements, bill_pdf_bytes)
            if snapshot_flowable is not None:
                elements.append(Spacer(1, 6))
                elements.append(snapshot_flowable)
        except Exception:
            # If the snapshot can't be rasterized for any reason, still
            # deliver the calculated report rather than failing the request.
            pass

    doc.build(elements)
    return buf.getvalue()


# Section markers (case-insensitive substring match) identifying the three
# PG&E bill pages Mark's manual sample includes as a snapshot: the account
# summary/energy statement page, the summary of energy related services
# page, and the delivery charges detail page.
BILL_SNAPSHOT_MARKERS = [
    "your account summary",
    "summary of your energy related services",
    "details of pg&e electric delivery charges",
]


def _select_bill_snapshot_page_indices(bill_pdf_bytes: bytes) -> list[int]:
    """Return the 0-based page indices in the bill matching the snapshot
    markers, in page order. Text is extracted with pdfplumber (the same
    library that already parses the bill's numbers reliably) rather than
    pypdf's own extract_text(), which can be extremely slow or hang outright
    on some real-world PDFs with complex embedded fonts."""
    import pdfplumber

    matched = []
    seen = set()
    with pdfplumber.open(io.BytesIO(bill_pdf_bytes)) as pdf:
        for page_index, page in enumerate(pdf.pages):
            text = (page.extract_text() or "").lower()
            if any(marker in text for marker in BILL_SNAPSHOT_MARKERS):
                if page_index not in seen:
                    matched.append(page_index)
                    seen.add(page_index)
    return matched


def _select_bill_snapshot_pages(bill_pdf_bytes: bytes):
    """Return the list of pypdf page objects from the bill matching the
    snapshot markers, in page order. Falls back to every page of the bill
    if none of the markers are found, so the appendix is never empty."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(bill_pdf_bytes))
    indices = _select_bill_snapshot_page_indices(bill_pdf_bytes)
    if not indices:
        return list(reader.pages)
    return [reader.pages[i] for i in indices]


def _measure_flowables_height(flowables, width, height_budget):
    """Sum the rendered height of a list of already-built flowables against
    a given width, so we know how much vertical space is left on the page."""
    used = 0.0
    for el in flowables:
        try:
            _, h = el.wrap(width, height_budget)
            used += h
        except Exception:
            pass
    return used


def _build_bill_snapshot_row(existing_elements, bill_pdf_bytes: bytes):
    """Rasterize the three relevant PG&E bill pages and lay them out as a
    single compact row of thumbnails sized to fit whatever vertical space
    remains on the page below the calculation — so the whole report,
    calculation and bill snapshot together, fits on one page, matching
    Mark's manual sample layout."""
    import pymupdf

    indices = _select_bill_snapshot_page_indices(bill_pdf_bytes)
    if not indices:
        return None

    used_height = _measure_flowables_height(existing_elements, CONTENT_WIDTH, USABLE_HEIGHT)
    remaining = USABLE_HEIGHT - used_height - 10
    # Keep a sensible minimum so thumbnails are still legible even if the
    # calculation table ran long (report will then flow onto a 2nd page,
    # which is an acceptable fallback rather than illegibly tiny images).
    max_row_height = max(remaining, 170)

    n = len(indices)
    gap = 6
    cell_width = (CONTENT_WIDTH - gap * (n - 1)) / n

    src = pymupdf.open(stream=bill_pdf_bytes, filetype="pdf")
    images = []
    row_height = 0.0
    for idx in indices:
        page = src[idx]
        pix = page.get_pixmap(dpi=150)
        png_bytes = pix.tobytes("png")
        iw, ih = pix.width, pix.height
        aspect = ih / iw
        w = cell_width
        h = w * aspect
        if h > max_row_height:
            h = max_row_height
            w = h / aspect
        images.append((png_bytes, w, h))
        row_height = max(row_height, h)
    src.close()

    row_cells = []
    for png_bytes, w, h in images:
        img = RLImage(io.BytesIO(png_bytes), width=w, height=h)
        row_cells.append(img)

    row_table = Table([row_cells], colWidths=[cell_width] * n)
    row_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), gap / 2),
        ("RIGHTPADDING", (0, 0), (-1, -1), gap / 2),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return row_table


def append_bill_snapshot(report_pdf_bytes: bytes, bill_pdf_bytes: bytes) -> bytes:
    """Legacy fallback: append the relevant PG&E bill pages as full extra
    pages after the calculated report (rather than as inline thumbnails).
    Kept for cases where the compact single-page layout can't be built."""
    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(report_pdf_bytes)).pages:
        writer.add_page(page)
    for page in _select_bill_snapshot_pages(bill_pdf_bytes):
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def _fmt_read(value):
    if value is None:
        return ""
    try:
        return f"{float(value):,.1f}"
    except (TypeError, ValueError):
        return str(value)
