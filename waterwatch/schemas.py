"""Pydantic models — the request/response contract shared by the API, the agents,
and the MCP layer. This is the 'shared seam' the project plan calls out: agree the
schema once so every part of the system speaks the same language.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Verdict(str, Enum):
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    UNSAFE = "UNSAFE"


class Status(str, Enum):
    SAFE = "safe"
    CONCERN = "concern"  # exceeds desirable (acceptable) but within permissible
    BREACH = "breach"  # exceeds permissible / hard limit / bacteria present


class Severity(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class Citation(BaseModel):
    """A receipt: every number and health claim points back to an authoritative source."""

    source: str
    reference: str
    url: str | None = None


class ParameterReading(BaseModel):
    """A single measured parameter extracted from the report."""

    key: str  # canonical key, e.g. "fluoride"
    label: str
    value: float
    unit: str = ""
    raw_name: str | None = None  # the name exactly as it appeared in the report
    confidence: float = 1.0  # per-field parse confidence in [0, 1]


class ParsedReport(BaseModel):
    sample_id: str | None = None
    location: str | None = None
    pincode: str | None = None
    collected_on: str | None = None  # ISO date string as printed on the report
    source: str = "manual"  # "gemini-vision" | "text" | "sample" | "manual"
    parse_confidence: float = 1.0
    readings: list[ParameterReading] = Field(default_factory=list)
    low_confidence_fields: list[str] = Field(default_factory=list)


class BISLimit(BaseModel):
    key: str
    label: str
    unit: str
    acceptable: float | None = None
    permissible: float | None = None
    no_relaxation: bool = False
    kind: str = "max"
    citation: Citation


class Breach(BaseModel):
    key: str
    label: str
    value: float
    unit: str
    status: Status
    acceptable: float | None = None
    permissible: float | None = None
    limit_used: float | None = None
    magnitude: float | None = None  # value / limit_used (how many× over)
    severity: Severity
    message: str
    citation: Citation


class HealthImpact(BaseModel):
    key: str
    label: str
    summary: str
    severity: Severity
    citation: Citation


class FiltrationRec(BaseModel):
    contaminant_key: str
    contaminant_label: str
    recommendation: str
    options: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    note: str = ""
    citation: Citation


class AreaReading(BaseModel):
    parameter: str
    value: float
    unit: str = ""


class AreaComparison(BaseModel):
    available: bool
    pincode: str | None = None
    source: str | None = None
    as_of: str | None = None
    note: str = ""
    readings: list[AreaReading] = Field(default_factory=list)


class RejectedClaim(BaseModel):
    text: str
    reason: str
    stage: str


class VerifierAudit(BaseModel):
    """The differentiator made visible: what the Verifier checked and rejected."""

    passed: bool
    loops: int
    claims_checked: int
    rejected_claims: list[RejectedClaim] = Field(default_factory=list)
    notes: str = ""


class TraceStep(BaseModel):
    agent: str
    title: str
    detail: str
    status: str = "ok"  # ok | warn | error
    duration_ms: int | None = None


class ComplaintDraft(BaseModel):
    to: str
    subject: str
    body: str
    pincode: str | None = None
    sample_id: str | None = None
    breached_parameters: list[str] = Field(default_factory=list)


class AnalyzeRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    text: str | None = None  # pasted report text
    sample_id: str | None = None  # one of the bundled sample reports
    pincode: str | None = None
    location: str | None = None
    demo_inject_uncited: bool = False  # force the Verifier to catch a bad claim (demo)


class AnalyzeResponse(BaseModel):
    request_id: str
    verdict: Verdict
    headline: str
    summary: str
    parsed: ParsedReport
    readings_evaluated: list[Breach]
    breaches: list[Breach]
    health_impacts: list[HealthImpact]
    area_comparison: AreaComparison
    verifier: VerifierAudit
    filtration: list[FiltrationRec]
    complaint_draft: ComplaintDraft | None = None
    trace: list[TraceStep] = Field(default_factory=list)
    citations_count: int = 0
    llm_used: bool = False


class ComplaintRecord(BaseModel):
    id: str
    request_id: str | None = None
    pincode: str | None = None
    location: str | None = None
    sample_id: str | None = None
    verdict: Verdict
    breached_parameters: list[str] = Field(default_factory=list)
    to: str
    subject: str
    body: str
    status: str = "open"  # open | resolved | escalated
    created_at: str
    updated_at: str
    rti_draft: str | None = None
    events: list[dict] = Field(default_factory=list)


class ErrorBody(BaseModel):
    code: str
    message: str
    details: dict | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody
