from pathlib import Path
import re
import pandas as pd

MAX_ROWS = 5000
REQUIRED = ["Name", "Email", "Event Name", "Certificate Type"]
ALIASES = {
    "name": "Name", "participant name": "Name", "full name": "Name",
    "email": "Email", "email address": "Email",
    "event name": "Event Name", "event": "Event Name",
    "certificate type": "Certificate Type", "certificate": "Certificate Type", "award": "Certificate Type",
    "issue date": "Issue Date", "event date": "Issue Date"
}

def normalize_type(value):
    value = str(value or "").strip().lower()
    value = re.sub(r"[\s_\-]+", " ", value)
    if "participat" in value:
        return "Participation"
    if "first prize" in value or "1st prize" in value or value in {"first", "1st", "first place"}:
        return "First Prize"
    if "second prize" in value or "2nd prize" in value or value in {"second", "2nd", "second place"}:
        return "Second Prize"
    return None

def valid_email(value):
    value = str(value or "").strip()
    return bool(re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value))

def parse_spreadsheet(path):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    elif path.suffix.lower() == ".xlsx":
        df = pd.read_excel(path, dtype=str, keep_default_na=False, engine="openpyxl")
    else:
        raise ValueError("Only .xlsx and .csv files are supported.")
    if len(df) > MAX_ROWS:
        raise ValueError(f"Spreadsheet exceeds the {MAX_ROWS} row limit.")
    # Normalize common column-name variations, case-insensitively.
    renamed = {}
    for column in df.columns:
        key = re.sub(r"\s+", " ", str(column).strip().lower())
        if key in ALIASES:
            renamed[column] = ALIASES[key]
    df = df.rename(columns=renamed)
    missing = [col for col in REQUIRED if col not in df.columns]
    if missing:
        raise ValueError("Missing required column(s): " + ", ".join(missing))
    rows, errors = [], []
    for idx, raw in df.iterrows():
        data = {str(k): str(v).strip() for k, v in raw.to_dict().items()}
        issues = []
        for col in REQUIRED:
            if not data.get(col, "").strip():
                issues.append(f"{col} is required")
        if data.get("Email") and not valid_email(data["Email"]):
            issues.append("Email address is invalid")
        normalized = normalize_type(data.get("Certificate Type", ""))
        if data.get("Certificate Type") and not normalized:
            issues.append("Unsupported certificate type")
        if normalized:
            data["Certificate Type"] = normalized
        if not issues:
            rows.append({"row_number": int(idx) + 2, "valid": True, "issues": [], "data": data})
        else:
            rows.append({"row_number": int(idx) + 2, "valid": False, "issues": issues, "data": data})
            errors.append({"row_number": int(idx) + 2, "issues": issues})
    return {"rows": rows, "errors": errors}
