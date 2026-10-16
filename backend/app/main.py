import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import InterfaceError, OperationalError

from app.config import get_settings
from app.db import SessionLocal
from app.routers import assignments, files, gradings, health, submissions
from app.services.llm_client import LLMConfigError, LLMError, LLMOutputError, TransientLLMError
from app.services.maintenance import fail_stale_gradings

settings = get_settings()
logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        await fail_stale_gradings(SessionLocal, settings.grading_stale_minutes)
    except Exception:
        logger.warning("Could not check for stale gradings at startup", exc_info=True)
    yield


app = FastAPI(title="RubricCheck API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def limit_request_size(request: Request, call_next):  # type: ignore[no-untyped-def]
    """Reject oversized bodies up front, before they are read into memory.

    Only checks the declared Content-Length. Individual fields (draft length, upload
    size) are validated again in the routes.
    """
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.max_request_bytes:
        return JSONResponse(
            status_code=413,
            content={"detail": f"Request is too large (limit {settings.max_request_bytes // (1024 * 1024)} MB)."},
        )
    return await call_next(request)


app.include_router(health.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(assignments.router, prefix="/api")
app.include_router(submissions.router, prefix="/api")
app.include_router(gradings.router, prefix="/api")


def _error(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


@app.exception_handler(LLMConfigError)
async def _handle_llm_config(_: Request, exc: LLMConfigError) -> JSONResponse:
    return _error(503, f"The AI service is not configured: {exc}")


@app.exception_handler(LLMOutputError)
async def _handle_llm_output(_: Request, exc: LLMOutputError) -> JSONResponse:
    return _error(502, "The AI returned output we could not use, even after a retry. Please try again.")


@app.exception_handler(TransientLLMError)
async def _handle_llm_transient(_: Request, exc: TransientLLMError) -> JSONResponse:
    return _error(503, "The AI service is busy or unavailable. Please try again.")


@app.exception_handler(LLMError)
async def _handle_llm_error(_: Request, exc: LLMError) -> JSONResponse:
    return _error(502, "The AI service returned an error.")


@app.exception_handler(OperationalError)
@app.exception_handler(InterfaceError)
@app.exception_handler(ConnectionError)
async def _handle_database_unavailable(_: Request, exc: Exception) -> JSONResponse:
    logger.error("Database unavailable: %s", exc)
    return _error(503, "The database is unavailable right now. Please try again in a moment.")


@app.exception_handler(Exception)
async def _handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
    # Log the details; never send stack traces or internals to the client.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return _error(500, "Something went wrong on our side. Please try again.")
