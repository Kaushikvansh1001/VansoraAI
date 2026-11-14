import pandas as pd

from app.core.errors import AppError

OPERATIONS = {"aggregate", "groupby", "trend", "top", "summary"}
AGGREGATIONS = {"sum", "mean", "count", "min", "max"}
CHARTS = {"bar", "line", "pie", "area", "table", "kpi"}
FILTERS = {"eq", "ne", "gt", "lt", "gte", "lte", "contains"}


def validate_plan(plan: dict, columns: list[str]) -> dict:
    if not isinstance(plan, dict):
        raise AppError("invalid_plan", "The analysis plan is not valid.", 422)
    operation = str(plan.get("operation") or "").strip().lower()
    aggregation = str(plan.get("agg") or "sum").strip().lower()
    chart = str(plan.get("chart") or "table").strip().lower()
    if operation not in OPERATIONS:
        raise AppError("invalid_plan", "That analysis is not supported.", 422)
    if aggregation not in AGGREGATIONS:
        raise AppError("invalid_plan", "That calculation is not supported.", 422)
    if chart not in CHARTS:
        chart = "table"
    known = set(columns)
    value_column = _column(plan.get("value_column"), known, required=operation in {"aggregate", "groupby", "trend", "top"} and aggregation != "count")
    group_column = _column(plan.get("group_column"), known, required=operation in {"groupby", "top"})
    time_column = _column(plan.get("time_column"), known, required=operation == "trend")
    if operation == "aggregate" and aggregation == "count" and value_column is None:
        value_column = columns[0]
    try:
        limit = int(plan.get("limit") or 5)
    except (TypeError, ValueError) as exc:
        raise AppError("invalid_plan", "The row limit is not valid.", 422) from exc
    limit = min(max(limit, 1), 20)
    filters = []
    for item in plan.get("filters") or []:
        if not isinstance(item, dict):
            continue
        column = _column(item.get("column"), known, required=True)
        operator = str(item.get("op") or "").strip().lower()
        if operator not in FILTERS:
            raise AppError("invalid_plan", "That filter is not supported.", 422)
        filters.append({"column": column, "op": operator, "value": item.get("value")})
    return {
        "operation": operation,
        "value_column": value_column,
        "group_column": group_column,
        "time_column": time_column,
        "agg": aggregation,
        "limit": limit,
        "chart": chart,
        "filters": filters,
    }


def execute(frame: pd.DataFrame, plan: dict) -> dict:
    cleaned = validate_plan(plan, [str(column) for column in frame.columns])
    data = _filter(frame, cleaned["filters"])
    operation = cleaned["operation"]
    if operation == "summary":
        rows = [{"label": "Rows", "value": float(len(data))}]
        chart = "kpi"
        value = float(len(data))
    elif operation == "aggregate":
        value = _aggregate(data[cleaned["value_column"]], cleaned["agg"])
        rows = [{"label": cleaned["value_column"], "value": value}]
        chart = "kpi"
    elif operation == "trend":
        rows = _trend(data, cleaned["time_column"], cleaned["value_column"], cleaned["agg"])
        value = rows[-1]["value"] if rows else None
        chart = cleaned["chart"] if cleaned["chart"] in {"line", "area"} else "line"
    else:
        rows = _grouped(data, cleaned["group_column"], cleaned["value_column"], cleaned["agg"])
        rows = rows[: cleaned["limit"]]
        value = rows[0]["value"] if rows else None
        chart = _chart_for_groups(cleaned["chart"], len(rows))
    return {
        "operation": operation,
        "aggregation": cleaned["agg"],
        "value_column": cleaned["value_column"],
        "group_column": cleaned["group_column"],
        "time_column": cleaned["time_column"],
        "value": value,
        "rows": rows,
        "chart": chart,
        "row_count": int(len(data)),
    }


def calculated_facts(result: dict) -> list[str]:
    if result["operation"] == "summary":
        return [f"The filtered dataset has {int(result['value'])} rows."]
    if result["operation"] == "aggregate":
        return [f"The {result['aggregation']} of {result['value_column']} is {_plain(result['value'])}."]
    if not result["rows"]:
        return ["No rows matched this question."]
    lead = result["rows"][0]
    label = "period" if result["operation"] == "trend" else result["group_column"]
    facts = [f"The highest {label} is {lead['label']} at {_plain(lead['value'])}."]
    if len(result["rows"]) > 1:
        last = result["rows"][-1] if result["operation"] != "trend" else min(result["rows"], key=lambda row: row["value"])
        facts.append(f"The lowest value in this result is {last['label']} at {_plain(last['value'])}.")
    return facts


