import uuid

from sqlalchemy.orm import Session

from app.models.enums import JobStatus
from app.models.operations import Job


def enqueue_job(
    db: Session,
    *,
    job_type: str,
    payload: dict | None = None,
    organization_id: uuid.UUID | None = None,
) -> Job:
    """Record work for the separate worker process. The HTTP process does not run it."""
    job = Job(
        job_type=job_type,
        payload=payload or {},
        organization_id=organization_id,
        status=JobStatus.pending,
    )
    db.add(job)
    db.flush()
    return job
