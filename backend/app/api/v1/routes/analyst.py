import uuid

from fastapi import APIRouter, Depends, File, Header, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.dependencies import get_current_user
from app.core.errors import AppError
from app.core.security import generation_rate_limiter, upload_rate_limiter
from app.db.session import get_db
from app.models.identity import Profile
from app.schemas.analyst import AnalysisResponse, AskRequest, DatasetResponse
from app.services.analyst.service import AnalystService
from app.services.organizations import OrganizationService

router = APIRouter(prefix="/analyst", tags=["analyst"])


def _organization_id(x_organization_id: str | None = Header(default=None)) -> uuid.UUID:
    if not x_organization_id:
        raise AppError("organization_required", "Choose an organization before continuing.", 400)
    try:
        return uuid.UUID(x_organization_id)
    except ValueError as exc:
        raise AppError("invalid_organization", "The organization id is not valid.", 400) from exc


def _member(
    organization_id: uuid.UUID = Depends(_organization_id),
    user: Profile = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> tuple[uuid.UUID, Profile, Session]:
    OrganizationService(db).require_context(user, organization_id)
    return organization_id, user, db


def _status(value) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _dataset_response(dataset) -> DatasetResponse:
    return DatasetResponse(
        id=dataset.id,
        name=dataset.name,
        status=_status(dataset.status),
        row_count=dataset.row_count,
        column_count=dataset.column_count,
        error_message=dataset.error_message,
        profile=dataset.schema_json or {},
        created_at=dataset.created_at,
    )


def _analysis_response(analysis) -> AnalysisResponse:
    result = analysis.result_json or {}
    return AnalysisResponse(
        id=analysis.id,
        dataset_id=analysis.dataset_id,
        question=analysis.question,
        status=_status(analysis.status),
        error_message=analysis.error_message,
        calculated=result.get("calculated"),
        facts=result.get("facts") or [],
        interpretation=result.get("interpretation"),
        insights=result.get("insights") or [],
        chart=analysis.chart_spec,
        created_at=analysis.created_at,
    )


@router.get("/datasets", response_model=list[DatasetResponse])
def list_datasets(context: tuple = Depends(_member)) -> list[DatasetResponse]:
    organization_id, _user, db = context
    return [_dataset_response(dataset) for dataset in AnalystService(db).list_datasets(organization_id)]


@router.post("/datasets", response_model=DatasetResponse)
def upload_dataset(file: UploadFile = File(...), context: tuple = Depends(_member)) -> DatasetResponse:
    organization_id, user, db = context
    upload_rate_limiter.check(str(user.id))
    content = file.file.read(get_settings().analyst_max_bytes + 1)
    dataset = AnalystService(db).upload(
        organization_id=organization_id,
        user_id=user.id,
        filename=file.filename or "",
        content=content,
    )
    return _dataset_response(dataset)


@router.get("/datasets/{dataset_id}", response_model=DatasetResponse)
def get_dataset(dataset_id: uuid.UUID, context: tuple = Depends(_member)) -> DatasetResponse:
    organization_id, _user, db = context
    return _dataset_response(AnalystService(db).get_dataset(organization_id, dataset_id))


@router.delete("/datasets/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: uuid.UUID, context: tuple = Depends(_member)) -> Response:
    organization_id, _user, db = context
    AnalystService(db).delete_dataset(organization_id, dataset_id)
    return Response(status_code=204)


@router.get("/datasets/{dataset_id}/summary.csv")
def summary_csv(dataset_id: uuid.UUID, context: tuple = Depends(_member)) -> Response:
    organization_id, _user, db = context
    body = AnalystService(db).summary_csv(organization_id, dataset_id)
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="dataset-summary.csv"'},
    )


@router.post("/datasets/{dataset_id}/ask", response_model=AnalysisResponse)
def ask(dataset_id: uuid.UUID, body: AskRequest, context: tuple = Depends(_member)) -> AnalysisResponse:
    organization_id, user, db = context
    generation_rate_limiter.check(str(user.id))
    analysis = AnalystService(db).ask(
        organization_id=organization_id,
        user_id=user.id,
        dataset_id=dataset_id,
        question=body.question,
    )
    return _analysis_response(analysis)


@router.get("/datasets/{dataset_id}/analyses", response_model=list[AnalysisResponse])
def list_analyses(dataset_id: uuid.UUID, context: tuple = Depends(_member)) -> list[AnalysisResponse]:
    organization_id, _user, db = context
    return [_analysis_response(item) for item in AnalystService(db).list_analyses(organization_id, dataset_id)]


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
def get_analysis(analysis_id: uuid.UUID, context: tuple = Depends(_member)) -> AnalysisResponse:
    organization_id, _user, db = context
    return _analysis_response(AnalystService(db).get_analysis(organization_id, analysis_id))


@router.delete("/analyses/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: uuid.UUID, context: tuple = Depends(_member)) -> Response:
    organization_id, _user, db = context
    AnalystService(db).delete_analysis(organization_id, analysis_id)
    return Response(status_code=204)


@router.get("/analyses/{analysis_id}/export.csv")
def export_csv(analysis_id: uuid.UUID, context: tuple = Depends(_member)) -> Response:
    organization_id, _user, db = context
    body = AnalystService(db).result_csv(organization_id, analysis_id)
    return Response(
        content=body,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="analysis.csv"'},
    )


@router.get("/analyses/{analysis_id}/report.pdf")
def export_pdf(analysis_id: uuid.UUID, context: tuple = Depends(_member)) -> Response:
    organization_id, _user, db = context
    body = AnalystService(db).report_pdf(organization_id, analysis_id)
    return Response(
        content=body,
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="analysis-report.pdf"'},
    )
