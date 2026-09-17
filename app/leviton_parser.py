"""Parse a Leviton BMO consumption export (.xlsx or .csv) into per-unit kWh."""
import io
import re
import pandas as pd


class LevitonParseError(Exception):
    pass


REQUIRED_COLS = {"Point Name", "Consumption"}


def parse_leviton_export(file_stream, filename: str) -> list[dict]:
    """Returns a list of {unit, consumption_kwh, start_date, end_date, property}."""
    filename = (filename or "").lower()
    raw = file_stream.read()
    buf = io.BytesIO(raw)

    if filename.endswith(".csv"):
        df = _read_with_header_detect(buf, is_csv=True)
    else:
        df = _read_with_header_detect(buf, is_csv=False)

    missing = REQUIRED_COLS - set(df.columns)
    if missing:
        raise LevitonParseError(
            f"Missing expected column(s) in the Leviton export: {', '.join(sorted(missing))}"
        )

    units = []
    for _, row in df.iterrows():
        point_name = str(row.get("Point Name", "")).strip()
        m = re.search(r"(\d+)", point_name)
        if not m:
            continue
        unit_no = m.group(1)
        consumption = row.get("Consumption")
        if pd.isna(consumption):
            continue
        units.append({
            "unit": unit_no,
            "point_name": point_name,
            "consumption_kwh": float(consumption),
            "start_read": _to_float(row.get("Start Read")),
            "end_read": _to_float(row.get("End Read")),
            "start_date": str(row.get("Start Read Date", "")).strip(),
            "end_date": str(row.get("End Read Date", "")).strip(),
            "property": str(row.get("Property", "")).strip(),
        })

    if not units:
        raise LevitonParseError("No unit consumption rows found in this file.")

    return units


def _to_float(value):
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def _read_with_header_detect(buf, is_csv: bool):
    """The export has a title row above the real header row, so scan for it."""
    if is_csv:
        raw_df = pd.read_csv(buf, header=None)
    else:
        raw_df = pd.read_excel(buf, header=None)

    header_row_idx = None
    for i, row in raw_df.iterrows():
        values = {str(v).strip() for v in row.values}
        if REQUIRED_COLS <= values:
            header_row_idx = i
            break

    if header_row_idx is None:
        raise LevitonParseError(
            "Couldn't find the header row (expected columns like 'Point Name' and 'Consumption')."
        )

    header = raw_df.iloc[header_row_idx]
    data = raw_df.iloc[header_row_idx + 1:].copy()
    data.columns = header
    return data.reset_index(drop=True)
