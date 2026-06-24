"""Agent 2 — Standards.

For each parameter, calls the grounding tools (get_bis_limit / evaluate_sample via the
MCP data layer) and reports exactly which values breach BIS 10500 and by how much. It may
only state limits a tool returned — this is where hallucinated thresholds are designed out.
It also pulls the area's official readings for context.
"""

from __future__ import annotations

from ..data_layer import evaluate_sample, get_area_readings, overall_verdict
from .base import Agent, AgentContext, AgentTool


class StandardsAgent(Agent):
    name = "standards"
    title = "Checking against BIS 10500"

    def __init__(self) -> None:
        self._evaluate = AgentTool("evaluate_sample", evaluate_sample)
        self._area = AgentTool("get_area_readings", get_area_readings)

    def run(self, ctx: AgentContext) -> None:
        def _do() -> str:
            parsed = ctx.state["parsed"]
            params = {r.key: r.value for r in parsed.readings}

            evaluations = self._evaluate(ctx, params=params)
            breaches = [e for e in evaluations if e["status"] != "safe"]
            verdict = overall_verdict(evaluations)

            area = self._area(ctx, pincode=parsed.pincode)

            ctx.state["evaluations"] = evaluations
            ctx.state["breaches"] = breaches
            ctx.state["verdict"] = verdict
            ctx.state["area"] = area

            # Emit a cited claim for every non-safe parameter — each carries its BIS receipt.
            claims = ctx.state.setdefault("claims", [])
            for ev in evaluations:
                if ev["status"] == "safe":
                    continue
                claims.append(
                    {
                        "id": f"std:{ev['key']}",
                        "stage": "standards",
                        "kind": "limit",
                        "text": ev["message"],
                        "citation": ev["citation"],
                    }
                )

            n_breach = sum(1 for e in evaluations if e["status"] == "breach")
            n_concern = sum(1 for e in evaluations if e["status"] == "concern")
            return (
                f"Verdict {verdict}: {n_breach} breach(es), {n_concern} above-desirable; "
                f"area data {'available' if area.get('available') else 'unavailable'}."
            )

        self._timed(ctx, _do)
