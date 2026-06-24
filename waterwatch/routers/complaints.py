"""Complaint lifecycle + watchdog endpoints (the actuation + escalation story).

Filing a complaint is the human-gated step: the agent only ever drafts; the user must
POST here to actually file it. Escalation/RTI is exposed both per-complaint and as a
batch endpoint that Cloud Scheduler hits daily.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import services
from ..exceptions import StoreError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1", tags=["complaints"])


class FileComplaintRequest(BaseModel):
    request_id: str | None = None
    pincode: str | None = None
    location: str | None = None
    sample_id: str | None = None
    verdict: str = "UNSAFE"
    breached_parameters: list[str] = Field(default_factory=list)  # canonical keys
    to: str = "Municipal Water Authority / Jal Board"
    subject: str
    body: str


@router.post("/complaints")
def file_complaint(req: FileComplaintRequest) -> dict:
    """File a complaint after explicit human approval (the human-in-the-loop gate)."""
    record = services.file_complaint(req.model_dump())
    cluster = services.detect_cluster(record["pincode"], record["breached_parameters"])
    collective = None
    if cluster["cluster_detected"] and cluster["shared_contaminant"]:
        collective = services.build_collective_complaint(
            record["pincode"], cluster["shared_contaminant"], cluster["complaint_ids"]
        )
    return {"complaint": record, "civic": cluster, "collective_complaint": collective}


@router.get("/complaints")
def list_complaints() -> dict:
    return {"complaints": services.list_complaints()}


@router.get("/complaints/{complaint_id}")
def get_complaint(complaint_id: str) -> dict:
    record = services.get_complaint(complaint_id)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Complaint not found."})
    return {"complaint": record}


@router.post("/complaints/{complaint_id}/resolve")
def resolve_complaint(complaint_id: str) -> dict:
    try:
        return {"complaint": services.resolve_complaint(complaint_id)}
    except StoreError as exc:
        raise HTTPException(status_code=404, detail={"code": exc.code, "message": str(exc)})


@router.post("/complaints/{complaint_id}/escalate")
def escalate_complaint(complaint_id: str) -> dict:
    """Manually escalate now — drafts the RTI application (the headline action)."""
    try:
        return {"complaint": services.force_escalate(complaint_id)}
    except StoreError as exc:
        raise HTTPException(status_code=404, detail={"code": exc.code, "message": str(exc)})


@router.post("/watchdog/run")
def run_watchdog() -> dict:
    """Cloud Scheduler target: escalate any complaint unresolved past the threshold."""
    return services.check_escalations()
