import uuid

from fastapi import APIRouter, Depends, File, Header, UploadFile
from sqlalchemy.orm import Session

from app.core.dependencies import get_current_user
from app.core.errors import AppError
from app.db.session import get_db
from app.models.identity import Profile
from app.schemas.knowledge import AnswerResponse, AskRequest, CitationResponse, DocumentResponse
from app.services.knowledge.service import KnowledgeService
from app.services.knowledge.text import MAX_BYTES
from app.services.organizations import OrganizationService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


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


def _document_response(document) -> DocumentResponse:
    status = document.status.value if hasattr(document.status, "value") else str(document.status)
    return DocumentResponse(
        id=document.id,
        filename=document.filename,
        status=status,
        size_bytes=document.size_bytes,
        error_message=document.error_message,
        created_at=document.created_at,
    )


@router.get("/documents", response_model=list[DocumentResponse])
def list_documents(context: tuple = Depends(_member)) -> list[DocumentResponse]:
    organization_id, _user, db = context
    return [_document_response(document) for document in KnowledgeService(db).list_documents(organization_id)]


@router.post("/documents", response_model=DocumentResponse)
def upload_document(file: UploadFile = File(...), context: tuple = Depends(_member)) -> DocumentResponse:
    organization_id, user, db = context
    content = file.file.read(MAX_BYTES + 1)
    document = KnowledgeService(db).upload(
        organization_id=organization_id,
        user_id=user.id,
        filename=file.filename or "",
        content=content,
    )
    return _document_response(document)


@router.post("/ask", response_model=AnswerResponse)
def ask(body: AskRequest, context: tuple = Depends(_member)) -> AnswerResponse:
    organization_id, user, db = context
    answer = KnowledgeService(db).ask(
        organization_id=organization_id,
        user_id=user.id,
        question=body.question,
        document_id=body.document_id,
    )
    return AnswerResponse(
        answer=answer.answer,
        provider=answer.provider,
        model=answer.model,
        citations=[
            CitationResponse(
                document_id=item.document_id,
                filename=item.filename,
                chunk_index=item.chunk_index,
                excerpt=item.excerpt,
            )
            for item in answer.citations
        ],
    )
