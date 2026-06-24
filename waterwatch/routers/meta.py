"""Meta + reference endpoints: health, app info, samples, BIS parameters, MCP tool list."""

from __future__ import annotations

import json

from fastapi import APIRouter

from ..config import DATA_DIR, get_settings
from ..data_layer import _bis
from ..llm import get_llm

router = APIRouter(prefix="/api/v1", tags=["meta"])


@router.get("/meta")
def meta() -> dict:
    settings = get_settings()
    return {
        "app": settings.app_name,
        "version": settings.version,
        "llm_enabled": get_llm().available,
        "store_backend": settings.store_backend,
        "escalation_days": settings.escalation_days,
        "cluster_threshold": settings.cluster_threshold,
    }


@router.get("/samples")
def samples() -> dict:
    with (DATA_DIR / "sample_reports.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    return {
        "samples": [
            {
                "id": s["id"],
                "title": s["title"],
                "subtitle": s.get("subtitle", ""),
                "location": s.get("location"),
                "pincode": s.get("pincode"),
                "expected_verdict": s.get("expected", {}).get("verdict"),
            }
            for s in data["samples"]
        ]
    }


@router.get("/parameters")
def parameters() -> dict:
    out = []
    for key, spec in _bis().items():
        out.append(
            {
                "key": key,
                "label": spec["label"],
                "unit": spec["unit"],
                "acceptable": spec.get("acceptable_max", spec.get("acceptable_min")),
                "permissible": spec.get("permissible_max", spec.get("permissible_min")),
                "no_relaxation": spec.get("no_relaxation", False),
                "citation": spec["citation"],
            }
        )
    return {"standard": "IS 10500:2012", "parameters": out}


@router.get("/mcp/tools")
def mcp_tools() -> dict:
    """Describe the MCP tools exposed by the data layer (the Day-2 grounding story)."""
    return {
        "server": "waterwatch-mcp",
        "tools": [
            {"name": "get_bis_limit", "args": ["param"], "returns": "Acceptable + permissible BIS 10500 limit"},
            {"name": "evaluate_sample", "args": ["params"], "returns": "Breach list with magnitude & severity"},
            {"name": "get_area_readings", "args": ["pincode"], "returns": "Recent official readings for the locality"},
            {"name": "match_filtration", "args": ["contaminants"], "returns": "Cheapest effective treatment per contaminant"},
            {"name": "health_effect", "args": ["contaminant"], "returns": "Cited health-impact summary"},
        ],
    }
