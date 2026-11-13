import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import AppError
from app.core.logging import configure_logging

configure_logging()
logger = logging.getLogger("vansoraai")
settings = get_settings()

app = FastAPI(
    title="VansoraAI API",
    version="0.1.0",
    summary="Business intelligence and workflow automation API.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Organization-Id"],
)
app.include_router(api_router, prefix="/api/v1")


@app.middleware("http")
async def request_context(request: Request, call_next):
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-Id"] = request_id
    logger.info("%s %s %s %s", request.method, request.url.path, response.status_code, request_id)
    return response


def _error_body(request: Request, code: str, message: str) -> dict:
    request_id = getattr(request.state, "request_id", None)
    return {"error": {"code": code, "message": message, "request_id": request_id}}


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=_error_body(request, exc.code, exc.message))


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    message = "Check the submitted fields."
    if exc.errors():
        first = exc.errors()[0]
        location = [str(part) for part in first.get("loc", []) if part not in {"body", "query", "header"}]
        detail = first.get("msg", message)
        message = f"{' '.join(location)}: {detail}" if location else str(detail)
    return JSONResponse(status_code=422, content=_error_body(request, "validation_error", message))


@app.exception_handler(Exception)
async def unhandled_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error")
    return JSONResponse(
        status_code=500,
        content=_error_body(request, "internal_error", "Something went wrong. Try again."),
    )
