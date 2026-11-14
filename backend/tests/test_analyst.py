import uuid
from datetime import datetime, timezone
from io import BytesIO

import pandas as pd
import pytest

from app.core.errors import AppError
from app.models.analytics import Dataset
from app.models.enums import DatasetStatus
from app.services.ai.exceptions import ProviderChainFailed
from app.services.ai.models import GenerationOutcome, ProviderResponse, TokenUsage
from app.services.analyst.engine import execute, validate_plan
from app.services.analyst.files import load_table
from app.services.analyst.profile import profile_frame
from app.services.analyst.service import AnalystService, _parse_json

CSV = b"product,region,revenue,order_date\nA,West,10,2024-01-15\nB,East,30,2024-02-15\nA,West,20,2024-03-15\nA,West,10,2024-01-15\n"


def limits():
    return {"max_bytes": 5_000_000, "max_rows": 100, "max_columns": 10}


def frame():
    return load_table("sales.csv", CSV, **limits())


def test_csv_profile_counts_rows_missing_values_and_duplicates():
    table = frame()
    profile = profile_frame(table)
    assert len(table) == 4
    assert profile["duplicate_rows"] == 1
    revenue = next(column for column in profile["columns"] if column["name"] == "revenue")
    assert revenue["type"] == "number"
    assert revenue["numeric"]["sum"] == 70
    dated = next(column for column in profile["columns"] if column["name"] == "order_date")
    assert dated["type"] == "date"
    assert dated["date_min"] == "2024-01-15"
    assert dated["date_max"] == "2024-03-15"


def test_excel_upload_is_profiled():
    buffer = BytesIO()
    pd.DataFrame({"revenue": [5, 15]}).to_excel(buffer, index=False)
    table = load_table("sales.xlsx", buffer.getvalue(), **limits())
    assert profile_frame(table)["columns"][0]["numeric"]["sum"] == 20


def test_invalid_and_oversized_files_are_rejected():
    with pytest.raises(AppError) as kind:
        load_table("notes.txt", b"a,b\n1,2\n", **limits())
    assert kind.value.code == "unsupported_file"
    with pytest.raises(AppError) as size:
        load_table("sales.csv", b"a\n" + b"1\n" * 5, max_bytes=100, max_rows=2, max_columns=5)
    assert size.value.code == "file_too_large"


def test_sum_and_grouped_ranking_use_the_file_numbers():
    table = frame()
    total = execute(table, {"operation": "aggregate", "value_column": "revenue", "agg": "sum", "chart": "kpi"})
    assert total["value"] == 70
    ranking = execute(
        table,
        {"operation": "top", "value_column": "revenue", "group_column": "product", "agg": "sum", "limit": 1, "chart": "bar"},
    )
    assert ranking["rows"][0] == {"label": "A", "value": 40.0}
    trend = execute(
        table,
        {"operation": "trend", "value_column": "revenue", "time_column": "order_date", "agg": "sum", "chart": "line"},
    )
    assert [row["label"] for row in trend["rows"]] == ["2024-01", "2024-02", "2024-03"]
    assert trend["chart"] == "line"


def test_contains_filter_matches_the_text_literally():
    frame = pd.DataFrame({"product": ["A.B", "AB"], "revenue": [1, 2]})
    result = execute(
        frame,
        {
            "operation": "groupby",
            "group_column": "product",
            "value_column": "revenue",
            "agg": "sum",
            "chart": "bar",
            "filters": [{"column": "product", "op": "contains", "value": "A.B"}],
        },
    )
    assert [row["label"] for row in result["rows"]] == ["A.B"]


def test_unknown_column_and_operation_are_rejected():
    with pytest.raises(AppError) as column:
        validate_plan({"operation": "aggregate", "value_column": "profit", "agg": "sum", "chart": "kpi"}, ["revenue"])
    assert column.value.code == "invalid_plan"
    with pytest.raises(AppError):
        validate_plan({"operation": "exec", "agg": "sum", "chart": "table"}, ["revenue"])


def test_malformed_plan_text_is_rejected():
    with pytest.raises(AppError) as exc:
        _parse_json("not json")
    assert exc.value.code == "invalid_plan"


def test_other_organization_dataset_is_not_analyzed():
    class MissingDb:
        def scalar(self, _statement):
            return None

    class Manager:
        def generate(self, *_args, **_kwargs):
            raise AssertionError("The model should not be called.")

    with pytest.raises(AppError) as exc:
        AnalystService(MissingDb(), manager=Manager()).ask(
            organization_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            dataset_id=uuid.uuid4(),
            question="What is the total revenue?",
        )
    assert exc.value.code == "not_found"


def test_provider_failure_does_not_invent_a_result():
    dataset = Dataset(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        name="sales.csv",
        storage_path="org/file.csv",
        row_count=4,
        column_count=4,
        schema_json={"columns": []},
        status=DatasetStatus.ready,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    class FoundDb:
        def scalar(self, _statement):
            return dataset

        def add(self, _obj):
            return None

        def flush(self):
            return None

    class Manager:
        def generate(self, *_args, **_kwargs):
            raise ProviderChainFailed([])

    class Store:
        def download(self, _path):
            return CSV

    analysis = AnalystService(FoundDb(), storage=Store(), manager=Manager()).ask(
        organization_id=dataset.organization_id,
        user_id=uuid.uuid4(),
        dataset_id=dataset.id,
        question="What is the total revenue?",
    )
    assert analysis.status.value == "failed"
    assert analysis.result_json is None


def test_successful_plan_returns_calculated_facts():
    dataset = Dataset(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        uploaded_by=uuid.uuid4(),
        name="sales.csv",
        storage_path="org/file.csv",
        row_count=4,
        column_count=4,
        schema_json=profile_frame(frame()),
        status=DatasetStatus.ready,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    calls = {"n": 0}

    class FoundDb:
        def scalar(self, _statement):
            return dataset

        def add(self, _obj):
            return None

        def flush(self):
            return None

    class Manager:
        def generate(self, request, **_kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                text = '{"operation":"aggregate","value_column":"revenue","agg":"sum","chart":"kpi"}'
            else:
                text = "The file total is 70."
            usage = TokenUsage(1, 1, "provider")
            return GenerationOutcome(ProviderResponse("gemini", "gemini-flash-lite-latest", text, usage, 5), None)

    class Store:
        def download(self, _path):
            return CSV

    analysis = AnalystService(FoundDb(), storage=Store(), manager=Manager()).ask(
        organization_id=dataset.organization_id,
        user_id=uuid.uuid4(),
        dataset_id=dataset.id,
        question="What is the total revenue?",
    )
    assert analysis.result_json["calculated"]["value"] == 70
    assert "70" in analysis.result_json["facts"][0]
    assert analysis.result_json["interpretation"] == "The file total is 70."
    assert analysis.chart_spec["type"] == "kpi"
