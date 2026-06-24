"""Complaint lifecycle + civic aggregation services (pure business logic).

Drives the memory story (Day 3) and the actuation story (file → track → escalate → RTI).
The Watchdog agent and the API both call into here; there is no HTTP or request object in
this layer.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from .config import get_settings
from .data_layer import _bis  # canonical label lookup
from .store import get_store

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _label(key: str) -> str:
    spec = _bis().get(key)
    return spec["label"] if spec else key


def _age_days(created_at: str) -> float:
    try:
        created = datetime.fromisoformat(created_at)
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.0
    return (_now() - created).total_seconds() / 86400.0


# --------------------------------------------------------------------------- #
# Civic aggregation (A2A)                                                     #
# --------------------------------------------------------------------------- #
def detect_cluster(pincode: str | None, contaminant_keys: list[str]) -> dict[str, Any]:
    """Detect a pincode-level contaminant cluster across stored complaints."""
    settings = get_settings()
    result = {
        "cluster_detected": False,
        "count": 0,
        "shared_contaminant": None,
        "shared_contaminant_label": None,
        "threshold": settings.cluster_threshold,
        "complaint_ids": [],
    }
    if not pincode or not contaminant_keys:
        return result

    store = get_store()
    matches_by_contaminant: dict[str, list[str]] = {}
    for record in store.list_complaints():
        if record.get("pincode") != pincode:
            continue
        if record.get("status") == "resolved":
            continue
        for key in record.get("breached_parameters", []):
            if key in contaminant_keys:
                matches_by_contaminant.setdefault(key, []).append(record["id"])

    if not matches_by_contaminant:
        return result

    # Most-shared contaminant in this pincode.
    shared_key, ids = max(matches_by_contaminant.items(), key=lambda kv: len(kv[1]))
    existing = len(ids)
    result.update(
        {
            "count": existing,
            "shared_contaminant": shared_key,
            "shared_contaminant_label": _label(shared_key),
            "complaint_ids": ids,
            # +1 for the current (not-yet-filed) report.
            "cluster_detected": (existing + 1) >= settings.cluster_threshold,
        }
    )
    return result


def build_collective_complaint(pincode: str, contaminant_key: str, complaint_ids: list[str]) -> str:
    label = _label(contaminant_key)
    return (
        f"To,\nThe Municipal Commissioner / District Magistrate,\n{pincode}.\n\n"
        f"Subject: Collective complaint — {label} contamination affecting multiple households in {pincode}\n\n"
        f"Respected Sir/Madam,\n\n"
        f"{len(complaint_ids) + 1} households in pincode {pincode} have independently reported drinking "
        f"water exceeding the IS 10500:2012 limit for {label}. This is no longer an isolated case but a "
        f"public-health pattern in the area, and warrants municipal-level investigation and remediation.\n\n"
        f"We jointly request an area-wide water-quality survey and corrective action.\n\n"
        f"Yours faithfully,\nResidents of {pincode}\n"
    )


# --------------------------------------------------------------------------- #
# Complaint lifecycle                                                         #
# --------------------------------------------------------------------------- #
def file_complaint(payload: dict[str, Any]) -> dict[str, Any]:
    """Persist an approved complaint (the human-gated actuation step)."""
    store = get_store()
    complaint_id = "WW-" + uuid.uuid4().hex[:10].upper()
    now = _now_iso()
    record = {
        "id": complaint_id,
        "request_id": payload.get("request_id"),
        "pincode": payload.get("pincode"),
        "location": payload.get("location"),
        "sample_id": payload.get("sample_id"),
        "verdict": payload.get("verdict", "UNSAFE"),
        "breached_parameters": payload.get("breached_parameters", []),  # canonical keys
        "to": payload.get("to", "Municipal Water Authority / Jal Board"),
        "subject": payload.get("subject", "Drinking-water quality complaint"),
        "body": payload.get("body", ""),
        "status": "open",
        "created_at": now,
        "updated_at": now,
        "rti_draft": None,
        "events": [{"type": "filed", "note": "Complaint filed after human approval.", "at": now}],
    }
    store.save_complaint(record)
    logger.info("Filed complaint %s for pincode %s.", complaint_id, record["pincode"])
    return record


def list_complaints() -> list[dict[str, Any]]:
    return get_store().list_complaints()


def get_complaint(complaint_id: str) -> dict[str, Any] | None:
    return get_store().get_complaint(complaint_id)


def resolve_complaint(complaint_id: str) -> dict[str, Any]:
    store = get_store()
    record = store.update_complaint(complaint_id, status="resolved")
    store.add_event(complaint_id, {"type": "resolved", "note": "Marked resolved."})
    return record


def draft_rti(record: dict[str, Any]) -> str:
    breached = ", ".join(_label(k) for k in record.get("breached_parameters", [])) or "the reported parameters"
    return (
        f"APPLICATION UNDER THE RIGHT TO INFORMATION ACT, 2005\n\n"
        f"To,\nThe Public Information Officer,\nMunicipal Water Authority / Jal Board,\n"
        f"{record.get('location') or ''} ({record.get('pincode') or '______'}).\n\n"
        f"Subject: Information regarding action taken on water-quality complaint {record['id']}\n\n"
        f"Sir/Madam,\n\n"
        f"A complaint ({record['id']}) was filed regarding drinking water exceeding the IS 10500:2012 "
        f"limits for {breached} at {record.get('location') or 'the reported location'}. No resolution has "
        f"been communicated. Under the RTI Act, 2005, I request the following information:\n\n"
        f"  1. The action taken on complaint {record['id']} and the dates of any testing;\n"
        f"  2. The current water-quality readings for this supply zone;\n"
        f"  3. The timeline and responsible officer for corrective action.\n\n"
        f"I enclose the prescribed fee. Kindly provide the information within 30 days as mandated.\n\n"
        f"Yours faithfully,\nApplicant\n"
    )


def check_escalations() -> dict[str, Any]:
    """Cloud-Scheduler entrypoint: escalate stale complaints by drafting an RTI."""
    settings = get_settings()
    store = get_store()
    escalated: list[str] = []
    for record in store.list_complaints():
        if record.get("status") != "open":
            continue
        if _age_days(record["created_at"]) >= settings.escalation_days:
            rti = draft_rti(record)
            store.update_complaint(record["id"], status="escalated", rti_draft=rti)
            store.add_event(
                record["id"],
                {"type": "escalated", "note": f"Unresolved > {settings.escalation_days} days — RTI drafted."},
            )
            escalated.append(record["id"])
    return {"escalated": escalated, "checked_at": _now_iso(), "threshold_days": settings.escalation_days}


def force_escalate(complaint_id: str) -> dict[str, Any]:
    """Manually escalate a complaint now (demo / officer action)."""
    store = get_store()
    record = store.get_complaint(complaint_id)
    if record is None:
        from .exceptions import StoreError

        raise StoreError(f"complaint not found: {complaint_id}")
    rti = draft_rti(record)
    record = store.update_complaint(complaint_id, status="escalated", rti_draft=rti)
    store.add_event(complaint_id, {"type": "escalated", "note": "Manually escalated; RTI drafted."})
    return record
