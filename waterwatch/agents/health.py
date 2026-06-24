"""Agent 3 — Health-Impact.

Translates each breach into a plain-language, cited health explanation grounded only in
the WHO/BIS health knowledge base. Never free-form medical advice — only sourced statements.

When the request asks for the verifier demo, this agent deliberately appends one *uncited*
claim so the Verifier can be seen catching and removing it (the 'agent catching itself'
money shot). The seam is explicit and documented, not hidden.
"""

from __future__ import annotations

from ..data_layer import health_effect
from ..schemas import HealthImpact, Severity
from .base import Agent, AgentContext, AgentTool

_DEMO_UNCITED_CLAIM = (
    "Drinking this water will cure kidney stones within a week."  # plausible-sounding, unsourced
)


class HealthAgent(Agent):
    name = "health"
    title = "Explaining the health impact"

    def __init__(self) -> None:
        self._health = AgentTool("health_effect", health_effect)

    def run(self, ctx: AgentContext) -> None:
        def _do() -> str:
            breaches = ctx.state.get("breaches", [])
            claims = ctx.state.setdefault("claims", [])
            impacts: list[HealthImpact] = []
            seen: set[str] = set()

            for ev in breaches:
                key = ev["key"]
                if key in seen:
                    continue
                seen.add(key)
                effect = self._health(ctx, contaminant=key)
                impacts.append(
                    HealthImpact(
                        key=effect["key"],
                        label=effect["label"],
                        summary=effect["summary"],
                        severity=Severity(effect["severity"]),
                        citation=effect["citation"],
                    )
                )
                claims.append(
                    {
                        "id": f"health:{key}",
                        "stage": "health",
                        "kind": "health",
                        "text": effect["summary"],
                        "citation": effect["citation"],
                    }
                )

            # Demo seam: inject one uncited health claim for the Verifier to reject.
            if ctx.request.demo_inject_uncited:
                claims.append(
                    {
                        "id": "health:demo_uncited",
                        "stage": "health",
                        "kind": "health",
                        "text": _DEMO_UNCITED_CLAIM,
                        "citation": None,
                    }
                )

            ctx.state["health_impacts"] = impacts
            note = f"Produced {len(impacts)} cited health explanation(s)"
            if ctx.request.demo_inject_uncited:
                note += " + 1 deliberately uncited claim for the Verifier"
            return note + "."

        self._timed(ctx, _do)
