import pytest

pytestmark = pytest.mark.db


def test_worker_runs_outside_the_request_and_records_success():
    from app.db.session import SessionLocal
    from app.models.enums import JobStatus
    from app.models.operations import Job
    from app.services.jobs import enqueue_job
    from app.workers.runner import process_next

    db = SessionLocal()
    try:
        job = enqueue_job(db, job_type="ping", payload={"source": "test"})
        db.commit()
        assert process_next(db) is True
        saved = db.get(Job, job.id)
        assert saved is not None
        assert saved.status == JobStatus.succeeded
        assert saved.payload["pong"] is True
        assert process_next(db) is False
    finally:
        db.close()


def test_unknown_job_fails_without_retry():
    from app.db.session import SessionLocal
    from app.models.enums import JobStatus
    from app.models.operations import Job
    from app.services.jobs import enqueue_job
    from app.workers.runner import process_next

    db = SessionLocal()
    try:
        job = enqueue_job(db, job_type="not-a-real-job", payload={})
        db.commit()
        assert process_next(db) is True
        saved = db.get(Job, job.id)
        assert saved is not None
        assert saved.status == JobStatus.failed
        assert "No handler" in (saved.last_error or "")
    finally:
        db.close()
