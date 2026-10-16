from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.routers import assignments, files, health
from app.services.llm_client import LLMConfigError, LLMError, LLMOutputError, TransientLLMError

settings = get_settings()

app = FastAPI(title="RubricCheck API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(assignments.router, prefix="/api")


def _llm_error_response(status_code: int, detail: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"detail": detail})


@app.exception_handler(LLMConfigError)
async def _handle_llm_config(_: Request, exc: LLMConfigError) -> JSONResponse:
    return _llm_error_response(503, f"The AI service is not configured: {exc}")


@app.exception_handler(LLMOutputError)
async def _handle_llm_output(_: Request, exc: LLMOutputError) -> JSONResponse:
    return _llm_error_response(
        502, "The AI returned output we could not use, even after a retry. Please try again."
    )


@app.exception_handler(TransientLLMError)
async def _handle_llm_transient(_: Request, exc: TransientLLMError) -> JSONResponse:
    return _llm_error_response(503, "The AI service is busy or unavailable. Please try again.")


@app.exception_handler(LLMError)
async def _handle_llm_error(_: Request, exc: LLMError) -> JSONResponse:
    return _llm_error_response(502, "The AI service returned an error.")
