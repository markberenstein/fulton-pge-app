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
            snapshot_flowables = _build_bill_snapshot_stack(elements, bill_pdf_bytes)
            if snapshot_flowables:
                elements.append(Spacer(1, 6))
                elements.extend(snapshot_flowables)
        except Exception:
            # If the snapshot can't be rasterized for any reason, still
            # deliver the calculated report rather than failing the request.
            pass

    doc.build(elements)
    return buf.getvalue()


# The three PG&E bill sections Mark's manual sample includes as a snapshot,
# in the ORDER he wants them displayed (not the bill's own page order): the
# Details of Electric Delivery Charges box first, since that's where the
# electric usage period date lives, then the account summary, then the
# energy-services summary. "start_marker"/"end_marker" (case-insensitive,
# searched as plain text) bound a tight crop around just that section's box;
# leaving "end_marker" unset falls back to the old blank-row-gap heuristic.
BILL_SNAPSHOT_SECTIONS = [
    {
        "search_marker": "details of pg&e electric delivery charges",
        "start_marker": "Details of PG&E Electric Delivery Charges",
        "end_marker": "Energy Charges",
    },
    {
        "search_marker": "your account summary",
        "start_marker": None,
        "end_marker": None,
    },
    {
        "search_marker": "summary of your energy related services",
        "start_marker": None,
        "end_marker": None,
    },
]


def _select_bill_snapshot_sections(bill_pdf_bytes: bytes) -> list[dict]:
    """Return one entry per matched section, in the display order Mark
    wants (BILL_SNAPSHOT_SECTIONS order), each with the section's page index
    plus its start/end marker text (in pixel terms, resolved later) for a
    tight crop. Text is extracted with pdfplumber (the same library that
    already parses the bill's numbers reliably) rather than pypdf's own
    extract_text(), which can be extremely slow or hang outright on some
    real-world PDFs with complex embedded fonts."""
    import pdfplumber

    results = []
    with pdfplumber.open(io.BytesIO(bill_pdf_bytes)) as pdf:
        for section in BILL_SNAPSHOT_SECTIONS:
            for page_index, page in enumerate(pdf.pages):
                text = (page.extract_text() or "").lower()
                if section["search_marker"] in text:
                    results.append({
                        "page_index": page_index,
                        "start_marker": section["start_marker"],
                        "end_marker": section["end_marker"],
                    })
                    break
    return results


def _select_bill_snapshot_page_indices(bill_pdf_bytes: bytes) -> list[int]:
    """Return the 0-based page indices in the bill matching the snapshot
    sections, in natural page order (used only by the legacy full-page
    fallback below, where display order doesn't matter)."""
    return sorted({s["page_index"] for s in _select_bill_snapshot_sections(bill_pdf_bytes)})


def _select_bill_snapshot_pages(bill_pdf_bytes: bytes):
    """Return the list of pypdf page objects from the bill matching the
    snapshot sections, in page order. Falls back to every page of the bill
    if none of the sections are found, so the appendix is never empty."""
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


def _crop_to_content_block(
    png_bytes: bytes,
    top_px: int = 0,
    bottom_px: int | None = None,
    min_start_px: int = 150,
    gap_threshold_px: int = 60,
) -> bytes:
    """Crop a rasterized bill page down to just one content block, dropping
    everything else on the page (a header from a different section above it,
    the usage chart and footer below it) — the way Mark's manual sample
    crops each section down to just its relevant box.

    When bottom_px is given (both boundaries were found precisely by text
    search — see _build_bill_snapshot_stack), the crop is exact: top_px to
    bottom_px, plus a small margin. Otherwise this falls back to the older
    heuristic: starting at top_px, scan down for the first tall band of
    near-blank rows (a real gap between sections, not just line spacing
    within a table) and cut there; if no such gap is found, keep the rest
    of the page."""
    from PIL import Image

    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")

    if bottom_px is not None:
        # Small padding above the section's heading, but none below: the
        # bottom bound is the top edge of the next section's heading, and
        # PG&E's line spacing there is tight enough that any extra margin
        # picks up a sliver of that next line's text.
        top_margin = 6
        bottom_trim = 2
        top = max(top_px - top_margin, 0)
        bottom = max(min(bottom_px - bottom_trim, img.height), top + 1)
        cropped = img.crop((0, top, img.width, bottom))
        out = io.BytesIO()
        cropped.save(out, format="PNG")
        return out.getvalue()

    import numpy as np

    if top_px:
        img = img.crop((0, top_px, img.width, img.height))
    gray = np.array(img.convert("L"))
    h = gray.shape[0]
    is_blank_row = (gray < 240).mean(axis=1) < 0.01

    i = min(min_start_px, h)
    cut_row = h
    while i < h:
        if is_blank_row[i]:
            j = i
            while j < h and is_blank_row[j]:
                j += 1
            if j - i >= gap_threshold_px:
                cut_row = i
                break
            i = j
        else:
            i += 1

    if cut_row >= h:
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue()

    cropped = img.crop((0, 0, img.width, cut_row))
    out = io.BytesIO()
    cropped.save(out, format="PNG")
    return out.getvalue()


