"""The grounded data layer — the single source of truth behind both the agents and the
MCP server. Every limit and every health statement returned here carries a citation, so
the system is *structurally* incapable of inventing a safe limit or a health risk.

These functions are pure Python (no HTTP, no Django/FastAPI request objects) so they can
be exposed equally as MCP tools (``mcp_server/server.py``) or called directly by the
specialist agents.
"""

from __future__ import annotations

import json
import logging
import re
from functools import lru_cache
from typing import Any

from .config import DATA_DIR
from .exceptions import DataLayerError

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = ["low", "moderate", "high", "critical"]


# --------------------------------------------------------------------------- #
# Bundled-data loaders (cached)                                               #
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=4)
def _load_json(filename: str) -> dict[str, Any]:
    path = DATA_DIR / filename
    try:
        with path.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError as exc:  # pragma: no cover - misconfiguration
        raise DataLayerError(f"bundled data file missing: {filename}") from exc
    except json.JSONDecodeError as exc:  # pragma: no cover - corrupt bundle
        raise DataLayerError(f"bundled data file invalid JSON: {filename}") from exc


def _bis() -> dict[str, Any]:
    return _load_json("bis_10500.json")["parameters"]


def _treatments() -> dict[str, Any]:
    return _load_json("treatment_kb.json")["treatments"]


def _health() -> dict[str, Any]:
    return _load_json("health_kb.json")["effects"]


@lru_cache(maxsize=1)
def _alias_index() -> dict[str, str]:
    """Map every alias (lower-cased) to its canonical parameter key."""
    index: dict[str, str] = {}
    for key, spec in _bis().items():
        index[key] = key
        index[spec["label"].lower()] = key
        index[spec["symbol"].lower()] = key
        for alias in spec.get("aliases", []):
            index[alias.lower()] = key
    return index


