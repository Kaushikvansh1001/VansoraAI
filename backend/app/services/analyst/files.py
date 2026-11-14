from io import BytesIO
from pathlib import PurePath

import pandas as pd

from app.core.errors import AppError

_TYPES = {
    ".csv": "text/csv",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".xls": "application/vnd.ms-excel",
}


def load_table(filename: str, content: bytes, *, max_bytes: int, max_rows: int, max_columns: int) -> pd.DataFrame:
    if len(content) > max_bytes:
        raise AppError("file_too_large", "The file must be 5 MB or smaller.", 400)
    if not content:
        raise AppError("empty_dataset", "The file is empty.", 400)
    name = PurePath(filename.replace("\\", "/")).name.strip()
    suffix = PurePath(name).suffix.lower()
    if suffix not in _TYPES:
        raise AppError("unsupported_file", "Upload a .csv, .xlsx, or .xls file.", 400)
    frame = _read(suffix, content, max_rows)
    if frame.empty or len(frame.columns) == 0:
        raise AppError("empty_dataset", "The file has no rows.", 400)
    if len(frame) > max_rows:
        raise AppError("file_too_large", f"The file must have {max_rows} rows or fewer.", 400)
    columns = [str(column).strip() for column in frame.columns]
    if any(not column for column in columns) or len(set(columns)) != len(columns):
        raise AppError("invalid_columns", "Each column needs a unique name.", 400)
    if len(columns) > max_columns:
        raise AppError("file_too_large", f"The file must have {max_columns} columns or fewer.", 400)
    frame.columns = columns
    return frame


def content_type(filename: str) -> str:
    suffix = PurePath(filename).suffix.lower()
    return _TYPES.get(suffix, "application/octet-stream")


def _read(suffix: str, content: bytes, max_rows: int) -> pd.DataFrame:
    limit = max_rows + 1
    try:
        if suffix == ".csv":
            return pd.read_csv(BytesIO(content), nrows=limit)
        engine = "openpyxl" if suffix == ".xlsx" else "xlrd"
        return pd.read_excel(BytesIO(content), nrows=limit, engine=engine)
    except Exception as exc:
        raise AppError("unreadable_dataset", "This spreadsheet could not be read.", 400) from exc
