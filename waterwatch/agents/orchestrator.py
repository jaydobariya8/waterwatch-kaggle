"""The root orchestrator — routes the job, holds session state, and calls the specialists
as a SequentialAgent spine with a Verifier LoopAgent embedded. Assembles the final,
fully-cited :class:`AnalyzeResponse`.
"""

from __future__ import annotations

import logging
import uuid

from ..llm import get_llm
from ..schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    AreaComparison,
    AreaReading,
    Breach,
    Status,
    Verdict,
)
from .action import ActionAgent
from .base import AgentContext, LoopAgent, SequentialAgent
from .health import HealthAgent
from .parser import ParserAgent
from .standards import StandardsAgent
from .verifier import VerifierAgent
from .watchdog import WatchdogAgent

logger = logging.getLogger(__name__)


class Orchestrator:
    """Builds and runs the WaterWatch agent pipeline."""

    def __init__(self) -> None:
        self._verifier = VerifierAgent()
        self._pipeline = SequentialAgent(
            "WaterWatchPipeline",
            [
                ParserAgent(),
                StandardsAgent(),
                HealthAgent(),
                LoopAgent(
                    "VerifierLoop",
                    body=self._verifier,
                    is_done=VerifierAgent.is_done,
                    max_iterations=3,
                ),
                ActionAgent(),
                WatchdogAgent(),
            ],
        )

    def analyze(
        self,
        request: AnalyzeRequest,
        *,
        upload_bytes: bytes | None = None,
        upload_mime: str | None = None,
    ) -> AnalyzeResponse:
        ctx = AgentContext(request=request, llm=get_llm())
        if upload_bytes is not None:
            ctx.state["upload_bytes"] = upload_bytes
            ctx.state["upload_mime"] = upload_mime or "application/octet-stream"

        self._pipeline.run(ctx)
        return self._assemble(ctx)

    # ------------------------------------------------------------------ #
    def _assemble(self, ctx: AgentContext) -> AnalyzeResponse:
        state = ctx.state
        parsed = state["parsed"]
        evaluations = state.get("evaluations", [])
        breaches_raw = state.get("breaches", [])
        verdict = Verdict(state.get("verdict", "SAFE"))

        readings_evaluated = [Breach(**ev) for ev in evaluations]
        breaches = [Breach(**ev) for ev in breaches_raw]
        health_impacts = state.get("health_impacts", [])
        filtration = state.get("filtration", [])
        complaint_draft = state.get("complaint_draft")
        verifier = VerifierAgent.build_audit(ctx)

        area_raw = state.get("area", {"available": False})
        area = AreaComparison(
            available=area_raw.get("available", False),
            pincode=area_raw.get("pincode"),
            source=area_raw.get("source"),
            as_of=area_raw.get("as_of"),
            note=area_raw.get("note", ""),
            readings=[AreaReading(**r) for r in area_raw.get("readings", [])],
        )

        headline, summary = _headline(verdict, breaches, parsed)

        # Every checked parameter carries a BIS citation receipt — count them all, plus
        # the cited health explanations, treatment recommendations, and area source.
        citations_count = (
            len(readings_evaluated)
            + len(health_impacts)
            + len(filtration)
            + (1 if area.available else 0)
        )

        return AnalyzeResponse(
            request_id=uuid.uuid4().hex[:12],
            verdict=verdict,
            headline=headline,
            summary=summary,
            parsed=parsed,
            readings_evaluated=readings_evaluated,
            breaches=breaches,
            health_impacts=health_impacts,
            area_comparison=area,
            verifier=verifier,
            filtration=filtration,
            complaint_draft=complaint_draft,
            trace=ctx.trace,
            citations_count=citations_count,
            llm_used=bool(state.get("llm_used", False)),
        )


def _headline(verdict: Verdict, breaches: list[Breach], parsed) -> tuple[str, str]:
    hard = [b for b in breaches if b.status == Status.BREACH]
    worst = sorted(hard, key=lambda b: b.severity != "critical")
    names = ", ".join(b.label for b in worst[:3]) if worst else ""

    if verdict == Verdict.UNSAFE:
        headline = "This water is UNSAFE to drink."
        summary = (
            f"{len(hard)} parameter(s) breach the BIS 10500 permissible limit"
            + (f", driven by {names}" if names else "")
            + ". Do not drink untreated — see the matched treatment below. Every figure is cited."
        )
    elif verdict == Verdict.CAUTION:
        concern = [b for b in breaches if b.status == Status.CONCERN]
        summary = (
            f"{len(breaches)} parameter(s) exceed the BIS desirable limit"
            + (f" ({names})" if names else "")
            + ". No acute health breach, but treatment is advisable. Every figure is cited."
        )
        headline = "This water needs CAUTION."
    else:
        headline = "This water is SAFE to drink."
        summary = "Every measured parameter is within the BIS 10500 acceptable limits. All figures are cited."
    return headline, summary


_orchestrator: Orchestrator | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator()
    return _orchestrator
