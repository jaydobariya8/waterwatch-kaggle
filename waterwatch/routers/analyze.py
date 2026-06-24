"""Analyze endpoints — run the full agent pipeline on a report (text/sample or upload)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..agents import get_orchestrator
from ..exceptions import ParseError, WaterWatchError
from ..schemas import AnalyzeRequest, AnalyzeResponse

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["analyze"])


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Analyze a pasted-text report or a bundled sample report."""
    try:
        return get_orchestrator().analyze(request)
    except ParseError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)})
    except WaterWatchError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})


@router.post("/analyze/upload", response_model=AnalyzeResponse)
async def analyze_upload(
    file: UploadFile = File(...),
    pincode: str | None = Form(default=None),
    location: str | None = Form(default=None),
    demo_inject_uncited: bool = Form(default=False),
) -> AnalyzeResponse:
    """Analyze an uploaded lab report (PDF or image). Uses Gemini vision when configured."""
    data = await file.read()
    request = AnalyzeRequest(
        pincode=pincode,
        location=location,
        demo_inject_uncited=demo_inject_uncited,
    )
    try:
        return get_orchestrator().analyze(
            request,
            upload_bytes=data,
            upload_mime=file.content_type or "application/octet-stream",
        )
    except ParseError as exc:
        raise HTTPException(status_code=422, detail={"code": exc.code, "message": str(exc)})
    except WaterWatchError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": str(exc)})
