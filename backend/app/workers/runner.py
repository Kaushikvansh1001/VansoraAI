import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.db.session import SessionLocal
from app.models.enums import JobStatus
from app.models.operations import Job
from app.workers.handlers import HANDLERS

logger = logging.getLogger("vansoraai.worker")


def process_next(db: Session) -> bool:
    """Claim one due job. Returns False when the queue is empty.

    The caller owns the session. This function commits the claim result.
    """
    job = db.scalar(
        select(Job)
        .where(Job.status == JobStatus.pending, Job.run_after <= func.now())
        .order_by(Job.run_after.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return False

    job_id = job.id
    job.status = JobStatus.running
    db.flush()
    handler = HANDLERS.get(job.job_type)
    if handler is None:
        job.status = JobStatus.failed
        job.last_error = f"No handler is registered for '{job.job_type}'."
        db.commit()
        return True

    try:
        handler(db, job)
    except Exception as exc:
        db.rollback()
        failed = db.get(Job, job_id)
        if failed is None:
            raise
        failed.attempts += 1
        failed.last_error = str(exc)[:1000]
        if failed.attempts >= failed.max_attempts:
            failed.status = JobStatus.failed
        else:
            failed.status = JobStatus.pending
            delay = timedelta(seconds=2**failed.attempts)
            failed.run_after = datetime.now(timezone.utc) + delay
        db.commit()
        logger.warning("Job %s failed: %s", job_id, exc)
        return True

    job.status = JobStatus.succeeded
    job.last_error = None
    db.commit()
    return True


def main() -> None:
    configure_logging()
    settings = get_settings()
    logger.info("Worker started. Poll interval %.1fs. HTTP server is a separate process.", settings.job_poll_seconds)
    while True:
        db = SessionLocal()
        try:
            worked = process_next(db)
        except Exception:
            db.rollback()
            logger.exception("Worker loop error")
            worked = False
        finally:
            db.close()
        if not worked:
            time.sleep(settings.job_poll_seconds)


if __name__ == "__main__":
    main()