def _column(value, known: set[str], *, required: bool) -> str | None:
    if value is None or str(value).strip() == "":
        if required:
            raise AppError("invalid_plan", "The analysis plan did not name a valid column.", 422)
        return None
    name = str(value).strip()
    if name not in known:
        raise AppError("invalid_plan", f"{name} is not a column in this dataset.", 422)
    return name


def _filter(frame: pd.DataFrame, filters: list[dict]) -> pd.DataFrame:
    data = frame
    for item in filters:
        series = data[item["column"]]
        value = item["value"]
        operator = item["op"]
        if operator == "contains":
            mask = series.astype(str).str.contains(str(value), case=False, na=False, regex=False)
        else:
            numeric = pd.to_numeric(series, errors="coerce")
            try:
                number = float(value)
            except (TypeError, ValueError):
                number = None
            compared = numeric if number is not None and numeric.notna().any() else series.astype(str)
            target = number if number is not None and numeric.notna().any() else str(value)
            if operator == "eq":
                mask = compared == target
            elif operator == "ne":
                mask = compared != target
            elif operator == "gt":
                mask = compared > target
            elif operator == "lt":
                mask = compared < target
            elif operator == "gte":
                mask = compared >= target
            else:
                mask = compared <= target
        data = data.loc[mask.fillna(False)]
    return data


def _aggregate(series: pd.Series, aggregation: str) -> float:
    if aggregation == "count":
        return float(series.notna().sum())
    numeric = pd.to_numeric(series, errors="coerce")
    if not numeric.notna().any():
        raise AppError("invalid_plan", f"{series.name} is not numeric.", 422)
    if aggregation == "sum":
        return round(float(numeric.sum()), 4)
    if aggregation == "mean":
        return round(float(numeric.mean()), 4)
    if aggregation == "min":
        return round(float(numeric.min()), 4)
    return round(float(numeric.max()), 4)


def _grouped(frame: pd.DataFrame, group_column: str, value_column: str, aggregation: str) -> list[dict]:
    labels = frame[group_column].fillna("(blank)").astype(str)
    if aggregation == "count":
        grouped = labels.value_counts()
        rows = [{"label": str(label), "value": float(value)} for label, value in grouped.items()]
    else:
        numeric = pd.to_numeric(frame[value_column], errors="coerce")
        table = pd.DataFrame({"label": labels, "value": numeric}).dropna(subset=["value"])
        if table.empty:
            raise AppError("invalid_plan", f"{value_column} is not numeric.", 422)
        grouped = table.groupby("label", sort=False)["value"].agg(aggregation)
        rows = [{"label": str(label), "value": round(float(value), 4)} for label, value in grouped.items()]
        rows.sort(key=lambda row: row["value"], reverse=True)
    return rows


def _trend(frame: pd.DataFrame, time_column: str, value_column: str, aggregation: str) -> list[dict]:
    dates = pd.to_datetime(frame[time_column], errors="coerce")
    if not dates.notna().any():
        raise AppError("invalid_plan", f"{time_column} does not contain dates.", 422)
    working = frame.loc[dates.notna()].copy()
    working["_period"] = dates.loc[dates.notna()].dt.to_period("M").astype(str)
    if aggregation == "count":
        grouped = working.groupby("_period", sort=True).size()
        return [{"label": str(label), "value": float(value)} for label, value in grouped.items()]
    working["_value"] = pd.to_numeric(working[value_column], errors="coerce")
    table = working.dropna(subset=["_value"])
    if table.empty:
        raise AppError("invalid_plan", f"{value_column} is not numeric.", 422)
    grouped = table.groupby("_period", sort=True)["_value"].agg(aggregation)
    return [{"label": str(label), "value": round(float(value), 4)} for label, value in grouped.items()]


def _chart_for_groups(requested: str, count: int) -> str:
    if count == 0:
        return "table"
    if requested == "pie" and count <= 6:
        return "pie"
    if requested in {"bar", "table"}:
        return requested
    return "bar"


def _plain(value) -> str:
    if value is None:
        return "0"
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return f"{number:.2f}"
