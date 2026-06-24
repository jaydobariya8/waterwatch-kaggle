"""FastAPI application — hosts the agent pipeline, the API, and the web UI on one Cloud
Run service (the single-deployable MVP from the plan).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import FRONTEND_DIR, get_settings
from .exceptions import WaterWatchError
from .routers import analyze, complaints, meta

logging.basicConfig(
    level=getattr(logging, get_settings().log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("waterwatch")

settings = get_settings()

app = FastAPI(
    title="WaterWatch API",
    version=settings.version,
    description=(
        "A verifiable, civic-action multi-agent system for drinking-water safety. "
        "Every threshold and health claim carries a citation receipt; a Verifier agent "
        "blocks anything uncited."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(meta.router)
app.include_router(analyze.router)
app.include_router(complaints.router)


@app.get("/healthz", tags=["meta"])
def healthz() -> dict:
    return {"status": "ok", "app": settings.app_name, "version": settings.version}


@app.exception_handler(WaterWatchError)
async def waterwatch_error_handler(_request: Request, exc: WaterWatchError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"error": {"code": exc.code, "message": str(exc), "details": None}},
    )


# Serve the single-page web UI. Mounted last so /api/* and /healthz win.
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