_SNAPSHOT_DPI = 150


def _find_marker_top(pdfplumber_page, marker_text: str) -> float | None:
    """Return the top y-coordinate (PDF points) of the first line matching
    marker_text on this pdfplumber page, or None if not found."""
    try:
        results = pdfplumber_page.search(marker_text, case=False)
    except TypeError:
        results = pdfplumber_page.search(marker_text)
    return results[0]["top"] if results else None


def _build_bill_snapshot_stack(existing_elements, bill_pdf_bytes: bytes):
    """Rasterize the three relevant PG&E bill sections, crop each down to
    just its own box — tightly, by text position, for the Details of
    Electric Delivery Charges section, since Mark asked for that section
    to only show the period/service/customer-charge block and nothing
    from the account-summary header above it or the usage breakdown below
    it — and lay them out as a vertical stack of thumbnails, Delivery
    Charges first (it carries the electric usage period date), then
    Account Summary, then the energy-services summary, one on top of the
    other, full width, each sized to fit whatever vertical space remains
    below the calculation — matching Mark's manual sample layout."""
    import pdfplumber
    import pymupdf

    sections = _select_bill_snapshot_sections(bill_pdf_bytes)
    if not sections:
        return []

    scale = _SNAPSHOT_DPI / 72.0

    # Resolve each section's tight top/bottom crop bounds (in raster pixels)
    # up front, while we still have the bill open in pdfplumber for text search.
    with pdfplumber.open(io.BytesIO(bill_pdf_bytes)) as pdf:
        for section in sections:
            page = pdf.pages[section["page_index"]]
            top_px = 0
            bottom_px = None
            if section["start_marker"]:
                top_pt = _find_marker_top(page, section["start_marker"])
                if top_pt is not None:
                    top_px = int(top_pt * scale)
            if section["end_marker"]:
                end_pt = _find_marker_top(page, section["end_marker"])
                if end_pt is not None:
                    bottom_px = int(end_pt * scale)
            section["top_px"] = top_px
            section["bottom_px"] = bottom_px

    gap = 5
    n = len(sections)
    used_height = _measure_flowables_height(existing_elements, CONTENT_WIDTH, USABLE_HEIGHT)
    remaining = USABLE_HEIGHT - used_height - 10 - gap * (n - 1)
    # Keep a sensible minimum per image so thumbnails stay legible even if
    # the calculation table ran long (the report will then flow onto a 2nd
    # page, which is an acceptable fallback rather than illegibly tiny images).
    max_height_each = max(remaining / n, 90)

    src = pymupdf.open(stream=bill_pdf_bytes, filetype="pdf")
    flowables = []
    for i, section in enumerate(sections):
        page = src[section["page_index"]]
        pix = page.get_pixmap(dpi=_SNAPSHOT_DPI)
        png_bytes = _crop_to_content_block(
            pix.tobytes("png"),
            top_px=section["top_px"],
            bottom_px=section["bottom_px"],
        )
        from PIL import Image as PILImage
        with PILImage.open(io.BytesIO(png_bytes)) as pil_img:
            iw, ih = pil_img.size
        aspect = ih / iw
        w = CONTENT_WIDTH
        h = w * aspect
        if h > max_height_each:
            h = max_height_each
            w = h / aspect
        img = RLImage(io.BytesIO(png_bytes), width=w, height=h)
        img.hAlign = "CENTER"
        if i > 0:
            flowables.append(Spacer(1, gap))
        flowables.append(img)
    src.close()

    return flowables


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
