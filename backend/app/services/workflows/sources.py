from app.services.ai.base import scrub_text
from app.services.workflows.catalog import MAX_TEXT


def dataset_summary_text(name: str, row_count: int, column_count: int, schema_json: dict | None, limit: int = MAX_TEXT) -> str:
    """Turn a saved dataset profile into text. The file itself is not opened."""
    lines = [f"Dataset: {name}", f"Rows: {row_count}", f"Columns: {column_count}"]
    columns = schema_json.get("columns") if isinstance(schema_json, dict) else None
    if isinstance(columns, list):
        for column in columns[:40]:
            if not isinstance(column, dict):
                continue
            title = scrub_text(str(column.get("name", "")), 80)
            kind = scrub_text(str(column.get("type", "")), 20)
            numeric = column.get("numeric") if isinstance(column.get("numeric"), dict) else {}
            extra = ""
            if "sum" in numeric:
                extra = f", sum {numeric.get('sum')}"
            missing = column.get("missing")
            if isinstance(missing, int):
                extra += f", missing {missing}"
            lines.append(f"- {title} ({kind}){extra}")
    return scrub_text("\n".join(lines), limit)


def join_document_text(parts: list[str], limit: int = MAX_TEXT) -> str:
    body = "\n".join(part.strip() for part in parts if isinstance(part, str) and part.strip())
    return scrub_text(body, limit).strip()
