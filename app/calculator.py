"""Prorate a PG&E bill across sub-metered units by Leviton consumption."""


def calculate_charges(units: list[dict], total_amount_due: float, bill_total_kwh: float) -> dict:
    """units: list of {unit, consumption_kwh, ...}

    Each unit's charge = (unit's kWh / total Leviton kWh) x total PG&E bill.
    The denominator is the SUM of the Leviton units' own consumption readings
    (matching Mark's reimbursement spreadsheet), not the bill's kWh figure.
    The bill's kWh figure (bill_total_kwh) is kept only as a verification check:
    if it doesn't closely match the Leviton sum, something is off (a meter missing
    from the export, a misread, etc.) and that should be flagged.

    Rounding: each unit's exact share is rounded to the nearest cent, then any
    leftover pennies (from rounding) are distributed one at a time to the units
    whose rounded amount was furthest below its exact share — so the charged
    amounts always sum to exactly total_amount_due, to the penny.
    """
    sum_consumption = sum(u["consumption_kwh"] for u in units)
    if sum_consumption <= 0:
        raise ValueError("Sum of Leviton unit consumption must be greater than zero.")

    rate = total_amount_due / sum_consumption

    # Exact (unrounded) share per unit, then round to the nearest cent
    exact_charges = [u["consumption_kwh"] / sum_consumption * total_amount_due for u in units]
    rounded_cents = [round(c * 100) for c in exact_charges]

    total_cents_due = round(total_amount_due * 100)
    leftover_cents = total_cents_due - sum(rounded_cents)

    # Distribute leftover pennies to whichever units' rounding lost (or gained)
    # the most, largest-remainder style, so the total lands exactly on the bill.
    remainders = [exact_charges[i] * 100 - rounded_cents[i] for i in range(len(units))]
    order = sorted(range(len(units)), key=lambda i: remainders[i], reverse=(leftover_cents > 0))
    for i in range(abs(leftover_cents)):
        idx = order[i % len(order)]
        rounded_cents[idx] += 1 if leftover_cents > 0 else -1

    charged_units = []
    running_total = 0.0
    for u, cents in zip(units, rounded_cents):
        charged = cents / 100
        running_total += charged
        charged_units.append({**u, "rate": rate, "charged": charged})

    consumption_variance_kwh = round(bill_total_kwh - sum_consumption, 2) if bill_total_kwh else None
    # Flag if Leviton and PG&E totals disagree by more than ~1% or 5 kWh, whichever is larger
    variance_flag = False
    if bill_total_kwh:
        threshold = max(5.0, 0.01 * bill_total_kwh)
        variance_flag = abs(consumption_variance_kwh) > threshold

    return {
        "rate": rate,
        "units": charged_units,
        "sum_consumption_kwh": sum_consumption,
        "bill_total_kwh": bill_total_kwh,
        "consumption_variance_kwh": consumption_variance_kwh,
        "variance_flag": variance_flag,
        "running_total_charged": round(running_total, 2),
        "total_amount_due": total_amount_due,
        "rounding_variance": round(total_amount_due - running_total, 2),
    }


def group_by_tenant(charged_units: list[dict], mapping: dict) -> list[dict]:
    """mapping: {unit_number: {"tenant": str, "address": str}}
    Groups charged units by tenant, summing charges and consumption.
    Units with no mapping entry are grouped under 'Unassigned'.
    """
    groups = {}
    for u in charged_units:
        info = mapping.get(u["unit"], {})
        tenant = info.get("tenant") or "Unassigned"
        address = info.get("address") or ""
        key = tenant
        if key not in groups:
            groups[key] = {
                "tenant": tenant,
                "address": address,
                "units": [],
                "total_charged": 0.0,
                "total_kwh": 0.0,
            }
        groups[key]["units"].append(u)
        groups[key]["total_charged"] = round(groups[key]["total_charged"] + u["charged"], 2)
        groups[key]["total_kwh"] += u["consumption_kwh"]

    return sorted(groups.values(), key=lambda g: g["tenant"])
