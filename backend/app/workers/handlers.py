from collections.abc import Callable

from sqlalchemy.orm import Session

from app.models.operations import Job

Handler = Callable[[Session, Job], None]
HANDLERS: dict[str, Handler] = {}


def handles(job_type: str) -> Callable[[Handler], Handler]:
    def register(function: Handler) -> Handler:
        HANDLERS[job_type] = function
        return function

    return register


@handles("ping")
def handle_ping(_db: Session, job: Job) -> None:
    job.payload = {**job.payload, "pong": True}
