"""FastAPI application with API endpoints for load generator lifecycle management."""

import os
from collections.abc import AsyncIterator

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from kasbench_load_generator import config
from kasbench_load_generator.models import (
    AbortResponse,
    ErrorResponse,
    HealthResponse,
    StartRequest,
    StartResponse,
    StatusEnum,
)
from kasbench_load_generator.subprocess_manager import SubprocessManager

app = FastAPI(title="KASBench Load Generator")

subprocess_manager = SubprocessManager(
    db_path=config.DB_PATH,
    output_path=config.OUTPUT_PATH,
)


@app.get("/health")
async def health() -> HealthResponse:
    """Return current health status of the load generator."""
    return subprocess_manager.get_health()


@app.post("/start", responses={409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def start(request: StartRequest) -> StartResponse:
    """Launch a new Locust subprocess with the given parameters.

    Pydantic handles request validation (returns 422 for invalid inputs).
    HTTPException from SubprocessManager propagates for 409/500/503.
    """
    return await subprocess_manager.start(request)


@app.post("/abort", responses={409: {"model": ErrorResponse}, 500: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})
async def abort() -> AbortResponse:
    """Terminate the running Locust subprocess.

    HTTPException from SubprocessManager propagates for 409/500/503.
    """
    return await subprocess_manager.abort()


async def _file_iterator(path: str, chunk_size: int = 8192) -> AsyncIterator[bytes]:
    """Read a file in chunks for streaming responses."""
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            yield chunk


@app.get("/download-db", responses={409: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})
async def download_db() -> StreamingResponse:
    """Stream the SQLite database file.

    Returns 409 if subprocess is still running.
    Returns 404 if the database file does not exist.
    """
    if subprocess_manager.is_running:
        raise HTTPException(status_code=409, detail="Subprocess is still active")

    if not os.path.exists(config.DB_PATH):
        raise HTTPException(status_code=404, detail="Database file not available")

    return StreamingResponse(
        _file_iterator(config.DB_PATH),
        media_type="application/x-sqlite3",
    )


@app.get("/download-output", responses={409: {"model": ErrorResponse}, 404: {"model": ErrorResponse}})
async def download_output() -> StreamingResponse:
    """Stream the subprocess output file.

    Returns 409 if subprocess is still running.
    Returns 404 if no subprocess has been started.
    Returns 200 with text/plain content (even if empty).
    """
    if subprocess_manager.is_running:
        raise HTTPException(status_code=409, detail="Subprocess is still active")

    if subprocess_manager._status == StatusEnum.NOT_STARTED:
        raise HTTPException(status_code=404, detail="No output available")

    return StreamingResponse(
        _file_iterator(config.OUTPUT_PATH),
        media_type="text/plain",
    )
