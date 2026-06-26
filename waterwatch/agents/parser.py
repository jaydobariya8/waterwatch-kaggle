"""Agent 1 — Parser.

Reads the uploaded report and extracts every parameter into a typed parameter set with
per-field confidence. Uses Gemini multimodal vision when available; otherwise a robust
deterministic text parser handles pasted text, bundled samples, and PDF text. Low-confidence
fields are surfaced for the user to confirm rather than silently guessed.
"""

from __future__ import annotations

import json
import re
from typing import Any

from ..config import DATA_DIR
from ..data_layer import normalize_param
from ..exceptions import ParseError
from ..schemas import ParameterReading, ParsedReport
from .base import Agent, AgentContext

# Match a standalone number only — a digit run not embedded in a token. This skips
# digits inside chemical formulae (the '3' in NO3, CaCO3; the '4' in SO4) so the parser
# reads the measured value, not the formula.
_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9.])\d+(?:\.\d+)?(?![A-Za-z0-9])")
_PINCODE_RE = re.compile(r"\b(\d{6})\b")
_SAMPLE_RE = re.compile(r"(?:sample\s*id|sample\s*no|sample\s*ref|sample|ref)\s*[:#]?\s*([A-Z0-9\-/]+)", re.I)
_DATE_RE = re.compile(r"(\d{1,2}[-/][0-9]{1,2}[-/]\d{2,4}|\d{4}-\d{2}-\d{2}|\d{1,2}\s+[A-Za-z]+\s+\d{4})")
_LOCATION_RE = re.compile(
    r"\b(?:location|village/area|sampling\s+point|village|area|address)\s*[:#-]\s*(.+?)(?=\s{2,}|pin|pincode|$)",
    re.I
)


def _load_samples() -> dict[str, dict[str, Any]]:
    with (DATA_DIR / "sample_reports.json").open(encoding="utf-8") as fh:
        data = json.load(fh)
    return {s["id"]: s for s in data["samples"]}


def parse_text(text: str) -> ParsedReport:
    """Deterministically extract parameters and metadata from report text."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    readings: list[ParameterReading] = []
    seen: set[str] = set()

    for line in lines:
        match = _NUMBER_RE.search(line)
        if not match:
            continue
        name_part = line[: match.start()].strip(" :\t|-")
        if not name_part:
            continue
        key = normalize_param(name_part)
        if key is None or key in seen:
            continue
        try:
            value = float(match.group())
        except ValueError:
            continue
        seen.add(key)
        readings.append(
            ParameterReading(
                key=key,
                label=name_part,
                value=value,
                raw_name=name_part,
                confidence=0.95,
            )
        )

    pincode = None
    for line in lines:
        if re.search(r"pin", line, re.I):
            pin = _PINCODE_RE.search(line)
            if pin:
                pincode = pin.group(1)
                break
    if pincode is None:
        pin = _PINCODE_RE.search(text)
        pincode = pin.group(1) if pin else None

    location = None
    for line in lines:
        loc_match = _LOCATION_RE.search(line)
        if loc_match:
            location = loc_match.group(1).strip(" :\t|-")
            break

    sample_match = _SAMPLE_RE.search(text)
    date_match = _DATE_RE.search(text)

    if not readings:
        raise ParseError(
            "Could not recognise any water-quality parameters in the report. "
            "Paste the report text or pick a sample report."
        )

    return ParsedReport(
        sample_id=sample_match.group(1) if sample_match else None,
        location=location,
        pincode=pincode,
        collected_on=date_match.group(1) if date_match else None,
        source="text",
        parse_confidence=round(sum(r.confidence for r in readings) / len(readings), 3),
        readings=readings,
    )


def _from_llm_payload(payload: dict[str, Any]) -> ParsedReport:
    meta = payload.get("meta", {}) or {}
    readings: list[ParameterReading] = []
    low_conf: list[str] = []
    for item in payload.get("readings", []) or []:
        raw_name = item.get("raw_name") or item.get("key") or ""
        key = normalize_param(item.get("key") or raw_name)
        if key is None:
            continue
        try:
            value = float(item.get("value"))
        except (TypeError, ValueError):
            continue
        confidence = float(item.get("confidence", 0.9) or 0.9)
        if confidence < 0.6:
            low_conf.append(key)
        readings.append(
            ParameterReading(
                key=key,
                label=raw_name or key,
                value=value,
                unit=str(item.get("unit", "")),
                raw_name=raw_name,
                confidence=confidence,
            )
        )
    if not readings:
        raise ParseError("Gemini returned no usable parameters from the document.")
    return ParsedReport(
        sample_id=meta.get("sample_id"),
        location=meta.get("location"),
        pincode=meta.get("pincode"),
        collected_on=meta.get("collected_on"),
        source="gemini-vision",
        parse_confidence=round(sum(r.confidence for r in readings) / len(readings), 3),
        readings=readings,
        low_confidence_fields=low_conf,
    )


class ParserAgent(Agent):
    name = "parser"
    title = "Reading the report"

    def run(self, ctx: AgentContext) -> None:
        def _do() -> str:
            request = ctx.request
            parsed: ParsedReport

            # 1) Bundled sample report.
            if request.sample_id:
                samples = _load_samples()
                sample = samples.get(request.sample_id)
                if sample is None:
                    raise ParseError(f"unknown sample report: {request.sample_id}")
                parsed = parse_text(sample["text"])
                parsed.source = "sample"
                parsed.location = sample.get("location")
                parsed.pincode = sample.get("pincode") or parsed.pincode
                parsed.collected_on = sample.get("collected_on") or parsed.collected_on
                parsed.sample_id = sample.get("id")

            # 2) Uploaded file (image/PDF) — Gemini vision, else PDF text.
            elif ctx.state.get("upload_bytes"):
                data = ctx.state["upload_bytes"]
                mime = ctx.state.get("upload_mime", "application/octet-stream")
                payload = ctx.llm.parse_report(data, mime, known_params=_known_params())
                if payload is not None:
                    parsed = _from_llm_payload(payload)
                    ctx.state["llm_used"] = True
                else:
                    text = _extract_pdf_text(data) if "pdf" in mime else None
                    if not text:
                        raise ParseError(
                            "This file needs Gemini vision to read (set GEMINI_API_KEY), "
                            "or paste the report text / pick a sample report."
                        )
                    parsed = parse_text(text)

            # 3) Pasted text.
            elif request.text:
                parsed = parse_text(request.text)

            else:
                raise ParseError("No report provided. Upload a file, paste text, or pick a sample.")

            if request.pincode:
                parsed.pincode = request.pincode
            if request.location:
                parsed.location = request.location

            ctx.state["parsed"] = parsed
            note = f"Extracted {len(parsed.readings)} parameters via {parsed.source}"
            if parsed.low_confidence_fields:
                note += f"; {len(parsed.low_confidence_fields)} low-confidence field(s) flagged for confirmation"
            return note + "."

        status = "ok"
        self._timed(ctx, _do, status=status)


def _known_params() -> list[str]:
    from ..data_layer import list_parameters

    return list_parameters()


def _extract_pdf_text(data: bytes) -> str | None:
    try:
        import io

        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:  # pragma: no cover - optional dep / unreadable pdf
        return None
