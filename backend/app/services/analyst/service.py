import json
import re
import uuid
from datetime import datetime, timezone
from io import StringIO

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.errors import AppError
from app.models.analytics import Dataset, DatasetAnalysis
from app.models.enums import AnalysisStatus, DatasetStatus
from app.repositories.analyst import AnalystRepository
from app.services.ai.exceptions import ProviderChainFailed
from app.services.ai.models import GenerationRequest
from app.services.ai.provider_manager import ProviderManager
from app.services.ai.usage_tracker import UsageTracker
from app.services.analyst.engine import calculated_facts, execute
from app.services.analyst.files import content_type, load_table
from app.services.analyst.profile import profile_frame
from app.services.storage import SupabaseStorage, build_object_path

PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "operation": {"type": "string"},
        "value_column": {"type": "string"},
        "group_column": {"type": "string"},
        "time_column": {"type": "string"},
        "agg": {"type": "string"},
        "limit": {"type": "integer"},
        "chart": {"type": "string"},
        "filters": {"type": "array"},
    },
    "required": ["operation", "agg", "chart"],
}


class AnalystService:
    def __init__(self, db: Session, storage: SupabaseStorage | None = None, manager=None, settings: Settings | None = None) -> None:
        self.db = db
        self.storage = storage or SupabaseStorage()
        self.manager = manager
        self.settings = settings or get_settings()
        self.repository = AnalystRepository(db)

    def list_datasets(self, organization_id: uuid.UUID) -> list[Dataset]:
        return self.repository.list_datasets(organization_id)

    def get_dataset(self, organization_id: uuid.UUID, dataset_id: uuid.UUID) -> Dataset:
        dataset = self.repository.get_dataset(organization_id, dataset_id)
        if dataset is None:
            raise AppError("not_found", "That dataset is not in this organization.", 404)
        return dataset

    def upload(self, *, organization_id: uuid.UUID, user_id: uuid.UUID, filename: str, content: bytes) -> Dataset:
        frame = load_table(
            filename,
            content,
            max_bytes=self.settings.analyst_max_bytes,
            max_rows=self.settings.analyst_max_rows,
            max_columns=self.settings.analyst_max_columns,
        )
        profile = profile_frame(frame)
        dataset = Dataset(
            id=uuid.uuid4(),
            organization_id=organization_id,
            uploaded_by=user_id,
            name=filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1][:200],
            storage_path="",
            row_count=int(len(frame)),
            column_count=int(len(frame.columns)),
            schema_json=profile,
            status=DatasetStatus.pending,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        self.db.add(dataset)
        self.db.flush()
        dataset.storage_path = build_object_path(organization_id, dataset.id, dataset.name)
        try:
            self.storage.upload(dataset.storage_path, content, content_type(dataset.name))
        except AppError as exc:
            dataset.status = DatasetStatus.failed
            dataset.error_message = exc.message
            self.db.flush()
            return dataset
        dataset.status = DatasetStatus.ready
        dataset.error_message = None
        self.db.flush()
        return dataset

    def delete_dataset(self, organization_id: uuid.UUID, dataset_id: uuid.UUID) -> None:
        dataset = self.get_dataset(organization_id, dataset_id)
        if dataset.storage_path:
            self.storage.delete(dataset.storage_path)
        self.db.delete(dataset)
        self.db.flush()

    def ask(self, *, organization_id: uuid.UUID, user_id: uuid.UUID, dataset_id: uuid.UUID, question: str) -> DatasetAnalysis:
        dataset = self.get_dataset(organization_id, dataset_id)
        if dataset.status != DatasetStatus.ready:
            raise AppError("not_ready", "This dataset is not ready.", 400)
        analysis = DatasetAnalysis(
            id=uuid.uuid4(),
            dataset_id=dataset.id,
            organization_id=organization_id,
            user_id=user_id,
            question=question.strip(),
            status=AnalysisStatus.running,
            created_at=datetime.now(timezone.utc),
        )
        self.db.add(analysis)
        self.db.flush()
        try:
            content = self.storage.download(dataset.storage_path)
            frame = load_table(
                dataset.name,
                content,
                max_bytes=self.settings.analyst_max_bytes,
                max_rows=self.settings.analyst_max_rows,
                max_columns=self.settings.analyst_max_columns,
            )
            plan_text = self._generate(_plan_prompt(question, dataset.schema_json), organization_id, user_id, PLAN_SCHEMA)
            plan = _parse_json(plan_text)
            calculated = execute(frame, plan)
            facts = calculated_facts(calculated)
            interpretation = self._explain(question, calculated, facts, organization_id, user_id)
        except AppError as exc:
            analysis.status = AnalysisStatus.failed
            analysis.error_message = exc.message
            self.db.flush()
            return analysis
        except ProviderChainFailed:
            analysis.status = AnalysisStatus.failed
            analysis.error_message = "No model could analyze this dataset."
            self.db.flush()
            return analysis
        analysis.plan_json = plan
        analysis.result_json = {
            "calculated": calculated,
            "facts": facts,
            "interpretation": interpretation,
            "insights": _insights(dataset.schema_json, calculated),
        }
        analysis.chart_spec = {"type": calculated["chart"], "data": calculated["rows"]}
        analysis.status = AnalysisStatus.succeeded
        analysis.error_message = None
        self.db.flush()
        return analysis

    def list_analyses(self, organization_id: uuid.UUID, dataset_id: uuid.UUID) -> list[DatasetAnalysis]:
        self.get_dataset(organization_id, dataset_id)
        return self.repository.list_analyses(organization_id, dataset_id)

    def get_analysis(self, organization_id: uuid.UUID, analysis_id: uuid.UUID) -> DatasetAnalysis:
        analysis = self.repository.get_analysis(organization_id, analysis_id)
        if analysis is None:
            raise AppError("not_found", "That analysis is not in this organization.", 404)
        return analysis

    def delete_analysis(self, organization_id: uuid.UUID, analysis_id: uuid.UUID) -> None:
        analysis = self.get_analysis(organization_id, analysis_id)
        self.db.delete(analysis)
        self.db.flush()

    def summary_csv(self, organization_id: uuid.UUID, dataset_id: uuid.UUID) -> str:
        dataset = self.get_dataset(organization_id, dataset_id)
        buffer = StringIO()
        buffer.write("column,type,missing,unique,min,max,mean,sum,date_min,date_max\n")
        for column in (dataset.schema_json or {}).get("columns", []):
            numeric = column.get("numeric") or {}
            buffer.write(
                ",".join(
                    _csv(value)
                    for value in (
                        column.get("name"),
                        column.get("type"),
                        column.get("missing"),
                        column.get("unique"),
                        numeric.get("min", ""),
                        numeric.get("max", ""),
                        numeric.get("mean", ""),
                        numeric.get("sum", ""),
                        column.get("date_min") or "",
                        column.get("date_max") or "",
                    )
                )
            )
            buffer.write("\n")
        return buffer.getvalue()

    def result_csv(self, organization_id: uuid.UUID, analysis_id: uuid.UUID) -> str:
        analysis = self.get_analysis(organization_id, analysis_id)
        rows = ((analysis.result_json or {}).get("calculated") or {}).get("rows") or []
        buffer = StringIO()
        buffer.write("label,value\n")
        for row in rows:
            buffer.write(f"{_csv(row.get('label'))},{_csv(row.get('value'))}\n")
        return buffer.getvalue()

    def report_pdf(self, organization_id: uuid.UUID, analysis_id: uuid.UUID) -> bytes:
        from fpdf import FPDF

        analysis = self.get_analysis(organization_id, analysis_id)
        result = analysis.result_json or {}
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font("Helvetica", size=16)
        pdf.multi_cell(0, 10, "Analysis report")
        pdf.set_font("Helvetica", size=12)
        pdf.multi_cell(0, 8, _latin(analysis.question))
        pdf.ln(2)
        pdf.set_font("Helvetica", style="B", size=12)
        pdf.cell(0, 8, "Calculated")
        pdf.ln(8)
        pdf.set_font("Helvetica", size=11)
        for fact in result.get("facts") or []:
            pdf.multi_cell(0, 7, _latin(fact))
        pdf.ln(2)
        pdf.set_font("Helvetica", style="B", size=12)
        pdf.cell(0, 8, "Interpretation")
        pdf.ln(8)
        pdf.set_font("Helvetica", size=11)
        pdf.multi_cell(0, 7, _latin(result.get("interpretation") or "No written interpretation."))
        return bytes(pdf.output())

    def _generate(self, prompt: str, organization_id, user_id, schema: dict | None) -> str:
        outcome = self._provider().generate(
            GenerationRequest(prompt=prompt, json_schema=schema),
            organization_id=organization_id,
            user_id=user_id,
            feature="data_analyst",
        )
        return outcome.response.text

    def _explain(self, question: str, calculated: dict, facts: list[str], organization_id, user_id) -> str:
        prompt = (
            "Explain the calculated result in plain sentences. "
            "Use only the numbers in the facts and result. Do not invent figures. "
            "Keep recommendations separate from the numbers.\n\n"
            f"Question: {question}\nFacts: {json.dumps(facts)}\nResult: {json.dumps(calculated)}"
        )
        try:
            return self._generate(prompt, organization_id, user_id, None).strip()
        except ProviderChainFailed:
            return "The numbers above were calculated from the file. A written explanation was not available."

    def _provider(self) -> ProviderManager:
        if self.manager is None:
            self.manager = ProviderManager(self.settings, sink=UsageTracker(self.db))
        return self.manager


