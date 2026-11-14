from datetime import date, datetime

import pandas as pd


def profile_frame(frame: pd.DataFrame, preview_rows: int = 8) -> dict:
    columns = []
    for name in frame.columns:
        series = frame[name]
        numeric = pd.to_numeric(series, errors="coerce")
        numeric_ratio = float(numeric.notna().sum()) / max(len(series), 1)
        parsed_dates = _dates(series) if numeric_ratio < 0.8 else None
        kind = "text"
        numeric_summary = None
        date_min = None
        date_max = None
        if numeric_ratio >= 0.8 and numeric.notna().any():
            kind = "number"
            numeric_summary = {
                "count": int(numeric.notna().sum()),
                "min": _number(numeric.min()),
                "max": _number(numeric.max()),
                "mean": _number(numeric.mean()),
                "sum": _number(numeric.sum()),
            }
        elif parsed_dates is not None:
            kind = "date"
            date_min = parsed_dates.min().date().isoformat()
            date_max = parsed_dates.max().date().isoformat()
        columns.append(
            {
                "name": str(name),
                "type": kind,
                "missing": int(series.isna().sum()),
                "unique": int(series.nunique(dropna=True)),
                "numeric": numeric_summary,
                "date_min": date_min,
                "date_max": date_max,
            }
        )
    preview = [_row(record) for record in frame.head(preview_rows).to_dict(orient="records")]
    return {
        "columns": columns,
        "duplicate_rows": int(frame.duplicated().sum()),
        "preview": preview,
    }


def _dates(series: pd.Series):
    sample = series.dropna().astype(str).head(20)
    if sample.empty:
        return None
    looks_dated = sample.str.contains(
        r"\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{1,2}[-/]\d{1,2}[-/]\d{2,4}",
        regex=True,
    ).any()
    if not bool(looks_dated):
        return None
    parsed = pd.to_datetime(series, errors="coerce")
    if float(parsed.notna().sum()) / max(len(series), 1) < 0.8:
        return None
    return parsed


def _number(value) -> float:
    return round(float(value), 4)


def _row(record: dict) -> dict:
    cleaned = {}
    for key, value in record.items():
        if value is None or (isinstance(value, float) and pd.isna(value)) or pd.isna(value):
            cleaned[str(key)] = None
        elif isinstance(value, (datetime, date, pd.Timestamp)):
            cleaned[str(key)] = value.isoformat()
        elif hasattr(value, "item"):
            cleaned[str(key)] = value.item()
        else:
            cleaned[str(key)] = value if isinstance(value, (int, float, str, bool)) else str(value)
    return cleaned