def normalize_param(name: str) -> str | None:
    """Resolve a free-text parameter name to its canonical key, or ``None``.

    Robust against report quirks: chemical formulae in the name (``Nitrate (as NO3)``,
    ``Total Hardness (as CaCO3)``) and short ambiguous symbols (``as``, ``f``, ``cl``)
    that would otherwise collide via naive substring matching.
    """
    if not name:
        return None
    index = _alias_index()
    cleaned = name.strip().lower()
    if cleaned in index:
        return index[cleaned]

    # Strip parentheticals and unit noise, then re-try an exact match.
    stripped = re.sub(r"\(.*?\)", " ", cleaned)
    stripped = re.sub(r"\b(?:mg/l|mg per l|ntu|mpn/100ml|as\s+caco3|as)\b", " ", stripped)
    stripped = re.sub(r"[^a-z0-9.\s]+", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    if stripped in index:
        return index[stripped]

    # Word-boundary alias match, longest alias first; skip ≤2-char symbols here so a
    # stray "as"/"f"/"cl" cannot hijack a longer name.
    for alias in sorted((a for a in index if len(a) >= 3), key=len, reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", stripped):
            return index[alias]
    return None


def list_parameters() -> list[str]:
    return list(_bis().keys())


# --------------------------------------------------------------------------- #
# Tool 1 — get_bis_limit                                                      #
# --------------------------------------------------------------------------- #
def get_bis_limit(param: str) -> dict[str, Any]:
    """Return the BIS 10500 acceptable + permissible limit for a parameter."""
    key = normalize_param(param)
    if key is None:
        raise DataLayerError(f"unknown parameter: {param!r}")
    spec = _bis()[key]
    kind = spec.get("kind", "max")
    if kind == "min":
        acceptable = spec.get("acceptable_min")
        permissible = spec.get("permissible_min")
        display = f"min {acceptable}"
    elif kind == "range":
        acceptable = spec.get("acceptable_max")
        permissible = spec.get("permissible_max")
        display = f"{spec.get('acceptable_min')}–{spec.get('acceptable_max')}"
    else:
        acceptable = spec.get("acceptable_max")
        permissible = spec.get("permissible_max")
        display = f"{acceptable}"
    return {
        "key": key,
        "label": spec["label"],
        "unit": spec["unit"],
        "kind": kind,
        "acceptable": acceptable,
        "permissible": permissible,
        "acceptable_display": display,
        "no_relaxation": spec.get("no_relaxation", False),
        "citation": spec["citation"],
    }


# --------------------------------------------------------------------------- #
# Severity helpers                                                            #
# --------------------------------------------------------------------------- #
def _bump(severity: str) -> str:
    idx = _SEVERITY_ORDER.index(severity)
    return _SEVERITY_ORDER[min(idx + 1, len(_SEVERITY_ORDER) - 1)]


def _cap(severity: str, ceiling: str) -> str:
    if _SEVERITY_ORDER.index(severity) > _SEVERITY_ORDER.index(ceiling):
        return ceiling
    return severity


def _baseline_severity(key: str) -> str:
    return _health().get(key, _health()["_default"]).get("severity", "moderate")


def _evaluate_one(key: str, value: float) -> dict[str, Any] | None:
    """Evaluate a single (key, value) against BIS. Returns a breach/reading dict."""
    spec = _bis().get(key)
    if spec is None:
        return None
    kind = spec.get("kind", "max")
    citation = spec["citation"]
    label = spec["label"]
    unit = spec["unit"]
    baseline = _baseline_severity(key)

    status: str
    limit_used: float | None
    magnitude: float | None = None
    message: str

    if kind == "absent" or (kind == "max" and (spec.get("acceptable_max") == 0)):
        # Bacteriological: must be absent.
        limit_used = 0.0
        if value > 0:
            status = "breach"
            message = f"{label} detected ({value:g}); BIS requires it be absent in any 100 mL sample."
            severity = _cap(_bump(baseline) if baseline != "critical" else baseline, "critical")
        else:
            status = "safe"
            message = f"{label} absent — within BIS requirement."
            severity = "low"
        return _breach_dict(key, label, value, unit, status, spec, limit_used, magnitude, severity, message, citation)

    if kind == "min":
        acceptable = spec.get("acceptable_min")
        limit_used = acceptable
        if acceptable is not None and value < acceptable:
            status = "concern"
            magnitude = round(value / acceptable, 3) if acceptable else None
            message = f"{label} is {value:g} {unit}, below the recommended minimum of {acceptable:g} {unit}."
            severity = _cap(baseline, "moderate")
        else:
            status = "safe"
            message = f"{label} is {value:g} {unit}, at or above the recommended minimum."
            severity = "low"
        return _breach_dict(key, label, value, unit, status, spec, limit_used, magnitude, severity, message, citation)

    if kind == "range":
        lo = spec.get("acceptable_min")
        hi = spec.get("acceptable_max")
        if lo is not None and hi is not None and lo <= value <= hi:
            status = "safe"
            limit_used = hi
            message = f"{label} is {value:g}, within the acceptable range {lo:g}–{hi:g}."
            severity = "low"
        else:
            status = "breach"
            limit_used = hi
            message = f"{label} is {value:g}, outside the acceptable range {lo:g}–{hi:g} (no relaxation)."
            severity = baseline
        return _breach_dict(key, label, value, unit, status, spec, limit_used, magnitude, severity, message, citation)

    # Default: kind == "max"
    acceptable = spec.get("acceptable_max")
    permissible = spec.get("permissible_max")
    # A 'health_critical' toxic (e.g. arsenic) has no safe margin: any exceedance of the
    # acceptable limit is a breach, since the permissible limit is only a reluctant
    # fallback in the absence of an alternate source.
    health_critical = spec.get("health_critical", False)

    if acceptable is not None and value <= acceptable:
        status = "safe"
        limit_used = acceptable
        message = f"{label} is {value:g} {unit}, within the acceptable limit of {acceptable:g} {unit}."
        severity = "low"
    elif (not health_critical) and permissible is not None and value <= permissible:
        status = "concern"
        limit_used = acceptable
        magnitude = round(value / acceptable, 3) if acceptable else None
        message = (
            f"{label} is {value:g} {unit}, above the acceptable limit ({acceptable:g}) "
            f"but within the permissible limit ({permissible:g} {unit})."
        )
        severity = _cap(baseline, "moderate")
    elif health_critical and permissible is not None and value <= permissible:
        status = "breach"
        limit_used = acceptable
        magnitude = round(value / acceptable, 3) if acceptable else None
        message = (
            f"{label} is {value:g} {unit}, exceeding the acceptable limit of {acceptable:g} {unit}. "
            f"This contaminant has no safe margin, so any exceedance is treated as a breach."
        )
        severity = baseline
        if magnitude is not None and magnitude >= 3:
            severity = _bump(severity)
    else:
        status = "breach"
        limit_used = permissible if permissible else acceptable
        magnitude = round(value / limit_used, 3) if limit_used else None
        message = (
            f"{label} is {value:g} {unit}, exceeding the permissible limit of "
            f"{(permissible if permissible else acceptable):g} {unit}."
        )
        severity = baseline
        if magnitude is not None and magnitude >= 3:
            severity = _bump(severity)
    return _breach_dict(key, label, value, unit, status, spec, limit_used, magnitude, severity, message, citation)


def _breach_dict(
    key: str,
    label: str,
    value: float,
    unit: str,
    status: str,
    spec: dict[str, Any],
    limit_used: float | None,
    magnitude: float | None,
    severity: str,
    message: str,
    citation: dict[str, Any],
) -> dict[str, Any]:
    return {
        "key": key,
        "label": label,
        "value": value,
        "unit": unit,
        "status": status,
        "acceptable": spec.get("acceptable_max", spec.get("acceptable_min")),
        "permissible": spec.get("permissible_max", spec.get("permissible_min")),
        "limit_used": limit_used,
        "magnitude": magnitude,
        "severity": severity,
        "message": message,
        "citation": citation,
    }


# --------------------------------------------------------------------------- #
# Tool 2 — evaluate_sample                                                    #
# --------------------------------------------------------------------------- #
def evaluate_sample(params: dict[str, float]) -> list[dict[str, Any]]:
    """Evaluate a full sample. ``params`` maps parameter name/key -> numeric value.

    Returns one evaluation dict per recognised parameter, sorted worst-first.
    """
    results: list[dict[str, Any]] = []
    for raw_name, value in params.items():
        key = normalize_param(raw_name)
        if key is None:
            logger.debug("evaluate_sample: skipping unrecognised parameter %r", raw_name)
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            logger.debug("evaluate_sample: non-numeric value for %r: %r", raw_name, value)
            continue
        evaluation = _evaluate_one(key, numeric)
        if evaluation is not None:
            results.append(evaluation)

    status_rank = {"breach": 0, "concern": 1, "safe": 2}
    results.sort(
        key=lambda r: (
            status_rank.get(r["status"], 3),
            -_SEVERITY_ORDER.index(r["severity"]),
        )
    )
    return results


def overall_verdict(evaluations: list[dict[str, Any]]) -> str:
    """Reduce per-parameter evaluations to SAFE / CAUTION / UNSAFE."""
    has_breach = False
    has_concern = False
    for ev in evaluations:
        if ev["status"] == "breach":
            has_breach = True
            if ev["severity"] in {"high", "critical"}:
                return "UNSAFE"
        elif ev["status"] == "concern":
            has_concern = True
    if has_breach or has_concern:
        return "CAUTION"
    return "SAFE"


# --------------------------------------------------------------------------- #
# Tool 3 — get_area_readings                                                  #
# --------------------------------------------------------------------------- #
# A last-known snapshot ships bundled, so the core verdict never depends on a live
# call succeeding. A failed external fetch degrades to "area comparison unavailable" —
# it never blocks the safety analysis (the resilience design from the plan).
_AREA_SNAPSHOT: dict[str, dict[str, Any]] = {
    "800001": {
        "place": "Patna, Bihar",
        "as_of": "2024-11",
        "source": "CPCB National Water Quality Monitoring Programme (bundled snapshot)",
        "readings": {"arsenic": 0.032, "iron": 0.45, "tds": 612, "ph": 7.4},
    },
    "342001": {
        "place": "Jodhpur, Rajasthan",
        "as_of": "2024-10",
        "source": "CPCB / State PHED (bundled snapshot)",
        "readings": {"fluoride": 2.1, "tds": 1180, "nitrate": 52, "ph": 7.9},
    },
    "110001": {
        "place": "New Delhi",
        "as_of": "2024-12",
        "source": "CPCB National Water Quality Monitoring Programme (bundled snapshot)",
        "readings": {"tds": 380, "ph": 7.6, "total_hardness": 210, "residual_chlorine": 0.3},
    },
    "700001": {
        "place": "Kolkata, West Bengal",
        "as_of": "2024-09",
        "source": "CPCB / State PHED (bundled snapshot)",
        "readings": {"arsenic": 0.028, "iron": 0.6, "ph": 7.2},
    },
}


def get_area_readings(pincode: str | None) -> dict[str, Any]:
    """Return recent official readings for an area, from the bundled snapshot.

    A live data.gov.in / CPCB call would be attempted here when an API key is present;
    on any failure (or no key) this degrades gracefully rather than blocking the verdict.
    """
    if not pincode:
        return {"available": False, "note": "No pincode provided — area comparison skipped.", "readings": []}
    snap = _AREA_SNAPSHOT.get(str(pincode).strip())
    if snap is None:
        return {
            "available": False,
            "pincode": pincode,
            "note": "No official readings on record for this pincode in the bundled snapshot.",
            "readings": [],
        }
    readings = []
    for raw_name, value in snap["readings"].items():
        key = normalize_param(raw_name) or raw_name
        spec = _bis().get(key, {})
        readings.append({"parameter": spec.get("label", key), "value": value, "unit": spec.get("unit", "")})
    return {
        "available": True,
        "pincode": pincode,
        "place": snap["place"],
        "source": snap["source"],
        "as_of": snap["as_of"],
        "note": f"Official area readings for {snap['place']} ({snap['as_of']}).",
        "readings": readings,
    }


# --------------------------------------------------------------------------- #
# Tool 4 — match_filtration                                                   #
# --------------------------------------------------------------------------- #
def match_filtration(contaminants: list[str]) -> list[dict[str, Any]]:
    """Map a set of contaminants to the cheapest effective treatment for each."""
    treatments = _treatments()
    seen: set[str] = set()
    recs: list[dict[str, Any]] = []
    for raw in contaminants:
        key = normalize_param(raw) or raw
        if key in seen:
            continue
        seen.add(key)
        spec = treatments.get(key, treatments["_default"])
        recs.append(
            {
                "contaminant_key": key,
                "contaminant_label": spec["contaminant_label"],
                "recommendation": spec["cheapest_effective"],
                "options": spec.get("options", []),
                "avoid": spec.get("not_effective", []),
                "note": spec.get("note", ""),
                "citation": spec["citation"],
            }
        )
    return recs


# --------------------------------------------------------------------------- #
# Tool 5 — health_effect                                                      #
# --------------------------------------------------------------------------- #
def health_effect(contaminant: str) -> dict[str, Any]:
    """Return a cited, plain-language health-impact summary for a contaminant."""
    key = normalize_param(contaminant) or contaminant
    health = _health()
    spec = health.get(key)
    if spec is None:
        spec = dict(health["_default"])
        # Use the BIS label if we at least know the parameter.
        bis_spec = _bis().get(key)
        if bis_spec:
            spec["label"] = bis_spec["label"]
    return {
        "key": key,
        "label": spec["label"],
        "summary": spec["summary"],
        "severity": spec.get("severity", "moderate"),
        "citation": spec["citation"],
    }


# Public tool registry — used by the MCP server to expose these uniformly.
TOOLS = {
    "get_bis_limit": get_bis_limit,
    "evaluate_sample": evaluate_sample,
    "get_area_readings": get_area_readings,
    "match_filtration": match_filtration,
    "health_effect": health_effect,
}
