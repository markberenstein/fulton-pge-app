"""Generate per-tenant reimbursement email drafts, matching Mark's Buildium template."""
import re
from datetime import datetime

DEFAULT_SUBJECT_TEMPLATE = "Fulton PG&E Reimbursement - {month_year}"

DEFAULT_BODY_TEMPLATE = """Hi {first_name},

We hope the updated PG&E bill reimbursement process is providing reports on PG&E usage for each sub-metered unit clearly for you. Attached you will find the usage data and prorated reimbursement calculations based on your unit's actual PG&E usage for the billing period from {billing_start} to {billing_end}.

Please reimburse {billed_entity} {amount}, which will be added to Buildium which can be paid at your convenience, or you may include the reimbursement with your next rent payment. The attachment includes a detailed explanation of the calculations used.

Note: If you have setup Buildium Epay for auto-pay, please be sure auto-pay is set to pay balance or update Epay appropriately to pay the full amount owed with your next monthly rent payment.

For any questions regarding this new process, please contact {contact_name} at {contact_phone}.
Thank you,
{sender_name}"""


def first_name_from_tenant(tenant: str) -> str:
    """'Tony Pimentel / Coastside Circuit Breakers Inc' -> 'Tony'"""
    if not tenant:
        return "there"
    name_part = tenant.split("/")[0].strip()
    tokens = name_part.split()
    return tokens[0] if tokens else "there"


def format_long_date(mmddyyyy: str) -> str:
    """'08/04/2026' -> 'August 4, 2026'"""
    try:
        dt = datetime.strptime(mmddyyyy, "%m/%d/%Y")
        return f"{dt.strftime('%B')} {dt.day}, {dt.year}"
    except (ValueError, TypeError):
        return mmddyyyy or ""


def month_year_from(mmddyyyy: str) -> str:
    try:
        dt = datetime.strptime(mmddyyyy, "%m/%d/%Y")
        return dt.strftime("%B %Y")
    except (ValueError, TypeError):
        return ""


def build_email_drafts(run: dict, settings: dict) -> list[dict]:
    """One draft per tenant group in run['groups']."""
    period = run.get("billing_period", {})
    billing_start = format_long_date(period.get("start"))
    billing_end = format_long_date(period.get("end"))
    month_year = month_year_from(period.get("start"))

    subject_template = settings.get("subject_template") or DEFAULT_SUBJECT_TEMPLATE
    body_template = settings.get("body_template") or DEFAULT_BODY_TEMPLATE

    drafts = []
    for g in run.get("groups", []):
        first_name = g.get("first_name_override") or first_name_from_tenant(g["tenant"])
        amount = f"${g['total_charged']:,.2f}"
        ctx = {
            "first_name": first_name,
            "billing_start": billing_start,
            "billing_end": billing_end,
            "month_year": month_year,
            "billed_entity": settings.get("billed_entity", "BA Partners LLC"),
            "amount": amount,
            "contact_name": settings.get("contact_name", ""),
            "contact_phone": settings.get("contact_phone", ""),
            "sender_name": settings.get("sender_name", ""),
            "tenant": g["tenant"],
            "address": g.get("address", ""),
        }
        subject = subject_template.format(**ctx)
        body = body_template.format(**ctx)
        drafts.append({
            "tenant": g["tenant"],
            "address": g.get("address", ""),
            "amount": amount,
            "subject": subject,
            "body": body,
        })
    return drafts
