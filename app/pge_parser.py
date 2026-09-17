"""Extract billing totals from a PG&E Energy Statement PDF."""
import re
import pdfplumber


class PGEParseError(Exception):
    pass


def parse_pge_bill(file_stream) -> dict:
    """Parse a PG&E bill PDF and return the totals needed for proration.

    Returns a dict:
        total_amount_due: float   -- total $ due on the bill (electric + gas + generation)
        total_kwh: float          -- total kWh billed for the property (from the Electric
                                      Delivery Charges line, used as the denominator)
        billing_start: str | None
        billing_end: str | None
        service_address: str | None
        account_number: str | None
        statement_date: str | None
    """
    with pdfplumber.open(file_stream) as pdf:
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)

    result = {
        "total_amount_due": None,
        "total_kwh": None,
        "billing_start": None,
        "billing_end": None,
        "service_address": None,
        "account_number": None,
        "statement_date": None,
    }

    m = re.search(r"Total Amount Due\s+by\s+\d{2}/\d{2}/\d{4}\s+\$([\d,]+\.\d{2})", full_text)
    if m:
        result["total_amount_due"] = float(m.group(1).replace(",", ""))

    m = re.search(r"PG&E Electric Delivery Charges\s+\d+\s+([\d,]+\.\d+)\s*kWh", full_text)
    if m:
        result["total_kwh"] = float(m.group(1).replace(",", ""))

    m = re.search(
        r"Details of PG&E Electric Delivery Charges.*?(\d{2}/\d{2}/\d{4}) to (\d{2}/\d{2}/\d{4})",
        full_text, re.S,
    )
    if m:
        result["billing_start"], result["billing_end"] = m.groups()

    m = re.search(r"Service For:\s*\n?\s*(\d+\s+[A-Z0-9 .'-]+?)\s*\n", full_text)
    if m:
        result["service_address"] = m.group(1).strip()

    m = re.search(r"Account No:\s*([\d-]+)", full_text)
    if m:
        result["account_number"] = m.group(1)

    m = re.search(r"Statement Date:\s*(\d{2}/\d{2}/\d{4})", full_text)
    if m:
        result["statement_date"] = m.group(1)

    if result["total_amount_due"] is None:
        raise PGEParseError(
            "Couldn't find the Total Amount Due on this PDF. You can enter it manually below."
        )
    if result["total_kwh"] is None:
        raise PGEParseError(
            "Couldn't find the total kWh (Electric Delivery Charges) on this PDF. "
            "You can enter it manually below."
        )

    return result