def _plan_prompt(question: str, profile: dict) -> str:
    columns = [
        f"{column['name']} ({column['type']})"
        for column in (profile or {}).get("columns", [])
    ]
    return (
        "Choose one analysis plan for the question. Use only these columns. "
        "operation is one of aggregate, groupby, trend, top, summary. "
        "agg is one of sum, mean, count, min, max. "
        "chart is one of bar, line, pie, area, table, kpi. "
        "Use trend only when a date column should be grouped by month. "
        "Return JSON only.\n\n"
        f"Columns: {', '.join(columns)}\nQuestion: {question}"
    )


def _parse_json(text: str) -> dict:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip().strip("`").strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AppError("invalid_plan", "The analysis plan could not be read. Ask a more specific question.", 422) from exc
    if not isinstance(value, dict):
        raise AppError("invalid_plan", "The analysis plan could not be read. Ask a more specific question.", 422)
    return value


def _insights(profile: dict, calculated: dict) -> list[str]:
    notes = []
    duplicates = int((profile or {}).get("duplicate_rows") or 0)
    if duplicates:
        notes.append(f"{duplicates} duplicate rows were found in the dataset.")
    missing = [
        column
        for column in (profile or {}).get("columns", [])
        if int(column.get("missing") or 0) > 0
    ]
    if missing:
        worst = max(missing, key=lambda column: int(column["missing"]))
        notes.append(f"{worst['name']} has {worst['missing']} missing values.")
    rows = calculated.get("rows") or []
    if len(rows) >= 2 and calculated.get("operation") in {"groupby", "top"}:
        notes.append(f"{rows[0]['label']} is the highest category in this result.")
        notes.append(f"{rows[-1]['label']} is the lowest category in this result.")
    return notes


def _csv(value) -> str:
    text = "" if value is None else str(value)
    if any(character in text for character in ",\"\n"):
        return '"' + text.replace('"', '""') + '"'
    return text


def _latin(text: str) -> str:
    return text.encode("latin-1", errors="replace").decode("latin-1")
